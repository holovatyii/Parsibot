import os
import time
import hmac
import json
import hashlib
import requests
from flask import Flask, request

# === Змінні з оточення ===
api_key = os.environ["api_key"]
api_secret = os.environ["api_secret"]
default_symbol = os.environ.get("symbol", "BTCUSDT")
default_base_qty = float(os.environ.get("base_qty", 0.01))
webhook_password = os.environ["webhook_password"]
telegram_token = os.environ["telegram_token"]
telegram_chat_id = os.environ["telegram_chat_id"]

app = Flask(__name__)

# === Telegram логування ===
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    try:
        requests.post(url, json=data)
    except Exception as e:
        print(f"Telegram Error: {e}")

# === Підпис запиту ===
def sign_request(api_key, api_secret, body, timestamp):
    param_str = f"{timestamp}{api_key}5000{body}"
    return hmac.new(
        bytes(api_secret, "utf-8"),
        msg=bytes(param_str, "utf-8"),
        digestmod=hashlib.sha256
    ).hexdigest()

# === Отримати ринкову ціну
def get_price(symbol):
    try:
        url = f"https://api-testnet.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
        response = requests.get(url)
        data = response.json()
        print("📊 API response:", data)
        if "result" in data and "list" in data["result"]:
            last_price = data["result"]["list"][0].get("lastPrice")
            return float(last_price) if last_price else None
        return None
    except Exception as e:
        print(f"❌ get_price() error: {e}")
        return None

# === Створити окремий TP-ордер
def create_take_profit_order(symbol, side, qty, tp):
    try:
        tp_side = "Sell" if side == "Buy" else "Buy"
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"

        order_data = {
            "category": "linear",
            "symbol": symbol,
            "side": tp_side,
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(tp),
            "timeInForce": "GoodTillCancel",
            "reduceOnly": True
        }

        body = json.dumps(order_data)
        sign = sign_request(api_key, api_secret, body, timestamp)

        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-SIGN": sign,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }

        url = "https://api-testnet.bybit.com/v5/order/create"
        response = requests.post(url, data=body, headers=headers)
        print("📤 Окремий TP-ордер:", response.text)
        return response.json()
    except Exception as e:
        print(f"❌ Помилка при створенні TP ордера: {e}")
        return None

# === Відправити основний ордер
def place_order(symbol, side, qty, tp=None, sl=None):
    try:
        price = get_price(symbol)
        print("📈 Поточна ціна:", price)

        url = "https://api-testnet.bybit.com/v5/order/create"
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"

        order_data = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "GoodTillCancel"
        }

        if price:
            if side == "Buy":
                if tp and float(tp) > price:
                    order_data["takeProfit"] = str(tp)
                if sl and float(sl) < price:
                    order_data["stopLoss"] = str(sl)
            elif side == "Sell":
                if tp and float(tp) < price:
                    order_data["takeProfit"] = str(tp)
                if sl and float(sl) > price:
                    order_data["stopLoss"] = str(sl)

        body = json.dumps(order_data)
        sign = sign_request(api_key, api_secret, body, timestamp)

        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-SIGN": sign,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }

        response = requests.post(url, data=body, headers=headers)
        print("📤 Відповідь Bybit:", response.text)
        return response.json()

    except Exception as e:
        print(f"❌ place_order error: {e}")
        return {"retCode": -1, "retMsg": str(e)}

# === Webhook ===
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        print("📩 Webhook отримано:", data)

        if not data or data.get("password") != webhook_password:
            return {"error": "Unauthorized"}, 401

        side = data.get("side")
        symbol = data.get("symbol", default_symbol)
        qty = data.get("qty", default_base_qty)
        tp = data.get("tp")
        sl = data.get("sl")

        if not side or not symbol or not qty:
            raise ValueError("❌ Відсутні ключові параметри (side, symbol або qty)")

        try:
            qty = float(qty)
        except Exception:
            raise ValueError(f"❌ Неможливо перетворити qty: {qty}")

        order = place_order(symbol, side, qty, tp, sl)

        # Якщо TP не був прийнятий — створити окремий TP-ордер
        if tp and ("takeProfit" not in json.dumps(order)):
            send_telegram_message(f"⚠️ TP не встановлено, створюємо окремий TP-ордер @ {tp}")
            create_take_profit_order(symbol, side, qty, tp)

        msg = (
            f"✅ Ордер відправлено!\n"
            f"Пара: {symbol}\n"
            f"Сторона: {side}\n"
            f"Кількість: {qty}\n"
            f"TP: {tp or 'немає'} | SL: {sl or 'немає'}\n"
            f"\nВідповідь: {json.dumps(order, indent=2)}"
        )
        send_telegram_message(msg)
        return {"success": True, "order": order}

    except Exception as e:
        error_msg = f"🔥 Error in webhook(): {e}"
        print(error_msg)
        send_telegram_message(error_msg)
        return {"error": str(e)}, 500

# === Запуск
if __name__ == '__main__':
    print("🚀 Flask-сервер запущено на 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)


