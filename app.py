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
    .main-header { color: #00d4ff; font-size: 2.2rem; font-weight: 700; margin-bottom: 0; }
    .sub-header { color: #a0aec0; font-size: 1rem; margin-bottom: 1.5rem; }
    
    .card { 
        background: #1a1d27; 
        border-radius: 12px; 
        padding: 1.5rem; 
        border: 1px solid #3f444e; 
        margin-bottom: 1rem;
    }
    .card h3 { color: #ffffff !important; margin-top: 0; }
    
    .price-up { color: #00ff87; font-size: 1.8rem; font-weight: 800; }
    .price-down { color: #ff3e3e; font-size: 1.8rem; font-weight: 800; }
    
    label { color: #ffffff !important; font-weight: 600; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 600; }
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

# ─── Telegram Functies ─────────────────────────────────────────
def send_telegram(msg):
    if config["telegram_token"] and config["telegram_chat_id"]:
        try:
            url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
            response = requests.post(url, json={
                "chat_id": config["telegram_chat_id"], 
                "text": msg, 
                "parse_mode": "HTML"
            }, timeout=5)
            return response.status_code == 200
        except Exception as e:
            st.sidebar.error(f"Telegram Fout: {e}")
            return False
    return False

# ─── Data Engine ───────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_market_data(tickers):
    if not tickers: return pd.DataFrame()
    try:
        data = yf.download(tickers, period="5d", interval="1d", group_by="ticker", progress=False)
        results = []
        for t in tickers:
            try:
                t_df = data[t] if len(tickers) > 1 else data
                if t_df.empty or len(t_df) < 2: continue
                latest, prev = t_df.iloc[-1], t_df.iloc[-2]
                price = float(latest['Close'])
                change = price - float(prev['Close'])
                vol, avg_vol = int(latest['Volume']), int(t_df['Volume'].mean())
                ratio = vol / avg_vol if avg_vol > 0 else 1
                results.append({
                    "Ticker": t, "Prijs": round(price, 2), "Verschil": round(change, 2), 
                    "Pct": round((change / prev['Close']) * 100, 2), "Volume": vol, 
                    "Ratio": round(ratio, 2), "Status": "🚨 ALERT" if ratio >= config["volume_threshold"] else "✅ Normaal"
                })
            except: continue
        return pd.DataFrame(results).sort_values("Ratio", ascending=False)
    except: return pd.DataFrame()

# ─── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Instellingen")
    
    with st.expander("➕ Ticker Toevoegen", expanded=True):
        quick_add = st.text_input("Symbool").upper().strip()
        if st.button("Toevoegen"):
            if quick_add and quick_add not in config["watchlist"]:
                config["watchlist"].append(quick_add)
                save_config(config)
                st.rerun()

    with st.expander("🤖 Telegram Configuratie", expanded=False):
        t_token = st.text_input("Bot Token", value=config["telegram_token"], type="password")
        t_id = st.text_input("Chat ID", value=config["telegram_chat_id"])
        
        if st.button("💾 Telegram Opslaan"):
            config["telegram_token"] = t_token
            config["telegram_chat_id"] = t_id
            save_config(config)
            st.success("Configuratie opgeslagen!")
            
        st.markdown("---")
        if st.button("📨 Test Bericht Verzenden"):
            if t_token and t_id:
                test_msg = f"<b>🔔 Test Bericht</b>\nDe Stock Tracker verbinding werkt!\nTijd: {datetime.now().strftime('%H:%M:%S')}"
                if send_telegram(test_msg):
                    st.success("✅ Test verzonden! Check je Telegram.")
                else:
                    st.error("❌ Verzenden mislukt. Controleer je Token/ID.")
            else:
                st.warning("Vul eerst je Token en Chat ID in.")

    if st.button("🗑️ Wis Gehele Watchlist"):
        config["watchlist"] = []
        save_config(config)
        st.rerun()

# ─── Main UI ───────────────────────────────────────────────────
st.markdown("<h1 class='main-header'>📈 Watchlist Scanner</h1>", unsafe_allow_html=True)
df = get_market_data(config["watchlist"])

if not df.empty:
    # Cards
    top_df = df.head(config["top_n"])
    cols = st.columns(len(top_df))
    for i, (_, row) in enumerate(top_df.iterrows()):
        with cols[i]:
            c_class = "price-up" if row['Verschil'] >= 0 else "price-down"
            st.markdown(f"""
            <div class='card'>
                <h3>{row['Ticker']} <span style='color:#00d4ff;'>{row['Ratio']}x</span></h3>
                <div class='{c_class}'>${row['Prijs']:.2f}</div>
                <div style='color:#cbd5e1;'>{row['Pct']:+.2f}%</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("### 📊 Alle Resultaten")
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("Watchlist is leeg. Gebruik de sidebar om tickers toe te voegen.")

st_autorefresh(interval=config["check_interval_minutes"] * 60 * 1000, key="mkt_refresh")
