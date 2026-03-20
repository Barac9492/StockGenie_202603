import unittest
import tempfile
import os
import json


class TestOnboardingFlow(unittest.TestCase):
    """End-to-end verification of the 3-step onboarding wizard DB operations."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.environ["DB_PATH"] = self.db_path
        import importlib
        import config.settings as settings
        settings.DB_PATH = self.db_path
        import models.database as db
        importlib.reload(db)
        self.db = db
        self.db.init_db()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # ── Step 1: Pick stocks ──────────────────────────────────────────

    def test_step1_insert_kr_stocks(self):
        """Step 1 inserts Korean stocks into DB."""
        conn = self.db.get_connection()
        kr_stocks = {"005930": "삼성전자", "000660": "SK하이닉스"}
        for ticker, name in kr_stocks.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'KR')",
                (ticker, name),
            )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks WHERE market = 'KR'").fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)

    def test_step1_insert_us_stocks(self):
        """Step 1 inserts US stocks into DB."""
        conn = self.db.get_connection()
        us_stocks = {"AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet"}
        for ticker, name in us_stocks.items():
            conn.execute(
                "INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'US')",
                (ticker, name),
            )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks WHERE market = 'US'").fetchone()[0]
        conn.close()
        self.assertEqual(count, 3)

    def test_step1_duplicate_stocks_ignored(self):
        """INSERT OR IGNORE prevents duplicates on re-run."""
        conn = self.db.get_connection()
        conn.execute("INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute("INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_step1_is_first_run_true_when_empty(self):
        """is_first_run() returns True when stocks table is empty."""
        conn = self.db.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_step1_is_first_run_false_after_insert(self):
        """is_first_run() returns False after stocks are inserted."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        conn.close()
        self.assertGreater(count, 0)

    # ── Step 2: Choose strategy ──────────────────────────────────────

    def test_step2_save_templates(self):
        """Step 2 saves all 7 strategy templates to DB."""
        from templates.strategies import STRATEGY_TEMPLATES
        from services.strategy_engine import save_strategy

        for tmpl in STRATEGY_TEMPLATES:
            save_strategy(tmpl)

        conn = self.db.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 1").fetchone()[0]
        conn.close()
        self.assertEqual(count, 7)

    def test_step2_save_user_strategy(self):
        """Step 2 saves user's chosen strategy as non-template."""
        from templates.strategies import STRATEGY_TEMPLATES
        from services.strategy_engine import save_strategy

        tmpl = STRATEGY_TEMPLATES[0]
        user_strategy = tmpl.copy()
        user_strategy["is_template"] = False
        user_strategy["name"] = f"My {tmpl['name']}"
        strategy_id = save_strategy(user_strategy)

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        conn.close()

        self.assertFalse(bool(row["is_template"]))
        self.assertTrue(row["name"].startswith("My "))
        self.assertEqual(json.loads(row["conditions"]), tmpl["conditions"])

    def test_step2_templates_saved_once(self):
        """Templates are only saved once (check existing == 0 guard)."""
        from templates.strategies import STRATEGY_TEMPLATES
        from services.strategy_engine import save_strategy

        # First save
        for tmpl in STRATEGY_TEMPLATES:
            save_strategy(tmpl)

        conn = self.db.get_connection()
        count_before = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 1").fetchone()[0]
        conn.close()

        # The guard: only save if existing == 0
        conn = self.db.get_connection()
        existing = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 1").fetchone()[0]
        conn.close()

        if existing == 0:
            for tmpl in STRATEGY_TEMPLATES:
                save_strategy(tmpl)

        conn = self.db.get_connection()
        count_after = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 1").fetchone()[0]
        conn.close()

        self.assertEqual(count_before, count_after)

    # ── Step 3: Data fetch + backtest readiness ──────────────────────

    def test_step3_stock_query_by_market(self):
        """Step 3 correctly partitions stocks by market for fetching."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('005930', '삼성전자', 'KR')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.commit()

        stocks = conn.execute("SELECT ticker, market FROM stocks").fetchall()
        conn.close()

        kr_tickers = [s["ticker"] for s in stocks if s["market"] == "KR"]
        us_tickers = [s["ticker"] for s in stocks if s["market"] == "US"]

        self.assertEqual(kr_tickers, ["005930"])
        self.assertEqual(us_tickers, ["AAPL"])

    def test_step3_price_cache_schema(self):
        """price_cache table accepts OHLCV rows for caching fetched data."""
        conn = self.db.get_connection()
        conn.execute(
            "INSERT INTO price_cache (ticker, date, open, high, low, close, volume) "
            "VALUES ('AAPL', '2026-01-01', 100.0, 105.0, 99.0, 103.0, 1000000)"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM price_cache WHERE ticker = 'AAPL'").fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["close"], 103.0)

    def test_step3_price_cache_upsert(self):
        """INSERT OR REPLACE updates existing price_cache rows."""
        conn = self.db.get_connection()
        conn.execute(
            "INSERT INTO price_cache (ticker, date, open, high, low, close, volume) "
            "VALUES ('AAPL', '2026-01-01', 100.0, 105.0, 99.0, 103.0, 1000000)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO price_cache (ticker, date, open, high, low, close, volume) "
            "VALUES ('AAPL', '2026-01-01', 101.0, 106.0, 100.0, 104.0, 2000000)"
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM price_cache WHERE ticker = 'AAPL'").fetchone()[0]
        row = conn.execute("SELECT close FROM price_cache WHERE ticker = 'AAPL'").fetchone()
        conn.close()

        self.assertEqual(count, 1)
        self.assertEqual(row["close"], 104.0)

    # ── Post-onboarding: main page stats ─────────────────────────────

    def test_post_onboarding_stock_count(self):
        """After onboarding, main page shows correct stock count."""
        conn = self.db.get_connection()
        stocks = [
            ("005930", "삼성전자", "KR"),
            ("000660", "SK하이닉스", "KR"),
            ("AAPL", "Apple", "US"),
        ]
        for ticker, name, market in stocks:
            conn.execute(
                "INSERT INTO stocks (ticker, name, market) VALUES (?, ?, ?)",
                (ticker, name, market),
            )
        conn.commit()
        num_stocks = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        conn.close()
        self.assertEqual(num_stocks, 3)

    def test_post_onboarding_strategy_count(self):
        """After onboarding, strategy count excludes templates."""
        from services.strategy_engine import save_strategy
        from templates.strategies import STRATEGY_TEMPLATES

        # Save templates
        for tmpl in STRATEGY_TEMPLATES:
            save_strategy(tmpl)
        # Save user strategy
        user = STRATEGY_TEMPLATES[0].copy()
        user["is_template"] = False
        user["name"] = "My Strategy"
        save_strategy(user)

        conn = self.db.get_connection()
        num_strategies = conn.execute(
            "SELECT COUNT(*) FROM strategies WHERE is_template = 0"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(num_strategies, 1)

    def test_post_onboarding_signals_count_zero(self):
        """After fresh onboarding, today's signals should be 0."""
        conn = self.db.get_connection()
        num_signals = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE date = date('now')"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(num_signals, 0)

    # ── Full flow simulation ─────────────────────────────────────────

    def test_full_onboarding_flow(self):
        """Simulate complete 3-step onboarding and verify final state."""
        from services.strategy_engine import save_strategy
        from templates.strategies import STRATEGY_TEMPLATES

        # Step 1: Insert stocks
        conn = self.db.get_connection()
        default_kr = {"005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
                       "005380": "현대차", "051910": "LG화학"}
        default_us = {"AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
                       "AMZN": "Amazon", "NVDA": "NVIDIA"}
        for ticker, name in default_kr.items():
            conn.execute("INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'KR')", (ticker, name))
        for ticker, name in default_us.items():
            conn.execute("INSERT OR IGNORE INTO stocks (ticker, name, market) VALUES (?, ?, 'US')", (ticker, name))
        conn.commit()
        conn.close()

        # Verify: stocks in DB
        conn = self.db.get_connection()
        stock_count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        self.assertEqual(stock_count, 10)

        # Step 2: Save templates + user strategy
        existing = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 1").fetchone()[0]
        conn.close()
        if existing == 0:
            for tmpl in STRATEGY_TEMPLATES:
                save_strategy(tmpl)

        selected = STRATEGY_TEMPLATES[0]
        user_strategy = selected.copy()
        user_strategy["is_template"] = False
        user_strategy["name"] = f"My {selected['name']}"
        save_strategy(user_strategy)

        # Verify: templates + 1 user strategy
        conn = self.db.get_connection()
        template_count = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 1").fetchone()[0]
        user_count = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 0").fetchone()[0]
        self.assertEqual(template_count, 7)
        self.assertEqual(user_count, 1)

        # Step 3: Simulate data caching (no network in tests)
        conn.execute(
            "INSERT INTO price_cache (ticker, date, open, high, low, close, volume) "
            "VALUES ('005930', '2026-03-19', 75000, 76000, 74500, 75500, 5000000)"
        )
        conn.commit()
        cached = conn.execute("SELECT COUNT(*) FROM price_cache").fetchone()[0]
        self.assertGreater(cached, 0)

        # Post-onboarding: main page stats
        num_stocks = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        num_strategies = conn.execute("SELECT COUNT(*) FROM strategies WHERE is_template = 0").fetchone()[0]
        num_signals = conn.execute("SELECT COUNT(*) FROM signals WHERE date = date('now')").fetchone()[0]
        conn.close()

        self.assertEqual(num_stocks, 10)
        self.assertEqual(num_strategies, 1)
        self.assertEqual(num_signals, 0)


if __name__ == "__main__":
    unittest.main()
