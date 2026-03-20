import pandas as pd
from datetime import datetime, timedelta
from models.database import get_connection
from config.settings import DEFAULT_HISTORY_YEARS


def fetch_kr_stocks(tickers: list[str], start: str | None = None, end: str | None = None) -> dict[str, pd.DataFrame]:
    """Fetch KR stock OHLCV via pykrx, cache to SQLite."""
    from pykrx import stock as krx

    if end is None:
        end = datetime.now().strftime("%Y%m%d")
    if start is None:
        start = (datetime.now() - timedelta(days=365 * DEFAULT_HISTORY_YEARS)).strftime("%Y%m%d")

    results = {}
    conn = get_connection()
    for ticker in tickers:
        try:
            df = krx.get_market_ohlcv_by_date(start, end, ticker)
            if df.empty:
                continue
            df = df.reset_index()
            # pykrx returns Korean column names — rename by position
            col_map = {df.columns[0]: "date"}
            # Map Korean or English column names
            kr_to_en = {"시가": "open", "고가": "high", "저가": "low", "종가": "close",
                        "거래량": "volume", "등락률": "change_pct", "거래대금": "trading_value"}
            for col in df.columns[1:]:
                if col in kr_to_en:
                    col_map[col] = kr_to_en[col]
            df = df.rename(columns=col_map)
            df = df[["date", "open", "high", "low", "close", "volume"]]
            df["ticker"] = ticker
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            _cache_prices(conn, ticker, df)
            results[ticker] = df
        except Exception:
            continue
    conn.close()
    return results


def fetch_us_stocks(tickers: list[str], start: str | None = None, end: str | None = None) -> dict[str, pd.DataFrame]:
    """Fetch US stock OHLCV via yfinance, cache to SQLite."""
    import yfinance as yf

    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if start is None:
        start = (datetime.now() - timedelta(days=365 * DEFAULT_HISTORY_YEARS)).strftime("%Y-%m-%d")

    results = {}
    conn = get_connection()
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            df = t.history(start=start, end=end)
            if df.empty:
                continue
            df = df.reset_index()
            df = df.rename(columns={
                "Date": "date", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume"
            })
            df = df[["date", "open", "high", "low", "close", "volume"]]
            df["ticker"] = ticker
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            _cache_prices(conn, ticker, df)
            results[ticker] = df
        except Exception:
            continue
    conn.close()
    return results


def _make_context_entry(df: pd.DataFrame) -> dict | None:
    """Build a market context dict from a Close series, handling NaN safely."""
    closes = df["Close"].dropna()
    if len(closes) < 1:
        return None
    value = round(float(closes.iloc[-1]), 2)
    if len(closes) > 1:
        prev = float(closes.iloc[-2])
        change = round(value - prev, 2)
        change_pct = round((value / prev - 1) * 100, 2) if prev != 0 else 0.0
    else:
        change = 0.0
        change_pct = 0.0
    return {"value": value, "change": change, "change_pct": change_pct}


def fetch_market_context() -> dict:
    """Fetch market indices: KOSPI, S&P500, VIX, USD/KRW."""
    context = {}

    # Try FDR first for KR data, fallback to yfinance
    try:
        import FinanceDataReader as fdr
        kospi = fdr.DataReader("KS11", datetime.now() - timedelta(days=7))
        if not kospi.empty:
            entry = _make_context_entry(kospi)
            if entry:
                context["KOSPI"] = entry
        usdkrw = fdr.DataReader("USD/KRW", datetime.now() - timedelta(days=7))
        if not usdkrw.empty:
            entry = _make_context_entry(usdkrw)
            if entry:
                context["USD/KRW"] = entry
    except Exception:
        pass

    # yfinance for US indices + fallback
    try:
        import yfinance as yf
        for symbol, label in [("^GSPC", "S&P500"), ("^VIX", "VIX")]:
            t = yf.Ticker(symbol)
            hist = t.history(period="5d")
            if not hist.empty:
                entry = _make_context_entry(hist)
                if entry:
                    context[label] = entry

        # yfinance fallback for missing KR data
        if "KOSPI" not in context:
            t = yf.Ticker("^KS11")
            hist = t.history(period="5d")
            if not hist.empty:
                entry = _make_context_entry(hist)
                if entry:
                    context["KOSPI"] = entry
        if "USD/KRW" not in context:
            t = yf.Ticker("KRW=X")
            hist = t.history(period="5d")
            if not hist.empty:
                entry = _make_context_entry(hist)
                if entry:
                    context["USD/KRW"] = entry
    except Exception:
        pass

    return context


def get_cached_prices(ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Read OHLCV from SQLite cache."""
    conn = get_connection()
    query = "SELECT date, open, high, low, close, volume FROM price_cache WHERE ticker = ?"
    params: list = [ticker]
    if start:
        query += " AND date >= ?"
        params.append(start)
    if end:
        query += " AND date <= ?"
        params.append(end)
    query += " ORDER BY date"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def _cache_prices(conn, ticker: str, df: pd.DataFrame):
    """Upsert OHLCV data into price_cache."""
    rows = [
        (ticker, row["date"], row["open"], row["high"], row["low"], row["close"], row["volume"])
        for _, row in df.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO price_cache (ticker, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows
    )
    conn.commit()
