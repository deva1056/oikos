"""Переосмысление тегов через LLM (отложенный /retag, пакетно).

По умолчанию берёт заметки с тегом «прочее» и прогоняет их текст через
extract_note_metadata() → проставляет typed-теги (topic:/person:/type:).

ВАЖНО: трогает ТОЛЬКО теги. event_date НЕ переставляет — в старых заметках
относительные даты («завтра») были привязаны к дате написания, и сейчас
их резолвить нельзя.

Нужен OPENAI_API_KEY в окружении (запуск в шелле Railway или локально с ключом).

Запуск:
    DATABASE_URL=... python scripts/retag_notes.py --dry          # показать
    DATABASE_URL=... python scripts/retag_notes.py                # применить (только «прочее»)
    DATABASE_URL=... python scripts/retag_notes.py --all          # перетегировать ВСЕ заметки
"""
import json
import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

# чтобы скрипт можно было запускать как `python scripts/...` из корня репо
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai import extract_note_metadata
from core.memory import _parse_tags, normalize_tag

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("DATABASE_URL не задана")

DRY = "--dry" in sys.argv
ALL = "--all" in sys.argv


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # известные теги — чтобы LLM переиспользовал канон, а не плодил синонимы
    cur.execute("SELECT tags FROM notes")
    known = sorted({t for r in cur.fetchall() for t in _parse_tags(r["tags"])})

    cur.execute("SELECT id, text, tags, author_name FROM notes ORDER BY id")
    rows = cur.fetchall()
    targets = [r for r in rows if ALL or "прочее" in _parse_tags(r["tags"])]
    print(f"К перетегированию: {len(targets)}\n")

    changed = 0
    for r in targets:
        meta = extract_note_metadata(r["text"], None, known, r["author_name"])
        new = [t for t in (normalize_tag(x) for x in meta.get("tags", [])) if t]
        old = _parse_tags(r["tags"])
        if not new:
            print(f"  #{r['id']}: LLM не дал тегов, оставляю {old}")
            continue
        if new == old:
            continue
        changed += 1
        print(f"  #{r['id']}: {old} -> {new}")
        print(f"        «{r['text'][:60]}…»")
        if not DRY:
            cur.execute(
                "UPDATE notes SET tags = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (json.dumps(new), r["id"]),
            )

    if DRY:
        print(f"\n[dry-run] изменилось бы {changed}. Ничего не записано.")
        conn.rollback()
    else:
        conn.commit()
        print(f"\n✅ Перетегировано {changed}.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
