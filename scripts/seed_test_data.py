"""Сидинг тестовых данных, помеченных тегом debug.

Детерминированно (без LLM): сами задаём теги, даты, note_type/status —
чтобы тестовый набор был воспроизводимым. Авторство — по реальным участникам.

Удаление после теста:  scripts/delete_by_tag.py debug

Запуск:  DATABASE_URL=... python scripts/seed_test_data.py
"""
import os
import sys
from datetime import time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_connection
from core.memory import add_note
from core.timeutils import now_local

if not os.getenv("DATABASE_URL"):
    sys.exit("DATABASE_URL не задана")

TEST_TAG = "debug"


def _members():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, name FROM members ORDER BY id")
    rows = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def main():
    members = _members()
    if not members:
        sys.exit("Нет зарегистрированных участников — сначала /start в боте.")

    def find(sub, default):
        return next((m for m in members if sub in m["name"].lower()), default)

    tanya = find("тан", members[0])
    andrey = find("андр", members[-1])

    today = now_local().date()
    tomorrow = today + timedelta(days=1)
    friday = today + timedelta(days=((4 - today.weekday()) % 7) or 7)

    # (автор, текст, теги, event_date, event_time, note_type, status)
    notes = [
        (tanya, "Варю отвести к стоматологу",
         ["person:варя", "topic:врач", "type:событие", TEST_TAG], tomorrow, time(15, 0), "note", None),
        (andrey, "Боря к врачу, пятница утром",
         ["person:боря", "topic:врач", "type:событие", TEST_TAG], friday, time(9, 0), "note", None),
        (tanya, "Варя хочет ролики на день рождения",
         ["person:варя", "topic:подарки", "type:желание", TEST_TAG], None, None, "wish", "open"),
        (andrey, "Хочу новый шоссейный велосипед",
         ["person:андрей", "topic:спорт", "type:желание", TEST_TAG], None, None, "wish", "open"),
        (tanya, "Сходить всей семьёй в аквапарк",
         ["topic:планы", "type:желание", TEST_TAG], None, None, "wish", "open"),
        (tanya, "Купить молоко, хлеб и корм собакам",
         ["topic:покупки", TEST_TAG], None, None, "note", None),
        (andrey, "Боря любит, когда ему читают на ночь",
         ["person:боря", "topic:семья", "type:факт", TEST_TAG], None, None, "note", None),
    ]

    ids = []
    for author, text, tags, ed, et, nt, st in notes:
        note = add_note(author["id"], author["name"], text, tags,
                        event_date=ed, event_time=et, note_type=nt, status=st)
        ids.append(note["id"])
        kind = "💭" if nt == "wish" else "📝"
        when = f" 🗓{ed}" if ed else ""
        print(f"  {kind} #{note['id']} [{author['name']}] {text}{when}")

    print(f"\n✅ Засеяно {len(ids)} заметок с тегом #{TEST_TAG}.")
    print(f"Удалить после теста: python scripts/delete_by_tag.py {TEST_TAG}")


if __name__ == "__main__":
    main()
