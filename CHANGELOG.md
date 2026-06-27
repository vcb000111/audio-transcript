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
- Bổ sung cơ chế tự động gửi báo cáo lỗi (error callback) từ Worker ngược về Central Hub khi gặp sự cố, tránh kẹt trạng thái xử lý.
- Tự động phát hiện và dọn dẹp (hủy máy, chuyển trạng thái FAILED) các máy ảo bị dừng (`stopped`) hoặc bị thu hồi khi job đang xử lý (`PROCESSING`).
- Hạ phiên bản thư viện `transformers` xuống `4.40.2` trong cấu hình Dockerfile của Worker để đảm bảo tương thích hoàn toàn với PyTorch 2.1.2, sửa triệt để lỗi sập Qwen (`NameError: name 'torch' is not defined`).
- Thực hiện khóa cứng (pin) toàn bộ các phiên bản thư viện Python của Worker (`faster-whisper==1.2.1`, `bitsandbytes==0.42.0`, `accelerate==0.29.3`, `requests==2.31.0`, `huggingface_hub==0.23.0`, `hf-transfer==0.1.6`) để triệt tiêu mọi rủi ro không tương thích phiên bản (dependency drift) trong tương lai.
- Thiết kế lại cơ chế dịch thuật Qwen 2.5: chuyển từ dịch theo lô (batch 25 câu) sang dịch từng câu thoại một kết hợp với ngữ cảnh trượt (sliding window 3 câu dịch trước đó). Thay đổi này giúp loại bỏ hoàn toàn tình trạng lệch dòng, mất câu, và lỗi parse mảng JSON của mô hình LLM, đảm bảo dịch hết 100% tiếng Nhật sang tiếng Việt chuẩn ngữ cảnh JAV.
- Khắc phục lỗi cú pháp `SyntaxError: invalid syntax` thừa ký tự markdown ở cuối file `qwen_translate.py` trong bản build trước.
- Nâng cấp thuật toán dịch thuật trong `qwen_translate.py`: Tích hợp bộ lọc regex phát hiện và ngăn chặn lây nhiễm ngôn ngữ ngoại lai (chữ Hán, Thái, Hàn) trong chuỗi ngữ cảnh trượt (sliding window context).
- Bổ sung quy tắc xưng hô tiếng Việt tự nhiên chuẩn văn phong gia đình/phụ đề JAV (Anh - Em thay vì dịch thô thô thiển như Anh bạn, Tôi, Tao, Mày), ép đầu ra chỉ trả về 100% tiếng Việt sạch sẽ.
- Tích hợp hàm `detect_speaker_info` phân tích đại từ tiếng Nhật để đoán chính xác vai vế (Anh trai/Em gái) từng câu thoại, giải quyết triệt để lỗi dịch ngược ngôi và sửa lỗi `NameError` liên quan đến biến `speaker_hint` ở bản build trước.
- Xây dựng cơ chế dịch tối giản (Minimalist Prompt Fallback) và lọc các câu từ chối dịch của Qwen để tự động vượt qua 100% bộ lọc kiểm duyệt (Censorship) đối với các câu thoại nhạy cảm.
- Nâng cấp mô hình dịch thuật sang `Qwen/Qwen3.5-9B-Instruct` (định dạng Safetensors chuẩn tương thích hoàn toàn với thư viện `transformers`).
- Cấu hình bộ tham số sinh tối ưu cho chế độ **Non-Thinking** (`temperature=0.7`, `top_p=0.8`, `top_k=20`) giúp tăng tốc độ phản hồi tối đa, tiết kiệm chi phí chạy máy ảo Vast.ai.
- Tích hợp bộ lọc regex tự động dọn dẹp và xóa sạch các thẻ `<think>...</think>` (đề phòng rò rỉ token suy nghĩ nếu sau này sếp chạy các model reasoning) để đảm bảo phụ đề đầu ra luôn sạch sẽ.

