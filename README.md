
# Bybit Trading Bot (Flask + Webhook + Telegram)

✅ Бот приймає сигнали з TradingView через webhook  
✅ Відкриває ордери на Bybit (Testnet)  
✅ Відправляє лог у Telegram  
✅ Підтримка Take Profit та Stop Loss (TP/SL)

---

## 📁 Структура проекту

```
bybit_trading_bot/
├── bybit_flask_server.py      # Основний Flask сервер
├── config.json                # Налаштування API, symbol, qty, Telegram тощо
├── requirements.txt           # Залежності
└── README.md                  # Цей файл
```

---

## ⚙️ Налаштування

1. Встанови залежності:

```bash
pip install -r requirements.txt
```

2. Заповни файл `config.json`:

```json
{
  "api_key": "YOUR_BYBIT_API_KEY",
  "api_secret": "YOUR_BYBIT_SECRET",
  "symbol": "SOLUSDT",
  "base_qty": 0.01,
  "webhook_password": "12345",
  "telegram_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID"
}
```

---

## 🚀 Запуск

```bash
python bybit_flask_server.py
```

> Сервер працює на `http://0.0.0.0:5000`

---

## 📤 Приклад Webhook-сигналу з TP/SL

```json
{
  "password": "12345",
  "side": "Buy",
  "symbol": "SOLUSDT",
  "qty": 0.01,
  "tp": 160,
  "sl": 145
}
```

---

## 🧪 Тестування

Для локального тесту можна скористатись `curl`:

```bash
curl -X POST http://127.0.0.1:5000/webhook -H "Content-Type: application/json" -d "{\"password\": \"12345\", \"side\": \"Buy\", \"symbol\": \"SOLUSDT\", \"qty\": 0.01, \"tp\": 160, \"sl\": 145}"
```

---

## 🛡 Функції безпеки

- Захист webhook — `password`
- Всі ключі конфігурації зберігаються в `config.json`
- Підтримка лише `Market` ордерів (на даному етапі)

---

## 🏁 Плани на майбутнє

- [ ] Автоматичне закриття угод (реал SL/TP через позиції)
- [ ] Підтримка трейлінг-стопу
- [ ] Мульти-монетна логіка
