FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-devel

# Cấu hình biến môi trường NVIDIA và CUDA để container nhận dạng GPU khi chạy trên Vast.ai
ENV PATH=/usr/local/nvidia/bin:/usr/local/cuda/bin:${PATH}
ENV LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64:/usr/local/cuda/targets/x86_64-linux/lib:${LD_LIBRARY_PATH}
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Tránh hộp thoại cấu hình tzdata tương tác gây treo tiến trình build
ENV DEBIAN_FRONTEND=noninteractive

# Cài đặt FFmpeg, Git, CMake và các công cụ biên dịch C++
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    cmake \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài đặt các thư viện Python gộp chung để tránh pip tự động cài đè torchaudio/torchvision
RUN pip install --no-cache-dir \
    torch==2.1.2 \
    torchaudio==2.1.2 \
    torchvision==0.16.2 \
    faster-whisper==1.2.1 \
    transformers==4.40.2 \
    bitsandbytes==0.42.0 \
    accelerate==0.29.3 \
    requests==2.31.0 \
    huggingface_hub==0.23.0 \
    hf-transfer==0.1.6 \
    --extra-index-url https://download.pytorch.org/whl/cu121

# Bật hf-transfer để tăng tốc download model trong quá trình build Docker
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# Thiết lập biến môi trường biên dịch CUDA cho llama-cpp-python
# Chỉ định cứng các kiến trúc CUDA (80;86;89) để build thành công trên GitHub runner không có GPU
ENV CMAKE_ARGS="-DGGML_CUDA=on -DLLAMA_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=80;86;89"
RUN pip install llama-cpp-python --force-reinstall --upgrade --no-cache-dir

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
