"""Тесты /story: роутинг, промпты, парсер запроса, выбор заметки, словарь фраз.

Запуск:  DATABASE_URL=... python scripts/test_story.py
LLM всегда мокается. Часть с БД идёт на реальную (лаб) базу и чистит за собой;
без DATABASE_URL на живую лабу — используйте .env.lab.
"""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres@localhost:55432/oikos_test")

import json  # noqa: E402

import core.ai as ai  # noqa: E402
import core.story as story  # noqa: E402
from bot.handlers.story import parse_story_args  # noqa: E402

_passed = 0


def check(cond, msg):
    global _passed
    assert cond, "FAIL: " + msg
    _passed += 1
    print("  ok:", msg)


# ---------- 1. роутинг аргументов ----------

def test_routing():
    check(parse_story_args([]) == ("help", None), "без аргументов → help")
    check(parse_story_args(["weather", "good"]) == ("weather", "good"), "weather good")
    check(parse_story_args(["wether", "good"]) == ("weather", "good"), "опечатка wether")
    check(parse_story_args(["weater", "b"]) == ("weather", "bad"), "weater b → bad")
    check(parse_story_args(["weather"]) == ("help", None), "weather без вида → help")
    check(parse_story_args(["weather", "хорошая"]) == ("help", None), "weather мусор → help")
    check(parse_story_args(["about_me", "вчера", "тренировка"]) == ("about_me", "вчера тренировка"),
          "about_me со свободным текстом")
    check(parse_story_args(["about_me"]) == ("about_me", ""), "about_me пустой")
    check(parse_story_args(["чушь"]) == ("help", None), "мусорный аргумент → help")


# ---------- 2. промпты генераторов (мокаем LLM) ----------

def test_prompts():
    calls = {}

    def fake_complete(system, user, max_tokens, json_mode=False):
        calls["system"], calls["user"] = system, user
        return "Nejdřív ... Nakonec ...\nSlovníček:\nslovo — перевод"

    def fake_vision(system, text, image_b64, media_type="image/jpeg", max_tokens=1024):
        calls["system"], calls["image"], calls["media"] = system, image_b64, media_type
        return "příběh"

    orig_c, orig_v = story._complete, story._complete_vision
    story._complete, story._complete_vision = fake_complete, fake_vision
    try:
        story.generate_story_about_me("Вчера была тренировка", vocab=["dát si pauzu"])
        s = calls["system"]
        check("A2" in s, "about_me: уровень A2 в промпте")
        check("Nejdřív" in s and "Nakonec" in s, "about_me: структура nejdřív/nakonec")
        check("minulý čas" in s, "about_me: прошедшее время")
        check("Slovníček" in s, "about_me: блок Slovníček")
        check("dát si pauzu" in s, "about_me: vocab вплетён в промпт")
        check("первого лица" in s, "about_me: от первого лица")

        story.generate_story_weather("good")
        s = calls["system"]
        check("svítí slunce" in s, "weather: тематическая лексика")
        check("варьируй" in s.lower(), "weather: указание варьировать")
        check("Nejdřív" not in s, "weather: без nejdřív/nakonec")
        check("minulý čas" not in s, "weather: без требования прошедшего времени")
        story.generate_story_weather("bad")
        check("prší" in calls["system"], "weather bad: лексика плохой погоды")

        story.generate_story_from_image("QUJD", vocab=None)
        check(calls["image"] == "QUJD" and calls["media"] == "image/jpeg", "image: b64 дошёл до vision")
        check("6–8" in calls["system"], "image: 6–8 предложений")
    finally:
        story._complete, story._complete_vision = orig_c, orig_v


# ---------- 3. parse_about_me_query ----------

def test_parse_query():
    orig = story._complete

    def fake(system, user, max_tokens, json_mode=False):
        fake.called = True
        return json.dumps({"selector": "date", "date": "2026-06-03", "tags": ["Тренировка"]})

    fake.called = False
    story._complete = fake
    try:
        p = story.parse_about_me_query("вчера тренировка", "Europe/Prague")
        check(p["selector"] == "date" and p["date"] == date(2026, 6, 3), "parse: дата разрешена")
        check(p["tags"] == ["тренировка"], "parse: теги нормализованы")

        fake.called = False
        p = story.parse_about_me_query("   ", "Europe/Prague")
        check(p == {"selector": "latest", "date": None, "tags": []}, "parse: пустой запрос → latest")
        check(not fake.called, "parse: пустой запрос не ходит в LLM")

        story._complete = lambda *a, **k: "не json"
        p = story.parse_about_me_query("что-то", None)
        check(p["selector"] == "latest" and p["tags"] == [], "parse: битый JSON → latest")
    finally:
        story._complete = orig


# ---------- 4. find_note_for_story (мокаем заметки) ----------

def _note(nid, tags, event_date=None, created=None, text="txt"):
    return {"id": nid, "text": text, "tags": json.dumps(tags),
            "event_date": event_date, "created_at": created or datetime(2026, 6, 1, 12)}


def test_find_note():
    yesterday = date(2026, 6, 3)
    notes = [
        _note(1, ["topic:cz", "topic:тренировка"], event_date=yesterday),
        _note(2, ["topic:cz", "topic:врач"], event_date=date(2026, 5, 20)),
        _note(3, ["topic:cz"], created=datetime(2026, 6, 3, 9)),          # без event_date
        _note(4, ["topic:покупки"], event_date=yesterday),                 # НЕ cz
        _note(5, ["cz", "topic:тренировка"], event_date=date(2026, 5, 1)),  # cz без namespace
    ]
    orig = story.get_user_notes
    story.get_user_notes = lambda uid: [dict(n) for n in notes]
    try:
        p = {"selector": "date", "date": yesterday, "tags": ["тренировка"]}
        r = story.find_note_for_story("1", p, "Europe/Prague")
        check(r and r["id"] == 1, "дата+тег → нужная заметка")

        p = {"selector": "date", "date": yesterday, "tags": []}
        r = story.find_note_for_story("1", p, "Europe/Prague")
        check(r and r["id"] in (1, 3), "дата без тегов: fallback created_at участвует")

        p = {"selector": "latest", "date": None, "tags": []}
        r = story.find_note_for_story("1", p, "Europe/Prague")
        check(r and r["id"] in (1, 3), "latest → самая свежая по эффективной дате")

        p = {"selector": "latest", "date": None, "tags": ["тренировка"]}
        r = story.find_note_for_story("1", p, "Europe/Prague")
        check(r and r["id"] == 1, "несколько по тегу → самая свежая, молча")

        p = {"selector": "date", "date": date(2020, 1, 1), "tags": []}
        check(story.find_note_for_story("1", p, "Europe/Prague") is None, "нет совпадений → None")

        p = {"selector": "latest", "date": None, "tags": ["покупки"]}
        check(story.find_note_for_story("1", p, "Europe/Prague") is None,
              "не-cz заметка не попадает даже при совпадении тега")

        p = {"selector": "latest", "date": None, "tags": []}
        r = story.find_note_for_story("1", p, None)
        check(r is not None, "без таймзоны тоже работает (DEFAULT_TZ)")

        tags = story.get_cz_note_tags("1", "Europe/Prague")
        names = [t for t, _ in tags]
        check("topic:тренировка" in names and "topic:cz" not in names,
              "сводка тегов: есть темы, нет самого cz")
    finally:
        story.get_user_notes = orig


# ---------- 5. _complete_vision: форма запроса к обоим провайдерам ----------

class _FakeMsg:
    def __init__(self, text):
        self.content = text
        self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]


def test_vision_payloads():
    captured = {}

    class FakeOpenAI:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    captured["openai"] = kw
                    return _FakeMsg("ok")

    class FakeAnthropic:
        class messages:
            @staticmethod
            def create(**kw):
                captured["anthropic"] = kw
                return type("R", (), {"content": [type("B", (), {"text": "ok"})()]})()

    orig_provider, orig_oc, orig_ac = ai.PROVIDER, ai._openai_client, ai._anthropic_client
    try:
        ai.PROVIDER, ai._openai_client = "openai", FakeOpenAI()
        ai._complete_vision("sys", "txt", "QUJD", media_type="image/png")
        parts = captured["openai"]["messages"][1]["content"]
        img = [p for p in parts if p["type"] == "image_url"][0]
        check(img["image_url"]["url"] == "data:image/png;base64,QUJD", "openai: data-url картинки")
        check(captured["openai"]["messages"][0]["role"] == "system", "openai: system первым")

        ai.PROVIDER, ai._anthropic_client = "anthropic", FakeAnthropic()
        ai._complete_vision("sys", "txt", "QUJD", media_type="image/png")
        blocks = captured["anthropic"]["messages"][0]["content"]
        img = [b for b in blocks if b["type"] == "image"][0]
        check(img["source"] == {"type": "base64", "media_type": "image/png", "data": "QUJD"},
              "anthropic: base64-блок картинки")
        check(captured["anthropic"]["system"] == "sys", "anthropic: system параметром")
    finally:
        ai.PROVIDER, ai._openai_client, ai._anthropic_client = orig_provider, orig_oc, orig_ac


# ---------- 6. живая БД: phrases + выбор заметки ----------

def test_db():
    from core.db import init_db
    from core.memory import add_note, delete_note
    from core.phrases import add_phrase, get_phrases_by_tags, get_random_phrases
    from core.db import db_cursor

    init_db()  # создаст phrases, если её ещё нет
    uid = "128121642"

    ph1 = add_phrase(uid, "dát si pauzu", "сделать паузу", tags=["#Тренировка"])
    ph2 = add_phrase(uid, "jít k lékaři", "пойти к врачу", tags=["topic:врач"], source="teacher")
    try:
        check(json.loads(ph1["tags"]) == ["тренировка"], "phrases: теги нормализованы")
        hits = get_phrases_by_tags(uid, ["topic:тренировка"], 3)
        check([h["phrase"] for h in hits] == ["dát si pauzu"], "phrases: поиск по тегу (по значению)")
        check(get_phrases_by_tags(uid, [], 3) == [], "phrases: пустые теги → пусто")
        rnd = get_random_phrases(uid, 5)
        check(len(rnd) >= 2, "phrases: random отдаёт фразы")
        check(get_random_phrases("999999", 3) == [], "phrases: чужой словарь пуст")

        vocab = story.pick_vocab(uid, ["topic:тренировка"])
        check(vocab == ["dát si pauzu"], "pick_vocab: по тегам")
        vocab = story.pick_vocab(uid, ["topic:небыло"])
        check(len(vocab) >= 1, "pick_vocab: fallback на случайные")
        check(story.pick_vocab("999999") == [], "pick_vocab: пустой словарь → []")

        # выбор заметки на реальных данных: моя cz-заметка находится, чужая — нет
        mine = add_note(uid, "Андрей", "Byl jsem na tréninku", ["topic:cz", "topic:тренировка"],
                        event_date=date.today() - timedelta(days=1))
        other = add_note("262349411", "Таня", "тоже про чешский", ["topic:cz", "topic:тренировка"],
                         event_date=date.today() - timedelta(days=1))
        try:
            p = {"selector": "date", "date": date.today() - timedelta(days=1), "tags": ["тренировка"]}
            r = story.find_note_for_story(uid, p, "Europe/Prague")
            check(r and r["id"] == mine["id"], "БД: своя cz-заметка найдена по дате+тегу")
            r = story.find_note_for_story("111", p, "Europe/Prague")
            check(r is None, "БД: чужие заметки не отдаются никогда")
        finally:
            delete_note(mine["id"], uid)
            delete_note(other["id"], "262349411")
    finally:
        with db_cursor() as cur:
            cur.execute("DELETE FROM phrases WHERE id IN (%s, %s)", (ph1["id"], ph2["id"]))


if __name__ == "__main__":
    test_routing()
    test_prompts()
    test_parse_query()
    test_find_note()
    test_vision_payloads()
    test_db()
    print(f"\nВСЕ {_passed} проверок прошли ✅")
