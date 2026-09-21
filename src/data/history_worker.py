"""单个接口在独立进程运行，让外层能终止超时请求。"""
import sys
import akshare as ak


def main():
    source, code, start, end, output = sys.argv[1:]
    if source == "tencent":
        symbol = ("sh" if code.startswith("6") else "sz") + code
        data = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start,
                                   end_date=end, adjust="hfq", timeout=10)
    else:
        data = ak.stock_zh_a_hist(symbol=code, start_date=start,
                                end_date=end, adjust="hfq", timeout=10)
    data.to_csv(output, index=False)


if __name__ == "__main__":
    main()
