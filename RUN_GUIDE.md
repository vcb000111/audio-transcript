# HƯỚNG DẪN VẬN HÀNH DỰ ÁN HÀNG NGÀY (DAILY OPERATIONS)

Tài liệu này hướng dẫn các bước khởi động và vận hành hệ thống dịch thuật SubtitleVastAI mỗi ngày khi khởi động lại máy tính.

---

## 🛠️ BƯỚC 1: KÍCH HOẠT ĐƯỜNG TRUYỀN CÔNG KHAI (TUNNEL)
Do Spoke Worker chạy trên máy ảo GPU Vast.ai cần gửi kết quả dịch ngược về máy sếp, sếp cần mở một cổng ngrok công khai:
1. Mở Terminal mới và chạy lệnh khởi tạo ngrok:
   ```bash
   ngrok http 8000
   ```
2. Copy địa chỉ HTTPS ngrok mới cấp (ví dụ: `https://xxxx.ngrok-free.dev`).
3. Mở file `.env` ở thư mục gốc dự án và cập nhật lại biến `HUB_PUBLIC_URL`:
   ```env
   HUB_PUBLIC_URL=https://xxxx.ngrok-free.dev
   ```

---

## 🚀 BƯỚC 2: KHỞI ĐỘNG TIẾN TRÌNH CENTRAL HUB (HUB SERVER)
Chạy lệnh khởi động máy chủ FastAPI Uvicorn tại local để làm trung tâm tiếp nhận job và điều phối máy ảo:
1. Mở Terminal tại thư mục dự án `D:\Projects\SubtitleVastAI`.
2. Chạy lệnh khởi động:
   ```powershell
   uvicorn app.main:app --port 8000 --reload
   ```
*Mẹo: Giữ nguyên Terminal này chạy ngầm suốt quá trình làm việc.*

---

## 🎬 BƯỚC 3: GỬI VIDEO VÀ KIỂM THỬ DỊCH PHỤ ĐỀ
Để gửi video dịch thử nghiệm và tự động theo dõi tiến độ thuê máy ảo, chạy bóc băng và dịch thuật:
1. Đảm bảo file video cần dịch đã được đặt đúng đường dẫn test.
2. Chạy lệnh kiểm thử tích hợp:
   ```powershell
   $env:PYTHONIOENCODING="utf-8"; python test_real_gpu.py
   ```
3. Sau khi chạy xong, file phụ đề Việt hóa `.srt` sẽ tự động được tải về lưu trữ tại thư mục gốc của sếp.

---

## 🧹 BƯỚC 4: DỌN DẸP CUỐI NGÀY (TRÁNH PHÁT SINH CHI PHÍ VAST.AI)
Trước khi tắt máy hoặc khi dự án gặp sự cố, luôn dọn dẹp để tránh bị Vast.ai tiếp tục tính tiền các máy ảo chạy ngầm hoặc máy ảo ở trạng thái stopped:
1. Hủy toàn bộ các instance đang thuê trên tài khoản Vast.ai:
   ```powershell
   python destroy_all.py
   ```
2. Dọn dẹp hàng đợi công việc bị kẹt trong CSDL SQLite ở local (nếu cần thiết):
   ```powershell
   python clear_db.py
   ```

---

## 📈 CÔNG CỤ THEO DÕI BUILD DOCKER (CI/CD)
Khi sếp push code mới lên GitHub và muốn kiểm tra trạng thái build Docker image mà không cần mở trình duyệt:
```powershell
python check_github_logs.py
```
*(Yêu cầu đã cấu hình `GITHUB_TOKEN` trong `.env` để xem log chi tiết).*
