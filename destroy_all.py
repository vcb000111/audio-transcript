import os
import requests
from dotenv import load_dotenv

# Tải biến môi trường
load_dotenv()
VAST_API_KEY = os.getenv("VAST_API_KEY", "")

headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {VAST_API_KEY}" if VAST_API_KEY else ""
}

def destroy_all():
    url_list = f"https://console.vast.ai/api/v1/instances/?api_key={VAST_API_KEY}"
    try:
        res = requests.get(url_list, headers=headers, timeout=15)
        if res.status_code == 200:
            instances = res.json().get("instances", [])
            print(f"Tìm thấy {len(instances)} máy ảo.")
            for inst in instances:
                inst_id = inst["id"]
                status = inst.get("actual_status", "")
                print(f"Đang hủy máy ảo {inst_id} (Trạng thái: {status})...")
                url_del = f"https://console.vast.ai/api/v0/instances/{inst_id}/?api_key={VAST_API_KEY}"
                del_res = requests.delete(url_del, headers=headers, timeout=15)
                print(f"Kết quả cho máy {inst_id}: {del_res.status_code} - {del_res.text}")
        else:
            print(f"Lỗi khi lấy danh sách máy ảo: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Lỗi kết nối Vast.ai: {e}")

if __name__ == "__main__":
    destroy_all()
