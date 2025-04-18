import os
import json
import requests
from flask import Flask, request
from binance.client import Client

app = Flask(__name__)

# Змінні середовища
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_KEY = os.getenv("BINANCE_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")

# Binance клієнт (testnet)
client = Client(BINANCE_KEY, BINANCE_SECRET)
client.API_URL = 'https://testnet.binancefuture.com/fapi'

# Функція надсилання в Telegram
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, json=payload)

# Webhook для сигналів TradingView
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        if request.headers.get('Content-Type') != 'application/json':
            return "Unsupported Media Type", 415

        data = request.json
        symbol = data.get("symbol", "BTCUSDT")
        entry_price = float(data.get("entry"))
        action = data.get("action", "LONG")
        timeframe = data.get("timeframe", "")

        usdt_balance = float(client.futures_account_balance()[1]['balance'])
        risk_percent = 1
        usd_amount = usdt_balance * (risk_percent / 100)
        quantity = round(usd_amount / entry_price, 3)

        if quantity <= 0:
            send_telegram("❌ Неможливо виконати угоду: обсяг = 0. Занадто малий баланс.")
            return "ok"

        send_telegram(f"\ud83d\udcc8 {action} | {symbol} | TF: {timeframe}\n\ud83d\udcb0 Entry: {entry_price}\n\ud83d\udcca \u041eбсяг: {quantity} ({risk_percent}% від балансу)")

        if action == "LONG":
            client.futures_create_order(symbol=symbol, side="BUY", type="MARKET", quantity=quantity)
            stop_price = round(entry_price * 0.92, 2)
            client.futures_create_order(
                symbol=symbol,
                side="SELL",
                type="STOP_MARKET",
                stopPrice=str(stop_price),
                closePosition=True
            )
            send_telegram(f"\ud83d\ude80 LONG placed | SL set at {stop_price}")

        elif action == "SHORT":
            client.futures_create_order(symbol=symbol, side="SELL", type="MARKET", quantity=quantity)
            stop_price = round(entry_price * 1.08, 2)
            client.futures_create_order(
                symbol=symbol,
                side="BUY",
                type="STOP_MARKET",
                stopPrice=str(stop_price),
                closePosition=True
            )
            send_telegram(f"\ud83d\udd3b SHORT placed | SL set at {stop_price}")

    except Exception as e:
        send_telegram(f"\u26a0 Error: {e}")
    return "ok"

# Перевірка IP
@app.route("/ip")
def show_ip():
    ip = requests.get("https://api.ipify.org").text
    return f"Render IP: {ip}"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)




