# AI Translation Serverless Pipeline (Vast.ai)

Hệ thống dịch thuật tự động video tiếng Nhật sang phụ đề tiếng Việt (.srt) sử dụng Faster-Whisper (ASR) và Qwen 2.5 7B (LLM) chạy trên hạ tầng GPU serverless của Vast.ai.

## Kiến trúc hệ thống
Hệ thống hoạt động theo mô hình **Hub-and-Spoke** để tối ưu hóa chi phí (Scale-to-zero):
- **Central Hub (Thư mục `/app`):** Chạy 24/7 trên VPS giá rẻ. FastAPI server đóng vai trò API Gateway nhận video (hỗ trợ tải lên hàng loạt), trích xuất âm thanh (qua FFmpeg), lưu trữ hàng đợi công việc vào SQLite và điều phối Vast.ai.
- **Spoke Worker (Thư mục `/worker`):** Được thuê động (RTX 4090) thông qua API Vast.ai khi có hàng đợi PENDING. Worker khởi động Docker, kéo audio, bóc băng tiếng Nhật, dịch thuật sang tiếng Việt mượt mà qua Qwen 2.5 7B 4-bit, callback trả kết quả phụ đề và tự giải phóng máy.

---

## Cấu trúc thư mục
```
├── app/                  # Mã nguồn Central Hub (API & DB & Provisioner)
│   ├── database.py       # Cấu hình SQLite và các hàm CRUD
│   ├── main.py           # API chính của FastAPI
│   └── provisioner.py    # Daemon tự động điều phối GPU Vast.ai
├── worker/               # Mã nguồn Worker chạy GPU Node
│   ├── cache_models.py   # Script tải trước model trong lúc build Docker
│   ├── whisper_transcribe.py  # Script ASR bóc băng tiếng Nhật (subprocess)
│   ├── qwen_translate.py      # Script LLM dịch tiếng Việt 4-bit (subprocess)
│   ├── handler.py        # Trình điều phối chạy chính trong Docker
│   └── Dockerfile        # Dockerfile đóng gói Worker
├── .github/              # Thư mục cấu hình CI/CD cho GitHub
│   └── workflows/
│       └── build-worker.yaml  # Workflow tự động build và push Docker image
├── .env                  # Lưu cấu hình môi trường
└── README.md
```

---

## Hướng dẫn cài đặt & Khởi chạy

### 1. Yêu cầu hệ thống
- Máy chủ Hub: Cài đặt Python 3.10+, FFmpeg và SQLite.
- Vast.ai: Đăng ký tài khoản và lấy API Key tại Account Settings.

### 2. Cấu hình file `.env` tại thư mục gốc
Tạo file `.env` và khai báo các giá trị sau:
```env
VAST_API_KEY=your_vast_api_key_here
HUB_PUBLIC_URL=http://your_public_ip_or_domain:8000
DATABASE_URL=sqlite:///app.db
MAX_CONCURRENT_GPUS=100
STORAGE_DIR=./storage
WORKER_DOCKER_IMAGE=docker.io/library/vast-translator:latest
```

### 3. Chạy Central Hub
Cài đặt thư viện:
```bash
pip install fastapi uvicorn requests python-dotenv
```
Khởi chạy server FastAPI:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Server sẽ chạy cổng `8000` và tự động khởi động trình điều phối nền (Provisioner) để quản lý Vast.ai.

### 4. Build Docker Worker
Trong thư mục `/worker`, tiến hành build Docker image:
```bash
docker build -t <dockerhub_username>/vast-translator:latest .
docker push <dockerhub_username>/vast-translator:latest
```
*Lưu ý: Quá trình build Docker sẽ chạy script `cache_models.py` tải sẵn model Faster-Whisper và Qwen 2.5 7B. Dung lượng image sẽ khá lớn (khoảng 15GB), nhưng bù lại thời gian khởi động (cold start) trên Vast.ai sẽ giảm từ 8 phút xuống dưới 1 phút.*
