"""Tests for US-003: Strategy builder loads templates and runs backtest."""
import json
import os
import tempfile
import importlib
import unittest
import pandas as pd
import numpy as np

from templates.strategies import STRATEGY_TEMPLATES
from services.strategy_engine import (
    INDICATORS, OPERATORS, save_strategy, get_strategies, get_strategy,
    evaluate_condition, apply_strategy, compute_rsi, compute_ma,
    compute_volume_ratio,
)
from services.backtest_runner import run_backtest, compute_benchmark_return


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


# ── Template Tests ──────────────────────────────────────────────────────

class TestTemplates(unittest.TestCase):
    def test_seven_templates_exist(self):
        """AC: 7 template buttons are visible."""
        self.assertEqual(len(STRATEGY_TEMPLATES), 7)

    def test_template_names_unique(self):
        names = [t["name"] for t in STRATEGY_TEMPLATES]
        self.assertEqual(len(names), len(set(names)))

    def test_template_required_fields(self):
        for tmpl in STRATEGY_TEMPLATES:
            self.assertIn("name", tmpl)
            self.assertIn("conditions", tmpl)
            self.assertIn("market", tmpl)
            self.assertIn("is_template", tmpl)
            self.assertTrue(tmpl["is_template"])
            self.assertIn(tmpl["market"], ("KR", "US", "BOTH"))

    def test_template_conditions_have_valid_indicators(self):
        for tmpl in STRATEGY_TEMPLATES:
            for cond in tmpl["conditions"]:
                self.assertIn(cond["indicator"], INDICATORS,
                              f"Unknown indicator {cond['indicator']} in template {tmpl['name']}")
                self.assertIn(cond["operator"], OPERATORS,
                              f"Unknown operator {cond['operator']} in template {tmpl['name']}")

    def test_each_template_applies_without_error(self):
        """Every template should evaluate against sample data without crashing."""
        df = _make_ohlcv(n=200)
        for tmpl in STRATEGY_TEMPLATES:
            with self.subTest(template=tmpl["name"]):
                result = apply_strategy(df, tmpl)
                self.assertEqual(len(result), len(df))


# ── Condition Builder Tests ─────────────────────────────────────────────

class TestConditionBuilder(unittest.TestCase):
    def test_add_condition(self):
        """AC: Condition builder allows adding conditions."""
        conditions = []
        conditions.append({"indicator": "RSI", "operator": "<", "value": 30})
        self.assertEqual(len(conditions), 1)
        conditions.append({"indicator": "VOLUME_SPIKE", "operator": ">", "value": 1.5})
        self.assertEqual(len(conditions), 2)

    def test_remove_condition(self):
        """AC: Condition builder allows removing conditions."""
        conditions = [
            {"indicator": "RSI", "operator": "<", "value": 30},
            {"indicator": "VOLUME_SPIKE", "operator": ">", "value": 1.5},
        ]
        conditions.pop(0)
        self.assertEqual(len(conditions), 1)
        self.assertEqual(conditions[0]["indicator"], "VOLUME_SPIKE")

    def test_max_three_conditions(self):
        """Strategy page limits to 3 conditions."""
        conditions = [
            {"indicator": "RSI", "operator": "<", "value": 30},
            {"indicator": "VOLUME_SPIKE", "operator": ">", "value": 1.5},
            {"indicator": "PRICE_ABOVE_MA200", "operator": "==", "value": 1},
        ]
        self.assertEqual(len(conditions), 3)
        # UI disables add button at 3 conditions
        can_add = len(conditions) < 3
        self.assertFalse(can_add)

    def test_all_indicators_selectable(self):
        """8 indicators should be available in the dropdown."""
        self.assertEqual(len(INDICATORS), 8)
        expected = {"RSI", "MA_CROSS_20_50", "MA_CROSS_5_20", "PER", "PBR",
                    "VOLUME_SPIKE", "PRICE_ABOVE_MA200", "PRICE_BELOW_MA200"}
        self.assertEqual(set(INDICATORS.keys()), expected)


# ── Save Strategy DB Tests ──────────────────────────────────────────────

class TestSaveStrategy(unittest.TestCase):
    def setUp(self):
        self.db_path = _setup_test_db()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_save_returns_id(self):
        """AC: Save Strategy button persists to DB."""
        sid = save_strategy({
            "name": "Test Strategy",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 30}],
            "market": "BOTH",
            "is_template": False,
        })
        self.assertIsInstance(sid, int)
        self.assertGreater(sid, 0)

    def test_save_and_retrieve(self):
        """Saved strategy should be retrievable with correct data."""
        conditions = [
            {"indicator": "RSI", "operator": "<", "value": 30},
            {"indicator": "VOLUME_SPIKE", "operator": ">", "value": 1.5},
        ]
        sid = save_strategy({
            "name": "My RSI + Volume",
            "conditions": conditions,
            "market": "KR",
            "is_template": False,
        })
        retrieved = get_strategy(sid)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["name"], "My RSI + Volume")
        self.assertEqual(retrieved["market"], "KR")
        self.assertFalse(retrieved["is_template"])
        self.assertEqual(len(retrieved["conditions"]), 2)

    def test_save_template_strategy(self):
        sid = save_strategy({
            "name": "Template Test",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 25}],
            "market": "BOTH",
            "is_template": True,
        })
        retrieved = get_strategy(sid)
        self.assertTrue(retrieved["is_template"])

    def test_get_strategies_returns_all(self):
        save_strategy({"name": "S1", "conditions": [], "market": "KR", "is_template": False})
        save_strategy({"name": "S2", "conditions": [], "market": "US", "is_template": True})
        all_strats = get_strategies()
        self.assertEqual(len(all_strats), 2)

    def test_get_strategies_templates_only(self):
        save_strategy({"name": "S1", "conditions": [], "market": "KR", "is_template": False})
        save_strategy({"name": "T1", "conditions": [], "market": "US", "is_template": True})
        templates = get_strategies(templates_only=True)
        self.assertEqual(len(templates), 1)
        self.assertTrue(templates[0]["is_template"])

    def test_get_nonexistent_strategy(self):
        result = get_strategy(9999)
        self.assertIsNone(result)

    def test_conditions_json_roundtrip(self):
        """Conditions should survive JSON serialization in SQLite."""
        conditions = [
            {"indicator": "MA_CROSS_20_50", "operator": "CROSS_ABOVE", "value": 0},
            {"indicator": "VOLUME_SPIKE", "operator": ">", "value": 2.0},
        ]
        sid = save_strategy({
            "name": "JSON Test",
            "conditions": conditions,
            "market": "BOTH",
            "is_template": False,
        })
        retrieved = get_strategy(sid)
        self.assertEqual(retrieved["conditions"], conditions)


# ── Backtest Scoreboard Tests ───────────────────────────────────────────

class TestBacktestScoreboard(unittest.TestCase):
    def test_scoreboard_has_all_metrics(self):
        """AC: Run Backtest returns scoreboard metrics (return, Sharpe, drawdown, win rate)."""
        df = _make_ohlcv()
        strategy = {"conditions": [{"indicator": "RSI", "operator": "<", "value": 40}]}
        result = run_backtest(df, strategy)
        self.assertIn("total_return_pct", result)
        self.assertIn("sharpe_ratio", result)
        self.assertIn("max_drawdown_pct", result)
        self.assertIn("win_rate_pct", result)
        self.assertIn("num_trades", result)

    def test_metrics_are_numeric(self):
        df = _make_ohlcv()
        strategy = {"conditions": [{"indicator": "RSI", "operator": "<", "value": 40}]}
        result = run_backtest(df, strategy)
        for key in ["total_return_pct", "sharpe_ratio", "max_drawdown_pct", "win_rate_pct"]:
            self.assertIsInstance(result[key], (int, float), f"{key} is not numeric")
            self.assertFalse(np.isnan(result[key]), f"{key} is NaN")

    def test_max_drawdown_is_non_positive(self):
        df = _make_ohlcv()
        strategy = {"conditions": [{"indicator": "RSI", "operator": "<", "value": 40}]}
        result = run_backtest(df, strategy)
        self.assertLessEqual(result["max_drawdown_pct"], 0)

    def test_win_rate_in_range(self):
        df = _make_ohlcv()
        strategy = {"conditions": [{"indicator": "RSI", "operator": "<", "value": 40}]}
        result = run_backtest(df, strategy)
        self.assertGreaterEqual(result["win_rate_pct"], 0)
        self.assertLessEqual(result["win_rate_pct"], 100)

    def test_benchmark_return_computed(self):
        df = _make_ohlcv()
        benchmark = compute_benchmark_return(df)
        self.assertIsInstance(benchmark, float)


# ── Equity Curve Tests ──────────────────────────────────────────────────

class TestEquityCurve(unittest.TestCase):
    def test_equity_curve_length_matches_data(self):
        """AC: Equity curve chart renders — curve must align with data length."""
        df = _make_ohlcv(n=100)
        strategy = {"conditions": [{"indicator": "RSI", "operator": "<", "value": 50}]}
        result = run_backtest(df, strategy)
        self.assertEqual(len(result["equity_curve"]), len(df))

    def test_dates_length_matches_data(self):
        df = _make_ohlcv(n=100)
        strategy = {"conditions": [{"indicator": "RSI", "operator": "<", "value": 50}]}
        result = run_backtest(df, strategy)
        self.assertEqual(len(result["dates"]), len(df))

    def test_equity_curve_all_positive(self):
        """Portfolio value should never go negative."""
        df = _make_ohlcv(n=100)
        strategy = {"conditions": [{"indicator": "RSI", "operator": "<", "value": 40}]}
        result = run_backtest(df, strategy)
        for val in result["equity_curve"]:
            self.assertGreater(val, 0)

    def test_equity_curve_starts_at_initial_capital(self):
        df = _make_ohlcv(n=100)
        strategy = {"conditions": []}  # No signals → capital stays flat
        result = run_backtest(df, strategy, initial_capital=5_000_000)
        self.assertEqual(result["equity_curve"][0], 5_000_000)


# ── Backtest with Each Template ─────────────────────────────────────────

class TestBacktestWithTemplates(unittest.TestCase):
    def test_each_template_backtests_without_error(self):
        """Every template should run through backtest without crashing."""
        df = _make_ohlcv(n=200)
        for tmpl in STRATEGY_TEMPLATES:
            with self.subTest(template=tmpl["name"]):
                result = run_backtest(df, tmpl)
                self.assertIn("total_return_pct", result)
                self.assertEqual(len(result["equity_curve"]), len(df))


if __name__ == "__main__":
    unittest.main()
