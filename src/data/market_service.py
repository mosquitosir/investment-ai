"""标准数字字段、缓存、候诊池左连接、筛选排序。"""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import numpy as np
from src.data.fund_flow import FundFlowAdapter, normalize_flow

NUMERIC = ['price','change_pct','change','speed','volume_ratio','turnover_rate','volume',
           'amount','market_cap','float_cap','amplitude','high','low','open','prev_close','ytd','pe_ttm','pb']
LABELS = dict(zip(NUMERIC, ['当前价','涨跌幅 %','涨跌额','涨速 %','量比','换手率 %','成交量（股）',
    '成交额（元）','总市值（元）','流通市值（元）','振幅 %','最高价','最低价','今开','昨收','YTD %','PE-TTM','PB']))
NUMERIC.insert(2, 'net_inflow_today')
LABELS['net_inflow_today'] = '今日净流入'


def standardize(frame):
    d = frame.copy()
    if 'code' not in d:
        return pd.DataFrame(columns=['code',*NUMERIC,'trade_date','quote_time','updated_at','data_source','data_status','missing_fields'])
    d['code'] = d.code.astype(str).str.replace(r'^(sh|sz|bj)', '', regex=True).str.zfill(6)
    d = d[d.code.str.fullmatch(r'\d{6}')].drop_duplicates('code', keep='last')
    for col in NUMERIC:
        d[col] = pd.to_numeric(d.get(col, np.nan), errors='coerce')
        d[col] = d[col].replace([np.inf,-np.inf],np.nan)
    for col in ['price','volume','amount','market_cap','float_cap','volume_ratio','turnover_rate']:
        d.loc[d[col] < 0, col] = np.nan
    d.loc[d.price.eq(0), 'price'] = np.nan
    for col in ['trade_date','quote_time','updated_at','data_source']:
        if col not in d:
            d[col] = ''
        d[col] = d[col].fillna('')
    d['missing_fields'] = d[NUMERIC].apply(lambda r: ','.join(r.index[r.isna()]),axis=1)
    return d


class MarketDataService:
    def __init__(self, root, adapter=None, flow_adapter=None):
        self.root = Path(root)
        self.path = self.root / 'data/cache/latest_quotes.csv'
        if adapter is None:
            from src.data.akshare_adapter import TencentMarketAdapter
            adapter = TencentMarketAdapter(root)
        self.adapter = adapter
        self.flow_adapter = flow_adapter or FundFlowAdapter(root)
        self.message = ''

    def identify(self, codes):
        """名称识别也通过服务层，不让界面依赖数据供应商。"""
        try:
            quotes = self.adapter.fetch(codes)
            return dict(zip(quotes.code,quotes.name)) if not quotes.empty and 'name' in quotes else {}
        except Exception:
            return {}

    def cached(self):
        try:
            d = standardize(pd.read_csv(self.path,dtype={'code':str}))
            now = pd.Timestamp.now(tz='Asia/Shanghai')
            times = pd.to_datetime(d.updated_at,utc=True,errors='coerce')
            d['data_status'] = np.where((now - times).dt.total_seconds() <= 1800,'CACHED','STALE')
            d.loc[d.price.isna(),'data_status'] = 'MISSING'
            return normalize_flow(d, cached=True)
        except (OSError,ValueError,KeyError):
            return standardize(pd.DataFrame())

    def refresh(self, codes):
        old = self.cached()
        # 资金流独立刷新；即使报价接口失败，也不能把旧资金流当成本次成功。
        try:
            flows = self.flow_adapter.fetch(codes)
        except Exception as exc:
            flows = normalize_flow(pd.DataFrame({'code': codes, 'fund_flow_error': type(exc).__name__}))
        try:
            fresh = standardize(self.adapter.fetch(codes))
            if fresh.empty or fresh.price.notna().sum() == 0:
                raise ValueError('无可用报价')
            fresh['data_status'] = np.where(fresh.price.notna(),'LIVE','MISSING')
            # 缺失整只股票时保留该股最近缓存，其他股票照常刷新。
            valid = fresh[fresh.price.notna()]
            fallback = old[~old.code.isin(valid.code)]
            combined = pd.concat([valid,fallback,fresh[~fresh.code.isin(valid.code) & ~fresh.code.isin(fallback.code)]],ignore_index=True)
            combined = self.attach_flow(combined, flows)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix('.tmp')
            combined.to_csv(tmp,index=False,encoding='utf-8-sig')
            tmp.replace(self.path)
            self.message = '行情已更新；LIVE表示本次从源站获取，不代表交易时段。'
            return combined
        except Exception:
            self.message = '实时行情暂时不可用，当前显示最近缓存；无缓存的股票显示 --。'
            fallback = self.attach_flow(old, flows)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix('.tmp')
                fallback.to_csv(tmp, index=False, encoding='utf-8-sig')
                tmp.replace(self.path)
            except OSError:
                self.message += ' 本次缓存写入失败。'
            return fallback

    @staticmethod
    def attach_flow(quotes, flows):
        fields = [c for c in flows.columns if c != 'code']
        # 只替换本次请求股票的资金流，保留另一个观察池的缓存。
        untouched = quotes[~quotes.code.isin(flows.code)]
        requested = quotes[quotes.code.isin(flows.code)].drop(columns=fields, errors='ignore')
        requested = requested.merge(flows, on='code', how='outer')
        return normalize_flow(pd.concat([untouched, requested], ignore_index=True))

    def for_watchlist(self, watchlist, quotes):
        selected = quotes.drop(columns=['name'],errors='ignore')
        out = watchlist.merge(selected,on='code',how='left')
        for col in NUMERIC:
            out[col] = pd.to_numeric(out.get(col,np.nan),errors='coerce')
        out['data_status'] = out.get('data_status',pd.Series(index=out.index,dtype=str)).fillna('MISSING')
        if 'updated_at' in out:
            age = pd.Timestamp.now(tz='Asia/Shanghai') - pd.to_datetime(out.updated_at,utc=True,errors='coerce')
            out.loc[age.dt.total_seconds().gt(1800) & out.price.notna(),'data_status'] = 'STALE'
        out['missing_fields'] = out[NUMERIC].apply(lambda r: ','.join(r.index[r.isna()]),axis=1)
        out['field_status'] = np.where(out.missing_fields.eq(''),'OK','DATA_MISSING')
        return normalize_flow(out, cached=True)


def filter_quotes(frame, industry='全部', search='', active=False, threshold=1.5):
    d=frame.copy()
    if industry != '全部':
        d=d[d.industry_name.eq(industry)]
    query=search.strip()
    if query:
        d=d[d.name.str.contains(query,regex=False,na=False)|d.code.str.contains(query,regex=False,na=False)]
    if active:
        d=d[d.volume_ratio.ge(threshold)]
    return d


def sort_quotes(frame, column, ascending=False):
    return frame.sort_values(column,ascending=ascending,na_position='last',kind='stable')
