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

# Надсилання повідомлення в Telegram (з підтримкою UTF-8)
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    headers = {"Content-Type": "application/json; charset=utf-8"}
    try:
        requests.post(url, data=json.dumps(data), headers=headers)
    except Exception as e:
        print(f"Telegram Error: {e}")

# Обробка webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json

        if not data or data.get("password") != webhook_password:
            return {"error": "Unauthorized"}, 401

        side = data.get("side", "Buy")
        symbol = data.get("symbol", default_symbol)
        qty = data.get("qty", default_base_qty)
        tp = data.get("tp")
        sl = data.get("sl")

        try:
            qty = float(qty)
        except (ValueError, TypeError):
            return {"error": "Invalid quantity"}, 400

        order_params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "order_type": "Market",
            "qty": str(qty),
            "time_in_force": "GoodTillCancel"
        }

        if tp:
            order_params["take_profit"] = str(tp)
        if sl:
            order_params["stop_loss"] = str(sl)

        order = session.place_order(**order_params)

        # Консоль без емодзі
        print(f"Order placed: {side} {symbol} qty={qty} TP={tp} SL={sl}")

        # Повне повідомлення в Telegram
        msg = (
            f"✅ Ордер відправлено!\n"
            f"Пара: {symbol}\n"
            f"Сторона: {side}\n"
            f"Кількість: {qty}\n"
            f"TP: {tp or 'немає'} | SL: {sl or 'немає'}\n"
            f"\nВідповідь: {order}"
        )
        send_telegram_message(msg)

        return {"success": True, "order": order}

    except Exception as e:
        error_msg = f"Error inside webhook: {str(e)}"
        print(error_msg)
        send_telegram_message(error_msg)
        return {"error": str(e)}, 500

# Запуск Flask
if __name__ == '__main__':
    print("Flask server running on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)




