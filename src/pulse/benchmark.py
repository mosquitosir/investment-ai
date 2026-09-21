"""基准接口：V0.1 使用固定八股、每日再平衡的等权组合。"""
import pandas as pd


class EqualWeightBenchmark:
    source = "FALLBACK_WATCHLIST_EQUAL_WEIGHT_8（每日再平衡，含自身，非正式行业指数）"

    def build(self, frames, codes):
        if not frames:
            return pd.DataFrame(columns=["date", "benchmark_return_20"])
        # 按日期严格对齐，任何成员缺失则当日基准缺失，不动态剔除失败股票。
        returns = pd.concat({code: frames[code].set_index("date")["close"]
            for code in codes if code in frames}, axis=1).sort_index()
        returns = returns.reindex(columns=codes).pct_change(fill_method=None)
        daily = returns.mean(axis=1).where(returns.notna().sum(axis=1) == len(codes))
        result = pd.DataFrame({"date": daily.index,
            "benchmark_return_20": (1 + daily).rolling(20, min_periods=20).apply(
                lambda values: values.prod(), raw=True).values - 1})
        return result
