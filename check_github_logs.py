import requests
import sys
import time

def check_latest_build_log():
    owner = "vcb000111"
    repo = "audio-transcript"
    headers = {
        "Accept": "application/json"
    }
    
    # 1. Lấy danh sách workflow runs gần nhất
    runs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs"
    print(f"[GitHub] Đang kiểm tra danh sách build gần nhất trên GitHub: {runs_url}")
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
        
        print(f"[GitHub] Lượt build gần nhất:")
        print(f"  ID: {run_id}")
        print(f"  Trạng thái: {status} (Kết quả: {conclusion})")
        print(f"  Commit: {commit_msg}")
        
        # 2. Lấy danh sách các jobs của run này
        jobs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
        r_jobs = requests.get(jobs_url, headers=headers, timeout=15)
        if r_jobs.status_code != 200:
            print(f"[GitHub] Không lấy được danh sách jobs: {r_jobs.status_code}")
            return
            
        jobs = r_jobs.json().get("jobs", [])
        failed_job = None
        for job in jobs:
            print(f"  - Job: {job['name']} | Trạng thái: {job['status']} | Kết quả: {job['conclusion']}")
            if job['conclusion'] == "failure" or job['status'] == "in_progress":
                failed_job = job
                
        if not failed_job and jobs:
            # Nếu không tìm thấy job thất bại cụ thể thì lấy job đầu tiên
            failed_job = jobs[0]
            
        if failed_job:
            job_id = failed_job["id"]
            # 3. Lấy log của job
            # Endpoint lấy log dạng text/plain
            log_url = f"https://api.github.com/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
            print(f"[GitHub] Đang tải log chi tiết cho Job {failed_job['name']} ({job_id})...")
            # GitHub yêu cầu redirect và có auth token hoặc không tùy thuộc vào repo public/private.
            # Vì repo này public, API trả về redirect trực tiếp sang file log.
            r_log = requests.get(log_url, timeout=20)
            if r_log.status_code == 200:
                log_text = r_log.text
                lines = log_text.splitlines()
                print(f"[GitHub] Đã tải thành công {len(lines)} dòng log.")
                print("\n" + "="*40 + " 100 DÒNG LOG CUỐI CÙNG BỊ LỖI " + "="*40)
                # In 100 dòng cuối cùng
                for line in lines[-100:]:
                    print(line)
                print("="*111 + "\n")
            else:
                print(f"[GitHub] Không thể tải log trực tiếp (API trả về status {r_log.status_code}).")
                print(f"Sếp có thể xem trực tiếp tại trình duyệt: {failed_job['html_url']}")
    except Exception as e:
        print(f"[GitHub] Lỗi hệ thống khi kiểm tra log: {e}")

if __name__ == "__main__":
    check_latest_build_log()
