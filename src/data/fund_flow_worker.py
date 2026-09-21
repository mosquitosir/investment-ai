"""在限时子进程中请求，资金流失败不能阻塞行情页。"""
import sys
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests
import akshare as ak
from src.watchlist.repository import exchange
from src.data.fund_flow import SOURCE

original_get = requests.get


def bounded_get(*args, **kwargs):
    kwargs['timeout'] = (3, 5)
    return original_get(*args, **kwargs)


def fetch_one(code):
    row = dict(code=code, fund_flow_source=SOURCE,
               fund_flow_fetched_at=pd.Timestamp.now(tz='Asia/Shanghai').isoformat())
    try:
        raw = ak.stock_individual_fund_flow(stock=code, market=exchange(code))
        if raw.empty:
            raise ValueError('空响应')
        raw = raw.sort_values('日期')
        latest = raw.iloc[-1]
        row.update(main_net_inflow_today=latest['主力净流入-净额'],
                   fund_flow_trade_date=str(latest['日期']),
                   fund_flow_error='仅有主力日资金流；未提供全口径净流入和盘中更新时间')
    except Exception as exc:
        row['fund_flow_error'] = type(exc).__name__
        row['failed'] = True
    return row


if __name__ == '__main__':
    requests.get = bounded_get
    codes = sys.argv[2:]
    rows = []
    if codes:
        first = fetch_one(codes[0])
        rows.append(first)
        if first.get('failed'):
            # 源站整体不可达时快速熔断，避免几十次重复代理失败。
            rows.extend(dict(first, code=code) for code in codes[1:])
        else:
            with ThreadPoolExecutor(max_workers=4) as pool:
                rows.extend(pool.map(fetch_one, codes[1:]))
    pd.DataFrame(rows).to_csv(sys.argv[1], index=False)
