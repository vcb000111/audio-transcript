import argparse
import json
import torch
import re
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# Định dạng thời gian SRT (HH:MM:SS,mmm)
def format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def translate_batch_with_retry(model, tokenizer, batch_texts, retries=3):
    system_prompt = (
        "You are a professional JAV subtitle translator. Translate Japanese to Vietnamese smoothly, "
        "retaining JAV adult slang, terms, and context naturally. "
        "Input is a JSON array of Japanese lines. Output MUST be a JSON array of Vietnamese translated lines of the exact same length. "
        "Output ONLY a valid JSON array of strings (e.g. [\"Xin chào\", \"Tạm biệt\"]). "
        "No explanations, no markdown codeblocks, no extra text."
    )
    
    prompt = json.dumps(batch_texts, ensure_ascii=False)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    model_inputs = tokenizer([text], return_tensors="pt").to(model.device)
    
    for attempt in range(retries):
        try:
            # Dùng nhiệt độ thấp hơn khi thử lại để tăng độ ổn định
            temp = 0.1 if attempt == retries - 1 else 0.4
            
            generated_ids = model.generate(
                **model_inputs,
                max_new_tokens=2048,
                do_sample=True,
                temperature=temp,
                top_p=0.9
            )
            generated_ids = [
                output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
            ]
            response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            
            # Trích xuất JSON từ phản hồi (đề phòng mô hình bọc trong ```json)
            json_match = re.search(r"(\[.*\])", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)
                
            translated_list = json.loads(response)
            
            if isinstance(translated_list, list) and len(translated_list) == len(batch_texts):
                return translated_list
            else:
                print(f"[LLM] Cảnh báo thử lại lần {attempt+1}: Độ dài kết quả dịch ({len(translated_list)}) khác đầu vào ({len(batch_texts)}).")
        except Exception as e:
            print(f"[LLM] Lỗi parse JSON tại lần thử {attempt+1}: {e}")
            
    print("[LLM] Thất bại khi dịch lô này sau tất cả các lần thử. Fallback giữ nguyên bản tiếng Nhật.")
    return batch_texts

def main():
    parser = argparse.ArgumentParser(description="Translate Japanese text to Vietnamese using Qwen 2.5 7B")
    parser.add_argument("--input", required=True, help="Đường dẫn file JSON bóc băng tạm")
    parser.add_argument("--output", required=True, help="Đường dẫn file SRT đầu ra")
    args = parser.parse_args()

    print("[LLM] Đang cấu hình BitsAndBytes 4-bit...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16
    )

    model_name = "Qwen/Qwen2.5-7B-Instruct"
    print(f"[LLM] Đang tải tokenizer và model: {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto"
    )

    with open(args.input, "r", encoding="utf-8") as f:
        segments = json.load(f)

    if not segments:
        print("[LLM] Không có phân đoạn thoại nào cần dịch.")
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("")
        return

    print(f"[LLM] Bắt đầu dịch {len(segments)} câu thoại theo lô (Batch size = 25)...")
    
    # Chia lô 25 câu
    batch_size = 25
    translated_texts = []
    
    for i in range(0, len(segments), batch_size):
        batch = segments[i:i+batch_size]
        batch_texts = [seg["text"] for seg in batch]
        
        print(f"[LLM] Dịch từ câu {i+1} đến {min(i+batch_size, len(segments))}...")
        translated_batch = translate_batch_with_retry(model, tokenizer, batch_texts)
        translated_texts.extend(translated_batch)

    # Ghi file SRT
    print(f"[LLM] Ghi kết quả dịch ra file SRT: {args.output}")
    with open(args.output, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(segments):
            srt_idx = idx + 1
            start_str = format_srt_time(seg["start"])
            end_str = format_srt_time(seg["end"])
            
            # Đề phòng lỗi thiếu hụt dòng dịch
            vn_text = translated_texts[idx] if idx < len(translated_texts) else seg["text"]
            
            f.write(f"{srt_idx}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{vn_text}\n\n")
            
    print("[LLM] Hoàn thành dịch thuật và tạo file SRT.")

if __name__ == "__main__":
    main()
