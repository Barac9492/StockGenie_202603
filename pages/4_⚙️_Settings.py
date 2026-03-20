import streamlit as st
from models.database import init_db, get_connection

init_db()

st.set_page_config(page_title="Settings — QuantRadar", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")

# Universe management
st.subheader("Stock Universe")

conn = get_connection()
stocks = conn.execute("SELECT ticker, name, market FROM stocks ORDER BY market, name").fetchall()
conn.close()

# Current stocks
if stocks:
    st.caption(f"{len(stocks)} stocks tracked")
    for stock in stocks:
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            st.write(f"**{stock['ticker']}** — {stock['name']}")
        with col2:
            st.write(f"{'🇰🇷' if stock['market'] == 'KR' else '🇺🇸'} {stock['market']}")
        with col3:
            if st.button("Remove", key=f"rm_{stock['ticker']}"):
                conn = get_connection()
                conn.execute("DELETE FROM stocks WHERE ticker = ?", (stock["ticker"],))
                conn.commit()
                conn.close()
                st.rerun()
else:
    st.info("No stocks in universe yet.")

st.markdown("---")

# Add stocks
st.subheader("Add Stocks")

col1, col2 = st.columns(2)
with col1:
    new_ticker = st.text_input("Ticker", placeholder="e.g. 005930 or AAPL")
with col2:
    new_name = st.text_input("Name", placeholder="e.g. 삼성전자 or Apple")

new_market = st.selectbox("Market", ["KR", "US"])

if st.button("➕ Add Stock", type="primary"):
    if new_ticker and new_name:
        conn = get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, ?)",
            (new_ticker.strip(), new_name.strip(), new_market)
        )
        conn.commit()
        conn.close()
        st.success(f"Added {new_ticker}")
        st.rerun()
    else:
        st.warning("Please enter both ticker and name.")

# Quick add presets
st.markdown("---")
st.subheader("Quick Add")

col1, col2 = st.columns(2)
with col1:
    if st.button("🇰🇷 KOSPI Top 10", use_container_width=True):
        kospi_top = {
            "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
            "005380": "현대차", "051910": "LG화학", "006400": "삼성SDI",
            "003670": "포스코홀딩스", "105560": "KB금융", "055550": "신한지주",
            "035720": "카카오",
        }
        conn = get_connection()
        for ticker, name in kospi_top.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'KR')",
                (ticker, name)
            )
        conn.commit()
        conn.close()
        st.success("Added KOSPI Top 10")
        st.rerun()

with col2:
    if st.button("🇺🇸 S&P Top 10", use_container_width=True):
        sp_top = {
            "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
            "AMZN": "Amazon", "NVDA": "NVIDIA", "META": "Meta",
            "TSLA": "Tesla", "BRK-B": "Berkshire Hathaway",
            "JPM": "JPMorgan Chase", "V": "Visa",
        }
        conn = get_connection()
        for ticker, name in sp_top.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'US')",
                (ticker, name)
            )
        conn.commit()
        conn.close()
        st.success("Added S&P Top 10")
        st.rerun()

# Email configuration
st.markdown("---")
st.subheader("Email Digest Configuration")
st.caption("Configure in `.env` file. Current status:")

from config.settings import SMTP_USER, EMAIL_TO

if SMTP_USER and EMAIL_TO:
    st.success(f"Email configured: {SMTP_USER} → {EMAIL_TO}")

    if st.button("📧 Send Test Email"):
        try:
            from services.notifier import send_digest
            send_digest()
            st.success("Test email sent!")
        except Exception as e:
            st.error(f"Failed to send: {e}")
else:
    st.warning("Email not configured. Set SMTP_USER, SMTP_PASS, EMAIL_TO in `.env`")

# Data refresh
st.markdown("---")
st.subheader("Data Management")

if st.button("🔄 Refresh All Price Data"):
    with st.spinner("Fetching latest data..."):
        from services.data_fetcher import fetch_kr_stocks, fetch_us_stocks

        conn = get_connection()
        all_stocks = conn.execute("SELECT ticker, market FROM stocks").fetchall()
        conn.close()

        kr = [s["ticker"] for s in all_stocks if s["market"] == "KR"]
        us = [s["ticker"] for s in all_stocks if s["market"] == "US"]

        if kr:
            fetch_kr_stocks(kr)
        if us:
            fetch_us_stocks(us)

    st.success("Price data refreshed!")
