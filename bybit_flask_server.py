from flask import Flask, request
from pybit.unified_trading import HTTP
import json

app = Flask(__name__)

# Завантаження API ключів з config.json
with open("config.json") as f:
    config = json.load(f)

api_key = config["bybit_api_key"]
api_secret = config["bybit_api_secret"]

session = HTTP(
    testnet=True,
    api_key=api_key,
    api_secret=api_secret
)

@app.route("/", methods=["GET"])
def home():
    return "Bybit bot is running."

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("📥 Отриманий webhook:", data)

    if not data or "symbol" not in data or "side" not in data:
        return {"error": "Некоректний запит"}, 400

    try:
        balance_data = session.get_wallet_balance(accountType="UNIFIED")
        balance = float(balance_data["result"]["list"][0]["totalEquity"])
        print(f"💰 Баланс: {balance}")

        if balance < 10:
            return {"error": "Недостатньо коштів"}, 400

        response = session.place_order(
            category="linear",
            symbol=data["symbol"],
            side=data["side"],
            order_type="Market",
            qty="0.01",
            time_in_force="GoodTillCancel"
        )
        print("📦 Ордер:", response)
        return {"success": True, "order": response}

    except Exception as e:
        print("❌ Помилка:", str(e))
        return {"error": str(e)}, 500

if __name__ == "__main__":
    app.run(debug=True, port=5002)
