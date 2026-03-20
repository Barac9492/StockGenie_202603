from datetime import datetime
from models.database import get_connection
from services.strategy_engine import apply_strategy, get_strategies
from services.data_fetcher import get_cached_prices


def generate_signals(strategy_id: int | None = None):
    """Generate signals for all stocks in universe against active strategy."""
    conn = get_connection()

    # Get stocks
    stocks = conn.execute("SELECT ticker, market FROM stocks").fetchall()

    # Get strategy
    if strategy_id:
        from services.strategy_engine import get_strategy
        strategies = [get_strategy(strategy_id)]
    else:
        strategies = get_strategies()
        strategies = [s for s in strategies if not s["is_template"]]
        if not strategies:
            # Use first template as fallback
            strategies = get_strategies(templates_only=True)[:1]

    if not strategies:
        conn.close()
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    new_signals = []

    for stock in stocks:
        ticker = stock["ticker"]
        market = stock["market"]
        df = get_cached_prices(ticker)
        if df.empty or len(df) < 50:
            continue

        for strategy in strategies:
            if strategy is None:
                continue
            if strategy["market"] != "BOTH" and strategy["market"] != market:
                continue

            signals = apply_strategy(df, strategy)
            if signals.iloc[-1]:  # Signal on latest day
                price = df["close"].iloc[-1]
                # Determine signal type based on strategy name
                signal_type = "SELL" if "short" in strategy["name"].lower() or "death" in strategy["name"].lower() else "BUY"
                strength = 1.0  # Simplified

                conn.execute(
                    "INSERT OR IGNORE INTO signals (ticker, date, signal_type, strategy_id, price, strength) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ticker, today, signal_type, strategy["id"], price, strength)
                )
                    new_signals.append({
                        "ticker": ticker, "date": today, "type": signal_type,
                        "strategy": strategy["name"], "price": price
                    })

    conn.commit()
    conn.close()
    return new_signals


def get_todays_signals() -> list[dict]:
    conn = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT s.id, s.ticker, s.signal_type, s.price, s.strength,
               st.name as strategy_name,
               j.action as journal_action
        FROM signals s
        LEFT JOIN strategies st ON s.strategy_id = st.id
        LEFT JOIN journal j ON j.signal_id = s.id
        WHERE s.date = ?
        ORDER BY s.created_at DESC
    """, (today,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signals_for_ticker(ticker: str, limit: int = 50) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.*, st.name as strategy_name, j.action as journal_action, j.outcome_pct
        FROM signals s
        LEFT JOIN strategies st ON s.strategy_id = st.id
        LEFT JOIN journal j ON j.signal_id = s.id
        WHERE s.ticker = ?
        ORDER BY s.date DESC LIMIT ?
    """, (ticker, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
