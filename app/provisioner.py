import os
import time
import json
import requests
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Đảm bảo load config từ file .env ở thư mục gốc
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

from app.database import (
    get_pending_jobs, get_processing_jobs, update_job_status, get_db_connection
)

def get_config():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(dotenv_path=env_path, override=True)
    return {
        "api_key": os.getenv("VAST_API_KEY", "").strip(),
        "hub_url": os.getenv("HUB_PUBLIC_URL", "http://localhost:8000").strip(),
        "max_gpus": int(os.getenv("MAX_CONCURRENT_GPUS", "100")),
        "worker_image": os.getenv("WORKER_DOCKER_IMAGE", "minhtu98/vast-translator:latest").strip(),
        "use_latest": os.getenv("USE_LATEST_IMAGE", "false").lower() == "true",
        "engine": os.getenv("TRANSLATION_ENGINE", "llamacpp").strip(),
        "model_repo": os.getenv("HF_MODEL_REPO", "bartowski/Qwen2.5-14B-Instruct-GGUF").strip(),
        "gguf_name": os.getenv("GGUF_FILE_NAME", "Qwen2.5-14B-Instruct-Q8_0.gguf").strip()
    }

VAST_API_URL_V0 = "https://console.vast.ai/api/v0"
VAST_API_URL_V1 = "https://console.vast.ai/api/v1"

def get_current_git_sha():
    """Lấy Git commit SHA hiện tại của repo local để định danh tag Docker image tránh cache"""
    try:
        import subprocess
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        print(f"[Provisioner] Git commit SHA cục bộ: {sha}")
        return sha
    except Exception as e:
        print(f"[Provisioner] Bỏ qua lấy Git SHA do lỗi: {e}")
        return None

def save_instance_log(instance_id: int):
    """Tải log của instance từ Vast.ai và lưu lại ở Hub trước khi hủy máy ảo để sếp tiện debug"""
    cfg = get_config()
    if not cfg["api_key"]:
        return
    try:
        # 1. Gọi PUT để yêu cầu tạo log từ Vast.ai
        url = f"{VAST_API_URL_V0}/instances/request_logs/{instance_id}/?api_key={cfg['api_key']}"
        print(f"[Provisioner] Yêu cầu Vast.ai tạo log cho máy ảo {instance_id}: PUT {url}")
        res = requests.put(url, json={}, headers=get_headers(), timeout=15)
        
        if res.status_code == 200:
            result_url = res.json().get("result_url")
            if result_url:
                # 2. Polling kết quả result_url để lấy log text
                print(f"[Provisioner] Đang tải log từ CDN: {result_url}")
                log_data = ""
                for _ in range(20): # thử tối đa 20 lần (khoảng 6 giây)
                    time.sleep(0.3)
                    try:
                        r_log = requests.get(result_url, timeout=10)
                        if r_log.status_code == 200:
                            log_data = r_log.text
                            break
                    except Exception as poll_err:
                        # Bỏ qua lỗi kết nối trong khi poll
                        pass
                
                if log_data:
                    log_dir = os.path.join(os.getenv("STORAGE_DIR", "./storage"), "logs")
                    os.makedirs(log_dir, exist_ok=True)
                    log_file = os.path.join(log_dir, f"{instance_id}.log")
                    with open(log_file, "w", encoding="utf-8") as f:
                        f.write(log_data)
                    print(f"[Provisioner] Đã lưu log máy ảo {instance_id} vào file: {log_file}")
                else:
                    print(f"[Provisioner] Không tải được nội dung log từ URL cho máy {instance_id} (Timeout).")
            else:
                print(f"[Provisioner] Vast.ai không trả về result_url cho log máy {instance_id}.")
        else:
            print(f"[Provisioner] Lỗi yêu cầu log máy {instance_id}: Status {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[Provisioner] Lỗi hệ thống khi tải log máy {instance_id}: {e}")

def get_headers():
    cfg = get_config()
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}" if cfg['api_key'] else ""
    }

def get_vast_instances():
    """Lấy danh sách các instance hiện tại trên tài khoản Vast.ai"""
    cfg = get_config()
    if not cfg["api_key"]:
        print("[Provisioner] Bỏ qua lấy instance do thiếu VAST_API_KEY.")
        return []
    try:
        url = f"{VAST_API_URL_V1}/instances/?api_key={cfg['api_key']}"
        print(f"[Provisioner] Gọi API Vast.ai lấy danh sách máy: GET {url}")
        res = requests.get(url, headers=get_headers(), timeout=15)
        if res.status_code == 200:
            instances = res.json().get("instances", [])
            print(f"[Provisioner] Lấy danh sách thành công. Tìm thấy {len(instances)} instances.")
            return instances
        else:
            print(f"[Provisioner] Lỗi API lấy danh sách instance: Status {res.status_code} - Phản hồi: {res.text}")
    except Exception as e:
        print(f"[Provisioner] Lỗi kết nối Vast.ai khi lấy danh sách: {e}")
    return []

def start_instance(instance_id: int):
    """Khởi động lại một instance đang bị Stopped"""
    cfg = get_config()
    url = f"{VAST_API_URL_V0}/instances/{instance_id}/?api_key={cfg['api_key']}"
    print(f"[Provisioner] Yêu cầu khởi động máy {instance_id}: PUT {url}")
    try:
        res = requests.put(url, json={"state": "running"}, headers=get_headers(), timeout=15)
        if res.status_code == 200:
            print(f"[Provisioner] Đã ra lệnh Start máy GPU {instance_id} thành công.")
            return True
        else:
            print(f"[Provisioner] Lỗi start máy GPU {instance_id}: Status {res.status_code} - Phản hồi: {res.text}")
    except Exception as e:
        print(f"[Provisioner] Lỗi kết nối khi start máy GPU {instance_id}: {e}")
    return False

def destroy_instance(instance_id: int):
    """Hủy hoàn toàn một instance để dừng tính tiền"""
    cfg = get_config()
    url = f"{VAST_API_URL_V0}/instances/{instance_id}/?api_key={cfg['api_key']}"
    print(f"[Provisioner] Yêu cầu hủy (Destroy) máy {instance_id} để dừng tính tiền: DELETE {url}")
    try:
        res = requests.delete(url, headers=get_headers(), timeout=15)
        if res.status_code == 200:
            print(f"[Provisioner] Đã ra lệnh Destroy máy GPU {instance_id} thành công.")
            return True
        else:
            print(f"[Provisioner] Lỗi destroy máy GPU {instance_id}: Status {res.status_code} - Phản hồi: {res.text}")
    except Exception as e:
        print(f"[Provisioner] Lỗi kết nối khi destroy máy GPU {instance_id}: {e}")
    return False
def rent_new_gpu() -> str:
    """Tìm kiếm và thuê thêm 1 GPU RTX 4090 rẻ nhất có mạng >= 1 Gbps, trả về contract_id nếu thành công"""
    cfg = get_config()
    if not cfg["api_key"]:
        print("[Provisioner] Chưa cấu hình VAST_API_KEY, bỏ qua thuê máy.")
        return None
        
    try:
        # Search query cho RTX 4090 có tốc độ mạng tải xuống tối thiểu 1 Gbps (1000 Mbps)
        query = {
            "gpu_name": {"eq": "RTX 4090"},
            "rentable": {"eq": True},
            "verified": {"eq": True},
            "inet_down": {"gte": 1000.0},
            "order": [["score", "desc"]],
            "type": "on-demand",
            "allocated_storage": 40.0
        }
        search_url = f"{VAST_API_URL_V0}/bundles/?api_key={cfg['api_key']}"
        print(f"[Provisioner] Đang tìm kiếm GPU RTX 4090 trống rẻ nhất (mạng >= 1Gbps): POST {search_url} | Query: {query}")
        res = requests.post(search_url, json=query, headers=get_headers(), timeout=15)
        
        if res.status_code != 200:
            print(f"[Provisioner] Lỗi tìm kiếm GPU: Status {res.status_code} - Phản hồi: {res.text}")
            return None
            
        offers = res.json().get("offers", [])
        if not offers:
            print("[Provisioner] Không tìm thấy máy GPU RTX 4090 nào trống để thuê.")
            return None
            
        # Sắp xếp theo giá từ thấp đến cao (dph_total: dollars per hour total)
        offers.sort(key=lambda x: x.get("dph_total", 999.0))
        cheapest_offer = offers[0]
        offer_id = cheapest_offer["id"]
        price = cheapest_offer.get("dph_total", 0.0)
        
        print(f"[Provisioner] Tìm thấy GPU RTX 4090 rẻ nhất: Offer ID {offer_id}, Host ID {cheapest_offer.get('host_id')}, Giá {price}$/giờ, Mạng down: {cheapest_offer.get('inet_down')} Mbps")
        
        # Xác định image name kèm Git SHA tag để tránh cache (cho phép ghi đè qua USE_LATEST_IMAGE)
        image_name = cfg["worker_image"]
        use_latest = cfg["use_latest"]
        if cfg["worker_image"].endswith(":latest") and not use_latest:
            sha = get_current_git_sha()
            if sha:
                base_image = cfg["worker_image"].rsplit(":", 1)[0]
                image_name = f"{base_image}:{sha}"
                print(f"[Provisioner] Dùng tag Git SHA để tránh cache: {image_name}")
        elif use_latest:
            print(f"[Provisioner] Ép buộc sử dụng Docker tag LATEST để test nhanh: {image_name}")
 
        # Gọi lệnh thuê máy
        rent_url = f"{VAST_API_URL_V0}/asks/{offer_id}/?api_key={cfg['api_key']}"
        payload = {
            "client_id": "me",
            "image": image_name,
            "env": {
                "HUB_URL": cfg["hub_url"],
                "TRANSLATION_ENGINE": cfg["engine"],
                "HF_MODEL_REPO": cfg["model_repo"],
                "GGUF_FILE_NAME": cfg["gguf_name"]
            },
            "disk": 40.0, # 40GB đủ cho CUDA runtime + cache models không bị tràn overlayfs
            "runtype": "args"
        }
        print(f"[Provisioner] Đang tiến hành thuê máy: PUT {rent_url} | Payload: {payload}")
        rent_res = requests.put(rent_url, json=payload, headers=get_headers(), timeout=15)
        
        if rent_res.status_code == 200:
            contract_id = rent_res.json().get("new_contract")
            print(f"[Provisioner] Thuê máy thành công! Contract ID / Instance ID mới: {contract_id}")
            return str(contract_id)
        else:
            print(f"[Provisioner] Lỗi thuê máy: Status {rent_res.status_code} - Phản hồi: {rent_res.text}")
            
    except Exception as e:
        print(f"[Provisioner] Lỗi hệ thống trong quá trình thuê GPU: {e}")
    return None

def handle_timeouts():
    """Kiểm tra các job PROCESSING quá lâu (30 phút) hoặc PENDING đã gán máy quá lâu (25 phút) để reset/hủy"""
    try:
        now = datetime.now()
        # 1. Timeout cho các job PROCESSING quá 30 phút
        processing_jobs = get_processing_jobs()
        for job in processing_jobs:
            updated_at = datetime.fromisoformat(job["updated_at"])
            if now - updated_at > timedelta(minutes=30):
                print(f"[Provisioner] [TIMEOUT] Phát hiện Job {job['id']} bị kẹt PROCESSING quá 30 phút. Chuyển trạng thái sang FAILED.")
                update_job_status(job["id"], "FAILED: Xử lý quá thời gian quy định (Timeout 30 phút)")
                
        # 2. Reset các job PENDING đã gán máy ảo quá lâu nhưng worker chưa claim (quá 25 phút)
        # Đồng thời hủy (destroy) máy ảo cũ bị kẹt để tránh tốn tiền tài khoản của sếp
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE status = 'PENDING' AND vast_contract_id IS NOT NULL")
        rows = cursor.fetchall()
        for row in rows:
            job = dict(row)
            updated_at = datetime.fromisoformat(job["updated_at"])
            if now - updated_at > timedelta(minutes=25):
                stuck_instance_id = job['vast_contract_id']
                print(f"[Provisioner] [TIMEOUT] Job {job['id']} đã gán máy {stuck_instance_id} quá 25 phút nhưng worker chưa nhận.")
                
                # Ra lệnh hủy máy bị kẹt
                try:
                    save_instance_log(int(stuck_instance_id))
                    destroy_instance(int(stuck_instance_id))
                except Exception as dest_err:
                    print(f"[Provisioner] Không thể tự động hủy máy kẹt {stuck_instance_id}: {dest_err}")
                
                # Reset DB về NULL để Provisioner thuê máy khác ở chu kỳ tiếp theo
                print(f"[Provisioner] [TIMEOUT] Reset vast_contract_id về NULL cho Job {job['id']} để chuẩn bị cấp phát lại máy mới.")
                cursor.execute("UPDATE jobs SET vast_contract_id = NULL, updated_at = ? WHERE id = ?", (now.isoformat(), job["id"]))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Provisioner] Lỗi trong quá trình xử lý timeouts: {e}")

def run_provisioner_cycle():
    """Thực thi một chu kỳ kiểm tra và phân phối tài nguyên"""
    cfg = get_config()
    pending_jobs = get_pending_jobs()
    pending_count = len(pending_jobs)
    
    # 1. Lấy danh sách instances thực tế trên Vast.ai
    instances = get_vast_instances()
    instance_states = {str(inst["id"]): inst for inst in instances} if instances else {}
    
    # 2. Tự động phát hiện và xử lý sớm các máy ảo bị chết/lỗi (stopped) hoặc bị thu hồi của các Job PENDING và PROCESSING
    needs_reload = False
    
    # Danh sách các job cần kiểm tra (tất cả job PENDING và PROCESSING có gán contract_id)
    jobs_to_check = []
    for job in pending_jobs:
        if job.get("vast_contract_id"):
            jobs_to_check.append(job)
    for job in get_processing_jobs():
        if job.get("vast_contract_id"):
            jobs_to_check.append(job)
            
    for job in jobs_to_check:
        contract_id = job.get("vast_contract_id")
        inst = instance_states.get(str(contract_id)) if instance_states else None
        
        # Nếu máy ảo tồn tại trên Vast.ai
        if inst:
            status = inst.get("actual_status", "")
            state = inst.get("cur_state", "")
            # Nếu máy ảo bị dừng (stopped) do lỗi container hoặc do worker kết thúc chương trình
            if status == "stopped" or state == "stopped":
                print(f"[Provisioner] [TỰ SỬA LỖI] Máy ảo {contract_id} của Job {job['id']} ({job['status']}) đã dừng/lỗi. Tiến hành hủy máy.")
                save_instance_log(inst["id"])
                destroy_instance(inst["id"])
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    if job["status"] == "PENDING":
                        # Đối với Job PENDING, reset vast_contract_id = NULL để thuê lại máy khác
                        cursor.execute("UPDATE jobs SET vast_contract_id = NULL, updated_at = ? WHERE id = ?", (datetime.now().isoformat(), job["id"]))
                    else:
                        # Đối với Job PROCESSING, đánh dấu FAILED vì worker đã chạy sập/exit
                        cursor.execute("UPDATE jobs SET status = ?, vast_contract_id = NULL, updated_at = ? WHERE id = ?", 
                                       (f"FAILED: Máy ảo tự dừng đột ngột (Status: {status})", datetime.now().isoformat(), job["id"]))
                    conn.commit()
                    conn.close()
                    needs_reload = True
                except Exception as db_err:
                    print(f"[Provisioner] Lỗi DB khi xử lý dừng máy ảo: {db_err}")
        
        # Nếu máy ảo đã bị xóa hoàn toàn khỏi tài khoản Vast.ai (bị thu hồi)
        elif instances: # Chỉ xử lý nếu API get_vast_instances() thành công trả về danh sách thực tế (tránh trường hợp gọi API lỗi trả về rỗng làm xóa nhầm)
            print(f"[Provisioner] [TỰ SỬA LỖI] Máy ảo {contract_id} của Job {job['id']} ({job['status']}) không còn tồn tại trên Vast.ai (bị thu hồi).")
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                if job["status"] == "PENDING":
                    cursor.execute("UPDATE jobs SET vast_contract_id = NULL, updated_at = ? WHERE id = ?", (datetime.now().isoformat(), job["id"]))
                else:
                    cursor.execute("UPDATE jobs SET status = 'FAILED: Máy ảo bị thu hồi hoặc xóa khỏi Vast.ai', vast_contract_id = NULL, updated_at = ? WHERE id = ?", 
                                   (datetime.now().isoformat(), job["id"]))
                conn.commit()
                conn.close()
                needs_reload = True
            except Exception as db_err:
                print(f"[Provisioner] Lỗi DB khi xử lý máy ảo bị thu hồi: {db_err}")
                
    if needs_reload:
        pending_jobs = get_pending_jobs()
        pending_count = len(pending_jobs)

    # 3. Thu thập các contract_id đang bận xử lý (PROCESSING) hoặc được gán cho job pending
    busy_contracts = set()
    for job in get_processing_jobs():
        if job.get("vast_contract_id"):
            busy_contracts.add(str(job["vast_contract_id"]))
    for job in pending_jobs:
        if job.get("vast_contract_id"):
            busy_contracts.add(str(job["vast_contract_id"]))
            
    # 4. Quét và Hủy ngay lập tức mọi máy ảo thừa (không có liên kết với job nào trong DB) để bảo vệ ví của sếp
    if instances:
        cleaned_instances = []
        for inst in instances:
            inst_id_str = str(inst["id"])
            if inst_id_str not in busy_contracts:
                print(f"[Provisioner] [DỌN DẸP] Phát hiện máy ảo thừa {inst_id_str} (không liên kết với job nào). Tiến hành hủy ngay lập tức.")
                save_instance_log(inst["id"])
                destroy_instance(inst["id"])
            else:
                cleaned_instances.append(inst)
        instances = cleaned_instances

    if pending_count == 0:
        # Không có job pending nào và các máy thừa đã được dọn dẹp ở trên
        return

    # Lọc các job pending chưa được gán máy ảo
    unassigned_jobs = [j for j in pending_jobs if not j.get("vast_contract_id")]
    unassigned_count = len(unassigned_jobs)

    if unassigned_count == 0:
        # Tất cả các job pending đã được gán máy ảo đang khởi động
        print(f"[Provisioner] Hàng đợi có {pending_count} Job PENDING. Tất cả đã được gán máy ảo và đang đợi khởi động xong.")
        return

    # Có job pending chưa gán máy ảo, tiến hành phân phối
    # Đếm số máy đang chạy hoặc đang chuẩn bị chạy từ những instance còn lại
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
    active_ids = [inst["id"] for inst in active_instances]
    stopped_ids = [inst["id"] for inst in stopped_instances]
    
    print(f"[Provisioner] [CHU KỲ] Hàng đợi: {pending_count} PENDING ({unassigned_count} chưa gán) | Active: {active_count} GPU {active_ids} | Stopped: {len(stopped_instances)} GPU {stopped_ids}")
    
    # Chỉ thuê máy cho những job chưa gán máy và chưa vượt giới hạn
    if active_count < cfg["max_gpus"]:
        needed = min(unassigned_count, cfg["max_gpus"] - active_count)
        print(f"[Provisioner] Cần cấp phát thêm {needed} GPU cho các job chưa gán.")
        
        for i in range(needed):
            job = unassigned_jobs[i]
            job_id = job["id"]
            
            # Ưu tiên khởi động lại máy đang Stopped để tránh Cold Start tải image
            if stopped_instances:
                target_inst = stopped_instances.pop(0)
                inst_id = target_inst["id"]
                print(f"[Provisioner] Ưu tiên tái sử dụng máy Stopped {inst_id} cho Job {job_id}")
                if start_instance(inst_id):
                    update_job_status(job_id, "PENDING", vast_contract_id=str(inst_id))
                    print(f"[Provisioner] Đã gán thành công máy Stopped {inst_id} cho Job {job_id}")
            else:
                # Nếu không có máy stopped, thuê máy mới
                print(f"[Provisioner] Không có máy Stopped. Tiến hành thuê máy mới cho Job {job_id}...")
                contract_id = rent_new_gpu()
                if contract_id:
                    update_job_status(job_id, "PENDING", vast_contract_id=contract_id)
                    print(f"[Provisioner] Đã gán thành công máy mới {contract_id} cho Job {job_id}")
                else:
                    print(f"[Provisioner] Thất bại khi thuê máy mới cho Job {job_id}.")
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
            print(f"[Provisioner] Lỗi nghiêm trọng trong chu kỳ daemon: {e}")
        time.sleep(15)

def start_provisioner_loop():
    """Khởi chạy Provisioner Daemon dưới dạng Background Thread"""
    t = threading.Thread(target=provisioner_daemon, daemon=True)
    t.start()
