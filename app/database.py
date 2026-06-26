import sqlite3
import os
from datetime import datetime

DATABASE_FILE = os.getenv("DATABASE_URL", "sqlite:///app.db").replace("sqlite:///", "")

def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # Đảm bảo thư mục cha tồn tại
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_FILE)), exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        video_name TEXT,
        video_path TEXT,
        audio_path TEXT,
        srt_path TEXT,
        vast_contract_id TEXT,
        callback_token TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def create_job(job_id: str, video_name: str, video_path: str, audio_path: str, callback_token: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO jobs (id, status, video_name, video_path, audio_path, callback_token, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (job_id, "PENDING", video_name, video_path, audio_path, callback_token, now, now))
    conn.commit()
    conn.close()

def get_job(job_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def update_job_status(job_id: str, status: str, vast_contract_id: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    if vast_contract_id:
        cursor.execute("""
        UPDATE jobs 
        SET status = ?, vast_contract_id = ?, updated_at = ?
        WHERE id = ?
        """, (status, vast_contract_id, now, job_id))
    else:
        cursor.execute("""
        UPDATE jobs 
        SET status = ?, updated_at = ?
        WHERE id = ?
        """, (status, now, job_id))
    conn.commit()
    conn.close()

def update_job_srt(job_id: str, srt_path: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
    UPDATE jobs 
    SET status = ?, srt_path = ?, updated_at = ?
    WHERE id = ?
    """, ("COMPLETED", srt_path, now, job_id))
    conn.commit()
    conn.close()

def get_pending_jobs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE status = 'PENDING'")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_processing_jobs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE status = 'PROCESSING'")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def claim_next_job():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("BEGIN TRANSACTION")
    cursor.execute("SELECT * FROM jobs WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT 1")
    row = cursor.fetchone()
    if row:
        job = dict(row)
        now = datetime.now().isoformat()
        cursor.execute("UPDATE jobs SET status = 'PROCESSING', updated_at = ? WHERE id = ?", (now, job["id"]))
        conn.commit()
        conn.close()
        return job
    conn.commit()
    conn.close()
    return None

