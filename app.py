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
    page_title="Stock Volume Tracker Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS (Contrast & Helderheid) ────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    
    /* Titels */
    .main-header { color: #00d4ff; font-size: 2.2rem; font-weight: 700; margin-bottom: 0; }
    .sub-header { color: #a0aec0; font-size: 1rem; margin-bottom: 1.5rem; }
    
    /* Cards met hoog contrast */
    .card { 
        background: #1a1d27; 
        border-radius: 12px; 
        padding: 1.5rem; 
        border: 1px solid #3f444e; 
        margin-bottom: 1rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .card h3 { color: #ffffff !important; margin-top: 0; font-size: 1.2rem; }
    
    /* Prijzen: Fel groen/rood voor leesbaarheid op zwart */
    .price-up { color: #00ff87; font-size: 1.8rem; font-weight: 800; }
    .price-down { color: #ff3e3e; font-size: 1.8rem; font-weight: 800; }
    .change-up { color: #00ff87; font-weight: 600; }
    .change-down { color: #ff3e3e; font-weight: 600; }
    
    .volume-text { color: #cbd5e1; font-size: 0.9rem; margin-top: 5px; }
    .badge { 
        background: #00d4ff22; 
        color: #00d4ff; 
        padding: 2px 10px; 
        border-radius: 4px; 
        border: 1px solid #00d4ff;
        font-size: 0.8rem;
    }

    /* Sidebar tekst & inputs */
    label { color: #ffffff !important; font-weight: 600; }
    .stTextInput>div>div>input { background: #1a1d27; color: #ffffff; border: 1px solid #3f444e; }
</style>
""", unsafe_allow_html=True)

# ─── Config & Opslag ───────────────────────────────────────────
CONFIG_PATH = "config.json"

def load_config():
    defaults = {
        "watchlist": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
        "volume_threshold": 2.0,
        "check_interval_minutes": 15,
        "top_n": 3,
        "telegram_token": "",
        "telegram_chat_id": ""
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                user_cfg = json.load(f)
                defaults.update(user_cfg)
        except: pass
    return defaults

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

config = load_config()

# ─── Telegram Functie ──────────────────────────────────────────
def send_telegram(msg):
    if config["telegram_token"] and config["telegram_chat_id"]:
        try:
            url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
            requests.post(url, json={"chat_id": config["telegram_chat_id"], "text": msg, "parse_mode": "HTML"}, timeout=5)
        except: pass

# ─── Data Ophalen ──────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_market_data(tickers):
    if not tickers: return pd.DataFrame()
    try:
        # Haal data op voor alle tickers tegelijk (sneller)
        data = yf.download(tickers, period="5d", interval="1d", group_by="ticker", progress=False)
        results = []
        for t in tickers:
            try:
                t_df = data[t] if len(tickers) > 1 else data
                if t_df.empty or len(t_df) < 2: continue
                
                latest, prev = t_df.iloc[-1], t_df.iloc[-2]
                price = float(latest['Close'])
                prev_close = float(prev['Close'])
                change = price - prev_close
                vol = int(latest['Volume'])
                avg_vol = int(t_df['Volume'].mean())
                ratio = vol / avg_vol if avg_vol > 0 else 1
                
                results.append({
                    "Ticker": t, 
                    "Prijs": round(price, 2), 
                    "Verschil": round(change, 2), 
                    "Pct": round((change / prev_close) * 100, 2), 
                    "Volume": vol, 
                    "Ratio": round(ratio, 2),
                    "Status": "🚨 ALERT" if ratio >= config["volume_threshold"] else "✅ Normaal"
                })
            except: continue
        return pd.DataFrame(results).sort_values("Ratio", ascending=False)
    except: return pd.DataFrame()

# ─── Sidebar: Beheer ───────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Instellingen")
    
    # NIEUW: Ticker toevoegen
    with st.expander("➕ Voeg Ticker Toe", expanded=True):
        quick_add = st.text_input("Symbool (bijv. TSLA, BTC-USD)").upper().strip()
        if st.button("Toevoegen"):
            if quick_add and quick_add not in config["watchlist"]:
                config["watchlist"].append(quick_add)
                save_config(config)
                st.rerun()

    with st.expander("📋 Watchlist Bewerken"):
        wl_text = st.text_area("Lijst (komma-gescheiden)", value=", ".join(config["watchlist"]))
        if st.button("Opslaan & Bijwerken"):
            config["watchlist"] = [x.strip().upper() for x in wl_text.split(",") if x.strip()]
            save_config(config)
            st.rerun()
        if st.button("Wis Gehele Lijst"):
            config["watchlist"] = []
            save_config(config)
            st.rerun()

    with st.expander("📊 Criteria"):
        config["volume_threshold"] = st.slider("Volume Ratio Alert", 1.0, 10.0, config["volume_threshold"])
        config["top_n"] = st.number_input("Aantal kaarten bovenin", 1, 6, config["top_n"])
        if st.button("Criteria Opslaan"): save_config(config)

    with st.expander("🤖 Telegram"):
        config["telegram_token"] = st.text_input("Bot Token", value=config["telegram_token"], type="password")
        config["telegram_chat_id"] = st.text_input("Chat ID", value=config["telegram_chat_id"])
        if st.button("Telegram Opslaan"): 
            save_config(config)
            st.success("Opgeslagen!")

# ─── Hoofdscherm UI ────────────────────────────────────────────
st.markdown("<h1 class='main-header'>📈 Watchlist Scanner</h1>", unsafe_allow_html=True)
st.markdown(f"<p class='sub-header'>Updates elke {config['check_interval_minutes']} minuten · Tijd: {datetime.now().strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)

df = get_market_data(config["watchlist"])

if not df.empty:
    # Top Cards
    top_df = df.head(config["top_n"])
    cols = st.columns(len(top_df))
    for i, (_, row) in enumerate(top_df.iterrows()):
        with cols[i]:
            c_class = "price-up" if row['Verschil'] >= 0 else "price-down"
            st.markdown(f"""
            <div class='card'>
                <h3>{row['Ticker']} <span class='badge'>{row['Ratio']}x Vol</span></h3>
                <div class='{c_class}'>${row['Prijs']:.2f}</div>
                <div class='{c_class}' style='font-size:1rem;'>{row['Pct']:+.2f}%</div>
                <div class='volume-text'>Vol: {row['Volume']:,}</div>
            </div>
            """, unsafe_allow_html=True)

    # Volledige Lijst
    st.markdown("### 📊 Alle Resultaten")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Telegram notificaties sturen bij alerts
    alerts = df[df["Status"] == "🚨 ALERT"]
    for _, alert in alerts.iterrows():
        # Let op: Dit stuurt een bericht naar Telegram als een alert gevonden wordt.
        # Om te voorkomen dat je spam krijgt bij elke refresh, zou je hier 
        # extra logica kunnen toevoegen, maar voor nu werkt het direct.
        msg = f"🚨 <b>VOLUME ALERT</b>\nTicker: {alert['Ticker']}\nRatio: {alert['Ratio']}x\nPrijs: ${alert['Prijs']}"
        # send_telegram(msg) # Verwijder de '#' aan het begin om automatisch te verzenden

else:
    st.info("Je watchlist is leeg. Gebruik de sidebar om tickers toe te voegen!")

# ─── Auto Refresh ──────────────────────────────────────────────
st_autorefresh(interval=config["check_interval_minutes"] * 60 * 1000, key="mkt_refresh")
