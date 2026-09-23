import unittest
from pathlib import Path
from unittest.mock import Mock
import tempfile
import pandas as pd
from streamlit.testing.v1 import AppTest
from src.data.fund_flow import normalize_flow, format_flow
from src.data.market_service import MarketDataService, sort_quotes
from src.watchlist.growth import load_growth, filter_growth

ROOT = Path(__file__).resolve().parents[1]


class FundFlowTests(unittest.TestCase):
    def test_format_and_numeric_sort(self):
        values = [325000000., 68500000., -136000000., -42000000., 0., float('nan')]
        self.assertEqual([format_flow(v) for v in values], ['+3.25亿', '+6850万', '-1.36亿', '-4200万', '0（基本平衡）', '--'])
        d = pd.DataFrame({'net_inflow_today': values})
        self.assertEqual(sort_quotes(d,'net_inflow_today',True).index.tolist(), [2,3,4,1,0,5])
        self.assertEqual(sort_quotes(d,'net_inflow_today',False).index.tolist(), [0,1,4,3,2,5])

    def test_date_isolation_and_definition(self):
        d = pd.DataFrame({'code':['000001','000002'], 'fund_flow_trade_date':['2026-09-20','2026-09-21'],
                          'main_net_inflow_today':[123., -456.], 'net_inflow_ratio':[.1,.2]})
        result=normalize_flow(d, now='2026-09-21T10:00:00+08:00')
        self.assertTrue(result.net_inflow_today.isna().all())
        self.assertTrue(pd.isna(result.iloc[0].main_net_inflow_today))
        self.assertEqual(result.iloc[1].main_net_inflow_today,-456.)
        self.assertTrue(result.net_inflow_ratio.isna().all())
        self.assertTrue(result.fund_flow_status.eq('MISSING').all())

    def test_fund_data_level_uses_real_available_fields(self):
        rows = pd.DataFrame([
            {'code':'000001','price':10.,'amount':1000.},
            {'code':'000002','price':10.,'main_net_inflow_today':20.,'fund_flow_trade_date':'2026-09-21'},
            {'code':'000003','price':10.,'active_net_buy':30.},
            {'code':'000004'},
        ])
        result = normalize_flow(rows, now='2026-09-21T10:00:00+08:00')
        self.assertEqual(result.fund_data_level.tolist(), ['F0','F1','F2','MISSING'])

    def test_flow_refresh_independent_of_quote_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'data/cache') as folder:
            quote=Mock();flow=Mock()
            quote.fetch.side_effect=RuntimeError('offline')
            flow.fetch.return_value=normalize_flow(pd.DataFrame({'code':['688498'],'fund_flow_error':['ProxyError']}))
            service=MarketDataService(folder,quote,flow)
            out=service.refresh(['688498'])
            self.assertEqual(out.iloc[0].fund_flow_status,'MISSING')
            self.assertEqual(service.cached().iloc[0].fund_flow_error,'ProxyError')
            flow.fetch.assert_called_once_with(['688498'])

    def test_both_pages_and_growth_filters(self):
        watch=load_growth(ROOT)
        self.assertEqual(len(watch),20)
        self.assertEqual(watch.set_index('code').loc['003021','name'],'兆威机电')
        self.assertTrue(watch.next_validation.str.len().gt(0).all())
        self.assertEqual(len(filter_growth(watch,'L3小批量')),0)
        self.assertEqual(len(filter_growth(watch,'待复诊')),20)
        page=AppTest.from_file(str(ROOT/'app.py')).run(timeout=20)
        self.assertFalse(page.exception)
        cols=list(page.dataframe[0].value.columns)
        self.assertEqual(cols[cols.index('change_pct')+1],'net_inflow_today')
        next(r for r in page.radio if r.label=='观察池').set_value('高成长跃迁20股').run()
        self.assertFalse(page.exception)
        self.assertEqual(len(page.dataframe[0].value),20)
        next(s for s in page.selectbox if s.label=='排序字段').set_value('net_inflow_today').run()
        page.text_input[0].set_value('源杰').run()
        self.assertEqual(len(page.dataframe[0].value),1)
        self.assertIn('688498',page.dataframe[0].value.code.tolist())
        page.text_input[0].set_value('').run()
        next(r for r in page.radio if r.label=='成长阶段').set_value('L4放量').run()
        self.assertEqual(len(page.dataframe[0].value),0)
        next(r for r in page.radio if r.label=='成长阶段').set_value('待复诊').run()
        self.assertEqual(len(page.dataframe[0].value),20)
        self.assertFalse(page.exception)
        next(r for r in page.radio if r.label=='视图').set_value('诊断').run()
        self.assertIn('next_validation',page.dataframe[0].value.columns)
        self.assertNotIn('current_pulse',page.dataframe[0].value.columns)
        self.assertFalse(page.exception)


if __name__=='__main__':
    unittest.main()
