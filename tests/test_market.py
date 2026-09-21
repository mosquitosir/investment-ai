import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock
import pandas as pd
from streamlit.testing.v1 import AppTest
from src.watchlist.repository import WatchlistRepository,normalize_code
from src.data.market_service import MarketDataService,standardize,filter_quotes,sort_quotes,NUMERIC
from src.diagnosis.service import load_diagnoses

ROOT=Path(__file__).resolve().parents[1]


class MarketTests(unittest.TestCase):
    def test_watchlist_codes_manage(self):
        for raw in ['002371','sz002371','002371.SZ']:
            self.assertEqual(normalize_code(raw),'002371')
        with self.assertRaises(ValueError): normalize_code('abc')
        with tempfile.TemporaryDirectory(dir=ROOT/'data/cache') as folder:
            path=Path(folder)/'watch.csv'
            shutil.copy2(ROOT/'data/watchlist.csv',path)
            repo=WatchlistRepository(path)
            self.assertEqual(len(repo.load()),50)
            record=repo.load().iloc[0].to_dict()
            record.update(code='000001',name='测试名称',notes='test')
            repo.upsert([record]);self.assertEqual(len(repo.load()),51)
            record['notes']='updated';repo.upsert([record])
            self.assertEqual(repo.load().set_index('code').loc['000001','notes'],'updated')
            repo.remove('000001');self.assertEqual(len(repo.load()),50)

    def test_numeric_missing_isolation_sort_filter(self):
        d=standardize(pd.DataFrame({'code':['002371','688012','688072'],'price':['9','100','bad']}))
        self.assertEqual(sort_quotes(d,'price',True).code.tolist(),['002371','688012','688072'])
        self.assertEqual(sort_quotes(d,'price',False).code.tolist(),['688012','002371','688072'])
        self.assertTrue(d.iloc[-1][NUMERIC].isna().all())
        d['name']=['北方华创','中微公司','拓荆科技'];d['industry_name']='半导体设备'
        self.assertEqual(len(filter_quotes(d,search='中微')),1)
        self.assertEqual(len(filter_quotes(d,search='688012')),1)
        self.assertEqual(len(filter_quotes(d,industry='创新药')),0)

    def test_cache_fallback(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'data/cache') as folder:
            adapter=Mock()
            adapter.fetch.return_value=pd.DataFrame({'code':['002371'],'price':[10.],
                'updated_at':[pd.Timestamp.now(tz='Asia/Shanghai').isoformat()]})
            service=MarketDataService(folder,adapter)
            self.assertEqual(service.refresh(['002371']).iloc[0].data_status,'LIVE')
            adapter.fetch.side_effect=RuntimeError('offline')
            fallback=service.refresh(['002371'])
            self.assertEqual(fallback.iloc[0].price,10.)
            self.assertEqual(fallback.iloc[0].data_status,'CACHED')

    def test_real_cache_50_and_diagnosis(self):
        w=WatchlistRepository(ROOT/'data/watchlist.csv').load()
        service=MarketDataService(ROOT)
        d=service.for_watchlist(w,service.cached())
        self.assertEqual(len(d),50)
        self.assertEqual(w.industry_id.nunique(),10)
        for name in w.industry_name.unique():
            self.assertEqual(len(filter_quotes(d,industry=name)),5)
        diagnosis=load_diagnoses(ROOT,w.code.tolist()).set_index('code')
        self.assertNotEqual(diagnosis.loc['002371','current_pulse'],'待诊')
        self.assertEqual(diagnosis.loc['300308','current_pulse'],'待诊')

    def test_page_search_views(self):
        page=AppTest.from_file(str(ROOT/'app.py')).run(timeout=20)
        self.assertFalse(page.exception)

        self.assertEqual(len(page.dataframe[0].value),50)
        page.text_input[0].set_value('688012').run()
        self.assertFalse(page.exception)
        self.assertEqual(len(page.dataframe[0].value),1)
        page.text_input[0].set_value('').run()
        next(r for r in page.radio if r.label=='视图').set_value('诊断').run()
        self.assertFalse(page.exception)
        self.assertEqual(len(page.dataframe[0].value),50)
        next(r for r in page.radio if r.label=='工作区').set_value('股票管理').run()
        self.assertFalse(page.exception)

    def test_manage_ui_add_edit_remove(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=ROOT/'data/cache') as folder:
            root=Path(folder)
            (root/'data/cache').mkdir(parents=True)
            (root/'config').mkdir()
            shutil.copy2(ROOT/'data/watchlist.csv',root/'data/watchlist.csv')
            shutil.copy2(ROOT/'config/settings.yaml',root/'config/settings.yaml')
            with patch('src.ui.market_table.ROOT',root):
                page=AppTest.from_file(str(ROOT/'app.py')).run()
                next(r for r in page.radio if r.label=='工作区').set_value('股票管理').run()
                page.text_area[0].set_value('002371').run()
                next(b for b in page.button if b.label=='识别并预览').click().run()
                self.assertFalse(page.exception)
                next(b for b in page.button if b.label=='确认加入候诊池').click().run()
                self.assertFalse(page.exception)
                self.assertEqual(len(WatchlistRepository(root/'data/watchlist.csv').load()),50)
                next(b for b in page.button if b.label=='保存修改').click().run()
                self.assertFalse(page.exception)
                next(b for b in page.button if b.label=='移出候诊池').click().run()
                self.assertFalse(page.exception)
                self.assertEqual(len(WatchlistRepository(root/'data/watchlist.csv').load()),49)



if __name__=='__main__': unittest.main()
