import os
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class CloudTests(unittest.TestCase):
    def test_cloud_readonly_and_mobile(self):
        with patch.dict(os.environ):
            page=AppTest.from_file(str(ROOT/'cloud_app.py')).run(timeout=20)
            self.assertFalse(page.exception)
            self.assertEqual(next(r for r in page.radio if r.label=='工作区').options,['候诊台'])
            self.assertTrue(page.toggle[0].value)
            self.assertEqual(len(page.dataframe[0].value),50)
            self.assertTrue(any(s.label=='查看股票详情' for s in page.selectbox))
            next(r for r in page.radio if r.label=='观察池').set_value('高成长跃迁20股').run()
            self.assertEqual(len(page.dataframe[0].value),20)
            page.toggle[0].set_value(False).run()
            self.assertIn('float_cap',page.dataframe[0].value.columns)
            self.assertFalse(page.exception)
