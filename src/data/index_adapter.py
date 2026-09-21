"""免费腾讯指数快照；供Service使用，UI不直接访问数据源。"""
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import requests
import pandas as pd


class TencentIndexAdapter:
    def fetch(self,symbol='sh000300'):
        response=requests.get('https://qt.gtimg.cn/q='+symbol,timeout=(5,10))
        response.raise_for_status(); response.encoding='gbk'
        match=re.search(r'="([^"]*)"',response.text)
        if not match: raise ValueError('指数响应为空')
        parts=match.group(1).split('~')
        if len(parts)<33: raise ValueError('指数响应字段不足')
        stamp=pd.to_datetime(parts[30],format='%Y%m%d%H%M%S',errors='coerce')
        return {'index_code':symbol,'index_name':parts[1],
            'index_price':pd.to_numeric(parts[3],errors='coerce'),
            'index_prev_close':pd.to_numeric(parts[4],errors='coerce'),
            'index_return_intraday':pd.to_numeric(parts[32],errors='coerce')/100,
            'index_quote_time':stamp.isoformat() if pd.notna(stamp) else '',
            'index_source':'腾讯指数快照',
            'index_fetched_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
            'index_status':'LIVE'}
