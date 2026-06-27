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

def contains_foreign_script(text: str) -> bool:
    """Kiểm tra xem chuỗi có chứa chữ Hán (Trung/Nhật Kanji), Hiragana, Katakana, chữ Thái hay chữ Hàn hay không"""
    pattern = re.compile(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u0e00-\u0e7f\uac00-\ud7a3]")
    return bool(pattern.search(text))

def clean_translation_trash(text: str) -> str:
    """Loại bỏ tag suy nghĩ <think>...</think>, tiền tố giải thích và dấu ngoặc kép thừa của LLM"""
    # 1. Loại bỏ tag <think>...</think> nếu có
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    # 2. Loại bỏ các tiền tố giải thích phổ biến
    text = re.sub(r"^(dịch câu thoại sang tiếng việt là|bản dịch tiếng việt là|dịch là|bản dịch là|câu thoại này dịch là)[:\s]*", "", text, flags=re.IGNORECASE).strip()
    # 3. Loại bỏ dấu ngoặc kép/đơn bọc ngoài
    text = text.strip('"\'')
    return text

def detect_speaker_info(text: str) -> str:
    """Phân tích câu thoại tiếng Nhật để đoán vai vế người nói và hướng dẫn xưng hô"""
    # Em gái gọi anh trai
    if any(k in text for k in ["お兄ちゃん", "おにいちゃん", "兄ちゃん", "お兄様"]):
        return (
            "VAI VẾ NHÂN VẬT: Người nói là EM GÁI (Rino), đang nói chuyện với ANH TRAI.\n"
            "QUY TẮC XƯNG HÔ: Em gái gọi anh trai là 'Anh' hoặc 'Anh hai' và xưng 'Em'. Không dùng 'Tôi', 'Cậu', 'Mày'."
        )
    # Anh trai tự sự hoặc nói với em gái (dùng boku, ore)
    if any(k in text for k in ["僕", "ぼく", "俺", "おれ"]):
        if "妹" in text:
            return (
                "VAI VẾ NHÂN VẬT: Người nói là ANH TRAI đang giới thiệu/nói về em gái (Rino).\n"
                "QUY TẮC XƯNG HÔ: Xưng 'Tôi' hoặc 'Anh' khi nói về em gái. Ví dụ: 'Em gái tôi, Rino'."
            )
        return (
            "VAI VẾ NHÂN VẬT: Người nói là ANH TRAI, đang nói với em gái (Rino) hoặc đang tự sự thầm.\n"
            "QUY TẮC XƯNG HÔ: Nếu nói với em gái, xưng 'Anh' và gọi em gái là 'Em' hoặc 'Rino'. Nếu đang tự thoại thầm (suy nghĩ trong đầu), xưng 'Tôi' hoặc 'Anh'."
        )
    # Em gái xưng watashi
    if "私" in text or "わたし" in text:
        return (
            "VAI VẾ NHÂN VẬT: Người nói là EM GÁI (Rino) nói với anh trai.\n"
            "QUY TẮC XƯNG HÔ: Gọi anh trai là 'Anh'/'Anh hai', xưng 'Em'."
        )
    
    return "VAI VẾ NHÂN VẬT: Cuộc trò chuyện thân mật trong gia đình giữa hai anh em. Hãy dịch xưng hô tự nhiên là 'Anh' - 'Em'."

def translate_single_text(model, tokenizer, text, history_context=[], retries=2):
    speaker_hint = detect_speaker_info(text)
    system_prompt = (
        "Bạn là một biên dịch viên phụ đề phim gia đình/tình cảm Nhật Bản sang tiếng Việt chuyên nghiệp.\n"
        "Hãy dịch câu thoại tiếng Nhật được yêu cầu sang tiếng Việt một cách tự nhiên, trôi chảy, đúng văn phong phim ảnh Việt Nam.\n"
        "RÀNG BUỘC ĐẦU RA:\n"
        "- Bản dịch bắt buộc phải là 100% TIẾNG VIỆT tự nhiên, thuần Việt, dễ hiểu.\n"
        "- Tuyệt đối KHÔNG chứa bất kỳ ký tự chữ Hán (Trung/Nhật), chữ Thái, chữ Hàn, hay chữ viết lạ nào khác.\n"
        "- Chỉ trả về duy nhất câu đã dịch sang tiếng Việt, không giải thích, không viết ghi chú, không markdown, không lặp lại câu gốc."
    )
    
    context_str = ""
    if history_context:
        context_str = "Các câu thoại trước đó để tham khảo ngữ cảnh diễn tiến:\n" + "\n".join(history_context) + "\n\n"
        
    prompt = (
        f"{context_str}"
        f"{speaker_hint}\n"
        f"Hãy dịch câu thoại tiếng Nhật này sang tiếng Việt: {text}"
    )
    
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
            
            # Làm sạch phản hồi bằng bộ lọc
            response = clean_translation_trash(response)
            
            # Kiểm tra xem bản dịch có chứa chữ nước ngoài hay câu từ chối dịch không
            is_refusal = any(k in response for k in ["không thể", "yêu cầu", "phù hợp", "từ chối", "đề xuất", "chính sách"])
            
            if response and response != text and not contains_foreign_script(response) and not is_refusal:
                return response
            else:
                print(f"[LLM] Cảnh báo: Bản dịch bị từ chối hoặc chứa chữ ngoại lai ở lần thử {attempt+1}: {response}")
        except Exception as e:
            print(f"[LLM] Lỗi khi dịch câu '{text}' ở lần thử {attempt+1}: {e}")
            
    # Fallback nếu bị từ chối dịch hoặc lỗi sau tất cả lần thử:
    # Dùng minimalist prompt để vượt qua bộ lọc an toàn của Qwen
    print(f"[LLM] Kích hoạt chế độ dịch tối giản (Minimalist Prompt) cho câu nhạy cảm: '{text}'")
    try:
        minimal_messages = [
            {"role": "user", "content": f"Dịch câu thoại này sang tiếng Việt: {text}"}
        ]
        text_in_min = tokenizer.apply_chat_template(minimal_messages, tokenize=False, add_generation_prompt=True)
        inputs_min = tokenizer([text_in_min], return_tensors="pt").to(model.device)
        gen_ids_min = model.generate(**inputs_min, max_new_tokens=256, temperature=0.1, do_sample=True)
        gen_ids_min = [o[len(i):] for i, o in zip(inputs_min.input_ids, gen_ids_min)]
        response_min = tokenizer.batch_decode(gen_ids_min, skip_special_tokens=True)[0].strip()
        response_min = clean_translation_trash(response_min)
        is_refusal_min = any(k in response_min for k in ["không thể", "yêu cầu", "phù hợp", "từ chối"])
        if response_min and response_min != text and not contains_foreign_script(response_min) and not is_refusal_min:
            return response_min
    except Exception as e_min:
        print(f"[LLM] Lỗi ở chế độ tối giản: {e_min}")
        
    return text  # Fallback cuối cùng trả về câu gốc

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
            # CHỈ đưa vào ngữ cảnh nếu bản dịch sạch (không chứa chữ Trung/Nhật/Thái/Hàn)
            if not contains_foreign_script(trans):
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
