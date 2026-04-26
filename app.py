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
    * Labels boven selectboxen (Ticker, Periode, Interval) */
    [data-testid="stWidgetLabel"] p { color: #ced4da !important; }
    /* NIEUW: Metrics onder de grafiek aanpassen */
    [data-testid="stMetricLabel"] { color: #ced4da !important; }
    [data-testid="stMetricValue"] { color: #00d4ff !important; }
    
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
        st.session_state.cfg["intraday_ratio"] = st.slider("Spike Ratio", 1.0, 10.0, float(st.session_state.cfg["intraday_ratio"]))
        if st.button("🔔 Test Telegram"): send_telegram_msg(f"✅ Testbericht voor {sel_ticker}"); st.success("OK!")
        for t in sorted(st.session_state.cfg["watchlist"]):
            if st.button(f"🗑️ {t}", key=f"del_{t}"): st.session_state.cfg["watchlist"].remove(t); sync_config(); st.rerun()

# ─── 4. GRAFIEK LOGICA ───────────────────────────────────────
if error:
    st.error(f"⚠️ {error}")
elif hist_df is not None:
    hist_df = hist_df.copy().reset_index()
    time_col = hist_df.columns[0]
    hist_df['x_label'] = hist_df[time_col].dt.strftime('%d %b %H:%M')

    avg_v = float(hist_df['Volume'].mean())
    vol_colors, spike_detected_now, final_ratio = [], False, 0

    for i in range(len(hist_df)):
        t, v = hist_df[time_col].iloc[i], hist_df['Volume'].iloc[i]
        is_opening = (t.hour == 9 and t.minute < 45)
        is_closing = (t.hour == 15 and t.minute > 45) or (t.hour >= 16)
        ratio = v / avg_v if avg_v > 0 else 0
        if ratio >= st.session_state.cfg["intraday_ratio"] and not is_opening and not is_closing:
            vol_colors.append('#ef5350')
            if i == len(hist_df) - 1: spike_detected_now, final_ratio = True, ratio
        else: vol_colors.append('rgba(150, 150, 150, 0.25)')

    if final_ratio == 0: final_ratio = float(hist_df['Volume'].iloc[-1]) / avg_v

    # Zoom 20/80
    p_min, p_max = hist_df['Close'].min(), hist_df['Close'].max()
    p_range = (p_max - p_min) if p_max != p_min else 1
    y_min, y_max = p_min - (0.2 * p_range / 0.6), p_max + (0.2 * p_range / 0.6)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist_df['x_label'], y=hist_df['Close'], line=dict(color='#00d4ff', width=2), fill='tonexty', fillcolor='rgba(0, 212, 255, 0.1)', yaxis="y2"))
    fig.add_trace(go.Bar(x=hist_df['x_label'], y=hist_df['Volume'], marker_color=vol_colors, yaxis="y"))

    day_indices = hist_df[hist_df[time_col].dt.date != hist_df[time_col].dt.date.shift(1)].index
    for idx in day_indices:
        if idx > 0: fig.add_vline(x=idx, line_width=0.8, line_color="rgba(200, 200, 200, 0.2)")

    fig.update_layout(template="plotly_dark", height=600, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
        xaxis=dict(type='category', nticks=8, showgrid=False, rangeslider_visible=True),
        yaxis=dict(range=[0, hist_df['Volume'].max() * 6], visible=False),
        yaxis2=dict(side="right", showgrid=True, gridcolor='rgba(255,255,255,0.05)', overlaying="y", range=[y_min, y_max], fixedrange=False))
    
    st.plotly_chart(fig, use_container_width=True)

    if spike_detected_now:
        event_id = f"{sel_ticker}_{hist_df[time_col].iloc[-1].strftime('%H:%M')}"
        if "last_alert_id" not in st.session_state or st.session_state.last_alert_id != event_id:
            send_telegram_msg(f"<b>🚀 SPIKE: {sel_ticker}</b>\nRatio: {final_ratio:.2f}x\nPrijs: ${d_close:.2f}")
            st.session_state.last_alert_id = event_id

    m1, m2, m3 = st.columns(3)
    m1.metric("Volume", f"{int(hist_df['Volume'].iloc[-1]):,}")
    m2.metric("Gemiddelde", f"{int(avg_v):,}")
    m3.metric("Ratio", f"{final_ratio:.2f}x")

st_autorefresh(interval=60 * 1000, key="auto_refresh")
