import unittest
import tempfile
import os
import importlib
from unittest.mock import patch, MagicMock


class TestCronScripts(unittest.TestCase):
    """Tests for cron scripts: daily_signals, daily_digest, data_refresh."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.environ["DB_PATH"] = self.db_path
        import config.settings as settings
        settings.DB_PATH = self.db_path
        import models.database as db
        importlib.reload(db)
        self.db = db
        self.db.init_db()

        # Force reimport of script modules so they pick up the test DB
        import scripts.daily_signals as ds
        importlib.reload(ds)
        self.daily_signals = ds

        import scripts.daily_digest as dd
        importlib.reload(dd)
        self.daily_digest = dd

        import scripts.data_refresh as dr
        importlib.reload(dr)
        self.data_refresh = dr

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def _get_status_rows(self, job_name=None):
        conn = self.db.get_connection()
        if job_name:
            rows = conn.execute(
                "SELECT * FROM system_status WHERE job_name = ? ORDER BY id",
                (job_name,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM system_status ORDER BY id"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _insert_stocks(self):
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('005930', '삼성전자', 'KR')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('AAPL', 'Apple', 'US')")
        conn.commit()
        conn.close()

    # ── daily_signals ────────────────────────────────────────────

    @patch("scripts.daily_signals.generate_signals")
    @patch("scripts.daily_signals.fetch_us_stocks")
    @patch("scripts.daily_signals.fetch_kr_stocks")
    def test_daily_signals_logs_running_then_ok(self, mock_kr, mock_us, mock_gen):
        """daily_signals logs RUNNING then OK to system_status."""
        mock_kr.return_value = {}
        mock_us.return_value = {}
        mock_gen.return_value = [{"ticker": "AAPL", "type": "BUY"}]
        self._insert_stocks()

        self.daily_signals.main()

        rows = self._get_status_rows("daily_signals")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "RUNNING")
        self.assertEqual(rows[1]["status"], "OK")
        self.assertIn("1 signals", rows[1]["message"])

    @patch("scripts.daily_signals.generate_signals")
    @patch("scripts.daily_signals.fetch_us_stocks")
    @patch("scripts.daily_signals.fetch_kr_stocks")
    def test_daily_signals_empty_universe(self, mock_kr, mock_us, mock_gen):
        """daily_signals works with no stocks in universe."""
        mock_gen.return_value = []

        self.daily_signals.main()

        rows = self._get_status_rows("daily_signals")
        self.assertEqual(rows[-1]["status"], "OK")
        self.assertIn("0 signals", rows[-1]["message"])
        mock_kr.assert_not_called()
        mock_us.assert_not_called()

    @patch("scripts.daily_signals.generate_signals")
    @patch("scripts.daily_signals.fetch_us_stocks")
    @patch("scripts.daily_signals.fetch_kr_stocks")
    def test_daily_signals_partitions_by_market(self, mock_kr, mock_us, mock_gen):
        """daily_signals calls fetch_kr_stocks and fetch_us_stocks with correct tickers."""
        mock_kr.return_value = {}
        mock_us.return_value = {}
        mock_gen.return_value = []
        self._insert_stocks()

        self.daily_signals.main()

        mock_kr.assert_called_once_with(["005930"])
        mock_us.assert_called_once_with(["AAPL"])

    @patch("scripts.daily_signals.generate_signals", side_effect=RuntimeError("signal error"))
    @patch("scripts.daily_signals.fetch_us_stocks")
    @patch("scripts.daily_signals.fetch_kr_stocks")
    def test_daily_signals_error_logged(self, mock_kr, mock_us, mock_gen):
        """daily_signals logs ERROR on exception."""
        mock_kr.return_value = {}
        mock_us.return_value = {}
        self._insert_stocks()

        self.daily_signals.main()

        rows = self._get_status_rows("daily_signals")
        error_row = [r for r in rows if r["status"] == "ERROR"]
        self.assertEqual(len(error_row), 1)
        self.assertIn("signal error", error_row[0]["message"])

    @patch("scripts.daily_signals.generate_signals")
    @patch("scripts.daily_signals.fetch_us_stocks")
    @patch("scripts.daily_signals.fetch_kr_stocks")
    def test_daily_signals_kr_only(self, mock_kr, mock_us, mock_gen):
        """daily_signals skips US fetch when only KR stocks exist."""
        mock_kr.return_value = {}
        mock_gen.return_value = []
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('005930', '삼성전자', 'KR')")
        conn.commit()
        conn.close()

        self.daily_signals.main()

        mock_kr.assert_called_once()
        mock_us.assert_not_called()

    @patch("scripts.daily_signals.generate_signals")
    @patch("scripts.daily_signals.fetch_us_stocks")
    @patch("scripts.daily_signals.fetch_kr_stocks")
    def test_daily_signals_signal_count_in_message(self, mock_kr, mock_us, mock_gen):
        """daily_signals OK message contains the signal count."""
        mock_gen.return_value = [
            {"ticker": "A", "type": "BUY"},
            {"ticker": "B", "type": "BUY"},
            {"ticker": "C", "type": "SELL"},
        ]
        self.daily_signals.main()

        rows = self._get_status_rows("daily_signals")
        self.assertIn("3 signals", rows[-1]["message"])

    # ── daily_digest ─────────────────────────────────────────────

    @patch("scripts.daily_digest.send_digest", return_value=True)
    def test_daily_digest_email_sent(self, mock_send):
        """daily_digest logs OK with 'Email sent' when email is configured."""
        self.daily_digest.main()

        rows = self._get_status_rows("daily_digest")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "RUNNING")
        self.assertEqual(rows[1]["status"], "OK")
        self.assertEqual(rows[1]["message"], "Email sent")

    @patch("scripts.daily_digest.send_digest", return_value=False)
    def test_daily_digest_email_not_configured(self, mock_send):
        """daily_digest logs OK with skip message when email not configured."""
        self.daily_digest.main()

        rows = self._get_status_rows("daily_digest")
        ok_row = rows[-1]
        self.assertEqual(ok_row["status"], "OK")
        self.assertIn("Skipped", ok_row["message"])
        self.assertIn("not configured", ok_row["message"])

    @patch("scripts.daily_digest.send_digest", side_effect=RuntimeError("smtp fail"))
    def test_daily_digest_error_logged(self, mock_send):
        """daily_digest logs ERROR on exception."""
        self.daily_digest.main()

        rows = self._get_status_rows("daily_digest")
        error_row = [r for r in rows if r["status"] == "ERROR"]
        self.assertEqual(len(error_row), 1)
        self.assertIn("smtp fail", error_row[0]["message"])

    @patch("scripts.daily_digest.send_digest", return_value=False)
    def test_daily_digest_no_crash_without_smtp(self, mock_send):
        """daily_digest completes without crash when SMTP is not configured."""
        self.daily_digest.main()
        rows = self._get_status_rows("daily_digest")
        statuses = [r["status"] for r in rows]
        self.assertNotIn("ERROR", statuses)

    # ── data_refresh ─────────────────────────────────────────────

    @patch("scripts.data_refresh.fetch_us_stocks")
    @patch("scripts.data_refresh.fetch_kr_stocks")
    def test_data_refresh_logs_running_then_ok(self, mock_kr, mock_us):
        """data_refresh logs RUNNING then OK to system_status."""
        mock_kr.return_value = {"005930": MagicMock()}
        mock_us.return_value = {"AAPL": MagicMock()}
        self._insert_stocks()

        self.data_refresh.main()

        rows = self._get_status_rows("data_refresh")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "RUNNING")
        self.assertEqual(rows[1]["status"], "OK")
        self.assertIn("2 stocks", rows[1]["message"])

    @patch("scripts.data_refresh.fetch_us_stocks")
    @patch("scripts.data_refresh.fetch_kr_stocks")
    def test_data_refresh_empty_universe(self, mock_kr, mock_us):
        """data_refresh works with empty stock universe."""
        self.data_refresh.main()

        rows = self._get_status_rows("data_refresh")
        ok_row = rows[-1]
        self.assertEqual(ok_row["status"], "OK")
        self.assertIn("0 stocks", ok_row["message"])
        mock_kr.assert_not_called()
        mock_us.assert_not_called()

    @patch("scripts.data_refresh.fetch_us_stocks", side_effect=RuntimeError("api down"))
    @patch("scripts.data_refresh.fetch_kr_stocks")
    def test_data_refresh_error_logged(self, mock_kr, mock_us):
        """data_refresh logs ERROR on exception."""
        mock_kr.return_value = {}
        self._insert_stocks()

        self.data_refresh.main()

        rows = self._get_status_rows("data_refresh")
        error_row = [r for r in rows if r["status"] == "ERROR"]
        self.assertEqual(len(error_row), 1)
        self.assertIn("api down", error_row[0]["message"])

    @patch("scripts.data_refresh.fetch_us_stocks")
    @patch("scripts.data_refresh.fetch_kr_stocks")
    def test_data_refresh_counts_fetched(self, mock_kr, mock_us):
        """data_refresh reports correct count of fetched stocks."""
        mock_kr.return_value = {"005930": MagicMock(), "000660": MagicMock()}
        mock_us.return_value = {}
        conn = self.db.get_connection()
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('005930', '삼성전자', 'KR')")
        conn.execute("INSERT INTO stocks (ticker, name, market) VALUES ('000660', 'SK하이닉스', 'KR')")
        conn.commit()
        conn.close()

        self.data_refresh.main()

        rows = self._get_status_rows("data_refresh")
        self.assertIn("2 stocks", rows[-1]["message"])

    @patch("scripts.data_refresh.fetch_us_stocks")
    @patch("scripts.data_refresh.fetch_kr_stocks")
    def test_data_refresh_partitions_by_market(self, mock_kr, mock_us):
        """data_refresh calls correct fetch function per market."""
        mock_kr.return_value = {"005930": MagicMock()}
        mock_us.return_value = {"AAPL": MagicMock()}
        self._insert_stocks()

        self.data_refresh.main()

        mock_kr.assert_called_once_with(["005930"])
        mock_us.assert_called_once_with(["AAPL"])

    # ── system_status table ──────────────────────────────────────

    @patch("scripts.data_refresh.fetch_us_stocks", return_value={})
    @patch("scripts.data_refresh.fetch_kr_stocks", return_value={})
    @patch("scripts.daily_digest.send_digest", return_value=False)
    @patch("scripts.daily_signals.generate_signals", return_value=[])
    @patch("scripts.daily_signals.fetch_us_stocks", return_value={})
    @patch("scripts.daily_signals.fetch_kr_stocks", return_value={})
    def test_system_status_has_entries_after_all_scripts(self, _a, _b, _c, _d, _e, _f):
        """system_status table has entries after running all 3 cron scripts."""
        self.daily_signals.main()
        self.daily_digest.main()
        self.data_refresh.main()

        rows = self._get_status_rows()
        self.assertGreaterEqual(len(rows), 6)  # 2 per script (RUNNING + OK)

        job_names = set(r["job_name"] for r in rows)
        self.assertIn("daily_signals", job_names)
        self.assertIn("daily_digest", job_names)
        self.assertIn("data_refresh", job_names)

    def test_system_status_table_exists(self):
        """system_status table is created by init_db."""
        conn = self.db.get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='system_status'"
        ).fetchall()
        conn.close()
        self.assertEqual(len(tables), 1)

    def test_system_status_columns(self):
        """system_status has expected columns."""
        conn = self.db.get_connection()
        conn.execute(
            "INSERT INTO system_status (job_name, status, message) VALUES ('test_job', 'OK', 'test')"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM system_status WHERE job_name='test_job'").fetchone()
        conn.close()
        self.assertIsNotNone(row["id"])
        self.assertEqual(row["job_name"], "test_job")
        self.assertEqual(row["status"], "OK")
        self.assertEqual(row["message"], "test")
        self.assertIsNotNone(row["timestamp"])

    def test_system_status_rejects_invalid_status(self):
        """system_status CHECK constraint rejects invalid status values."""
        conn = self.db.get_connection()
        with self.assertRaises(Exception):
            conn.execute(
                "INSERT INTO system_status (job_name, status, message) VALUES ('test', 'INVALID', 'x')"
            )
        conn.close()

    def test_system_status_ordering(self):
        """system_status entries can be ordered by id for chronological ordering."""
        conn = self.db.get_connection()
        conn.execute("INSERT INTO system_status (job_name, status, message) VALUES ('job', 'RUNNING', 'first')")
        conn.execute("INSERT INTO system_status (job_name, status, message) VALUES ('job', 'OK', 'second')")
        conn.commit()
        rows = conn.execute("SELECT * FROM system_status ORDER BY id").fetchall()
        conn.close()
        self.assertEqual(rows[0]["message"], "first")
        self.assertEqual(rows[1]["message"], "second")

    # ── notifier compose_digest_html ─────────────────────────────

    def test_compose_digest_html_with_signals(self):
        """compose_digest_html produces HTML with signal data."""
        from services.notifier import compose_digest_html
        signals = [
            {"ticker": "AAPL", "signal_type": "BUY", "strategy_name": "Golden Cross", "price": 150.0},
            {"ticker": "MSFT", "signal_type": "SELL", "strategy_name": "Death Cross", "price": 300.0},
        ]
        html = compose_digest_html(signals)
        self.assertIn("AAPL", html)
        self.assertIn("MSFT", html)
        self.assertIn("BUY", html)
        self.assertIn("SELL", html)
        self.assertIn("1 BUY", html)
        self.assertIn("1 SELL", html)

    def test_compose_digest_html_empty_signals(self):
        """compose_digest_html handles empty signal list."""
        from services.notifier import compose_digest_html
        html = compose_digest_html([])
        self.assertIn("No signals today", html)

    def test_send_digest_returns_false_without_config(self):
        """send_digest returns False when SMTP not configured."""
        import config.settings as settings
        original_user = settings.SMTP_USER
        original_to = settings.EMAIL_TO
        try:
            settings.SMTP_USER = ""
            settings.EMAIL_TO = ""
            import services.notifier as notifier_mod
            importlib.reload(notifier_mod)
            result = notifier_mod.send_digest()
            self.assertFalse(result)
        finally:
            settings.SMTP_USER = original_user
            settings.EMAIL_TO = original_to
            importlib.reload(notifier_mod)


if __name__ == "__main__":
    unittest.main()
