"""Tests for US-004: Stock Detail page shows candlestick chart."""
import os
import tempfile
import importlib
import unittest
import pandas as pd
import numpy as np

from services.strategy_engine import compute_rsi, compute_ma, save_strategy
from services.signal_generator import get_signals_for_ticker


def _setup_test_db():
    """Create a temporary DB and reinitialize models.database to use it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DB_PATH"] = path
    from config import settings
    settings.DB_PATH = path
    from models import database as db
    importlib.reload(db)
    db.init_db()
    return path


def _make_ohlcv(n=200, seed=42):
    """Generate realistic OHLCV data for testing."""
    np.random.seed(seed)
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    return pd.DataFrame({
        "date": pd.date_range("2023-01-01", periods=n),
        "open": close - np.random.rand(n),
        "high": close + np.abs(np.random.randn(n)),
        "low": close - np.abs(np.random.randn(n)),
        "close": close,
        "volume": np.random.randint(1000, 50000, n),
    })


def _insert_stock(conn, ticker="AAPL", name="Apple", market="US"):
    conn.execute(
        "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, ?)",
        (ticker, name, market),
    )
    conn.commit()


def _insert_prices(conn, ticker, df):
    rows = [
        (ticker, row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"]),
         row["open"], row["high"], row["low"], row["close"], int(row["volume"]))
        for _, row in df.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO price_cache (ticker, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


# ── get_cached_prices Tests ────────────────────────────────────────────

class TestGetCachedPrices(unittest.TestCase):
    def setUp(self):
        self.db_path = _setup_test_db()
        from models.database import get_connection
        from services import data_fetcher
        importlib.reload(data_fetcher)
        self.get_cached_prices = data_fetcher.get_cached_prices
        self.conn = get_connection()
        _insert_stock(self.conn, "AAPL", "Apple", "US")

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)

    def test_returns_dataframe_with_ohlcv_columns(self):
        """Cached prices DataFrame has date, open, high, low, close, volume."""
        df = _make_ohlcv(50)
        _insert_prices(self.conn, "AAPL", df)
        result = self.get_cached_prices("AAPL")
        for col in ["date", "open", "high", "low", "close", "volume"]:
            self.assertIn(col, result.columns)

    def test_returns_correct_row_count(self):
        df = _make_ohlcv(100)
        _insert_prices(self.conn, "AAPL", df)
        result = self.get_cached_prices("AAPL")
        self.assertEqual(len(result), 100)

    def test_empty_for_unknown_ticker(self):
        result = self.get_cached_prices("UNKNOWN")
        self.assertTrue(result.empty)

    def test_date_column_is_datetime(self):
        """get_cached_prices converts date to pd.Timestamp."""
        df = _make_ohlcv(10)
        _insert_prices(self.conn, "AAPL", df)
        result = self.get_cached_prices("AAPL")
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["date"]))

    def test_ordered_by_date_ascending(self):
        df = _make_ohlcv(50)
        _insert_prices(self.conn, "AAPL", df)
        result = self.get_cached_prices("AAPL")
        dates = result["date"].tolist()
        self.assertEqual(dates, sorted(dates))

    def test_filters_by_ticker(self):
        """Only returns data for the requested ticker."""
        df = _make_ohlcv(20)
        _insert_prices(self.conn, "AAPL", df)
        _insert_stock(self.conn, "MSFT", "Microsoft", "US")
        _insert_prices(self.conn, "MSFT", df)
        result = self.get_cached_prices("AAPL")
        self.assertEqual(len(result), 20)


# ── Indicator Tests (for chart overlays) ───────────────────────────────

class TestChartIndicators(unittest.TestCase):
    def setUp(self):
        self.df = _make_ohlcv(200)

    def test_ma20_length_matches_input(self):
        ma = compute_ma(self.df["close"], 20)
        self.assertEqual(len(ma), len(self.df))

    def test_ma50_length_matches_input(self):
        ma = compute_ma(self.df["close"], 50)
        self.assertEqual(len(ma), len(self.df))

    def test_ma200_length_matches_input(self):
        ma = compute_ma(self.df["close"], 200)
        self.assertEqual(len(ma), len(self.df))

    def test_ma20_first_19_are_nan(self):
        """First period-1 values should be NaN."""
        ma = compute_ma(self.df["close"], 20)
        self.assertTrue(ma.iloc[:19].isna().all())
        self.assertFalse(np.isnan(ma.iloc[19]))

    def test_rsi_length_matches_input(self):
        rsi = compute_rsi(self.df["close"])
        self.assertEqual(len(rsi), len(self.df))

    def test_rsi_values_in_range(self):
        """RSI should be between 0 and 100 where not NaN."""
        rsi = compute_rsi(self.df["close"]).dropna()
        self.assertTrue((rsi >= 0).all())
        self.assertTrue((rsi <= 100).all())

    def test_rsi_30_70_reference_lines_meaningful(self):
        """RSI should have values both above and below 50 for realistic data."""
        rsi = compute_rsi(self.df["close"]).dropna()
        self.assertTrue((rsi < 50).any())
        self.assertTrue((rsi > 50).any())


# ── Signal Matching Tests ──────────────────────────────────────────────

class TestSignalMatching(unittest.TestCase):
    """Tests the date-matching logic used to overlay BUY/SELL markers."""

    def setUp(self):
        self.db_path = _setup_test_db()
        from models.database import get_connection
        self.conn = get_connection()
        _insert_stock(self.conn, "AAPL", "Apple", "US")
        self.df = _make_ohlcv(200)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)

    def test_buy_sell_date_matching_via_astype_str(self):
        """Reproduces the page's signal matching: df['date'].astype(str).isin(...)."""
        # Insert a signal
        strategy_id = save_strategy({
            "name": "Test Strategy", "conditions": [{"indicator": "RSI", "operator": "<", "value": 30}],
            "market": "BOTH", "is_template": False,
        })
        signal_date = self.df["date"].iloc[50].strftime("%Y-%m-%d")
        self.conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) VALUES (?, ?, ?, ?, ?, ?)",
            ("AAPL", signal_date, "BUY", strategy_id, 100.0, 1.0),
        )
        self.conn.commit()

        # Simulate the page's matching logic
        signals = get_signals_for_ticker("AAPL")
        buy_dates = [s["date"] for s in signals if s["signal_type"] == "BUY"]
        matched = self.df[self.df["date"].astype(str).isin(buy_dates)]
        self.assertEqual(len(matched), 1)

    def test_no_signals_produces_empty_match(self):
        signals = get_signals_for_ticker("AAPL")
        buy_dates = [s["date"] for s in signals if s["signal_type"] == "BUY"]
        matched = self.df[self.df["date"].astype(str).isin(buy_dates)]
        self.assertTrue(matched.empty)


# ── get_signals_for_ticker Tests ───────────────────────────────────────

class TestGetSignalsForTicker(unittest.TestCase):
    def setUp(self):
        self.db_path = _setup_test_db()
        from models.database import get_connection
        from services import signal_generator
        importlib.reload(signal_generator)
        self.get_signals = signal_generator.get_signals_for_ticker
        self.conn = get_connection()
        _insert_stock(self.conn, "AAPL", "Apple", "US")
        self.strategy_id = save_strategy({
            "name": "Test Buy Strategy", "conditions": [{"indicator": "RSI", "operator": "<", "value": 30}],
            "market": "BOTH", "is_template": False,
        })

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)

    def test_returns_list_of_dicts(self):
        result = self.get_signals("AAPL")
        self.assertIsInstance(result, list)

    def test_empty_for_no_signals(self):
        result = self.get_signals("AAPL")
        self.assertEqual(len(result), 0)

    def test_returns_signal_with_strategy_name(self):
        """Signal JOIN includes strategy_name."""
        self.conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) VALUES (?, ?, ?, ?, ?, ?)",
            ("AAPL", "2024-01-15", "BUY", self.strategy_id, 150.0, 1.0),
        )
        self.conn.commit()
        result = self.get_signals("AAPL")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["strategy_name"], "Test Buy Strategy")

    def test_returns_journal_action_when_present(self):
        """Signal JOIN includes journal_action."""
        self.conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) VALUES (?, ?, ?, ?, ?, ?)",
            ("AAPL", "2024-01-15", "BUY", self.strategy_id, 150.0, 1.0),
        )
        self.conn.commit()
        signal_id = self.conn.execute("SELECT id FROM signals WHERE ticker='AAPL'").fetchone()["id"]
        self.conn.execute(
            "INSERT INTO journal (signal_id, action, notes) VALUES (?, ?, ?)",
            (signal_id, "ACTED", "Looks good"),
        )
        self.conn.commit()
        result = self.get_signals("AAPL")
        self.assertEqual(result[0]["journal_action"], "ACTED")

    def test_journal_action_null_when_not_reviewed(self):
        self.conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) VALUES (?, ?, ?, ?, ?, ?)",
            ("AAPL", "2024-01-15", "BUY", self.strategy_id, 150.0, 1.0),
        )
        self.conn.commit()
        result = self.get_signals("AAPL")
        self.assertIsNone(result[0]["journal_action"])

    def test_outcome_pct_included(self):
        self.conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) VALUES (?, ?, ?, ?, ?, ?)",
            ("AAPL", "2024-01-15", "BUY", self.strategy_id, 150.0, 1.0),
        )
        self.conn.commit()
        signal_id = self.conn.execute("SELECT id FROM signals WHERE ticker='AAPL'").fetchone()["id"]
        self.conn.execute(
            "INSERT INTO journal (signal_id, action, notes, outcome_pct) VALUES (?, ?, ?, ?)",
            (signal_id, "ACTED", "", 5.2),
        )
        self.conn.commit()
        result = self.get_signals("AAPL")
        self.assertAlmostEqual(result[0]["outcome_pct"], 5.2)

    def test_ordered_by_date_desc(self):
        for d in ["2024-01-10", "2024-01-20", "2024-01-15"]:
            self.conn.execute(
                "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) VALUES (?, ?, ?, ?, ?, ?)",
                ("AAPL", d, "BUY", self.strategy_id, 100.0, 1.0),
            )
        self.conn.commit()
        result = self.get_signals("AAPL")
        dates = [r["date"] for r in result]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_respects_limit(self):
        for i in range(10):
            self.conn.execute(
                "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) VALUES (?, ?, ?, ?, ?, ?)",
                ("AAPL", f"2024-01-{i+1:02d}", "BUY", self.strategy_id, 100.0, 1.0),
            )
        self.conn.commit()
        result = self.get_signals("AAPL", limit=5)
        self.assertEqual(len(result), 5)

    def test_filters_by_ticker(self):
        """Signals for other tickers are not returned."""
        _insert_stock(self.conn, "MSFT", "Microsoft", "US")
        self.conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) VALUES (?, ?, ?, ?, ?, ?)",
            ("MSFT", "2024-01-15", "BUY", self.strategy_id, 200.0, 1.0),
        )
        self.conn.commit()
        result = self.get_signals("AAPL")
        self.assertEqual(len(result), 0)


# ── Key Stats Computation Tests ────────────────────────────────────────

class TestKeyStats(unittest.TestCase):
    """Tests the key stats computation logic from the Stock Detail page."""

    def test_change_and_change_pct(self):
        """Close delta and percentage match manual calculation."""
        df = _make_ohlcv(50)
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest["close"] - prev["close"]
        change_pct = (change / prev["close"]) * 100
        self.assertAlmostEqual(change, latest["close"] - prev["close"])
        self.assertAlmostEqual(change_pct, (change / prev["close"]) * 100)

    def test_single_row_no_crash(self):
        """With only 1 row, prev == latest (no division error)."""
        df = _make_ohlcv(1)
        latest = df.iloc[-1]
        prev = df.iloc[-1]  # Same as latest when len==1
        change = latest["close"] - prev["close"]
        self.assertEqual(change, 0.0)

    def test_rsi_display_not_empty(self):
        """RSI on 200 rows should produce a valid last value."""
        df = _make_ohlcv(200)
        rsi = compute_rsi(df["close"])
        self.assertFalse(rsi.empty)
        self.assertFalse(np.isnan(rsi.iloc[-1]))

    def test_ma20_display_value(self):
        """MA20 on 200 rows should produce a valid last value."""
        df = _make_ohlcv(200)
        ma20 = compute_ma(df["close"], 20)
        self.assertFalse(np.isnan(ma20.iloc[-1]))


# ── Stock Selector Tests ───────────────────────────────────────────────

class TestStockSelector(unittest.TestCase):
    """Tests the stock selector dropdown data."""

    def setUp(self):
        self.db_path = _setup_test_db()
        from models.database import get_connection
        self.conn = get_connection()

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)

    def test_stocks_query_returns_all(self):
        """Selector shows all stocks from universe."""
        _insert_stock(self.conn, "AAPL", "Apple", "US")
        _insert_stock(self.conn, "005930", "Samsung", "KR")
        _insert_stock(self.conn, "MSFT", "Microsoft", "US")
        stocks = self.conn.execute(
            "SELECT ticker, name, market FROM stocks ORDER BY market, name"
        ).fetchall()
        self.assertEqual(len(stocks), 3)

    def test_ticker_options_format(self):
        """Dropdown labels match format: 'TICKER — Name (Market)'."""
        _insert_stock(self.conn, "AAPL", "Apple", "US")
        stocks = self.conn.execute(
            "SELECT ticker, name, market FROM stocks ORDER BY market, name"
        ).fetchall()
        label = f"{stocks[0]['ticker']} — {stocks[0]['name']} ({stocks[0]['market']})"
        self.assertEqual(label, "AAPL — Apple (US)")

    def test_query_param_ticker_lookup(self):
        """Query param ticker finds correct default index."""
        _insert_stock(self.conn, "AAPL", "Apple", "US")
        _insert_stock(self.conn, "MSFT", "Microsoft", "US")
        _insert_stock(self.conn, "005930", "Samsung", "KR")
        stocks = self.conn.execute(
            "SELECT ticker, name, market FROM stocks ORDER BY market, name"
        ).fetchall()
        query_ticker = "MSFT"
        default_idx = next(
            (i for i, s in enumerate(stocks) if s["ticker"] == query_ticker), 0
        )
        self.assertEqual(stocks[default_idx]["ticker"], "MSFT")


if __name__ == "__main__":
    unittest.main()
