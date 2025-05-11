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
    url = "https://api.telegram.org/bot" + telegram_token + "/sendMessage"
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
        url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
        response = requests.get(url)
        data = response.json()
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
        url = "https://api.bybit.com/v5/order/create"
        response = requests.post(url, data=body, headers=headers)
        return response.json()
    except Exception as e:
        print(f"❌ TP fallback error: {e}")
        return None

# === Створити окремий SL-ордер
def create_stop_loss_order(symbol, side, qty, sl):
    try:
        sl_side = "Sell" if side == "Buy" else "Buy"
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        order_data = {
            "category": "linear",
            "symbol": symbol,
            "side": sl_side,
            "orderType": "Market",
            "qty": str(qty),
            "stopLoss": str(sl),
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
        url = "https://api.bybit.com/v5/order/create"
        response = requests.post(url, data=body, headers=headers)
        return response.json()
    except Exception as e:
        print(f"❌ SL fallback error: {e}")
        return None

# === Перевірити TP/SL
def check_position_tp_sl(symbol):
    try:
        url = "https://api.bybit.com/v5/position/list"
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        query = {"category": "linear", "symbol": symbol}
        query_str = json.dumps(query, separators=(",", ":"))
        sign = sign_request(api_key, api_secret, query_str, timestamp)
        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-SIGN": sign,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }
        response = requests.get(url, params=query, headers=headers)

        if response.status_code != 200:
            send_telegram_message(f"❌ Bybit API error {response.status_code}: {response.text}")
            return False

        try:
            data = response.json()
        except Exception as e:
            send_telegram_message(f"❌ JSON decode error in check_position_tp_sl(): {e}")
            return False

        if "result" in data and "list" in data["result"]:
            position = data["result"]["list"][0]
            take_profit = position.get("takeProfit")
            stop_loss = position.get("stopLoss")
            if not take_profit or not stop_loss:
                send_telegram_message("🚨 TP/SL не встановлено. Пробую fallback...")
                return False
            return True
        return False
    except Exception as e:
        send_telegram_message(f"❌ TP/SL check error: {e}")
        return False

# === Відправити ордер
def place_order(symbol, side, qty, tp=None, sl=None):
    try:
        price = get_price(symbol)
        url = "https://api.bybit.com/v5/order/create"
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
        return response.json()
    except Exception as e:
        print(f"❌ place_order error: {e}")
        return {"retCode": -1, "retMsg": str(e)}

# === Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        if not data or data.get("password") != webhook_password:
            return {"error": "Unauthorized"}, 401
        side = data.get("side")
        symbol = data.get("symbol", default_symbol)
        qty = float(data.get("qty", default_base_qty))
        tp = data.get("tp")
        sl = data.get("sl")
        order = place_order(symbol, side, qty, tp, sl)
        time.sleep(8)
        if not check_position_tp_sl(symbol):
            create_take_profit_order(symbol, side, qty, tp)
            create_stop_loss_order(symbol, side, qty, sl)
        send_telegram_message(f"✅ Ордер виконано. Пара: {symbol}, Сторона: {side}, TP: {tp}, SL: {sl}")
        return {"success": True, "order": order}
    except Exception as e:
        error_msg = f"🔥 Webhook error: {e}"
        send_telegram_message(error_msg)
        return {"error": str(e)}, 500

# === Запуск Flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
