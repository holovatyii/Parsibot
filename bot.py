import os
import json
import time
import requests
from flask import Flask, request
from pybit.unified_trading import HTTP

# === Config from environment ===
api_key = os.environ["api_key"]
api_secret = os.environ["api_secret"]
default_symbol = os.environ.get("symbol", "BTCUSDT")
default_base_qty = float(os.environ.get("base_qty", 0.01))
webhook_password = os.environ["webhook_password"]
telegram_token = os.environ["telegram_token"]
telegram_chat_id = os.environ["telegram_chat_id"]

# === Flask app ===
app = Flask(__name__)

# === Bybit session ===
client = HTTP(api_key=api_key, api_secret=api_secret, testnet=True)

# === Telegram sender ===
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {
        "chat_id": telegram_chat_id,
        "text": message
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# === Webhook endpoint ===
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return {"code": 400, "message": "No JSON payload received"}, 400

    if data.get("password") != webhook_password:
        return {"code": 403, "message": "Unauthorized"}, 403

    symbol = data.get("symbol", default_symbol)
    qty = float(data.get("qty", default_base_qty))
    side = data.get("side", "Buy").capitalize()
    tp = data.get("tp")
    sl = data.get("sl")

    try:
        # === Відкриваємо Market позицію ===
        market_order = client.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            position_idx=1
        )

        msg = f"✅ Ордер відкрито: {side} {symbol} x{qty}\n"

        # === Take Profit як окремий ордер ===
        if tp:
            client.place_order(
                category="linear",
                symbol=symbol,
                side="Sell" if side == "Buy" else "Buy",
                order_type="TakeProfitMarket",
                qty=qty,
                trigger_price=float(tp),
                trigger_by="LastPrice",
                reduce_only=True,
                position_idx=1
            )
            msg += f"🎯 TP: {tp}\n"

        # === Stop Loss як окремий ордер ===
        if sl:
            client.place_order(
                category="linear",
                symbol=symbol,
                side="Sell" if side == "Buy" else "Buy",
                order_type="StopLossMarket",
                qty=qty,
                trigger_price=float(sl),
                trigger_by="LastPrice",
                reduce_only=True,
                position_idx=1
            )
            msg += f"🛑 SL: {sl}\n"

        msg += f"📬 Відповідь: {market_order}"
        print(msg)
        send_telegram_message(msg)

        return {"code": 200, "message": "Order and TP/SL placed"}

    except Exception as e:
        error_msg = f"🔥 Error: {e}"
        print(error_msg)
        send_telegram_message(error_msg)
        return {"code": 500, "message": str(e)}, 500

# === Run locally for testing ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)



