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

def add_note(user_id, author_name: str, text: str, tags: list) -> dict:
    """Сохранить заметку. `text` — финальная, согласованная через диалог версия.

    Сырого/приватного поля нет by design: в БД попадает только то, что
    автор утвердил для семьи.
    """
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO notes (author_id, author_name, text, tags)
            VALUES (%s, %s, %s, %s)
            RETURNING *
            """,
            (str(user_id), author_name, text, json.dumps(tags)),
        )
        return dict(cur.fetchone())


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


def add_tag_to_note(note_id: int, tag: str) -> list:
    """Добавить тег к заметке (если ещё нет). Возвращает новый список тегов или None."""
    note = get_note(note_id)
    if not note:
        return None
    tags = _parse_tags(note["tags"])
    if tag not in tags:
        tags.append(tag)
        with db_cursor() as cur:
            cur.execute(
                "UPDATE notes SET tags = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (json.dumps(tags), note_id),
            )
    return tags
