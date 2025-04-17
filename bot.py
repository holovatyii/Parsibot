import os
import json
import requests
from flask import Flask, request
from binance.client import Client

app = Flask(__name__)

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_KEY = os.getenv("BINANCE_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")
client = Client(BINANCE_KEY, BINANCE_SECRET, testnet=True)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    message = f"📈 {data.get('action', 'SIGNAL')} | {data.get('symbol', '')} | TF: {data.get('timeframe', '')}\n💰 Entry: {data.get('entry', '')}"

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, json=payload)

    try:
        if data.get("action") == "LONG":
            client.futures_create_order(symbol=data.get("symbol", "BTCUSDT"), side="BUY", type="MARKET", quantity=0.01)
        elif data.get("action") == "SHORT":
            client.futures_create_order(symbol=data.get("symbol", "BTCUSDT"), side="SELL", type="MARKET", quantity=0.01)
    except Exception as e:
        error_message = f"⚠ Binance API error: {e}"
        requests.post(url, json={"chat_id": CHAT_ID, "text": error_message})

    return "ok"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
