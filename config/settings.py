import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "quantradar.db"))

# SQLite WAL mode for concurrent cron + Streamlit access
DB_WAL_MODE = True

# Cache TTL for Streamlit queries (seconds)
CACHE_TTL = 300

# Email / SMTP
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")

# Data fetch defaults
DEFAULT_HISTORY_YEARS = 3
BACKTEST_BENCHMARK_KR = "KOSPI"
BACKTEST_BENCHMARK_US = "^GSPC"
