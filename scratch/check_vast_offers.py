import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def check_offers():
    api_key = os.getenv("VAST_API_KEY", "")
    url = f"https://console.vast.ai/api/v0/bundles/?api_key={api_key}"
    headers = {"Accept": "application/json"}
    
    # 1. Thử query gốc (mạng >= 1Gbps)
    query_strict = {
        "gpu_name": {"eq": "RTX 4090"},
        "rentable": {"eq": True},
        "verified": {"eq": True},
        "inet_down": {"gte": 1000.0},
        "order": [["score", "desc"]],
        "type": "on-demand",
        "allocated_storage": 40.0
    }
    
    # 2. Thử query lỏng hơn (mạng >= 200Mbps)
    query_loose = {
        "gpu_name": {"eq": "RTX 4090"},
        "rentable": {"eq": True},
        "verified": {"eq": True},
        "inet_down": {"gte": 200.0},
        "order": [["score", "desc"]],
        "type": "on-demand",
        "allocated_storage": 40.0
    }

    try:
        print("[Strict Query] Mạng >= 1Gbps:")
        res = requests.post(url, json=query_strict, headers=headers, timeout=15)
        if res.status_code == 200:
            offers = res.json().get("offers", [])
            print(f"  -> Tìm thấy {len(offers)} offers RTX 4090 trống.")
            for o in offers[:3]:
                print(f"     Offer ID: {o['id']} | Giá: {o.get('dph_total')}$/h | Mạng down: {o.get('inet_down')} Mbps | Host ID: {o.get('host_id')}")
        else:
            print(f"  -> Lỗi API: {res.status_code} - {res.text}")
            
        print("\n[Loose Query] Mạng >= 200Mbps:")
        res_loose = requests.post(url, json=query_loose, headers=headers, timeout=15)
        if res_loose.status_code == 200:
            offers_loose = res_loose.json().get("offers", [])
            print(f"  -> Tìm thấy {len(offers_loose)} offers RTX 4090 trống.")
            for o in offers_loose[:3]:
                print(f"     Offer ID: {o['id']} | Giá: {o.get('dph_total')}$/h | Mạng down: {o.get('inet_down')} Mbps | Host ID: {o.get('host_id')}")
        else:
            print(f"  -> Lỗi API: {res_loose.status_code} - {res_loose.text}")
            
    except Exception as e:
        print(f"Lỗi kết nối: {e}")

if __name__ == "__main__":
    check_offers()
