import os
import json
import requests
from flask import Flask, request
from pybit.unified_trading import HTTP

# === Змінні з оточення ===
api_key = os.environ["api_key"]
api_secret = os.environ["api_secret"]
default_symbol = os.environ.get("symbol", "BTCUSDT")
default_base_qty = float(os.environ.get("base_qty", 0.01))
webhook_password = os.environ["webhook_password"]
telegram_token = os.environ["telegram_token"]
telegram_chat_id = os.environ["telegram_chat_id"]

# === Ініціалізація Flask та Bybit session ===
app = Flask(__name__)
client = HTTP(api_key=api_key, api_secret=api_secret, testnet=True)

# === Отримати ринкову ціну ===
# === Отримати ринкову ціну з Bybit ===
def get_price(symbol):
    try:
        print(f"🔵 Викликаємо get_price() для: {symbol}")
        price_data = client.market.get_ticker(category="linear", symbol=symbol)
        print("📦 Відповідь від Bybit (type):", type(price_data))
        print("📦 Відповідь від Bybit (raw):", price_data)

        # Надсилаємо в Telegram для дистанційного моніторингу
        send_telegram_message(f"📊 get_price() -> symbol: {symbol}\n📦 price_data: {price_data}")

        if "result" in price_data and "list" in price_data["result"]:
            last_price = price_data["result"]["list"][0].get("lastPrice")
            return float(last_price) if last_price else None

        return None
    except Exception as e:
        print(f"❌ Помилка отримання ціни: {e}")
        send_telegram_message(f"❌ Помилка get_price(): {e}")
        return None

# === Telegram логування ===
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    headers = {"Content-Type": "application/json"}
    try:
        requests.post(url, data=json.dumps(data), headers=headers)
    except Exception as e:
        print(f"Telegram Error: {e}")

# === Відправка ордера ===
def place_order(symbol, side, qty, tp=None, sl=None):
    try:
        current_price = get_price(symbol)
        if current_price is None:
            return {"retCode": -1, "retMsg": "Failed to fetch current price"}

        order_data = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "GoodTillCancel"
        }

        if side == "Buy":
            if tp and float(tp) > current_price:
                order_data["takeProfit"] = str(tp)
            if sl and float(sl) < current_price:
                order_data["stopLoss"] = str(sl)
        elif side == "Sell":
            if tp and float(tp) < current_price:
                order_data["takeProfit"] = str(tp)
            if sl and float(sl) > current_price:
                order_data["stopLoss"] = str(sl)

        response = client.order.create(order_data)
        print(f">> SDK RESPONSE: {response}")
        return response
    except Exception as e:
        print(f">> SDK ERROR: {e}")
        return {"retCode": -1, "retMsg": str(e)}

# === Webhook ===
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        print(f">> Received webhook: {data}")

        if not data or data.get("password") != webhook_password:
            return {"error": "Unauthorized"}, 401

        side = data.get("side", "Buy")
        symbol = data.get("symbol", default_symbol)
        qty = float(data.get("qty", default_base_qty))
        tp = data.get("tp")
        sl = data.get("sl")

        order = place_order(symbol, side, qty, tp, sl)

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
        error_msg = f"🔥 Error: {str(e)}"
        print(error_msg)
        send_telegram_message(error_msg)
        return {"error": str(e)}, 500

# === Запуск ===
if __name__ == '__main__':
    print("🚀 Flask-сервер запущено на 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)





