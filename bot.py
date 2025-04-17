import os
import requests
from flask import Flask

app = Flask(__name__)

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_KEY = os.getenv("BINANCE_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, json=payload)

@app.route("/")
def check_env():
    try:
        send_telegram("🌍 ENV TEST\n" +
                      f"BOT_TOKEN: {TOKEN[:10]}...\n" +
                      f"CHAT_ID: {CHAT_ID}\n" +
                      f"BINANCE_KEY: {BINANCE_KEY[:8]}...\n" +
                      f"BINANCE_SECRET: {BINANCE_SECRET[:8]}...")
        return "Environment sent to Telegram."
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
