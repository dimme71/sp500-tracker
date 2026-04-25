import streamlit as st
import yfinance as yf
import pandas as pd
import time
import json
import os
import requests
from datetime import datetime, timedelta
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ─── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="S&P 500 Top 3 Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─── Custom CSS ────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .main-header { color: #00d4ff; font-size: 2.2rem; font-weight: 700; margin-bottom: 0; }
    .sub-header { color: #8892b0; font-size: 0.9rem; margin-bottom: 1.5rem; }
    .card { background: #1a1d27; border-radius: 12px; padding: 1.2rem; border: 1px solid #2a2d3a; margin-bottom: 0.8rem; }
    .card h3 { color: #ccd6f6; font-size: 1rem; margin: 0 0 0.3rem 0; }
    .price-up { color: #00c853; font-size: 1.4rem; font-weight: 700; }
    .price-down { color: #ff1744; font-size: 1.4rem; font-weight: 700; }
    .change-up { color: #00c853; font-size: 0.85rem; }
    .change-down { color: #ff1744; font-size: 0.85rem; }
    .volume-text { color: #8892b0; font-size: 0.8rem; }
    .badge { display: inline-block; background: #00d4ff22; color: #00d4ff; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; margin-left: 6px; }
    .stButton>button { background: #00d4ff; color: #0e1117; font-weight: 600; border-radius: 8px; }
    .stTextInput>div>div>input { background: #1a1d27; color: #ccd6f6; border: 1px solid #2a2d3a; border-radius: 8px; }
    .stSelectbox>div>div>select { background: #1a1d27; color: #ccd6f6; border: 1px solid #2a2d3a; }
    .watchlist-tag { display: inline-block; background: #1a1d27; color: #ccd6f6; padding: 4px 10px; border-radius: 6px; margin: 2px; border: 1px solid #2a2d3a; font-size: 0.8rem; }
    .footer { color: #4a5568; font-size: 0.7rem; text-align: center; margin-top: 2rem; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; }
    @media (max-width: 768px) {
        .main-header { font-size: 1.5rem; }
        .price-up, .price-down { font-size: 1.1rem; }
    }
</style>
""", unsafe_allow_html=True)

# ─── Config laden ──────────────────────────────────────────────
CONFIG_PATH = "config.json"

@st.cache_data(ttl=60)
def load_config():
    config = {}
    
    # Streamlit Secrets hebben voorrang (cloud deployment)
    if hasattr(st, "secrets") and st.secrets:
        config["telegram_token"] = st.secrets.get("telegram_token", "")
        config["telegram_chat_id"] = st.secrets.get("telegram_chat_id", "")
    else:
        config["telegram_token"] = ""
        config["telegram_chat_id"] = ""
    
    # Config.json als fallback voor lokale development
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            file_config = json.load(f)
        # Alleen niet-telegram values uit file, tenzij secrets leeg zijn
        config["watchlist"] = file_config.get("watchlist", ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"])
        config["volume_threshold"] = file_config.get("volume_threshold", 2.0)
        config["check_interval_minutes"] = file_config.get("check_interval_minutes", 15)
        config["top_n"] = file_config.get("top_n", 3)
        # Telegram uit file alleen als secrets niet beschikbaar zijn
        if not config["telegram_token"]:
            config["telegram_token"] = file_config.get("telegram_token", "")
            config["telegram_chat_id"] = file_config.get("telegram_chat_id", "")
    else:
        config.setdefault("watchlist", ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"])
        config.setdefault("volume_threshold", 2.0)
        config.setdefault("check_interval_minutes", 15)
        config.setdefault("top_n", 3)
    
    return config


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    st.cache_data.clear()

config = load_config()

# ─── S&P 500 lijst ─────────────────────────────────────────────
SP500_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "BRK.B", "LLY", "AVGO", "JPM",
    "V", "TSLA", "XOM", "UNH", "MA", "PG", "JNJ", "COST", "HD", "ORCL",
    "ABBV", "CVX", "MRK", "KO", "BAC", "CRM", "PEP", "ADBE", "WMT", "NFLX",
    "TMO", "ACN", "MCD", "CSCO", "DIS", "ABT", "AMD", "CMCSA", "QCOM", "VZ",
    "INTU", "TXN", "AMGN", "CAT", "IBM", "PM", "GE", "NEE", "GS", "BA",
    "MS", "SPGI", "RTX", "HON", "LOW", "ISRG", "BLK", "PLD", "AMAT", "T",
    "SYK", "LMT", "TJX", "UNP", "ELV", "MDT", "DE", "AXP", "SBUX", "ADP",
    "GILD", "MMC", "C", "BSX", "SCHW", "TMUS", "BMY", "UPS", "CB", "ADI",
    "CI", "MDLZ", "AMT", "REGN", "MO", "NKE", "DUK", "SO", "ICE", "INTC",
    "CL", "WM", "ZTS", "SHW", "PH", "EOG", "PGR", "ITW", "MCO", "PNC"
]

# ─── Data fetching ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_sp500_data():
    """Haal data op voor de top N S&P 500 op basis van volume-afwijking."""
    tickers = config.get("watchlist", SP500_TICKERS[:20])
    top_n = config.get("top_n", 3)
    vol_threshold = config.get("volume_threshold", 2.0)

    try:
        data = yf.download(
            tickers,
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            auto_adjust=True
        )

        results = []
        for t in tickers:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    t_data = data[t]
                else:
                    t_data = data

                if t_data.empty or len(t_data) < 2:
                    continue

                latest = t_data.iloc[-1]
                prev = t_data.iloc[-2]

                price = float(latest.get("Close", latest.get("Adj Close", 0)))
                prev_close = float(prev.get("Close", prev.get("Adj Close", 0)))
                change = price - prev_close
                change_pct = (change / prev_close) * 100 if prev_close else 0
                volume = int(latest.get("Volume", 0))

                # Volume gemiddelde (5 dagen)
                avg_volume = int(t_data["Volume"].mean()) if "Volume" in t_data.columns else 1
                vol_ratio = volume / avg_volume if avg_volume else 1

                results.append({
                    "ticker": t,
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": volume,
                    "avg_volume": avg_volume,
                    "vol_ratio": round(vol_ratio, 2),
                    "high_volume": vol_ratio >= vol_threshold
                })
            except Exception:
                continue

        df = pd.DataFrame(results)
        if df.empty:
            return pd.DataFrame()

        # Sorteer op volume-afwijking (hoogste eerst)
        df = df.sort_values("vol_ratio", ascending=False).head(top_n * 3)
        return df

    except Exception as e:
        st.error(f"Fout bij ophalen data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_ticker_info(ticker):
    """Haal bedrijfsinformatie op."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "name": info.get("shortName", info.get("longName", ticker)),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A")
        }
    except:
        return {"name": ticker, "sector": "N/A", "industry": "N/A"}

# ─── Telegram notificatie ──────────────────────────────────────
def send_telegram(msg):
    token = config.get("telegram_token", "")
    chat_id = config.get("telegram_chat_id", "")
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
        except:
            pass

# ─── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Instellingen")

    with st.expander("📋 Watchlist", expanded=True):
        current_watchlist = config.get("watchlist", [])
        watchlist_str = st.text_area(
            "Tickers (komma-gescheiden)",
            value=", ".join(current_watchlist),
            height=100,
            help="Bijv: AAPL, MSFT, NVDA, GOOGL, AMZN"
        )
        new_watchlist = [t.strip().upper() for t in watchlist_str.split(",") if t.strip()]
        if new_watchlist and new_watchlist != current_watchlist:
            config["watchlist"] = new_watchlist
            save_config(config)
            st.success(f"✅ Watchlist bijgewerkt ({len(new_watchlist)} tickers)")

        st.markdown("**Huidige watchlist:**")
        cols = st.columns(3)
        for i, t in enumerate(current_watchlist[:9]):
            cols[i % 3].markdown(f"<span class='watchlist-tag'>{t}</span>", unsafe_allow_html=True)
        if len(current_watchlist) > 9:
            st.caption(f"...en {len(current_watchlist) - 9} meer")

    with st.expander("📊 Criteria", expanded=True):
        new_top_n = st.number_input("Top N resultaten", min_value=1, max_value=20, value=config.get("top_n", 3))
        new_vol_threshold = st.slider("Volume drempel (x gemiddelde)", 1.0, 10.0, config.get("volume_threshold", 2.0), 0.1)
        if new_top_n != config.get("top_n") or new_vol_threshold != config.get("volume_threshold"):
            config["top_n"] = new_top_n
            config["volume_threshold"] = new_vol_threshold
            save_config(config)

    with st.expander("🤖 Telegram", expanded=False):
        new_token = st.text_input("Bot Token", value=config.get("telegram_token", ""), type="password")
        new_chat_id = st.text_input("Chat ID", value=config.get("telegram_chat_id", ""))
        if new_token != config.get("telegram_token") or new_chat_id != config.get("telegram_chat_id"):
            config["telegram_token"] = new_token
            config["telegram_chat_id"] = new_chat_id
            save_config(config)
            st.success("✅ Telegram config opgeslagen")

        if st.button("📨 Test notificatie", use_container_width=True):
            test_msg = f"<b>✅ S&P 500 Tracker Test</b>\n\nBot werkt correct! 🎉\nTijd: {datetime.now().strftime('%H:%M:%S')}"
            send_telegram(test_msg)
            st.success("Test notificatie verzonden!")

    st.markdown("---")
    st.markdown(f"<div class='footer'>Laatste update: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
    if st.button("🔄 Verversen", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ─── Auto-refresh ──────────────────────────────────────────────
refresh_interval = config.get("check_interval_minutes", 15) * 60 * 1000
st_autorefresh(interval=refresh_interval, key="auto_refresh")

# ─── Main content ──────────────────────────────────────────────
st.markdown("<h1 class='main-header'>📈 S&P 500 Top 3 Tracker</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-header'>Live volume-afwijking monitoring · Automatische notificaties</p>", unsafe_allow_html=True)

# Metrics row
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Watchlist", f"{len(config.get('watchlist', []))} stocks")
with col2:
    st.metric("Volume drempel", f"{config.get('volume_threshold', 2.0)}x")
with col3:
    st.metric("Top N", config.get("top_n", 3))
with col4:
    telegram_status = "✅ Aan" if config.get("telegram_token") else "❌ Uit"
    st.metric("Telegram", telegram_status)

# ─── Data ophalen ──────────────────────────────────────────────
with st.spinner("📡 Bezig met ophalen van marktdata..."):
    df = get_sp500_data()

if df.empty:
    st.warning("⚠️ Geen data beschikbaar. De markt is mogelijk gesloten of er is een verbindingsfout.")
    st.stop()

# ─── Top 3 cards ───────────────────────────────────────────────
st.markdown("### 🏆 Top 3 — Hoogste Volume Afwijking")

top3 = df.head(3)

cols = st.columns(3)
for i, (_, row) in enumerate(top3.iterrows()):
    info = get_ticker_info(row["ticker"])
    with cols[i]:
        direction = "up" if row["change"] >= 0 else "down"
        price_class = "price-up" if direction == "up" else "price-down"
        change_class = "change-up" if direction == "up" else "change-down"
        arrow = "▲" if direction == "up" else "▼"

        st.markdown(f"""
        <div class='card'>
            <h3>{info['name']} <span class='badge'>{row['ticker']}</span></h3>
            <div class='{price_class}'>${row['price']:,.2f}</div>
            <div class='{change_class}'>{arrow} {abs(row['change']):.2f} ({abs(row['change_pct']):.2f}%)</div>
            <div class='volume-text'>Volume: {row['volume']:,} · {row['vol_ratio']:.1f}x gemiddelde</div>
        </div>
        """, unsafe_allow_html=True)

# ─── Volledige tabel ───────────────────────────────────────────
st.markdown("### 📊 Alle Resultaten")

display_df = df.copy()
display_df["price"] = display_df["price"].apply(lambda x: f"${x:,.2f}")
display_df["change"] = display_df.apply(
    lambda x: f"▲ {x['change']:.2f}" if x['change'] >= 0 else f"▼ {abs(x['change']):.2f}", axis=1
)
display_df["change_pct"] = display_df["change_pct"].apply(lambda x: f"{x:+.2f}%")
display_df["volume"] = display_df["volume"].apply(lambda x: f"{x:,}")
display_df["avg_volume"] = display_df["avg_volume"].apply(lambda x: f"{x:,}")
display_df["vol_ratio"] = display_df["vol_ratio"].apply(lambda x: f"{x:.1f}x")
display_df["high_volume"] = display_df["high_volume"].apply(lambda x: "🔴 Hoog" if x else "✅ Normaal")

display_df = display_df.rename(columns={
    "ticker": "Ticker", "price": "Prijs", "change": "Verandering",
    "change_pct": "%", "volume": "Volume", "avg_volume": "Gem. Volume",
    "vol_ratio": "Ratio", "high_volume": "Status"
})

# ─── GEFIXT: .map() i.p.v. .applymap() ────────────────────────
styled = display_df[["Ticker", "Prijs", "Verandering", "%", "Volume", "Ratio", "Status"]].style.map(
    lambda v: "color: #ff1744; font-weight: 600" if isinstance(v, str) and "🔴" in v
    else "color: #00c853; font-weight: 600" if isinstance(v, str) and "▲" in v
    else ""
)
st.dataframe(
    styled,
    use_container_width=True,
    height=400,
    column_config={
        "Ticker": st.column_config.TextColumn("Ticker", width="small"),
        "Prijs": st.column_config.TextColumn("Prijs", width="small"),
        "Verandering": st.column_config.TextColumn("Verandering", width="small"),
        "%": st.column_config.TextColumn("%", width="small"),
        "Volume": st.column_config.TextColumn("Volume", width="small"),
        "Ratio": st.column_config.TextColumn("Ratio", width="small"),
        "Status": st.column_config.TextColumn("Status", width="small"),
    }
)

# ─── Volume anomalie meldingen ─────────────────────────────────
alerts = df[df["high_volume"] == True]
if not alerts.empty:
    st.markdown("### 🔔 Volume Anomalieën")
    for _, row in alerts.iterrows():
        info = get_ticker_info(row["ticker"])
        st.info(f"**{info['name']}** ({row['ticker']}) — Volume {row['vol_ratio']:.1f}x hoger dan gemiddeld!")
        # Stuur Telegram notificatie
        msg = f"🔔 <b>Volume Anomalie</b>\n{info['name']} ({row['ticker']})\nVolume: {row['vol_ratio']:.1f}x gemiddelde\nPrijs: ${row['price']:,.2f}"
        send_telegram(msg)

# ─── Footer ────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div class='footer'>S&P 500 Top 3 Tracker · Data: Yahoo Finance · "
    f"Auto-refresh elke {config.get('check_interval_minutes', 15)} minuten</div>",
    unsafe_allow_html=True
)
