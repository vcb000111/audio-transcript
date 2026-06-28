import argparse
import json
from faster_whisper import WhisperModel

def main():
    parser = argparse.ArgumentParser(description="ASR using Faster-Whisper large-v3")
    parser.add_argument("--audio", required=True, help="Đường dẫn file audio đầu vào")
    parser.add_argument("--output", required=True, help="Đường dẫn file JSON đầu ra")
    parser.add_argument("--initial_prompt", default="", help="Mồi ngữ cảnh cho ASR")
    args = parser.parse_args()

    print("[ASR] Đang khởi tạo model Faster-Whisper (large-v3, float16)...")
    # Tải model từ cache (sẽ được cache sẵn trong lúc build Docker)
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    
    print(f"[ASR] Bắt đầu nhận diện giọng nói cho: {args.audio}")
    prompt = args.initial_prompt if args.initial_prompt else "Japanese adult video, JAV, rên rỉ, thỏ thẻ, yamete kudasai, iku, senpai, sensei, kimochi, gomen"
    
    segments, info = model.transcribe(
        args.audio,
        beam_size=5,
        language="ja",
        vad_filter=True,
        # VAD Parameters nặng để lọc tiếng rên/thở dốc ngắn
        vad_parameters=dict(min_speech_duration_ms=600, threshold=0.5),
        # Mồi ngữ cảnh động giúp mô hình đoán chính xác hơn
        initial_prompt=prompt,
        condition_on_previous_text=False
    )
    
    result_segments = []
    for segment in segments:
        print(f"[{segment.start:.2f}s -> {segment.end:.2f}s]: {segment.text}")
        result_segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text
        })
        
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result_segments, f, ensure_ascii=False, indent=2)
        
    print(f"[ASR] Nhận diện hoàn thành. Lưu {len(result_segments)} câu vào {args.output}")

if __name__ == "__main__":
    main()
