"""云端入口：只读观察池；访问权限由托管平台设置为私有。"""
import os
import runpy
from pathlib import Path

os.environ['INVESTMENT_READ_ONLY'] = '1'
runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
