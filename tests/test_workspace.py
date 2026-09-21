import unittest
from unittest.mock import patch
from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")

class WorkspaceTests(unittest.TestCase):
    def test_docs_and_quotes(self):
        sample = pd.DataFrame({"code": ["sz000001"] * 35, "name": ["测试"] * 35,
                               "zxj": ["10.00"] * 35, "zdf": ["1.00"] * 35})
        with patch("src.data.data_manager.fetch_quotes", return_value=sample) as fetch:
            page = AppTest.from_string("from src.ui.workspace import render_workspace; render_workspace()").run()
            for label in page.sidebar.radio[0].options[:-1]:
                page.sidebar.radio[0].set_value(label).run()
                self.assertFalse(page.exception)
                self.assertTrue(page.markdown)
            fetch.assert_not_called()
            page.sidebar.radio[0].set_value("实时行情").run()
            self.assertFalse(page.exception)
            self.assertEqual(page.dataframe[0].value.shape, (30, 4))
            self.assertEqual(page.dataframe[0].value.iloc[0, 0], "sz000001")
            fetch.assert_called_once()
            page.sidebar.radio[0].set_value("项目说明").run()
            page.sidebar.radio[0].set_value("实时行情").run()
            fetch.assert_called_once()
        with patch("src.data.data_manager.fetch_quotes", side_effect=ConnectionError("测试断网")):
            page.button[0].click().run()
            self.assertFalse(page.exception)
            self.assertTrue(page.error)
            self.assertEqual(len(page.dataframe), 0)
            page.sidebar.radio[0].set_value("项目说明").run()
            self.assertFalse(page.exception)
            self.assertTrue(page.markdown)

if __name__ == "__main__":
    unittest.main()
