import os
import time
import requests

HUB_URL = "http://127.0.0.1:8000"

def run_real_gpu_test():
    print("=== BẮT ĐẦU TEST THỰC TẾ TRÊN VAST.AI ===")
    
    # 0. Chuẩn bị file video mẫu
    video_filename = "real_test_video.mp4"
    if not os.path.exists(video_filename):
        print(f"Đang tạo file video mẫu hợp lệ '{video_filename}' (chứa 3 giây âm thanh im lặng)...")
        # Sinh file WAV chuẩn 3 giây để FFmpeg/Whisper giải mã được
        import struct
        duration_sec = 3
        sample_rate = 16000
        num_samples = duration_sec * sample_rate
        num_channels = 1
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = num_samples * block_align
        
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + data_size,
            b'WAVE',
            b'fmt ',
            16,
            1,
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b'data',
            data_size
        )
        with open(video_filename, "wb") as f:
            f.write(header)
            f.write(b"\x00" * data_size)
            
    # 1. Gửi video lên Hub
    print("\n[Bước 1] Gửi video lên Central Hub...")
    url_upload = f"{HUB_URL}/api/jobs"
    with open(video_filename, "rb") as f:
        files = [("files", (video_filename, f, "video/mp4"))]
        res = requests.post(url_upload, files=files)
        
    if res.status_code != 200:
        print(f"LỖI: Upload thất bại: {res.text}")
        return
        
    upload_data = res.json()
    job_id = upload_data["jobs"][0]["job_id"]
    print(f"-> Gửi Job thành công! Job ID: {job_id}")
    print("-> Trình điều phối Provisioner của Hub sẽ quét và tự động thuê GPU Vast.ai trong vài giây tới...")
    
    # 2. Vòng lặp kiểm tra trạng thái tự động từ Hub
    print("\n[Bước 2] Bắt đầu theo dõi trạng thái Job xử lý...")
    url_status = f"{HUB_URL}/api/jobs/{job_id}"
    
    start_time = time.time()
    last_status = ""
    
    while True:
        try:
            res_status = requests.get(url_status, timeout=5)
            if res_status.status_code == 200:
                job_info = res_status.json()
                status = job_info.get("status", "UNKNOWN")
                
                # In trạng thái nếu có thay đổi
                if status != last_status:
                    print(f"[{int(time.time() - start_time)}s] Trạng thái hiện tại: {status}")
                    last_status = status
                    
                    if "vast_contract_id" in job_info and job_info["vast_contract_id"]:
                        print(f"   -> Đang chạy trên Vast.ai Instance ID: {job_info['vast_contract_id']}")
                
                if status == "COMPLETED":
                    print("\n=== DỊCH THUẬT THÀNH CÔNG TRÊN GPU VAST.AI ===")
                    break
                elif "FAILED" in status:
                    print(f"\n LỖI: Job thất bại với thông tin: {status}")
                    break
            elif res_status.status_code == 404:
                # Bỏ qua log lỗi 404 lúc ban đầu do job đang được tạo bất đồng bộ trong DB
                pass
            else:
                print(f"Lỗi gọi API check status: {res_status.status_code}")
        except Exception as e:
            print(f"Lỗi kết nối tới Hub: {e}")
            
        time.sleep(10)
        
    # 3. Tải kết quả phụ đề SRT về
    print("\n[Bước 3] Tải phụ đề SRT kết quả về máy local...")
    url_srt = f"{HUB_URL}/api/jobs/{job_id}/srt"
    res_srt = requests.get(url_srt)
    if res_srt.status_code == 200:
        output_filename = f"result_{job_id}.srt"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(res_srt.text)
        print(f"-> Đã lưu phụ đề dịch từ GPU về file: {output_filename}")
        print("--------------------------------------")
        print(res_srt.text[:500] + "\n...(còn tiếp)..." if len(res_srt.text) > 500 else res_srt.text)
        print("--------------------------------------")
    else:
        print(f"LỖI: Không thể tải file SRT: {res_srt.text}")

if __name__ == "__main__":
    # Kiểm tra xem uvicorn đang chạy cổng 8000 chưa
    try:
        requests.get(HUB_URL, timeout=2)
    except requests.exceptions.ConnectionError:
        print(f"LỖI: Vui lòng khởi động uvicorn trước: uvicorn app.main:app --port 8000")
        exit(1)
        
    run_real_gpu_test()
