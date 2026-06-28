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

def analyze_script_context_via_llm(model, tokenizer, segments: list, is_llamacpp=True) -> dict:
    """
    Rút trích các mẫu câu chứa đại từ tiếng Nhật quan trọng và dùng LLM để phân tích
    mối quan hệ toàn cục và quy tắc xưng hô dưới dạng cấu trúc JSON.
    """
    print("[LLM-ANALYZER] Đang trích xuất câu thoại mẫu để phân tích bối cảnh phim...")
    
    # 1. Lọc thông minh câu thoại chứa đại từ nhân xưng/vai vế quan trọng
    keywords = ["お兄ちゃん", "お姉ちゃん", "妹", "先生", "先輩", "俺", "僕", "私", "あなた", "君", "パパ", "ママ", "旦那", "奥さん"]
    candidate_segments = []
    
    for seg in segments:
        text = seg["text"]
        if len(text) > 12 and any(k in text for k in keywords):
            candidate_segments.append(text)
            
    # Lấy tối đa 25 câu đại diện để không vượt quá token ngữ cảnh
    sample_texts = candidate_segments[:25]
    
    # Nếu không tìm thấy câu chứa đại từ, lấy 20 câu đầu tiên của kịch bản
    if len(sample_texts) < 5:
        sample_texts = [seg["text"] for seg in segments[:20]]
        
    sample_dialogue = "\n".join([f"- {text}" for text in sample_texts])
    
    system_prompt = (
        "Bạn là một biên dịch viên phụ đề phim Nhật Bản sang tiếng Việt chuyên nghiệp.\n"
        "Nhiệm vụ: Phân tích các câu thoại tiếng Nhật dưới đây và trả về quy tắc xưng hô tiếng Việt phù hợp nhất dưới dạng đối tượng JSON.\n"
        "YÊU CẦU BẮT BUỘC:\n"
        "- Trả về duy nhất một cấu trúc JSON hợp lệ.\n"
        "- KHÔNG ĐƯỢC SUY NGHĨ. Tuyệt đối không viết giải thích, không sử dụng thẻ <think>...</think>.\n"
        "- Cấu trúc JSON bắt buộc phải theo mẫu sau:\n"
        "{\n"
        '  "role_play_rules": "Bối cảnh quan hệ (ví dụ: Quan hệ vợ chồng, thầy trò, anh em). Nhân vật 1 xưng gì gọi nhân vật 2 là gì...",\n'
        '  "replacements": {\n'
        '    "tôi": "anh",\n'
        '    "bạn": "em"\n'
        '  }\n'
        "}\n"
        "- Phần 'replacements' định nghĩa các quy tắc thay thế đại từ nhân xưng thô của Google Translate sang xưng hô tự nhiên của nhân vật trong phim."
    )
    
    user_prompt = (
        "Dưới đây là một số câu thoại mẫu trong phim:\n\n"
        f"{sample_dialogue}\n\n"
        "Hãy phân tích và trả về đối tượng JSON quy tắc xưng hô:"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    # Fallback mặc định nếu có lỗi
    default_rules = {
        "role_play_rules": "BỐI CẢNH TOÀN CỤC: Giao tiếp thân mật thông thường.\nQUY TẮC XƯNG HÔ TOÀN CỤC: Người lớn tuổi/Nam xưng Anh/Tôi, gọi Em/Cậu. Người nhỏ tuổi/Nữ xưng Em, gọi Anh/Chị. Tránh dùng tao/bạn/mày.",
        "replacements": {
            "tôi": "anh",
            "bạn": "em"
        }
    }
    
    try:
        if is_llamacpp:
            response_data = model.create_chat_completion(
                messages=messages,
                max_tokens=512,
                temperature=0.3,
                top_p=0.8,
                top_k=20
            )
            response = response_data["choices"][0]["message"]["content"].strip()
        else:
            text_in = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            model_inputs = tokenizer([text_in], return_tensors="pt").to(model.device)
            generated_ids = model.generate(
                **model_inputs,
                max_new_tokens=512,
                temperature=0.3,
                top_p=0.8,
                top_k=20,
                do_sample=True
            )
            generated_ids = [
                output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
            ]
            response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            
        # Làm sạch thẻ think hoặc markdown block nếu có
        if "<think>" in response:
            if "</think>" in response:
                response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
            else:
                response = response.split("<think>")[0].strip()
                
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].strip()
            
        parsed = json.loads(response)
        if "role_play_rules" in parsed and "replacements" in parsed:
            print("[LLM-ANALYZER] Phân tích bối cảnh kịch bản thành công!")
            return parsed
    except Exception as e:
        print(f"[LLM-ANALYZER] Lỗi trong quá trình phân tích kịch bản bằng LLM: {e}. Sử dụng bối cảnh mặc định.")
        
    return default_rules

def clean_vietnamese_pronouns(text: str, replacements: dict) -> str:
    """Làm sạch các từ xưng hô mặc định từ Google Translate dựa trên bản đồ thay thế động"""
    if not replacements:
        return text
    for target, rep in replacements.items():
        pattern = re.compile(rf"\b{re.escape(target)}\b", re.IGNORECASE)
        text = pattern.sub(rep, text)
        
    # Các từ xưng hô cấm lọt
    text = re.sub(r"\btao\b", "em", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmày\b", "anh", text, flags=re.IGNORECASE)
    return text

def detect_speaker_info(text: str) -> str:
    """Phân tích câu thoại tiếng Nhật để đoán vai vế xưng hô cục bộ của câu"""
    if any(k in text for k in ["お兄ちゃん", "おにいちゃん", "兄ちゃん", "お兄様"]):
        return "GỢI Ý CỤC BỘ: Người nói đang gọi đối phương là ANH TRAI."
    if any(k in text for k in ["お姉ちゃん", "おねえちゃん", "姉ちゃん"]):
        return "GỢI Ý CỤC BỘ: Người nói đang gọi đối phương là CHỊ GÁI."
    if any(k in text for k in ["先生", "せんせい"]):
        return "GỢI Ý CỤC BỘ: Người nói đang gọi đối phương là THẦY/CÔ GIÁO."
    if any(k in text for k in ["先輩", "せんぱい"]):
        return "GỢI Ý CỤC BỘ: Người nói đang gọi đối phương là TIỀN BỐI (đàn anh/đàn chị)."
    if any(k in text for k in ["社長", "部長", "課長"]):
        return "GỢI Ý CỤC BỘ: Người nói đang gọi đối phương là CẤP TRÊN (Sếp)."
    return ""

def google_translate_fallback(text: str, replacements: dict = None) -> str:
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
                translated = clean_vietnamese_pronouns(translated.strip(), replacements)
                print(f"[LLM-FALLBACK] Dịch thành công qua Google Translate: '{text}' -> '{translated}'")
                return translated
    except Exception as e:
        print(f"[LLM-FALLBACK] Lỗi gọi Google Translate API: {e}")
    return text

def translate_single_text(model, tokenizer, text, history_context=[], global_relationship="", replacements=None, retries=2):
    # Xác định loại động cơ dịch dựa trên instance của model
    is_llamacpp = False
    try:
        from llama_cpp import Llama
        if isinstance(model, Llama):
            is_llamacpp = True
    except ImportError:
        pass

    speaker_hint = detect_speaker_info(text)
    full_hint = f"{global_relationship}\n{speaker_hint}" if global_relationship else speaker_hint
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
        f"{full_hint}\n"
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
                response_data = model.create_chat_completion(
                    messages=messages,
                    max_tokens=256,
                    temperature=0.5 if attempt == retries - 1 else 0.7,
                    top_p=0.8,
                    top_k=20
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
                
            # Xử lý thẻ think bị cụt
            if "<think>" in response:
                if "</think>" in response:
                    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
                else:
                    response = response.split("<think>")[0].strip()

            # Loại bỏ các tiêu đề suy nghĩ tự do
            response = re.sub(r"(Thinking Process|Thought|Analysis):.*?(?=\n\n|\Z)", "", response, flags=re.DOTALL | re.IGNORECASE).strip()
            for key in ["thinking process", "thought", "analysis"]:
                if key in response.lower():
                    response = response.lower().split(key)[0].strip()

            # Làm sạch phản hồi
            response = response.strip('"\' \n\t')
            
            # Kiểm tra xem bản dịch có chứa chữ nước ngoài, câu từ chối hoặc tàn dư suy nghĩ không
            is_refusal = any(k in response.lower() for k in ["không thể", "yêu cầu", "phù hợp", "từ chối", "đề xuất", "chính sách", "thinking", "thought", "analysis", "<think>"])
            is_too_long = len(text) < 20 and len(response) > 100
            
            if response and response != text and not contains_foreign_script(response) and not is_refusal and not is_too_long:
                return response
            else:
                print(f"[LLM] Cảnh báo: Bản dịch bị từ chối hoặc chứa chữ ngoại lai ở lần thử {attempt+1}: {response}")
        except Exception as e:
            print(f"[LLM] Lỗi khi dịch câu '{text}' ở lần thử {attempt+1}: {e}")
            
    # 2. Fallback tối giản
    print(f"[LLM] Kích hoạt chế độ dịch tối giản (Minimalist Prompt) cho câu nhạy cảm: '{text}'")
    try:
        minimal_messages = [
            {"role": "system", "content": "Bạn là biên biên dịch viên tiếng Nhật sang tiếng Việt. Chỉ trả về duy nhất câu dịch tiếng Việt thuần túy, không chứa chữ Nhật, không giải thích."},
            {"role": "user", "content": f"Dịch câu thoại này sang tiếng Việt: {text}"}
        ]
        if is_llamacpp:
            response_data = model.create_chat_completion(
                messages=minimal_messages,
                max_tokens=256,
                temperature=0.4,
                top_p=0.8,
                top_k=20
            )
            response_min = response_data["choices"][0]["message"]["content"].strip()
        else:
            text_in_min = tokenizer.apply_chat_template(minimal_messages, tokenize=False, add_generation_prompt=True)
            inputs_min = tokenizer([text_in_min], return_tensors="pt").to(model.device)
            gen_ids_min = model.generate(**inputs_min, max_new_tokens=256, temperature=0.7, top_p=0.8, top_k=20, do_sample=True)
            gen_ids_min = [o[len(i):] for i, o in zip(inputs_min.input_ids, gen_ids_min)]
            response_min = tokenizer.batch_decode(gen_ids_min, skip_special_tokens=True)[0].strip()
            
        if "<think>" in response_min:
            if "</think>" in response_min:
                response_min = re.sub(r"<think>.*?</think>", "", response_min, flags=re.DOTALL).strip()
            else:
                response_min = response_min.split("<think>")[0].strip()

        response_min = re.sub(r"(Thinking Process|Thought|Analysis):.*?(?=\n\n|\Z)", "", response_min, flags=re.DOTALL | re.IGNORECASE).strip()
        for key in ["thinking process", "thought", "analysis"]:
            if key in response_min.lower():
                response_min = response_min.lower().split(key)[0].strip()

        response_min = response_min.strip('"\' \n\t')
        
        is_refusal_min = any(k in response_min.lower() for k in ["không thể", "yêu cầu", "phù hợp", "từ chối", "đề xuất", "chính sách", "thinking", "thought", "analysis", "<think>"])
        is_too_long_min = len(text) < 20 and len(response_min) > 100
        
        if response_min and response_min != text and not contains_foreign_script(response_min) and not is_refusal_min and not is_too_long_min:
            return response_min
    except Exception as e_min:
        print(f"[LLM] Lỗi ở chế độ tối giản: {e_min}")
        
    print(f"[LLM-FALLBACK] Sử dụng Google Translate cho câu không thể dịch: '{text}'")
    return google_translate_fallback(text, replacements)

def refine_translated_subtitles(model, tokenizer, segments, translated_texts, global_relationship="", is_llamacpp=True) -> list:
    """Đọc lại toàn bộ mạch hội thoại để tối ưu hóa phụ đề, thống nhất xưng hô và trau chuốt câu chữ"""
    print("[LLM-REFINE] Bắt đầu bước 2: Đọc lại toàn bộ hội thoại và tối ưu hóa phụ đề...")
    
    total_len = len(segments)
    refined_texts = list(translated_texts)
    
    batch_size = 25
    for batch_start in range(0, total_len, batch_size):
        batch_end = min(batch_start + batch_size, total_len)
        print(f"[LLM-REFINE] Đang tối ưu hóa phân đoạn từ câu {batch_start + 1} đến {batch_end}...")
        
        dialogue_list = []
        for i in range(batch_start, batch_end):
            orig = segments[i]["text"]
            draft = translated_texts[i]
            dialogue_list.append(f"{i + 1}. [Gốc]: {orig}\n   [Bản dịch tạm]: {draft}")
        
        dialogue_text = "\n".join(dialogue_list)
        
        system_prompt = (
            "Bạn là một biên biên dịch viên phụ đề phim Nhật Bản sang tiếng Việt chuyên nghiệp.\n"
            "Nhiệm vụ: Rà soát, tối ưu hóa và làm mượt các bản dịch tạm thời bên dưới để phù hợp với ngữ cảnh hội thoại của phim.\n"
            "YÊU CẦU TỐI ƯU HÓA:\n"
            f"1. Thống nhất xưng hô: Dựa vào mạch truyện để sửa xưng hô đồng nhất từ đầu đến cuối.\n"
            f"{global_relationship}\n"
            "Tránh xưng hô bất nhất gượng gạo.\n"
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
                response_data = model.create_chat_completion(
                    messages=messages,
                    max_tokens=2048,
                    temperature=0.5,
                    top_p=0.8,
                    top_k=20
                )
                response = response_data["choices"][0]["message"]["content"].strip()
            else:
                text_in = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                model_inputs = tokenizer([text_in], return_tensors="pt").to(model.device)
                generated_ids = model.generate(
                    **model_inputs,
                    max_new_tokens=2048,
                    temperature=0.5,
                    top_p=0.8,
                    top_k=20
                )
                generated_ids = [
                    output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
                ]
                response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            
            response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
            response = re.sub(r"(Thinking Process|Thought|Analysis):.*?(?=\n\n|\Z)", "", response, flags=re.DOTALL | re.IGNORECASE).strip()
            response = response.strip()
            
            lines = response.split("\n")
            parsed_count = 0
            for line in lines:
                line = line.strip()
                match = re.match(r"^(\d+)\.\s*(.*)$", line)
                if match:
                    num = int(match.group(1))
                    refined_val = match.group(2).strip()
                    
                    if batch_start <= (num - 1) < batch_end:
                        if refined_val and not contains_foreign_script(refined_val):
                            refined_texts[num - 1] = refined_val
                            parsed_count += 1
            
            print(f"[LLM-REFINE] Đã tối ưu hóa thành công {parsed_count} trên {batch_end - batch_start} câu thoại.")
            
        except Exception as e:
            print(f"[LLM-REFINE] Lỗi khi tối ưu hóa batch {batch_start + 1}-{batch_end}: {e}. Giữ nguyên bản dịch tạm.")
            
    return refined_texts

def translate_batch(model, tokenizer, batch_segments, start_idx, global_relationship, replacements=None, is_llamacpp=True):
    """Dịch một lô các câu thoại tiếng Nhật sang tiếng Việt cùng lúc bằng định dạng JSON"""
    # Xây dựng input JSON cho model
    input_dict = {}
    for idx, seg in enumerate(batch_segments):
        input_dict[str(start_idx + idx + 1)] = seg["text"]
        
    dialogue_json = json.dumps(input_dict, ensure_ascii=False, indent=2)
    
    system_prompt = (
        "Bạn là một biên dịch viên phụ đề phim Nhật Bản sang tiếng Việt chuyên nghiệp.\n"
        "Nhiệm vụ: Dịch danh sách các câu thoại tiếng Nhật dưới đây sang tiếng Việt.\n"
        "QUY TẮC BẮT BUỘC:\n"
        "- Đảm bảo xưng hô nhất quán, tự nhiên, văn phong phim ảnh.\n"
        "- Trả về kết quả dưới dạng một đối tượng JSON hợp lệ duy nhất, với khóa là chỉ số câu thoại (dưới dạng chuỗi) và giá trị là câu dịch tiếng Việt thuần túy.\n"
        "- TUYỆT ĐỐI KHÔNG thêm số thứ tự, chỉ số hoặc dấu chấm vào đầu giá trị dịch (ví dụ: KHÔNG dịch thành '1. Câu dịch', chỉ dịch thành 'Câu dịch').\n"
        "- KHÔNG ĐƯỢC SUY NGHĨ. Không viết bất kỳ suy nghĩ hay giải thích nào ngoài chuỗi JSON.\n"
        "- Tuyệt đối KHÔNG sử dụng thẻ <think>...</think> hoặc viết tiếng Anh.\n"
        "Ví dụ định dạng đầu ra:\n"
        "{\n"
        '  "1": "Bản dịch câu 1",\n'
        '  "2": "Bản dịch câu 2"\n'
        "}"
    )
    
    user_prompt = (
        f"{global_relationship}\n\n"
        "Hãy dịch danh sách câu thoại tiếng Nhật sau đây sang tiếng Việt. Giữ nguyên các khóa ID:\n"
        f"{dialogue_json}"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        if is_llamacpp:
            response_data = model.create_chat_completion(
                messages=messages,
                max_tokens=1024,
                temperature=0.3,
                top_p=0.8,
                top_k=20
            )
            response = response_data["choices"][0]["message"]["content"].strip()
        else:
            text_in = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            model_inputs = tokenizer([text_in], return_tensors="pt").to(model.device)
            generated_ids = model.generate(
                **model_inputs,
                max_new_tokens=1024,
                temperature=0.3,
                top_p=0.8,
                top_k=20,
                do_sample=True
            )
            generated_ids = [
                output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
            ]
            response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            
        if "<think>" in response:
            if "</think>" in response:
                response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
            else:
                response = response.split("<think>")[0].strip()
        
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].strip()
            
        result_dict = json.loads(response)
        
        validated_dict = {}
        for idx in range(len(batch_segments)):
            key = str(start_idx + idx + 1)
            if key in result_dict:
                trans = result_dict[key].strip()
                trans = re.sub(r"^\d+\.\s*", "", trans).strip()
                trans = clean_vietnamese_pronouns(trans, replacements)
                if trans and not contains_foreign_script(trans):
                    validated_dict[key] = trans
                    
        if len(validated_dict) == len(batch_segments):
            return [validated_dict[str(start_idx + idx + 1)] for idx in range(len(batch_segments))]
            
        print(f"[LLM-BATCH] Lô dịch {start_idx + 1}-{start_idx + len(batch_segments)} không khớp đủ số câu hoặc chứa chữ ngoại lai. Kích hoạt fallback dịch đơn lẻ.")
    except Exception as e:
        print(f"[LLM-BATCH] Lỗi dịch lô {start_idx + 1}-{start_idx + len(batch_segments)}: {e}. Kích hoạt fallback dịch đơn lẻ.")
        
    return None

def deduplicate_subtitles(segments, translated_texts):
    """
    Lọc bỏ các câu phụ đề trùng lặp liên tiếp hoặc có độ tương đồng cực kỳ cao.
    Nếu trùng lặp: gộp thời gian (nếu liền kề) hoặc loại bỏ phân đoạn lặp thừa.
    """
    if not segments:
        return [], []
        
    new_segments = []
    new_translated = []
    
    new_segments.append(dict(segments[0]))
    new_translated.append(translated_texts[0])
    
    for i in range(1, len(segments)):
        prev_text = new_translated[-1].strip().lower()
        curr_text = translated_texts[i].strip().lower()
        
        prev_clean = re.sub(r"[.,\/#!$%\^&\*;:{}=\-_`~()?”“]", "", prev_text).strip()
        curr_clean = re.sub(r"[.,\/#!$%\^&\*;:{}=\-_`~()?”“]", "", curr_text).strip()
        
        is_similar = False
        if prev_clean == curr_clean:
            is_similar = True
        elif len(prev_clean) > 10 and len(curr_clean) > 10:
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, prev_clean, curr_clean).ratio()
            if ratio > 0.85:
                is_similar = True
                
        time_gap = segments[i]["start"] - new_segments[-1]["end"]
        
        if is_similar and time_gap < 1.5:
            print(f"[DEDUPLICATE] Phát hiện trùng lặp câu: '{new_translated[-1]}' và '{translated_texts[i]}'. Gộp thời gian phân đoạn.")
            new_segments[-1]["end"] = max(new_segments[-1]["end"], segments[i]["end"])
        else:
            new_segments.append(dict(segments[i]))
            new_translated.append(translated_texts[i])
            
    return new_segments, new_translated

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
        
        repo_id = os.getenv("HF_MODEL_REPO", "bartowski/Qwen2.5-14B-Instruct-GGUF")
        filename = os.getenv("GGUF_FILE_NAME", "Qwen2.5-14B-Instruct-Q8_0.gguf")
        
        print(f"[LLM] Đang định vị file GGUF trong cache: {filename} từ {repo_id}...")
        model_path = hf_hub_download(repo_id=repo_id, filename=filename)
        print(f"[LLM] Đang tải model GGUF lên GPU: {model_path}...")
        
        model = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_gpu_layers=-1,
            chat_format="qwen"
        )
    else:
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

    # Nhận diện mối quan hệ toàn cục bằng LLM
    context_data = analyze_script_context_via_llm(model, tokenizer, segments, is_llamacpp=(engine == "llamacpp"))
    global_relationship = context_data.get("role_play_rules", "")
    replacements = context_data.get("replacements", {})
    print(f"[LLM] Phân tích bối cảnh toàn cục:\n{global_relationship}")
    print(f"[LLM] Bản đồ thay thế xưng hô: {replacements}")

    print(f"[LLM] Bắt đầu dịch {len(segments)} câu thoại theo Batch hội thoại...")
    translated_texts = [None] * len(segments)
    
    batch_size = 12
    idx = 0
    while idx < len(segments):
        batch_segments = segments[idx : idx + batch_size]
        print(f"[LLM] Đang dịch lô {idx + 1} đến {idx + len(batch_segments)}...")
        
        batch_results = translate_batch(
            model, tokenizer, batch_segments, idx, global_relationship, replacements=replacements, is_llamacpp=(engine == "llamacpp")
        )
        
        if batch_results:
            for b_i, trans in enumerate(batch_results):
                translated_texts[idx + b_i] = trans
            idx += len(batch_segments)
        else:
            print(f"[LLM] Gặp sự cố dịch lô, kích hoạt fallback dịch đơn lẻ cho {len(batch_segments)} câu...")
            for b_i in range(len(batch_segments)):
                curr_idx = idx + b_i
                seg = batch_segments[b_i]
                
                history = []
                start_h = max(0, curr_idx - 3)
                for h_idx in range(start_h, curr_idx):
                    orig = segments[h_idx]["text"]
                    trans = translated_texts[h_idx]
                    if trans and not contains_foreign_script(trans):
                        history.append(f"Gốc: {orig} -> Dịch: {trans}")
                        
                print(f"[LLM] (Fallback) ({curr_idx+1}/{len(segments)}) Dịch: {seg['text']}")
                trans_single = translate_single_text(
                    model, tokenizer, seg["text"], history, global_relationship, replacements=replacements
                )
                translated_texts[curr_idx] = trans_single
                print(f"      -> Kết quả: {trans_single}")
                
            idx += len(batch_segments)

    is_llamacpp_engine = (engine == "llamacpp")
    translated_texts = refine_translated_subtitles(model, tokenizer, segments, translated_texts, global_relationship, is_llamacpp=is_llamacpp_engine)

    segments, translated_texts = deduplicate_subtitles(segments, translated_texts)

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
