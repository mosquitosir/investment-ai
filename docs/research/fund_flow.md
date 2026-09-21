# 资金流接入实际状态
检查日期：2026-09-21。

调用链：src/ui/market_table.py:render_market → src/data/market_service.py:MarketDataService.refresh → src/data/fund_flow.py:FundFlowAdapter.fetch → 限时子进程src/data/fund_flow_worker.py:fetch_one → ak.stock_individual_fund_flow → https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get。

另实测stock_individual_fund_flow_rank(indicator="今日")，底层https://push2.eastmoney.com/api/qt/clist/get，同样ProxyError；排名结果不保留行情时间戳，未作为今日字段来源。

官方说明：https://akshare.akfamily.xyz/data/stock/stock.html ；源站：https://data.eastmoney.com/zjlx/detail.html 。
个股接口返回日期和“主力净流入-净额”等分类字段，不是全口径资金净流入。当前连接失败，没有验证真实响应，不能声称盘中稳定更新。只将该字段保留到main_net_inflow_today；net_inflow_today缺失，严禁相加分类净流或用腾讯成交额推算资金流。

主力日资金流无源站盘中时刻，fund_flow_update_time留空；fund_flow_fetched_at仅为本地请求时间。同日主力数据如取得标CACHED，非当日字段清空；净流入率始终UNKNOWN，因为没有验证同源同快照的分母。历史统计未实现。

测试数据仅用于单元测试，不写入生产缓存。实测成功计数见reports/fund_flow_acceptance.json。
