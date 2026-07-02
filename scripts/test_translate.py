"""Тесты /t_cz и /t_eng: промпт, эвристика 💾-подсказки, извлечение текста.

Запуск:  python scripts/test_translate.py  (БД и LLM не нужны — всё на моках)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://x/x")  # не используется

import core.translate as tr  # noqa: E402
from bot.handlers.translate import MAX_LEN, extract_text  # noqa: E402

_passed = 0


def check(cond, msg):
    global _passed
    assert cond, "FAIL: " + msg
    _passed += 1
    print("  ok:", msg)


# ---------- 1. промпт ----------

def test_prompt():
    calls = {}
    orig = tr._complete

    def fake(system, user, max_tokens, json_mode=False):
        calls["system"], calls["user"] = system, user
        return "Musím si prodloužit kupón."

    tr._complete = fake
    try:
        tr.translate("Мне нужно продлить проездной", "cz")
        s = calls["system"]
        check("чешский" in s and "строго A2" in s, "cz: язык и уровень в промпте")
        check("на русский" in s, "cz: обратное направление на русский")
        check("упрощено" in s, "cz: пометка об упрощении")
        check("💡" in s and "1–2" in s, "cz: заметки только по делу, максимум 1–2")
        check("Никаких приветствий" in s, "cz: без болтовни")
        check(calls["user"] == "Мне нужно продлить проездной", "cz: текст уходит как есть")

        tr.translate("hello", "eng")
        s = calls["system"]
        check("английский" in s and "A2–B1" in s, "eng: язык и уровень")
    finally:
        tr._complete = orig


# ---------- 2. эвристика подсказки 💾 (только ru→cz, коротко) ----------

def test_phrase_hint():
    h = tr.phrase_hint("Мне нужно продлить проездной", "Musím si prodloužit kupón.")
    check(h == "💾 Сохранить в словарь: /phrase Musím si prodloužit kupón. — Мне нужно продлить проездной",
          "ru→cz коротко → подсказка с готовой командой")

    h = tr.phrase_hint("Мне нужно продлить проездной",
                       "Musím si prodloužit kupón.\n💡 kupón — это проездной, ложный друг")
    check(h and "💡" not in h, "заметки 💡 не попадают в подсказку (берётся первая строка)")

    check(tr.phrase_hint("Musím si prodloužit kupón", "Мне нужно продлить проездной.") is None,
          "cz→ru → подсказки нет")
    long_result = "Tohle je opravdu velmi dlouhy preklad ktery se nevejde do slovniku nikdy"
    check(tr.phrase_hint("Длинная русская фраза", long_result) is None, "длиннее 60 → нет")
    check(tr.phrase_hint("привет", "") is None and tr.phrase_hint("", "ahoj") is None,
          "пустые вход/выход → нет")
    check(tr.phrase_hint("сложная мысль", "⚠️ упрощено: пришлось убрать идиому") is None,
          "первая строка без латиницы (служебная) → нет")


# ---------- 3. извлечение текста из апдейта (args / reply) ----------

class _Msg:
    def __init__(self, text=None, caption=None, reply=None):
        self.text, self.caption, self.reply_to_message = text, caption, reply


class _Upd:
    def __init__(self, reply=None):
        self.message = _Msg(reply=reply)


class _Ctx:
    def __init__(self, args):
        self.args = args


def test_extract_text():
    check(extract_text(_Upd(), _Ctx(["Мне", "нужно", "хлеб"])) == "Мне нужно хлеб",
          "args склеиваются")
    check(extract_text(_Upd(reply=_Msg(text="Musím jít domů")), _Ctx([])) == "Musím jít domů",
          "reply без своего текста → текст reply-сообщения")
    check(extract_text(_Upd(reply=_Msg(caption="podpis fotky")), _Ctx([])) == "podpis fotky",
          "reply на фото → подпись")
    check(extract_text(_Upd(reply=_Msg(text="из reply")), _Ctx(["свой", "текст"])) == "свой текст",
          "свой текст приоритетнее reply")
    check(extract_text(_Upd(), _Ctx([])) == "", "пусто и без reply → ''")
    check(MAX_LEN == 1000, "лимит входа ~1000 символов")


if __name__ == "__main__":
    test_prompt()
    test_phrase_hint()
    test_extract_text()
    print(f"\nВСЕ {_passed} проверок прошли ✅")
