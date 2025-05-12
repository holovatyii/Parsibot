import os
import time
import hmac
import json
import csv
import hashlib
import requests
from flask import Flask, request
from dotenv import load_dotenv
from datetime import datetime

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
MAX_SL_DISTANCE_PERC = 0.07
CSV_LOG_PATH = "trades.csv"

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
            send_telegram_message(f"⚠️ TP {original_tp} занадто далекий від ціни {price}. Автоматично скориговано до {tp} (макс {MAX_TP_DISTANCE_PERC*100}%).")
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

def create_trailing_stop(symbol, side, callback_rate):
    try:
        position_idx = 0
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        order_data = {
            "category": "linear",
            "symbol": symbol,
            "trailingStop": str(callback_rate),
            "positionIdx": position_idx
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
        url = f"{base_url}/v5/position/trading-stop"
        response = requests.post(url, data=body, headers=headers)
        send_telegram_message(f"🧾 Trailing SL Response:\n{json.dumps(response.json(), indent=2)}")
        return response.json()
    except Exception as e:
        error_text = f"❌ Trailing SL error: {e}"
        print(error_text)
        send_telegram_message(error_text)
        return None

def log_trade_to_csv(entry):
    try:
        file_exists = os.path.isfile(CSV_LOG_PATH)
        with open(CSV_LOG_PATH, mode="a", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["timestamp", "symbol", "side", "qty", "entry_price", "tp", "sl", "trailing", "order_id", "result", "pnl"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(entry)
    except Exception as e:
        print(f"CSV log error: {e}")

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
        use_trailing = data.get("trailing", False)
        callback = float(data.get("callback", 0.75))

        entry_price = get_price(symbol)
        market_result = create_market_order(symbol, side, qty)
        if not market_result or market_result.get("retCode") != 0:
            send_telegram_message(f"❌ Market ордер не створено: {market_result}")
            return {"error": "Market order failed"}, 400

        tp_result = create_take_profit_order(symbol, side, qty, tp)
        sl_result = create_stop_loss_order(symbol, side, qty, sl)
        trailing_result = create_trailing_stop(symbol, side, callback) if use_trailing else None

        order_id = market_result["result"].get("orderId", "")

        log_trade_to_csv({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_price": entry_price,
            "tp": tp,
            "sl": sl,
            "trailing": use_trailing,
            "order_id": order_id,
            "result": "pending",
            "pnl": ""
        })

        send_telegram_message(f"✅ Ордер виконано. Пара: {symbol}, Сторона: {side}, TP: {tp}, SL: {sl}")
        return {"success": True}
    except Exception as e:
        send_telegram_message(f"🔥 Webhook error: {e}")
        return {"error": str(e)}, 500
from flask import send_file
import io
from flask import send_file
import io

@app.route("/export-today-csv", methods=["GET"])
def export_today_csv():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    output = io.StringIO()
    writer = csv.writer(output)
    
    try:
        with open(CSV_LOG_PATH, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            writer.writerow(reader.fieldnames)
            for row in reader:
                if row["timestamp"].startswith(today):
                    writer.writerow([row[field] for field in reader.fieldnames])
    except Exception as e:
        return {"error": f"CSV export error: {e}"}, 500

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"trades_{today}.csv"
    )

@app.route("/export-today-csv", methods=["GET"])
def export_today_csv():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    output = io.StringIO()
    writer = csv.writer(output)
    
    try:
        with open(CSV_LOG_PATH, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            writer.writerow(reader.fieldnames)
            for row in reader:
                if row["timestamp"].startswith(today):
                    writer.writerow([row[field] for field in reader.fieldnames])
    except Exception as e:
        return {"error": f"CSV export error: {e}"}, 500

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"trades_{today}.csv"
    )
# 🛠️ Автостворення CSV-файлу, якщо ще не існує
if not os.path.exists(CSV_LOG_PATH):
    with open(CSV_LOG_PATH, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "symbol", "side", "qty", "entry_price", "tp", "sl", "trailing", "order_id", "result", "pnl"])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
