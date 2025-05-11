import os
import time
import hmac
import json
import hashlib
import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv("bot.env")

api_key = os.environ["api_key"]
api_secret = os.environ["api_secret"]
default_symbol = os.environ.get("symbol", "BTCUSDT")
default_base_qty = float(os.environ.get("base_qty", 0.01))
webhook_password = os.environ["webhook_password"]
telegram_token = os.environ["telegram_token"]
telegram_chat_id = os.environ["telegram_chat_id"]
env = os.environ.get("env", "live")
debug_responses = os.environ.get("debug_responses", "False").lower() == "true"
base_url = "https://api-testnet.bybit.com" if env == "test" else "https://api.bybit.com"

MAX_TP_DISTANCE_PERC = 0.30
MAX_SL_DISTANCE_PERC = 0.07  # ← тепер стоп-лосс дозволений до -7%


app = Flask(__name__)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    try:
        requests.post(url, json=data)
    except Exception as e:
        print(f"Telegram Error: {e}")

def sign_request(api_key, api_secret, body, timestamp):
    param_str = f"{timestamp}{api_key}5000{body}"
    return hmac.new(bytes(api_secret, "utf-8"), msg=bytes(param_str, "utf-8"), digestmod=hashlib.sha256).hexdigest()

def get_price(symbol):
    try:
        url = f"{base_url}/v5/market/tickers?category=linear&symbol={symbol}"
        response = requests.get(url)
        data = response.json()
        if "result" in data and "list" in data["result"]:
            last_price = data["result"]["list"][0].get("lastPrice")
            return float(last_price) if last_price else None
        return None
    except Exception as e:
        print(f"❌ get_price() error: {e}")
        return None

def is_tp_valid(tp, price):
    return abs(tp - price) / price <= MAX_TP_DISTANCE_PERC

def is_sl_valid(sl, price):
    return abs(sl - price) / price <= MAX_SL_DISTANCE_PERC

def create_market_order(symbol, side, qty):
    try:
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        order_data = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "ImmediateOrCancel"
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
        url = f"{base_url}/v5/order/create"
        response = requests.post(url, data=body, headers=headers)
        return response.json()
    except Exception as e:
        print(f"❌ Market order error: {e}")
        return None

def create_take_profit_order(symbol, side, qty, tp):
    try:
        price = get_price(symbol)
        if price is None:
            send_telegram_message("❌ Не вдалося отримати ціну для TP.")
            return None

        max_tp = price * (1 + MAX_TP_DISTANCE_PERC)
        if tp > max_tp:
            original_tp = tp
            tp = round(max_tp, 2)
            send_telegram_message(
                f"⚠️ TP {original_tp} занадто далекий від ціни {price}. "
                f"Автоматично скориговано до {tp} (макс {MAX_TP_DISTANCE_PERC*100}%)."
            )

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
            "timeInForce": "PostOnly",
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
        url = f"{base_url}/v5/order/create"
        response = requests.post(url, data=body, headers=headers)
        return response.json()
    except Exception as e:
        print(f"❌ TP fallback error: {e}")
        return None


def create_stop_loss_order(symbol, side, qty, sl):
    try:
        price = get_price(symbol)
        if not is_sl_valid(sl, price):
            send_telegram_message(f"🚫 SL {sl} занадто далекий від ціни {price}. Не створюю.")
            return None
        trigger_direction = 2 if side == "Buy" else 1
        sl_side = "Sell" if side == "Buy" else "Buy"
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        order_data = {
            "category": "linear",
            "symbol": symbol,
            "side": sl_side,
            "orderType": "Market",
            "qty": str(qty),
            "triggerPrice": str(sl),
            "triggerDirection": trigger_direction,
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
        url = f"{base_url}/v5/order/create"
        response = requests.post(url, data=body, headers=headers)
        return response.json()
    except Exception as e:
        print(f"❌ SL fallback error: {e}")
        return None


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        if not data or data.get("password") != webhook_password:
            return {"error": "Unauthorized"}, 401
        side = data.get("side")
        symbol = data.get("symbol", default_symbol)
        qty = float(data.get("qty", default_base_qty))
        tp = float(data.get("tp"))
        sl = float(data.get("sl"))

        market_result = create_market_order(symbol, side, qty)
        if not market_result or market_result.get("retCode") != 0:
            send_telegram_message(f"❌ Market ордер не створено: {market_result}")
            return {"error": "Market order failed"}, 400

        tp_result = create_take_profit_order(symbol, side, qty, tp)
        sl_result = create_stop_loss_order(symbol, side, qty, sl)

        if tp_result and sl_result:
            send_telegram_message(f"✅ Ордер виконано. Пара: {symbol}, Сторона: {side}, TP: {tp}, SL: {sl}")
        else:
            send_telegram_message(f"⚠️ Ордер частково виконано. TP або SL не були створені.\nTP: {tp_result is not None}, SL: {sl_result is not None}")

        if debug_responses:
    send_telegram_message(f"🧾 Market Order виконано: {side} {symbol}, Qty: {qty}")

    tp_success = tp_result and tp_result.get("retCode") == 0
    sl_success = sl_result and sl_result.get("retCode") == 0

    tp_price = tp
    sl_price = sl
    tp_id = tp_result["result"].get("orderId", "N/A") if tp_success else "❌"
    sl_id = sl_result["result"].get("orderId", "N/A") if sl_success else "❌"

    summary = (
        f"📊 Ордер з TradingView виконано\n"
        f"Пара: {symbol} | Сторона: {side}\n"
        f"🎯 TP: {tp_price} (Limit) 🆔 {tp_id}\n"
        f"🛡 SL: {sl_price} (Trigger Market) 🆔 {sl_id}"
    )
    send_telegram_message(summary)


        return {"success": True}
    except Exception as e:
        error_msg = f"🔥 Webhook error: {e}"
        send_telegram_message(error_msg)
        return {"error": str(e)}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


