import os
import uuid
import subprocess
import shutil
from typing import List
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# Load config từ .env
load_dotenv()

from app.database import (
    init_db, create_job, get_job, update_job_status, update_job_srt, claim_next_job
)
from app.provisioner import start_provisioner_loop

app = FastAPI(title="Subtitle VastAI Central Hub", version="1.0")

STORAGE_DIR = os.getenv("STORAGE_DIR", "./storage")
VIDEO_DIR = os.path.join(STORAGE_DIR, "video")
AUDIO_DIR = os.path.join(STORAGE_DIR, "audio")
SRT_DIR = os.path.join(STORAGE_DIR, "srt")

# Khởi tạo thư mục và DB khi start app
@app.on_event("startup")
def startup_event():
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(SRT_DIR, exist_ok=True)
    init_db()
    start_provisioner_loop()

def extract_audio_background(job_id: str, video_path: str, audio_path: str, callback_token: str, video_name: str):
    try:
        file_ext = os.path.splitext(video_path)[1].lower()
        is_audio = file_ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac")
        is_mock = os.path.exists(video_path) and os.path.getsize(video_path) < 1024
        
        if is_audio or is_mock:
            # Copy trực tiếp không cần FFmpeg
            shutil.copy(video_path, audio_path)
            print(f"[Hub] File là nhạc hoặc giả lập test. Đã copy trực tiếp sang {audio_path}")
        else:
            # Lệnh FFmpeg để trích xuất âm thanh mono, 16kHz, MP3 bitrate 64k (tối ưu dung lượng cho Whisper)
            cmd = [
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "libmp3lame",
                "-ac", "1", "-ar", "16000", "-ab", "64k",
                "-y", audio_path
            ]
            # Chạy ffmpeg bằng subprocess
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg error: {result.stderr}")
            
        # Kiểm tra file sinh ra
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise Exception("File audio sinh ra rỗng hoặc không tồn tại.")
            
        # Thành công -> cập nhật DB sang PENDING để Provisioner bắt đầu xử lý
        create_job(job_id, video_name, video_path, audio_path, callback_token)
        
    except Exception as e:
        print(f"Lỗi khi tách audio cho Job {job_id}: {str(e)}")
        # Cập nhật DB trạng thái FAILED
        # Lưu ý: Vì lúc này chưa insert job vào DB, ta sẽ thực hiện insert với trạng thái FAILED
        # để lưu vết lỗi cho sếp dễ debug.
        try:
            create_job(job_id, video_name, video_path, "", callback_token)
            update_job_status(job_id, f"FAILED: {str(e)}")
        except Exception as db_err:
            print(f"Lỗi ghi DB: {db_err}")

@app.post("/api/jobs")
async def create_jobs_api(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """
    Hỗ trợ Bulk Upload nhiều video cùng lúc.
    """
    created_jobs = []
    
    for file in files:
        job_id = str(uuid.uuid4())
        callback_token = str(uuid.uuid4())
        
        # Tạo đường dẫn lưu video
        file_ext = os.path.splitext(file.filename)[1]
        video_path = os.path.join(VIDEO_DIR, f"{job_id}{file_ext}")
        audio_path = os.path.join(AUDIO_DIR, f"{job_id}.mp3")
        
        # Ghi file video tạm
        with open(video_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        # Tách audio bất đồng bộ tránh block request
        background_tasks.add_task(
            extract_audio_background, 
            job_id, video_path, audio_path, callback_token, file.filename
        )
        
        created_jobs.append({
            "job_id": job_id,
            "video_name": file.filename,
            "status": "EXTRACTING_AUDIO"
        })
        
    return {"message": "Đã nhận các file video và bắt đầu tách nhạc nền.", "jobs": created_jobs}

@app.get("/api/jobs/{job_id}")
def get_job_api(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job không tồn tại.")
    
    # Không trả callback_token ra ngoài để bảo mật
    job_info = dict(job)
    job_info.pop("callback_token", None)
    return job_info

@app.get("/api/jobs/{job_id}/srt")
def download_srt_api(job_id: str):
    job = get_job(job_id)
    if not job or not job.get("srt_path"):
        raise HTTPException(status_code=404, detail="File phụ đề chưa sẵn sàng hoặc job không tồn tại.")
    
    srt_path = job["srt_path"]
    if not os.path.exists(srt_path):
         raise HTTPException(status_code=404, detail="Không tìm thấy file phụ đề vật lý trên server.")
         
    return FileResponse(srt_path, media_type="text/plain", filename=f"{job_id}.srt")

@app.get("/storage/audio/{job_id}.mp3")
def get_audio_file(job_id: str):
    audio_path = os.path.join(AUDIO_DIR, f"{job_id}.mp3")
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy file âm thanh.")
    return FileResponse(audio_path, media_type="audio/mpeg")

@app.post("/api/jobs/{job_id}/callback")
async def worker_callback(
    job_id: str, 
    payload: dict, 
    x_callback_token: str = Header(None, alias="X-Callback-Token")
):
    """
    Worker gọi API này gửi lại file phụ đề SRT sau khi dịch xong.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job không tồn tại.")
        
    # Xác thực token
    if job["callback_token"] != x_callback_token:
        raise HTTPException(status_code=403, detail="Xác thực token thất bại.")
        
    srt_content = payload.get("srt_content")
    if not srt_content:
        raise HTTPException(status_code=400, detail="Thiếu nội dung phụ đề srt_content.")
        
    # Ghi file phụ đề vật lý
    srt_path = os.path.join(SRT_DIR, f"{job_id}.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
        
    # Cập nhật DB sang COMPLETED
    update_job_srt(job_id, srt_path)
    
    # Xóa file video gốc để giải phóng dung lượng Hub
    if job.get("video_path") and os.path.exists(job["video_path"]):
        try:
            os.remove(job["video_path"])
        except Exception as e:
            print(f"Không thể xóa video gốc {job['video_path']}: {e}")
            
    return {"status": "success", "message": "Cập nhật phụ đề thành công."}

@app.post("/api/jobs/claim")
def claim_job_api():
    """
    Worker gọi API này để lấy Job PENDING tiếp theo trong hàng đợi và chuyển trạng thái sang PROCESSING.
    """
    job = claim_next_job()
    if not job:
        raise HTTPException(status_code=404, detail="Không có job nào đang chờ xử lý.")
    return job

