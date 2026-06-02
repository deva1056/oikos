# Робо — Семейный AI-ассистент

Telegram-бот для семейной памяти с AI-помощником на базе Claude.

## 🚀 Быстрый старт локально

```bash
# 1. Клонируй репо
git clone https://github.com/deva1056/oikos.git
cd oikos

# 2. Создай виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate  # на Windows: .venv\Scripts\activate

# 3. Установи зависимости
pip install -r requirements.txt

# 4. Создай .env (скопируй .env.example)
cp .env.example .env
# Заполни TELEGRAM_TOKEN и ANTHROPIC_API_KEY

# 5. Запусти бота
python -m bot.main
```

## 🌐 Деплой на Railway

### 1. Подготовка
- Репо уже залит на GitHub (https://github.com/deva1056/oikos)
- `Procfile` и `requirements.txt` готовы

### 2. Создай Railway проект
1. Перейди на [railway.app](https://railway.app)
2. Sign up / Log in
3. Нажми "New Project"
4. Выбери "Deploy from GitHub"
5. Авторизуй GitHub и выбери `oikos` репо

### 3. Настрой переменные окружения
Railway автоматически загрузит переменные из `Procfile`.

Добавь в Railway переменные:
- `TELEGRAM_TOKEN` — токен от BotFather
- `ANTHROPIC_API_KEY` — ключ от Anthropic
- `ALLOWED_IDS` — ID пользователей (через запятую)
- `DB_PATH` — можешь оставить `data/oikos.db`

### 4. Деплой
Railway автоматически деплоит при push на GitHub. Или нажми "Deploy" в UI.

### 5. Проверка
- Посмотри логи в Railway: "Logs"
- Если ошибок нет — бот работает 24/7 ✅

## 📁 Структура

```
oikos/
├── bot/              # Telegram-слой (хендлеры)
├── core/             # Бизнес-логика (БД, AI, приватность)
├── data/             # Данные (БД создаётся автоматически)
├── Procfile          # Инструкции для Railway
├── requirements.txt  # Зависимости
└── .env.example      # Пример переменных
```

## 📚 Документация

- **[PRODUCT.md](PRODUCT.md)** — для пользователей
- **[DEVELOPMENT.md](DEVELOPMENT.md)** — для разработчиков

## 🔐 Безопасность

- Приватные заметки видит только автор
- Claude видит только публичные данные
- `.env` никогда не коммитится (в `.gitignore`)

## 📝 Использование

**В Telegram напиши боту:**
- Заметку: "Завтра врач в 10" → бот попросит выбрать видимость
- Вопрос: "Что запланировано?" → бот ответит на основе памяти

**Команды:**
- `/start` — регистрация
- `/notes` — твои заметки
- `/members` — члены семьи
- `/clear` — удалить все заметки
- `/help` — справка
