import os
import sys
import time
import requests
import subprocess

HUB_URL = os.getenv("HUB_URL", "http://localhost:8000")

def claim_job():
    url = f"{HUB_URL}/api/jobs/claim"
    try:
        res = requests.post(url, timeout=10)
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 404:
            print("[Worker] Không có Job nào trong hàng đợi. Sẵn sàng nghỉ.")
            return None
        else:
            print(f"[Worker] Lỗi claim job: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[Worker] Không thể kết nối tới Hub {HUB_URL}: {e}")
    return None

def download_audio(job_id, dest_path):
    url = f"{HUB_URL}/storage/audio/{job_id}.mp3"
    print(f"[Worker] Đang tải file audio từ {url}...")
    res = requests.get(url, stream=True, timeout=60)
    res.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in res.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"[Worker] Tải file audio thành công: {dest_path}")

def send_callback(job_id, callback_token, srt_content=None, error=None):
    url = f"{HUB_URL}/api/jobs/{job_id}/callback"
    headers = {
        "Content-Type": "application/json",
        "X-Callback-Token": callback_token
    }
    payload = {}
    if srt_content is not None:
        payload["srt_content"] = srt_content
    if error is not None:
        payload["error"] = error
        
    print(f"[Worker] Gửi callback kết quả cho Job {job_id}...")
    res = requests.post(url, json=payload, headers=headers, timeout=30)
    if res.status_code == 200:
        print(f"[Worker] Callback thành công cho Job {job_id}.")
        return True
    else:
        print(f"[Worker] Lỗi callback: {res.status_code} - {res.text}")
        return False

def process_job(job):
    job_id = job["id"]
    callback_token = job["callback_token"]
    
    temp_audio = f"temp_{job_id}.mp3"
    temp_json = f"temp_{job_id}.json"
    temp_srt = f"temp_{job_id}.srt"
    
    try:
        # Bước 1: Tải audio
        download_audio(job_id, temp_audio)
        
        # Bước 2: Chạy bóc băng trong subprocess riêng biệt (giúp giải phóng hoàn toàn VRAM sau khi chạy xong)
        print(f"[Worker] Bắt đầu chạy tiến trình phụ Whisper ASR...")
        asr_cmd = [sys.executable, "whisper_transcribe.py", "--audio", temp_audio, "--output", temp_json]
        initial_prompt = job.get("initial_prompt")
        if initial_prompt:
            asr_cmd.extend(["--initial_prompt", initial_prompt])
        asr_res = subprocess.run(asr_cmd)
        if asr_res.returncode != 0:
            raise Exception("Tiến trình Whisper ASR trả về mã lỗi.")
            
        # Bước 3: Chạy dịch thuật trong subprocess riêng biệt
        print(f"[Worker] Bắt đầu chạy tiến trình phụ Qwen LLM Translation...")
        trans_cmd = [sys.executable, "qwen_translate.py", "--input", temp_json, "--output", temp_srt]
        trans_res = subprocess.run(trans_cmd)
        if trans_res.returncode != 0:
            raise Exception("Tiến trình Qwen Translation trả về mã lỗi.")
            
        # Đọc kết quả SRT
        if not os.path.exists(temp_srt):
            raise Exception("Không tìm thấy file phụ đề SRT kết quả.")
            
        with open(temp_srt, "r", encoding="utf-8") as f:
            srt_content = f.read()
            
        # Bước 4: Gửi trả phụ đề về Hub
        send_callback(job_id, callback_token, srt_content=srt_content)
        
    except Exception as e:
        print(f"[Worker] Lỗi nghiêm trọng khi xử lý Job {job_id}: {e}")
        # Báo cáo lỗi trực tiếp về Hub để Hub cập nhật trạng thái và hủy máy ảo ngay lập tức
        try:
            send_callback(job_id, callback_token, error=str(e))
        except Exception as cb_err:
            print(f"[Worker] Không thể gửi callback báo lỗi về Hub: {cb_err}")
    finally:
        # Dọn dẹp file tạm
        for temp_file in (temp_audio, temp_json, temp_srt):
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as clean_err:
                    print(f"[Worker] Lỗi dọn dẹp file {temp_file}: {clean_err}")

def main():
    print("[Worker] Bắt đầu khởi chạy Worker Daemon...")
    while True:
        job = claim_job()
        if not job:
            break
            
        print(f"[Worker] Nhận Job mới để xử lý: ID {job['id']}")
        process_job(job)
        print(f"[Worker] Hoàn thành Job {job['id']}. Tiếp tục quét hàng đợi...")
        time.sleep(2)
        
    print("[Worker] Hết công việc. Kết thúc chương trình.")

if __name__ == "__main__":
    main()
