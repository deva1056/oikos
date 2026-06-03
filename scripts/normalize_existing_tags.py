"""Разовая нормализация существующих тегов в notes.

Применяет ту же механическую normalize_tag(), что и боевой код:
регистр, ё→е, пробелы→_, выкидывает мусорные символы, схлопывает дубли.
НЕ добавляет namespace (topic:/person:) — это семантика, задача LLM (/retag).

Идемпотентно: повторный запуск ничего не меняет.

Запуск:
    DATABASE_URL=... python scripts/normalize_existing_tags.py          # применить
    DATABASE_URL=... python scripts/normalize_existing_tags.py --dry    # только показать
"""
import json
import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

# чтобы скрипт можно было запускать как `python scripts/...` из корня репо
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.memory import _parse_tags, normalize_tag

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("DATABASE_URL не задана")

DRY = "--dry" in sys.argv


def normalize_list(raw) -> list:
    """Нормализовать список тегов с дедупом и сохранением порядка."""
    out, seen = [], set()
    for tag in _parse_tags(raw):
        n = normalize_tag(tag)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, tags FROM notes ORDER BY id")
    rows = cur.fetchall()

    scanned = changed = 0
    for row in rows:
        scanned += 1
        before = _parse_tags(row["tags"])
        after = normalize_list(row["tags"])
        if before == after:
            continue
        changed += 1
        print(f"  #{row['id']}: {before} -> {after}")
        if not DRY:
            cur.execute(
                "UPDATE notes SET tags = %s WHERE id = %s",
                (json.dumps(after), row["id"]),
            )

    if DRY:
        print(f"\n[dry-run] просмотрено {scanned}, изменилось бы {changed}. Ничего не записано.")
        conn.rollback()
    else:
        conn.commit()
        print(f"\n✅ Просмотрено {scanned}, обновлено {changed}.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
