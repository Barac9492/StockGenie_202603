import pandas as pd
import numpy as np
from services.strategy_engine import apply_strategy


def run_backtest(df: pd.DataFrame, strategy: dict, initial_capital: float = 10_000_000) -> dict:
    """
    Run a simple long-only backtest.
    Returns scoreboard: return_pct, sharpe, max_drawdown, win_rate, trades, equity_curve.
    """
    df = df.copy().reset_index(drop=True)
    signals = apply_strategy(df, strategy)

    capital = initial_capital
    position = 0
    entry_price = 0.0
    trades = []
    equity = [capital]

    for i in range(len(df)):
        price = df["close"].iloc[i]

        if signals.iloc[i] and position == 0:
            # Buy
            position = capital / price
            entry_price = price
            capital = 0
        elif position > 0 and i > 0:
            # Simple exit: sell after 10 days or if RSI > 70 (simplified)
            days_held = i - next(
                (j for j in range(i - 1, -1, -1) if signals.iloc[j]), i
            )
            if days_held >= 10:
                capital = position * price
                ret = (price - entry_price) / entry_price
                trades.append(ret)
                position = 0

        current_value = capital + (position * price if position > 0 else 0)
        equity.append(current_value)

    # Force close final position
    if position > 0:
        final_price = df["close"].iloc[-1]
        capital = position * final_price
        ret = (final_price - entry_price) / entry_price
        trades.append(ret)

    equity_series = pd.Series(equity[1:])  # align with df length
    if len(equity_series) < len(df):
        equity_series = pd.concat(
            [equity_series, pd.Series([equity_series.iloc[-1]] * (len(df) - len(equity_series)))],
            ignore_index=True
        )
    equity_series = equity_series[:len(df)]

    # Compute metrics
    total_return = (equity_series.iloc[-1] / initial_capital - 1) * 100

    daily_returns = equity_series.pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0

    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    max_drawdown = drawdown.min() * 100

    win_rate = (sum(1 for t in trades if t > 0) / len(trades) * 100) if trades else 0

    return {
        "total_return_pct": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "win_rate_pct": round(win_rate, 1),
        "num_trades": len(trades),
        "equity_curve": equity_series.tolist(),
        "dates": df["date"].tolist() if "date" in df.columns else list(range(len(df))),
    }


def compute_benchmark_return(df: pd.DataFrame) -> float:
    """Simple buy-and-hold return for comparison."""
    if df.empty:
        return 0.0
    return round((df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100, 2)
