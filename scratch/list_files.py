from huggingface_hub import HfApi
api = HfApi()
try:
    files = api.list_repo_files(repo_id="bartowski/Qwen2.5-14B-Instruct-GGUF")
    print("Files in bartowski/Qwen2.5-14B-Instruct-GGUF:")
    for file in files:
        if "q8_0" in file.lower():
            print(file)
except Exception as e:
    print("Error:", e)
