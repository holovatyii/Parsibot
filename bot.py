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

# Binance клієнт
client = Client(BINANCE_KEY, BINANCE_SECRET)
client.API_URL = 'https://fapi.binance.com'

# Telegram
def send_telegram(text):
    print("📤 Надсилаємо в Telegram:", text)
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, json=payload)

# Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    print("✅ Запит прийшов!")
    print(request.headers)
    print(request.data)

    try:
        data = request.get_json(force=True)
        print("📦 JSON:", data)

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

        send_telegram(f"📈 {action} | {symbol} | TF: {timeframe}\n💰 Entry: {entry_price}\n📊 Обсяг: {quantity} ({risk_percent}% від балансу)")

        if quantity <= 0:
            raise Exception("Обсяг <= 0, перевір баланс")

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
            send_telegram(f"🚀 LONG placed | SL set at {stop_price}")

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
            send_telegram(f"🔻 SHORT placed | SL set at {stop_price}")

    except Exception as e:
        send_telegram(f"⚠ Error: {e}")
        print("❌ Виникла помилка:", e)

    return "ok"

# Для перевірки IP
@app.route("/ip")
def show_ip():
    ip = requests.get("https://api.ipify.org").text
    return f"Render IP: {ip}"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

