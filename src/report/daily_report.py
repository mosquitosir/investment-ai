"""只重点描述触发异常的股票，其余用一行汇总。"""
from pathlib import Path


def write_report(result, path, now):
    dates = sorted(set(result.trade_date.astype(str)) - {"missing"})
    healthy = result.data_status.eq("OK")
    focus = result.trigger_count.gt(0)
    lines = ["# 《资本脉象｜每日候诊单》", "",
        f"生成时间：{now.isoformat(timespec='seconds')}",
        f"交易日：{'、'.join(dates) or 'missing'}（以各股实际日期为准）",
        "数据源：" + "、".join(sorted(set(result.data_source.astype(str)))),
        f"候诊池：{len(result)}；数据完整且新鲜：{int(healthy.sum())}；脉变：{int(result.pulse_changed.sum())}；异常触发：{int(focus.sum())}；数据降级/缺失：{int((~healthy).sum())}", "",
        "基准：" + str(result.benchmark_source.iloc[0]),
        "价格口径：后复权 OHLC，CSV close 不是当日未复权成交报价。收益率、振幅、RS和高点距离为小数；换手率为百分数；成交额为元、成交量为股。",
        "研究标签与脉象不是投资评级或买卖信号。confidence 只是规则完整度评分，不是预测概率。",
        "新鲜度按最近工作日保守检查，未接正式交易日历；节假日/停牌可能被标 DATA_STALE。",
        "上一交易日状态由截至该日的历史数据重算，并已保存；未采用当天数据回填之前的基准。", ""]
    if not focus.any():
        if healthy.all():
            lines.append("今日候诊池无显著脉变。")
        else:
            lines.append("可用数据未检出显著脉变；存在缺失或陈旧数据，不能据此判定整个候诊池无异常。")
    for row in result[focus].to_dict("records"):
        lines += ["---", f"## 【{row['name']} {row['code']}】", "",
            f"体：{row['body_state']}（用户提供的研究标签）", f"势：{row['industry_state']}",
            f"交易日：{row['trade_date']}；数据状态：{row['data_status']}；最近获取：{row['last_update']}",
            f"脉：{row['previous_pulse']} → {row['current_pulse']}；规则评分：{row['pulse_confidence']}",
            "", "触发："]
        lines += [f"- {reason}" for reason in row["trigger_reasons"].split("；") if reason]
        lines += ["", "解释：" + row["pulse_reasons"], ""]
    quiet = result[~focus & healthy]
    lines += ["---", "## 其余无显著变化", "、".join(quiet.name) or "无", "", "## 数据质量与降级"]
    for row in result[~healthy].to_dict("records"):
        lines.append(f"- {row['name']} {row['code']}：{row['data_status']}；缺失 {row.get('missing_fields', '')}；{row.get('data_errors', '')}")
    if healthy.all():
        lines.append("- 八股所需历史及本次核心指标齐全；行业基准仍为候诊池替代基准。")
    lines += ["", "完整数值见 data/pulse_watchlist.csv；规则见 docs/research/pulse_rules.md。",
              "系统保留 R01–R07，行情脉象不能替代企业基本面诊断。"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(lines), encoding="utf-8")
