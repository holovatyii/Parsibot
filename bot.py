import os
import json
import requests
from flask import Flask, request
from binance.client import Client

app = Flask(__name__)

# Змінні середовища
TOKEN = os.getenv("BOT_TOKEN")                     # Токен Telegram бота
CHAT_ID = os.getenv("CHAT_ID")                     # ID чату
BINANCE_KEY = os.getenv("BINANCE_KEY")             # Binance API Key (Testnet)
BINANCE_SECRET = os.getenv("BINANCE_SECRET")       # Binance Secret (Testnet)

# Binance клієнт (TESTNET)
client = Client(BINANCE_KEY, BINANCE_SECRET, testnet=True)
client.API_URL = 'https://testnet.binancefuture.com'

# Надсилання повідомлення в Telegram
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, json=payload)

# Webhook для TradingView
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

        # Отримання балансу
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
    return "ok"

# Для перевірки IP сервера
@app.route("/ip")
def show_ip():
    ip = requests.get("https://api.ipify.org").text
    return f"Render IP: {ip}"

# Запуск сервера Flask
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
