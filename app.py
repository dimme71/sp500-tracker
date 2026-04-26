import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import requests
from datetime import datetime
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ─── 1. CONFIGURATIE & STYLING ────────────────────────────────
st.set_page_config(page_title="Stock Volume Pro", page_icon="📈", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ced4da; }
    .main-header { color: #00d4ff; font-size: 2.2rem; font-weight: 700; margin-bottom: 1rem; }
    .sidebar-text { color: #ced4da; font-size: 0.85rem; }
    .metric-val { color: #00d4ff; font-weight: bold; }
    .spike-val { color: #ef5350; font-weight: bold; }
    .watchlist-card { 
        background: #1a1d27; padding: 10px; border-radius: 8px; 
        border-left: 3px solid #3f444e; margin-bottom: 8px;
    }
    .sidebar-metric { background: #1a1d27; padding: 12px; border-radius: 8px; border: 1px solid #3f444e; }
</style>
""", unsafe_allow_html=True)

CONFIG_PATH = "config.json"

def load_config():
    defaults = {"watchlist": ["AAPL", "MSFT", "NVDA", "TSLA"], "intraday_ratio": 3.0}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f: return json.load(f)
        except: pass
    return defaults

def sync_config():
    with open(CONFIG_PATH, "w") as f: json.dump(st.session_state.cfg, f)

if 'cfg' not in st.session_state:
    st.session_state.cfg = load_config()

def send_telegram_msg(message):
    try:
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=5)
    except Exception as e: st.error(f"Telegram fout: {e}")

@st.cache_data(ttl=60)
def get_data_safe(ticker, period, interval):
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty: return None, "Geen data gevonden."
        return df, None
    except Exception as e: return None, str(e)

# ─── 2. SELECTOR EN DATA INLADEN ─────────────────────────────
st.markdown("<h1 class='main-header'>⚡ Volume Spike Explorer</h1>", unsafe_allow_html=True)

c1, c2, c3 = st.columns([1, 1, 1])
with c1: sel_ticker = st.selectbox("Ticker", st.session_state.cfg["watchlist"])
with c2: sel_period = st.selectbox("Periode", ["1d", "5d", "1mo", "6mo", "1y"], index=0)
with c3: sel_interval = st.selectbox("Interval", ["1m", "5m", "15m", "60m", "1d"], index=0)

hist_df, error = get_data_safe(sel_ticker, sel_period, sel_interval)

# ─── 3. SIDEBAR (Watchlist & Stats) ──────────────────────────
with st.sidebar:
    st.header("📋 Watchlist Overview")
    
    # Overzicht alle tickers
    for t in sorted(st.session_state.cfg["watchlist"]):
        try:
            w_df = yf.download(t, period="1d", interval="15m", progress=False)
            if not w_df.empty:
                if isinstance(w_df.columns, pd.MultiIndex): w_df.columns = w_df.columns.get_level_values(0)
                w_last = float(w_df['Close'].iloc[-1].iloc[0] if hasattr(w_df['Close'].iloc[-1], 'iloc') else w_df['Close'].iloc[-1])
                w_max_s = float((w_df['Volume'] / w_df['Volume'].mean()).max())
                st.markdown(f"""<div class="watchlist-card"><div style="display:flex;justify-content:space-between;">
                <span style="color:white;">{t}</span><span class="metric-val">${w_last:.2f}</span></div>
                <div class="sidebar-text">Max Spike: <span class="spike-val">{w_max_s:.2f}x</span></div></div>""", unsafe_allow_html=True)
        except: pass

    st.write("---")
    
    # Details Main Ticker
    if hist_df is not None and not error:
        if isinstance(hist_df.columns, pd.MultiIndex): hist_df.columns = hist_df.columns.get_level_values(0)
        st.subheader(f"🔍 Details: {sel_ticker}")
        d_high = float(hist_df['High'].max().iloc[0] if hasattr(hist_df['High'].max(), 'iloc') else hist_df['High'].max())
        d_low = float(hist_df['Low'].min().iloc[0] if hasattr(hist_df['Low'].min(), 'iloc') else hist_df['Low'].min())
        d_close = float(hist_df['Close'].iloc[-1].iloc[0] if hasattr(hist_df['Close'].iloc[-1], 'iloc') else hist_df['Close'].iloc[-1])
        
        ca, cb = st.columns(2)
        ca.markdown(f"<div class='sidebar-text'>Hoog<br><b style='color:white;'>${d_high:.2f}</b></div>", unsafe_allow_html=True)
        cb.markdown(f"<div class='sidebar-text'>Laag<br><b style='color:white;'>${d_low:.2f}</b></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='sidebar-metric' style='margin-top:10px;'><small class='sidebar-text'>Huidig</small><br><b style='color:#00d4ff; font-size:1.4rem;'>${d_close:.2f}</b></div>", unsafe_allow_html=True)

    st.write("---")
    with st.expander("⚙️ Beheer"):
        new_t = st.text_input("Ticker +").upper().strip()
        if st.button("Voeg toe") and new_t:
            st.session_state.cfg["watchlist"].append(new_t); sync_config(); st.rerun()
        st.session_state.cfg["intraday_ratio
