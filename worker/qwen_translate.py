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

def translate_single_text(model, tokenizer, text, history_context=[], retries=2):
    system_prompt = (
        "Bạn là một dịch giả phụ đề JAV chuyên nghiệp. Hãy dịch câu thoại tiếng Nhật sau sang tiếng Việt một cách tự nhiên, trôi chảy.\n"
        "Lưu ý giữ đúng ngữ cảnh người lớn, từ lóng JAV tự nhiên, xưng hô phù hợp (anh - em, em - anh, tôi - cô,...).\n"
        "Chỉ trả về bản dịch tiếng Việt duy nhất. Tuyệt đối không giải thích, không viết ghi chú, không markdown, không lặp lại câu gốc."
    )
    
    context_str = ""
    if history_context:
        context_str = "Các câu thoại và bản dịch trước đó để tham khảo ngữ cảnh:\n" + "\n".join(history_context) + "\n\n"
        
    prompt = f"{context_str}Hãy dịch câu thoại tiếng Nhật này: {text}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    text_in = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    model_inputs = tokenizer([text_in], return_tensors="pt").to(model.device)
    
    for attempt in range(retries):
        try:
            generated_ids = model.generate(
                **model_inputs,
                max_new_tokens=256,
                do_sample=True,
                temperature=0.1 if attempt == retries - 1 else 0.3,
                top_p=0.9
            )
            generated_ids = [
                output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
            ]
            response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            
            # Làm sạch phản hồi
            response = response.strip('"\'')
            if response and response != text:
                return response
        except Exception as e:
            print(f"[LLM] Lỗi khi dịch câu '{text}' ở lần thử {attempt+1}: {e}")
            
    return text  # Fallback trả về câu gốc nếu thất bại

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

    print(f"[LLM] Bắt đầu dịch {len(segments)} câu thoại từng câu một với ngữ cảnh trượt...")
    translated_texts = []
    
    for idx, seg in enumerate(segments):
        text = seg["text"]
        # Lấy tối đa 3 câu dịch gần nhất làm ngữ cảnh
        history = []
        start_idx = max(0, idx - 3)
        for h_idx in range(start_idx, idx):
            orig = segments[h_idx]["text"]
            trans = translated_texts[h_idx]
            history.append(f"Gốc: {orig} -> Dịch: {trans}")
            
        print(f"[LLM] ({idx+1}/{len(segments)}) Dịch: {text}")
        translated_text = translate_single_text(model, tokenizer, text, history)
        translated_texts.append(translated_text)
        print(f"      -> Kết quả: {translated_text}")

    # Ghi file SRT
    print(f"[LLM] Ghi kết quả dịch ra file SRT: {args.output}")
    with open(args.output, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(segments):
            srt_idx = idx + 1
            start_str = format_srt_time(seg["start"])
            end_str = format_srt_time(seg["end"])
            
            vn_text = translated_texts[idx]
            
            f.write(f"{srt_idx}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{vn_text}\n\n")
            
    print("[LLM] Hoàn thành dịch thuật và tạo file SRT.")

if __name__ == "__main__":
    main()
