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

# 5. Локально нужна БД (SQLite для разработки или PostgreSQL)
# Для локальной разработки — SQLite создаётся автоматически

# 6. Запусти бота
python -m bot.main
```

## 🌐 Деплой на Railway (24/7)

### 1. Подготовка
- Репо уже залит на GitHub (https://github.com/deva1056/oikos)
- `Procfile` готов, требует только переменных окружения

### 2. Создай Railway проект
1. Перейди на [railway.app](https://railway.app)
2. Sign up / Log in
3. Нажми **"New Project"**
4. Выбери **"Deploy from GitHub"**
5. Авторизуй GitHub и выбери репо `oikos`

### 3. Добавь PostgreSQL (для сохранения данных)
1. В своём Railway проекте нажми **"+ New"**
2. Выбери **"Database"** → **"PostgreSQL"**
3. Railway автоматически создаст БД и переменную `DATABASE_URL`

**⚠️ Важно:** Без PostgreSQL данные теряются при рестарте! SQLite на Railway не сохраняется.

### 4. Настрой переменные окружения
В Railway проекте перейди в **"Variables"** и добавь:

| Переменная | Значение | Источник |
|----------|----------|----------|
| `TELEGRAM_TOKEN` | `8316437082:AAH...` | BotFather (@BotFather → /token) |
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` | console.anthropic.com → API Keys |
| `ALLOWED_IDS` | `128121642,262349411` | Свои Telegram ID (@userinfobot) |
| `DATABASE_URL` | Создаётся автоматически | Railway PostgreSQL |

### 5. Деплой
Railway автоматически деплоит при push на GitHub. Или нажми **"Deploy"** в UI.

### 6. Проверка
- Посмотри логи в Railway: откройся сервис → **"Logs"**
- Если `✅ Робо запущен` — бот работает 24/7
- Напиши боту в Telegram — должен ответить
- Данные сохраняются в PostgreSQL ✅

## 📁 Структура

```
oikos/
├── bot/              # Telegram-слой (хендлеры)
│   ├── handlers/     # /start, /notes, commands, messages
│   └── main.py       # Запуск бота
├── core/             # Бизнес-логика (переиспользуется в MCP)
│   ├── db.py         # PostgreSQL инициализация
│   ├── memory.py     # CRUD операции с заметками
│   ├── ai.py         # Claude интеграция
│   └── auth.py       # Проверка доступа
├── data/             # Данные (локально, на Railway не используется)
├── Procfile          # Инструкции для Railway
├── requirements.txt  # Зависимости
├── .env.example      # Пример переменных
└── README.md         # Этот файл
```

## 📚 Документация

- **[PRODUCT.md](PRODUCT.md)** — для пользователей (жена)
- **[DEVELOPMENT.md](DEVELOPMENT.md)** — для разработчиков
- **[BUGS.md](BUGS.md)** — известные баги и TODO

## 🔐 Безопасность & Приватность

### 3-уровневая система видимости
- 🔒 **Приватная** — видит только автор
- 👥 **Интерпретация** — все видят суть, но не детали
- 🌐 **Публичная** — все видят полный текст

### Claude и приватность
- Claude **видит только публичные заметки** при ответах на вопросы
- Claude **видит приватный текст только** при генерации интерпретации
- Приватные данные **никогда не попадают в логи**

## 🛠️ Стек

- **Язык:** Python 3.9+
- **Telegram:** `python-telegram-bot` 22.5+
- **AI:** Anthropic Claude API
- **БД:** PostgreSQL (production), SQLite (development)
- **Хостинг:** Railway.app

## 📋 Использование

**В Telegram напиши боту:**

```
Заметка: "Завтра врач в 10 утра"
→ Бот предложит выбрать видимость (приватная/интерпретация/публичная)

Вопрос: "Что запланировано завтра?"
→ Бот ответит на основе публичных заметок семьи
```

**Команды:**
- `/start` — регистрация в семье
- `/notes` — твои заметки (с кнопками смены видимости)
- `/members` — члены семьи
- `/clear` — удалить все свои заметки
- `/help` — справка

## 🚀 Будущие версии

- **v2.1:** Редактирование видимости заметок, фильтры, поиск
- **v3.0:** MCP-сервер (переиспользует `core/`), веб-интерфейс
- **v4.0:** Интеграция с Google Calendar, напоминания (cron)

## 🐛 Известные баги

Смотри [BUGS.md](BUGS.md) для полного списка.

---

**Автор:** Andrey Dmitriev  
**Лицензия:** MIT  
**Статус:** Production Ready ✅
