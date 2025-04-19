import os
import time
import hmac
import hashlib
import requests
import urllib.parse
from flask import Flask, request

app = Flask(__name__)

# Змінні середовища
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_KEY = os.getenv("BINANCE_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")

BINANCE_ENDPOINT = "https://testnet.binancefuture.com"

# Функція для надсилання повідомлення в Telegram
def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, json=payload)

# Отримати баланс USDT з Binance
def get_usdt_balance():
    timestamp = round(time.time() * 1000)
    params = {"timestamp": timestamp}
    query = urllib.parse.urlencode(params)
    signature = hmac.new(BINANCE_SECRET.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
    url = f"{BINANCE_ENDPOINT}/fapi/v2/balance?{query}&signature={signature}"
    headers = {
        'X-MBX-APIKEY': BINANCE_KEY
    }
    response = requests.get(url, headers=headers).json()
    for asset in response:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0

# Створити ордер на LONG або SHORT
def place_order(symbol, side, quantity, stop_price):
    timestamp = round(time.time() * 1000)
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": quantity,
        "timestamp": timestamp
    }
    query = urllib.parse.urlencode(params)
    signature = hmac.new(BINANCE_SECRET.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
    url = f"{BINANCE_ENDPOINT}/fapi/v1/order?{query}&signature={signature}"
    headers = {'X-MBX-APIKEY': BINANCE_KEY}
    requests.post(url, headers=headers)

    # Stop Loss
    sl_params = {
        "symbol": symbol,
        "side": "SELL" if side == "BUY" else "BUY",
        "type": "STOP_MARKET",
        "stopPrice": stop_price,
        "closePosition": True,
        "timestamp": round(time.time() * 1000)
    }
    sl_query = urllib.parse.urlencode(sl_params)
    sl_signature = hmac.new(BINANCE_SECRET.encode('utf-8'), sl_query.encode('utf-8'), hashlib.sha256).hexdigest()
    sl_url = f"{BINANCE_ENDPOINT}/fapi/v1/order?{sl_query}&signature={sl_signature}"
    requests.post(sl_url, headers=headers)

# Webhook endpoint
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        symbol = data.get("symbol", "BTCUSDT")
        entry = float(data.get("entry"))
        action = data.get("action", "LONG")
        tf = data.get("timeframe", "")

        usdt = get_usdt_balance()
        usd_amount = usdt * 0.01
        quantity = round(usd_amount / entry, 3)

        send_telegram(f"\u2b06 {action} | {symbol} | TF: {tf}\n\ud83d\udcb0 Entry: {entry}\n\ud83d\udcca Qty: {quantity}")

        if quantity <= 0:
            raise Exception("Недостатній обсяг")

        if action == "LONG":
            place_order(symbol, "BUY", quantity, round(entry * 0.92, 2))
        elif action == "SHORT":
            place_order(symbol, "SELL", quantity, round(entry * 1.08, 2))

        send_telegram("\u2705 Ордер створено")

    except Exception as e:
        send_telegram(f"\u26a0 Error: {e}")
    return "ok"

# Для перевірки
@app.route("/")
def home():
    return "Bot is working."

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)





