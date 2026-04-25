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
    page_title="Stock Tracker Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS (Optimale Leesbaarheid) ────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .main-header { color: #00d4ff; font-size: 2.2rem; font-weight: 700; margin-bottom: 0; }
    .sub-header { color: #cbd5e1; font-size: 1rem; margin-bottom: 1.5rem; }
    
    /* Cards */
    .card { 
        background: #1a1d27; 
        border-radius: 12px; 
        padding: 1.5rem; 
        border: 1px solid #3f444e; 
        margin-bottom: 1rem;
    }
    .card h3 { color: #ffffff !important; margin-top: 0; font-size: 1.2rem; }
    
    /* Prijzen & Cijfers */
    .price-up { color: #00ff87; font-size: 1.8rem; font-weight: 800; }
    .price-down { color: #ff3e3e; font-size: 1.8rem; font-weight: 800; }
    .text-bright { color: #ffffff !important; }
    .text-muted { color: #94a3b8 !important; }

    /* Input velden */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        background-color: #1a1d27 !important;
        color: #ffffff !important;
        border: 1px solid #3f444e !important;
    }
</style>
""", unsafe_allow_html=True)

# ─── Config & Secrets Laden ────────────────────────────────────
CONFIG_PATH = "config.json"

def load_config():
    # Basis watchlist
    config = {"watchlist": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"], "volume_threshold": 2.0, "top_n": 3}
    
    # Laad watchlist uit lokaal bestand als het bestaat
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
                config.update(saved)
        except: pass
    
    # Telegram info direct uit Secrets (geen fallback nodig)
    config["telegram_token"] = st.secrets.get("telegram_token", "")
    config["telegram_chat_id"] = st.secrets.get("telegram_chat_id", "")
    return config

def save_watchlist(watchlist):
    # Sla alleen de watchlist op, secrets blijven in de cloud
    with open(CONFIG_PATH, "w") as f:
        json.dump({"watchlist": watchlist}, f, indent=2)

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

# ─── Data Engine ───────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_data(tickers):
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
                    "Ratio": round(ratio, 2), "Alert": ratio >= config["volume_threshold"]
                })
            except: continue
        return pd.DataFrame(results).sort_values("Ratio", ascending=False)
    except: return pd.DataFrame()

# ─── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("📋 Watchlist Beheer")
    
    # 1. Enkele ticker toevoegen
    new_t = st.text_input("Snel toevoegen", placeholder="bijv. TSLA").upper().strip()
    if st.button("➕ Voeg Toe"):
        if new_t and new_t not in config["watchlist"]:
            config["watchlist"].append(new_t)
            save_watchlist(config["watchlist"])
            st.rerun()

    # 2. Bulk bewerken
    with st.expander("📝 Bewerk volledige lijst"):
        wl_text = st.text_area("Tickers (komma-gescheiden)", value=", ".join(config["watchlist"]))
        if st.button("💾 Lijst Opslaan"):
            config["watchlist"] = [x.strip().upper() for x in wl_text.split(",") if x.strip()]
            save_watchlist(config["watchlist"])
            st.rerun()

    st.markdown("---")
    st.header("🤖 Telegram")
    if config["telegram_token"]:
        st.success("✅ Secrets geladen")
        if st.button("📨 Test Bericht"):
            if send_telegram("<b>Test:</b> Streamlit Secrets koppeling werkt!"):
                st.toast("Bericht verzonden!")
            else: st.error("Fout bij verzenden.")
    else:
        st.error("❌ Geen Secrets gevonden")

    if st.button("🗑️ Wis Alles"):
        save_watchlist([])
        st.rerun()

# ─── Dashboard UI ──────────────────────────────────────────────
st.markdown("<h1 class='main-header'>📈 Watchlist Scanner</h1>", unsafe_allow_html=True)
st.markdown(f"<p class='sub-header'>Laatste update: {datetime.now().strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)

df = get_data(config["watchlist"])

if not df.empty:
    # Top Cards
    top_n = min(len(df), config["top_n"])
    cols = st.columns(top_n)
    for i in range(top_n):
        row = df.iloc[i]
        with cols[i]:
            c_class = "price-up" if row['Verschil'] >= 0 else "price-down"
            st.markdown(f"""
            <div class='card'>
                <h3 class='text-bright'>{row['Ticker']} <span style='color:#00d4ff;'>{row['Ratio']}x</span></h3>
                <div class='{c_class}'>${row['Prijs']:.2f}</div>
                <div class='{c_class}' style='font-size:1rem;'>{row['Pct']:+.2f}%</div>
                <div class='text-muted' style='font-size:0.8rem;'>Vol: {row['Volume']:,}</div>
            </div>
            """, unsafe_allow_html=True)

    # Tabel
    st.markdown("### 📊 Overzicht")
    st.dataframe(df.drop(columns="Alert"), use_container_width=True, hide_index=True)
else:
    st.info("Voeg tickers toe in de sidebar om te beginnen.")

# Refresh
st_autorefresh(interval=15 * 60 * 1000, key="auto")
