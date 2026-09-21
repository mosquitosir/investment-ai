"""只使用当前及之前的日线；收益率/振幅/距离以小数保存。"""
import numpy as np
import pandas as pd


def ratio_previous(series, window=20):
    baseline = series.shift(1).rolling(window, min_periods=window).mean()
    return series / baseline.where(baseline > 0)


def compute_indicators(frame, thresholds):
    d = frame.sort_values("date").reset_index(drop=True).copy()
    close, high, low = d["close"], d["high"], d["low"]
    previous = close.shift(1)
    d["daily_return"] = close / previous - 1
    d["return_20"] = close / close.shift(20) - 1
    d["amount_ratio_20"] = ratio_previous(d["amount"])
    d["turnover_ratio_20"] = ratio_previous(d["turnover_rate"])
    d["volume_ratio_20"] = ratio_previous(d["volume"])
    for window in [5, 10, 20, 60]:
        d[f"ma{window}"] = close.rolling(window, min_periods=window).mean()
    for window in [20, 60, 120]:
        peak = high.shift(1).rolling(window, min_periods=window).max()
        d[f"new_high_{window}"] = (close > peak).astype("boolean").mask(peak.isna(), pd.NA)
        d[f"distance_high_{window}"] = close / peak - 1
    platform_high = high.shift(1).rolling(20).max()
    platform_low = low.shift(1).rolling(20).min()
    d["platform_width_20"] = platform_high / platform_low - 1
    d["platform_breakout"] = ((d["platform_width_20"] <= thresholds["platform_width"]) &
        (close > platform_high) & (d["amount_ratio_20"] >= thresholds["platform_amount"]))
    d["ma_bull"] = (d.ma5 > d.ma10) & (d.ma10 > d.ma20)
    d["above_ma60"] = close > d.ma60
    d["ma_structure_changed"] = ((d.ma_bull != d.ma_bull.shift(1)) |
        (d.above_ma60 != d.above_ma60.shift(1))) & d.ma60.shift(1).notna()
    d["amplitude"] = (high - low) / previous
    span = (high - low).replace(0, np.nan)
    d["upper_shadow_ratio"] = (high - d[["open", "close"]].max(axis=1)) / span
    d["lower_shadow_ratio"] = (d[["open", "close"]].min(axis=1) - low) / span
    d["volatility_20"] = d.daily_return.rolling(20).std()
    d["drawdown_20"] = close / close.rolling(20).max() - 1
    d["bull_days"] = d.ma_bull.astype(int).rolling(thresholds["smooth_days"]).sum()
    d["up_amount_mean"] = d.amount.where(d.daily_return > 0).rolling(20, min_periods=1).mean()
    d["down_amount_mean"] = d.amount.where(d.daily_return < 0).rolling(20, min_periods=1).mean()
    d["history_count"] = np.arange(1, len(d) + 1)
    d["price_volume_pattern"] = d.apply(lambda row: price_volume_pattern(row, thresholds), axis=1)
    return d


def price_volume_pattern(r, t):
    a, ret = r["amount_ratio_20"], r["daily_return"]
    if pd.isna(a) or pd.isna(ret):
        return "missing"
    if a >= t["amount_active"]:
        if r["upper_shadow_ratio"] >= t["upper_shadow"]:
            return "放量冲高回落"
        if r["distance_high_60"] >= -t["near_high"] and abs(ret) <= t["stall_return"]:
            return "高位放量滞涨"
        return "放量上涨" if ret > 0 else "放量下跌" if ret < 0 else "放量平盘"
    if a < t["low_activity"]:
        return "缩量上涨" if ret > 0 else "缩量回调" if ret < 0 else "缩量平盘"
    return "常态量价"
