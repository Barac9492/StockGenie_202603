import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from models.database import init_db, get_connection
from services.data_fetcher import get_cached_prices
from services.strategy_engine import compute_rsi, compute_ma
from services.signal_generator import get_signals_for_ticker

init_db()

st.set_page_config(page_title="Stock Detail — QuantRadar", page_icon="📈", layout="wide")
st.title("📈 Stock Detail")

# Stock selector
conn = get_connection()
stocks = conn.execute("SELECT ticker, name, market FROM stocks ORDER BY market, name").fetchall()
conn.close()

if not stocks:
    st.info("No stocks in universe. Add some in Settings first.")
    st.stop()

# Check for query param or selection
ticker_options = {f"{s['ticker']} — {s['name']} ({s['market']})": s["ticker"] for s in stocks}
query_ticker = st.query_params.get("ticker", None)

if query_ticker and any(s["ticker"] == query_ticker for s in stocks):
    default_idx = next(
        i for i, s in enumerate(stocks) if s["ticker"] == query_ticker
    )
else:
    default_idx = 0

selected_label = st.selectbox("Select Stock", list(ticker_options.keys()), index=default_idx)
ticker = ticker_options[selected_label]

# Load data
df = get_cached_prices(ticker)
if df.empty:
    st.warning("No price data cached for this stock. Run data refresh.")
    st.stop()

# Candlestick chart with indicators
st.subheader("Price Chart")

fig = make_subplots(
    rows=3, cols=1, shared_xaxes=True,
    row_heights=[0.6, 0.2, 0.2],
    vertical_spacing=0.03,
)

# Candlestick
fig.add_trace(go.Candlestick(
    x=df["date"], open=df["open"], high=df["high"],
    low=df["low"], close=df["close"], name="OHLC",
    increasing_line_color="#00D26A", decreasing_line_color="#FF4B4B",
), row=1, col=1)

# Moving averages
ma20 = compute_ma(df["close"], 20)
ma50 = compute_ma(df["close"], 50)
ma200 = compute_ma(df["close"], 200)
fig.add_trace(go.Scatter(x=df["date"], y=ma20, name="MA20",
                         line=dict(color="#FFA726", width=1)), row=1, col=1)
fig.add_trace(go.Scatter(x=df["date"], y=ma50, name="MA50",
                         line=dict(color="#636EFA", width=1)), row=1, col=1)
fig.add_trace(go.Scatter(x=df["date"], y=ma200, name="MA200",
                         line=dict(color="#A3A8B8", width=1, dash="dash")), row=1, col=1)

# Signal markers
signals = get_signals_for_ticker(ticker)
buy_dates = [s["date"] for s in signals if s["signal_type"] == "BUY"]
sell_dates = [s["date"] for s in signals if s["signal_type"] == "SELL"]

buy_prices = df[df["date"].astype(str).isin(buy_dates)]["close"]
buy_dates_matched = df[df["date"].astype(str).isin(buy_dates)]["date"]
sell_prices = df[df["date"].astype(str).isin(sell_dates)]["close"]
sell_dates_matched = df[df["date"].astype(str).isin(sell_dates)]["date"]

if not buy_prices.empty:
    fig.add_trace(go.Scatter(
        x=buy_dates_matched, y=buy_prices, mode="markers", name="BUY",
        marker=dict(color="#00D26A", size=10, symbol="triangle-up"),
    ), row=1, col=1)
if not sell_prices.empty:
    fig.add_trace(go.Scatter(
        x=sell_dates_matched, y=sell_prices, mode="markers", name="SELL",
        marker=dict(color="#FF4B4B", size=10, symbol="triangle-down"),
    ), row=1, col=1)

# Volume
fig.add_trace(go.Bar(
    x=df["date"], y=df["volume"], name="Volume",
    marker_color="#636EFA", opacity=0.5,
), row=2, col=1)

# RSI
rsi = compute_rsi(df["close"])
fig.add_trace(go.Scatter(
    x=df["date"], y=rsi, name="RSI(14)",
    line=dict(color="#FFA726", width=1),
), row=3, col=1)
fig.add_hline(y=70, line_dash="dash", line_color="#FF4B4B", row=3, col=1)
fig.add_hline(y=30, line_dash="dash", line_color="#00D26A", row=3, col=1)

fig.update_layout(
    template="plotly_dark",
    height=700,
    xaxis_rangeslider_visible=False,
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
fig.update_yaxes(title_text="Price", row=1, col=1)
fig.update_yaxes(title_text="Volume", row=2, col=1)
fig.update_yaxes(title_text="RSI", row=3, col=1)

st.plotly_chart(fig, use_container_width=True)

# Key stats
st.subheader("Key Stats")
col1, col2, col3, col4 = st.columns(4)
latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) > 1 else latest
change = latest["close"] - prev["close"]
change_pct = (change / prev["close"]) * 100

col1.metric("Close", f"{latest['close']:,.0f}", delta=f"{change:+,.0f} ({change_pct:+.2f}%)")
col2.metric("Volume", f"{latest['volume']:,.0f}")
col3.metric("RSI(14)", f"{rsi.iloc[-1]:.1f}" if not rsi.empty else "N/A")
col4.metric("MA20", f"{ma20.iloc[-1]:,.0f}" if not ma20.empty else "N/A")

# Signal history
st.markdown("---")
st.subheader("Signal History")
if signals:
    for sig in signals[:20]:
        col1, col2, col3, col4, col5 = st.columns([2, 1, 2, 1, 1])
        with col1:
            st.write(sig["date"])
        with col2:
            color = "green" if sig["signal_type"] == "BUY" else "red"
            st.markdown(f":{color}[{sig['signal_type']}]")
        with col3:
            st.write(sig.get("strategy_name", "-"))
        with col4:
            st.write(f"{sig.get('price', 0):,.0f}")
        with col5:
            if sig.get("journal_action"):
                st.write(sig["journal_action"])
                if sig.get("outcome_pct") is not None:
                    st.caption(f"Outcome: {sig['outcome_pct']:+.1f}%")
            else:
                st.caption("—")
else:
    st.caption("No signals for this stock yet.")
