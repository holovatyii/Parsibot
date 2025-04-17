# bot.py
import json
import requests
from flask import Flask, request
from binance.client import Client

app = Flask(__name__)

with open("config.json") as f:
    config = json.load(f)

TOKEN = config["bot_token"]
CHAT_ID = config["chat_id"]
client = Client(config["binance_api_key"], config["binance_api_secret"], testnet=True)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    message = f"\u2705 {data.get('action', 'SIGNAL')} | {data.get('symbol', '')} | TF: {data.get('timeframe', '')}\n\ud83d\udcb0 Вхід: {data.get('entry', '')}"

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, json=payload)

    try:
        if data.get("action") == "LONG":
            client.futures_create_order(symbol=data.get("symbol", "BTCUSDT"), side="BUY", type="MARKET", quantity=0.01)
        elif data.get("action") == "SHORT":
            client.futures_create_order(symbol=data.get("symbol", "BTCUSDT"), side="SELL", type="MARKET", quantity=0.01)
    except Exception as e:
        error_message = f"\u26a0 Binance API error: {e}"
        requests.post(url, json={"chat_id": CHAT_ID, "text": error_message})

    return "ok"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
