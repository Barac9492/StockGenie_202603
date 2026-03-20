# QuantRadar MVP — Implementation Tracker

## Phase 1: Foundation
- [x] config/settings.py — DB_PATH, WAL mode, app constants, .env loading
- [x] models/database.py — SQLite schema, init_db(), get_connection() with WAL
- [x] requirements.txt — all dependencies (fixed: `finance-datareader` is the PyPI name)
- [x] .env.example — SMTP config template
- [x] .gitignore — .env, *.db, __pycache__/, .streamlit/
- [x] .streamlit/config.toml — dark theme config

## Phase 2: Data Layer
- [x] services/data_fetcher.py — fetch_kr_stocks (pykrx), fetch_us_stocks (yfinance), fetch_market_context (FDR + yfinance fallback), cache to SQLite

## Phase 3: Strategy Engine
- [x] services/strategy_engine.py — strategy schema, evaluate conditions (RSI, MA crossover, PER, volume)
- [x] templates/strategies.py — 7 pre-built templates
- [x] services/backtest_runner.py — run backtest, compute scoreboard metrics

## Phase 4: Signal System
- [x] services/signal_generator.py — generate daily signals, save to SQLite
- [x] services/journal_manager.py — log signal actions, query history

## Phase 5: UI Pages
- [x] app.py — Streamlit entry point, page config, 3-step onboarding wizard
- [x] pages/1_📊_Dashboard.py — market context, signal table with journal buttons, health dot
- [x] pages/2_🔧_Strategy.py — template selector, condition builder, backtest runner + scoreboard
- [x] pages/3_📈_Stock_Detail.py — candlestick chart (Plotly), indicators, signal history
- [x] pages/4_⚙️_Settings.py — universe management, email config, data refresh

## Phase 6: Notifications & Cron
- [x] services/notifier.py — compose email digest HTML, send via SMTP
- [x] scripts/daily_signals.py — cron script with error handling → system_status
- [x] scripts/daily_digest.py — cron script with error handling → system_status
- [x] scripts/data_refresh.py — cron script with error handling → system_status

## Phase 7: Polish
- [x] Onboarding wizard (3-step in app.py)
- [x] Error handling wrappers for all cron scripts (try/except → system_status)
- [x] Verified: `streamlit run app.py` starts successfully

## Verification
- [x] `pip install -r requirements.txt` — all dependencies install (Python 3.11 venv)
- [x] `streamlit run app.py` — app starts, serves HTML
- [ ] Full E2E test (onboarding → dashboard → strategy → backtest → stock detail)
