"""Удаление всех заметок с данным тегом (для чистки тестовых данных).

Сравнение по значению тега (без namespace): 'debug' матчит и 'topic:debug'.

Запуск:
    DATABASE_URL=... python scripts/delete_by_tag.py --dry debug   # показать
    DATABASE_URL=... python scripts/delete_by_tag.py debug         # удалить
"""
import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.memory import _parse_tags, normalize_tag, tag_value

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("DATABASE_URL не задана")

DRY = "--dry" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    sys.exit("Укажи тег: python scripts/delete_by_tag.py [--dry] debug")
target = tag_value(normalize_tag(args[0]))


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, author_name, text, tags FROM notes ORDER BY id")
    matched = [
        r for r in cur.fetchall()
        if target in {tag_value(t) for t in _parse_tags(r["tags"])}
    ]

    for r in matched:
        print(f"  #{r['id']} [{r['author_name']}] {r['text'][:60]}")

    if DRY:
        print(f"\n[dry-run] удалилось бы {len(matched)} (тег #{target}). Ничего не удалено.")
        conn.rollback()
    else:
        ids = [r["id"] for r in matched]
        if ids:
            cur.execute("DELETE FROM notes WHERE id = ANY(%s)", (ids,))
        conn.commit()
        print(f"\n🗑 Удалено {len(ids)} заметок с тегом #{target}.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
