import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date

import numpy as np
import pandas as pd

from src.pulse.indicators import compute_indicators, price_volume_pattern
from src.pulse.classifier import classify, detect_change
from src.pulse.benchmark import EqualWeightBenchmark
from src.data.akshare_adapter import normalize_history, HistoryAdapter

ROOT = Path(__file__).resolve().parents[1]
T = json.loads((ROOT / "config/pulse_thresholds.json").read_text())


def fixture(n=180):
    close = np.arange(n, dtype=float) + 100
    return pd.DataFrame({"date": pd.bdate_range("2025-01-01", periods=n), "open": close - 0.5,
        "close": close, "high": close + 1, "low": close - 1, "volume": np.full(n, 1000.),
        "amount": np.full(n, 100.), "turnover_rate": np.full(n, 2.)})


class IndicatorTests(unittest.TestCase):
    def test_ma(self):
        f = fixture()
        d = compute_indicators(f, T)
        for n in [5, 10, 20, 60]:
            self.assertAlmostEqual(d.iloc[-1][f"ma{n}"], f.close.tail(n).mean())

    def test_ratios_exclude_today(self):
        f = fixture()
        f.loc[len(f)-1, ["amount", "turnover_rate"]] = [200., 6.]
        d = compute_indicators(f, T)
        self.assertEqual(d.iloc[-1].amount_ratio_20, 2.)
        self.assertEqual(d.iloc[-1].turnover_ratio_20, 3.)

    def test_new_high(self):
        f = fixture()
        f.loc[len(f)-1, "close"] += 2
        f.loc[len(f)-1, "high"] += 2
        d = compute_indicators(f, T)
        for n in [20, 60, 120]:
            self.assertTrue(d.iloc[-1][f"new_high_{n}"])
            self.assertAlmostEqual(d.iloc[-1][f"distance_high_{n}"], f.close.iloc[-1] / f.high.iloc[-n-1:-1].max() - 1)
        self.assertTrue(pd.isna(d.iloc[5].new_high_20))

    def test_no_future_data(self):
        f = fixture()
        before = compute_indicators(f.iloc[:160], T)
        f.loc[160:, ["close", "amount", "turnover_rate", "high"]] *= 100
        after = compute_indicators(f, T).iloc[:160]
        pd.testing.assert_frame_equal(before, after)

    def test_missing_and_zero_baselines(self):
        f = fixture()
        f["turnover_rate"] = np.nan
        f["amount"] = 0.
        d = compute_indicators(f, T)
        self.assertTrue(pd.isna(d.iloc[-1].turnover_ratio_20))
        self.assertTrue(pd.isna(d.iloc[-1].amount_ratio_20))
        self.assertEqual(classify(d.iloc[-1], T)["pulse_type"], "INSUFFICIENT_DATA")

    def test_benchmark_rs_and_alignment(self):
        dates = pd.bdate_range("2025-01-01", periods=45)
        a = pd.DataFrame({"date": dates, "close": 100 * 1.01 ** np.arange(45)})
        b = pd.DataFrame({"date": dates, "close": 100 * 1.02 ** np.arange(45)})
        result = EqualWeightBenchmark().build({"a": a, "b": b}, ["a", "b"])
        self.assertAlmostEqual(result.iloc[-1].benchmark_return_20, 1.015 ** 20 - 1)
        rs = (a.close.iloc[-1] / a.close.iloc[-21] - 1) - result.iloc[-1].benchmark_return_20
        self.assertAlmostEqual(rs, 1.01 ** 20 - 1.015 ** 20)
        missing = EqualWeightBenchmark().build({"a": a}, ["a", "b"])
        self.assertTrue(missing.benchmark_return_20.isna().all())
        short = EqualWeightBenchmark().build({"a": a.iloc[:30], "b": b.iloc[:30]}, ["a", "b"])
        pd.testing.assert_frame_equal(short, result.iloc[:30])

    def test_patterns(self):
        base = {"amount_ratio_20": 1.6, "daily_return": .03, "upper_shadow_ratio": .1, "distance_high_60": -.1}
        for changes, expected in [({}, "放量上涨"), ({"daily_return": -.03}, "放量下跌"),
            ({"amount_ratio_20": .5}, "缩量上涨"),
            ({"amount_ratio_20": .5, "daily_return": -.03}, "缩量回调"),
            ({"upper_shadow_ratio": .7}, "放量冲高回落"),
            ({"distance_high_60": -.01, "daily_return": .001}, "高位放量滞涨")]:
            self.assertEqual(price_volume_pattern(dict(base, **changes), T), expected)


class ClassifierTests(unittest.TestCase):
    def base(self):
        return dict(history_count=180, amount_ratio_20=1., turnover_ratio_20=1., volume_ratio_20=1.,
            daily_return=.01, ma60=100., volatility_20=.03, amplitude=.02,
            price_volume_pattern="常态量价", bull_days=3, ma_bull=False, above_ma60=False,
            up_amount_mean=100., down_amount_mean=110., drawdown_20=-.15, return_20=.1, rs20=.1)

    def test_six_states_unknown_mixed(self):
        scenarios = [({"amount_ratio_20": .5, "turnover_ratio_20": .5}, "沉"),
            ({"amount_ratio_20": 1.6}, "浮"),
            ({"volatility_20": .005, "return_20": .01}, "迟"),
            ({"amount_ratio_20": 2., "volume_ratio_20": 2., "turnover_ratio_20": 2.,
              "daily_return": .05, "amplitude": .07, "bull_days": 5}, "数"),
            ({"bull_days": 5, "above_ma60": True, "up_amount_mean": 120., "drawdown_20": -.03}, "滑"),
            ({"price_volume_pattern": "高位放量滞涨"}, "涩"),
            ({}, "UNKNOWN"),
            ({"amount_ratio_20": .5, "turnover_ratio_20": .5, "volatility_20": .005, "return_20": .01}, "MIXED")]
        for changes, expected in scenarios:
            self.assertEqual(classify(dict(self.base(), **changes), T)["pulse_type"], expected)

    def test_change_and_insufficient(self):
        self.assertTrue(detect_change("数", "涩")[0])
        self.assertFalse(detect_change("滑", "滑")[0])
        self.assertFalse(detect_change("INSUFFICIENT_DATA", "滑")[0])
        self.assertEqual(classify(dict(self.base(), history_count=149), T)["pulse_type"], "INSUFFICIENT_DATA")


class AdapterTests(unittest.TestCase):
    def test_normalize_missing_turnover_and_cutoff(self):
        f = fixture().drop(columns="turnover_rate")
        normalized = normalize_history(f, "002371", "测试", "tencent", "test", f.date.iloc[-2])
        self.assertEqual(len(normalized), len(f)-1)
        self.assertTrue(normalized.turnover_rate.isna().all())
        f["turnover"] = .02
        normalized = normalize_history(f, "002371", "测试", "tencent", "test", f.date.iloc[-1])
        self.assertAlmostEqual(normalized.turnover_rate.iloc[-1], 2.)

    def test_cache_on_api_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "data/cache") as folder:
            adapter = HistoryAdapter(folder, T)
            data = normalize_history(fixture(), "002371", "测试", "tencent", "original", date(2026, 9, 18))
            data.to_csv(adapter.cache / "002371_hfq.csv", index=False)
            with patch("src.data.akshare_adapter.subprocess.run", side_effect=TimeoutError("test")):
                cached, status, errors = adapter.get_history({"code": "002371", "name": "测试"}, date(2026, 9, 18))
            self.assertEqual(status, "DATA_STALE")
            self.assertEqual(cached.last_update.iloc[-1], "original")
            self.assertEqual(len(errors), 2)
            missing, status, _ = adapter.get_history({"code": "688012", "name": "缺失"}, date(2026, 9, 18), refresh=False)
            self.assertEqual(status, "DATA_MISSING")
            self.assertTrue(missing.empty)


if __name__ == "__main__":
    unittest.main()
