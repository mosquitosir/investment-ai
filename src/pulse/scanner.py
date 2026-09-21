"""每日扫描入口：python -m src.pulse.scanner；只扫描配置里的八家公司。"""
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import hashlib
import pandas as pd

from src.data.akshare_adapter import HistoryAdapter
from src.pulse.indicators import compute_indicators
from src.pulse.benchmark import EqualWeightBenchmark
from src.pulse.classifier import classify, detect_change
from src.report.daily_report import write_report

ROOT = Path(__file__).resolve().parents[2]


def get_triggers(row, previous, thresholds):
    reasons = []
    if row["pulse_changed"]:
        reasons.append(row["change_reason"])
    for field, threshold, title in [
        ("amount_ratio_20", thresholds["amount_active"], "成交额/前20日均额"),
        ("turnover_ratio_20", thresholds["turnover_abnormal"], "换手/前20日均换手")]:
        if pd.notna(row.get(field)) and row[field] >= threshold:
            reasons.append(f"{title} {row[field]:.2f}倍")
    for window in [20, 60, 120]:
        value = row.get(f"new_high_{window}")
        if pd.notna(value) and bool(value):
            reasons.append(f"收盘突破此前{window}日最高价")
    if row.get("platform_breakout", False):
        reasons.append("20日窄平台突破候选")
    if row.get("ma_structure_changed", False):
        reasons.append("短均线多头或站上MA60状态变化")
    if previous is not None and pd.notna(row.get("rs20")) and pd.notna(previous.get("rs20")):
        delta = row["rs20"] - previous["rs20"]
        if abs(delta) >= thresholds["rs_change"]:
            reasons.append(f"RS20较上一交易日变化 {delta * 100:+.2f}个百分点")
    if row.get("price_volume_pattern") in ["放量冲高回落", "高位放量滞涨"]:
        reasons.append(row["price_volume_pattern"])
    return reasons


def run_scan(root=ROOT, end=None, refresh=True, adapter=None):
    root = Path(root)
    watchlist = json.loads((root / "config/watchlist.yaml").read_text(encoding="utf-8"))
    t = json.loads((root / "config/pulse_thresholds.json").read_text(encoding="utf-8"))
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    closed_cutoff = now.date() if now.hour >= t["completed_day_hour"] else now.date() - timedelta(days=1)
    end = min(end or closed_cutoff, closed_cutoff)
    # 周末回退；节假日由数据日期判断，未接交易日历时明确标记不确定性。
    expected = end
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    adapter = adapter or HistoryAdapter(root, t)
    frames, statuses, errors = {}, {}, {}
    for stock in watchlist["stocks"]:
        code = stock["code"]
        print(f"Fetching {code} ...", flush=True)
        frame, status, issue = adapter.get_history(stock, end, refresh=refresh)
        if not frame.empty:
            frame = frame[frame["date"] <= pd.Timestamp(end)].copy()
        if frame.empty:
            status = "DATA_MISSING"
        else:
            frames[code] = frame
            if frame.date.max().date() < expected:
                status = "DATA_STALE"
                issue.append("最新日线早于工作日参考日期；可能节假日、停牌或延迟，未接正式交易日历")
        statuses[code], errors[code] = status, issue
        print(f"  {status}: {len(frame)} rows", flush=True)

    benchmark = EqualWeightBenchmark()
    codes = [stock["code"] for stock in watchlist["stocks"]]
    bench = benchmark.build(frames, codes)
    rows, saved_states = [], []
    for stock in watchlist["stocks"]:
        code = stock["code"]
        row = dict(stock, industry_state=watchlist["industry_state"], benchmark_source=benchmark.source,
            data_status=statuses[code], data_errors="；".join(errors[code]),
            price_adjustment="hfq（后复权价格，不是当日未复权报价）", scan_reference_date=str(expected))
        if code not in frames:
            row.update(trade_date="missing", data_source="missing", last_update="missing",
                current_pulse="INSUFFICIENT_DATA", pulse_type="INSUFFICIENT_DATA", previous_pulse="UNKNOWN",
                pulse_confidence=0.0, pulse_changed=False, pulse_reasons="无有效历史数据",
                trigger_count=0, trigger_reasons="", missing_fields="ALL", change_reason="不可比较")
            rows.append(row)
            continue
        computed = compute_indicators(frames[code], t).merge(bench, on="date", how="left")
        computed["rs20"] = computed["return_20"] - computed["benchmark_return_20"]
        latest = computed.iloc[-1].to_dict()
        previous = computed.iloc[-2].to_dict() if len(computed) >= 2 else None
        current_state = classify(latest, t)
        previous_state = classify(previous, t) if previous else {"pulse_type": "UNKNOWN"}
        changed, reason = detect_change(previous_state["pulse_type"], current_state["pulse_type"])
        row.update(latest)
        row.update(current_state)
        row.update(previous_pulse=previous_state["pulse_type"], current_pulse=current_state["pulse_type"],
            pulse_changed=changed, change_reason=reason,
            previous_trade_date=previous["trade_date"] if previous else "missing",
            previous_state_source="由上一条交易日历史日线重算；与本日状态一同保存")
        missing = [key for key in ["volume", "amount", "amount_ratio_20", "turnover_rate",
            "turnover_ratio_20", "rs20", "ma60", "distance_high_120"] if pd.isna(row.get(key))]
        row["missing_fields"] = ",".join(missing)
        if missing and row["data_status"] == "OK":
            row["data_status"] = "PARTIAL_MISSING"
        if statuses[code] == "DATA_STALE":
            row["pulse_confidence"] = round(row["pulse_confidence"] * 0.5, 2)
        triggers = get_triggers(row, previous, t)
        row.update(trigger_count=len(triggers), trigger_reasons="；".join(triggers))
        rows.append(row)
        for state_row, state in [(previous, previous_state), (latest, current_state)]:
            if state_row:
                saved_states.append({"code": code, "trade_date": state_row["trade_date"],
                    "pulse_type": state["pulse_type"], "data_source": row["data_source"],
                    "computed_at": now.isoformat(),
                    "threshold_hash": hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest()[:12]})

    result = pd.DataFrame(rows)
    required = "trade_date code name body_state industry_state close daily_return amount amount_ratio_20 turnover_rate turnover_ratio_20 ma5 ma10 ma20 ma60 new_high_20 new_high_60 new_high_120 return_20 benchmark_return_20 rs20 benchmark_source price_volume_pattern previous_pulse current_pulse pulse_changed pulse_confidence trigger_count trigger_reasons data_source data_status last_update pulse_type pulse_reasons change_reason".split()
    for column in required:
        if column not in result:
            result[column] = pd.NA
    result = result[required + [column for column in result if column not in required]]
    (root / "data").mkdir(exist_ok=True)
    result.to_csv(root / "data/pulse_watchlist.csv", index=False, encoding="utf-8-sig", na_rep="missing")
    state_path = root / "data/cache/pulse_states.csv"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if saved_states:
        states = pd.DataFrame(saved_states)
        if state_path.exists():
            states = pd.concat([pd.read_csv(state_path, dtype={"code": str}), states], ignore_index=True)
        states = states.drop_duplicates(["code", "trade_date"], keep="last").sort_values(["code", "trade_date"])
        states.to_csv(state_path, index=False, encoding="utf-8-sig")
    write_report(result, root / "reports/daily_pulse_report.md", now)
    print(result[["code", "data_status", "previous_pulse", "current_pulse", "trigger_count"]].to_string(index=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-only", action="store_true", help="只用缓存；报告明确标为 DATA_STALE")
    parser.add_argument("--as-of", help="截止日期 YYYY-MM-DD，不允许使用未来或未收盘数据")
    args = parser.parse_args()
    run_scan(end=datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else None,
             refresh=not args.cache_only)
