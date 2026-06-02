import json
from psycopg2.extras import RealDictCursor
from core.db import get_connection


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


def add_note(user_id, author_name: str, private_text: str, tags: list, visibility: str = "private", interpretation: str = None, public_text: str = None) -> dict:
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    tags_json = json.dumps(tags)
    cursor.execute(
        """
        INSERT INTO notes (author_id, author_name, private_text, public_interpretation, public_text, visibility, tags)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (str(user_id), author_name, private_text, interpretation, public_text, visibility, tags_json),
    )
    note = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()

    return dict(note)


def update_note_visibility(note_id: int, visibility: str, interpretation: str = None, public_text: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE notes
        SET visibility = %s, public_interpretation = %s, public_text = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (visibility, interpretation, public_text, note_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


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


def get_public_context() -> str:
    """Get only public notes (interpretation + public) for Claude."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        """
        SELECT author_name, public_interpretation, public_text, visibility
        FROM notes
        WHERE visibility IN ('interpretation', 'public')
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
        if note["visibility"] == "interpretation" and note["public_interpretation"]:
            lines.append(f"{note['author_name']}: {note['public_interpretation']}")
        elif note["visibility"] == "public" and note["public_text"]:
            lines.append(f"{note['author_name']}: {note['public_text']}")

    return "\n".join(lines) if lines else "Заметок пока нет."


def get_all_members() -> list:
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT name FROM members ORDER BY name")
    members = [row["name"] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return members
