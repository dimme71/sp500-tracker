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

# ─── 1. CONFIGURATIE & WATCHLIST BEHEER ───────────────────────
CONFIG_PATH = "config.json"

def load_config():
    # Dit zijn je standaard tickers als het bestand leeg is of ontbreekt
    defaults = {
        "watchlist": ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META"], 
        "intraday_ratio": 3.0
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved_data = json.load(f)
                # Alleen overschrijven als er echt tickers in de file staan
                if saved_data.get("watchlist"):
                    defaults["watchlist"] = saved_data["watchlist"]
                if saved_data.get("intraday_ratio"):
                    defaults["intraday_ratio"] = saved_data["intraday_ratio"]
        except: 
            pass
    return defaults

# Zorg dat de configuratie in de sessie geladen wordt
if 'cfg' not in st.session_state:
    st.session_state.cfg = load_config()

# Helper functie om wijzigingen direct op te slaan
def sync_config():
    with open(CONFIG_PATH, "w") as f:
        json.dump({
            "watchlist": st.session_state.cfg["watchlist"], 
            "intraday_ratio": st.session_state.cfg["intraday_ratio"]
        }, f)

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
    st.header("📋 Watchlist Beheer")
    
    # 1. Ticker Toevoegen
    with st.expander("➕ Ticker Toevoegen", expanded=True):
        new_t = st.text_input("Symbool (bijv. TSLA)").upper().strip()
        if st.button("Toevoegen"):
            if new_t and new_t not in st.session_state.cfg["watchlist"]:
                st.session_state.cfg["watchlist"].append(new_t)
                sync_config() # Sla op naar config.json
                st.rerun()

    # 2. Lijst tonen en verwijderen
    st.write("---")
    st.subheader("Huidige lijst")
    # HIER zat de fout, nu gecorrigeerd naar st.session_state.cfg["watchlist"]
    for t in sorted(st.session_state.cfg["watchlist"]):
        cols = st.columns([3, 1])
        cols[0].write(t)
        if cols[1].button("🗑️", key=f"del_{t}"):
            st.session_state.cfg["watchlist"].remove(t)
            sync_config() # Sla op naar config.json
            st.rerun()

    st.write("---")
    # Ratio aanpassen binnen de cfg
    st.session_state.cfg["intraday_ratio"] = st.slider(
        "Spike Ratio", 1.0, 10.0, float(st.session_state.cfg["intraday_ratio"])
    )

# ─── 4. MAIN DASHBOARD ────────────────────────────────────────
st.markdown("<h1 class='main-header'>⚡ Volume Spike Explorer</h1>", unsafe_allow_html=True)

# STAP 1: Definieer de kolommen en de variabelen
c1, c2, c3 = st.columns([1, 1, 1])

with c1:
    # Hier maken we 'sel_ticker' aan
    sel_ticker = st.selectbox("Ticker", st.session_state.cfg["watchlist"])

with c2:
    # Hier maken we 'sel_period' aan
    sel_period = st.selectbox("Tijdsbestek", ["1d", "5d", "1mo", "6mo", "1y", "max"], index=1)

with c3:
    # Hier maken we 'sel_interval' aan
    sel_interval = st.selectbox("Detail (Zoom)", ["1m", "5m", "15m", "60m", "1d", "1wk"], index=2)

# STAP 2: Nu pas de data ophalen (nu sel_ticker, sel_period en sel_interval bestaan)
with st.spinner(f"Ophalen van {sel_ticker}..."):
    hist_df, error = get_data_safe(sel_ticker, sel_period, sel_interval)

# STAP 3: De rest van de verwerking (Plotten en Metrics)
if error:
    st.error(f"⚠️ {error}")
elif hist_df is not None:
    # 1. FIX: Kolommen platslaan voor Multi-index (Yahoo Finance update)
    if isinstance(hist_df.columns, pd.MultiIndex):
        hist_df.columns = hist_df.columns.get_level_values(0)
    
    # Maak index (tijd) bruikbaar
    hist_df = hist_df.reset_index()
    time_col = hist_df.columns[0] 

    # 2. SUBPLOTS AANMAKEN (Prijs boven, Volume onder)
    from plotly.subplots import make_subplots
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.05, 
        row_heights=[0.7, 0.3]
    )

    # 3. PRIJS GRAFIEK (Rij 1)
    fig.add_trace(
        go.Scatter(
            x=hist_df[time_col], 
            y=hist_df['Close'], 
            name="Prijs",
            line=dict(color='#00d4ff', width=2),
            fill='tozeroy',
            fillcolor='rgba(0, 212, 255, 0.1)'
        ),
        row=1, col=1
    )

    # 4. VOLUME GRAFIEK (Rij 2)
    colors = ['#4a5568'] * (len(hist_df) - 1) + ['#ffc107']
    fig.add_trace(
        go.Bar(
            x=hist_df[time_col], 
            y=hist_df['Volume'], 
            name="Volume",
            marker_color=colors,
            opacity=0.8
        ),
        row=2, col=1
    )

    # 5. WEEKENDEN & NACHTEN VERBERGEN + DAGSCHEIDINGEN
    # We voegen een verticale lijn toe bij elke nieuwe openingsbel (09:30 of 09:00)
    for timestamp in hist_df[time_col]:
        if timestamp.hour == 9 and (timestamp.minute == 30 or timestamp.minute == 0):
            fig.add_vline(
                x=timestamp, 
                line_width=1, 
                line_dash="dash", 
                line_color="rgba(255, 255, 255, 0.3)",
                row="all", col=1
            )

    # 6. LAYOUT CONFIGURATIE
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),           # Sla weekenden over
            dict(bounds=[16, 9.5], pattern="hour") # Sla nachten over (NYSE tijden)
        ]
    )

    fig.update_layout(
        template="plotly_dark",
        height=600,
        xaxis_rangeslider_visible=True,
        xaxis_rangeslider_thickness=0.05,
        margin=dict(l=0, r=0, t=30, b=0),
        showlegend=False
    )

    # Automatische zoom op prijs (Rij 1)
    fig.update_yaxes(title_text="Prijs ($)", row=1, col=1, fixedrange=False, autorange=True)
    fig.update_yaxes(title_text="Volume", row=2, col=1, fixedrange=False)

    # 7. TOON DE GRAFIEK
    st.plotly_chart(fig, use_container_width=True)

    # --- Hierna volgen je metrics (current_ratio, m1, m2, etc.) ---
    
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
