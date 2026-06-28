import json
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def get_media_info():
    try:
        import subprocess
        cmd_vid = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1", "real_test_video.mp4"]
        cmd_aud = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1", "real_test_audio.mp3"]
        
        vid_dur = subprocess.check_output(cmd_vid, text=True).strip().split("=")[-1]
        aud_dur = subprocess.check_output(cmd_aud, text=True).strip().split("=")[-1]
        
        print(f"[Media] Độ dài Video: {float(vid_dur):.2f} giây | Độ dài Audio: {float(aud_dur):.2f} giây")
    except Exception as e:
        print(f"[Media] Lỗi ffprobe: {e}")

def parse_srt(filepath):
    texts = []
    if not os.path.exists(filepath):
        print(f"File {filepath} không tồn tại.")
        return texts
    
    with open(filepath, "r", encoding="utf-8-sig") as f:
        content = f.read()
        
    content = content.replace("\r\n", "\n")
    # Thay thế \n\n\n\n bằng nhãn phân tách
    if "\n\n\n\n" in content:
        content = content.replace("\n\n\n\n", "===BLOCK===")
    else:
        # Fallback tách bằng double newline
        # Nhưng ở đây \n\n cũng phân tách giữa ID, timeline và text trong cùng 1 block,
        # nên ta phải gộp các block trước
        content = re.sub(r"\n\n+", "\n\n", content)
        # Nếu chỉ có \n\n bình thường, srt chuẩn sẽ có cấu trúc: ID\nTimeline\nText\n\nID\nTimeline...
        # Ta sẽ dùng regex để bóc tách text
        pass
        
    if "===BLOCK===" in content:
        blocks = content.strip().split("===BLOCK===")
        for block in blocks:
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            if len(lines) >= 3:
                texts.append(" ".join(lines[2:]))
    else:
        # Cách parse dự phòng dùng regex khớp cấu trúc phụ đề tiêu chuẩn
        # Format: số\nTimeline\nText
        pattern = re.compile(r"\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n(.*?)(?=\n\d+\n|\Z)", re.DOTALL)
        matches = pattern.findall(content)
        for m in matches:
            texts.append(m.replace("\n", " ").strip())
            
    return texts

def compare_translations():
    ja_texts = [
        "お兄ちゃん、まだ寝てる。早く行かないと遅刻するよ。", # 1
        "僕の妹、リノ。", # 2
        "おい、もうちょっとだけ。", # 3
        "もうダメだってば。お兄ちゃんがしっかりしてくれないと私が困るの。", # 4
        "両親を早く亡くし、僕が親代わりとして二人でここまで暮らしてきた。", # 5
        "そんな背景もあって、僕には全くと言っていいほど女っ気がない。", # 6
        "いわゆる素人童貞ってやつだ。", # 7
        "ああ、お兄ちゃんのスケベ。今、私の足ばっか見てたでしょ。", # 8
        "日に日に成長し、女の色気をまとい出した妹にムラッとしてしまう僕がここにいる。", # 9
        "見てないよ。見るわけないじゃん。寝てたからそういう風に見えたんじゃないの。", # 10
        "お兄ちゃんってさ、彼女とかできたことないですよ。", # 11
        "え?いや、それくらいいたことあるし。", # 12
        "大丈夫。お兄ちゃんとは私が結婚してあげるから。", # 13
        "お兄ちゃんのこと大好きなのに。だってお兄ちゃん優しいし、なんかリノのために生きてるって感じ。", # 14
        "いや、そんな兄弟なんだから当たり前なんでそれくらい。急いで朝風呂入ってくる。", # 15
        "こんな無邪気な妹に、僕は最近、ありえない。", # 16
        "こんな無邪気な妹に、僕は最近、ありえない。", # 17
        "... (lặp)", # 18
        "あってはいけない想像をかきたててしまっていた。", # 19
        "兄だから、家族だからか、無防備なリノの振る舞いが、僕を苦しめていた。", # 20
        "お兄ちゃんってさ、最近、リノのことなんか意識してない?", # 21
        "なんかだって、イッチな目で見てる気がする。", # 22
        "お兄ちゃんってさ、もしかして、変態?", # 23
        "え?いや、ち、違う。違う違う。なんでいきなりそんなこと言うの?", # 24
        "なんでいきなりそんなこと言うの?", # 25
        "僕は、頭のいかれた変態なのかもしれない。", # 26
        "リノ。", # 27
        "ん?", # 28
        "そんな短い靴着たじゃん。足寒いな。", # 29
        "うん、まあ。", # 30
        "これ履きなよ。", # 31
        "え?いいの?", # 32
        "あ,ありがとう.かわいい。", # 33
        "なんか寒くなってきたしさ、そろそろ。", # 34
        "履こうかなと思ってたんだよね。", # 35
        "兄ちゃん、こういうの好き?", # 36
        "え?あ、ち、違うよ。", # 37
        "いや、か、風邪ひくと、悪いってな。", # 38
        "うんうん。まあ、すごかったりしといてあげるよ。", # 39
        "じゃ、先行くね。", # 40
        "うん。", # 41
        "この時、自分が完全に変態だと、確信した。", # 42
        "いや、いや、これは、いや、その、いや、ち、ち、違うね。", # 43
        "いや、最近、その、とにかく、ちょっと、今見たら、ちょっと、もう忘れて。", # 44
        "ずっと見てたもんね。", # 45
        "足。お兄ちゃん。こういうのが好きなんだ。", # 46
        "え、いや、好きとか、そういうんじゃ。", # 47
        "ええね。こういうの?", # 48
    ]
    
    vn_texts = parse_srt("real_test_video.srt")
    print(f"\n[SRT Analysis] Tổng số câu tiếng Nhật (Whisper): {len(ja_texts)} | Số câu dịch trong SRT: {len(vn_texts)}")
    
    # Phân tích từng câu
    print("\n--- BẢNG SO SÁNH PHÂN TÍCH NGHĨA PHỤ ĐỀ ---")
    for i in range(min(len(ja_texts), len(vn_texts))):
        ja = ja_texts[i]
        vn = vn_texts[i]
        
        status = "OK"
        comment = ""
        
        if i == 21: # index 21 là câu 22 (イッチな目)
            status = "SAI NGHĨA NẶNG"
            comment = "Gốc 'イッチな目' (Ecchi na me) là ánh mắt dâm đãng/bậy bạ. Bản dịch cũ bị dịch sai thành 'ánh mắt của một người anh trai'."
        elif i == 39: # index 39 là câu 40 (先行くね)
            status = "SAI XƯNG HÔ"
            comment = "Gốc '先行くね' là em gái nói 'Em đi trước đây nhé'. Bản dịch cũ bị dịch ngược xưng hô thành 'anh đi trước nhé'."
        elif i == 28: # câu 29 (短い靴下)
            status = "DỊCH CHƯA CHUẨN"
            comment = "Gốc là 'vớ/tất ngắn'. Bản dịch cũ dịch là 'giày ngắn'."
        elif i == 30: # câu 31 (これ履きなよ)
            status = "DỊCH CHƯA CHUẨN"
            comment = "Gốc là xỏ tất/mang vớ vào. Bản dịch cũ dịch là 'đôi giày này em mang đi'."
        elif i == 38: # câu 39 (すごかったりしといてあげるよ)
            status = "SAI NGHĨA"
            comment = "Gốc Rino trêu chọc sẽ mang tất đùi quyến rũ cho anh ngắm. Bản dịch cũ dịch là 'anh sẽ cố gắng làm cho nó thật tuyệt vời'."
            
        print(f"Câu {i+1}:")
        print(f"  [Gốc Nhật]: {ja}")
        print(f"  [Dịch hiện tại]: {vn}")
        if status != "OK":
            print(f"  [Đánh giá]: 🔴 {status} - {comment}")
        else:
            print(f"  [Đánh giá]: 🟢 OK")
        print()

if __name__ == "__main__":
    get_media_info()
    compare_translations()
