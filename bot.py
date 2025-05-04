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

# === Raw POST до Bybit з підписом у заголовках ===
def place_order_raw(symbol, side, qty, tp=None, sl=None):
    url = "https://api-testnet.bybit.com/v5/order/create"
    timestamp = str(int(time.time() * 1000))

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

    body_str = json.dumps(body, separators=(',', ':'), ensure_ascii=False)

    recv_window = "5000"
    to_sign = f"api_key={api_key}&recv_window={recv_window}&timestamp={timestamp}&{body_str}"
    sign = hmac.new(bytes(api_secret, "utf-8"), to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {
        "X-BYBIT-API-KEY": api_key,
        "X-BYBIT-SIGN": sign,
        "X-BYBIT-TIMESTAMP": timestamp,
        "X-BYBIT-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, data=body_str)
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


