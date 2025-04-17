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

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, json=payload)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        send_telegram(f"✅ Webhook received:\n{json.dumps(data, indent=2)}")

        action = data.get("action")
        symbol = data.get("symbol", "BTCUSDT")
        timeframe = data.get("timeframe", "")
        entry = data.get("entry", "")

        msg = f"📈 {action} | {symbol} | TF: {timeframe}\n💰 Entry: {entry}"
        send_telegram(msg)

        if action == "LONG":
            client.futures_create_order(symbol=symbol, side="BUY", type="MARKET", quantity=0.01)
            send_telegram("🚀 LONG order placed.")
        elif action == "SHORT":
            client.futures_create_order(symbol=symbol, side="SELL", type="MARKET", quantity=0.01)
            send_telegram("🔻 SHORT order placed.")
    except Exception as e:
        send_telegram(f"⚠ Error: {e}")
    return "ok"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)


    return "ok"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
