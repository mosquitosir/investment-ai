"""行情页面。"""
import streamlit as st
from src.data.data_manager import load_quotes


def render_quotes():
    st.title("A股基础策略筛选器 V0.1")
    st.caption("免费数据源：AKShare / 腾讯财经；无需 Token 或付费 API。")
    st.caption("非交易时段通常为最近交易行情；当前会话保留已加载结果，点击刷新重新请求。")
    refresh = st.button("刷新行情")
    if refresh or "quotes" not in st.session_state:
        st.session_state.pop("quotes", None)
        try:
            with st.spinner("正在获取 A 股行情，请稍候……"):
                st.session_state.quotes = load_quotes()
        except Exception as exc:
            st.error("行情请求失败，请检查网络或稍后刷新。")
            with st.expander("查看错误详情"):
                st.code(f"{type(exc).__name__}: {exc}")
            return
    quotes = st.session_state.quotes
    st.caption(f"本次获取 {len(quotes)} 条行情，展示前 {min(30, len(quotes))} 条。")
    st.dataframe(quotes.head(30), hide_index=True, width="stretch")
    st.caption("最新价单位为元，涨跌幅单位为 %。当前仅展示 4 个基础字段。")
