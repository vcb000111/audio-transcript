import time
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer

def download_with_retry(repo_id, retries=5, delay=15, **kwargs):
    for attempt in range(retries):
        try:
            print(f"[Cache] Đang tải model {repo_id} (Lần thử {attempt+1}/{retries})...")
            snapshot_download(repo_id=repo_id, **kwargs)
            print(f"[Cache] Tải thành công: {repo_id}")
            return
        except Exception as e:
            print(f"[Cache] Gặp sự cố khi tải {repo_id}: {e}")
            if attempt < retries - 1:
                print(f"[Cache] Đợi {delay} giây trước khi thử lại...")
                time.sleep(delay)
                delay *= 2  # Tăng gấp đôi thời gian chờ
            else:
                raise e

def cache():
    # Tải cache model Whisper qua HuggingFace Hub snapshot (nặng ~3GB)
    download_with_retry(repo_id="Systran/faster-whisper-large-v3")
    
    model_name = "Qwen/Qwen3.5-9B-Instruct"
    print(f"[Cache] Đang tải tokenizer cho {model_name}...")
    
    # Tải trước tokenizer với cơ chế thử lại
    for attempt in range(5):
        try:
            AutoTokenizer.from_pretrained(model_name)
            break
        except Exception as e:
            print(f"[Cache] Lỗi tải tokenizer (Lần thử {attempt+1}): {e}")
            if attempt < 4:
                time.sleep(10)
            else:
                raise e
                
    # Tải model weights
    download_with_retry(
        repo_id=model_name,
        ignore_patterns=["*.msgpack", "*.h5", "*.ot"]
    )
    
    print("[Cache] Hoàn tất lưu cache toàn bộ model.")

if __name__ == "__main__":
    cache()
