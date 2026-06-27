import os
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer

def cache():
    print("[Cache] Đang tải sẵn model Faster-Whisper (large-v3)...")
    # Tải cache model Whisper qua HuggingFace Hub snapshot (nặng ~3GB)
    snapshot_download(repo_id="Systran/faster-whisper-large-v3")
    
    print("[Cache] Đang tải sẵn model Qwen/Qwen3.5-9B-Instruct...")
    model_name = "Qwen/Qwen3.5-9B-Instruct"
    # Tải trước tokenizer
    AutoTokenizer.from_pretrained(model_name)
    # Tải toàn bộ model weights lưu cache HF (nặng ~18GB)
    snapshot_download(repo_id=model_name, ignore_patterns=["*.msgpack", "*.h5", "*.ot"])
    
    print("[Cache] Hoàn tất lưu cache toàn bộ model.")

if __name__ == "__main__":
    cache()
