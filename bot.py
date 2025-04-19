import os
import json
import requests
from flask import Flask, request
from binance.client import Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ENV
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_KEY = os.getenv("BINANCE_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")

# Binance
client = Client(BINANCE_KEY, BINANCE_SECRET)
client.API_URL = 'https://testnet.binancefuture.com'

# Telegram
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text})

# Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("Content-Type") != "application/json":
        return "Unsupported Media Type", 415

    try:
        data = request.get_json(force=True)
        symbol = data.get("symbol", "BTCUSDT")
        entry_price = float(data.get("entry"))
        action = data.get("action", "LONG")
        timeframe = data.get("timeframe", "")

        balances = client.futures_account_balance()
        usdt_balance = next(item for item in balances if item['asset'] == 'USDT')
        usdt = float(usdt_balance['balance'])

        risk_percent = 1
        usd_amount = usdt * (risk_percent / 100)
        quantity = round(usd_amount / entry_price, 3)

        if quantity <= 0:
            raise Exception("Обсяг менший або рівний 0")

        send_telegram(f"📈 {action} | {symbol} | TF: {timeframe}\n💰 Entry: {entry_price}\n📊 Qty: {quantity}")

        if action == "LONG":
            client.futures_create_order(symbol=symbol, side="BUY", type="MARKET", quantity=quantity)
            stop = round(entry_price * 0.92, 2)
            client.futures_create_order(symbol=symbol, side="SELL", type="STOP_MARKET", stopPrice=str(stop), closePosition=True)
            send_telegram(f"🚀 LONG order | SL at {stop}")

        elif action == "SHORT":
            client.futures_create_order(symbol=symbol, side="SELL", type="MARKET", quantity=quantity)
            stop = round(entry_price * 1.08, 2)
            client.futures_create_order(symbol=symbol, side="BUY", type="STOP_MARKET", stopPrice=str(stop), closePosition=True)
            send_telegram(f"🔻 SHORT order | SL at {stop}")

    except Exception as e:
        send_telegram(f"⚠ Error: {e}")
    return "ok"

# Перевірка IP
@app.route("/ip")
def ip():
    return requests.get("https://api.ipify.org").text

# Запуск
if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
