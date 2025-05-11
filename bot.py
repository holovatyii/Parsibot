
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

def log_trade_to_csv(entry):
    try:
        file_exists = os.path.isfile(CSV_LOG_PATH)
        with open(CSV_LOG_PATH, mode="a", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "timestamp", "symbol", "side", "qty", "entry_price", "tp", "sl", "trailing",
                "callback_rate", "order_id", "exit_price", "exit_reason", "pnl",
                "duration_sec", "leverage", "status", "error"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(entry)
    except Exception as e:
        print(f"CSV log error: {e}")

def update_trade_on_close(order_id, exit_price, pnl, exit_reason="manual_exit"):
    try:
        rows = []
        with open(CSV_LOG_PATH, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row["order_id"] == order_id and row["status"] != "closed":
                    row["exit_price"] = exit_price
                    row["pnl"] = pnl
                    row["exit_reason"] = exit_reason
                    row["status"] = "closed"
                    entry_time = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                    duration = (datetime.utcnow() - entry_time).total_seconds()
                    row["duration_sec"] = int(duration)

                    sign = "+" if float(pnl) > 0 else ""
                    emoji = "🟢" if float(pnl) > 0 else "🔴"
                    send_telegram_message(
                        f"{emoji} Угода закрита: {sign}{float(pnl):.2f}$\nПара: {row['symbol']} | Тип: {row['side']}\nПричина: {exit_reason}"
                    )
                rows.append(row)

        with open(CSV_LOG_PATH, mode="w", newline="", encoding="utf-8") as csvfile:
            fieldnames = rows[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    except Exception as e:
        print(f"❌ update_trade_on_close error: {e}")
        send_telegram_message(f"❌ update_trade_on_close error: {e}")

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
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        order_id = f"{symbol}_{int(time.time())}"

        log_trade_to_csv({
            "timestamp": timestamp,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_price": entry_price,
            "tp": tp,
            "sl": sl,
            "trailing": use_trailing,
            "callback_rate": callback,
            "order_id": order_id,
            "exit_price": "",
            "exit_reason": "",
            "pnl": "",
            "duration_sec": "",
            "leverage": "",
            "status": "opened",
            "error": ""
        })

        send_telegram_message(f"✅ Ордер виконано. Пара: {symbol}, Сторона: {side}, TP: {tp}, SL: {sl}")
        return {"success": True}
    except Exception as e:
        send_telegram_message(f"🔥 Webhook error: {e}")
        return {"error": str(e)}, 500

@app.route("/close", methods=["POST"])
def close_trade():
    try:
        data = request.get_json(force=True)
        if not data or data.get("password") != webhook_password:
            return {"error": "Unauthorized"}, 401

        order_id = data.get("order_id")
        exit_price = data.get("exit_price")
        pnl = data.get("pnl")
        reason = data.get("exit_reason", "manual_exit")

        update_trade_on_close(order_id, str(exit_price), str(pnl), reason)
        return {"success": True}

    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/csv", methods=["GET"])
def send_csv_to_telegram():
    if request.args.get("key") != webhook_password:
        return {"error": "Unauthorized"}, 401
    try:
        url = f"https://api.telegram.org/bot{telegram_token}/sendDocument"
        with open(CSV_LOG_PATH, "rb") as file:
            files = {"document": file}
            data = {
                "chat_id": telegram_chat_id,
                "caption": "📊 Trades CSV лог файл"
            }
            response = requests.post(url, data=data, files=files)
        return {
            "status": "success",
            "telegram_response": response.json()
        }
    except Exception as e:
        error_text = f"❌ Не вдалося надіслати CSV у Telegram: {e}"
        print(error_text)
        return {"error": error_text}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
