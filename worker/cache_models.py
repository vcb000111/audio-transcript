import os
from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer

def cache():
    print("[Cache] Đang tải sẵn model Faster-Whisper (large-v3)...")
    # Tải cache model Whisper
    WhisperModel("large-v3", device="cpu", compute_type="float32", download_only=True)
    
    print("[Cache] Đang tải sẵn model Qwen/Qwen2.5-7B-Instruct...")
    model_name = "Qwen/Qwen2.5-7B-Instruct"
    # Tải tokenizer
    AutoTokenizer.from_pretrained(model_name)
    # Tải toàn bộ model weights lưu cache HF (tránh load vào RAM gây OOM khi build Docker)
    snapshot_download(repo_id=model_name, ignore_patterns=["*.msgpack", "*.h5", "*.ot"])
    
    print("[Cache] Hoàn tất lưu cache toàn bộ model.")

if __name__ == "__main__":
    cache()
