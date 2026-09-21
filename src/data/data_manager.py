"""检查源数据，整理成页面需要的列；不截断全量数据。"""
from src.data.akshare_adapter import fetch_quotes

COLUMNS = {"code": "股票代码", "name": "股票名称", "zxj": "最新价", "zdf": "涨跌幅"}


def load_quotes():
    quotes = fetch_quotes()
    if quotes is None or quotes.empty:
        raise ValueError("数据源未返回行情，请稍后刷新重试。")
    missing = [name for name in COLUMNS if name not in quotes.columns]
    if missing:
        raise ValueError("数据源字段发生变化，缺少：" + "、".join(missing))
    table = quotes.loc[:, list(COLUMNS)].rename(columns=COLUMNS).copy()
    table["股票代码"] = table["股票代码"].astype("string")
    return table
