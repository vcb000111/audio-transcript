# Lịch sử thay đổi (Changelog)

Tất cả các thay đổi quan trọng của dự án sẽ được ghi nhận tại đây.

## [1.0.0] - 2026-06-26

### 🌐 Tính năng chính (Tier 1 & Tier 2)
- Khởi tạo kiến trúc Hub-and-Spoke cho hệ thống dịch thuật tự động sử dụng Vast.ai.
- Xây dựng Central Hub API sử dụng FastAPI để nhận video hàng loạt (Bulk Upload), tự động trích xuất âm thanh và quản lý hàng đợi.
- Thiết lập cơ chế điều phối (Provisioner) tự động phát hiện hàng đợi, thuê máy RTX 4090 giá rẻ và tự động hủy/tắt máy khi rảnh.
- Phát triển Spoke Worker tích hợp bóc băng bằng Faster-Whisper và dịch thuật tiếng Việt qua Qwen 2.5 7B Instruct (bitsandbytes 4-bit).
- Xây dựng Dockerfile cho Worker hỗ trợ tải trước và lưu cache model để triệt tiêu thời gian cold-start.
- Bổ sung cơ chế tự sửa lỗi tự động, tự động quét dọn và hủy các máy ảo bị lỗi, khởi động lâu hoặc chạy rảnh rỗi trên đám mây để tối ưu chi phí.
- Tích hợp ghi vết mã số máy ảo (Instance ID) ngay khi thuê thành công để tránh việc thuê trùng lặp.
- Hỗ trợ cập nhật địa chỉ máy chủ công khai của Hub thời gian thực khi sử dụng các dịch vụ tạo đường truyền (ngrok/tunnel).

### 🛠️ Tối ưu hóa & Sửa lỗi (Tier 3)
- Tối ưu hóa phân tách tiến trình Whisper và Qwen thành các subprocess riêng biệt để giải phóng hoàn toàn bộ nhớ GPU (VRAM < 14GB), ngăn ngừa lỗi phân mảnh CUDA.
- Bổ sung xác thực bảo mật token callback tránh các cuộc tấn công giả mạo kết quả phụ đề.
- Tự động kiểm tra tính hợp lệ của file audio (> 0 bytes) trước khi xếp hàng đợi xử lý.
- Tự động hóa CI/CD tự động build Docker image worker qua GitHub Actions.
- Khắc phục lỗi dừng đột ngột của tiến trình dịch thuật trên máy ảo bằng cách đồng bộ hóa phiên bản các thư viện xử lý âm thanh và hình ảnh tương thích với nhân tính toán GPU.
- Sửa lỗi không tải được tệp tin video kiểm thử do định dạng tệp tin giả lập bị lỗi bằng cách tự động sinh tệp tin âm thanh im lặng chuẩn.
- Tạo công cụ dọn dẹp nhanh hàng đợi công việc bị kẹt trong cơ sở dữ liệu.
- Tối ưu hóa điều kiện lựa chọn máy ảo: chỉ thuê từ các máy chủ uy tín, độ tin cậy trên 95% và tốc độ truyền tải cao.
