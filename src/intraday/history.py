"""日线基线缓存；未复权价格才能和当前未复权报价比较。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
import pandas as pd


class IntradayHistoryStore:
    def __init__(self, root, config):
        self.root = Path(root)
        self.path = self.root / 'data/cache/intraday_daily'
        self.path.mkdir(parents=True, exist_ok=True)
        self.config = config

    def load(self, code, before_date=None):
        path = self.path / f'{code}.csv'
        try:
            d = pd.read_csv(path)
            d['date'] = pd.to_datetime(d.date, errors='coerce')
            for col in ['open','high','low','close','volume','amount','turnover_rate']:
                d[col] = pd.to_numeric(d.get(col), errors='coerce')
            d = d.dropna(subset=['date','close']).sort_values('date').drop_duplicates('date',keep='last')
            if before_date:
                d = d[d.date < pd.Timestamp(before_date)]
            return d.reset_index(drop=True)
        except (OSError, ValueError, KeyError):
            return pd.DataFrame()

    def _fetch_one(self, code, end):
        start = end - timedelta(days=int(self.config['history_days']) * 2)
        try:
            with tempfile.TemporaryDirectory(dir=self.path) as folder:
                output = Path(folder) / 'history.csv'
                result = subprocess.run([sys.executable,'-m','src.intraday.history_worker',code,
                    start.strftime('%Y%m%d'),end.strftime('%Y%m%d'),str(output)],cwd=self.root,
                    capture_output=True,timeout=self.config['history_timeout_seconds'])
                if result.returncode:
                    raise RuntimeError('history worker failed')
                raw = pd.read_csv(output)
            raw = raw.rename(columns={'turnover':'turnover_rate'})
            raw['date'] = pd.to_datetime(raw.date,errors='coerce')
            raw = raw.dropna(subset=['date','close']).sort_values('date').drop_duplicates('date',keep='last')
            target = self.path / f'{code}.csv'
            temp = target.with_suffix('.tmp')
            raw.to_csv(temp,index=False,encoding='utf-8-sig')
            temp.replace(target)
            return code, 'LIVE', len(raw)
        except Exception as exc:
            return code, 'CACHED' if not self.load(code).empty else 'MISSING', type(exc).__name__

    def refresh(self, codes, end=None):
        end = end or date.today()
        results = {}
        with ThreadPoolExecutor(max_workers=int(self.config['history_workers'])) as pool:
            futures = [pool.submit(self._fetch_one,code,end) for code in codes]
            for future in as_completed(futures):
                code,status,detail = future.result()
                results[code] = {'status':status,'detail':detail}
        return results
