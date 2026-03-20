#!/usr/bin/env python3
"""Cron script: read today's signals → send email digest.
Schedule: 08:30 KST daily (crontab -e → 30 8 * * * python /path/to/daily_digest.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from models.database import init_db, get_connection
from services.notifier import send_digest


def main():
    init_db()
    conn = get_connection()

    try:
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("daily_digest", "RUNNING", "Started")
        )
        conn.commit()

        result = send_digest()

        if result:
            conn.execute(
                "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
                ("daily_digest", "OK", "Email sent")
            )
            print(f"[{datetime.now()}] daily_digest: OK — email sent")
        else:
            conn.execute(
                "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
                ("daily_digest", "OK", "Skipped — email not configured")
            )
            print(f"[{datetime.now()}] daily_digest: Skipped — email not configured")
        conn.commit()

    except Exception as e:
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("daily_digest", "ERROR", str(e))
        )
        conn.commit()
        print(f"[{datetime.now()}] daily_digest: ERROR — {e}", file=sys.stderr)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
