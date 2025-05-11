🧠 Bybit Trading Bot (Flask + Webhook + Telegram + CSV)
✅ Можливості
Приймає сигнали з TradingView Webhook

Відкриває ордери на Bybit (Testnet або Mainnet)

Автоматично виставляє TP, SL або трейлінг-стоп

Надсилає логи в Telegram

Логує угоди в trades.csv для подальшої оптимізації

📁 Структура проекту
bash
Copy
Edit
bybit_trading_bot/
├── bot.py               # Основний Flask сервер
├── requirements.txt     # Залежності
├── trades.csv           # CSV лог всіх угод (створюється автоматично)
├── .env                 # Змінні оточення
└── README.md            # Цей файл
⚙️ Налаштування
Встанови залежності:

bash
Copy
Edit
pip install -r requirements.txt
Створи .env файл у корені:

env
Copy
Edit
api_key=YOUR_BYBIT_API_KEY
api_secret=YOUR_BYBIT_SECRET
symbol=BTCUSDT
base_qty=0.01
webhook_password=12345
telegram_token=YOUR_TELEGRAM_BOT_TOKEN
telegram_chat_id=YOUR_CHAT_ID
env=test
debug_responses=True
🚀 Запуск
bash
Copy
Edit
python bot.py
Сервер буде доступний на:

arduino
Copy
Edit
http://0.0.0.0:5000/webhook
📤 Webhook-приклад для TradingView
json
Copy
Edit
{
  "password": "12345",
  "side": "Buy",
  "symbol": "BTCUSDT",
  "qty": 0.01,
  "tp": 103000,
  "sl": 98000,
  "trailing": true,
  "callback": 0.75
}
🧪 Тестування через curl
bash
Copy
Edit
curl -X POST http://127.0.0.1:5000/webhook \\
-H "Content-Type: application/json" \\
-d "{\"password\": \"12345\", \"side\": \"Buy\", \"symbol\": \"BTCUSDT\", \"qty\": 0.01, \"tp\": 103000, \"sl\": 98000, \"trailing\": true, \"callback\": 0.75}"
📊 trades.csv
Після кожної угоди створюється лог-файл trades.csv з колонками:

sql
Copy
Edit
timestamp, symbol, side, qty, entry_price, tp, sl, trailing, order_id, result, pnl
🛡 Безпека
Webhook-захист через password

Ключі приховані через .env

Обмеження на TP/SL діапазон

🧠 Майбутнє
Telegram-команди /status, /csv, /log

AI-оптимізація TP/SL на основі trades.csv

Інтеграція з Google Sheets

Мульти-монетна логіка


