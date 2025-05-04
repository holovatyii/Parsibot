import os
import json
import time
import requests
from flask import Flask, request
from pybit.unified_trading import HTTP

# === Config from environment ===
api_key = os.environ["api_key"]
api_secret = os.environ["api_secret"]
default_symbol = os.environ.get("symbol", "SOLUSDT")
default_base_qty = float(os.environ.get("base_qty", 1))
webhook_password = os.environ["webhook_password"]
telegram_token = os.environ["telegram_token"]
telegram_chat_id = os.environ["telegram_chat_id"]

# === Flask app ===
app = Flask(__name__)

# === Bybit session ===
client = HTTP(api_key=api_key, api_secret=api_secret, testnet=True)

# === Telegram sender ===
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": telegram_chat_id, "text": msg})
    except Exception as e:
        print(f"Telegram error: {e}")

# === Place order ===
def place_order(symbol, side, qty, tp=None, sl=None):
    order = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "order_type": "Market",
        "qty": str(qty),
        "time_in_force": "GoodTillCancel"
    }
    if tp: order["take_profit"] = str(tp)
    if sl: order["stop_loss"] = str(sl)

    return client.place_order(**order)

# === Webhook ===
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print(">> Incoming data:", data)

    if not data or data.get("password") != webhook_password:
        return {"error": "unauthorized"}, 401

    side = data.get("side", "Buy")
    symbol = data.get("symbol", default_symbol)  # 🔥 Тепер читає symbol із запиту
    qty = data.get("qty", default_base_qty)
    tp = data.get("tp")
    sl = data.get("sl")

    try:
        qty = float(qty)
        result = place_order(symbol, side, qty, tp, sl)
        msg = (
            f"✅ Ордер відправлено!\n"
            f"Пара: {symbol}\nСторона: {side}\nКількість: {qty}\n"
            f"TP: {tp or 'немає'} | SL: {sl or 'немає'}\n\n"
            f"Відповідь: {result}"
        )
        send_telegram(msg)
        return {"success": True, "order": result}
    except Exception as e:
        err = f"🔥 Error: {str(e)}"
        print(err)
        send_telegram(err)
        return {"error": str(e)}, 500

if __name__ == "__main__":
    print("🚀 Flask server running on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)

