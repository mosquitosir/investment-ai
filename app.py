"""启动命令：python -m streamlit run app.py。"""
import streamlit as st
from src.ui.market_table import render_market

st.set_page_config(page_title="资本候诊台 V0.2", layout="wide")
st.markdown("""<style>
.block-container {padding-top:3.5rem;padding-bottom:1rem;}
[data-testid="stVerticalBlock"] {gap:0.45rem;}
h3 {font-size:1.2rem !important;}
@media (max-width: 640px) {
 .block-container {padding-left:0.75rem;padding-right:0.75rem;}
 [data-testid="stHorizontalBlock"] {flex-wrap:wrap;gap:0.6rem;}
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width:100% !important;flex:1 1 100% !important;}
 button {min-height:44px;}
}
</style>""", unsafe_allow_html=True)
render_market()
