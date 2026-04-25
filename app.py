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
st.set_page_config(page_title="Stock Volume Master Pro", page_icon="📈", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .main-header { color: #00d4ff; font-size: 2.2rem; font-weight: 700; margin-bottom: 1rem; }
    .card { background: #1a1d27; border-radius: 12px; padding: 1.2rem; border: 1px solid #3f444e; }
    .price-up { color: #00ff87; font-size: 1.5rem; font-weight: 800; }
    .price-down { color: #ff3e3e; font-size: 1.5rem; font-weight: 800; }
    label { color: #ffffff !important; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

CONFIG_PATH = "config.json"

def load_config():
    defaults = {"watchlist": ["AAPL", "MSFT", "NVDA", "TSLA"], "intraday_ratio": 3.0}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                defaults.update(json.load(f))
        except: pass
    return defaults

def save_config(wl, ratio):
    with open(CONFIG_PATH, "w") as f:
        json.dump({"watchlist": wl, "intraday_ratio": ratio}, f)

if 'cfg' not in st.session_state:
    st.session_state.cfg = load_config()

# ─── 2. DATA FUNCTIES ──────────────────────────────────────────
@st.cache_data(ttl=300)
def get_data_safe(ticker, period, interval):
    try:
        # Check op Yahoo Finance limieten
        if period in ["1y", "max", "6mo"] and interval in ["1m", "5m", "15m"]:
            return None, f"Interval '{interval}' is niet beschikbaar voor periode '{period}'. Max 60 dagen voor intraday."
        
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return None, "Geen data gevonden voor deze combinatie."
        return df.dropna(), None
    except Exception as e:
        return None, f"Fout: {str(e)}"

def send_telegram(msg):
    token = st.secrets.get("telegram_token")
    chat_id = st.secrets.get("telegram_chat_id")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)

# ─── 3. SIDEBAR ───────────────────────────────────────────────
with st.sidebar:
    st.header("🛠️ Beheer")
    new_t = st.text_input("Voeg Ticker toe").upper().strip()
    if st.button("➕ Voeg toe"):
        if new_t and new_t not in st.session_state.cfg["watchlist"]:
            st.session_state.cfg["watchlist"].append(new_t)
            save_config(st.session_state.cfg["watchlist"], st.session_state.cfg["intraday_ratio"])
            st.rerun()
    
    st.session_state.cfg["intraday_ratio"] = st.slider("Spike Ratio", 1.0, 10.0, float(st.session_state.cfg["intraday_ratio"]))
    
    if st.button("🗑️ Reset Lijst"):
        st.session_state.cfg["watchlist"] = ["AAPL"]
        save_config(st.session_state.cfg["watchlist"], 3.0)
        st.rerun()

# ─── 4. MAIN DASHBOARD ────────────────────────────────────────
st.markdown("<h1 class='main-header'>⚡ Volume Spike Explorer</h1>", unsafe_allow_html=True)

# Selectie menu's
c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    sel_ticker = st.selectbox("Ticker", st.session_state.cfg["watchlist"])
with c2:
    sel_period = st.selectbox("Tijdsbestek", ["1d", "5d", "1mo", "6mo", "1y", "max"], index=1)
with c3:
    sel_interval = st.selectbox("Detail (Zoom)", ["1m", "5m", "15m", "60m", "1d", "1wk"], index=2)

# Data ophalen & Plotten
hist_df, error = get_data_safe(sel_ticker, sel_period, sel_interval)

if error:
    st.error(f"⚠️ {error}")
elif hist_df is not None:
    # --- FIX: Kolommen platslaan als ze Multi-Index zijn ---
    if isinstance(hist_df.columns, pd.MultiIndex):
        hist_df.columns = hist_df.columns.get_level_values(0)
    
    # Zorg dat de index (tijd) bruikbaar is voor Plotly
    hist_df = hist_df.reset_index()
    time_col = hist_df.columns[0] # Meestal 'Date' of 'Datetime'

    # --- FIX: Zorg dat mean() een enkel getal is ---
    avg_v = float(hist_df['Volume'].mean())
    last_v = int(hist_df['Volume'].iloc[-1])
    
    # Plotting
    colors = ['#00d4ff'] * (len(hist_df) - 1) + ['#ffc107']
    
    fig = go.Figure(go.Bar(
        x=hist_df[time_col], 
        y=hist_df['Volume'], 
        marker_color=colors,
        name="Volume"
    ))
    
    # De lijn heeft nu een vast getal (avg_v)
    fig.add_hline(y=avg_v, line_dash="dash", line_color="#ff4b4b")
    
    fig.update_layout(
        template="plotly_dark", 
        height=450, 
        xaxis_rangeslider_visible=True, 
        margin=dict(l=0,r=0,t=30,b=0)
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Metrics
    current_ratio = last_v / avg_v if avg_v > 0 else 0
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Huidig Volume", f"{last_v:,}")
    m2.metric("Gemiddelde", f"{int(avg_v):,}")
    m3.metric("Ratio", f"{current_ratio:.2f}x")

    # Automatische Alert Check
    if current_ratio >= st.session_state.cfg["intraday_ratio"]:
        st.warning(f"🚨 SPIKE DETECTIE: {sel_ticker} vertoont {current_ratio:.2f}x normaal volume!")

st_autorefresh(interval=60 * 1000, key="auto_refresh")
