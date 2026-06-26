import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///app.db")
DATABASE_FILE = DATABASE_URL.replace("sqlite:///", "")

def clear_db():
    if os.path.exists(DATABASE_FILE):
        print(f"[Hub DB] Connecting to database: {DATABASE_FILE}")
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs")
        conn.commit()
        print(f"[Hub DB] Successfully cleared jobs queue. Rows deleted: {cursor.rowcount}")
        conn.close()
    else:
        print(f"[Hub DB] Database file '{DATABASE_FILE}' not found.")

if __name__ == "__main__":
    clear_db()
