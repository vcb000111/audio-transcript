import requests
import os
import sys
import io
from dotenv import load_dotenv

# Ép console sử dụng encoding UTF-8 để tránh lỗi UnicodeEncodeError trên Windows Terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Load config từ file .env ở thư mục gốc
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

def check_latest_build_log():
    owner = "vcb000111"
    repo = "audio-transcript"
    
    # Đọc GitHub Token từ .env nếu sếp có cấu hình
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json"
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
        print("[GitHub] Sử dụng GITHUB_TOKEN để xác thực tải log...")
    else:
        print("[GitHub] Không cấu hình GITHUB_TOKEN. Sẽ hiển thị trạng thái các Step và link xem trực tiếp.")
    
    # 1. Lấy danh sách workflow runs gần nhất
    runs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs"
    try:
        res = requests.get(runs_url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"[GitHub] Lỗi lấy danh sách build: {res.status_code} - {res.text}")
            return
        
        runs = res.json().get("workflow_runs", [])
        if not runs:
            print("[GitHub] Không tìm thấy lượt build nào.")
            return
        
        latest_run = runs[0]
        run_id = latest_run["id"]
        status = latest_run["status"]
        conclusion = latest_run["conclusion"]
        commit_msg = latest_run["head_commit"]["message"]
        
        print(f"\n[GitHub] Lượt build gần nhất:")
        print(f"  ID: {run_id}")
        print(f"  Trạng thái: {status.upper()} (Kết quả: {str(conclusion).upper()})")
        print(f"  Commit: {commit_msg}")
        
        # 2. Lấy danh sách các jobs và steps của run này
        jobs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
        r_jobs = requests.get(jobs_url, headers=headers, timeout=15)
        if r_jobs.status_code != 200:
            print(f"[GitHub] Không lấy được danh sách jobs: {r_jobs.status_code}")
            return
            
        jobs = r_jobs.json().get("jobs", [])
        active_job = None
        for job in jobs:
            print(f"\n  Job: {job['name']} | Trạng thái: {job['status'].upper()} | Kết quả: {str(job['conclusion']).upper()}")
            
            # Hiển thị tiến trình chi tiết của từng Step trong Job
            steps = job.get("steps", [])
            if steps:
                print("  Các bước thực thi (Steps):")
                for step in steps:
                    step_status = step["status"].upper()
                    step_conclusion = str(step["conclusion"]).upper() if step["conclusion"] else "RUNNING"
                    print(f"    - [{step_status}/{step_conclusion}] {step['name']}")
            
            if job['status'] == "in_progress" or job['conclusion'] == "failure":
                active_job = job
                
        if not active_job and jobs:
            active_job = jobs[0]
            
        if active_job:
            job_id = active_job["id"]
            # 3. Thử tải log chi tiết (chỉ hoạt động nếu có GITHUB_TOKEN)
            log_url = f"https://api.github.com/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
            if github_token:
                print(f"\n[GitHub] Đang tải log chi tiết cho Job {active_job['name']}...")
                r_log = requests.get(log_url, headers=headers, timeout=20)
                if r_log.status_code == 200:
                    log_text = r_log.text
                    lines = log_text.splitlines()
                    print(f"[GitHub] Đã tải thành công {len(lines)} dòng log.")
                    print("\n" + "="*40 + " LOG TRÍCH XUẤT THẤT BẠI/ĐANG CHẠY " + "="*40)
                    for line in lines[-100:]:
                        print(line)
                    print("="*111 + "\n")
                else:
                    print(f"[GitHub] Không thể tải log chi tiết: Status {r_log.status_code}.")
            else:
                print(f"\n[GitHub] Để xem log chi tiết ngay tại local, sếp có thể tạo Personal Access Token (classic) trên GitHub")
                print(f"và cấu hình vào file .env ở thư mục gốc: GITHUB_TOKEN=your_token")
                print(f"Sếp xem log trực tiếp trên web tại: {active_job['html_url']}")
                
    except Exception as e:
        print(f"[GitHub] Lỗi hệ thống khi kiểm tra log: {e}")

if __name__ == "__main__":
    check_latest_build_log()
