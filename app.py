import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import requests
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

# ─── 1. CONFIGURATIE & STYLING ────────────────────────────────
st.set_page_config(page_title="Stock Volume Pro", page_icon="📈", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .main-header { color: #00d4ff; font-size: 2.2rem; font-weight: 700; margin-bottom: 1rem; }
    .card { background: #1a1d27; border-radius: 12px; padding: 1.2rem; border: 1px solid #3f444e; }
</style>
""", unsafe_allow_html=True)

CONFIG_PATH = "config.json"

def load_config():
    defaults = {
        "watchlist": ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META"], 
        "intraday_ratio": 3.0
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
                if saved.get("watchlist"):
                    defaults["watchlist"] = saved["watchlist"]
                defaults["intraday_ratio"] = saved.get("intraday_ratio", 3.0)
        except: pass
    return defaults

def sync_config():
    with open(CONFIG_PATH, "w") as f:
        json.dump({
            "watchlist": st.session_state.cfg["watchlist"], 
            "intraday_ratio": st.session_state.cfg["intraday_ratio"]
        }, f)

if 'cfg' not in st.session_state:
    st.session_state.cfg = load_config()

# ─── 2. DATA ENGINE ───────────────────────────────────────────
@st.cache_data(ttl=300)
def get_data_safe(ticker, period, interval):
    try:
        # Check op Yahoo Finance intraday limieten
        if period in ["1y", "max", "6mo"] and interval in ["1m", "5m", "15m"]:
            return None, f"Interval '{interval}' is niet beschikbaar voor '{period}'. Max 60 dagen voor intraday."
        
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return None, "Geen data gevonden."
        return df, None
    except Exception as e:
        return None, f"Fout: {str(e)}"

# ─── 3. SIDEBAR ───────────────────────────────────────────────
with st.sidebar:
    st.header("📋 Watchlist")
    
    with st.expander("➕ Toevoegen", expanded=False):
        new_t = st.text_input("Ticker (bijv. NVDA)").upper().strip()
        if st.button("Voeg toe"):
            if new_t and new_t not in st.session_state.cfg["watchlist"]:
                st.session_state.cfg["watchlist"].append(new_t)
                sync_config()
                st.rerun()

    st.write("---")
    for t in sorted(st.session_state.cfg["watchlist"]):
        cols = st.columns([3, 1])
        cols[0].write(t)
        if cols[1].button("🗑️", key=f"del_{t}"):
            st.session_state.cfg["watchlist"].remove(t)
            sync_config()
            st.rerun()

    st.write("---")
    st.session_state.cfg["intraday_ratio"] = st.slider("Spike Ratio", 1.0, 10.0, float(st.session_state.cfg["intraday_ratio"]))

# ─── 4. MAIN UI ───────────────────────────────────────────────
st.markdown("<h1 class='main-header'>⚡ Volume Spike Explorer</h1>", unsafe_allow_html=True)

c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    sel_ticker = st.selectbox("Ticker", st.session_state.cfg["watchlist"])
with c2:
    sel_period = st.selectbox("Periode", ["1d", "5d", "1mo", "6mo", "1y", "max"], index=1)
with c3:
    sel_interval = st.selectbox("Interval (Zoom)", ["1m", "5m", "15m", "60m", "1d", "1wk"], index=2)

hist_df, error = get_data_safe(sel_ticker, sel_period, sel_interval)

if error:
    st.error(f"⚠️ {error}")
    st.info("Tip: Kies een kortere periode voor gedetailleerde charts.")
elif hist_df is not None:
    # Data opschonen (Multi-index fix)
    if isinstance(hist_df.columns, pd.MultiIndex):
        hist_df.columns = hist_df.columns.get_level_values(0)
    
    hist_df = hist_df.reset_index()
    time_col = hist_df.columns[0]

    # --- Visualisatie: Gecentreerde Zoom zonder Sluitingstijden ---

    # 1. Voorbereiding: Gebruik een string-as om gaten te voorkomen
    # We maken een hulpkolom voor de labels op de X-as
    hist_df['x_label'] = hist_df[time_col].dt.strftime('%d %b %H:%M')
    
    # 2. Bereken de schaal (Min op 20%, Max op 80%)
    p_min = hist_df['Close'].min()
    p_max = hist_df['Close'].max()
    p_range = p_max - p_min if p_max != p_min else 1
    
    # De formule voor de marges
    y_min = p_min - (0.2 * p_range / 0.6)
    y_max = p_max + (0.2 * p_range / 0.6)
    
    fig = go.Figure()
    
    # 3. Prijs (Area)
    fig.add_trace(
        go.Scatter(
            x=hist_df['x_label'], 
            y=hist_df['Close'], 
            name="Prijs",
            line=dict(color='#00d4ff', width=2),
            fill='tonexty', 
            fillcolor='rgba(0, 212, 255, 0.15)',
            yaxis="y2" 
        )
    )
    
    # 4. Volume (Bars)
    fig.add_trace(
        go.Bar(
            x=hist_df['x_label'], 
            y=hist_df['Volume'], 
            marker_color='rgba(150, 150, 150, 0.25)',
            yaxis="y"
        )
    )
    
    # 5. Verticale lijnen (Dagscheidingen)
    # We zoeken de indexen waar de dag verandert
    day_indices = hist_df[hist_df[time_col].dt.date != hist_df[time_col].dt.date.shift(1)].index
    for idx in day_indices:
        if idx > 0: # Sla de allereerste bar over
            fig.add_vline(
                x=idx, 
                line_width=0.8, 
                line_color="rgba(200, 200, 200, 0.3)", 
                line_dash="solid"
            )
    
    # 6. Layout & Schaling
    fig.update_layout(
        template="plotly_dark",
        height=600,
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
        xaxis=dict(
            type='category', # VERWIJDERT ALLE GATEN (Nachten/Weekenden)
            tickangle=0,
            nticks=8,
            showgrid=False,
            rangeslider_visible=True,
            rangeslider_thickness=0.04
        ),
        yaxis=dict(
            range=[0, hist_df['Volume'].max() * 6], 
            visible=False
        ),
        yaxis2=dict(
            side="right",
            showgrid=True,
            gridcolor='rgba(255,255,255,0.05)',
            overlaying="y",
            range=[y_min, y_max], # FORCEERT DE 20/80 ZOOM
            fixedrange=False
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # Metrics
    avg_v = float(hist_df['Volume'].mean())
    last_v = int(hist_df['Volume'].iloc[-1])
    ratio = last_v / avg_v if avg_v > 0 else 0
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Laatste Volume", f"{last_v:,}")
    m2.metric("Gemiddelde", f"{int(avg_v):,}")
    m3.metric("Volume Ratio", f"{ratio:.2f}x")

    if ratio >= st.session_state.cfg["intraday_ratio"]:
        st.warning(f"🚨 SPIKE: {sel_ticker} volume is {ratio:.2f}x hoger dan gemiddeld!")

st_autorefresh(interval=60 * 1000, key="auto_refresh")
