import json
import pandas as pd
import numpy as np
from models.database import get_connection

# Strategy schema:
# {
#   "name": str,
#   "conditions": [{"indicator": str, "operator": str, "value": float}],
#   "market": "KR" | "US" | "BOTH",
#   "is_template": bool
# }

INDICATORS = {
    "RSI": "RSI (14-day)",
    "MA_CROSS_20_50": "MA Crossover (20/50)",
    "MA_CROSS_5_20": "MA Crossover (5/20)",
    "PER": "PER (Price-to-Earnings)",
    "PBR": "PBR (Price-to-Book)",
    "VOLUME_SPIKE": "Volume Spike (vs 20d avg)",
    "PRICE_ABOVE_MA200": "Price Above MA200",
    "PRICE_BELOW_MA200": "Price Below MA200",
}

OPERATORS = ["<", "<=", ">", ">=", "==", "CROSS_ABOVE", "CROSS_BELOW"]


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_ma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period).mean()


def compute_volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
    return volume / volume.rolling(window=period).mean()


def evaluate_condition(df: pd.DataFrame, condition: dict) -> pd.Series:
    """Evaluate a single condition against OHLCV dataframe. Returns boolean Series."""
    indicator = condition["indicator"]
    operator = condition["operator"]
    value = condition.get("value", 0)

    if indicator == "RSI":
        series = compute_rsi(df["close"])
    elif indicator == "MA_CROSS_20_50":
        ma_short = compute_ma(df["close"], 20)
        ma_long = compute_ma(df["close"], 50)
        if operator == "CROSS_ABOVE":
            return (ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))
        elif operator == "CROSS_BELOW":
            return (ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))
        series = ma_short - ma_long
    elif indicator == "MA_CROSS_5_20":
        ma_short = compute_ma(df["close"], 5)
        ma_long = compute_ma(df["close"], 20)
        if operator == "CROSS_ABOVE":
            return (ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))
        elif operator == "CROSS_BELOW":
            return (ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))
        series = ma_short - ma_long
    elif indicator == "PER":
        series = pd.Series(value, index=df.index)  # PER must be provided externally
        return _compare(series, operator, value)
    elif indicator == "PBR":
        series = pd.Series(value, index=df.index)
        return _compare(series, operator, value)
    elif indicator == "VOLUME_SPIKE":
        series = compute_volume_ratio(df["volume"])
    elif indicator == "PRICE_ABOVE_MA200":
        ma200 = compute_ma(df["close"], 200)
        return df["close"] > ma200
    elif indicator == "PRICE_BELOW_MA200":
        ma200 = compute_ma(df["close"], 200)
        return df["close"] < ma200
    else:
        return pd.Series(False, index=df.index)

    return _compare(series, operator, value)


def _compare(series: pd.Series, operator: str, value: float) -> pd.Series:
    if operator == "<":
        return series < value
    elif operator == "<=":
        return series <= value
    elif operator == ">":
        return series > value
    elif operator == ">=":
        return series >= value
    elif operator == "==":
        return series == value
    return pd.Series(False, index=series.index)


def apply_strategy(df: pd.DataFrame, strategy: dict) -> pd.Series:
    """Apply all conditions (AND logic). Returns boolean Series for signal days."""
    conditions = strategy["conditions"]
    if not conditions:
        return pd.Series(False, index=df.index)

    result = pd.Series(True, index=df.index)
    for cond in conditions:
        result = result & evaluate_condition(df, cond)
    return result


def save_strategy(strategy: dict) -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO strategies (name, conditions, market, is_template) VALUES (?, ?, ?, ?)",
        (strategy["name"], json.dumps(strategy["conditions"]),
         strategy["market"], strategy.get("is_template", False))
    )
    conn.commit()
    strategy_id = cursor.lastrowid
    conn.close()
    return strategy_id


def get_strategies(templates_only: bool = False) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM strategies"
    if templates_only:
        query += " WHERE is_template = 1"
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [
        {
            "id": r["id"], "name": r["name"],
            "conditions": json.loads(r["conditions"]),
            "market": r["market"], "is_template": bool(r["is_template"]),
        }
        for r in rows
    ]


def get_strategy(strategy_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"], "name": row["name"],
        "conditions": json.loads(row["conditions"]),
        "market": row["market"], "is_template": bool(row["is_template"]),
    }
