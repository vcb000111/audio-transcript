import argparse
import json
import torch
import re
import os

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

def google_translate_fallback(text: str) -> str:
    """Gọi Google Translate API miễn phí làm phương án dự phòng cuối cùng để đảm bảo có tiếng Việt"""
    try:
        import requests
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "ja",
            "tl": "vi",
            "dt": "t",
            "q": text
        }
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            result = res.json()
            translated = "".join([part[0] for part in result[0] if part[0]])
            if translated:
                print(f"[LLM-FALLBACK] Dịch thành công qua Google Translate: '{text}' -> '{translated}'")
                return translated.strip()
    except Exception as e:
        print(f"[LLM-FALLBACK] Lỗi gọi Google Translate API: {e}")
    return text

def translate_single_text(model, tokenizer, text, history_context=[], retries=2):
    # Xác định loại động cơ dịch dựa trên instance của model
    is_llamacpp = False
    try:
        from llama_cpp import Llama
        if isinstance(model, Llama):
            is_llamacpp = True
    except ImportError:
        pass

    speaker_hint = detect_speaker_info(text)
    # Hướng dẫn cực kỳ nghiêm khắc cấm suy nghĩ và cấm viết thẻ think
    system_prompt = (
        "Bạn là một biên dịch viên phụ đề phim Nhật Bản sang tiếng Việt chuyên nghiệp.\n"
        "Nhiệm vụ: Dịch trực tiếp câu thoại được yêu cầu sang tiếng Việt.\n"
        "QUY TẮC BẮT BUỘC:\n"
        "- KHÔNG ĐƯỢC SUY NGHĨ. Tuyệt đối KHÔNG viết bất kỳ suy nghĩ, lập luận, phân tích hay thảo luận nào.\n"
        "- KHÔNG sử dụng thẻ <think>...</think> hoặc viết bất kỳ từ nào như 'Thinking Process', 'Thought' hay 'Analysis'.\n"
        "- Dịch thẳng sang tiếng Việt thuần túy, tự nhiên, văn phong phim ảnh.\n"
        "- Chỉ trả về duy nhất bản dịch tiếng Việt, không lặp lại câu gốc, không giải thích."
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
    
    # 1. Thử dịch với ngữ cảnh trượt
    for attempt in range(retries):
        try:
            if is_llamacpp:
                # 151357 là ID của token '<think>' trong tokenizer của Qwen
                # Đặt logit_bias cực âm -100 để ngăn cấm tuyệt đối model sinh ra token '<think>'
                response_data = model.create_chat_completion(
                    messages=messages,
                    max_tokens=256,
                    temperature=0.0 if attempt == retries - 1 else 0.3, # Giảm nhiệt độ thấp để model dịch chính xác thay vì sáng tạo/suy nghĩ tự do
                    top_p=0.8,
                    top_k=20,
                    logit_bias={"151357": -100.0}
                )
                response = response_data["choices"][0]["message"]["content"].strip()
            else:
                text_in = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                model_inputs = tokenizer([text_in], return_tensors="pt").to(model.device)
                generated_ids = model.generate(
                    **model_inputs,
                    max_new_tokens=256,
                    do_sample=True,
                    temperature=0.5 if attempt == retries - 1 else 0.7,
                    top_p=0.8,
                    top_k=20
                )
                generated_ids = [
                    output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
                ]
                response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
                
            # Xử lý thẻ think bị cụt (nếu có mở <think> nhưng không có đóng </think> do bị cắt giữa chừng)
            if "<think>" in response:
                if "</think>" in response:
                    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
                else:
                    response = response.split("<think>")[0].strip()

            # Loại bỏ các tiêu đề suy nghĩ tự do (Thinking Process, Thought, Analysis)
            response = re.sub(r"(Thinking Process|Thought|Analysis):.*?(?=\n\n|\Z)", "", response, flags=re.DOTALL | re.IGNORECASE).strip()
            # Cắt đuôi nếu còn sót tàn dư suy nghĩ tự do chưa kết thúc
            for key in ["thinking process", "thought", "analysis"]:
                if key in response.lower():
                    response = response.lower().split(key)[0].strip()

            # Làm sạch phản hồi
            response = response.strip('"\' \n\t')
            
            # Kiểm tra xem bản dịch có chứa chữ nước ngoài, câu từ chối hoặc tàn dư suy nghĩ không
            is_refusal = any(k in response.lower() for k in ["không thể", "yêu cầu", "phù hợp", "từ chối", "đề xuất", "chính sách", "thinking", "thought", "analysis", "<think>"])
            # Phát hiện nếu model đang luyên thuyên giải thích dông dài
            is_too_long = len(text) < 20 and len(response) > 100
            
            if response and response != text and not contains_foreign_script(response) and not is_refusal and not is_too_long:
                return response
            else:
                print(f"[LLM] Cảnh báo: Bản dịch bị từ chối hoặc chứa chữ ngoại lai ở lần thử {attempt+1}: {response}")
        except Exception as e:
            print(f"[LLM] Lỗi khi dịch câu '{text}' ở lần thử {attempt+1}: {e}")
            
    # 2. Fallback tối giản (Minimalist Fallback) nếu gặp sự cố/kiểm duyệt
    print(f"[LLM] Kích hoạt chế độ dịch tối giản (Minimalist Prompt) cho câu nhạy cảm: '{text}'")
    try:
        minimal_messages = [
            {"role": "system", "content": "Bạn là biên dịch viên tiếng Nhật sang tiếng Việt. Chỉ trả về duy nhất câu dịch tiếng Việt thuần túy, không chứa chữ Nhật, không giải thích."},
            {"role": "user", "content": f"Dịch câu thoại này sang tiếng Việt: {text}"}
        ]
        if is_llamacpp:
            response_data = model.create_chat_completion(
                messages=minimal_messages,
                max_tokens=256,
                temperature=0.1,
                top_p=0.8,
                top_k=20,
                logit_bias={"151357": -100.0}
            )
            response_min = response_data["choices"][0]["message"]["content"].strip()
        else:
            text_in_min = tokenizer.apply_chat_template(minimal_messages, tokenize=False, add_generation_prompt=True)
            inputs_min = tokenizer([text_in_min], return_tensors="pt").to(model.device)
            gen_ids_min = model.generate(**inputs_min, max_new_tokens=256, temperature=0.7, top_p=0.8, top_k=20, do_sample=True)
            gen_ids_min = [o[len(i):] for i, o in zip(inputs_min.input_ids, gen_ids_min)]
            response_min = tokenizer.batch_decode(gen_ids_min, skip_special_tokens=True)[0].strip()
            
        # Xử lý thẻ think bị cụt (nếu có mở <think> nhưng không có đóng </think> do bị cắt giữa chừng)
        if "<think>" in response_min:
            if "</think>" in response_min:
                response_min = re.sub(r"<think>.*?</think>", "", response_min, flags=re.DOTALL).strip()
            else:
                response_min = response_min.split("<think>")[0].strip()

        # Loại bỏ các tiêu đề suy nghĩ tự do (Thinking Process, Thought, Analysis)
        response_min = re.sub(r"(Thinking Process|Thought|Analysis):.*?(?=\n\n|\Z)", "", response_min, flags=re.DOTALL | re.IGNORECASE).strip()
        # Cắt đuôi nếu còn sót tàn dư suy nghĩ tự do chưa kết thúc
        for key in ["thinking process", "thought", "analysis"]:
            if key in response_min.lower():
                response_min = response_min.lower().split(key)[0].strip()

        # Làm sạch phản hồi
        response_min = response_min.strip('"\' \n\t')
        
        # Kiểm tra xem bản dịch có chứa chữ nước ngoài, câu từ chối hoặc tàn dư suy nghĩ không
        is_refusal_min = any(k in response_min.lower() for k in ["không thể", "yêu cầu", "phù hợp", "từ chối", "đề xuất", "chính sách", "thinking", "thought", "analysis", "<think>"])
        # Phát hiện nếu model đang luyên thuyên giải thích dông dài
        is_too_long_min = len(text) < 20 and len(response_min) > 100
        
        if response_min and response_min != text and not contains_foreign_script(response_min) and not is_refusal_min and not is_too_long_min:
            return response_min
    except Exception as e_min:
        print(f"[LLM] Lỗi ở chế độ tối giản: {e_min}")
        
    # 3. Sử dụng Google Translate API làm phương án cứu cánh cuối cùng để bảo đảm 100% có tiếng Việt
    print(f"[LLM-FALLBACK] Sử dụng Google Translate cho câu không thể dịch: '{text}'")
    return google_translate_fallback(text)

def refine_translated_subtitles(model, tokenizer, segments, translated_texts, is_llamacpp=True) -> list:
    """Đọc lại toàn bộ mạch hội thoại để tối ưu hóa phụ đề, thống nhất xưng hô và trau chuốt câu chữ"""
    print("[LLM-REFINE] Bắt đầu bước 2: Đọc lại toàn bộ hội thoại và tối ưu hóa phụ đề...")
    
    total_len = len(segments)
    refined_texts = list(translated_texts) # Khởi tạo danh sách kết quả tối ưu
    
    # Chia phụ đề thành các batch nhỏ khoảng 25 câu để tránh tràn token đầu ra của LLM
    batch_size = 25
    for batch_start in range(0, total_len, batch_size):
        batch_end = min(batch_start + batch_size, total_len)
        print(f"[LLM-REFINE] Đang tối ưu hóa phân đoạn từ câu {batch_start + 1} đến {batch_end}...")
        
        # Tạo prompt danh sách hội thoại cho batch này
        dialogue_list = []
        for i in range(batch_start, batch_end):
            orig = segments[i]["text"]
            draft = translated_texts[i]
            dialogue_list.append(f"{i + 1}. [Gốc]: {orig}\n   [Bản dịch tạm]: {draft}")
        
        dialogue_text = "\n".join(dialogue_list)
        
        system_prompt = (
            "Bạn là một biên tập viên phụ đề phim Nhật Bản sang tiếng Việt chuyên nghiệp.\n"
            "Nhiệm vụ: Rà soát, tối ưu hóa và làm mượt các bản dịch tạm thời bên dưới để phù hợp với ngữ cảnh hội thoại của phim.\n"
            "YÊU CẦU TỐI ƯU HÓA:\n"
            "1. Thống nhất xưng hô: Dựa vào mạch truyện để sửa xưng hô đồng nhất từ đầu đến cuối (ví dụ: Anh - Em cho cặp anh em Rino). Tránh xưng hô bất nhất gượng gạo.\n"
            "2. Làm mượt văn phong: Trau chuốt các bản dịch tạm bị thô cứng, gượng gạo thành câu văn trôi chảy, tự nhiên chuẩn phim ảnh, nhưng tuyệt đối giữ nguyên nghĩa gốc.\n"
            "3. RÀNG BUỘC ĐẦU RA:\n"
            "   - KHÔNG ĐƯỢC SUY NGHĨ. Tuyệt đối KHÔNG viết suy nghĩ, giải thích hay bất kỳ chữ gì ngoài danh sách kết quả.\n"
            "   - Chỉ trả về danh sách các câu đã tối ưu với định dạng chính xác từng dòng: 'Số_thứ_tự. Câu_dịch_tối_ưu'\n"
            "   - Số thứ tự phải khớp chính xác 100% với danh sách đầu vào.\n"
            "   - Tuyệt đối không sử dụng thẻ <think> hoặc viết tiếng Anh."
        )
        
        user_prompt = (
            "Dưới đây là danh sách các câu thoại cần tối ưu hóa. Hãy trả về danh sách đã sửa đổi:\n\n"
            f"{dialogue_text}"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            if is_llamacpp:
                # 151357 là ID token '<think>' của Qwen, đặt logit_bias để cấm tuyệt đối suy nghĩ
                response_data = model.create_chat_completion(
                    messages=messages,
                    max_tokens=2048, # Tăng max_tokens đủ rộng để chứa kết quả dịch của 25 câu
                    temperature=0.2, # Nhiệt độ thấp để model bám sát cấu trúc
                    top_p=0.8,
                    top_k=20,
                    logit_bias={"151357": -100.0}
                )
                response = response_data["choices"][0]["message"]["content"].strip()
            else:
                text_in = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                model_inputs = tokenizer([text_in], return_tensors="pt").to(model.device)
                generated_ids = model.generate(
                    **model_inputs,
                    max_new_tokens=2048,
                    temperature=0.2,
                    top_p=0.8,
                    top_k=20
                )
                generated_ids = [
                    output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
                ]
                response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            
            # Làm sạch tàn dư suy nghĩ nếu có
            response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
            response = re.sub(r"(Thinking Process|Thought|Analysis):.*?(?=\n\n|\Z)", "", response, flags=re.DOTALL | re.IGNORECASE).strip()
            response = response.strip()
            
            # Phân tích kết quả trả về của LLM theo định dạng 'Số_thứ_tự. Câu_dịch'
            lines = response.split("\n")
            parsed_count = 0
            for line in lines:
                line = line.strip()
                # Khớp định dạng: bắt đầu bằng số thứ tự + dấu chấm + khoảng trắng
                match = re.match(r"^(\d+)\.\s*(.*)$", line)
                if match:
                    num = int(match.group(1))
                    refined_val = match.group(2).strip()
                    
                    # Xác thực số thứ tự nằm trong phạm vi của batch hiện tại
                    if batch_start <= (num - 1) < batch_end:
                        # Chỉ áp dụng nếu bản dịch tối ưu sạch (không chứa tiếng Nhật) và không rỗng
                        if refined_val and not contains_foreign_script(refined_val):
                            refined_texts[num - 1] = refined_val
                            parsed_count += 1
            
            print(f"[LLM-REFINE] Đã tối ưu hóa thành công {parsed_count} trên {batch_end - batch_start} câu thoại.")
            
        except Exception as e:
            print(f"[LLM-REFINE] Lỗi khi tối ưu hóa batch {batch_start + 1}-{batch_end}: {e}. Giữ nguyên bản dịch tạm.")
            
    return refined_texts

def main():
    parser = argparse.ArgumentParser(description="Translate Japanese text to Vietnamese using Qwen Hybrid Engine")
    parser.add_argument("--input", required=True, help="Đường dẫn file JSON bóc băng tạm")
    parser.add_argument("--output", required=True, help="Đường dẫn file SRT đầu ra")
    args = parser.parse_args()

    engine = os.getenv("TRANSLATION_ENGINE", "llamacpp").lower()
    print(f"[LLM] Khởi chạy dịch thuật với động cơ: {engine.upper()}")

    model = None
    tokenizer = None

    if engine == "llamacpp":
        from llama_cpp import Llama
        from huggingface_hub import hf_hub_download
        
        repo_id = os.getenv("HF_MODEL_REPO", "HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive")
        filename = os.getenv("GGUF_FILE_NAME", "Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf")
        
        print(f"[LLM] Đang định vị file GGUF trong cache: {filename} từ {repo_id}...")
        model_path = hf_hub_download(repo_id=repo_id, filename=filename)
        print(f"[LLM] Đang tải model GGUF lên GPU: {model_path}...")
        
        model = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_gpu_layers=-1,  # Nạp toàn bộ model weights lên GPU VRAM
            chat_format="qwen"
        )
    else:
        # Fallback sử dụng Transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        
        model_name = os.getenv("HF_MODEL_REPO", "Qwen/Qwen3.5-9B")
        print(f"[LLM] Đang cấu hình BitsAndBytes 4-bit cho Transformers...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16
        )
        
        print(f"[LLM] Đang tải tokenizer và model qua Transformers: {model_name}...")
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

    # Bước 2: Tối ưu hóa phụ đề theo mạch ngữ cảnh (Review & Refine)
    is_llamacpp_engine = (engine == "llamacpp")
    translated_texts = refine_translated_subtitles(model, tokenizer, segments, translated_texts, is_llamacpp=is_llamacpp_engine)

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
