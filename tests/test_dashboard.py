import unittest
import tempfile
import os
import json

import pandas as pd
import numpy as np


class TestDashboard(unittest.TestCase):
    """Verify dashboard DB queries and market context logic."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.environ["DB_PATH"] = self.db_path
        import config.settings as settings
        settings.DB_PATH = self.db_path
        import importlib
        import models.database as db
        importlib.reload(db)
        self.db = db
        self.db.init_db()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # ── Health status ──────────────────────────────────────────────

    def test_health_no_cron_data(self):
        """Health dot is yellow when no system_status rows exist."""
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT status, message, timestamp FROM system_status ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        self.assertIsNone(row)

    def test_health_ok_status(self):
        """Health dot is green when last cron was OK."""
        conn = self.db.get_connection()
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("daily_signals", "OK", "Completed"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT status, message, timestamp FROM system_status ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        self.assertEqual(row["status"], "OK")

    def test_health_error_status(self):
        """Health dot is red when last cron had an error."""
        conn = self.db.get_connection()
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES (?, ?, ?)",
            ("data_refresh", "ERROR", "Network timeout"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT status, message, timestamp FROM system_status ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        self.assertEqual(row["status"], "ERROR")
        self.assertIn("timeout", row["message"].lower())

    def test_health_latest_row_wins(self):
        """Health status returns the most recent entry (by id, matching dashboard logic)."""
        conn = self.db.get_connection()
        conn.execute(
            "INSERT INTO system_status (job_name, status, message, timestamp) VALUES (?, ?, ?, ?)",
            ("daily_signals", "ERROR", "fail", "2026-03-20 10:00:00"),
        )
        conn.execute(
            "INSERT INTO system_status (job_name, status, message, timestamp) VALUES (?, ?, ?, ?)",
            ("daily_signals", "OK", "recovered", "2026-03-20 10:01:00"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT status FROM system_status ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        self.assertEqual(row["status"], "OK")

    # ── Market context (_make_context_entry) ───────────────────────

    def test_make_context_entry_valid(self):
        """_make_context_entry returns valid dict with no NaN."""
        from services.data_fetcher import _make_context_entry

        df = pd.DataFrame({"Close": [100.0, 101.5, 103.0]})
        entry = _make_context_entry(df)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["value"], 103.0)
        self.assertFalse(np.isnan(entry["value"]))
        self.assertFalse(np.isnan(entry["change"]))
        self.assertFalse(np.isnan(entry["change_pct"]))

    def test_make_context_entry_single_row(self):
        """Single data point gives zero change."""
        from services.data_fetcher import _make_context_entry

        df = pd.DataFrame({"Close": [500.0]})
        entry = _make_context_entry(df)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["change"], 0.0)
        self.assertEqual(entry["change_pct"], 0.0)

    def test_make_context_entry_with_nan_rows(self):
        """NaN rows are dropped before computing entry."""
        from services.data_fetcher import _make_context_entry

        df = pd.DataFrame({"Close": [float("nan"), 200.0, float("nan"), 205.0]})
        entry = _make_context_entry(df)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["value"], 205.0)
        self.assertFalse(np.isnan(entry["change"]))

    def test_make_context_entry_all_nan(self):
        """All-NaN returns None."""
        from services.data_fetcher import _make_context_entry

        df = pd.DataFrame({"Close": [float("nan"), float("nan")]})
        entry = _make_context_entry(df)
        self.assertIsNone(entry)

    def test_make_context_entry_empty(self):
        """Empty series returns None."""
        from services.data_fetcher import _make_context_entry

        df = pd.DataFrame({"Close": pd.Series([], dtype=float)})
        entry = _make_context_entry(df)
        self.assertIsNone(entry)

    # ── Today's signals query ──────────────────────────────────────

    def test_get_todays_signals_empty(self):
        """No signals returns empty list."""
        from services.signal_generator import get_todays_signals

        signals = get_todays_signals()
        self.assertEqual(signals, [])

    def test_get_todays_signals_returns_today(self):
        """Signals for today are returned with strategy name."""
        from services.strategy_engine import save_strategy
        from services.signal_generator import get_todays_signals
        from datetime import datetime

        strategy_id = save_strategy({
            "name": "Test Strategy",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 30}],
            "market": "BOTH",
            "is_template": False,
        })

        today = datetime.now().strftime("%Y-%m-%d")
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("AAPL", today, "BUY", strategy_id, 150.0, 1.0),
        )
        conn.commit()
        conn.close()

        signals = get_todays_signals()
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["ticker"], "AAPL")
        self.assertEqual(signals[0]["signal_type"], "BUY")
        self.assertEqual(signals[0]["strategy_name"], "Test Strategy")
        self.assertIsNone(signals[0]["journal_action"])

    def test_get_todays_signals_excludes_past(self):
        """Signals from yesterday are not included."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('MSFT', 'Microsoft', 'US')")
        conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) "
            "VALUES ('MSFT', '2020-01-01', 'SELL', NULL, 200.0, 0.8)",
        )
        conn.commit()
        conn.close()

        from services.signal_generator import get_todays_signals

        signals = get_todays_signals()
        self.assertEqual(len(signals), 0)

    # ── Pending review (unreviewed signals) ────────────────────────

    def test_unreviewed_signals_empty(self):
        """No signals means no pending reviews."""
        from services.journal_manager import get_unreviewed_signals

        self.assertEqual(get_unreviewed_signals(), [])

    def test_unreviewed_signals_excludes_reviewed(self):
        """Signals with journal entries are excluded."""
        from services.journal_manager import get_unreviewed_signals, record_action

        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, price, strength) "
            "VALUES ('AAPL', '2026-03-19', 'BUY', 150.0, 1.0)",
        )
        conn.commit()
        sig_id = conn.execute("SELECT id FROM signals LIMIT 1").fetchone()["id"]
        conn.close()

        # Before review
        self.assertEqual(len(get_unreviewed_signals()), 1)

        # After review
        record_action(sig_id, "ACTED")
        self.assertEqual(len(get_unreviewed_signals()), 0)

    # ── Journal record_action ──────────────────────────────────────

    def test_record_action_acted(self):
        """record_action saves ACTED to journal."""
        from services.journal_manager import record_action

        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, price, strength) "
            "VALUES ('AAPL', '2026-03-19', 'BUY', 150.0, 1.0)",
        )
        conn.commit()
        sig_id = conn.execute("SELECT id FROM signals LIMIT 1").fetchone()["id"]
        conn.close()

        record_action(sig_id, "ACTED")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM journal WHERE signal_id = ?", (sig_id,)).fetchone()
        conn.close()
        self.assertEqual(row["action"], "ACTED")

    def test_record_action_upsert(self):
        """Recording action twice replaces previous entry."""
        from services.journal_manager import record_action

        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, price, strength) "
            "VALUES ('AAPL', '2026-03-19', 'BUY', 150.0, 1.0)",
        )
        conn.commit()
        sig_id = conn.execute("SELECT id FROM signals LIMIT 1").fetchone()["id"]
        conn.close()

        record_action(sig_id, "ACTED")
        record_action(sig_id, "SKIPPED")

        conn = self.db.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM journal WHERE signal_id = ?", (sig_id,)).fetchone()[0]
        row = conn.execute("SELECT action FROM journal WHERE signal_id = ?", (sig_id,)).fetchone()
        conn.close()
        self.assertEqual(count, 1)
        self.assertEqual(row["action"], "SKIPPED")

    # ── Signal shows journal_action in today's query ───────────────

    def test_todays_signals_show_journal_action(self):
        """After recording action, today's signals show journal_action."""
        from services.signal_generator import get_todays_signals
        from services.journal_manager import record_action
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('NVDA', 'NVIDIA', 'US')")
        conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, price, strength) "
            "VALUES ('NVDA', ?, 'BUY', 800.0, 1.0)",
            (today,),
        )
        conn.commit()
        sig_id = conn.execute("SELECT id FROM signals LIMIT 1").fetchone()["id"]
        conn.close()

        record_action(sig_id, "ACTED")
        signals = get_todays_signals()
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["journal_action"], "ACTED")


if __name__ == "__main__":
    unittest.main()
