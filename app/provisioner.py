import os
import time
import json
import requests
import threading
from datetime import datetime, timedelta
from app.database import (
    get_pending_jobs, get_processing_jobs, update_job_status, get_db_connection
)

VAST_API_KEY = os.getenv("VAST_API_KEY", "")
HUB_PUBLIC_URL = os.getenv("HUB_PUBLIC_URL", "http://localhost:8000")
MAX_CONCURRENT_GPUS = int(os.getenv("MAX_CONCURRENT_GPUS", "100"))
WORKER_DOCKER_IMAGE = os.getenv("WORKER_DOCKER_IMAGE", "docker.io/library/vast-translator:latest")

VAST_API_URL = "https://console.vast.ai/api/v1"

def get_headers():
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {VAST_API_KEY}" if VAST_API_KEY else ""
    }

def get_vast_instances():
    """Lấy danh sách các instance hiện tại trên tài khoản Vast.ai"""
    if not VAST_API_KEY:
        return []
    try:
        url = f"{VAST_API_URL}/instances/?api_key={VAST_API_KEY}"
        res = requests.get(url, headers=get_headers(), timeout=15)
        if res.status_code == 200:
            return res.json().get("instances", [])
        else:
            print(f"[Provisioner] Lỗi lấy danh sách instance: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[Provisioner] Lỗi kết nối Vast.ai: {e}")
    return []

def start_instance(instance_id: int):
    """Khởi động lại một instance đang bị Stopped"""
    url = f"{VAST_API_URL}/instances/{instance_id}/?api_key={VAST_API_KEY}"
    try:
        res = requests.put(url, json={"state": "running"}, headers=get_headers(), timeout=15)
        if res.status_code == 200:
            print(f"[Provisioner] Đã ra lệnh Start máy GPU {instance_id}")
            return True
        else:
            print(f"[Provisioner] Lỗi start máy GPU {instance_id}: {res.text}")
    except Exception as e:
        print(f"[Provisioner] Lỗi start máy GPU: {e}")
    return False

def destroy_instance(instance_id: int):
    """Hủy hoàn toàn một instance để dừng tính tiền"""
    url = f"{VAST_API_URL}/instances/{instance_id}/?api_key={VAST_API_KEY}"
    try:
        res = requests.delete(url, headers=get_headers(), timeout=15)
        if res.status_code == 200:
            print(f"[Provisioner] Đã ra lệnh Destroy máy GPU {instance_id}")
            return True
        else:
            print(f"[Provisioner] Lỗi destroy máy GPU {instance_id}: {res.text}")
    except Exception as e:
        print(f"[Provisioner] Lỗi destroy máy GPU: {e}")
    return False

def rent_new_gpu():
    """Tìm kiếm và thuê thêm 1 GPU RTX 4090 rẻ nhất"""
    if not VAST_API_KEY:
        print("[Provisioner] Chưa cấu hình VAST_API_KEY, bỏ qua thuê máy.")
        return False
        
    try:
        # Search query cho RTX 4090
        query = {
            "gpu_name": {"eq": "RTX 4090"},
            "rentable": {"eq": True},
            "verified": {"eq": True}
        }
        search_url = f"{VAST_API_URL}/bundle/?q={json.dumps(query)}&api_key={VAST_API_KEY}"
        res = requests.get(search_url, headers=get_headers(), timeout=15)
        
        if res.status_code != 200:
            print(f"[Provisioner] Lỗi tìm kiếm GPU: {res.status_code} - {res.text}")
            return False
            
        offers = res.json().get("offers", [])
        if not offers:
            print("[Provisioner] Không tìm thấy máy GPU RTX 4090 nào trống để thuê.")
            return False
            
        # Sắp xếp theo giá từ thấp đến cao (dph_total: dollars per hour total)
        offers.sort(key=lambda x: x.get("dph_total", 999.0))
        cheapest_offer = offers[0]
        offer_id = cheapest_offer["id"]
        price = cheapest_offer.get("dph_total", 0.0)
        
        print(f"[Provisioner] Tìm thấy GPU RTX 4090 rẻ nhất: Offer ID {offer_id}, Giá {price}$/giờ")
        
        # Gọi lệnh thuê máy
        rent_url = f"{VAST_API_URL}/asks/{offer_id}/?api_key={VAST_API_KEY}"
        payload = {
            "image": WORKER_DOCKER_IMAGE,
            "env": {"HUB_URL": HUB_PUBLIC_URL},
            "disk": 30.0, # 30GB đủ cho CUDA runtime + cache models
            "runtype": "args"
        }
        rent_res = requests.post(rent_url, json=payload, headers=get_headers(), timeout=15)
        
        if rent_res.status_code == 200:
            contract_id = rent_res.json().get("new_contract")
            print(f"[Provisioner] Thuê máy thành công! Contract ID: {contract_id}")
            return True
        else:
            print(f"[Provisioner] Lỗi thuê máy: {rent_res.status_code} - {rent_res.text}")
            
    except Exception as e:
        print(f"[Provisioner] Lỗi trong quá trình thuê GPU: {e}")
    return False

def handle_timeouts():
    """Kiểm tra các job PROCESSING quá lâu (30 phút) và đánh dấu lỗi"""
    try:
        processing_jobs = get_processing_jobs()
        now = datetime.now()
        for job in processing_jobs:
            updated_at = datetime.fromisoformat(job["updated_at"])
            # Nếu chạy quá 30 phút mà chưa xong
            if now - updated_at > timedelta(minutes=30):
                print(f"[Provisioner] Phát hiện Job {job['id']} bị timeout xử lý. Chuyển sang trạng thái FAILED.")
                update_job_status(job["id"], "FAILED: Xử lý quá thời gian quy định (Timeout 30 phút)")
    except Exception as e:
        print(f"[Provisioner] Lỗi xử lý timeout: {e}")

def run_provisioner_cycle():
    """Thực thi một chu kỳ kiểm tra và phân phối tài nguyên"""
    pending_jobs = get_pending_jobs()
    pending_count = len(pending_jobs)
    
    if pending_count == 0:
        # Không có job pending nào, kiểm tra xem có máy nào rảnh (stopped) để hủy không
        # Nếu muốn tiết kiệm tối đa, có thể destroy các máy Stopped
        instances = get_vast_instances()
        for inst in instances:
            # Nếu máy bị stopped và container đã hoàn thành (không có job chạy)
            if inst.get("actual_status") == "stopped" or inst.get("cur_state") == "stopped":
                # Chỉ hủy nếu không muốn duy trì Stopped instance
                # (Mặc định: hủy luôn để tránh tốn $0.01/giờ nếu không có nhu cầu tối ưu cold start)
                destroy_instance(inst["id"])
        return

    # Có job pending, xử lý
    instances = get_vast_instances()
    
    # Đếm số máy đang chạy hoặc đang chuẩn bị chạy
    active_instances = []
    stopped_instances = []
    
    for inst in instances:
        status = inst.get("actual_status", "")
        state = inst.get("cur_state", "")
        
        if status in ("running", "starting", "loading") or state in ("running", "starting"):
            active_instances.append(inst)
        elif status == "stopped" or state == "stopped":
            stopped_instances.append(inst)

    active_count = len(active_instances)
    
    print(f"[Provisioner] Hàng đợi: {pending_count} Job PENDING | Đang hoạt động: {active_count} GPU | Giới hạn tối đa: {MAX_CONCURRENT_GPUS}")
    
    # Nếu số lượng job lớn hơn số GPU đang hoạt động và chưa vượt quá giới hạn
    if pending_count > active_count and active_count < MAX_CONCURRENT_GPUS:
        needed_gpus = min(pending_count - active_count, MAX_CONCURRENT_GPUS - active_count)
        print(f"[Provisioner] Cần thêm {needed_gpus} GPU để xử lý hàng đợi.")
        
        for _ in range(needed_gpus):
            # Ưu tiên khởi động lại máy đang Stopped để tránh Cold Start tải image
            if stopped_instances:
                target_inst = stopped_instances.pop(0)
                start_instance(target_inst["id"])
            else:
                # Nếu không có máy stopped, thuê máy mới
                rent_new_gpu()
                # Nghỉ ngắn giữa các lần thuê tránh bị Vast.ai rate-limit
                time.sleep(2)

def provisioner_daemon():
    """Vòng lặp vô hạn của daemon chạy mỗi 15 giây"""
    print("[Provisioner] Đã khởi động background daemon.")
    # Đợi server FastAPI khởi động hoàn toàn
    time.sleep(5)
    while True:
        try:
            handle_timeouts()
            run_provisioner_cycle()
        except Exception as e:
            print(f"[Provisioner] Lỗi trong chu kỳ daemon: {e}")
        time.sleep(15)

def start_provisioner_loop():
    """Khởi chạy Provisioner Daemon dưới dạng Background Thread"""
    t = threading.Thread(target=provisioner_daemon, daemon=True)
    t.start()
