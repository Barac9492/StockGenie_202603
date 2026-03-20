import unittest
import pandas as pd
import numpy as np
from services.strategy_engine import compute_rsi, compute_ma, evaluate_condition, apply_strategy, _compare


class TestComputeRSI(unittest.TestCase):
    def test_rsi_range(self):
        """RSI should always be between 0 and 100."""
        close = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109,
                           111, 110, 112, 114, 113, 115, 117, 116, 118, 120])
        rsi = compute_rsi(close)
        valid = rsi.dropna()
        self.assertTrue((valid >= 0).all())
        self.assertTrue((valid <= 100).all())

    def test_rsi_all_gains(self):
        """Monotonically increasing prices should give RSI near 100 or NaN (division by zero)."""
        close = pd.Series(range(100, 130))
        rsi = compute_rsi(close)
        last = rsi.iloc[-1]
        # When all changes are gains, avg_loss=0 → rs=inf → RSI=NaN or 100
        self.assertTrue(np.isnan(last) or last > 90)

    def test_rsi_all_losses(self):
        """Monotonically decreasing prices should give RSI near 0."""
        close = pd.Series(range(130, 100, -1))
        rsi = compute_rsi(close)
        self.assertLess(rsi.iloc[-1], 10)


class TestComputeMA(unittest.TestCase):
    def test_ma_simple(self):
        close = pd.Series([10, 20, 30, 40, 50])
        ma = compute_ma(close, 3)
        self.assertAlmostEqual(ma.iloc[-1], 40.0)

    def test_ma_nan_for_insufficient_data(self):
        close = pd.Series([10, 20])
        ma = compute_ma(close, 5)
        self.assertTrue(ma.isna().all())


class TestCompare(unittest.TestCase):
    def test_less_than(self):
        s = pd.Series([10, 20, 30])
        result = _compare(s, "<", 25)
        self.assertEqual(list(result), [True, True, False])

    def test_greater_equal(self):
        s = pd.Series([10, 20, 30])
        result = _compare(s, ">=", 20)
        self.assertEqual(list(result), [False, True, True])

    def test_unknown_operator(self):
        s = pd.Series([10, 20])
        result = _compare(s, "INVALID", 15)
        self.assertTrue((~result).all())


class TestEvaluateCondition(unittest.TestCase):
    def _make_df(self, n=100):
        np.random.seed(42)
        close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
        return pd.DataFrame({
            "open": close - 1, "high": close + 1,
            "low": close - 2, "close": close,
            "volume": np.random.randint(1000, 10000, n),
        })

    def test_rsi_condition(self):
        df = self._make_df()
        result = evaluate_condition(df, {"indicator": "RSI", "operator": "<", "value": 30})
        self.assertEqual(len(result), len(df))
        self.assertIsInstance(result.dtype, type(pd.Series([True]).dtype))

    def test_ma_crossover(self):
        df = self._make_df(200)
        result = evaluate_condition(df, {"indicator": "MA_CROSS_20_50", "operator": "CROSS_ABOVE", "value": 0})
        self.assertEqual(len(result), len(df))

    def test_unknown_indicator(self):
        df = self._make_df()
        result = evaluate_condition(df, {"indicator": "UNKNOWN", "operator": ">", "value": 0})
        self.assertTrue((~result).all())


class TestApplyStrategy(unittest.TestCase):
    def test_empty_conditions(self):
        df = pd.DataFrame({"close": [100, 200], "volume": [1000, 2000],
                           "open": [99, 199], "high": [101, 201], "low": [98, 198]})
        result = apply_strategy(df, {"conditions": []})
        self.assertTrue((~result).all())

    def test_single_condition(self):
        np.random.seed(42)
        close = pd.Series(np.cumsum(np.random.randn(50)) + 100)
        df = pd.DataFrame({
            "open": close - 1, "high": close + 1,
            "low": close - 2, "close": close,
            "volume": np.random.randint(1000, 10000, 50),
        })
        result = apply_strategy(df, {"conditions": [{"indicator": "RSI", "operator": "<", "value": 90}]})
        self.assertEqual(len(result), len(df))


if __name__ == "__main__":
    unittest.main()
