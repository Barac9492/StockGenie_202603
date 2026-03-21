import streamlit as st
from models.database import init_db, get_connection
from templates.strategies import STRATEGY_TEMPLATES
from services.strategy_engine import save_strategy

st.set_page_config(
    page_title="QuantRadar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database
init_db()


def _ensure_price_data():
    """Auto-fetch price data on startup if cache is empty."""
    if st.session_state.get("_data_checked"):
        return
    conn = get_connection()
    cached = conn.execute("SELECT COUNT(*) FROM price_cache").fetchone()[0]
    has_stocks = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    conn.close()
    if has_stocks > 0 and cached == 0:
        with st.spinner("First load — fetching price data (this takes ~30 seconds)..."):
            from services.data_fetcher import fetch_kr_stocks, fetch_us_stocks
            conn = get_connection()
            stocks = conn.execute("SELECT ticker, market FROM stocks").fetchall()
            conn.close()
            kr = [s["ticker"] for s in stocks if s["market"] == "KR"]
            us = [s["ticker"] for s in stocks if s["market"] == "US"]
            if kr:
                try:
                    fetch_kr_stocks(kr)
                except Exception:
                    pass
            if us:
                try:
                    fetch_us_stocks(us)
                except Exception:
                    pass
    st.session_state["_data_checked"] = True


def is_first_run() -> bool:
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    conn.close()
    return count == 0


def run_onboarding():
    st.title("📡 QuantRadar Setup")
    st.markdown("Welcome! Let's get you set up in 3 steps.")

    if "onboarding_step" not in st.session_state:
        st.session_state.onboarding_step = 1

    step = st.session_state.onboarding_step

    # Step 1: Pick stocks
    if step == 1:
        st.subheader("Step 1/3 — Pick some stocks")
        st.markdown("Start with some blue chips. You can change these anytime in Settings.")

        default_kr = {
            "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
            "005380": "현대차", "051910": "LG화학",
        }
        default_us = {
            "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
            "AMZN": "Amazon", "NVDA": "NVIDIA",
        }

        st.markdown("**🇰🇷 Korean Stocks**")
        kr_selected = {}
        cols = st.columns(5)
        for i, (ticker, name) in enumerate(default_kr.items()):
            with cols[i]:
                if st.checkbox(f"{name}", value=True, key=f"kr_{ticker}"):
                    kr_selected[ticker] = name

        st.markdown("**🇺🇸 US Stocks**")
        us_selected = {}
        cols = st.columns(5)
        for i, (ticker, name) in enumerate(default_us.items()):
            with cols[i]:
                if st.checkbox(f"{name}", value=True, key=f"us_{ticker}"):
                    us_selected[ticker] = name

        if st.button("Next →", type="primary"):
            conn = get_connection()
            for ticker, name in kr_selected.items():
                conn.execute(
                    "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'KR')",
                    (ticker, name)
                )
            for ticker, name in us_selected.items():
                conn.execute(
                    "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'US')",
                    (ticker, name)
                )
            conn.commit()
            conn.close()
            st.session_state.onboarding_step = 2
            st.rerun()

    # Step 2: Choose a strategy
    elif step == 2:
        st.subheader("Step 2/3 — Choose a strategy")
        st.markdown("Pick a template to start with. You can customize it later.")

        selected_template = None
        cols = st.columns(3)
        for i, tmpl in enumerate(STRATEGY_TEMPLATES[:6]):
            with cols[i % 3]:
                conds = ", ".join(c["indicator"] for c in tmpl["conditions"])
                if st.button(f"**{tmpl['name']}**\n{conds}", key=f"tmpl_{i}", use_container_width=True):
                    selected_template = tmpl

        if selected_template:
            # Save templates to DB
            conn = get_connection()
            existing = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 1").fetchone()[0]
            conn.close()
            if existing == 0:
                for tmpl in STRATEGY_TEMPLATES:
                    save_strategy(tmpl)
            # Save user's choice as active strategy
            user_strategy = selected_template.copy()
            user_strategy["is_template"] = False
            user_strategy["name"] = f"My {selected_template['name']}"
            save_strategy(user_strategy)
            st.session_state.onboarding_step = 3
            st.rerun()

        if st.button("← Back"):
            st.session_state.onboarding_step = 1
            st.rerun()

    # Step 3: Run first backtest
    elif step == 3:
        st.subheader("Step 3/3 — Run your first backtest")
        st.markdown("We'll run a quick backtest on your selected stocks and strategy.")

        if st.button("🚀 Run Backtest", type="primary"):
            with st.spinner("Fetching data and running backtest..."):
                from services.data_fetcher import fetch_kr_stocks, fetch_us_stocks
                conn = get_connection()
                stocks = conn.execute("SELECT ticker, market FROM stocks").fetchall()
                conn.close()

                kr_tickers = [s["ticker"] for s in stocks if s["market"] == "KR"]
                us_tickers = [s["ticker"] for s in stocks if s["market"] == "US"]

                fetch_errors = []
                if kr_tickers:
                    try:
                        fetch_kr_stocks(kr_tickers)
                    except Exception as e:
                        fetch_errors.append(f"KR data: {e}")
                if us_tickers:
                    try:
                        fetch_us_stocks(us_tickers)
                    except Exception as e:
                        fetch_errors.append(f"US data: {e}")

                if fetch_errors:
                    st.warning(f"Some data could not be fetched: {'; '.join(fetch_errors)}. "
                               "You can refresh data later in Settings.")

            st.success("Setup complete! Navigate to the Dashboard using the sidebar.")
            st.session_state.onboarding_complete = True
            st.balloons()

        if st.button("← Back"):
            st.session_state.onboarding_step = 2
            st.rerun()


# Main — continue onboarding if mid-flow (steps 2-3) even though stocks exist
onboarding_in_progress = st.session_state.get("onboarding_step", 0) in (2, 3)
if (is_first_run() or onboarding_in_progress) and not st.session_state.get("onboarding_complete"):
    run_onboarding()
else:
    _ensure_price_data()
    st.title("📡 QuantRadar")

    # Quick stats
    conn = get_connection()
    num_stocks = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    num_strategies = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 0").fetchone()[0]
    num_signals = conn.execute("SELECT COUNT(*) FROM signals WHERE date = date('now')").fetchone()[0]
    conn.close()

    col1, col2, col3 = st.columns(3)
    col1.metric("Stocks Tracked", num_stocks)
    col2.metric("Active Strategies", num_strategies)
    col3.metric("Today's Signals", num_signals)

    st.markdown("---")

    # Action items — tell the user what to do next
    st.subheader("What to do next")
    if num_signals > 0:
        st.markdown("**→ Review today's signals** on the **📊 Dashboard** — decide whether to act or skip each one.")
    elif num_strategies == 0:
        st.markdown("**→ Pick a strategy** on the **🔧 Strategy** page — choose a template and run your first backtest.")
    else:
        st.markdown("**→ Check the market** on the **📊 Dashboard** — see KOSPI, S&P500, VIX, and USD/KRW at a glance.")
        st.markdown("**→ Backtest a new idea** on the **🔧 Strategy** page — try different conditions and compare results.")
        st.markdown("**→ Deep-dive a stock** on the **📈 Stock Detail** page — check the chart, indicators, and signal history.")
