"""盘中快照、点时指标和规则状态；缺数据保留NaN及明确状态。"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import numpy as np
import pandas as pd

from src.watchlist.repository import WatchlistRepository
from src.watchlist.growth import load_growth
from src.intraday.history import IntradayHistoryStore
from src.data.index_adapter import TencentIndexAdapter

P0 = ['price','pct_change','amount','turnover','ma5','ma10','ma20','ma60','ma20_slope','ma60_slope',
      'distance_to_ma20','distance_to_ma60','distance_to_20d_high','distance_to_60d_high','open_gap_pct',
      'index_return_intraday','industry_return_intraday','stock_excess_return_intraday','net_inflow_today',
      'net_inflow_ratio','vwap','price_vs_vwap','intraday_high','intraday_low','max_intraday_drawdown']
P1 = ['amount_ratio_20','turnover_ratio_20','vwap_hold_ratio','higher_high_count','higher_low_count',
      'breakout_count','failed_breakout_count','breakout_hold_minutes','continuation_state','pulse_state']
P2 = ['positive_flow_window_ratio','consecutive_positive_flow_windows','flow_acceleration','flow_decay',
      'rally_volume_ratio','pullback_volume_ratio','flow_price_efficiency']
L2 = ['aggressive_buy_amount','aggressive_sell_amount','active_net_buy','active_buy_ratio',
      'ask_consumption_rate','bid_replenishment_rate','order_book_imbalance','large_active_buy_ratio']


def monitored_universe(root):
    root = Path(root)
    capital = WatchlistRepository(root/'data/watchlist.csv').load().copy()
    capital['watchlist_type'] = 'capital_clinic'
    growth = load_growth(root).copy()
    growth['watchlist_type'] = 'growth_inflection'
    columns = ['code','name','industry_name','watchlist_type']
    both = pd.concat([capital[columns],growth[columns]],ignore_index=True)
    grouped=[]
    for code,rows in both.groupby('code',sort=False):
        industries=[x for x in rows.industry_name if x and x!='待诊']
        grouped.append({'code':code,'name':rows.name.iloc[0],
            'industry_name':industries[0] if industries else '待诊',
            'watchlist_type':' + '.join(dict.fromkeys(rows.watchlist_type))})
    return pd.DataFrame(grouped)


def _safe_ratio(numerator, denominator, subtract=False):
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return np.nan
    value = numerator / denominator
    return value - 1 if subtract else value


def calculate_excess_return(stock_return, industry_return):
    if pd.isna(stock_return) or pd.isna(industry_return):
        return np.nan
    return stock_return-industry_return


def detect_pulse_change(previous,current,timestamp=''):
    valid={'沉','浮','迟','数','滑','涩','MIXED'}
    changed=previous in valid and current in valid and previous!=current
    return changed,timestamp if changed else ''


def daily_position_metrics(history, current, cfg):
    result={key:np.nan for key in ['ma5','ma10','ma20','ma60','ma20_slope','ma60_slope',
        'distance_to_ma20','distance_to_ma60','distance_to_20d_high','distance_to_60d_high','rs_5','rs_20']}
    result['open_gap_pct']=_safe_ratio(current.get('open'),current.get('prev_close'),True)
    if history.empty or pd.isna(current.get('price')):
        result['daily_history_status']='MISSING'
        return result
    closes=pd.concat([history.close,pd.Series([current['price']])],ignore_index=True)
    slopes=int(cfg['ma_slope_days'])
    for window in [5,10,20,60]:
        rolling=closes.rolling(window,min_periods=window).mean()
        result[f'ma{window}']=rolling.iloc[-1]
        if window in [20,60] and len(rolling)>slopes and pd.notna(rolling.iloc[-1-slopes]):
            result[f'ma{window}_slope']=_safe_ratio(rolling.iloc[-1],rolling.iloc[-1-slopes],True)
        result[f'distance_to_ma{window}']=_safe_ratio(current['price'],result[f'ma{window}'],True)
    for window in [20,60]:
        peak=history.high.tail(window).max() if len(history)>=window else np.nan
        result[f'distance_to_{window}d_high']=_safe_ratio(current['price'],peak,True)
    result['daily_history_status']='CACHED' if len(history)>=60 else 'PARTIAL'
    return result


def _interval_delta(d, field, minutes):
    if d.empty or pd.isna(d.iloc[-1].get(field)):
        return np.nan
    target=pd.Timestamp(d.iloc[-1].timestamp)-pd.Timedelta(minutes=minutes)
    earlier=d[pd.to_datetime(d.timestamp,errors='coerce')<=target]
    if earlier.empty or pd.isna(earlier.iloc[-1].get(field)):
        return np.nan
    value=d.iloc[-1][field]-earlier.iloc[-1][field]
    return value if value>=0 else np.nan


def intraday_series_metrics(series, current, refs, cfg):
    d=series.sort_values('timestamp').drop_duplicates('snapshot_slot',keep='last').copy()
    result={}
    amount,volume=current.get('amount'),current.get('volume')
    vwap=_safe_ratio(amount,volume)
    low,high=current.get('intraday_low'),current.get('intraday_high')
    if pd.notna(vwap) and pd.notna(low) and pd.notna(high) and not low<=vwap<=high:
        vwap=np.nan
    result.update(vwap=vwap,price_vs_vwap=_safe_ratio(current.get('price'),vwap,True),
        intraday_return=_safe_ratio(current.get('price'),current.get('prev_close'),True),
        distance_to_intraday_high=_safe_ratio(current.get('price'),high,True),
        amount_5m=_interval_delta(d,'amount',5),amount_15m=_interval_delta(d,'amount',15),
        amount_30m=_interval_delta(d,'amount',30))
    prices=pd.to_numeric(d.price,errors='coerce').dropna()
    result['max_intraday_drawdown']=(prices/prices.cummax()-1).min() if len(prices)>=2 else np.nan
    result['higher_high_count']=int((pd.to_numeric(d.intraday_high,errors='coerce').diff()>0).sum()) if len(d)>=2 else np.nan
    result['higher_low_count']=int((pd.to_numeric(d.intraday_low,errors='coerce').diff()>0).sum()) if len(d)>=2 else np.nan
    vwaps=pd.to_numeric(d.vwap,errors='coerce') if 'vwap' in d else pd.Series(dtype=float)
    valid_vwap=d[pd.to_numeric(d.get('vwap'),errors='coerce').notna()] if 'vwap' in d else d.iloc[:0]
    result['vwap_hold_ratio']=(valid_vwap.price>valid_vwap.vwap).mean() if len(valid_vwap)>=2 else np.nan
    result['vwap_slope']=_safe_ratio(vwaps.iloc[-1],vwaps.iloc[max(0,len(vwaps)-3)],True) if len(vwaps)>=2 else np.nan

    reference=max([x for x in refs if pd.notna(x)],default=np.nan)
    result.update(breakout_count=np.nan,failed_breakout_count=np.nan,breakout_hold_minutes=np.nan)
    if pd.notna(reference) and len(prices)>=2:
        above=pd.to_numeric(d.price,errors='coerce')>reference
        result['breakout_count']=int((above & ~above.shift(1,fill_value=False)).sum())
        result['failed_breakout_count']=int((~above & above.shift(1,fill_value=False)).sum())
        if bool(above.iloc[-1]):
            starts=d.loc[above & ~above.shift(1,fill_value=False),'timestamp']
            result['breakout_hold_minutes']=(pd.Timestamp(d.timestamp.iloc[-1])-pd.Timestamp(starts.iloc[-1])).total_seconds()/60

    increments=pd.to_numeric(d.amount,errors='coerce').diff()
    returns=pd.to_numeric(d.price,errors='coerce').pct_change()
    baseline=increments.tail(20).mean() if (increments.tail(20)>=0).any() else np.nan
    rally=(returns>cfg['rally_return_threshold']) & (d.price>=d.price.rolling(3,min_periods=1).max())
    pullback=returns<0
    result['rally_volume_ratio']=_safe_ratio(increments[rally].mean(),baseline)
    result['pullback_volume_ratio']=_safe_ratio(increments[pullback].mean(),baseline)
    result['snapshot_count']=len(d)
    return result


def derive_states(row,cfg):
    enough=row.get('snapshot_count',0)>=cfg['min_snapshots_for_state']
    if pd.isna(row.get('industry_return_intraday')):
        market='INSUFFICIENT_DATA'
    elif row.get('stock_excess_return_intraday')>0 and row.get('industry_return_intraday')>0:
        market='POSITIVE'
    elif row.get('stock_excess_return_intraday')<0 and row.get('industry_return_intraday')<0:
        market='NEGATIVE'
    else: market='MIXED'
    if pd.isna(row.get('ma20')) or pd.isna(row.get('ma60')):
        position='INSUFFICIENT_DATA'
    elif row.get('price')>row.get('ma20')>row.get('ma60') and row.get('ma20_slope')>0:
        position='STRONG'
    elif row.get('price')<row.get('ma20') and row.get('ma20_slope')<0:
        position='WEAK'
    else: position='NEUTRAL'
    if not enough or pd.isna(row.get('vwap_hold_ratio')) or pd.isna(row.get('max_intraday_drawdown')):
        continuation='INSUFFICIENT_DATA'
    elif row.get('price_vs_vwap')>0 and row.get('vwap_hold_ratio')>=cfg['vwap_hold_strong'] and row.get('max_intraday_drawdown')>=cfg['shallow_drawdown']:
        continuation='STRENGTHENING'
    elif row.get('price_vs_vwap')<0 and row.get('vwap_hold_ratio')<cfg['vwap_hold_weak'] and row.get('max_intraday_drawdown')<=cfg['weak_drawdown']:
        continuation='REVERSING'
    elif row.get('price_vs_vwap')<0 or row.get('max_intraday_drawdown')<cfg['shallow_drawdown']:
        continuation='WEAKENING'
    else: continuation='STABLE'

    pulse='INSUFFICIENT_DATA'
    if enough:
        if pd.notna(row.get('failed_breakout_count')) and row.get('failed_breakout_count')>0 and row.get('price_vs_vwap')<0:
            pulse='涩'
        elif abs(row.get('pct_change'))>=cfg['strong_change_pct'] and row.get('turnover')>=cfg['high_turnover_pct'] and row.get('volume_ratio_intraday')>=cfg['active_volume_ratio']:
            pulse='数'
        elif continuation=='STRENGTHENING' and row.get('volume_ratio_intraday')>=1:
            pulse='滑'
        elif row.get('volume_ratio_intraday')<cfg['quiet_volume_ratio'] and abs(row.get('pct_change'))<1:
            pulse='迟'
        elif continuation in ['WEAKENING','REVERSING'] and row.get('pct_change')>0:
            pulse='浮'
        elif row.get('volume_ratio_intraday')<1 and position in ['NEUTRAL','STRONG']:
            pulse='沉'
        else: pulse='MIXED'
    return dict(market_support_state=market,position_state=position,
        incremental_flow_state='UNKNOWN',selling_pressure_state='INSUFFICIENT_DATA',
        price_efficiency_state='UNKNOWN',continuation_state=continuation,pulse_state=pulse)


class IntradayPulseService:
    def __init__(self,root,index_adapter=None):
        self.root=Path(root)
        self.config=json.loads((self.root/'config/intraday_pulse.yaml').read_text(encoding='utf-8'))
        self.snapshot_dir=self.root/'data/intraday_snapshots'
        self.snapshot_dir.mkdir(parents=True,exist_ok=True)
        self.history=IntradayHistoryStore(root,self.config)
        self.index_adapter=index_adapter or TencentIndexAdapter()
        self.index_cache=self.root/'data/cache/intraday_index.csv'

    def refresh_history(self,codes):
        return self.history.refresh(codes)

    def index_quote(self,refresh=False):
        if refresh:
            try:
                row=self.index_adapter.fetch(self.config['benchmark_index'])
                temp=self.index_cache.with_suffix('.tmp')
                pd.DataFrame([row]).to_csv(temp,index=False,encoding='utf-8-sig')
                temp.replace(self.index_cache)
                return row
            except Exception:
                pass
        try:
            row=pd.read_csv(self.index_cache).iloc[-1].to_dict()
            row['index_status']='CACHED'
            return row
        except (OSError,ValueError,IndexError):
            return {'index_return_intraday':np.nan,'index_status':'MISSING','index_source':'','index_quote_time':''}

    def _load_day(self,trade_date):
        path=self.snapshot_dir/f'{trade_date}.csv'
        try:
            return pd.read_csv(path,dtype={'code':str})
        except (OSError,ValueError):
            return pd.DataFrame()

    def calculate(self,watch,quotes,save=False):
        selected=quotes.drop(columns=['name'],errors='ignore')
        current=watch.merge(selected,on='code',how='left')
        now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
        rows=[]
        index=self.index_quote(refresh=save)
        for _,source in current.iterrows():
            row=source.to_dict()
            for field in ['price','change_pct','amount','turnover_rate','volume','volume_ratio','high','low',
                          'open','prev_close','net_inflow_today','main_net_inflow_today']:
                if field not in row:
                    row[field]=np.nan
            for field in ['trade_date','quote_time','updated_at','data_source','data_status']:
                if field not in row or pd.isna(row[field]):
                    row[field]=''
            row.update(pct_change=row.get('change_pct'),turnover=row.get('turnover_rate'),
                intraday_high=row.get('high'),intraday_low=row.get('low'),captured_at=now)
            stamp=pd.to_datetime(row.get('quote_time'),errors='coerce')
            if pd.isna(stamp): stamp=pd.to_datetime(row.get('updated_at'),errors='coerce')
            row['timestamp']=stamp.isoformat() if pd.notna(stamp) else ''
            row['snapshot_slot']=stamp.floor(f"{self.config['snapshot_minutes']}min").isoformat() if pd.notna(stamp) else ''
            trade_date=str(row.get('trade_date') or '')
            history=self.history.load(row['code'],before_date=trade_date or None)
            row.update(daily_position_metrics(history,row,self.config))
            row.update(index_return_intraday=index.get('index_return_intraday'),industry_return_intraday=np.nan,industry_breadth=np.nan,
                industry_amount_ratio=np.nan,stock_excess_return_intraday=np.nan,
                amount_ratio_20=np.nan,turnover_ratio_20=np.nan,
                volume_ratio_intraday=row.get('volume_ratio'),net_inflow_ratio=np.nan,
                net_inflow_3d=np.nan,net_inflow_5d=np.nan,
                minute_status='PARTIAL',industry_status='MISSING',index_status=index.get('index_status','MISSING'),
                index_source=index.get('index_source',''),index_quote_time=index.get('index_quote_time',''),
                amount_ratio_status='PARTIAL',l2_status='MISSING_L2',intraday_flow_status='MISSING_INTRADAY_FLOW')
            for field in P2:
                row[field]=np.nan
            for field in L2:
                row[field]=np.nan
            previous=self._load_day(trade_date) if trade_date else pd.DataFrame()
            own=previous[previous.code.eq(row['code'])].copy() if not previous.empty else pd.DataFrame()
            ephemeral=pd.DataFrame([row])
            if not own.empty and row['snapshot_slot']:
                own=own[~own.snapshot_slot.eq(row['snapshot_slot'])]
            series=pd.concat([own,ephemeral],ignore_index=True)
            refs=[history.high.tail(20).max() if len(history)>=20 else np.nan,
                  history.high.tail(60).max() if len(history)>=60 else np.nan,
                  history.high.iloc[-1] if len(history) else np.nan]
            series.loc[series.index[-1],'vwap']=_safe_ratio(row.get('amount'),row.get('volume'))
            row.update(intraday_series_metrics(series,row,refs,self.config))
            row['return']=row.get('intraday_return')
            row['net_inflow']=row.get('net_inflow_today')
            row['industry_return']=row.get('industry_return_intraday')
            row['stock_excess_return']=row.get('stock_excess_return_intraday')
            row['amount_ratio']=row.get('amount_ratio_20')
            state_input=pd.Series(row)
            row.update(derive_states(state_input,self.config))
            previous_pulse=own.sort_values('timestamp').iloc[-1].get('pulse_state','UNKNOWN') if not own.empty else 'UNKNOWN'
            current_pulse=row['pulse_state']
            changed,change_time=detect_pulse_change(previous_pulse,current_pulse,row['timestamp'])
            row.update(previous_pulse_state=previous_pulse,current_pulse_state=current_pulse,
                pulse_changed=changed,pulse_change_time=change_time,
                return_to_close=np.nan,excess_return_to_close=np.nan,return_next_1d=np.nan,
                return_next_3d=np.nan,max_return_to_close=np.nan,max_drawdown_to_close=np.nan)
            rows.append(row)
        result=pd.DataFrame(rows)
        if save:
            self.save(result)
        return result

    def save(self,result):
        valid=result[result.timestamp.astype(str).ne('') & result.trade_date.astype(str).ne('')].copy()
        for trade_date,group in valid.groupby('trade_date'):
            path=self.snapshot_dir/f'{trade_date}.csv'
            old=self._load_day(trade_date)
            combined=pd.concat([old,group],ignore_index=True)
            combined=combined.drop_duplicates(['code','snapshot_slot'],keep='last').sort_values(['timestamp','code'])
            temp=path.with_suffix('.tmp')
            combined.to_csv(temp,index=False,encoding='utf-8-sig')
            temp.replace(path)
