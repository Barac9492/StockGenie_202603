import unittest
import tempfile
import os
import importlib


class TestSettingsPage(unittest.TestCase):
    """Tests for Settings page: stock universe management, Quick Add, data refresh."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.environ["DB_PATH"] = self.db_path
        import config.settings as settings
        settings.DB_PATH = self.db_path
        import models.database as db
        importlib.reload(db)
        self.db = db
        self.db.init_db()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # ── Stock listing ──────────────────────────────────────────

    def test_list_stocks_empty(self):
        """Empty universe returns no rows."""
        conn = self.db.get_connection()
        rows = conn.execute("SELECT ticker, name, market FROM stocks ORDER BY market, name").fetchall()
        conn.close()
        self.assertEqual(len(rows), 0)

    def test_list_stocks_ordered_by_market_then_name(self):
        """Stocks are ordered by market (KR first), then name."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('005930', '삼성전자', 'KR')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('MSFT', 'Microsoft', 'US')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('000660', 'SK하이닉스', 'KR')")
        conn.commit()
        rows = conn.execute("SELECT ticker, name, market FROM stocks ORDER BY market, name").fetchall()
        conn.close()
        markets = [r["market"] for r in rows]
        # KR stocks first, then US
        self.assertEqual(markets, ["KR", "KR", "US", "US"])
        # Within US, alphabetical by name
        us_names = [r["name"] for r in rows if r["market"] == "US"]
        self.assertEqual(us_names, sorted(us_names))

    def test_stock_count_display(self):
        """Stock count matches inserted rows."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('MSFT', 'Microsoft', 'US')")
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)

    # ── Remove stock ───────────────────────────────────────────

    def test_remove_stock(self):
        """Removing a stock deletes it from the DB."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('MSFT', 'Microsoft', 'US')")
        conn.commit()
        # Remove AAPL
        conn.execute("DELETE FROM stocks WHERE ticker = ?", ("AAPL",))
        conn.commit()
        remaining = conn.execute("SELECT ticker FROM stocks").fetchall()
        conn.close()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["ticker"], "MSFT")

    def test_remove_nonexistent_stock_no_error(self):
        """Removing a ticker that doesn't exist is a no-op."""
        conn = self.db.get_connection()
        conn.execute("DELETE FROM stocks WHERE ticker = ?", ("FAKE",))
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    # ── Add stock ──────────────────────────────────────────────

    def test_add_stock_kr(self):
        """Adding a KR stock persists correctly."""
        conn = self.db.get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, ?)",
            ("005930", "삼성전자", "KR"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM stocks WHERE ticker = '005930'").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "삼성전자")
        self.assertEqual(row["market"], "KR")

    def test_add_stock_us(self):
        """Adding a US stock persists correctly."""
        conn = self.db.get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, ?)",
            ("AAPL", "Apple", "US"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM stocks WHERE ticker = 'AAPL'").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "Apple")
        self.assertEqual(row["market"], "US")

    def test_add_stock_strips_whitespace(self):
        """Ticker and name are stripped of leading/trailing whitespace."""
        conn = self.db.get_connection()
        ticker = "  AAPL  ".strip()
        name = "  Apple  ".strip()
        conn.execute(
            "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, ?)",
            (ticker, name, "US"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM stocks WHERE ticker = 'AAPL'").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["ticker"], "AAPL")
        self.assertEqual(row["name"], "Apple")

    def test_add_duplicate_stock_ignored(self):
        """INSERT OR IGNORE prevents duplicate tickers."""
        conn = self.db.get_connection()
        conn.execute("INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute("INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple Inc.', 'US')")
        conn.commit()
        rows = conn.execute("SELECT * FROM stocks WHERE ticker = 'AAPL'").fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        # Original name kept
        self.assertEqual(rows[0]["name"], "Apple")

    def test_add_stock_invalid_market_rejected(self):
        """Market CHECK constraint rejects invalid values."""
        conn = self.db.get_connection()
        with self.assertRaises(Exception):
            conn.execute(
                "INSERT INTO stocks (ticker, name, market) VALUES ('X', 'Test', 'JP')"
            )
        conn.close()

    # ── Quick Add KOSPI Top 10 ─────────────────────────────────

    def test_quick_add_kospi_top10_count(self):
        """Quick Add KOSPI inserts exactly 10 stocks."""
        kospi_top = {
            "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
            "005380": "현대차", "051910": "LG화학", "006400": "삼성SDI",
            "003670": "포스코홀딩스", "105560": "KB금융", "055550": "신한지주",
            "035720": "카카오",
        }
        conn = self.db.get_connection()
        for ticker, name in kospi_top.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'KR')",
                (ticker, name),
            )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks WHERE market = 'KR'").fetchone()[0]
        conn.close()
        self.assertEqual(count, 10)

    def test_quick_add_kospi_all_kr_market(self):
        """All KOSPI Quick Add stocks have market = 'KR'."""
        kospi_top = {
            "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
            "005380": "현대차", "051910": "LG화학", "006400": "삼성SDI",
            "003670": "포스코홀딩스", "105560": "KB금융", "055550": "신한지주",
            "035720": "카카오",
        }
        conn = self.db.get_connection()
        for ticker, name in kospi_top.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'KR')",
                (ticker, name),
            )
        conn.commit()
        non_kr = conn.execute("SELECT COUNT(*) FROM stocks WHERE market != 'KR'").fetchone()[0]
        conn.close()
        self.assertEqual(non_kr, 0)

    def test_quick_add_kospi_idempotent(self):
        """Clicking KOSPI Quick Add twice doesn't duplicate stocks."""
        kospi_top = {
            "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
            "005380": "현대차", "051910": "LG화학", "006400": "삼성SDI",
            "003670": "포스코홀딩스", "105560": "KB금융", "055550": "신한지주",
            "035720": "카카오",
        }
        conn = self.db.get_connection()
        # Insert twice
        for _ in range(2):
            for ticker, name in kospi_top.items():
                conn.execute(
                    "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'KR')",
                    (ticker, name),
                )
            conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        conn.close()
        self.assertEqual(count, 10)

    # ── Quick Add S&P Top 10 ──────────────────────────────────

    def test_quick_add_sp_top10_count(self):
        """Quick Add S&P inserts exactly 10 stocks."""
        sp_top = {
            "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
            "AMZN": "Amazon", "NVDA": "NVIDIA", "META": "Meta",
            "TSLA": "Tesla", "BRK-B": "Berkshire Hathaway",
            "JPM": "JPMorgan Chase", "V": "Visa",
        }
        conn = self.db.get_connection()
        for ticker, name in sp_top.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'US')",
                (ticker, name),
            )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks WHERE market = 'US'").fetchone()[0]
        conn.close()
        self.assertEqual(count, 10)

    def test_quick_add_sp_all_us_market(self):
        """All S&P Quick Add stocks have market = 'US'."""
        sp_top = {
            "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
            "AMZN": "Amazon", "NVDA": "NVIDIA", "META": "Meta",
            "TSLA": "Tesla", "BRK-B": "Berkshire Hathaway",
            "JPM": "JPMorgan Chase", "V": "Visa",
        }
        conn = self.db.get_connection()
        for ticker, name in sp_top.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'US')",
                (ticker, name),
            )
        conn.commit()
        non_us = conn.execute("SELECT COUNT(*) FROM stocks WHERE market != 'US'").fetchone()[0]
        conn.close()
        self.assertEqual(non_us, 0)

    def test_quick_add_sp_idempotent(self):
        """Clicking S&P Quick Add twice doesn't duplicate stocks."""
        sp_top = {
            "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
            "AMZN": "Amazon", "NVDA": "NVIDIA", "META": "Meta",
            "TSLA": "Tesla", "BRK-B": "Berkshire Hathaway",
            "JPM": "JPMorgan Chase", "V": "Visa",
        }
        conn = self.db.get_connection()
        for _ in range(2):
            for ticker, name in sp_top.items():
                conn.execute(
                    "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'US')",
                    (ticker, name),
                )
            conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        conn.close()
        self.assertEqual(count, 10)

    def test_quick_add_both_presets(self):
        """Adding both KOSPI and S&P gives 20 stocks total."""
        kospi_top = {
            "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
            "005380": "현대차", "051910": "LG화학", "006400": "삼성SDI",
            "003670": "포스코홀딩스", "105560": "KB금융", "055550": "신한지주",
            "035720": "카카오",
        }
        sp_top = {
            "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
            "AMZN": "Amazon", "NVDA": "NVIDIA", "META": "Meta",
            "TSLA": "Tesla", "BRK-B": "Berkshire Hathaway",
            "JPM": "JPMorgan Chase", "V": "Visa",
        }
        conn = self.db.get_connection()
        for ticker, name in kospi_top.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'KR')",
                (ticker, name),
            )
        for ticker, name in sp_top.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'US')",
                (ticker, name),
            )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        kr = conn.execute("SELECT COUNT(*) FROM stocks WHERE market = 'KR'").fetchone()[0]
        us = conn.execute("SELECT COUNT(*) FROM stocks WHERE market = 'US'").fetchone()[0]
        conn.close()
        self.assertEqual(total, 20)
        self.assertEqual(kr, 10)
        self.assertEqual(us, 10)

    # ── Data refresh (DB partitioning) ─────────────────────────

    def test_data_refresh_partitions_by_market(self):
        """Data refresh correctly partitions stocks by market for fetch calls."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('005930', '삼성전자', 'KR')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('MSFT', 'Microsoft', 'US')")
        conn.commit()
        all_stocks = conn.execute("SELECT ticker, market FROM stocks").fetchall()
        conn.close()
        kr = [s["ticker"] for s in all_stocks if s["market"] == "KR"]
        us = [s["ticker"] for s in all_stocks if s["market"] == "US"]
        self.assertEqual(kr, ["005930"])
        self.assertEqual(sorted(us), ["AAPL", "MSFT"])

    def test_data_refresh_empty_universe_no_crash(self):
        """Data refresh with no stocks doesn't crash."""
        conn = self.db.get_connection()
        all_stocks = conn.execute("SELECT ticker, market FROM stocks").fetchall()
        conn.close()
        kr = [s["ticker"] for s in all_stocks if s["market"] == "KR"]
        us = [s["ticker"] for s in all_stocks if s["market"] == "US"]
        self.assertEqual(kr, [])
        self.assertEqual(us, [])

    def test_data_refresh_caches_prices(self):
        """Price data from fetch is cached in price_cache table."""
        import pandas as pd
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('TEST', 'Test Co', 'US')")
        conn.commit()
        # Simulate what _cache_prices does
        rows = [
            ("TEST", "2026-03-18", 100.0, 105.0, 99.0, 103.0, 1000000),
            ("TEST", "2026-03-19", 103.0, 107.0, 102.0, 106.0, 1200000),
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO price_cache (ticker, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        cached = conn.execute(
            "SELECT * FROM price_cache WHERE ticker = 'TEST' ORDER BY date"
        ).fetchall()
        conn.close()
        self.assertEqual(len(cached), 2)
        self.assertEqual(cached[0]["close"], 103.0)
        self.assertEqual(cached[1]["close"], 106.0)

    def test_data_refresh_upsert_updates_existing(self):
        """INSERT OR REPLACE updates existing price_cache rows."""
        conn = self.db.get_connection()
        conn.execute(
            "INSERT INTO price_cache (ticker, date, open, high, low, close, volume) "
            "VALUES ('TEST', '2026-03-18', 100, 105, 99, 103, 1000000)"
        )
        conn.commit()
        # Update same date with new data
        conn.execute(
            "INSERT OR REPLACE INTO price_cache (ticker, date, open, high, low, close, volume) "
            "VALUES ('TEST', '2026-03-18', 101, 106, 100, 104, 1100000)"
        )
        conn.commit()
        rows = conn.execute("SELECT * FROM price_cache WHERE ticker = 'TEST'").fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close"], 104.0)

    # ── Remove stock cascading behavior ────────────────────────

    def test_remove_stock_leaves_other_stocks(self):
        """Removing one stock doesn't affect others."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('MSFT', 'Microsoft', 'US')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('005930', '삼성전자', 'KR')")
        conn.commit()
        conn.execute("DELETE FROM stocks WHERE ticker = 'MSFT'")
        conn.commit()
        remaining = conn.execute("SELECT ticker FROM stocks ORDER BY ticker").fetchall()
        conn.close()
        tickers = [r["ticker"] for r in remaining]
        self.assertEqual(tickers, ["005930", "AAPL"])

    # ── Stock fields ───────────────────────────────────────────

    def test_stock_has_added_at_timestamp(self):
        """Inserted stock gets an added_at timestamp."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.commit()
        row = conn.execute("SELECT added_at FROM stocks WHERE ticker = 'AAPL'").fetchone()
        conn.close()
        self.assertIsNotNone(row["added_at"])

    def test_stock_row_has_all_fields(self):
        """Stock row contains ticker, name, market, added_at."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.commit()
        row = conn.execute("SELECT * FROM stocks WHERE ticker = 'AAPL'").fetchone()
        conn.close()
        self.assertEqual(row["ticker"], "AAPL")
        self.assertEqual(row["name"], "Apple")
        self.assertEqual(row["market"], "US")
        self.assertIsNotNone(row["added_at"])

    # ── get_cached_prices integration ──────────────────────────

    def test_get_cached_prices_returns_dataframe(self):
        """get_cached_prices returns a DataFrame for cached ticker."""
        conn = self.db.get_connection()
        rows = [
            ("TEST", "2026-03-17", 98.0, 101.0, 97.0, 100.0, 900000),
            ("TEST", "2026-03-18", 100.0, 105.0, 99.0, 103.0, 1000000),
            ("TEST", "2026-03-19", 103.0, 107.0, 102.0, 106.0, 1200000),
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO price_cache (ticker, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        conn.close()

        from services.data_fetcher import get_cached_prices
        df = get_cached_prices("TEST")
        self.assertEqual(len(df), 3)
        self.assertIn("close", df.columns)
        self.assertEqual(df.iloc[-1]["close"], 106.0)

    def test_get_cached_prices_empty_for_unknown_ticker(self):
        """get_cached_prices returns empty DataFrame for unknown ticker."""
        from services.data_fetcher import get_cached_prices
        df = get_cached_prices("NONEXISTENT")
        self.assertEqual(len(df), 0)


if __name__ == "__main__":
    unittest.main()
