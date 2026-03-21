import streamlit as st
from datetime import datetime
from models.database import init_db, get_connection
from services.data_fetcher import fetch_market_context
from services.signal_generator import get_todays_signals
from services.journal_manager import record_action, get_unreviewed_signals

init_db()

st.set_page_config(page_title="Dashboard — QuantRadar", page_icon="📊", layout="wide")
st.title("📊 Dashboard")


# Health dot
def get_health_status() -> tuple[str, str]:
    conn = get_connection()
    row = conn.execute(
        "SELECT status, message, timestamp FROM system_status ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return "🟡", "No cron data yet"
    if row["status"] == "OK":
        return "🟢", f"Last run: {row['timestamp']}"
    elif row["status"] == "ERROR":
        return "🔴", f"Error: {row['message']}"
    return "🟡", f"Running: {row['message']}"


health_dot, health_msg = get_health_status()
st.caption(f"{health_dot} System: {health_msg}")


# Market Context
st.subheader("Market Context")


@st.cache_data(ttl=300, show_spinner="Loading market data...")
def _get_market_context():
    return fetch_market_context()


context = _get_market_context()
if context:
    cols = st.columns(4)
    for i, (label, data) in enumerate(context.items()):
        with cols[i % 4]:
            delta_str = f"{data['change']:+.2f} ({data['change_pct']:+.2f}%)"
            st.metric(label, f"{data['value']:,.2f}", delta=delta_str)
else:
    st.info("Market data unavailable. Run data refresh or check your connection.")

st.markdown("---")

# Today's Signals
st.subheader("Today's Signals")
signals = get_todays_signals()

if signals:
    for sig in signals:
        col1, col2, col3, col4, col5 = st.columns([2, 1, 2, 1, 2])
        with col1:
            st.write(f"**{sig['ticker']}**")
        with col2:
            color = "green" if sig["signal_type"] == "BUY" else "red"
            st.markdown(f":{color}[**{sig['signal_type']}**]")
        with col3:
            st.write(sig.get("strategy_name", "-"))
        with col4:
            st.write(f"{sig.get('price', 0):,.0f}")
        with col5:
            if sig.get("journal_action"):
                st.write(f"✅ {sig['journal_action']}")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Acted", key=f"act_{sig['id']}"):
                        record_action(sig["id"], "ACTED")
                        st.rerun()
                with c2:
                    if st.button("Skipped", key=f"skip_{sig['id']}"):
                        record_action(sig["id"], "SKIPPED")
                        st.rerun()
else:
    st.info("No signals today. Here's what you can do:")
    st.markdown("**→ Run a backtest** on the **🔧 Strategy** page to evaluate your strategy")
    st.markdown("**→ Check a stock** on **📈 Stock Detail** to see charts and indicators")
    st.markdown("**→ Add more stocks** in **⚙️ Settings** to expand your signal universe")

st.markdown("---")

# Unreviewed signals from previous days
st.subheader("Pending Review")
unreviewed = get_unreviewed_signals()
if unreviewed:
    st.caption(f"{len(unreviewed)} signals need your review")
    for sig in unreviewed[:10]:
        col1, col2, col3, col4 = st.columns([2, 1, 2, 2])
        with col1:
            st.write(f"{sig['ticker']} — {sig['date']}")
        with col2:
            color = "green" if sig["signal_type"] == "BUY" else "red"
            st.markdown(f":{color}[{sig['signal_type']}]")
        with col3:
            st.write(sig.get("strategy_name", "-"))
        with col4:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Acted", key=f"rev_act_{sig['id']}"):
                    record_action(sig["id"], "ACTED")
                    st.rerun()
            with c2:
                if st.button("Skipped", key=f"rev_skip_{sig['id']}"):
                    record_action(sig["id"], "SKIPPED")
                    st.rerun()
else:
    st.caption("All signals reviewed ✓")
