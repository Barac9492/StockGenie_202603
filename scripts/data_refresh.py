#!/usr/bin/env python3
"""Cron script: refresh OHLCV cache for all stocks in universe.
Schedule: after market close (e.g., 16:30 KST for KR, 22:00 KST for US)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from models.database import init_db, get_connection
from services.data_fetcher import fetch_kr_stocks, fetch_us_stocks


def main():
    init_db()
    conn = get_connection()

    try:
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("data_refresh", "RUNNING", "Started")
        )
        conn.commit()

        stocks = conn.execute("SELECT ticker, market FROM stocks").fetchall()
        kr_tickers = [s["ticker"] for s in stocks if s["market"] == "KR"]
        us_tickers = [s["ticker"] for s in stocks if s["market"] == "US"]

        fetched = 0
        if kr_tickers:
            results = fetch_kr_stocks(kr_tickers)
            fetched += len(results)
        if us_tickers:
            results = fetch_us_stocks(us_tickers)
            fetched += len(results)

        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("data_refresh", "OK", f"Refreshed {fetched} stocks")
        )
        conn.commit()
        print(f"[{datetime.now()}] data_refresh: OK — {fetched} stocks refreshed")

    except Exception as e:
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("data_refresh", "ERROR", str(e))
        )
        conn.commit()
        print(f"[{datetime.now()}] data_refresh: ERROR — {e}", file=sys.stderr)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
