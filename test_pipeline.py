import os
import time
import requests

HUB_URL = "http://127.0.0.1:8000"

def run_test():
    print("=== BẮT ĐẦU KIỂM THỬ TÍCH HỢP LOCAL ===")
    
    # 0. Chuẩn bị file video mẫu nếu chưa có
    video_filename = "test_video.mp4"
    if not os.path.exists(video_filename):
        print(f"Đang tạo file video giả lập '{video_filename}' để test...")
        with open(video_filename, "wb") as f:
            f.write(b"Gia lap du lieu video de trich xuat nhac nen")
            
    # 1. Gửi video lên Hub (Bulk Upload)
    print("\n[Bước 1] Gửi video lên Hub...")
    url_upload = f"{HUB_URL}/api/jobs"
    with open(video_filename, "rb") as f:
        files = [("files", (video_filename, f, "video/mp4"))]
        res = requests.post(url_upload, files=files)
        
    if res.status_code != 200:
        print(f"LỖI: Gửi video thất bại: {res.text}")
        return
        
    upload_data = res.json()
    jobs = upload_data.get("jobs", [])
    if not jobs:
        print("LỖI: Không nhận được thông tin Job từ Hub.")
        return
        
    job_id = jobs[0]["job_id"]
    print(f"-> Tạo Job thành công! Job ID: {job_id}")
    
    # 2. Đợi FFmpeg tách nhạc nền bất đồng bộ
    print("\n[Bước 2] Đợi 3 giây để Hub chạy tách audio trong background...")
    time.sleep(3)
    
    # 3. Giả lập Worker vào nhận Job
    print("\n[Bước 3] Giả lập Worker gọi API nhận Job (claim)...")
    url_claim = f"{HUB_URL}/api/jobs/claim"
    res_claim = requests.post(url_claim)
    
    if res_claim.status_code != 200:
        print(f"LỖI: Worker không thể nhận Job: {res_claim.text}")
        return
        
    claimed_job = res_claim.json()
    claimed_id = claimed_job["id"]
    callback_token = claimed_job["callback_token"]
    print(f"-> Worker đã nhận thành công Job ID: {claimed_id}")
    print(f"-> Nhận mã bảo mật Callback Token: {callback_token}")
    
    # 4. Giả lập Worker xử lý và gửi lại phụ đề SRT
    print("\n[Bước 4] Giả lập Worker gửi trả phụ đề SRT (callback)...")
    url_callback = f"{HUB_URL}/api/jobs/{claimed_id}/callback"
    mock_srt_content = (
        "1\n00:00:01,000 --> 00:00:04,000\n[Yamete kudasai] Sếp ơi, yamete!\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\n[Kimochi] Cảm giác tuyệt vời lắm sếp!\n"
    )
    
    headers = {
        "X-Callback-Token": callback_token
    }
    payload = {
        "srt_content": mock_srt_content
    }
    res_callback = requests.post(url_callback, json=payload, headers=headers)
    
    if res_callback.status_code != 200:
        print(f"LỖI: Gửi callback thất bại: {res_callback.text}")
        return
    print("-> Worker gửi trả phụ đề thành công.")
    
    # 5. Kiểm tra trạng thái Job trên Hub
    print("\n[Bước 5] Kiểm tra trạng thái Job từ phía Client...")
    url_status = f"{HUB_URL}/api/jobs/{job_id}"
    res_status = requests.get(url_status)
    job_info = res_status.json()
    print(f"-> Trạng thái hiện tại: {job_info.get('status')}")
    print(f"-> Đường dẫn file phụ đề lưu trên Hub: {job_info.get('srt_path')}")
    
    # 6. Tải thử file SRT về máy
    print("\n[Bước 6] Tải file phụ đề .srt về máy...")
    url_srt = f"{HUB_URL}/api/jobs/{job_id}/srt"
    res_srt = requests.get(url_srt)
    if res_srt.status_code == 200:
        print("-> Nội dung phụ đề đã tải về thành công:")
        print("--------------------------------------")
        print(res_srt.text)
        print("--------------------------------------")
        print("=== KIỂM THỬ THÀNH CÔNG 100% ===")
    else:
        print(f"LỖI: Tải phụ đề thất bại: {res_srt.text}")

if __name__ == "__main__":
    # Kiểm tra xem có đang bật Hub ở cổng 8000 hay chưa
    try:
        requests.get(HUB_URL, timeout=2)
    except requests.exceptions.ConnectionError:
        print(f"LỖI: Vui lòng khởi động server API trước: uvicorn app.main:app --port 8000")
        exit(1)
        
    run_test()
