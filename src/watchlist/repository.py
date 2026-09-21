"""CSV候诊池；代码始终按字符串处理，更新先写临时文件再替换。"""
from pathlib import Path
import re
import pandas as pd

COLUMNS = ['code','name','industry_id','industry_name','industry_archetype','status','notes','added_date']


def normalize_code(value):
    text = str(value).strip().lower()
    text = re.sub(r'^(sh|sz|bj)', '', text)
    text = re.sub(r'\.(sh|sz|bj)$', '', text)
    if not re.fullmatch(r'\d{6}', text):
        raise ValueError('股票代码须为6位数字，例如002371；CSV代码列请用文本格式。')
    return text


def exchange(code):
    return 'sh' if code.startswith('6') else 'sz' if code.startswith(('0','3')) else 'bj'


class WatchlistRepository:
    def __init__(self, path):
        self.path = Path(path)

    def load(self, active_only=True):
        frame = pd.read_csv(self.path, dtype=str, keep_default_na=False)
        if not set(COLUMNS).issubset(frame.columns):
            raise ValueError('候诊池格式不完整')
        frame['code'] = frame.code.map(normalize_code)
        if frame.code.duplicated().any():
            raise ValueError('候诊池存在重复代码')
        return frame[frame.status.eq('ACTIVE')].copy() if active_only else frame

    def save(self, frame):
        tmp = self.path.with_suffix('.tmp')
        frame[COLUMNS].to_csv(tmp, index=False, encoding='utf-8-sig')
        tmp.replace(self.path)

    def upsert(self, records):
        frame = self.load(False).set_index('code')
        for record in records:
            record = dict(record)
            code = normalize_code(record.pop('code'))
            if not str(record.get('name', '')).strip():
                raise ValueError(f'{code} 未识别名称，请填写确认名称后再添加。')
            if code in frame.index:
                record['added_date'] = frame.loc[code, 'added_date']
            frame.loc[code, [key for key in COLUMNS if key != 'code']] = [record.get(key, '') for key in COLUMNS if key != 'code']
        self.save(frame.reset_index())

    def remove(self, code):
        frame = self.load(False)
        frame.loc[frame.code.eq(normalize_code(code)), 'status'] = 'REMOVED'
        self.save(frame)
