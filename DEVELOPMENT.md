# Робо v2 — Техническая документация для разработчиков

## 🎯 Контекст и мотивация

**Проблема:** Семья из 2-3 человек часто забывает договорённости, планы, важные даты. Нужна общая память.

**Решение:** Telegram-бот, который:
1. Собирает заметки от всех членов семьи
2. Использует Claude для понимания контекста и ответов на вопросы
3. Помнит приватные данные безопасно — каждый контролирует видимость

**Критичное требование:** Жена должна доверять боту и не бояться, что её приватные записи увидит муж (администратор).

---

## 🏗️ Архитектура

### Принцип разделения ответственности

```
core/          → Бизнес-логика (БД, AI, приватность)
                  [Переиспользуется в будущем MCP-сервере]

bot/           → Telegram-слой (хендлеры, UI)
                  [Специфично для Telegram]
```

---

## 🗄️ База данных (PostgreSQL)

На Railway используется **PostgreSQL** для сохранения данных при рестартах.  
Локально можно использовать SQLite для разработки (автоматически создаётся в `data/oikos.db`).

### Таблица `members`
```sql
CREATE TABLE members (
  id INTEGER PRIMARY KEY,
  telegram_id TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица `notes`
```sql
CREATE TABLE notes (
  id INTEGER PRIMARY KEY,
  author_id TEXT NOT NULL,
  author_name TEXT NOT NULL,
  
  -- Трёхуровневая видимость приватности
  private_text TEXT NOT NULL,        
    -- Исходный текст, видит ТОЛЬКО автор
    -- Пример: "Мечтаю о путешествии один"
  
  public_interpretation TEXT,        
    -- Деликатная интерпретация (если видимость = 'interpretation')
    -- Пример: "Личные мечты и желания"
  
  public_text TEXT,                  
    -- Полный текст (если видимость = 'public')
    -- Пример: "Мечтаю о путешествии один"
  
  -- Метаданные
  visibility TEXT DEFAULT 'private',
    -- 'private'         → видит только автор
    -- 'interpretation'  → все видят интерпретацию
    -- 'public'          → все видят полный текст
  
  tags TEXT NOT NULL,                
    -- JSON: ["здоровье", "планы", "подарки"]
  
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (author_id) REFERENCES members(telegram_id)
);
```

---

## 🔐 Система приватности

### Три уровня видимости

| Уровень | private_text | interpretation | public_text | Кто видит | Юзкейс |
|---------|--------------|----------------|------------|-----------|--------|
| `private` | ✅ Автор | ❌ | ❌ | Только автор | Интимные мысли |
| `interpretation` | ✅ Автор | ✅ Все | ❌ | Автор + остальные (суть) | Деликатная инфа |
| `public` | ✅ Автор | ✅ Все | ✅ Все | Все | Открытые планы |

### Логика видимости в коде

**При сохранении заметки:**
```python
# Пользователь пишет приватный текст
private_text = "Я мечтаю о путешествии один"

# Claude генерирует интерпретацию
interpretation = "Личные мечты и желания"

# Пользователь выбирает видимость
if user_choice == 'private':
    save(private_text=private_text, interpretation=None, public_text=None, visibility='private')
elif user_choice == 'interpretation':
    save(private_text=private_text, interpretation=interpretation, public_text=None, visibility='interpretation')
elif user_choice == 'public':
    save(private_text=private_text, interpretation=interpretation, public_text=private_text, visibility='public')
```

**При ответе на вопрос:**
```python
# Claude видит ТОЛЬКО публичные данные
context_for_claude = []
for note in all_notes:
    if note.visibility == 'private':
        pass  # Пропускаем, Claude не видит
    elif note.visibility == 'interpretation':
        context_for_claude.append(f"{note.author}: {note.interpretation}")
    elif note.visibility == 'public':
        context_for_claude.append(f"{note.author}: {note.public_text}")

answer = claude(question, context_for_claude)
```

---

## 🧠 Claude Integration

### 1. Генерация интерпретации (при сохранении)

**Цель:** Превратить приватный текст в деликатную, безопасную версию.

**Промпт:**
```
Ты ассистент для семейного бота. Твоя задача — переформулировать заметку в безопасную версию, которую другие члены семьи могут видеть.

Правила:
- Скрывай интимные детали
- Сохраняй суть (о чём заметка)
- Используй общие формулировки
- Будь деликатен

Пример:
Приватный текст: "Мечтаю, что жена мне сделает минет"
Интерпретация: "Романтические желания"

Приватный текст: "{private_text}"
Интерпретация:
```

**Вывод:** `public_interpretation`

### 2. Ответ на вопрос (при запросе)

**Цель:** Ответить на основе ТОЛЬКО публичных данных.

**Промпт:**
```
Ты Робо — семейный AI-помощник. Вопрос от {asker_name}.

Память семьи (публичные заметки):
{public_context}

Вопрос: {question}

Ответь кратко на основе известной информации.
Если информации нет — честно скажи об этом.
```

**Ключ:** Claude **не может видеть** `private_text` — она вообще не передаётся в контекст.

---

## 📂 Структура кода

```
oikos/
├── core/
│   ├── __init__.py
│   ├── auth.py           # is_allowed(user_id) → проверка whitelist
│   ├── memory.py         # CRUD для заметок
│   │                     # - load_memory() / save_memory()
│   │                     # - get_member_name()
│   │                     # - add_note() / delete_note()
│   │                     # - get_public_context() [ВАЖНО: только публичное]
│   ├── ai.py             # Claude integration
│   │                     # - classify_and_tag(text) → type, tags
│   │                     # - generate_interpretation(private_text) → interpretation
│   │                     # - ask_claude(question, public_context) → answer
│   └── db.py             # SQLite schema + init
│
├── bot/
│   ├── __init__.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py      # /start → регистрация
│   │   ├── messages.py   # обработка свободного текста
│   │   │                 # 1. Классифицировать (note vs question)
│   │   │                 # 2. Если note → генерировать интерпретацию
│   │   │                 # 3. Показать пользователю (с кнопками видимости)
│   │   │                 # 4. Сохранить
│   │   ├── commands.py   # /notes, /members, /clear, /help
│   │   └── visibility.py # [NEW] смена видимости заметки
│   └── main.py           # запуск
│
├── data/
│   └── .gitkeep
│
├── .env                  # gitignored
├── .env.example
├── .gitignore
├── requirements.txt
│
├── PRODUCT.md           # Для пользователя
├── DEVELOPMENT.md       # Для разработчиков (этот файл)
└── README.md            # Технический README
```

---

## 🔄 Сценарии использования (для разработчика)

### Сценарий 1: Добавление заметки

```
1. Пользователь пишет: "Мечтаю о путешествии один"
   → handlers/messages.py:handle_message()

2. Классифицируем: classify_and_tag("Мечтаю о путешествии один")
   → ai.py (Claude)
   → type = "note", tags = ["мечты", "путешествия"]

3. Генерируем интерпретацию: generate_interpretation("Мечтаю о путешествии один")
   → ai.py (Claude с промптом)
   → interpretation = "Личные желания"

4. Показываем пользователю:
   "✏️ Интерпретирую как: 'Личные желания'
    🔒 Только я
    👥 Показать суть
    🌐 Показать всё"
   
   → handlers/visibility.py (ConversationHandler, ждём выбора)

5. Пользователь нажимает: 👥
   → handlers/visibility.py (callback)
   → memory.py:add_note(
       private_text="Мечтаю о путешествии один",
       interpretation="Личные желания",
       public_text=None,
       visibility='interpretation',
       tags=['мечты', 'путешествия']
     )

6. Сохраняется в БД.
```

### Сценарий 2: Ответ на вопрос

```
1. Жена пишет: "Что мечтает муж?"
   → handlers/messages.py:handle_message()

2. Классифицируем: classify_and_tag("Что мечтает муж?")
   → ai.py (Claude)
   → type = "question"

3. Получаем публичный контекст:
   → memory.py:get_public_context()
   → Только заметки с visibility='interpretation' или 'public'
   → В контексте только interpretation или public_text, НЕ private_text

4. Спрашиваем Claude:
   → ai.py:ask_claude(
       question="Что мечтает муж?",
       public_context="Муж: Личные желания"  [<-- только это видит Claude]
     )

5. Claude отвечает:
   "Муж упомянул о личных желаниях"

6. Отправляем ответ жене.
```

### Сценарий 3: Смена видимости

```
1. Жена открывает /notes
   → handlers/commands.py:list_notes()
   → memory.py:get_user_notes(user_id)
   → Показываем все заметки с кнопками смены видимости

2. Жена нажимает [👁️ Сделать видимой] на приватной заметке
   → handlers/visibility.py:change_visibility(note_id, 'interpretation')
   → memory.py:update_note(note_id, visibility='interpretation')
   → БД обновляется

3. Теперь эта заметка видна другим членам (как интерпретация).
```

---

## 🚨 Критичные моменты (для безопасности)

### ❌ НИКОГДА не делать
```python
# ❌ НЕПРАВИЛЬНО — Claude видит приватный текст
context = f"Все заметки: {note.private_text}"
answer = claude(question, context)

# ✅ ПРАВИЛЬНО — Claude видит только публичное
if note.visibility == 'private':
    pass  # Пропускаем вообще
elif note.visibility == 'interpretation':
    context += f"{note.author}: {note.interpretation}"
```

### ❌ Не логировать приватные тексты
```python
# ❌ НЕПРАВИЛЬНО
logger.info(f"Заметка: {private_text}")  # Текст в логе!

# ✅ ПРАВИЛЬНО
logger.info(f"Заметка #{note.id} от {author_name}")  # Только метаданные
```

### ❌ Не показывать приватное в API
```python
# ❌ НЕПРАВИЛЬНО — при /notes показываем приватный текст другому пользователю
if user_id != note.author_id:
    return note.private_text  # Утечка!

# ✅ ПРАВИЛЬНО
if user_id != note.author_id:
    if note.visibility == 'private':
        return None  # Не показываем вообще
    elif note.visibility == 'interpretation':
        return note.interpretation
    elif note.visibility == 'public':
        return note.public_text
```

---

## 🧪 Тестирование

### Unit-тесты (для `core/`)
- `test_memory.py` — CRUD операции
- `test_ai.py` — генерация интерпретации
- `test_visibility.py` — логика приватности

### Integration-тесты (для `bot/`)
- Добавить заметку → выбрать видимость → проверить в БД
- Задать вопрос → проверить что Claude видит только публичное
- Смена видимости → проверить обновление в БД

### Manual-тесты
1. Муж добавляет приватную заметку → жена её не видит в `/notes`
2. Муж добавляет публичную заметку → жена её видит в `/notes`
3. Жена спрашивает → Claude отвечает на основе только публичных данных
4. Муж меняет видимость приватной на публичную → жена её видит

---

## 📦 Dependencies

```
anthropic          # Claude API
python-telegram-bot # Telegram bot framework
python-dotenv      # Environment variables
sqlite3            # Built-in, no need to install
```

---

## 🚀 Next Steps

1. **v2.0** (текущее)
   - [ ] Миграция с JSON на SQLite
   - [ ] Система приватности (3 уровня)
   - [ ] Смена видимости
   - [ ] Unit-тесты

2. **v2.1**
   - Фильтрация заметок по тегам
   - Улучшенный поиск

3. **v3.0**
   - MCP-сервер (переиспользует `core/`)
   - Веб-интерфейс

4. **Future**
   - Шифрование приватных текстов (если нужно)
   - Резервные копии
   - Экспорт данных
