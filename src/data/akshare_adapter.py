"""数据源适配：这里只负责向 AKShare 要数据。"""
import akshare as ak


def fetch_quotes():
    return ak.stock_zh_a_spot_tx()


# 历史扫描接口与原行情页面并存。脉象引擎只接收标准 DataFrame。
from pathlib import Path
from datetime import datetime, timedelta
import subprocess
import sys
import tempfile
import pandas as pd

STANDARD = ["date", "code", "name", "open", "high", "low", "close",
            "volume", "amount", "turnover_rate", "data_source", "last_update", "trade_date"]


class TencentMarketAdapter:
    """复用AKShare批量行情，用腾讯批量快照补充时间戳及OHLC。"""
    def __init__(self, root):
        self.root = Path(root)

    def fetch(self, codes):
        import requests
        import re
        from zoneinfo import ZoneInfo
        from src.watchlist.repository import exchange
        cache = self.root / 'data/cache'
        cache.mkdir(parents=True,exist_ok=True)
        rank = pd.DataFrame()
        try:
            with tempfile.TemporaryDirectory(dir=cache) as folder:
                output=Path(folder)/'rank.csv'
                p=subprocess.run([sys.executable,'-m','src.data.quote_worker',str(output)],cwd=self.root,
                                 capture_output=True,timeout=40)
                if p.returncode == 0:
                    rank=pd.read_csv(output,dtype={'code':str})
        except (OSError,subprocess.TimeoutExpired):
            pass
        rows=[]
        for start in range(0,len(codes),60):
            symbols=','.join(exchange(code)+code for code in codes[start:start+60])
            response=None
            for attempt in range(2):
                try:
                    response=requests.get('https://qt.gtimg.cn/q='+symbols,timeout=(5,10))
                    response.raise_for_status()
                    break
                except requests.RequestException:
                    response=None
            if response is None:
                continue
            response.encoding='gbk'
            for symbol, content in re.findall(r'v_([a-z]+\d+)="([^"]*)"',response.text):
                parts=content.split('~')
                if len(parts)<50:
                    continue
                def number(i):
                    return pd.to_numeric(parts[i],errors='coerce')
                stamp=pd.to_datetime(parts[30],format='%Y%m%d%H%M%S',errors='coerce')
                code=parts[2]
                row=dict(code=code,name=parts[1],price=number(3),prev_close=number(4),open=number(5),
                    change=number(31),change_pct=number(32),high=number(33),low=number(34),
                    amount=number(37)*10000,turnover_rate=number(38),amplitude=number(43),
                    float_cap=number(44)*1e8,market_cap=number(45)*1e8,pb=number(46),volume_ratio=number(49),
                    volume=number(6)*(1 if code.startswith('688') else 100),
                    trade_date=stamp.strftime('%Y-%m-%d') if pd.notna(stamp) else '',
                    quote_time=stamp.isoformat() if pd.notna(stamp) else '',
                    updated_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
                    data_source='腾讯批量快照 + AKShare/tencent')
                rows.append(row)
        frame=pd.DataFrame(rows)
        if not rank.empty:
            rank['code']=rank.code.str.replace(r'^(sh|sz|bj)','',regex=True)
            extra=rank.rename(columns={'speed':'speed','zdf_y':'ytd'})
            for field in ['speed','ytd','pe_ttm']:
                if field not in extra:
                    extra[field]=float('nan')
            if frame.empty:
                # 排行接口没有行情时间戳，不能猜测交易日。
                frame=rank.rename(columns={'name':'name','zxj':'price','zdf':'change_pct','zd':'change',
                    'hsl':'turnover_rate','lb':'volume_ratio','zf':'amplitude','zsz':'market_cap','ltsz':'float_cap','turnover':'amount'}).copy()
                for col,scale in [('amount',10000),('market_cap',1e8),('float_cap',1e8)]:
                    frame[col]=pd.to_numeric(frame.get(col),errors='coerce')*scale
                frame['volume']=float('nan')
                frame['data_source']='AKShare/tencent（行情日期未提供）'
                frame['updated_at']=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
            frame=frame.drop(columns=['speed','ytd','pe_ttm'],errors='ignore').merge(extra[['code','speed','ytd','pe_ttm']],on='code',how='left')
        return frame[frame.code.isin(codes)] if not frame.empty else frame


def normalize_history(raw, code, name, source, last_update, end):
    if source == "tencent":
        frame = raw.rename(columns={"turnover": "turnover_rate"}).copy()
        # AKShare 腾讯返回小数比例，统一为百分数（1.34 表示 1.34%）。
        if "turnover_rate" in frame:
            frame["turnover_rate"] = pd.to_numeric(frame["turnover_rate"], errors="coerce") * 100
    else:
        frame = raw.rename(columns={"日期": "date", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "成交量": "volume", "成交额": "amount",
            "换手率": "turnover_rate"}).copy()
        if "volume" in frame:
            frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce") * 100
    if "date" not in frame:
        raise ValueError("缺少日期字段")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    frame = frame[frame["date"] <= pd.Timestamp(end)].sort_values("date")
    frame = frame.drop_duplicates("date", keep="last")
    for column in ["open", "high", "low", "close", "volume", "amount", "turnover_rate"]:
        frame[column] = pd.to_numeric(frame.get(column, float("nan")), errors="coerce")
        frame.loc[frame[column] < 0, column] = float("nan")
    if frame.empty or frame[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError("无有效日线或 OHLC 缺失")
    if (frame["low"] <= 0).any() or (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any() or (frame["low"] > frame[["open", "close"]].min(axis=1)).any():
        raise ValueError("OHLC 关系异常")
    frame["code"], frame["name"] = code, name
    frame["data_source"] = f"AKShare/{source}/hfq"
    frame["last_update"] = last_update
    frame["trade_date"] = frame["date"].dt.strftime("%Y-%m-%d")
    return frame[STANDARD].reset_index(drop=True)


class HistoryAdapter:
    def __init__(self, root, settings):
        self.root = Path(root)
        self.cache = self.root / "data/cache/pulse"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.settings = settings

    def get_history(self, stock, end, refresh=True):
        code, name = stock["code"], stock["name"]
        cache_file = self.cache / f"{code}_hfq.csv"
        errors = []
        if refresh:
            start = end - timedelta(days=self.settings["history_calendar_days"])
            for source in ["tencent", "eastmoney"]:
                try:
                    with tempfile.TemporaryDirectory(dir=self.cache) as folder:
                        output = Path(folder) / "response.csv"
                        result = subprocess.run([sys.executable, "-m", "src.data.history_worker",
                            source, code, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), str(output)],
                            cwd=self.root, capture_output=True, timeout=self.settings["max_api_seconds"])
                        if result.returncode:
                            raise RuntimeError("接口进程失败")
                        raw = pd.read_csv(output)
                        frame = normalize_history(raw, code, name, source,
                            datetime.now().astimezone().isoformat(timespec="seconds"), end)
                    if len(frame) < self.settings["min_history"]:
                        raise ValueError(f"历史仅 {len(frame)} 日，不足最低要求")
                    # 不用明显比缓存更旧的数据覆盖最近有效缓存。
                    if cache_file.exists():
                        cached_dates = pd.read_csv(cache_file, usecols=["date"])
                        if pd.to_datetime(cached_dates["date"]).max() > frame["date"].max():
                            raise ValueError("接口返回日期早于已有缓存")
                    temp = cache_file.with_suffix(".tmp")
                    frame.to_csv(temp, index=False)
                    temp.replace(cache_file)
                    return frame, "OK", errors
                except Exception as exc:
                    errors.append(f"{source}: {type(exc).__name__}: {exc}")
        if cache_file.exists():
            try:
                frame = pd.read_csv(cache_file, dtype={"code": str})
                frame["date"] = pd.to_datetime(frame["date"])
                frame = frame[frame["date"] <= pd.Timestamp(end)].sort_values("date")
                if frame.empty or not set(STANDARD).issubset(frame.columns):
                    raise ValueError("缓存为空或格式无效")
                if frame[["open", "high", "low", "close"]].isna().any().any():
                    raise ValueError("缓存 OHLC 缺失")
                return frame.reset_index(drop=True), "DATA_STALE", errors
            except Exception as exc:
                errors.append(f"cache: {type(exc).__name__}")
        return pd.DataFrame(columns=STANDARD), "DATA_MISSING", errors
