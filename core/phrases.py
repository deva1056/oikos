import json

from core.db import db_cursor
from core.memory import _parse_tags, normalize_tag, tag_value


def add_phrase(member_id, phrase: str, translation: str = None, example: str = None,
               tags: list = None, source: str = "manual") -> dict:
    """Сохранить фразу в личный словарь. Теги нормализуются, как у заметок."""
    tags = [t for t in (normalize_tag(t) for t in (tags or [])) if t]
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO phrases (member_id, phrase, translation, example, tags, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (str(member_id), phrase.strip(), translation, example, json.dumps(tags), source),
        )
        return dict(cur.fetchone())


def get_phrases_by_tags(member_id, tags: list, limit: int = 3) -> list:
    """Фразы пользователя, чьи теги пересекаются с данными (по значению, без namespace).

    Фильтрация в Python — личный словарь небольшой, как и в остальном проекте.
    """
    wanted = {tag_value(normalize_tag(t)) for t in (tags or [])} - {""}
    if not wanted:
        return []
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM phrases WHERE member_id = %s ORDER BY created_at DESC",
            (str(member_id),),
        )
        rows = [dict(r) for r in cur.fetchall()]
    hits = [r for r in rows if wanted & {tag_value(t) for t in _parse_tags(r["tags"])}]
    return hits[:limit]


def get_random_phrases(member_id, limit: int = 3) -> list:
    """Случайные фразы пользователя — когда по тегам ничего не совпало."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM phrases WHERE member_id = %s ORDER BY random() LIMIT %s",
            (str(member_id), limit),
        )
        return [dict(r) for r in cur.fetchall()]
