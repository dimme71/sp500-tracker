#!/usr/bin/env python3
"""
S&P 500 Live Tracker — Streamlit Dashboard
Gebruik: streamlit run app.py
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import yfinance as yf
import pandas as pd
import requests

# ─── Config ───────────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "watchlist": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
    "volume_threshold": 2.0,
    "check_interval_minutes": 15,
    "top_n": 3,
    "telegram_token": "",
    "telegram_chat_id": "",
    "last_notifications": {}
}

NOTIFICATION_COOLDOWN = 3600


# ─── Config beheer ────────────────────────────────────────────────────────────
def load_config() -> dict:
    cfg = {**DEFAULT_CONFIG}

    # 1. Laad lokaal config.json (voor lokale dev)
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text())
        cfg.update(data)

    # 2. Overschrijf met Streamlit Secrets (voor cloud deploy)
    try:
        secrets = st.secrets.to_dict()
        if "telegram" in secrets:
            if "token" in secrets["telegram"]:
                cfg["telegram_token"] = secrets["telegram"]["token"]
            if "chat_id" in secrets["telegram"]:
                cfg["telegram_chat_id"] = secrets["telegram"]["chat_id"]
    except Exception:
        pass  # Geen secrets beschikbaar (lokaal)

    return cfg


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ─── Data ophalen (vereenvoudigd voor Streamlit) ─────────────────────────────
@st.cache_data(ttl=300)  # 5 min cache
def get_sp500_top(n: int = 3) -> pd.DataFrame:
    tickers = [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "BRK-B", "TSLA",
        "AVGO", "JPM", "V", "LLY", "WMT", "XOM", "UNH", "MA", "PG", "JNJ",
        "COST", "HD", "ORCL", "BAC", "ABBV", "CVX", "KO", "MRK", "PEP",
        "CRM", "ADBE", "TMO", "NFLX", "AMD", "ACN", "LIN", "MCD", "CSCO",
        "ABT", "WFC", "DHR", "TXN", "QCOM", "VZ", "NEE", "IBM", "DIS",
        "INTU", "AMGN", "GE", "CAT", "SPGI", "GS", "MS", "RTX", "PFE",
        "T", "C", "LOW", "HON", "BA", "AXP", "UBER", "AMAT", "BKNG",
        "PLTR", "SYK", "MDT", "LMT", "DE", "BLK", "CB", "ADP", "GILD",
        "ADSK", "ADI", "PANW", "VRTX", "MU", "F", "GM", "SBUX", "MMM",
        "NKE", "LRCX", "KLAC", "CMG", "MRNA", "ABNB", "DASH", "SNOW",
    ]

    data = yf.download(tickers, period="2d", group_by="ticker", progress=False)

    rows = []
    for t in tickers:
        try:
            if t not in data.columns.levels[0]:
                continue
            df = data[t]
            if df.empty or "Close" not in df.columns:
                continue
            close_prices = df["Close"].dropna()
            volumes = df["Volume"].dropna()
            if close_prices.empty or volumes.empty:
                continue

            price = float(close_prices.iloc[-1])
            volume = int(volumes.iloc[-1])
            avg_volume = int(volumes.mean())
            t_info = yf.Ticker(t).info
            shares = t_info.get("sharesOutstanding", t_info.get("impliedSharesOutstanding", 0))
            market_cap = price * int(shares) if shares else 0

            # Daily change
            change = 0.0
            if len(close_prices) >= 2:
                change = round(((close_prices.iloc[-1] - close_prices.iloc[-2]) / close_prices.iloc[-2]) * 100, 2)

            rows.append({
                "Ticker": t,
                "Prijs": round(price, 2),
                "±%": change,
                "Volume": volume,
                "Gem. Volume": avg_volume,
                "xGem": round(volume / avg_volume, 2) if avg_volume > 0 else 0,
                "Mkt Cap": market_cap,
            })
        except Exception:
            continue

    df_result = pd.DataFrame(rows)
    df_result = df_result.sort_values("Mkt Cap", ascending=False).head(n)
    return df_result


@st.cache_data(ttl=300)
def get_watchlist_data(tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()

    data = yf.download(tickers, period="5d", group_by="ticker", progress=False)

    rows = []
    for t in tickers:
        try:
            if t not in data.columns.levels[0]:
                continue
            df = data[t]
            if df.empty:
                continue
            close_prices = df["Close"].dropna()
            volumes = df["Volume"].dropna()
            if close_prices.empty or volumes.empty:
                continue

            price = float(close_prices.iloc[-1])
            volume = int(volumes.iloc[-1])
            avg_volume = int(volumes.mean())

            change = 0.0
            if len(close_prices) >= 2:
                change = round(((close_prices.iloc[-1] - close_prices.iloc[-2]) / close_prices.iloc[-2]) * 100, 2)

            rows.append({
                "Ticker": t.upper(),
                "Prijs": round(price, 2),
                "±%": change,
                "Volume": volume,
                "Gem. Volume": avg_volume,
                "xGem": round(volume / avg_volume, 2) if avg_volume > 0 else 0,
            })
        except Exception:
            continue

    return pd.DataFrame(rows)


def format_market_cap(cap: float) -> str:
    if cap >= 1_000_000_000_000:
        return f"${cap/1_000_000_000_000:.2f}T"
    elif cap >= 1_000_000_000:
        return f"${cap/1_000_000_000:.2f}B"
    elif cap >= 1_000_000:
        return f"${cap/1_000_000:.2f}M"
    return f"${cap:.0f}"


def color_change(val):
    """Kleur voor ±% kolom."""
    if val > 0:
        return "color: #00c853"
    elif val < 0:
        return "color: #ff1744"
    return ""


def color_volume(val):
    """Kleur voor volume ratio — rood als boven threshold."""
    try:
        cfg = load_config()
        threshold = cfg["volume_threshold"]
        if float(val) >= threshold:
            return "background-color: #ff1744; color: white; font-weight: bold"
    except:
        pass
    return ""


def send_telegram_alert(ticker: str, price: float, volume_ratio: float, avg_volume: int, volume: int):
    """Stuur een volume-alert via Telegram."""
    cfg = load_config()
    token = cfg.get("telegram_token", "")
    chat_id = cfg.get("telegram_chat_id", "")
    if not token or not chat_id:
        return False

    # Cooldown check
    now = time.time()
    key = f"vol_{ticker}"
    last = cfg.get("last_notifications", {}).get(key, 0)
    if now - last < NOTIFICATION_COOLDOWN:
        return False  # skip, nog in cooldown

    message = (
        f"🚨 *Volume Alert!*\n\n"
        f"**{ticker}** — ${price:.2f}\n\n"
        f"📊 Volume: {volume:,}\n"
        f"📈 Gem. volume: {avg_volume:,}\n"
        f"🔥 Ratio: **x{volume_ratio:.1f}**\n\n"
        f"_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
    )

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }, timeout=10)

        if resp.status_code == 200:
            # Update cooldown
            if "last_notifications" not in cfg:
                cfg["last_notifications"] = {}
            cfg["last_notifications"][key] = now
            save_config(cfg)
            return True
    except:
        pass
    return False


def check_and_alert_volume(wl_data: pd.DataFrame):
    """Controleer watchlist op volume-anomalieën en stuur alerts."""
    cfg = load_config()
    threshold = cfg["volume_threshold"]
    alerts = wl_data[wl_data["xGem"] >= threshold]

    for _, row in alerts.iterrows():
        sent = send_telegram_alert(
            ticker=row["Ticker"],
            price=row["Prijs"],
            volume_ratio=row["xGem"],
            avg_volume=row["Gem. Volume"],
            volume=row["Volume"],
        )
        if sent:
            st.toast(f"📨 Alert verstuurd voor {row['Ticker']}!", icon="✅")


# ─── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="S&P 500 Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Title
col1, col2 = st.columns([3, 1])
with col1:
    st.title("📈 S&P 500 Live Tracker")
with col2:
    st.caption(f"Laatste update: {datetime.now().strftime('%H:%M:%S')}")
    if st.button("🔄 Ververs", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

cfg = load_config()

# ─── S&P 500 Top ──────────────────────────────────────────────────────────────
st.subheader(f"🏆 S&P 500 Top {cfg['top_n']} — Market Cap")

with st.spinner("Live data ophalen..."):
    top3 = get_sp500_top(cfg["top_n"])

if not top3.empty:
    # Format market cap voor display
    display = top3.copy()
    display["Mkt Cap"] = display["Mkt Cap"].apply(format_market_cap)
    display["Volume"] = display["Volume"].apply(lambda x: f"{x:,}")
    display["Gem. Volume"] = display["Gem. Volume"].apply(lambda x: f"{x:,}")

    styled = display.style \
        .map(color_change, subset=["±%"]) \
        .map(color_volume, subset=["xGem"]) \
        .format({"Prijs": "${:.2f}"}, subset=["Prijs"])

    st.dataframe(styled, use_container_width=True, hide_index=True)
else:
    st.warning("⚠️ Kon geen data ophalen. Check je internetverbinding.")

# ─── Watchlist ────────────────────────────────────────────────────────────────
st.divider()
st.subheader("📋 Watchlist")

watchlist = cfg["watchlist"]

with st.spinner("Watchlist data ophalen..."):
    wl_data = get_watchlist_data(watchlist)

if not wl_data.empty:
    display_wl = wl_data.copy()
    display_wl["Volume"] = display_wl["Volume"].apply(lambda x: f"{x:,}")
    display_wl["Gem. Volume"] = display_wl["Gem. Volume"].apply(lambda x: f"{x:,}")

    styled_wl = display_wl.style \
        .map(color_change, subset=["±%"]) \
        .map(color_volume, subset=["xGem"]) \
        .format({"Prijs": "${:.2f}"}, subset=["Prijs"])

    st.dataframe(styled_wl, use_container_width=True, hide_index=True)

    # Volume alerts + Telegram push
    threshold = cfg["volume_threshold"]
    alerts = wl_data[wl_data["xGem"] >= threshold]
    if not alerts.empty:
        st.error(f"🚨 **Volume Alert!** {len(alerts)} ticker(s) boven {threshold}x gemiddeld volume:")
        for _, row in alerts.iterrows():
            st.warning(f"**{row['Ticker']}** — Volume: x{row['xGem']:.1f} gemiddelde (${row['Prijs']:.2f})")
        # Stuur Telegram alerts
        check_and_alert_volume(wl_data)
else:
    st.info("ℹ️ Watchlist is leeg. Voeg tickers toe via de sidebar.")

# ─── Watchlist beheer ─────────────────────────────────────────────────────────
st.divider()
st.subheader("⚙️ Watchlist Beheer")

col1, col2, col3, col4 = st.columns([2, 2, 2, 3])

with col1:
    new_ticker = st.text_input("Ticker toevoegen", placeholder="TSLA", max_chars=10).upper()
    if st.button("➕ Toevoegen", use_container_width=True) and new_ticker:
        if new_ticker not in cfg["watchlist"]:
            cfg["watchlist"].append(new_ticker)
            save_config(cfg)
            st.cache_data.clear()
            st.success(f"✅ {new_ticker} toegevoegd!")
            st.rerun()
        else:
            st.warning(f"⚠️ {new_ticker} staat al in watchlist.")

with col2:
    remove_ticker = st.selectbox("Ticker verwijderen", [""] + cfg["watchlist"])
    if st.button("❌ Verwijderen", use_container_width=True) and remove_ticker:
        if remove_ticker in cfg["watchlist"]:
            cfg["watchlist"].remove(remove_ticker)
            save_config(cfg)
            st.cache_data.clear()
            st.success(f"✅ {remove_ticker} verwijderd!")
            st.rerun()

with col3:
    st.markdown("**Huidige watchlist**")
    for t in cfg["watchlist"]:
        st.markdown(f"- {t}")

with col4:
    threshold_val = st.number_input(
        "Volume threshold (x gem.)",
        min_value=1.0,
        max_value=10.0,
        value=cfg["volume_threshold"],
        step=0.5,
    )
    if threshold_val != cfg["volume_threshold"]:
        cfg["volume_threshold"] = threshold_val
        save_config(cfg)
        st.success(f"✅ Threshold gewijzigd naar {threshold_val}x")

# ─── Telegram Config ──────────────────────────────────────────────────────────
st.divider()
st.subheader("📱 Telegram Notificaties")

with st.expander("Telegram instellen", expanded=not cfg.get("telegram_token")):
    token = st.text_input("Bot Token", value=cfg.get("telegram_token", ""), type="password")
    chat_id = st.text_input("Chat ID", value=cfg.get("telegram_chat_id", ""))

    if st.button("💾 Opslaan", use_container_width=True):
        cfg["telegram_token"] = token
        cfg["telegram_chat_id"] = chat_id
        save_config(cfg)
        st.success("✅ Telegram configuratie opgeslagen!")

    if token and chat_id:
        if st.button("📨 Test notificatie sturen", use_container_width=True):
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                resp = requests.post(url, json={
                    "chat_id": chat_id,
                    "text": "✅ *S&P 500 Tracker* — Test notificatie werkt!",
                    "parse_mode": "Markdown",
                }, timeout=10)
                if resp.status_code == 200:
                    st.success("✅ Test notificatie verstuurd!")
                else:
                    st.error(f"❌ Fout: {resp.text}")
            except Exception as e:
                st.error(f"❌ Fout: {e}")

# ─── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"S&P 500 Live Tracker • Data: Yahoo Finance • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
