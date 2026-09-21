"""成长池只保存研究标签，报价仍由同一个 MarketDataService 提供。"""
import pandas as pd

STAGES = {'L1': '逻辑萌芽', 'L2': '送样/验证', 'L3': '定点/小批量', 'L4': '批量放量', 'L5': '业绩兑现'}


def load_growth(root):
    d = pd.read_csv(root / 'data/growth_inflection_watchlist.csv', dtype=str, keep_default_na=False)
    if d.code.duplicated().any() or not d.code.str.fullmatch(r'\d{6}').all():
        raise ValueError('成长池代码重复或格式错误')
    d = d[d.status.eq('ACTIVE')].copy()
    d['industry_name'] = d.industry.replace({'UNKNOWN': '待诊'})
    d['industry_id'] = 'GROWTH'
    d['industry_archetype'] = '待诊'
    return d


def filter_growth(d, choice):
    if choice.startswith('L'):
        return d[d.current_stage.str.startswith(choice[:2])]
    if choice == '今日有变化':
        today = pd.Timestamp.now(tz='Asia/Shanghai').strftime('%Y-%m-%d')
        return d[d.stage_changed.eq('TRUE') & d.last_review_date.eq(today)]
    if choice == '待复诊':
        return d[d.current_stage.isin(['UNKNOWN', '待诊', ''])]
    return d


def render_growth_detail(row):
    import streamlit as st
    st.subheader(f'{row["name"]} · {row.code}')
    st.markdown('**高成长跃迁诊断**')
    st.write('当前阶段：' + ('待诊' if row.current_stage == 'UNKNOWN' else row.current_stage))
    for dimension in ['空间', '刚需', '壁垒', '份额', '基数', '兑现', '预期']:
        st.write(f'{dimension}：待诊')
    st.write('关键证据：' + row.key_evidence)
    st.write('下一验证点（人工研究问题，尚未证实）：' + row.next_validation)
    st.write('今日触发：' + row.daily_trigger)
    st.write('风险检查清单（非已发生事实）：' + row.risk_note)
