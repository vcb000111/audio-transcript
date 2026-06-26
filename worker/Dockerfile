FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime

# Cài đặt FFmpeg và Git
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài đặt các thư viện Python
RUN pip install --no-cache-dir \
    faster-whisper \
    transformers \
    bitsandbytes \
    accelerate \
    requests \
    huggingface_hub \
    hf-transfer

# Bật hf-transfer để tăng tốc download model trong quá trình build Docker
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# Copy file cache và tải trước các model weights về cache của image
COPY cache_models.py /app/
RUN python cache_models.py

# Copy mã nguồn xử lý của Worker vào container
COPY whisper_transcribe.py /app/
COPY qwen_translate.py /app/
COPY handler.py /app/

# Cấu hình biến môi trường mặc định cho Hub URL
ENV HUB_URL=http://localhost:8000

# Chạy file handler điều phối
CMD ["python", "handler.py"]
