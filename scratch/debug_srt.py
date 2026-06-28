import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

filepath = "real_test_video.srt"
if os.path.exists(filepath):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        content = f.read()
    print("Length of content:", len(content))
    print("Represented first 200 chars:")
    print(repr(content[:200]))
    print("Line endings present:")
    print("CRLF count:", content.count("\r\n"))
    print("LF count:", content.count("\n") - content.count("\r\n"))
    print("Double CRLF count:", content.count("\r\n\r\n"))
    print("Double LF count:", content.count("\n\n"))
else:
    print("File not found")
