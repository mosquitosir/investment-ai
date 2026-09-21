"""行情适配器协议；UI不依赖具体供应商。"""
from typing import Protocol
import pandas as pd


class MarketAdapter(Protocol):
    def fetch(self, codes: list[str]) -> pd.DataFrame: ...
