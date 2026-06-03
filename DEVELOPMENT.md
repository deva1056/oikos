# Робо — техническая документация

## Идея

Общая память семьи в Telegram. Две ключевые механики:

1. **Заметка рождается в диалоге.** Пользователь пишет сырьё, LLM формулирует
   черновик, пользователь правит словами, по `/save` сохраняется финальный текст.
   Сырьё нигде не хранится и не логируется.
2. **Ответ через поиск, а не дамп.** Вопрос превращается в профиль поиска
   (теги/люди/автор/период/тип), профиль режет заметки на уровне SQL+Python, и
   только релевантный срез уходит в LLM.

### Модель приватности (важно)
Уровней видимости нет. В БД лежит только согласованный автором текст → админ
видит ровно то, что предназначено семье. Это сознательный отказ от «приватных
полей»: надёжно скрыть данные от админа в серверном Telegram-боте нельзя (сервер
всё равно обрабатывает входящее), поэтому секрет просто **не сохраняется**.

---

## Архитектура

```
core/   — бизнес-логика, без Telegram (потенциально переиспользуема в MCP)
bot/    — Telegram-слой (хендлеры, диалоги, сессии)
scripts/— разовое обслуживание БД
```

LLM-вызовы синхронные (SDK), но в хендлерах оборачиваются в `asyncio.to_thread`,
чтобы не блокировать event loop. Доступ к БД — через пул соединений (`db_cursor`).

---

## Данные (PostgreSQL)

```sql
members(
  id SERIAL PK,
  telegram_id TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  timezone TEXT,                 -- IANA, определяется по геолокации
  created_at TIMESTAMP
)

notes(
  id SERIAL PK,
  author_id TEXT NOT NULL REFERENCES members(telegram_id),
  author_name TEXT NOT NULL,

  text TEXT NOT NULL,            -- финальная согласованная версия (единственное поле текста)
  tags TEXT NOT NULL,            -- JSON: ["topic:врач","person:варя","type:событие"]

  event_date DATE,               -- машинная дата события (для «что завтра»)
  event_time TIME,

  note_type TEXT DEFAULT 'note', -- 'note' | 'wish'
  status TEXT,                   -- для желаний: 'open'|'fulfilled'|'cancelled'
  fulfilled_at TIMESTAMP,
  fulfilled_by TEXT,

  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```

Схема создаётся/мигрируется в `init_db()` через `CREATE TABLE IF NOT EXISTS` +
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — новые колонки приезжают на старте,
отдельные миграции не нужны (кроме разовой `migrate_to_single_field.py`).

---

## Жизненный цикл заметки (`bot/handlers/draft.py`)

`ConversationHandler`, состояние `DRAFTING`. Черновик и история реплик живут в
`context.user_data["draft"]` (память процесса, не БД).

1. **Вход.** `looks_like_question()` (эвристика, без LLM) делит вопрос/заметку.
   Override: `/note`, `/ask`. Ошибка маршрутизации чинится кнопкой (variant A).
2. **Черновик.** `refine_draft(history)` собирает текст; правки — обычными
   сообщениями (мультитёрн), кнопки `💾/❌/❓`.
3. **Сохранение.** `extract_note_metadata(text, tz, known_tags, author)` →
   typed-теги + `event_date/time` + `note_type`. `add_note(...)` (или
   `update_note(...)` при `/edit_<id>`).

Правило person-тега: заметка от первого лица → `person:<автор>` (имя автора
передаётся в экстрактор).

---

## Поиск контекста (`core/retrieval.py`)

```
вопрос → extract_search_profile(question, tz, known_tags, history)
       → {tags_any, tags_all, people, authors, note_type, period, date_*}
       → period → Python считает границы (timeutils.period_bounds), даты НЕ от LLM
       → query_notes(date_field, lo, hi)        # SQL: дата — жёсткий фильтр
       → фильтр по автору (жёсткий) и note_type=wish (жёсткий)
       → теги/люди — МЯГКИЙ фильтр (по значению, без namespace); пусто → откат
       → срез (до 30) → ask_claude(question, срез, asker, tz, history)
```

Принципы:
- **Дата и автор — жёсткие** (структурные, надёжные). **Теги/люди — мягкие**:
  сужают при совпадении, но не «голодят» модель при разрежённых тегах.
- Сравнение тегов **по значению** (`tag_value`): `topic:планы` ≡ `планы` —
  чтобы матчить и старые плоские, и новые namespaced.
- Профайлер устойчив: при сбое LLM откатывается на последние заметки.

---

## Память сессии (`bot/handlers/session.py`)

`chat_turns` (последние ~3 обмена) и `last_active` в `user_data`. `TypeHandler`
в group −1 на каждый апдейт: активность продлевает сессию (sliding TTL), простой
> `SESSION_TTL_MIN` (дефолт 15) чистит и историю, и незавершённый черновик.
История кормится и профайлеру, и `ask_claude` → работают уточнения.

---

## Теги

Typed namespaces: `topic:` (тема), `person:` (человек/питомец), `type:`
(событие/покупка/идея/факт/желание). `normalize_tag()` — механическая нормализация
(регистр, `ё→е`, пробелы→`_`, мусор, namespace сохраняется). Семантическую
консолидацию синонимов делает LLM, получая список уже существующих тегов
(динамический словарь) — без захардкоженных алиасов.

---

## Желания

`note_type='wish'` ставит LLM (`extract_note_metadata`), не ключевые слова.
Новое желание → `status='open'`. Команды: `/wishes [имя]`, `/fulfilled [имя]`,
`/done <id>`, `/cancelwish <id>` (отметить может любой участник, пишем
`fulfilled_by`). Естественные вопросы «что хочет X» → профайлер ставит
`note_type=wish`, retrieval отдаёт только желания. Без рейтингов по людям —
осознанно (чтобы не превращать в «бухгалтерию обид»).

---

## LLM-слой (`core/ai.py`)

Провайдер выбирается `LLM_PROVIDER` (`openai`|`anthropic`); клиенты ленивые,
модели — из env. Функции:
- `_complete(system, user, ...)` / `_chat(system, messages, ...)` — единичный/мультитёрн.
- `refine_draft(messages)` — формулировка черновика.
- `extract_note_metadata(text, tz, known_tags, author)` — теги + дата + note_type.
- `extract_search_profile(question, tz, known_tags, history)` — профиль поиска.
- `ask_claude(question, context, asker, tz, history)` — ответ (имя историческое).

**Готча:** экстракторы НЕ используют `response_format=json_object` (часть моделей
его не поддерживает → 400). JSON парсится из обычного ответа (`_parse_json`,
снимает ```-обёртки). Ошибки LLM в боте глотает `_run_llm` (логируется тип, не
текст пользователя) → дружелюбное сообщение вместо краша.

---

## Таймзоны (`core/timeutils.py`)

Таймзона на участника, определяется по геолокации (`timezonefinder`) или
`/timezone <IANA>`. `period_bounds(period, tz)` детерминированно считает границы
(`today/tomorrow/this_week/...`). `event_date` хранится как локальная дата;
`created_at` (UTC) для дневных срезов конвертируется через `day_range_utc`.

---

## Конвенции / на что не наступить

- **Не логировать текст заметок/сообщений** — только id/метаданные.
- **Markdown** в исходящих с динамическим текстом — через `safe_reply`
  (фолбэк на plain при битой разметке).
- **Удаление/правка чужого** — `delete_note`/`update_note` фильтруют по `author_id`.
- **`event_date` ретроактивно не пересчитывать** (относительные даты были
  привязаны к моменту написания) — `retag_notes.py` трогает только теги.
- **Имя пользователя** санитизируется (`sanitize_name`).

---

## Скрипты (`scripts/`, запуск с `DATABASE_URL`)

| Скрипт | Назначение |
|---|---|
| `migrate_to_single_field.py` | разовая миграция со старой 3-уровневой схемы |
| `normalize_existing_tags.py` | нормализация тегов (`--dry`) |
| `retag_notes.py [--all]` | переосмыслить теги через LLM (`--dry`) |
| `seed_test_data.py` | тестовый набор с тегом `debug` |
| `delete_by_tag.py <tag>` | удалить всё по тегу (`--dry`) |
| `delete_notes.py <id...>` | удалить заметки по id (`--dry`) |

---

## Roadmap

- Авто-связывание исполнения желаний («купили ролики» → закрыть желание #N) +
  таблица связей `note_links`.
- Профили «живых существ» (beings): имя/пол/др/атрибуты, авто-наполнение из заметок.
- Перенос `tags` в `jsonb` + GIN-индекс (когда вырастет объём).
- Напоминания по `event_date` (cron).
