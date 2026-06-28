from huggingface_hub import HfApi, hf_hub_download
api = HfApi()

print("Checking Systran/faster-whisper-large-v3...")
try:
    info = api.model_info("Systran/faster-whisper-large-v3")
    print("Systran/faster-whisper-large-v3 exists.")
except Exception as e:
    print("Whisper model check failed:", e)

print("Checking bartowski/Qwen2.5-14B-Instruct-GGUF...")
try:
    files = api.list_repo_files(repo_id="bartowski/Qwen2.5-14B-Instruct-GGUF")
    if "Qwen2.5-14B-Instruct-Q8_0.gguf" in files:
        print("Qwen2.5-14B-Instruct-Q8_0.gguf exists in bartowski/Qwen2.5-14B-Instruct-GGUF.")
    else:
        print("Qwen2.5-14B-Instruct-Q8_0.gguf NOT found in bartowski repo.")
except Exception as e:
    print("Qwen model check failed:", e)
