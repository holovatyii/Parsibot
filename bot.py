from flask import Flask, request
from pybit.unified_trading import HTTP
import json
import requests

# Завантаження конфігурації
with open("config.json") as f:
    config = json.load(f)

api_key = config["api_key"]
api_secret = config["api_secret"]
default_symbol = config["symbol"]
default_base_qty = config["base_qty"]
webhook_password = config["webhook_password"]
telegram_token = config["telegram_token"]
telegram_chat_id = config["telegram_chat_id"]

# Ініціалізація Flask
app = Flask(__name__)

# Ініціалізація сесії Bybit
session = HTTP(
    api_key=api_key,
    api_secret=api_secret,
    testnet=True
)

# Функція для відправки повідомлення в Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram Error: {e}")

# Вебхук маршрут
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json

        if not data or data.get("password") != webhook_password:
            return {"error": "Unauthorized"}, 401

        side = data.get("side", "Buy")
        symbol = data.get("symbol", default_symbol)
        qty = data.get("qty", default_base_qty)

        try:
            qty = float(qty)  # Перетворюємо qty на float
        except (ValueError, TypeError):
            return {"error": "Invalid quantity"}, 400

        order = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=str(qty),
            time_in_force="GoodTillCancel"
        )

        msg = f"✅ Ордер відправлено!\nПара: {symbol}\nСторона: {side}\nКількість: {qty}\n\nВідповідь: {order}"
        print(msg)
        send_telegram_message(msg)

        return {"success": True, "order": order}

    except Exception as e:
        error_msg = f"🔥 Помилка всередині webhook: {str(e)}"
        print(error_msg)
        send_telegram_message(error_msg)
        return {"error": str(e)}, 500

# Запуск Flask
if __name__ == '__main__':
    print("🚀 Flask-сервер запущено на порту 5000")
    app.run(host="0.0.0.0", port=5000)




