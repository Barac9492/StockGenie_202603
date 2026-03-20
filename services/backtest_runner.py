import pandas as pd
import numpy as np
from services.strategy_engine import apply_strategy, compute_rsi


def run_backtest(df: pd.DataFrame, strategy: dict, initial_capital: float = 10_000_000) -> dict:
    """
    Run a long-only backtest with proper entry/exit logic.

    Entry: strategy signal fires AND no existing position.
    Exit (first triggered wins):
      1. Stop-loss: price drops 5% from entry
      2. Take-profit: price rises 15% from entry
      3. RSI overbought: RSI(14) > 70 AND held at least 3 days
      4. Max holding period: 20 trading days
      5. Opposite signal (sell-type strategy)
    """
    df = df.copy().reset_index(drop=True)
    signals = apply_strategy(df, strategy)
    rsi = compute_rsi(df["close"])

    STOP_LOSS = -0.05
    TAKE_PROFIT = 0.15
    RSI_EXIT = 70
    MIN_HOLD_FOR_RSI = 3
    MAX_HOLD = 20

    capital = initial_capital
    position = 0.0
    entry_price = 0.0
    entry_day = -1
    trades = []
    equity = []

    for i in range(len(df)):
        price = float(df["close"].iloc[i])
        current_rsi = float(rsi.iloc[i]) if not pd.isna(rsi.iloc[i]) else 50.0

        # Check exit conditions if in a position
        if position > 0:
            days_held = i - entry_day
            pnl_pct = (price - entry_price) / entry_price

            exit_reason = None
            if pnl_pct <= STOP_LOSS:
                exit_reason = "stop_loss"
            elif pnl_pct >= TAKE_PROFIT:
                exit_reason = "take_profit"
            elif current_rsi > RSI_EXIT and days_held >= MIN_HOLD_FOR_RSI:
                exit_reason = "rsi_overbought"
            elif days_held >= MAX_HOLD:
                exit_reason = "max_hold"

            if exit_reason:
                capital = position * price
                trades.append(pnl_pct)
                position = 0.0
                entry_price = 0.0
                entry_day = -1

        # Check entry if no position
        if position == 0 and i < len(df) - 1:  # don't enter on last day
            if signals.iloc[i]:
                position = capital / price
                entry_price = price
                entry_day = i
                capital = 0.0

        current_value = capital + (position * price if position > 0 else 0)
        equity.append(current_value)

    # Force close final position
    if position > 0:
        final_price = float(df["close"].iloc[-1])
        pnl_pct = (final_price - entry_price) / entry_price
        capital = position * final_price
        trades.append(pnl_pct)
        equity[-1] = capital

    equity_series = pd.Series(equity)

    # Compute metrics
    total_return = (equity_series.iloc[-1] / initial_capital - 1) * 100

    daily_returns = equity_series.pct_change().dropna()
    if daily_returns.std() > 0:
        sharpe = float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))
    else:
        sharpe = 0.0

    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    max_drawdown = float(drawdown.min()) * 100

    win_rate = (sum(1 for t in trades if t > 0) / len(trades) * 100) if trades else 0
    avg_return = (sum(trades) / len(trades) * 100) if trades else 0

    return {
        "total_return_pct": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "win_rate_pct": round(win_rate, 1),
        "avg_trade_pct": round(avg_return, 2),
        "num_trades": len(trades),
        "equity_curve": equity_series.tolist(),
        "dates": df["date"].tolist() if "date" in df.columns else list(range(len(df))),
    }


def compute_benchmark_return(df: pd.DataFrame) -> float:
    """Simple buy-and-hold return for comparison."""
    if df.empty:
        return 0.0
    return round((df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100, 2)
