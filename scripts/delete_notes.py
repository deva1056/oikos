"""Разовое удаление заметок по id (для чистки дев-мусора).

Запуск:
    DATABASE_URL=... python scripts/delete_notes.py --dry 6 7 8 15 16   # показать
    DATABASE_URL=... python scripts/delete_notes.py 6 7 8 15 16         # удалить
"""
import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("DATABASE_URL не задана")

DRY = "--dry" in sys.argv
ids = [int(a.lstrip("#")) for a in sys.argv[1:] if a.lstrip("#").isdigit()]
if not ids:
    sys.exit("Укажи id: python scripts/delete_notes.py [--dry] 6 7 8")


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, author_name, text FROM notes WHERE id = ANY(%s) ORDER BY id", (ids,))
    rows = cur.fetchall()

    found = {r["id"] for r in rows}
    missing = [i for i in ids if i not in found]
    for r in rows:
        print(f"  #{r['id']} [{r['author_name']}]: {r['text'][:70]}")
    if missing:
        print(f"  (не найдены: {missing})")

    if DRY:
        print(f"\n[dry-run] удалилось бы {len(rows)} из {len(ids)}. Ничего не удалено.")
        conn.rollback()
    else:
        cur.execute("DELETE FROM notes WHERE id = ANY(%s)", (ids,))
        conn.commit()
        print(f"\n🗑 Удалено {cur.rowcount} заметок.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
