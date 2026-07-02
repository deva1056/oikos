"""Тест извлечения явных #тегов из текста заметки и слияния с LLM-тегами.

Запуск:  python scripts/test_hashtags.py  (БД не нужна)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://x/x")  # не используется

from core.memory import extract_hashtags  # noqa: E402

_passed = 0


def check(cond, msg):
    global _passed
    assert cond, "FAIL: " + msg
    _passed += 1
    print("  ok:", msg)


# пример из постановки задачи — дословно
EXAMPLE = (
    "сегодня утром гуляли всей семьей с собаками. Дошли до ручья. После грозы его "
    "весь размыло и упали два дерева. Потом мы слушали подкаст про глобальное "
    "потепление. Оно есть и не стоит игнорировать очевидные факты. Потом я работал "
    "и писал бота для генерации историй на чешском. #cz"
)

check(extract_hashtags(EXAMPLE) == ["cz"], "пример из задания → ['cz']")
check(extract_hashtags("купил #Покупки и #покупки хлеб") == ["покупки"], "дубли и регистр")
check(extract_hashtags("#topic:врач приём в 10") == ["topic:врач"], "namespace сохраняется")
check(extract_hashtags("#ёлка нарядили") == ["елка"], "ё → е")
check(extract_hashtags("без тегов вообще") == [], "нет тегов → []")
check(extract_hashtags("#cz #тренировка бег") == ["cz", "тренировка"], "несколько тегов, порядок")
check(extract_hashtags("см. issue #42 в трекере") == ["42"], "числовой тоже тег (норм для нас)")
check(extract_hashtags("") == [] and extract_hashtags(None) == [], "пусто/None")

# слияние как в save_draft: явные приоритетнее, без дублей, fallback 'прочее'
def merge(text, auto):
    explicit = extract_hashtags(text)
    return explicit + [t for t in auto if t not in explicit] or ["прочее"]

check(merge(EXAMPLE, ["topic:прогулка", "person:андрей"]) == ["cz", "topic:прогулка", "person:андрей"],
      "явный #cz добавлен к автоматическим")
check(merge("бег #cz", ["cz", "topic:спорт"]) == ["cz", "topic:спорт"], "дубль с LLM не плодится")
check(merge("ничего", []) == ["прочее"], "нет ничего → 'прочее'")

print(f"\nВСЕ {_passed} проверок прошли ✅")
