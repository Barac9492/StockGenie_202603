#!/usr/bin/env python3
"""Cron script: fetch data → generate signals → log status.
Schedule: 06:00 KST daily (crontab -e → 0 6 * * * python /path/to/daily_signals.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from models.database import init_db, get_connection
from services.data_fetcher import fetch_kr_stocks, fetch_us_stocks
from services.signal_generator import generate_signals


def main():
    init_db()
    conn = get_connection()

    try:
        # Log start
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("daily_signals", "RUNNING", "Started")
        )
        conn.commit()

        # Fetch latest data
        stocks = conn.execute("SELECT ticker, market FROM stocks").fetchall()
        kr_tickers = [s["ticker"] for s in stocks if s["market"] == "KR"]
        us_tickers = [s["ticker"] for s in stocks if s["market"] == "US"]

        if kr_tickers:
            fetch_kr_stocks(kr_tickers)
        if us_tickers:
            fetch_us_stocks(us_tickers)

        # Generate signals
        new_signals = generate_signals()

        # Log success
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("daily_signals", "OK", f"Generated {len(new_signals)} signals")
        )
        conn.commit()
        print(f"[{datetime.now()}] daily_signals: OK — {len(new_signals)} signals generated")

    except Exception as e:
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("daily_signals", "ERROR", str(e))
        )
        conn.commit()
        print(f"[{datetime.now()}] daily_signals: ERROR — {e}", file=sys.stderr)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
