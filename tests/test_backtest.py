import unittest
import pandas as pd
import numpy as np
from services.backtest_runner import run_backtest, compute_benchmark_return


class TestRunBacktest(unittest.TestCase):
    def _make_df(self, n=100):
        np.random.seed(42)
        dates = pd.date_range("2023-01-01", periods=n)
        close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
        return pd.DataFrame({
            "date": dates, "open": close - 1, "high": close + 1,
            "low": close - 2, "close": close,
            "volume": np.random.randint(1000, 10000, n),
        })

    def test_no_signals_returns_flat(self):
        """Strategy with impossible conditions should return ~0% return."""
        df = self._make_df()
        strategy = {"conditions": [{"indicator": "RSI", "operator": "<", "value": -100}]}
        result = run_backtest(df, strategy)
        self.assertEqual(result["total_return_pct"], 0.0)
        self.assertEqual(result["num_trades"], 0)

    def test_result_structure(self):
        df = self._make_df()
        strategy = {"conditions": [{"indicator": "RSI", "operator": "<", "value": 50}]}
        result = run_backtest(df, strategy)
        for key in ["total_return_pct", "sharpe_ratio", "max_drawdown_pct", "win_rate_pct", "num_trades", "equity_curve", "dates"]:
            self.assertIn(key, result)
        self.assertEqual(len(result["equity_curve"]), len(df))

    def test_equity_curve_starts_at_initial_capital(self):
        df = self._make_df()
        strategy = {"conditions": []}
        result = run_backtest(df, strategy, initial_capital=1_000_000)
        self.assertEqual(result["equity_curve"][0], 1_000_000)


class TestBenchmarkReturn(unittest.TestCase):
    def test_empty_df(self):
        self.assertEqual(compute_benchmark_return(pd.DataFrame()), 0.0)

    def test_positive_return(self):
        df = pd.DataFrame({"close": [100, 110]})
        self.assertEqual(compute_benchmark_return(df), 10.0)

    def test_negative_return(self):
        df = pd.DataFrame({"close": [100, 90]})
        self.assertEqual(compute_benchmark_return(df), -10.0)


if __name__ == "__main__":
    unittest.main()
