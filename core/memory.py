import json
from psycopg2.extras import RealDictCursor
from core.db import get_connection
from core.timeutils import format_dt


def get_member_name(user_id) -> str:
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT name FROM members WHERE telegram_id = %s", (str(user_id),))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row["name"] if row else None


def register_member(user_id, name: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO members (telegram_id, name) VALUES (%s, %s) ON CONFLICT (telegram_id) DO UPDATE SET name = %s",
        (str(user_id), name, name),
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_member_timezone(user_id) -> str:
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT timezone FROM members WHERE telegram_id = %s", (str(user_id),))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row["timezone"] if row else None


def set_member_timezone(user_id, tz: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE members SET timezone = %s WHERE telegram_id = %s",
        (tz, str(user_id)),
    )
    conn.commit()
    cursor.close()
    conn.close()


def add_note(user_id, author_name: str, text: str, tags: list) -> dict:
    """Сохранить заметку. `text` — финальная, согласованная через диалог версия.

    Сырого/приватного поля нет by design: в БД попадает только то, что
    автор утвердил для семьи.
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    tags_json = json.dumps(tags)
    cursor.execute(
        """
        INSERT INTO notes (author_id, author_name, text, tags)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (str(user_id), author_name, text, tags_json),
    )
    note = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()

    return dict(note)


def get_user_notes(user_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM notes WHERE author_id = %s ORDER BY created_at DESC", (str(user_id),))
    notes = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return notes


def delete_note(note_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = %s", (note_id,))
    conn.commit()
    cursor.close()
    conn.close()


def delete_user_notes(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE author_id = %s", (str(user_id),))
    conn.commit()
    cursor.close()
    conn.close()


def get_public_context(viewer_tz: str = None) -> str:
    """Все заметки семьи для ответов ассистента.

    Уровней приватности больше нет — каждая сохранённая заметка видна семье.
    Метки времени рендерятся в таймзоне спрашивающего, чтобы «сегодня/вчера»
    совпадали с тем, как он переживает день.
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        """
        SELECT author_name, text, created_at
        FROM notes
        ORDER BY created_at ASC
        """,
    )
    notes = cursor.fetchall()
    cursor.close()
    conn.close()

    if not notes:
        return "Заметок пока нет."

    lines = []
    for note in notes:
        ts = format_dt(note["created_at"], viewer_tz)
        lines.append(f"[{ts}] {note['author_name']}: {note['text']}")

    return "\n".join(lines)


def get_all_members() -> list:
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT name FROM members ORDER BY name")
    members = [row["name"] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return members
