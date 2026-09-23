import tempfile
import unittest
from pathlib import Path
import pandas as pd
import numpy as np
from streamlit.testing.v1 import AppTest

from src.intraday.service import (IntradayPulseService, monitored_universe,
    daily_position_metrics, intraday_series_metrics, derive_states,
    calculate_excess_return, detect_pulse_change)

ROOT=Path(__file__).resolve().parents[1]
CFG=IntradayPulseService(ROOT).config


class IntradayTests(unittest.TestCase):
    def test_union_and_page(self):
        self.assertEqual(len(monitored_universe(ROOT)),70)
        page=AppTest.from_file(str(ROOT/'app.py')).run(timeout=20)
        next(r for r in page.radio if r.label=='观察池').set_value('今日脉动').run(timeout=20)
        self.assertFalse(page.exception)
        self.assertEqual(len(page.dataframe[0].value),70)
        self.assertTrue(any(b.label=='刷新并保存快照' for b in page.button))

    def test_daily_ma_point_in_time(self):
        h=pd.DataFrame({'date':pd.date_range('2026-01-01',periods=60),'close':range(1,61),
                        'high':range(2,62),'low':range(0,60)})
        out=daily_position_metrics(h,{'price':61.,'open':60.,'prev_close':60.},CFG)
        self.assertAlmostEqual(out['ma5'],59.)
        self.assertAlmostEqual(out['distance_to_ma20'],61/51.5-1)
        self.assertAlmostEqual(out['distance_to_20d_high'],61/61-1)
        self.assertEqual(out['daily_history_status'],'CACHED')

    def test_vwap_drawdown_and_no_future(self):
        rows=[]
        for i,(price,amount,high,low) in enumerate([(10,1000,10,9),(12,2200,12,10),(9,3100,12,8)]):
            rows.append({'timestamp':f'2026-09-21T09:{30+i*5:02d}:00','snapshot_slot':str(i),
                         'price':price,'amount':amount,'volume':100+i*100,'intraday_high':high,
                         'intraday_low':low,'vwap':amount/(100+i*100)})
        d=pd.DataFrame(rows)
        current=dict(d.iloc[2],prev_close=9.,intraday_high=12.,intraday_low=8.,volume=300.)
        out=intraday_series_metrics(d,current,[11.],CFG)
        self.assertAlmostEqual(out['vwap'],3100/300)
        self.assertAlmostEqual(out['max_intraday_drawdown'],9/12-1)
        prefix=intraday_series_metrics(d.iloc[:2],dict(d.iloc[1],prev_close=9.,volume=200.),[11.],CFG)
        self.assertEqual(prefix['snapshot_count'],2)
        self.assertNotEqual(prefix['max_intraday_drawdown'],out['max_intraday_drawdown'])

    def test_missing_is_not_zero_and_l2(self):
        service=IntradayPulseService(ROOT)
        d=service.calculate(monitored_universe(ROOT),pd.DataFrame({'code':[]}),save=False)
        self.assertTrue(d.net_inflow_today.isna().all())
        self.assertTrue(d.aggressive_buy_amount.isna().all())
        self.assertTrue(d.l2_status.eq('MISSING_L2').all())
        self.assertTrue(d.pulse_state.eq('INSUFFICIENT_DATA').all())
        self.assertTrue(d.amount_ratio_20.isna().all())
        self.assertTrue(d.amount_ratio_status.eq('PARTIAL').all())
        self.assertTrue(d.fund_data_level.eq('MISSING').all())

    def test_excess_state_and_pulse_change(self):
        self.assertAlmostEqual(calculate_excess_return(.05,.02),.03)
        self.assertTrue(pd.isna(calculate_excess_return(.05,np.nan)))
        changed,stamp=detect_pulse_change('浮','滑','2026-09-21T10:00:00')
        self.assertTrue(changed); self.assertEqual(stamp,'2026-09-21T10:00:00')
        self.assertFalse(detect_pulse_change('UNKNOWN','滑')[0])
        row=pd.Series({'snapshot_count':4,'industry_return_intraday':np.nan,
            'price':100.,'ma20':90.,'ma60':80.,'ma20_slope':.02,
            'vwap_hold_ratio':.8,'max_intraday_drawdown':-.01,'price_vs_vwap':.01,
            'pct_change':2.,'turnover':1.,'volume_ratio_intraday':1.2,
            'failed_breakout_count':0})
        states=derive_states(row,CFG)
        self.assertEqual(states['continuation_state'],'STRENGTHENING')
        self.assertEqual(states['pulse_state'],'滑')

    def test_snapshot_save_deduplicates_slot(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'data/cache') as folder:
            root=Path(folder); (root/'config').mkdir(); (root/'data').mkdir()
            (root/'config/intraday_pulse.yaml').write_text((ROOT/'config/intraday_pulse.yaml').read_text(encoding='utf-8'),encoding='utf-8')
            service=IntradayPulseService(root)
            d=pd.DataFrame([{'code':'000001','trade_date':'2026-09-21','timestamp':'2026-09-21T10:00:01',
                             'snapshot_slot':'2026-09-21T10:00:00','price':10},
                            {'code':'000001','trade_date':'2026-09-21','timestamp':'2026-09-21T10:00:59',
                             'snapshot_slot':'2026-09-21T10:00:00','price':11}])
            service.save(d)
            saved=pd.read_csv(root/'data/intraday_snapshots/2026-09-21.csv',dtype={'code':str})
            self.assertEqual(len(saved),1); self.assertEqual(saved.iloc[0].price,11)


if __name__=='__main__': unittest.main()
