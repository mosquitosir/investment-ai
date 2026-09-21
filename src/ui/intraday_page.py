"""今日脉动页面：摘要表和完整参数详情。"""
import pandas as pd
import streamlit as st

from src.data.market_service import MarketDataService
from src.data.fund_flow import format_flow
from src.intraday.service import IntradayPulseService, monitored_universe, P0, P1, P2, L2


def _fmt_pct(value):
    return '--' if pd.isna(value) else f'{value*100:+.2f}%'


def render_intraday(root, mobile=True):
    watch=monitored_universe(root)
    market=MarketDataService(root)
    pulse=IntradayPulseService(root)
    if 'market_quotes' not in st.session_state:
        st.session_state.market_quotes=market.cached()

    st.markdown('### 资本脉象｜今日脉动')
    st.caption('监控两个观察池去重后的70只股票 · 市场状态研究，不是买卖信号或上涨概率')
    controls=st.columns([3,1])
    search=controls[0].text_input('搜索名称 / 代码',placeholder='源杰 或 688498',key='intraday_search')
    refresh=controls[1].button('刷新并保存快照',type='primary')
    if refresh:
        with st.spinner('正在刷新70只行情、日线基线并保存点时快照……'):
            st.session_state.market_quotes=market.refresh(watch.code.tolist())
            history_result=pulse.refresh_history(watch.code.tolist())
            frame=pulse.calculate(watch,st.session_state.market_quotes,save=True)
        history_ok=sum(x['status']=='LIVE' for x in history_result.values())
        st.info(f'{market.message} 已保存5分钟快照；日线基线更新 {history_ok}/{len(watch)} 只。')
    else:
        frame=pulse.calculate(watch,st.session_state.market_quotes,save=False)

    if search.strip():
        frame=frame[frame.name.str.contains(search.strip(),regex=False,na=False)|frame.code.str.contains(search.strip(),regex=False,na=False)]
    quick=st.radio('快速筛选',['全部','脉变','持续增强','滑','涩','数','浮','资金增强','突破有效','承接减弱','数据不足'],horizontal=True)
    if quick=='脉变': frame=frame[frame.pulse_changed.eq(True)]
    elif quick=='持续增强': frame=frame[frame.continuation_state.eq('STRENGTHENING')]
    elif quick in ['滑','涩','数','浮']: frame=frame[frame.pulse_state.eq(quick)]
    elif quick=='资金增强': frame=frame[frame.incremental_flow_state.eq('STRONG')]
    elif quick=='突破有效': frame=frame[frame.breakout_hold_minutes.ge(pulse.config['breakout_hold_minutes'])]
    elif quick=='承接减弱': frame=frame[frame.selling_pressure_state.isin(['WEAK','NEGATIVE'])]
    elif quick=='数据不足': frame=frame[frame.pulse_state.eq('INSUFFICIENT_DATA')]

    sort_options=['pct_change','volume_ratio_intraday','net_inflow_ratio','price_vs_vwap','max_intraday_drawdown','snapshot_count']
    labels={'pct_change':'涨跌幅','volume_ratio_intraday':'量能（量比）','net_inflow_ratio':'净流入率',
            'price_vs_vwap':'VWAP位置','max_intraday_drawdown':'最大盘中回撤','snapshot_count':'快照数'}
    sort_columns=st.columns([2,1,2])
    sort_by=sort_columns[0].selectbox('排序字段',sort_options,format_func=lambda x:labels[x],key='intraday_sort')
    ascending=sort_columns[1].radio('顺序',['降序','升序'],horizontal=True,key='intraday_order')=='升序'
    frame=frame.sort_values(sort_by,ascending=ascending,na_position='last',kind='stable')

    table=frame[['name','code','industry_name','price','pct_change','stock_excess_return_intraday',
        'volume_ratio_intraday','net_inflow_ratio','price_vs_vwap','incremental_flow_state',
        'selling_pressure_state','price_efficiency_state','continuation_state','pulse_state','data_status']].copy()
    table.columns=['股票','代码','行业','现价','涨跌幅','行业超额','量能','净流入率','VWAP位置',
        '资金持续性','回撤承接','价格效率','延续状态','脉象','行情状态']
    table['延续状态']=table['延续状态'].replace({'STRENGTHENING':'增强','STABLE':'稳定','WEAKENING':'衰减',
        'REVERSING':'转弱','MIXED':'混合','UNKNOWN':'未知','INSUFFICIENT_DATA':'数据不足'})
    table['资金持续性']=table['资金持续性'].replace({'UNKNOWN':'未知','INSUFFICIENT_DATA':'数据不足'})
    table['回撤承接']=table['回撤承接'].replace({'UNKNOWN':'未知','INSUFFICIENT_DATA':'数据不足'})
    table['价格效率']=table['价格效率'].replace({'UNKNOWN':'未知','INSUFFICIENT_DATA':'数据不足'})
    table['脉象']=table['脉象'].replace({'INSUFFICIENT_DATA':'数据不足','UNKNOWN':'未知','MIXED':'混合'})
    styled=table.style.format({'现价':'{:.2f}','涨跌幅':'{:+.2f}%','行业超额':_fmt_pct,
        '量能':'{:.2f}','净流入率':_fmt_pct,'VWAP位置':_fmt_pct},na_rep='--')
    event=st.dataframe(styled,hide_index=True,width='stretch',height=520,on_select='rerun',
        selection_mode='single-row',key='intraday_grid')
    st.caption(f'当前显示 {len(frame)} / {len(watch)} 只。-- 表示缺失，不代表0；快照只在点击刷新时保存，同一5分钟窗口覆盖为最新值。')

    if frame.empty:
        st.info('没有匹配股票。')
        return
    selected=event.selection.rows
    idx=selected[0] if selected and selected[0]<len(frame) else 0
    if mobile:
        code=st.selectbox('查看完整参数',frame.code.tolist(),index=idx,
            format_func=lambda c:f'{frame.set_index("code").loc[c,"name"]} · {c}',key='intraday_detail')
        idx=frame.code.tolist().index(code)
    row=frame.iloc[idx]
    st.subheader(f'{row["name"]} · {row.code}')
    st.caption(f'行情交易日：{row.trade_date or "--"}｜行情时刻：{row.timestamp or "--"}｜已积累快照：{int(row.snapshot_count)}')
    summary=pd.DataFrame([
        ['市场支持',row.market_support_state],['位置',row.position_state],['资金增量',row.incremental_flow_state],
        ['回撤承接',row.selling_pressure_state],['价格效率',row.price_efficiency_state],
        ['延续',row.continuation_state],['脉象',row.pulse_state],
        ['脉变',f'{row.previous_pulse_state} → {row.current_pulse_state}' if row.pulse_changed else '无可确认脉变']
    ],columns=['诊断项','状态'])
    st.dataframe(summary,hide_index=True,width='stretch')
    for title,fields in [('P0参数',P0),('P1参数',P1),('P2参数',P2),('Level-2预留',L2)]:
        with st.expander(title):
            details=[]
            for field in fields:
                value=row.get(field)
                if pd.isna(value): value='--'
                elif isinstance(value,(float,int)):
                    value=f'{value:.6g}'
                else:
                    value=str(value)
                details.append({'字段':field,'值':value})
            st.dataframe(pd.DataFrame(details),hide_index=True,width='stretch')
    st.caption('数据质量：日线 '+str(row.daily_history_status)+'｜分钟 '+str(row.minute_status)+
        '｜行业 '+str(row.industry_status)+'｜资金流 '+str(row.intraday_flow_status)+'｜Level-2 '+str(row.l2_status))
