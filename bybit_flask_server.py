from flask import Flask, request
from pybit.unified_trading import HTTP
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# Завантаження ключів з .env
api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")

# ініціалізація сесії
session = HTTP(
    testnet=True,
    api_key=api_key,
    api_secret=api_secret
)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("🔔 Сигнал отримано:", data)

    try:
        # Отримання балансу
        balance = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        usdt_balance = float(balance["result"]["list"][0]["coin"][0]["walletBalance"])
        print(f"💰 Баланс: {usdt_balance}")

        if usdt_balance < 10:
            return "❌ Недостатньо балансу", 400

        # Надсилання ордеру
        order = session.place_order(
            category="linear",
            symbol="BTCUSDT",
            side="Buy",
            order_type="Market",
            qty="0.01",
            time_in_force="GoodTillCancel"
        )
        print("📦 Ордер:", order)
        return "✅ Ордер відправлено"

    except Exception as e:
        print("❗ Помилка:", str(e))
        return f"❗ Сталася помилка: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)
