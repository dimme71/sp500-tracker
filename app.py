import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import requests
from datetime import datetime
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ─── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="⚡ 15m Spike Visualizer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS ────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .main-header { color: #00d4ff; font-size: 2.2rem; font-weight: 700; margin-bottom: 0; }
    .card { 
        background: #1a1d27; 
        border-radius: 12px; 
        padding: 1.2rem; 
        border: 1px solid #3f444e; 
        margin-bottom: 1rem;
    }
    .price-up { color: #00ff87; font-size: 1.5rem; font-weight: 800; }
    .price-down { color: #ff3e3e; font-size: 1.5rem; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# ─── Config Laden ──────────────────────────────────────────────
CONFIG_PATH = "config.json"

def load_config():
    config = {"watchlist": ["AAPL", "MSFT", "NVDA", "TSLA"], "intraday_ratio": 3.0}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                config.update(json.load(f))
        except: pass
    config["telegram_token"] = st.secrets.get("telegram_token", "")
    config["telegram_chat_id"] = st.secrets.get("telegram_chat_id", "")
    return config

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump({"watchlist": cfg["watchlist"], "intraday_ratio": cfg["intraday_ratio"]}, f)

config = load_config()

# ─── Plot Functie ──────────────────────────────────────────────
def plot_volume_spike(t_df, ticker):
    """Maakt een grafiek van volume over tijd (15m bars)."""
    # Kleuren bepalen: de laatste bar (de potentiële spike) is goud
    colors = ['#00d4ff'] * (len(t_df) - 1) + ['#ffc107']
    
    fig = go.Figure(data=[
        go.Bar(
            x=t_df.index,
            y=t_df['Volume'],
            marker_color=colors,
            name="Volume"
        )
    ])
    
    # Gemiddelde lijn toevoegen
    avg_v = t_df['Volume'].iloc[:-1].mean()
    fig.add_hline(y=avg_v, line_dash="dash", line_color="#ff4b4b", 
                  annotation_text="Gemiddelde", annotation_position="top left")

    fig.update_layout(
        title=f"Volume Verloop: {ticker} (15m)",
        template="plotly_dark",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis_title="Tijdstip",
        yaxis_title="Volume",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
    )
    return fig

# ─── Data Engine ───────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_spike_data(tickers):
    if not tickers: return pd.DataFrame(), {}
    try:
        data = yf.download(tickers, period="1d", interval="15m", group_by="ticker", progress=False)
        results = []
        raw_dfs = {}
        
        for t in tickers:
            try:
                t_df = data[t].dropna() if len(tickers) > 1 else data.dropna()
                if len(t_df) < 3: continue
                
                raw_dfs[t] = t_df
                latest = t_df.iloc[-1]
                prev_avg = t_df.iloc[:-1]['Volume'].mean()
                ratio = latest['Volume'] / prev_avg if prev_avg > 0 else 1
                
                results.append({
                    "Ticker": t,
                    "Prijs": round(float(latest['Close']), 2),
                    "Ratio": round(ratio, 2),
                    "Volume": int(latest['Volume']),
                    "Spike": ratio >= config["intraday_ratio"]
                })
            except: continue
        return pd.DataFrame(results).sort_values("Ratio", ascending=False), raw_dfs
    except: return pd.DataFrame(), {}

# ─── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Instellingen")
    config["intraday_ratio"] = st.slider("Spike Drempel (Ratio)", 1.0, 10.0, float(config["intraday_ratio"]), 0.5)
    
    new_t = st.text_input("Voeg Ticker toe").upper().strip()
    if st.button("➕"):
        if new_t and new_t not in config["watchlist"]:
            config["watchlist"].append(new_t)
            save_config(config)
            st.rerun()
    
    if st.button("💾 Opslaan"): save_config(config)
    if st.button("🗑️ Reset Lijst"):
        save_config({"watchlist": [], "intraday_ratio": 3.0})
        st.rerun()

# ─── Main UI ───────────────────────────────────────────────────
st.markdown("<h1 class='main-header'>⚡ Volume Spike Visualizer</h1>", unsafe_allow_html=True)

df, raw_data = get_spike_data(config["watchlist"])

if not df.empty:
    # Sectie voor gedetecteerde spikes
    spikes = df[df["Spike"] == True]
    
    if not spikes.empty:
        st.subheader(f"🚨 Gedetecteerde Spikes ({len(spikes)})")
        for _, row in spikes.iterrows():
            ticker = row['Ticker']
            with st.container():
                col_info, col_chart = st.columns([1, 2])
                with col_info:
                    st.markdown(f"""
                    <div class='card'>
                        <h3>{ticker}</h3>
                        <div class='price-up'>${row['Prijs']}</div>
                        <p>Ratio: <b>{row['Ratio']}x</b><br>
                        Volume: {row['Volume']:,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col_chart:
                    st.plotly_chart(plot_volume_spike(raw_data[ticker], ticker), use_container_width=True)
    
    # Overzichtstabel
    st.markdown("---")
    st.subheader("📊 Alle Tickers")
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("Geen data gevonden. Voeg tickers toe of wacht op de marktopening.")

st_autorefresh(interval=60 * 1000, key="refresh")
