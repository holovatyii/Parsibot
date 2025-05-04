import time
import hmac
import hashlib
import requests
import json
import os
from flask import Flask, request

# === Завантаження з Environment ===
api_key = os.environ["api_key"]
api_secret = os.environ["api_secret"]
default_symbol = os.environ.get("symbol", "SOLUSDT")
default_base_qty = float(os.environ.get("base_qty", 1))
webhook_password = os.environ["webhook_password"]
telegram_token = os.environ["telegram_token"]
telegram_chat_id = os.environ["telegram_chat_id"]

app = Flask(__name__)

# === Надсилання повідомлення в Telegram ===
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    headers = {"Content-Type": "application/json; charset=utf-8"}
    try:
        requests.post(url, data=json.dumps(data), headers=headers)
    except Exception as e:
        print(f"Telegram Error: {e}")

# === Raw POST до Bybit з підписом у query string (без body) ===
def place_order_raw(symbol, side, qty, tp=None, sl=None):
    base_url = "https://api-testnet.bybit.com"
    endpoint = "/v5/order/create"
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    # Підписуємо лише ключові параметри
    to_sign = f"api_key={api_key}&recv_window={recv_window}&timestamp={timestamp}"
    sign = hmac.new(bytes(api_secret, "utf-8"), to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    query_string = f"?api_key={api_key}&timestamp={timestamp}&sign={sign}&recv_window={recv_window}"
    final_url = base_url + endpoint + query_string

    body = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "order_type": "Market",
        "qty": str(qty),
        "time_in_force": "GoodTillCancel"
    }
    if tp:
        body["take_profit"] = str(tp)
    if sl:
        body["stop_loss"] = str(sl)

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(final_url, headers=headers, data=json.dumps(body))
    print(f">> RAW POST: {response.status_code} | {response.text}")
    return response.json()

# === Webhook ===
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        print(f">> Debug: Received data: {data}")

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

        order = place_order_raw(symbol, side, qty, tp, sl)

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
        error_msg = f"🔥 Error inside webhook: {str(e)}"
        print(error_msg)
        try:
            send_telegram_message(error_msg)
        except:
            print("❌ Telegram send failed")
        return {"error": str(e)}, 500

if __name__ == '__main__':
    print("Flask server running on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)

