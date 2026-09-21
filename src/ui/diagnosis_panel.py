import streamlit as st
import pandas as pd


def render_diagnosis(row, diagnosis):
    st.subheader(f"{row['name']} · {row['code']}")
    st.caption(row['industry_name'])
    st.markdown('**数据事实**')
    price='--' if pd.isna(row['price']) else f"{row['price']:.2f}"
    change='--' if pd.isna(row['change_pct']) else f"{row['change_pct']:+.2f}%"
    st.write(f"当前价 {price}　涨跌 {change}")
    st.caption(f"行情日期：{row.get('trade_date') or '--'} · {row['data_status']}")
    st.divider()
    st.markdown('**模型诊断 · 不构成投资评级**')
    st.caption(f"诊断日期：{diagnosis['diagnosis_date']}；已有历史结果，不随刷新行情自动重算。")
    with st.expander('A｜价值诊断',expanded=True):
        st.write('天时：待接入')
        st.write('行业势：'+str(diagnosis['industry_state']))
        st.write('人和体质：'+str(diagnosis['body_state']))
        st.caption('体质为用户研究标签，行业名称不代表行业强弱。')
        st.write('主证：待诊　｜　红旗门：待接入')
    with st.expander('B｜地利八诊'):
        for label,key in zip('位 筹 控 活 行 压 情 时'.split(),['position_state','chip_state','control_state','activity_state','capital_behavior_state','capital_pressure_state','sentiment_state','market_regime_state']):
            st.write(f'{label}：{diagnosis[key]}')
    with st.expander('C｜脉诊',expanded=True):
        st.write(f"{diagnosis['previous_pulse']} → {diagnosis['current_pulse']}")
        st.write(f"脉变：{diagnosis['pulse_changed']}；规则评分：{diagnosis['pulse_confidence']}")
        st.caption(str(diagnosis['pulse_reasons']))
    with st.expander('D｜今日触发'):
        st.write(str(diagnosis['trigger_reasons']))
        st.caption('触发来自上述诊断日期，不代表今日实时触发。')
    with st.expander('E｜主要矛盾'):
        st.write(diagnosis['main_conflict'])
    with st.expander('F｜复诊条件'):
        st.write(diagnosis['review_conditions'])
