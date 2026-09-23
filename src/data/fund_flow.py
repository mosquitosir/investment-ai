"""独立的资金流字段：不把主力口径冒充全口径，不跨日沿用今日值。"""
from pathlib import Path
import subprocess
import sys
import tempfile
import pandas as pd
import numpy as np

FLOW_NUMERIC = ['net_inflow_today', 'main_net_inflow_today', 'net_inflow_ratio']
FLOW_TEXT = ['fund_flow_source', 'fund_flow_update_time', 'fund_flow_trade_date',
             'fund_flow_fetched_at', 'fund_flow_status', 'fund_flow_error',
             'main_fund_flow_status', 'net_inflow_ratio_status', 'fund_data_level']
SOURCE = 'AKShare / 东方财富 / stock_individual_fund_flow（主力口径）'


def normalize_flow(frame, now=None, cached=False):
    d = frame.copy()
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz='Asia/Shanghai')
    today = now.strftime('%Y-%m-%d')
    for col in FLOW_NUMERIC:
        d[col] = pd.to_numeric(d.get(col, np.nan), errors='coerce').replace([np.inf, -np.inf], np.nan) if col in d else np.nan
    for col in FLOW_TEXT:
        if col not in d:
            d[col] = ''
        d[col] = d[col].fillna('')
    current = d.fund_flow_trade_date.eq(today)
    # 旧交易日不保留在名称含“今日”的字段中。
    d.loc[~current, FLOW_NUMERIC] = np.nan
    d['fund_flow_status'] = np.where(d.net_inflow_today.notna(), 'CACHED' if cached else 'LIVE', 'MISSING')
    # 日线资金流没有源站盘中时刻，不标作实时；获取时刻另列。
    d['main_fund_flow_status'] = np.where(d.main_net_inflow_today.notna(), 'CACHED', 'MISSING')
    # 腾讯成交额与东方财富资金流没有同源同快照保证，不计算比率。
    d['net_inflow_ratio'] = np.nan
    d['net_inflow_ratio_status'] = 'UNKNOWN'
    # F0=仅价格/量额，F1=有明确口径的净流入，F2=有逐笔主动买卖或盘口。
    def available(fields):
        present = [field for field in fields if field in d]
        if not present:
            return pd.Series(False, index=d.index)
        return d[present].apply(pd.to_numeric, errors='coerce').notna().any(axis=1)

    has_f2 = available(['active_net_buy', 'aggressive_buy_amount', 'aggressive_sell_amount',
                        'order_book_imbalance'])
    has_f1 = d.net_inflow_today.notna() | d.main_net_inflow_today.notna()
    has_f0 = available(['price', 'amount', 'volume'])
    d['fund_data_level'] = np.select([has_f2, has_f1, has_f0], ['F2', 'F1', 'F0'], default='MISSING')
    return d


class FundFlowAdapter:
    def __init__(self, root):
        self.root = Path(root)

    def fetch(self, codes):
        cache = self.root / 'data/cache'
        cache.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=cache) as folder:
                output = Path(folder) / 'flow.csv'
                result = subprocess.run([sys.executable, '-m', 'src.data.fund_flow_worker', str(output), *codes],
                                        cwd=self.root, capture_output=True, timeout=25)
                if result.returncode:
                    raise RuntimeError('资金流请求进程失败')
                return normalize_flow(pd.read_csv(output, dtype={'code': str}))
        except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError) as exc:
            return normalize_flow(pd.DataFrame({'code': codes, 'fund_flow_source': SOURCE,
                'fund_flow_error': type(exc).__name__,
                'fund_flow_fetched_at': pd.Timestamp.now(tz='Asia/Shanghai').isoformat()}))


def format_flow(value):
    if pd.isna(value):
        return '--'
    if value == 0:
        return '0（基本平衡）'
    scale, unit = (1e8, '亿') if abs(value) >= 1e8 else (1e4, '万') if abs(value) >= 1e4 else (1, '元')
    number = f'{abs(value) / scale:.2f}'.rstrip('0').rstrip('.')
    return ('+' if value > 0 else '-') + number + unit
