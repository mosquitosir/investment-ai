"""AKShare全量批量行情（外层进程超时保护）。"""
import sys
from src.data.akshare_adapter import fetch_quotes

if __name__ == '__main__':
    fetch_quotes().to_csv(sys.argv[1], index=False)
