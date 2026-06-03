"""Разовая миграция notes: 3-уровневая приватность → одно поле `text`.

Логика:
- приватные заметки (visibility='private') ДРОПАЕМ — у них нет согласованной
  для семьи версии, а сырой private_text хранить мы больше не хотим;
- из остальных переносим в `text` публичную версию (public_text, иначе
  public_interpretation);
- удаляем старые колонки.

⚠️ НЕОБРАТИМО. Перед запуском сделай бэкап:
    pg_dump "$DATABASE_URL" > backup_$(date +%F).sql

Запуск (локально с боевым DATABASE_URL или на Railway):
    DATABASE_URL=... python scripts/migrate_to_single_field.py
"""
import os
import sys

import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("DATABASE_URL не задана")


def column_exists(cur, table, column) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    if not column_exists(cur, "notes", "visibility"):
        print("Колонки visibility нет — миграция, похоже, уже выполнена. Выходим.")
        conn.close()
        return

    cur.execute("SELECT COUNT(*) FROM notes")
    total_before = cur.fetchone()[0]

    # 1. новая колонка
    cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS text TEXT")

    # 2. дропаем приватные
    cur.execute("DELETE FROM notes WHERE visibility = 'private'")
    dropped = cur.rowcount

    # 3. переносим публичную версию
    cur.execute(
        "UPDATE notes SET text = COALESCE(public_text, public_interpretation) WHERE text IS NULL"
    )

    # 4. подчищаем то, что осталось без текста (на всякий случай)
    cur.execute("DELETE FROM notes WHERE text IS NULL OR text = ''")
    cleaned = cur.rowcount

    # 5. NOT NULL + дроп старых колонок
    cur.execute("ALTER TABLE notes ALTER COLUMN text SET NOT NULL")
    for col in ("private_text", "public_interpretation", "public_text", "visibility"):
        cur.execute(f"ALTER TABLE notes DROP COLUMN IF EXISTS {col}")

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM notes")
    total_after = cur.fetchone()[0]
    cur.close()
    conn.close()

    print(f"Было заметок:        {total_before}")
    print(f"Дропнуто приватных:  {dropped}")
    print(f"Дропнуто без текста: {cleaned}")
    print(f"Осталось:            {total_after}")
    print("✅ Миграция завершена.")


if __name__ == "__main__":
    main()
