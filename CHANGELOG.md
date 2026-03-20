# Changelog

All notable changes to QuantRadar will be documented in this file.

## [0.1.0.0] - 2026-03-20

### Added
- Streamlit monolith with dark theme and 4-page navigation (Dashboard, Strategy, Stock Detail, Settings)
- SQLite database with WAL mode for concurrent cron + app access
- Data fetchers: pykrx (KR stocks), yfinance (US stocks), FinanceDataReader (indices/FX) with yfinance fallback
- Strategy engine with 8 indicators (RSI, MA crossover, PER, PBR, volume spike, price vs MA200)
- 7 pre-built strategy templates (Golden Cross, RSI Oversold, Value+Momentum, etc.)
- Backtest runner with scoreboard metrics (return, Sharpe ratio, max drawdown, win rate)
- Daily signal generator with UNIQUE constraint to prevent duplicates
- Decision journal with one-click Acted/Skipped buttons and outcome tracking
- Market context panel (KOSPI, S&P500, VIX, USD/KRW) with 5-minute cache
- 3-step onboarding wizard for first-time setup
- Candlestick chart (Plotly) with MA overlays, RSI subplot, and signal markers
- Stock universe management with Quick Add presets (KOSPI Top 10, S&P Top 10)
- Email digest system via SMTP with dark-themed HTML
- 3 cron scripts (daily_signals, daily_digest, data_refresh) with system_status monitoring
- Health indicator dot on dashboard showing cron status
- 23 unit tests covering strategy engine, database schema, and backtest runner

### Fixed
- NaN display in market context when FDR returns sparse data
- Onboarding flow skipping steps 2-3 after stock insertion
- Loading spinner exposing internal function name to users
- Race condition in signal insertion (added UNIQUE constraint + INSERT OR IGNORE)
