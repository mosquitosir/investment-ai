"""规则匹配，不输出交易建议；confidence 是完整度评分，不是收益概率。"""
import pandas as pd


def classify(row, t):
    if row.get("history_count", 0) < t["min_history"]:
        return {"pulse_type": "INSUFFICIENT_DATA", "pulse_confidence": 0.0,
                "pulse_reasons": "不足150个有效交易日"}
    required = ["amount_ratio_20", "daily_return", "ma60", "volatility_20"]
    if any(pd.isna(row.get(key)) for key in required):
        return {"pulse_type": "INSUFFICIENT_DATA", "pulse_confidence": 0.0,
                "pulse_reasons": "核心指标缺失"}
    a, turn = row["amount_ratio_20"], row.get("turnover_ratio_20", float("nan"))
    matches = []
    if row["price_volume_pattern"] in ["放量冲高回落", "高位放量滞涨"]:
        matches.append(("涩", row["price_volume_pattern"]))
    if (a >= t["amount_active"] and row.get("volume_ratio_20", 0) >= t["amount_active"] and
        pd.notna(turn) and turn >= t["turnover_abnormal"] and
        row["daily_return"] >= t["daily_fast"] and row["amplitude"] >= t["amplitude_fast"]):
        matches.append(("数", "成交额、成交量、换手、价格和振幅同时增强"))
    if a >= t["amount_active"] and row["bull_days"] < t["smooth_days"]:
        matches.append(("浮", "成交活跃，短均线多头尚未持续"))
    if (row["bull_days"] >= t["smooth_days"] and row["above_ma60"] and
        row["up_amount_mean"] > row["down_amount_mean"] and
        row["drawdown_20"] >= -t["smooth_drawdown"]):
        matches.append(("滑", "连续短均线多头、站上MA60、上涨均额高于下跌均额且回撤温和"))
    if (a < t["low_activity"] and pd.notna(turn) and turn < t["low_activity"] and
        not row["ma_bull"] and not row["above_ma60"]):
        matches.append(("沉", "成交额和换手偏低，趋势偏弱"))
    if row["volatility_20"] < t["low_volatility"] and abs(row["return_20"]) < t["slow_return_20"]:
        matches.append(("迟", "20日波动低且价格推进缓慢"))
    pulse = matches[0][0] if len(matches) == 1 else "MIXED" if matches else "UNKNOWN"
    completeness = sum(pd.notna(row.get(k)) for k in ["amount_ratio_20", "turnover_ratio_20", "rs20", "volume_ratio_20"]) / 4
    confidence = round((0.75 if len(matches) == 1 else 0.4 if matches else 0) * completeness, 2)
    reasons = "；".join(f"{kind}：{why}" for kind, why in matches) or "未满足任何单一脉象规则"
    if pd.isna(turn):
        reasons += "；P4 missing，沉/数条件禁用"
    return {"pulse_type": pulse, "pulse_confidence": confidence, "pulse_reasons": reasons}


def detect_change(previous, current):
    valid = {"沉", "浮", "迟", "数", "滑", "涩", "MIXED"}
    changed = previous in valid and current in valid and previous != current
    return changed, f"规则状态变化：{previous} → {current}" if changed else "无可确认脉变"
