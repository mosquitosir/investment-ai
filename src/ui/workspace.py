"""固定文档目录组成工作栏，避免文档查询依赖行情接口。"""
from pathlib import Path
import streamlit as st
from src.ui.quotes import render_quotes

ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = {
    "项目说明": "README.md",
    "开发日志": "PROJECT_LOG.md",
    "下一步计划": "ROADMAP.md",
    "产品需求": "docs/product/PRD.md",
    "版本变化": "docs/product/CHANGELOG.md",
    "数据源研究": "docs/research/data_sources.md",
    "因子研究": "docs/research/factors.md",
    "策略研究": "docs/research/strategies.md",
    "架构决策": "docs/decisions/architecture.md",
    "长期规则": "AGENTS.md",
}


def render_workspace():
    st.sidebar.title("投资 AI · 工作栏")
    choice = st.sidebar.radio("查看内容", [*DOCUMENTS, "实时行情"])
    st.sidebar.caption("当前阶段：V0.1 免费行情与项目文档")
    if choice == "实时行情":
        render_quotes()
        return
    path = ROOT / DOCUMENTS[choice]
    st.caption(f"项目文档 · {DOCUMENTS[choice]}")
    if path.is_file():
        st.markdown(path.read_text(encoding="utf-8-sig"))
    else:
        st.warning("文档暂未创建。")
