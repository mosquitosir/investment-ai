"""下载未复权日线，供盘中MA和前高基线使用。"""
import sys
import akshare as ak


if __name__ == '__main__':
    code, start, end, output = sys.argv[1:]
    symbol = ('sh' if code.startswith('6') else 'sz') + code
    frame = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start, end_date=end,
                                  adjust='', timeout=10)
    frame.to_csv(output, index=False)
