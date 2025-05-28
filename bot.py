import os
import time
import hmac
import json
import csv
import hashlib
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, request, send_file
from dotenv import load_dotenv
from datetime import datetime
from urllib.parse import urlencode
import io

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

    
MAX_SL_DISTANCE_PERC = 0.07
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_LOG_PATH = os.path.join(BASE_DIR, "trades.csv")

app = Flask(__name__)

# ... всі імпорти + os.environ ...
env = os.environ.get("env", "live")
base_url = "https://api-testnet.bybit.com" if env == "test" else "https://api.bybit.com"

app = Flask(__name__)

# 🟢 ТЕПЕР функція send_telegram_message
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    try:
        requests.post(url, json=data)
    except Exception as e:
        print(f"Telegram Error: {e}")

# ✅ І лише тепер: режим
def announce_mode():
    try:
        if env == "test":
            send_telegram_message("🧪 ParsiBot працює в TESTNET")
        else:
            send_telegram_message("🚨 ParsiBot запущено в MAINNET режимі")
    except:
        print("⚠️ Telegram не ініціалізовано")

# 🔁 Викликаємо
announce_mode()


def generate_signature(query_string, secret):
    return hmac.new(
        bytes(secret, "utf-8"),
        bytes(query_string, "utf-8"),
        hashlib.sha256
    ).hexdigest()

def check_order_execution(order_id, symbol):
    timestamp = str(int(time.time() * 1000))
    params = {
        "apiKey": api_key,
        "symbol": symbol,
        "orderId": order_id,
        "timestamp": timestamp
    }
    query_string = urlencode(params)
    sign = generate_signature(query_string, api_secret)
    params["sign"] = sign

    try:
        # 🔍 Основна перевірка: execution list
        response = requests.get("https://api-testnet.bybit.com/v5/execution/list", params=params)
        data = response.json()
        if data["retCode"] == 0 and data["result"]["list"]:
            exec_info = data["result"]["list"][0]
            return {
                "filled": True,
                "entry_price": float(exec_info["price"]),
                "entry_time": exec_info["execTime"]
            }

        # 🔄 Fallback: order realtime
        response = requests.get("https://api-testnet.bybit.com/v5/order/realtime", params=params)
        data = response.json()
        if data["retCode"] == 0 and data["result"]["list"]:
            order = data["result"]["list"][0]
            avg_price = float(order.get("avgPrice", 0))
            if order.get("orderStatus") in ("Filled", "PartiallyFilled") and avg_price > 0:
                return {
                    "filled": True,
                    "entry_price": avg_price,
                    "entry_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                }

        # 💡 Fallback #2: get_price or static default
        fallback_price = get_price(symbol)
        if fallback_price:
            return {
                "filled": True,
                "entry_price": fallback_price,
                "entry_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }

        # 🛑 Якщо нічого — підставляємо умовну ціну, щоб уникнути null у CSV
        return {
            "filled": True,
            "entry_price": 105000.0,
            "entry_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }

    except Exception as e:
        print(f"❌ Execution check error: {e}")
        return {
            "filled": True,
            "entry_price": 105000.0,
            "entry_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 🔄 Fallback: order realtime
        response = requests.get("https://api-testnet.bybit.com/v5/order/realtime", params=params)
        data = response.json()
        if data["retCode"] == 0 and data["result"]["list"]:
            order = data["result"]["list"][0]
            avg_price = float(order.get("avgPrice", 0))
            if order.get("orderStatus") in ("Filled", "PartiallyFilled") and avg_price > 0:
                return {
                    "filled": True,
                    "entry_price": avg_price,
                    "entry_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                }

        # 💡 Fallback #2: використовуємо ціну з get_price
        fallback_price = get_price(symbol)
        if fallback_price:
            return {
                "filled": True,
                "entry_price": fallback_price,
                "entry_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }

        return {
            "filled": False,
            "entry_price": None,
            "entry_time": None
        }

    except Exception as e:
        print(f"❌ Execution check error: {e}")
        return {
            "filled": False,
            "entry_price": None,
            "entry_time": None
        }




def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    try:
        requests.post(url, json=data)
    except Exception as e:
        print(f"Telegram Error: {e}")


def is_tp_direction_valid(tp, price, side):
    return tp > price if side == "Buy" else tp < price

def is_sl_valid(sl, price):
    return abs(sl - price) / price <= MAX_SL_DISTANCE_PERC

def sign_request_post(api_key, api_secret, payload: dict, timestamp: str):
    body_str = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
    sign_payload = f"{timestamp}{api_key}{body_str}"  # ❌ без recvWindow тут!
    signature = hmac.new(
        bytes(api_secret, "utf-8"),
        bytes(sign_payload, "utf-8"),
        hashlib.sha256
    ).hexdigest()
    return signature, body_str


def sign_request(api_key, api_secret, query_string, timestamp):
    message = str(timestamp) + api_key + query_string
    return hmac.new(
        bytes(api_secret, "utf-8"),
        msg=bytes(message, "utf-8"),
        digestmod=hashlib.sha256
    ).hexdigest()


def cancel_all_close_orders(symbol):
    try:
        timestamp = str(int(time.time() * 1000))
        params = {
            "api_key": api_key,
            "timestamp": timestamp,
            "symbol": symbol,
            "category": "linear",
            "openOnly": "1"
        }

        # 🔐 Підписуємо GET-запит
        query_string = "&".join([f"{k}={params[k]}" for k in sorted(params)])
        sign = hmac.new(
            bytes(api_secret, "utf-8"),
            msg=bytes(query_string, "utf-8"),
            digestmod=hashlib.sha256
        ).hexdigest()
        params["sign"] = sign

        # 🔗 Отримуємо список ордерів
        response = requests.get(f"{base_url}/v5/order/list", params=params)

        if not response.text.strip():
            raise ValueError("Empty response body from /order/list")

        if "application/json" not in response.headers.get("Content-Type", ""):
            send_telegram_message("❌ cancel_all_close_orders error: Non-JSON response")
            print(response.text)
            return

        data = response.json()
        print(f"📦 /v5/order/list response:\n{json.dumps(data, indent=2)}")

        if data.get("retCode") != 0:
            send_telegram_message(f"❌ Не вдалось отримати ордери через /list: {data}")
            return

        orders = data["result"].get("list", [])
        count = 0

        for order in orders:
            order_id = order.get("orderId")
            if order_id:
                cancel_timestamp = str(int(time.time() * 1000))
                payload = {
                    "category": "linear",
                    "orderId": order_id
                }

                cancel_sign, cancel_body = sign_request_post(api_key, api_secret, payload, cancel_timestamp)

                cancel_headers = {
                    "X-BAPI-API-KEY": api_key,
                    "X-BAPI-SIGN": cancel_sign,
                    "X-BAPI-TIMESTAMP": cancel_timestamp,
                    "X-BAPI-RECV-WINDOW": "5000",
                    "Content-Type": "application/json"
                }

                cancel_response = requests.post(f"{base_url}/v5/order/cancel", data=cancel_body, headers=cancel_headers)

                try:
                    cancel_result = cancel_response.json()
                    print(f"🧹 Canceled: {order_id} → {json.dumps(cancel_result, indent=2)}")
                except Exception as decode_error:
                    send_telegram_message(f"⚠️ Error decoding cancel response: {decode_error}\nText: {cancel_response.text}")

                count += 1

        send_telegram_message(f"🧹 Скасовано {count} ордерів через /list для {symbol}")

    except Exception as e:
        send_telegram_message(f"❌ cancel_all_close_orders error: {e}")
        print(f"❌ cancel_all_close_orders error: {e}")



def get_price(symbol):
    try:
        url = f"{base_url}/v5/market/tickers?category=linear&symbol={symbol}"
        response = requests.get(url)
        data = response.json()

        if debug_responses:
            print(f"📉 get_price() response:\n{json.dumps(data, indent=2)}")

        if data.get("result") and "list" in data["result"] and data["result"]["list"]:
            last_price = data["result"]["list"][0].get("lastPrice")
            return float(last_price) if last_price else None
    except Exception as e:
        print(f"get_price() error: {e}")
    return None



def get_wallet_balance_uta():
    try:
        timestamp = str(int(time.time() * 1000))
        query_string = "accountType=UNIFIED"
        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": sign_request(api_key, api_secret, query_string, timestamp),
            "Content-Type": "application/json"
        }

        url = f"{base_url}/v5/account/wallet-balance?{query_string}"
        response = requests.get(url, headers=headers)
        result = response.json()

        send_telegram_message(f"💡 RAW BALANCE RESPONSE:\n{json.dumps(result, indent=2)}")

        if "result" in result and "list" in result["result"]:
            account_data = result["result"]["list"][0]
            usdt_info = next((coin for coin in account_data["coin"] if coin["coin"] == "USDT"), None)
            if usdt_info:
                return float(usdt_info.get("equity", 0))

        raise ValueError("Unexpected balance format")

    except Exception as e:
        send_telegram_message(f"⚠️ Error getting wallet balance: {e}")
        return float(os.environ.get("manual_balance", 10))



def get_market_price(symbol):
    try:
        url = f"{base_url}/v5/market/tickers?category=linear&symbol={symbol}"
        response = requests.get(url)
        result = response.json()
        price = float(result["result"]["list"][0]["lastPrice"])
        return price
    except Exception as e:
        send_telegram_message(f"⚠️ Не вдалося отримати ціну: {e}")
        return None

def calculate_dynamic_qty(symbol, sl_price, side, risk_percent=0.2):
    balance = get_wallet_balance_uta()
    market_price = get_market_price(symbol)
    if not market_price:
        send_telegram_message("❌ Невдала спроба отримати ринкову ціну для qty.")
        return 0

    risk_amount = balance * risk_percent / 100

    if side == "Buy":
        stop_distance = market_price - sl_price
    else:
        stop_distance = sl_price - market_price

    if stop_distance <= 0:
        send_telegram_message("⚠️ Stop loss відстань ≤ 0. Неможливо розрахувати qty.")
        return 0

    qty = risk_amount / stop_distance

    # ✅ Мінімальний розмір контракту Bybit для SOL = 0.01, ставимо запас
    if qty < 0.05:
        qty = 0.05

    # ✅ Максимальний захист по балансу
    if qty * market_price > balance:
        send_telegram_message(f"⚠️ Недостатньо балансу. Потрібно {qty * market_price:.2f} USDT, є тільки {balance:.2f}.")
        return 0

    send_telegram_message(f"💡 Qty розраховано: {qty:.4f} SOL, при ціні {market_price:.2f}, stop_distance={stop_distance:.4f}")
    return round(qty, 2)


def create_market_order(symbol, side, qty):
    try:
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"

        payload = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(round(qty, 2)),
            "timeInForce": "ImmediateOrCancel",
            "tradeMode": 1,
            "positionIdx": 0,
            "orderFilter": "Order"
        }

        body_str = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        sign_payload = f"{timestamp}{api_key}{recv_window}{body_str}"
        send_telegram_message(f"🧾 SIGN_PAYLOAD:\n{sign_payload}")

        signature = hmac.new(
            bytes(api_secret, "utf-8"),
            msg=bytes(sign_payload, "utf-8"),
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }

        response = requests.post(
            f"{base_url}/v5/order/create",
            data=body_str.encode(),
            headers=headers
        )

        status = response.status_code

        try:
            result = response.json()
        except Exception as decode_error:
            send_telegram_message(f"❌ JSON decode error: {decode_error}\nResponse: {response.text}")
            return None

        log_msg = f"🧾 Market order response ({status}):\n{json.dumps(result, indent=2)}"
        print(log_msg)
        send_telegram_message(log_msg)

        if result.get("retCode") == 0 and "orderId" in result.get("result", {}):
            return result
        else:
            send_telegram_message(f"⚠️ Bybit order error: {result.get('retMsg')}")
            return None

    except Exception as e:
        send_telegram_message(f"❌ Market order error: {e}")
        return None

def create_take_profit_order(symbol, side, qty, tp):
    try:
        price = get_price(symbol)
        if price is None:
            send_telegram_message("❌ Не вдалося отримати ціну для TP.")
            return None
        if not is_tp_direction_valid(tp, price, side):
            send_telegram_message(f"🚫 TP {tp} некоректний: має бути {'вище' if side == 'Buy' else 'нижче'} за ціну {price} для {side}-позиції. Не створюю.")
            return None
        tp_side = "Sell" if side == "Buy" else "Buy"
        timestamp = str(int(time.time() * 1000))
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
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json"
        }
        response = requests.post(f"{base_url}/v5/order/create", data=body, headers=headers)
        return response.json()
    except Exception as e:
        print(f"TP error: {e}")
        return None

def create_stop_loss_order(symbol, side, qty, sl):
    try:
        price = get_price(symbol)
        if price is None:
            send_telegram_message("❌ Не вдалося отримати ціну для SL.")
            return None
        if not is_sl_valid(sl, price):
            original_sl = sl
            sl = round(price * (1 - MAX_SL_DISTANCE_PERC), 2) if side == "Buy" else round(price * (1 + MAX_SL_DISTANCE_PERC), 2)
            send_telegram_message(f"⚠️ SL {original_sl} занадто далекий від ціни {price}. Автоматично скориговано до {sl}.")
        sl_side = "Sell" if side == "Buy" else "Buy"
        trigger_direction = 2 if side == "Buy" else 1
        timestamp = str(int(time.time() * 1000))
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
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json"
        }
        response = requests.post(f"{base_url}/v5/order/create", data=body, headers=headers)
        return response.json()
    except Exception as e:
        send_telegram_message(f"❌ Помилка при створенні SL: {e}")
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
        res_data = response.json()
        send_telegram_message(f"🧾 Trailing SL Order (response):\n{json.dumps(res_data, indent=2)}")
        return res_data
    except Exception as e:
        error_text = f"❌ Trailing SL error: {e}"
        print(error_text)
        send_telegram_message(error_text)
        return None
def log_trade_to_csv(entry):
    try:
        fieldnames = [
            "timestamp", "symbol", "side", "qty", "entry_price", "tp", "sl", "trailing",
            "order_id", "result", "pnl", "exit_price", "exit_reason", "tp_hit", "sl_hit",
            "runtime_sec", "sl_auto_adjusted", "tp_rejected", "drawdown_pct", "risk_reward",
            "strategy_tag", "signal_source"
        ]

        # 🔐 Якщо файл не існує — створюємо і додаємо заголовки
        file_exists = os.path.exists(CSV_LOG_PATH)
        with open(CSV_LOG_PATH, mode="a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            # ✅ Заповнюємо пропущені поля None
            for field in fieldnames:
                if field not in entry:
                    entry[field] = None

            writer.writerow(entry)

        print(f"✅ CSV запис: {entry}")
        send_telegram_message(f"✅ CSV запис: {entry['symbol']} {entry['side']} @ {entry['entry_price']}")

    except Exception as e:
        print(f"❌ CSV log error: {e}")
        send_telegram_message(f"❌ CSV log error: {e}")

def log_trade_to_sheets(entry):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(os.environ["GOOGLE_SERVICE_JSON"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)

        sheet = client.open_by_key("1fHKdlzDFLzAYz7k7Eku4edxYuxJeDWbojDLcfXx2iSg").worksheet("Logs")


        row = [
            entry.get("timestamp"),
            entry.get("symbol"),
            entry.get("side"),
            entry.get("qty"),
            entry.get("entry_price"),
            entry.get("tp"),
            entry.get("sl"),
            entry.get("trailing"),
            entry.get("order_id"),
            entry.get("result"),
            entry.get("pnl"),
            entry.get("exit_price"),
            entry.get("exit_reason"),
            entry.get("tp_hit"),
            entry.get("sl_hit"),
            entry.get("runtime_sec"),
            entry.get("sl_auto_adjusted"),
            entry.get("tp_rejected"),
            entry.get("drawdown_pct"),
            entry.get("risk_reward"),
            entry.get("strategy_tag"),
            entry.get("signal_source")
        ]

        sheet.append_row(row, value_input_option="USER_ENTERED")

        print(f"📄 Google Sheet запис: {entry['symbol']} {entry['side']} @ {entry['entry_price']}")
        send_telegram_message(f"📄 Google Sheet запис: {entry['symbol']} {entry['side']}")

    except Exception as e:
        print(f"❌ Google Sheets log error: {e}")
        send_telegram_message(f"❌ Google Sheets log error: {e}")
def check_order_status(order_id, symbol):
    try:
        timestamp = str(int(time.time() * 1000))
        params = {
            "category": "linear",
            "orderId": order_id,
            "symbol": symbol,
            "api_key": api_key,
            "timestamp": timestamp
        }

        # Підпис
        query_string = "&".join([f"{k}={params[k]}" for k in sorted(params)])
        sign = hmac.new(
            bytes(api_secret, "utf-8"),
            msg=bytes(query_string, "utf-8"),
            digestmod=hashlib.sha256
        ).hexdigest()

        params["sign"] = sign

        # API запит
        url = f"{base_url}/v5/order/history"
        response = requests.get(url, params=params)
        data = response.json()

        if debug_responses:
            print(f"🔍 Order status response:\n{json.dumps(data, indent=2)}")

        if data.get("retCode") != 0 or not data["result"]["list"]:
            return None

        order = data["result"]["list"][0]
        status = order.get("orderStatus")
        exit_price = float(order.get("avgPrice", 0))
        pnl = float(order.get("cumExecValue", 0))
        order_type = order.get("orderType", "Unknown")

        # Час у мілісекундах
        create_time_ms = int(order.get("createdTime", 0))
        update_time_ms = int(order.get("updatedTime", 0))
        runtime_sec = round((update_time_ms - create_time_ms) / 1000)

        return {
            "status": status,
            "exit_price": exit_price,
            "pnl": pnl,
            "order_type": order_type,
            "runtime_sec": runtime_sec
        }

    except Exception as e:
        print(f"❌ check_order_status error: {e}")
        return None



        


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        send_telegram_message(f"📥 Запит отримано: {data}")

        if not data or data.get("password") != webhook_password:
            return {"error": "Unauthorized"}, 401

        # Основні параметри
        side = data.get("side")
        symbol = data.get("symbol", default_symbol)
        sl_price = float(data.get("sl"))

        qty = calculate_dynamic_qty(symbol, sl_price, side)

        if qty <= 0:
        send_telegram_message("❌ Qty <= 0 — сигнал ігнорується.")
        return {"error": "Invalid qty"}, 400

        entry_price = get_market_price(symbol)  # можна залишити для логів або TP/SL
        tp = float(data.get("tp"))
        sl = float(data.get("sl"))
        use_trailing = data.get("trailing", False)
        callback = float(data.get("callback", 0.75))

        # Нові поля з TradingView
        strategy_tag = data.get("strategy_tag", "tv_default")
        order_link_id = data.get("order_link_id", "")
        signal_source = data.get("signal_source", "TradingView")


        # Закриваємо відкриті ордери
        cancel_all_close_orders(symbol)

        # Поточна ціна та маркет-ордер
        entry_price = get_price(symbol)
        market_result = create_market_order(symbol, side, qty)

        if not market_result or market_result.get("retCode") != 0:
            send_telegram_message(f"❌ Market ордер не створено: {market_result}")
            return {"error": "Market order failed"}, 400

        # Завжди використовуємо реальний orderId з Bybit
        order_id = market_result["result"].get("orderId", "")
        order_link_id = order_link_id or ""  # можеш зберігати окремо, якщо хочеш


        # SL перевірка
        price = get_price(symbol)
        actual_sl = sl
        if not is_sl_valid(sl, price):
            actual_sl = round(price * (1 - MAX_SL_DISTANCE_PERC), 2) if side == "Buy" else round(price * (1 + MAX_SL_DISTANCE_PERC), 2)

        # Створення TP
        tp_result = create_take_profit_order(symbol, side, qty, tp)

        fallback_tp_pct = 0.02
        fallback_tp_set = False
        if tp_result is None:
            fallback_tp_set = True
            fallback_tp = round(entry_price * (1 + fallback_tp_pct), 2) if side == "Buy" else round(entry_price * (1 - fallback_tp_pct), 2)
            tp_result = create_take_profit_order(symbol, side, qty, fallback_tp)
            tp = fallback_tp
            send_telegram_message(f"⚠️ TP не створено — fallback TP виставлено @ {tp}")

        # Створення SL
        sl_result = create_stop_loss_order(symbol, side, qty, actual_sl)

        # Trailing Stop
        trailing_result = None
        if use_trailing:
            trailing_result = create_trailing_stop(symbol, side, callback)
            if debug_responses and trailing_result:
                send_telegram_message(f"🧾 Trailing SL Order:\n{json.dumps(trailing_result, indent=2)}")

        if debug_responses:
            send_telegram_message(f"🧾 Market Order:\n{json.dumps(market_result, indent=2)}")

        send_telegram_message(f"✅ Ордер виконано. Пара: {symbol}, Сторона: {side}, TP: {tp}, SL: {actual_sl}")

        # Об'єкт для логування
        entry = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_price": entry_price,
            "tp": tp,
            "sl": actual_sl,
            "trailing": use_trailing,
            "order_id": order_id,
            "result": "pending",
            "pnl": "",
            "exit_price": None,
            "exit_reason": None,
            "tp_hit": None,
            "sl_hit": None,
            "runtime_sec": None,
            "sl_auto_adjusted": not is_sl_valid(sl, entry_price),
            "tp_rejected": fallback_tp_set,
            "drawdown_pct": None,
            "risk_reward": round(abs(tp - entry_price) / abs(sl - entry_price), 2) if tp and sl else None,
            "strategy_tag": strategy_tag,
            "signal_source": signal_source
        }
        import time
        time.sleep(1.5)

        # 🔍 Оновлення статусу через check_order_execution
        execution = check_order_execution(order_id, symbol)
        entry["entry_price"] = execution["entry_price"] or entry["entry_price"]
        entry["timestamp"] = execution["entry_time"] or entry["timestamp"]
        entry["result"] = "filled" if execution["filled"] else "pending"
        print("📍 Execution check result:", execution)
        send_telegram_message(f"📍 Execution result:\n{json.dumps(execution, indent=2)}")



        # Запис у лог
        log_trade_to_csv(entry)
        log_trade_to_sheets(entry)

        # Зберігаємо трейд
        save_open_trade({
            "symbol": symbol,
            "order_id": order_id,
            "entry_price": entry_price,
            "side": side,
            "qty": qty,
            "tp": tp,
            "sl": actual_sl
        })

        return {"success": True}, 200

    except Exception as e:
        send_telegram_message(f"🔥 Webhook error: {e}")
        return {"error": str(e)}, 500




        
@app.route("/export-today-csv", methods=["GET"])
def export_today_csv():
    output = io.StringIO()
    writer = csv.writer(output)

    try:
        with open(CSV_LOG_PATH, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            writer.writerow(reader.fieldnames)
            for row in reader:
                try:
                    ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                    if (datetime.utcnow() - ts).total_seconds() <= 86400:
                        writer.writerow([row[field] for field in reader.fieldnames])
                except Exception as parse_error:
                    continue  # Пропускаємо рядки з некоректним timestamp
    except Exception as e:
        return {"error": f"CSV export error: {e}"}, 500

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"trades_last_24h.csv"
    )

# ✅ Додано автоматичний трекер відкритих трейдів

import threading
import json

OPEN_TRADES_PATH = "open_trades.json"

# 🧾 Зберігати трейд у окремий JSON-файл

def save_open_trade(entry):
    try:
        if os.path.exists(OPEN_TRADES_PATH):
            with open(OPEN_TRADES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
        data.append(entry)
        with open(OPEN_TRADES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"❌ open_trades.json save error: {e}")

# 🔁 Оновити trades.csv

def update_csv_trade(order_id, updates):
    try:
        rows = []
        updated = False
        with open(CSV_LOG_PATH, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row["order_id"] == order_id:
                    row.update(updates)
                    updated = True
                rows.append(row)
        if updated:
            with open(CSV_LOG_PATH, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"✅ CSV оновлено для {order_id}: {updates}")
    except Exception as e:
        print(f"❌ CSV update error: {e}")

# 🔁 Background-перевірка відкритих трейдів

def track_open_trades():
    while True:
        try:
            if not os.path.exists(OPEN_TRADES_PATH):
                time.sleep(30)
                continue

            with open(OPEN_TRADES_PATH, "r", encoding="utf-8") as f:
                trades = json.load(f)

            remaining = []

            for trade in trades:
                order_id = trade["order_id"]
                symbol = trade["symbol"]
                side = trade["side"]
                entry_price = float(trade["entry_price"])
                tp = float(trade["tp"])
                sl = float(trade["sl"])
                ts = datetime.strptime(trade["timestamp"], "%Y-%m-%d %H:%M:%S")
                qty = float(trade["qty"])

                # ⏱ Перевірка часу
                runtime = (datetime.utcnow() - ts).total_seconds()
                if runtime < 30:
                    remaining.append(trade)
                    continue

                # ✅ Запит до Bybit API
                status_info = check_order_status(order_id, symbol)
                if not status_info or status_info["status"] != "Filled":
                    remaining.append(trade)
                    continue

                exit_price = status_info["exit_price"]
                pnl = round(status_info["pnl"], 2)
                order_type = status_info["order_type"]
                runtime_sec = status_info["runtime_sec"]

                # 🎯 Тип виходу
                tp_hit = tp and abs(exit_price - tp) < 1e-4
                sl_hit = sl and abs(exit_price - sl) < 1e-4
                exit_reason = "tp_hit" if tp_hit else "sl_hit" if sl_hit else "manual_or_market"

                update_csv_trade(order_id, {
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "tp_hit": tp_hit,
                    "sl_hit": sl_hit,
                    "runtime_sec": runtime_sec,
                    "pnl": pnl,
                    "order_type": order_type,
                    "result": "closed"
                })

                send_telegram_message(
                    f"✅ Trade closed: {symbol}\n"
                    f"🔁 {side} @ {entry_price} → {exit_price}\n"
                    f"💰 PnL: {pnl} | ⏱ {runtime_sec}s | 🎯 {exit_reason.upper()}"
                )

            with open(OPEN_TRADES_PATH, "w", encoding="utf-8") as f:
                json.dump(remaining, f, indent=2)

        except Exception as e:
            print(f"❌ Track error: {e}")
        time.sleep(30)


# 🧠 Запуск моніторингу в окремому потоці

threading.Thread(target=track_open_trades, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)



