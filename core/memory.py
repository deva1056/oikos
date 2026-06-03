import json
import re

from core.db import db_cursor
from core.timeutils import format_dt

# Сколько последних заметок отдавать ассистенту в контекст (защита от роста промпта)
CONTEXT_NOTE_LIMIT = 100


def sanitize_name(raw: str) -> str:
    """Имя из пользовательского ввода: схлопнуть пробелы/переводы строк,
    выкинуть непечатаемое, ограничить длину."""
    name = re.sub(r"\s+", " ", (raw or "").strip())
    name = "".join(ch for ch in name if ch.isprintable())
    return name[:64]


def tag_value(tag: str) -> str:
    """Значение тега без namespace: 'topic:покупки' и 'покупки' → 'покупки'."""
    return (tag or "").split(":")[-1]


def normalize_tag(tag: str) -> str:
    """Механическая нормализация тега (регистр, ё, пробелы, мусор).

    Namespace-двоеточие сохраняется (topic:врач). Семантическая консолидация
    синонимов — задача LLM-тэггера (через список известных тегов), не этой функции.
    """
    tag = (tag or "").strip().lower().lstrip("#")
    tag = tag.replace("ё", "е")
    tag = re.sub(r"\s+", "_", tag)
    tag = re.sub(r"[^a-zа-я0-9_:-]", "", tag)
    return tag[:32]


# ---------- members ----------

def get_member_name(user_id) -> str:
    with db_cursor() as cur:
        cur.execute("SELECT name FROM members WHERE telegram_id = %s", (str(user_id),))
        row = cur.fetchone()
    return row["name"] if row else None


def register_member(user_id, name: str):
    name = sanitize_name(name)
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO members (telegram_id, name) VALUES (%s, %s) "
            "ON CONFLICT (telegram_id) DO UPDATE SET name = %s",
            (str(user_id), name, name),
        )


def get_member_timezone(user_id) -> str:
    with db_cursor() as cur:
        cur.execute("SELECT timezone FROM members WHERE telegram_id = %s", (str(user_id),))
        row = cur.fetchone()
    return row["timezone"] if row else None


def set_member_timezone(user_id, tz: str):
    with db_cursor() as cur:
        cur.execute(
            "UPDATE members SET timezone = %s WHERE telegram_id = %s",
            (tz, str(user_id)),
        )


def get_all_members() -> list:
    with db_cursor() as cur:
        cur.execute("SELECT name FROM members ORDER BY name")
        return [row["name"] for row in cur.fetchall()]


# ---------- notes ----------

def add_note(user_id, author_name: str, text: str, tags: list,
             event_date=None, event_time=None, note_type="note", status=None) -> dict:
    """Сохранить заметку. `text` — финальная, согласованная через диалог версия.

    note_type='wish' + status='open' — для желаний (см. /wishes).
    Сырого/приватного поля нет by design: в БД попадает только то, что автор утвердил.
    """
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO notes (author_id, author_name, text, tags, event_date, event_time, note_type, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (str(user_id), author_name, text, json.dumps(tags), event_date, event_time, note_type, status),
        )
        return dict(cur.fetchone())


def update_note(note_id: int, author_id, text: str, tags: list,
                event_date=None, event_time=None, note_type="note") -> int:
    """Обновить свою заметку (текст + метаданные). status не трогаем — им
    управляют /done /cancelwish. Возвращает число изменённых строк."""
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE notes
            SET text = %s, tags = %s, event_date = %s, event_time = %s, note_type = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND author_id = %s
            """,
            (text, json.dumps(tags), event_date, event_time, note_type, note_id, str(author_id)),
        )
        return cur.rowcount


def get_wishes(status: str = "open", person: str = None) -> list:
    """Желания (note_type='wish') с данным статусом, опц. по человеку (person-тег)."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, author_name, text, tags, status, fulfilled_by, fulfilled_at, created_at
            FROM notes WHERE note_type = 'wish' AND status = %s
            ORDER BY created_at DESC
            """,
            (status,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    if person:
        pv = tag_value(normalize_tag(person))
        rows = [r for r in rows if pv in {tag_value(t) for t in _parse_tags(r["tags"])}]
    return rows


def set_wish_status(note_id: int, status: str, by_name: str = None) -> int:
    """Сменить статус желания (open/fulfilled/cancelled). fulfilled_at ставим при fulfilled."""
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE notes
            SET status = %s,
                fulfilled_at = CASE WHEN %s = 'fulfilled' THEN CURRENT_TIMESTAMP ELSE NULL END,
                fulfilled_by = CASE WHEN %s = 'fulfilled' THEN %s ELSE NULL END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND note_type = 'wish'
            """,
            (status, status, status, by_name, note_id),
        )
        return cur.rowcount


def set_note_tags(note_id: int, tags: list):
    """Заменить теги заметки целиком (для /retag)."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE notes SET tags = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (json.dumps(tags), note_id),
        )


def get_note(note_id: int) -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM notes WHERE id = %s", (note_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_user_notes(user_id):
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM notes WHERE author_id = %s ORDER BY created_at DESC",
            (str(user_id),),
        )
        return [dict(row) for row in cur.fetchall()]


def delete_note(note_id: int, author_id):
    """Удалять только свою заметку: id + author_id, чтобы нельзя было снести чужую."""
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM notes WHERE id = %s AND author_id = %s",
            (note_id, str(author_id)),
        )


def delete_user_notes(user_id):
    with db_cursor() as cur:
        cur.execute("DELETE FROM notes WHERE author_id = %s", (str(user_id),))


def get_public_context(viewer_tz: str = None) -> str:
    """Все заметки семьи для ответов ассистента.

    Уровней приватности нет — каждая сохранённая заметка видна семье.
    Метки времени рендерятся в таймзоне спрашивающего.
    """
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT author_name, text, created_at FROM (
                SELECT author_name, text, created_at FROM notes
                ORDER BY created_at DESC LIMIT %s
            ) recent
            ORDER BY created_at ASC
            """,
            (CONTEXT_NOTE_LIMIT,),
        )
        notes = cur.fetchall()

    if not notes:
        return "Заметок пока нет."

    return "\n".join(
        f"[{format_dt(n['created_at'], viewer_tz)}] {n['author_name']}: {n['text']}"
        for n in notes
    )


# ---------- tags ----------

def _parse_tags(raw) -> list:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return []


def get_all_tags() -> list:
    """Список (тег, количество) по всем заметкам семьи, по убыванию частоты."""
    with db_cursor() as cur:
        cur.execute("SELECT tags FROM notes")
        rows = cur.fetchall()

    counter = {}
    for row in rows:
        for tag in _parse_tags(row["tags"]):
            counter[tag] = counter.get(tag, 0) + 1
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


def get_notes_by_tag(tag: str) -> list:
    """Заметки семьи с данным тегом (фильтрация в Python — объём небольшой)."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, author_name, text, tags, created_at FROM notes ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows if tag in _parse_tags(r["tags"])]


def add_tag_to_note(note_id: int, new_tags) -> list:
    """Добавить один или несколько тегов к заметке (с нормализацией, без дублей)."""
    if isinstance(new_tags, str):
        new_tags = [new_tags]
    note = get_note(note_id)
    if not note:
        return None
    tags = _parse_tags(note["tags"])
    changed = False
    for raw in new_tags:
        t = normalize_tag(raw)
        if t and t not in tags:
            tags.append(t)
            changed = True
    if changed:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE notes SET tags = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (json.dumps(tags), note_id),
            )
    return tags


def remove_tag_from_note(note_id: int, tag: str) -> list:
    """Убрать тег из заметки. Возвращает новый список тегов или None, если заметки нет."""
    note = get_note(note_id)
    if not note:
        return None
    target = normalize_tag(tag)
    tags = [t for t in _parse_tags(note["tags"]) if t != target]
    with db_cursor() as cur:
        cur.execute(
            "UPDATE notes SET tags = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (json.dumps(tags), note_id),
        )
    return tags


_DATE_FIELDS = {"event_date", "created_at"}


def query_notes(date_field: str = None, lo=None, hi=None, limit: int = CONTEXT_NOTE_LIMIT) -> list:
    """Заметки с опциональным фильтром по дате. date_field ∈ {event_date, created_at}.

    Тег/people-фильтрация делается выше (в retrieval) по Python — объём небольшой.
    """
    with db_cursor() as cur:
        if date_field in _DATE_FIELDS and lo is not None and hi is not None:
            cur.execute(
                f"""
                SELECT id, author_name, text, tags, event_date, event_time,
                       note_type, status, created_at
                FROM notes
                WHERE {date_field} BETWEEN %s AND %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (lo, hi, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, author_name, text, tags, event_date, event_time,
                       note_type, status, created_at
                FROM notes
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
        return [dict(r) for r in cur.fetchall()]
