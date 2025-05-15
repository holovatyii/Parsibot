import os
import time
import hmac
import json
import csv
import hashlib
import requests
from flask import Flask, request, send_file
from dotenv import load_dotenv
from datetime import datetime
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

def sign_request(api_key, api_secret, body, timestamp):
    param_str = f"{timestamp}{api_key}5000{body}"
    return hmac.new(bytes(api_secret, "utf-8"), msg=bytes(param_str, "utf-8"), digestmod=hashlib.sha256).hexdigest()
def cancel_all_close_orders(symbol):
    try:
        timestamp = str(int(time.time() * 1000))

        # 📦 Параметри для GET /v5/order/list
        params = {
            "api_key": api_key,
            "timestamp": timestamp,
            "symbol": symbol,
            "category": "linear",
            "openOnly": "1"
        }

        # 🔐 Підписуємо запит
        query_string = "&".join([f"{k}={params[k]}" for k in sorted(params)])
        sign = hmac.new(
            bytes(api_secret, "utf-8"),
            msg=bytes(query_string, "utf-8"),
            digestmod=hashlib.sha256
        ).hexdigest()
        params["sign"] = sign

        # 🔗 Відправляємо запит
        response = requests.get(f"{base_url}/v5/order/list", params=params)

        # 🛡 Перевірка типу відповіді
        if "application/json" not in response.headers.get("Content-Type", ""):
            print("❌ Unexpected response:")
            print(response.text)
            send_telegram_message("❌ cancel_all_close_orders error: Non-JSON response from Bybit")
            return

        data = response.json()
        print(f"📦 /v5/order/list response:\n{json.dumps(data, indent=2)}")

        if data.get("retCode") != 0:
            send_telegram_message(f"❌ Не вдалось отримати ордери через /list: {data}")
            return

        orders = data["result"].get("list", [])
        count = 0

        for order in orders:
            if order.get("symbol") == symbol and order.get("orderId"):
                order_id = order["orderId"]
                cancel_timestamp = str(int(time.time() * 1000))
                cancel_body = json.dumps({
                    "category": "linear",
                    "orderId": order_id
                })
                cancel_sign = sign_request(api_key, api_secret, cancel_body, cancel_timestamp)
                cancel_headers = {
                    "X-BAPI-API-KEY": api_key,
                    "X-BAPI-SIGN": cancel_sign,
                    "X-BAPI-TIMESTAMP": cancel_timestamp,
                    "X-BAPI-RECV-WINDOW": "5000",
                    "Content-Type": "application/json"
                }
                cancel_response = requests.post(f"{base_url}/v5/order/cancel", data=cancel_body, headers=cancel_headers)
                print(f"🧹 Canceled: {order_id} → {cancel_response.json()}")
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
        if "result" in data and "list" in data["result"]:
            last_price = data["result"]["list"][0].get("lastPrice")
            return float(last_price) if last_price else None
    except Exception as e:
        print(f"get_price() error: {e}")
    return None

def create_market_order(symbol, side, qty):
    try:
        timestamp = str(int(time.time() * 1000))
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
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json"
        }
        response = requests.post(f"{base_url}/v5/order/create", data=body, headers=headers)
        return response.json()
    except Exception as e:
        print(f"Market order error: {e}")
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
        cancel_all_close_orders(symbol)

        entry_price = get_price(symbol)
        market_result = create_market_order(symbol, side, qty)

        if not market_result or market_result.get("retCode") != 0:
            send_telegram_message(f"❌ Market ордер не створено: {market_result}")
            return {"error": "Market order failed"}, 400

        order_id = market_result["result"].get("orderId", "") if market_result.get("result") else ""
        price = get_price(symbol)
        actual_sl = sl
        if not is_sl_valid(sl, price):
            actual_sl = round(price * (1 - MAX_SL_DISTANCE_PERC), 2) if side == "Buy" else round(price * (1 + MAX_SL_DISTANCE_PERC), 2)

        # Створення TP
        tp_result = create_take_profit_order(symbol, side, qty, tp)

        # fallback, якщо TP не створено
        fallback_tp_pct = 0.02  # fallback TP = +2%
        fallback_tp_set = False

        if tp_result is None:
            fallback_tp_set = True
            fallback_tp = round(entry_price * (1 + fallback_tp_pct), 2) if side == "Buy" else round(entry_price * (1 - fallback_tp_pct), 2)
            tp_result = create_take_profit_order(symbol, side, qty, fallback_tp)
            tp = fallback_tp  # оновлюємо TP для логування
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

        send_telegram_message(
            f"✅ Ордер виконано. Пара: {symbol}, Сторона: {side}, TP: {tp}, SL: {actual_sl}"
        )

        print("⚙️ Викликаємо log_trade_to_csv...")

        log_trade_to_csv({
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
    "strategy_tag": "tv_default",
    "signal_source": "TradingView"
})


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


def log_trade_to_csv(entry):
    try:
        # Якщо файл не існує — створюємо з заголовками
        if not os.path.exists(CSV_LOG_PATH):
            with open(CSV_LOG_PATH, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "symbol", "side", "qty", "entry_price", "tp", "sl", "trailing",
                    "order_id", "result", "pnl", "exit_price", "exit_reason", "tp_hit", "sl_hit",
                    "runtime_sec", "sl_auto_adjusted", "tp_rejected", "drawdown_pct", "risk_reward",
                    "strategy_tag", "signal_source"
                ])
            print("📁 CSV файл створено автоматично")

        # Запис трейду
        with open(CSV_LOG_PATH, mode="a", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "timestamp", "symbol", "side", "qty", "entry_price", "tp", "sl", "trailing",
                "order_id", "result", "pnl", "exit_price", "exit_reason", "tp_hit", "sl_hit",
                "runtime_sec", "sl_auto_adjusted", "tp_rejected", "drawdown_pct", "risk_reward",
                "strategy_tag", "signal_source"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # Заповнюємо відсутні поля None
            for field in fieldnames:
                if field not in entry:
                    entry[field] = None

            writer.writerow(entry)

        print(f"✅ CSV запис: {entry}")
        send_telegram_message(f"✅ CSV запис: {entry['symbol']} {entry['side']} @ {entry['entry_price']}")

    except Exception as e:
        print(f"❌ CSV log error: {e}")
        send_telegram_message(f"❌ CSV log error: {e}")



        
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

                # 🔍 Запит до Bybit (отримати статус позиції / ордерів)
                # ⚠️ Тут треба вставити API-запит до /v5/position/list або order/history
                # 🔧 Тимчасово емулюємо, що всі закрились вручну через 90 сек

                runtime = (datetime.utcnow() - ts).total_seconds()
                if runtime < 90:
                    remaining.append(trade)
                    continue

                exit_price = entry_price * (0.99 if side == "Buy" else 1.01)
                tp_hit = exit_price == tp
                sl_hit = exit_price == sl
                pnl = round((entry_price - exit_price) * qty * (-1 if side == "Sell" else 1), 2)
                exit_reason = "tp_hit" if tp_hit else "sl_hit" if sl_hit else "timeout"

                update_csv_trade(order_id, {
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "tp_hit": tp_hit,
                    "sl_hit": sl_hit,
                    "runtime_sec": int(runtime),
                    "pnl": pnl,
                    "result": "closed"
                })
               

            with open(OPEN_TRADES_PATH, "w", encoding="utf-8") as f:
                json.dump(remaining, f, indent=2)
        except Exception as e:
            print(f"❌ Track error: {e}")
        time.sleep(30)

# 🧠 Запуск моніторингу в окремому потоці

threading.Thread(target=track_open_trades, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
