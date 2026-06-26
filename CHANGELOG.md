# Lịch sử thay đổi (Changelog)

Tất cả các thay đổi quan trọng của dự án sẽ được ghi nhận tại đây.

## [1.0.0] - 2026-06-26

### 🌐 Tính năng chính (Tier 1 & Tier 2)
- Khởi tạo kiến trúc Hub-and-Spoke cho hệ thống dịch thuật tự động sử dụng Vast.ai.
- Xây dựng Central Hub API sử dụng FastAPI để nhận video hàng loạt (Bulk Upload), tự động trích xuất âm thanh và quản lý hàng đợi.
- Thiết lập cơ chế điều phối (Provisioner) tự động phát hiện hàng đợi, thuê máy RTX 4090 giá rẻ và tự động hủy/tắt máy khi rảnh.
- Phát triển Spoke Worker tích hợp bóc băng bằng Faster-Whisper và dịch thuật tiếng Việt qua Qwen 2.5 7B Instruct (bitsandbytes 4-bit).
- Xây dựng Dockerfile cho Worker hỗ trợ tải trước và lưu cache model để triệt tiêu thời gian cold-start.

### 🛠️ Tối ưu hóa & Sửa lỗi (Tier 3)
- Tối ưu hóa phân tách tiến trình Whisper và Qwen thành các subprocess riêng biệt để giải phóng hoàn toàn bộ nhớ GPU (VRAM < 14GB), ngăn ngừa lỗi phân mảnh CUDA.
- Bổ sung xác thực bảo mật token callback tránh các cuộc tấn công giả mạo kết quả phụ đề.
- Tự động kiểm tra tính hợp lệ của file audio (> 0 bytes) trước khi xếp hàng đợi xử lý.
- Tự động hóa CI/CD tự động build Docker image worker qua GitHub Actions.
