import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ─── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="15m Volume Spike Tracker",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS (Contrast & Helderheid) ────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .main-header { color: #00d4ff; font-size: 2.2rem; font-weight: 700; margin-bottom: 0; }
    .sub-header { color: #cbd5e1; font-size: 1rem; margin-bottom: 1.5rem; }
    .card { 
        background: #1a1d27; 
        border-radius: 12px; 
        padding: 1.5rem; 
        border: 1px solid #3f444e; 
        margin-bottom: 1rem;
    }
    .card h3 { color: #ffffff !important; margin-top: 0; font-size: 1.2rem; }
    .price-up { color: #00ff87; font-size: 1.8rem; font-weight: 800; }
    .price-down { color: #ff3e3e; font-size: 1.8rem; font-weight: 800; }
    .text-muted { color: #94a3b8 !important; }
    .stTextInput>div>div>input { background-color: #1a1d27 !important; color: #ffffff !important; }
</style>
""", unsafe_allow_html=True)

# ─── Config & Secrets ──────────────────────────────────────────
CONFIG_PATH = "config.json"

def load_config():
    config = {
        "watchlist": ["AAPL", "MSFT", "NVDA", "TSLA", "AMD"], 
        "intraday_ratio": 3.0, 
        "top_n": 3
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
                config.update(saved)
        except: pass
    
    config["telegram_token"] = st.secrets.get("telegram_token", "")
    config["telegram_chat_id"] = st.secrets.get("telegram_chat_id", "")
    return config

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        # Sla alleen relevante instellingen op, geen secrets
        json.dump({
            "watchlist": cfg["watchlist"], 
            "intraday_ratio": cfg["intraday_ratio"],
            "top_n": cfg["top_n"]
        }, f, indent=2)

config = load_config()

# ─── Telegram Functie ──────────────────────────────────────────
def send_telegram(msg):
    token = config.get("telegram_token")
    chat_id = config.get("telegram_chat_id")
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
            return True
        except: return False
    return False

# ─── 15m Data Engine ───────────────────────────────────────────
@st.cache_data(ttl=60) # Kortere cache voor intraday data
def get_intraday_data(tickers):
    if not tickers: return pd.DataFrame()
    try:
        # Haal 15-minuten data op van vandaag
        data = yf.download(tickers, period="1d", interval="15m", group_by="ticker", progress=False)
        results = []
        
        for t in tickers:
            try:
                t_df = data[t] if len(tickers) > 1 else data
                t_df = t_df.dropna()
                
                if len(t_df) < 3: continue
                
                latest_bar = t_df.iloc[-1]
                previous_bars = t_df.iloc[:-1] # Alle bars behalve de laatste
                
                current_vol = int(latest_bar['Volume'])
                avg_vol = int(previous_bars['Volume'].mean())
                
                # Ratio berekening
                ratio = current_vol / avg_vol if avg_vol > 0 else 1
                
                price = float(latest_bar['Close'])
                prev_price = float(previous_bars.iloc[-1]['Close'])
                change_pct = ((price - prev_price) / prev_price) * 100
                
                results.append({
                    "Ticker": t,
                    "Prijs": round(price, 2),
                    "15m Pct": round(change_pct, 2),
                    "Volume": current_vol,
                    "Gem. Vol": avg_vol,
                    "Ratio": round(ratio, 2),
                    "Spike": ratio >= config["intraday_ratio"]
                })
            except: continue
            
        return pd.DataFrame(results).sort_values("Ratio", ascending=False)
    except: return pd.DataFrame()

# ─── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚡ Detectie Instellingen")
    
    # Ratio instelling
    new_ratio = st.slider("Minimale 15m Ratio", 1.0, 15.0, float(config["intraday_ratio"]), 0.5)
    if new_ratio != config["intraday_ratio"]:
        config["intraday_ratio"] = new_ratio
        save_config(config)
        st.rerun()

    with st.expander("📋 Watchlist"):
        new_t = st.text_input("Ticker toevoegen").upper().strip()
        if st.button("➕"):
            if new_t and new_t not in config["watchlist"]:
                config["watchlist"].append(new_t)
                save_config(config)
                st.rerun()
        
        wl_text = st.text_area("Bewerk lijst", value=", ".join(config["watchlist"]))
        if st.button("💾 Opslaan"):
            config["watchlist"] = [x.strip().upper() for x in wl_text.split(",") if x.strip()]
            save_config(config)
            st.rerun()

    st.markdown("---")
    if st.button("📨 Test Telegram"):
        send_telegram("⚡ <b>Volume Tracker:</b> Testbericht succesvol.")
        st.toast("Verzonden!")

# ─── Dashboard UI ──────────────────────────────────────────────
st.markdown("<h1 class='main-header'>⚡ 15m Volume Spike Tracker</h1>", unsafe_allow_html=True)
st.markdown(f"<p class='sub-header'>Vergelijkt huidig kwartier met daggemiddelde · Check elke minuut</p>", unsafe_allow_html=True)

df = get_intraday_data(config["watchlist"])

if not df.empty:
    # Spike Cards
    spikes = df[df["Spike"] == True]
    if not spikes.empty:
        st.markdown(f"### 🚨 {len(spikes)} Volume Spikes Gevonden!")
        cols = st.columns(min(len(spikes), 4))
        for i, (_, row) in enumerate(spikes.head(4).iterrows()):
            with cols[i]:
                color = "price-up" if row['15m Pct'] >= 0 else "price-down"
                st.markdown(f"""
                <div class='card'>
                    <h3>{row['Ticker']} <span style='color:#00d4ff;'>{row['Ratio']}x</span></h3>
                    <div class='{color}'>${row['Prijs']:.2f}</div>
                    <div class='{color}' style='font-size:1rem;'>{row['15m Pct']:+.2f}% (15m)</div>
                </div>
                """, unsafe_allow_html=True)
                
                # Optioneel: Automatisch Telegram sturen (Let op: kan spammen bij elke refresh)
                # msg = f"🚨 <b>SPIKE</b>: {row['Ticker']}\nRatio: {row['Ratio']}x\nPrijs: ${row['Prijs']}"
                # send_telegram(msg)

    st.markdown("### 📊 Alle Live Data (15m Interval)")
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("Wachten op marktdata of de markt is momenteel gesloten.")

# Kortere autorefresh voor intraday (elke 60 seconden)
st_autorefresh(interval=60 * 1000, key="intraday_refresh")
