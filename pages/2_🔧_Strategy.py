import streamlit as st
import plotly.graph_objects as go
from models.database import init_db, get_connection
from services.strategy_engine import (
    INDICATORS, OPERATORS, save_strategy, get_strategies,
)
from services.backtest_runner import run_backtest, compute_benchmark_return
from services.data_fetcher import get_cached_prices
from templates.strategies import STRATEGY_TEMPLATES

init_db()

st.set_page_config(page_title="Strategy — QuantRadar", page_icon="🔧", layout="wide")
st.title("🔧 Strategy Builder")

# Template selector
st.subheader("Templates")
cols = st.columns(4)
for i, tmpl in enumerate(STRATEGY_TEMPLATES):
    with cols[i % 4]:
        if st.button(tmpl["name"], key=f"tmpl_{i}", use_container_width=True):
            st.session_state.strategy_conditions = [c.copy() for c in tmpl["conditions"]]
            st.session_state.strategy_name = tmpl["name"]
            st.rerun()

st.markdown("---")

# Condition builder
st.subheader("Conditions")

if "strategy_conditions" not in st.session_state:
    # Auto-select RSI Oversold Bounce as default so backtest isn't empty
    default = STRATEGY_TEMPLATES[1]  # RSI Oversold Bounce
    st.session_state.strategy_conditions = [c.copy() for c in default["conditions"]]
    st.session_state.strategy_name = default["name"]

strategy_name = st.text_input(
    "Strategy Name",
    value=st.session_state.get("strategy_name", "My Strategy")
)

conditions = st.session_state.strategy_conditions

for i, cond in enumerate(conditions):
    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
    with col1:
        indicator = st.selectbox(
            "Indicator", list(INDICATORS.keys()),
            index=list(INDICATORS.keys()).index(cond["indicator"]) if cond["indicator"] in INDICATORS else 0,
            key=f"ind_{i}",
            format_func=lambda x: INDICATORS.get(x, x),
        )
        conditions[i]["indicator"] = indicator
    with col2:
        operator = st.selectbox(
            "Operator", OPERATORS,
            index=OPERATORS.index(cond["operator"]) if cond["operator"] in OPERATORS else 0,
            key=f"op_{i}",
        )
        conditions[i]["operator"] = operator
    with col3:
        value = st.number_input("Value", value=float(cond.get("value", 0)), key=f"val_{i}")
        conditions[i]["value"] = value
    with col4:
        if st.button("✕", key=f"del_{i}"):
            conditions.pop(i)
            st.rerun()

if len(conditions) < 3:
    if st.button("+ Add Condition"):
        conditions.append({"indicator": "RSI", "operator": "<", "value": 30})
        st.rerun()

market = st.selectbox("Market", ["BOTH", "KR", "US"])

col_save, col_bt = st.columns(2)
with col_save:
    if st.button("💾 Save Strategy", type="primary"):
        strategy = {
            "name": strategy_name,
            "conditions": conditions,
            "market": market,
            "is_template": False,
        }
        sid = save_strategy(strategy)
        st.success(f"Strategy saved (ID: {sid})")

st.markdown("---")

# Backtest
st.subheader("Backtest")

conn = get_connection()
stocks = conn.execute("SELECT ticker, name, market FROM stocks").fetchall()
conn.close()

if stocks:
    ticker_options = {f"{s['ticker']} — {s['name']}": s["ticker"] for s in stocks}
    selected_label = st.selectbox("Stock to backtest", list(ticker_options.keys()))
    selected_ticker = ticker_options[selected_label]

    if st.button("▶ Run Backtest"):
        if not conditions:
            st.warning("No conditions set. Select a template or add conditions above.")
        elif (df := get_cached_prices(selected_ticker)).empty or len(df) < 50:
            st.warning("Not enough price data. Run data refresh first.")
        else:
            strategy = {
                "name": strategy_name,
                "conditions": conditions,
                "market": market,
            }
            with st.spinner("Running backtest..."):
                results = run_backtest(df, strategy)
                benchmark = compute_benchmark_return(df)

            # Scoreboard
            st.subheader("Scoreboard")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Return", f"{results['total_return_pct']}%",
                       delta=f"vs B&H {benchmark}%")
            c2.metric("Sharpe Ratio", results["sharpe_ratio"])
            c3.metric("Max Drawdown", f"{results['max_drawdown_pct']}%")
            c4.metric("Win Rate", f"{results['win_rate_pct']}%",
                       delta=f"{results['num_trades']} trades")
            c5.metric("Avg Trade", f"{results.get('avg_trade_pct', 0)}%")

            # Action items based on results
            st.markdown("---")
            st.subheader("What this means")

            if results["num_trades"] == 0:
                st.warning("**No trades triggered.** This strategy's conditions are too strict for this stock. "
                           "Try loosening the thresholds (e.g., RSI < 35 instead of < 30) or pick a different template.")
            else:
                # Grade the strategy
                if results["total_return_pct"] > benchmark:
                    st.success(f"**Strategy beats buy & hold** by {results['total_return_pct'] - benchmark:+.1f}%")
                elif results["total_return_pct"] > 0:
                    st.info(f"**Positive return** but underperforms buy & hold ({benchmark}%). "
                            "The strategy trades selectively — consider if the lower drawdown is worth it.")
                else:
                    st.error(f"**Negative return.** This strategy lost money on {selected_label.split(' — ')[1]}. "
                             "Try a different template or adjust conditions.")

                actions = []
                if results["win_rate_pct"] >= 60 and results["sharpe_ratio"] > 0.5:
                    actions.append("**→ Save this strategy** and use it for daily signal generation")
                if results["max_drawdown_pct"] < -15:
                    actions.append("**→ Consider tighter stop-loss** — max drawdown was significant")
                if results["num_trades"] < 5:
                    actions.append("**→ Test on more stocks** to see if the pattern holds across your universe")
                if results["num_trades"] >= 5:
                    actions.append(f"**→ Check individual trades** on **📈 Stock Detail** for {selected_label.split(' — ')[0]}")
                actions.append("**→ Compare templates** — try other strategies on the same stock to find the best fit")

                for action in actions:
                    st.markdown(action)

            # Equity curve
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=results["dates"], y=results["equity_curve"],
                mode="lines", name="Strategy",
                line=dict(color="#636EFA", width=2),
            ))
            fig.update_layout(
                title="Equity Curve",
                template="plotly_dark",
                height=400,
                xaxis_title="Date",
                yaxis_title="Portfolio Value",
            )
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No stocks in universe. Add some in Settings first.")

# Saved strategies
st.markdown("---")
st.subheader("Saved Strategies")
saved = get_strategies()
if saved:
    for s in saved:
        with st.expander(f"{'📋' if s['is_template'] else '⚡'} {s['name']} ({s['market']})"):
            for c in s["conditions"]:
                st.write(f"- {INDICATORS.get(c['indicator'], c['indicator'])} {c['operator']} {c['value']}")
else:
    st.caption("No strategies saved yet.")
