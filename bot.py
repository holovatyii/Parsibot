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
        symbol = data.get("symbol", "BTCUSDT")
        entry_price = float(data.get("entry"))
        action = data.get("action", "LONG")
        timeframe = data.get("timeframe", "")
        
        # Баланс
        usdt_balance = float(client.futures_account_balance()[1]['balance'])  # USDT
        risk_percent = 1  # 1% від балансу
        usd_amount = usdt_balance * (risk_percent / 100)
        quantity = round(usd_amount / entry_price, 3)

        send_telegram(f"📈 {action} | {symbol} | TF: {timeframe}\n💰 Entry: {entry_price}\n📊 Обсяг: {quantity} ({risk_percent}% від балансу)")

        # Відкриття угоди
        if action == "LONG":
            client.futures_create_order(symbol=symbol, side="BUY", type="MARKET", quantity=quantity)
            stop_price = round(entry_price * 0.92, 2)  # -8% страховий SL
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
            stop_price = round(entry_price * 1.08, 2)  # +8% страховий SL
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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

