# S&P 500 Live Tracker

Real-time S&P 500 top 3 + watchlist monitor met volume-detectie en Telegram notificaties.

## Installatie

```bash
pip install yfinance pandas requests
```

## Snel starten

```bash
# Eerste keer — setup wizard (Telegram configuratie)
python sp500_tracker.py --setup

# Check top 3 + watchlist
python sp500_tracker.py --check

# Watchlist beheren
python sp500_tracker.py --add TSLA
python sp500_tracker.py --remove AAPL
python sp500_tracker.py --list

# Continuous monitoring (daemon)
python sp500_tracker.py --daemon
```

## Configuratie

`config.json` wordt automatisch aangemaakt:

| Veld | Standaard | Beschrijving |
|------|-----------|-------------|
| `watchlist` | AAPL, MSFT, NVDA, GOOGL, AMZN | Te monitoren tickers |
| `volume_threshold` | 2.0 | x keer gemiddeld volume = alert |
| `check_interval_minutes` | 15 | Hoe vaak checken in daemon modus |
| `top_n` | 3 | Hoeveel S&P 500 top tonen |
| `telegram_token` | "" | Bot token van @BotFather |
| `telegram_chat_id` | "" | Chat ID voor notificaties |

## Telegram setup

1. Open Telegram en zoek **@BotFather**
2. Stuur `/newbot` en volg de stappen
3. Kopieer de token en gebruik `--setup`
4. Stuur een bericht naar je nieuwe bot
5. Bezoek `https://api.telegram.org/bot<TOKEN>/getUpdates`
6. Kopieer het `chat.id` nummer

## Volume alerts

Een alert wordt gestuurd wanneer:
- Het volume > `volume_threshold` x het gemiddelde volume is
- Maximaal 1x per uur per ticker (anti-spam)

## Automatiseren (cron)

```bash
# Check elk uur
crontab -e
0 * * * * cd /pad/naar/script && python sp500_tracker.py --check
```
