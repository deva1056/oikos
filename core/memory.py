import json
from datetime import datetime

from core.db import get_connection


def get_member_name(user_id) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM members WHERE telegram_id = ?", (str(user_id),))
    row = cursor.fetchone()
    conn.close()
    return row["name"] if row else None


def register_member(user_id, name: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO members (telegram_id, name) VALUES (?, ?)",
        (str(user_id), name),
    )
    conn.commit()
    conn.close()


def add_note(user_id, author_name: str, private_text: str, tags: list, visibility: str = "private", interpretation: str = None, public_text: str = None) -> dict:
    conn = get_connection()
    cursor = conn.cursor()

    tags_json = json.dumps(tags)
    cursor.execute(
        """
        INSERT INTO notes (author_id, author_name, private_text, public_interpretation, public_text, visibility, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(user_id), author_name, private_text, interpretation, public_text, visibility, tags_json),
    )
    conn.commit()

    note_id = cursor.lastrowid
    cursor.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
    note = cursor.fetchone()
    conn.close()

    return dict(note)


def update_note_visibility(note_id: int, visibility: str, interpretation: str = None, public_text: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE notes
        SET visibility = ?, public_interpretation = ?, public_text = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (visibility, interpretation, public_text, note_id),
    )
    conn.commit()
    conn.close()


def get_user_notes(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notes WHERE author_id = ? ORDER BY created_at DESC", (str(user_id),))
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes


def delete_note(note_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()


def delete_user_notes(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE author_id = ?", (str(user_id),))
    conn.commit()
    conn.close()


def get_public_context() -> str:
    """Get only public notes (interpretation + public) for Claude."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT author_name, public_interpretation, public_text, visibility
        FROM notes
        WHERE visibility IN ('interpretation', 'public')
        ORDER BY created_at ASC
        """,
    )
    notes = cursor.fetchall()
    conn.close()

    if not notes:
        return "Заметок пока нет."

    lines = []
    for note in notes:
        if note["visibility"] == "interpretation" and note["public_interpretation"]:
            lines.append(f"{note['author_name']}: {note['public_interpretation']}")
        elif note["visibility"] == "public" and note["public_text"]:
            lines.append(f"{note['author_name']}: {note['public_text']}")

    return "\n".join(lines) if lines else "Заметок пока нет."


def get_all_members() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM members ORDER BY name")
    members = [row["name"] for row in cursor.fetchall()]
    conn.close()
    return members
