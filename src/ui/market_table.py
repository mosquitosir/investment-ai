"""50股候诊台：纯数字行情表与模型诊断分开。"""
from pathlib import Path
from datetime import date
import json
import io
import re
import os
import pandas as pd
import streamlit as st

from src.watchlist.repository import WatchlistRepository,normalize_code,exchange
from src.data.market_service import MarketDataService,NUMERIC,LABELS,filter_quotes,sort_quotes
from src.diagnosis.service import load_diagnoses
from src.ui.diagnosis_panel import render_diagnosis
from src.watchlist.growth import load_growth, filter_growth, render_growth_detail
from src.data.fund_flow import format_flow
from src.ui.intraday_page import render_intraday

ROOT=Path(__file__).resolve().parents[2]


def manage_stocks(repo, settings, quotes):
    st.subheader('候诊池管理')
    industries={r['industry_name']:r for r in settings['industries']}
    current=repo.load()
    with st.expander('＋ 添加股票 / 批量导入'):
        text=st.text_area('股票代码（每行一只，也可以用逗号分隔）',key='import_codes')
        upload=st.file_uploader('或上传CSV（code必需，name和notes可选；行业在下方确认）',type='csv')
        industry=st.selectbox('确认行业',list(industries),key='new_industry')
        manual_name=st.text_input('未识别时填写名称（单只添加）')
        notes=st.text_input('备注',key='new_notes')
        if st.button('识别并预览'):
            try:
                incoming=pd.read_csv(upload,dtype=str,keep_default_na=False) if upload else pd.DataFrame({'code':[x for x in re.split(r'[\s,，;；]+',text.strip()) if x]})
                if 'code' not in incoming or incoming.empty:
                    raise ValueError('请先输入代码或上传含code列的CSV。')
                incoming['code']=incoming.code.map(normalize_code)
                names={**dict(zip(current.code,current.name)),**(dict(zip(quotes.code,quotes.name)) if 'name' in quotes else {})}
                unknown=[c for c in incoming.code if c not in names]
                if unknown:
                    with st.spinner('批量识别股票名称……'):
                        names.update(MarketDataService(ROOT).identify(unknown))
                records=[]
                for _,r in incoming.drop_duplicates('code').iterrows():
                    name=r.get('name','') or names.get(r.code,'') or (manual_name if len(incoming)==1 else '')
                    records.append(dict(code=r.code,name=name,**industries[industry],status='ACTIVE',
                        notes=r.get('notes','') or notes,added_date=str(date.today())))
                st.session_state.import_preview=records
            except Exception as exc:
                st.error(str(exc))
        if st.session_state.get('import_preview'):
            st.dataframe(pd.DataFrame(st.session_state.import_preview),hide_index=True)
            if st.button('确认加入候诊池'):
                try:
                    repo.upsert(st.session_state.import_preview)
                    del st.session_state.import_preview
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    with st.expander('修改行业、备注 / 移出股票'):
        if current.empty:
            st.info('候诊池为空，可在上方添加。')
            return
        code=st.selectbox('选择股票',current.code.tolist(),format_func=lambda c:f"{current.set_index('code').loc[c,'name']} · {c}")
        record=current.set_index('code').loc[code].to_dict()
        selected=st.selectbox('调整行业',list(industries),index=list(industries).index(record['industry_name']) if record['industry_name'] in industries else 0)
        note=st.text_input('研究备注',record['notes'])
        if st.button('保存修改'):
            repo.upsert([dict(record,code=code,**industries[selected],notes=note)])
            st.rerun()
        if st.button('移出候诊池',type='secondary'):
            repo.remove(code)
            st.rerun()


def render_market():
    settings=json.loads((ROOT/'config/settings.yaml').read_text(encoding='utf-8'))
    repo=WatchlistRepository(ROOT/'data/watchlist.csv')
    pool=st.radio('观察池',['50股资本候诊','高成长跃迁20股','今日脉动'],horizontal=True)
    mobile=st.toggle('手机简洁布局',value=True,help='精简表格，诊断显示在下方；关闭可查看完整桌面表格。')
    read_only=os.environ.get('INVESTMENT_READ_ONLY')=='1'
    if pool=='今日脉动':
        render_intraday(ROOT,mobile)
        return
    growth=pool=='高成长跃迁20股'
    watch=load_growth(ROOT) if growth else repo.load()
    service=MarketDataService(ROOT)
    if 'market_quotes' not in st.session_state:
        st.session_state.market_quotes=service.cached()
    st.markdown('### 资本脉象｜'+pool)
    st.caption('研究候诊对象，不是投资推荐 · 行情事实与模型判断分开呈现')
    st.sidebar.title('行业候诊池')
    counts=watch.groupby('industry_name').size().to_dict()
    names=['全部']+list(dict.fromkeys(([] if growth else [r['industry_name'] for r in settings['industries']])+watch.industry_name.tolist()))
    industry=st.sidebar.radio('行业',names,format_func=lambda n:f"{n}  {len(watch) if n=='全部' else counts.get(n,0)}")
    section=st.sidebar.radio('工作区',['候诊台'] if read_only else ['候诊台','股票管理','项目文档'])
    if section=='项目文档':
        paths={'说明':'README.md','开发日志':'PROJECT_LOG.md','计划':'ROADMAP.md'}
        which=st.selectbox('文档',list(paths))
        st.markdown((ROOT/paths[which]).read_text(encoding='utf-8-sig'))
        return
    if section=='股票管理':
        if growth:
            st.info('成长观察字段保存在 data/growth_inflection_watchlist.csv；本页展示名单，原50股管理保持独立。')
            st.dataframe(watch,hide_index=True)
            return
        manage_stocks(repo,settings,st.session_state.market_quotes)
        return
    top=st.columns([2,3,1])
    mode=top[0].radio('视图',['行情','诊断'],horizontal=True)
    search=top[1].text_input('搜索名称 / 代码',placeholder='中微 或 688012')
    refresh=top[2].button('刷新行情',type='primary')
    if refresh:
        with st.spinner('正在批量更新候诊池行情……'):
            st.session_state.market_quotes=service.refresh(watch.code.tolist())
        st.info(service.message)
    quotes=st.session_state.market_quotes
    if quotes.empty:
        st.info('暂无行情缓存，请点击“刷新行情”。股票列表仍可正常查看。')
    merged=service.for_watchlist(watch,quotes)
    if 'trade_date' in merged:
        dates=sorted(set(merged.trade_date.dropna())-{''})
        updated=merged.updated_at.dropna().max() if merged.updated_at.notna().any() else '--'
        sources=' / '.join(merged.data_source.dropna().unique()) or '--'
        st.caption(f"行情日期：{'、'.join(dates) or '未提供'} ｜ 最后获取：{updated} ｜ {sources}")
    st.caption('LIVE＝本次源站快照；CACHED＝近期缓存；STALE＝较早缓存；MISSING＝无报价。休市时显示最近交易报价。')
    successes=int(merged.net_inflow_today.notna().sum())
    flow_sources=' / '.join(x for x in merged.fund_flow_source.unique() if x) or '未取得'
    flow_times=' / '.join(x for x in merged.fund_flow_update_time.unique() if x) or '--（源站未提供）'
    st.caption(f'今日净流入：{successes}/{len(watch)} 只｜来源：{flow_sources}｜数据更新时间：{flow_times}')
    if not successes:
        st.caption('今日净流入当前缺少可靠数据源；-- / MISSING 不表示0。主力净流入单独保存，不冒充全口径资金流；净流入率 UNKNOWN。')
    stage=st.radio('成长阶段',['全部20','L2验证','L3小批量','L4放量','L5兑现','今日有变化','待复诊'],horizontal=True) if growth else None
    quick=st.radio('快捷筛选',['全部','今日活跃','脉变','舆情异常','风险'],horizontal=True)
    diagnoses=load_diagnoses(ROOT,watch.code.tolist())
    filtered=filter_quotes(merged,industry,search,quick=='今日活跃',settings['active_volume_ratio'])
    if growth:
        filtered=filter_growth(filtered,stage)
    if quick=='今日活跃':
        st.caption(f"客观规则：量比 ≥ {settings['active_volume_ratio']}；量比缺失不入选。")
    if quick in ['脉变','舆情异常','风险']:
        st.info('暂无可靠的当日数据，功能待接入。历史脉象可在诊断详情中查看。')
        filtered=filtered.iloc[:0]
    sort_cols=st.columns([2,1,3])
    sort_by=sort_cols[0].selectbox('排序字段',NUMERIC,format_func=lambda c:LABELS[c],index=1)
    ascending=sort_cols[1].radio('顺序',['降序','升序'],horizontal=True)=='升序'
    filtered=sort_quotes(filtered,sort_by,ascending)
    left,right=(st.container(),st.container()) if mobile else st.columns([3,1])
    with left:
        st.caption(f'当前显示 {len(filtered)} / {len(watch)} 只 · 可点击数字表头排序，点击行打开右侧诊断。缺失显示 --。')
        if mode=='行情':
            extra=['growth_theme','current_stage','stage_changed','key_evidence','next_validation'] if growth else []
            table=filtered[['name','code','industry_name',*NUMERIC,*extra,'data_status','fund_flow_status','fund_flow_source','fund_flow_update_time']].copy()
            if mobile:
                table=table[['name','code','industry_name','price','change_pct','net_inflow_today','volume_ratio','turnover_rate','amount','market_cap','data_status']]
            # 使用数值单位缩放，保持排序为数值排序，而不是字符串排序。
            money_config={}
            for key in ['amount','market_cap','float_cap']:
                if key not in table:
                    continue
                maximum=table[key].max()
                scale,unit=(1e4,'万') if key=='amount' and pd.notna(maximum) and maximum<1e8 else (1e12,'万亿') if key!='amount' and pd.notna(maximum) and maximum>=1e12 else (1e8,'亿')
                table[key]=table[key]/scale
                money_config[key]=st.column_config.NumberColumn(LABELS[key].replace('（元）',f'（{unit}）'),format='%.2f')
            config={col:st.column_config.NumberColumn(LABELS[col],format='%.2f') for col in NUMERIC}
            config.update(money_config)
            # 不配置数字 format 覆盖 Styler：保留每格万/亿显示和底层数值排序。
            config['net_inflow_today']=st.column_config.NumberColumn('今日净流入',help='未确认全口径来源时显示--；主力口径单独保存，不混用。')
            config.update(growth_theme='成长主题',current_stage='当前阶段',stage_changed='阶段变化',key_evidence='关键证据',next_validation='下一验证点',fund_flow_status='资金流状态',fund_flow_source='资金流来源',fund_flow_update_time='资金流更新时间')
            config.update(name=st.column_config.TextColumn('股票名称',pinned=True),code=st.column_config.TextColumn('代码'),industry_name='行业',data_status='数据状态')
            styled=table.style.format({'net_inflow_today':format_flow},na_rep='--').map(lambda v:'color: #c43d3d' if pd.notna(v) and v>0 else 'color: #178456' if pd.notna(v) and v<0 else '',subset=[c for c in ['change_pct','change','net_inflow_today'] if c in table])
            event=st.dataframe(styled,column_config=config,hide_index=True,width='stretch',height=620,
                on_select='rerun',selection_mode='single-row',key='market_grid')
        elif growth:
            cols=['name','code','industry_name','growth_theme','current_stage','stage_changed','key_evidence','next_validation','daily_trigger','risk_note','last_review_date']
            table=filtered[cols].copy().replace('UNKNOWN','待诊')
            event=st.dataframe(table,column_config=dict(zip(cols,['股票','代码','行业','成长主题','当前阶段','阶段变化','关键证据','下一验证点','今日触发','风险检查','复诊日期'])),hide_index=True,width='stretch',height=620,on_select='rerun',selection_mode='single-row',key='growth_diagnosis_grid')
        else:
            table=filtered[['code','name','industry_name']].merge(diagnoses,on='code',how='left')
            cols=['name','code','industry_name','body_state','industry_state','position_state','chip_state','sentiment_state','current_pulse','pulse_changed','trigger_reasons','diagnosis_date']
            event=st.dataframe(table[cols],column_config=dict(zip(cols,['股票','代码','行业','体','势','位','筹','情','脉','脉变','触发','诊断日期'])),hide_index=True,width='stretch',height=620,on_select='rerun',selection_mode='single-row',key='diagnosis_grid')
        st.download_button('导出当前行情CSV',filtered.to_csv(index=False).encode('utf-8-sig'),'watchlist_quotes.csv','text/csv')
    with right:
        if filtered.empty:
            st.info('没有匹配股票。')
        else:
            selected=event.selection.rows
            idx=selected[0] if selected and selected[0]<len(filtered) else 0
            if mobile:
                code=st.selectbox('查看股票详情',filtered.code.tolist(),index=idx,format_func=lambda c:f'{filtered.set_index("code").loc[c,"name"]} · {c}',key=f'detail_{pool}')
                idx=filtered.code.tolist().index(code)
            row=filtered.iloc[idx]
            if growth:
                render_growth_detail(row)
            else:
                diagnosis=diagnoses.set_index('code').loc[row.code]
                render_diagnosis(row,diagnosis)
            with st.expander('资金流来源与状态'):
                st.write('今日净流入：'+format_flow(row.net_inflow_today))
                st.write('主力净流入（独立口径）：'+format_flow(row.main_net_inflow_today))
                st.write('净流入率：UNKNOWN（尚无兼容分母）')
                for key,label in [('fund_flow_source','来源'),('fund_flow_trade_date','资金流日期'),('fund_flow_update_time','源站更新时间'),('fund_flow_fetched_at','请求时间'),('fund_flow_status','净流入状态'),('main_fund_flow_status','主力资金流状态'),('fund_flow_error','缺口/请求结果')]:
                    st.write(f'{label}：{row[key] or "--"}')
