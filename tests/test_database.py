import unittest
import tempfile
import os
import sqlite3


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.environ["DB_PATH"] = self.db_path
        # Re-import to pick up test DB path
        import importlib
        import config.settings as settings
        settings.DB_PATH = self.db_path
        import models.database as db
        importlib.reload(db)
        self.db = db

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_init_db_creates_tables(self):
        self.db.init_db()
        conn = self.db.get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        conn.close()
        for expected in ["stocks", "price_cache", "strategies", "signals", "journal", "system_status"]:
            self.assertIn(expected, table_names)

    def test_wal_mode(self):
        self.db.init_db()
        conn = self.db.get_connection()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        self.assertEqual(mode, "wal")

    def test_foreign_keys_enabled(self):
        self.db.init_db()
        conn = self.db.get_connection()
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()
        self.assertEqual(fk, 1)

    def test_signal_unique_constraint(self):
        self.db.init_db()
        conn = self.db.get_connection()
        # Insert a strategy first
        conn.execute("INSERT INTO strategies (name, conditions, market) VALUES ('test', '[]', 'BOTH')")
        conn.execute(
            "INSERT INTO signals (ticker, date, signal_type, strategy_id, price, strength) "
            "VALUES ('AAPL', '2026-01-01', 'BUY', 1, 100.0, 1.0)"
        )
        # Duplicate should be ignored with INSERT OR IGNORE
        conn.execute(
            "INSERT OR IGNORE INTO signals (ticker, date, signal_type, strategy_id, price, strength) "
            "VALUES ('AAPL', '2026-01-01', 'BUY', 1, 100.0, 1.0)"
        )
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        conn.commit()
        conn.close()
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
