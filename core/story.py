"""Генератор тренировочных историй на чешском (уровень A2) для /story.

Три режима: по картинке, про погоду, пересказ своей заметки (about_me).
Общие правила уровня/структуры собраны в одном месте (_story_system),
чтобы не расползались по трём промптам.
"""
import logging
import random
from datetime import date

from core.ai import _complete, _complete_vision, _parse_json
from core.memory import _parse_tags, get_user_notes, normalize_tag, tag_value
from core.phrases import get_phrases_by_tags, get_random_phrases
from core.timeutils import now_prompt_str, to_local

logger = logging.getLogger(__name__)

CZ_TAG_VALUE = "cz"  # заметки-кандидаты для about_me: только с тегом topic:cz


# ---------- генерация ----------

def _story_system(task: str, vocab: list = None, past_tense: bool = True,
                  narrative: bool = True) -> str:
    """Общая обвязка промпта: уровень A2, время, структура, Slovníček, словарь."""
    rules = [
        "Ты помощник в изучении чешского языка. Уровень ученика — A2 (экзамен на trvalý pobyt).",
        "История — ТОЛЬКО на чешском: простые предложения, базовая лексика A2, "
        "без сложных подчинённых конструкций.",
    ]
    if past_tense:
        rules.append("Время повествования — прошедшее (minulý čas).")
    if narrative:
        rules.append(
            "Обязательная структура повествования: начни с «Nejdřív…», "
            "развивай через «Potom…» и «Pak…», закончи «Nakonec…»."
        )
    if vocab:
        rules.append(
            "Обязательно естественно вплети в историю 2–3 фразы из словаря ученика: "
            + "; ".join(vocab)
        )
    rules.append(
        "После истории добавь блок «Slovníček:» — 5–6 ключевых слов или фраз "
        "из истории с переводом на русский, каждое с новой строки, "
        "в формате: slovo — перевод."
    )
    rules.append(task)
    return "\n".join(rules)


def generate_story_from_image(image_b64: str, vocab: list = None,
                              media_type: str = "image/jpeg") -> str:
    """История 6–8 предложений по фотографии. Картинка не сохраняется/не логируется."""
    system = _story_system(
        "Посмотри на картинку и составь по ней историю из 6–8 предложений "
        "о том, что на ней происходит или могло происходить.",
        vocab,
    )
    return _complete_vision(system, "Составь историю по этой картинке.", image_b64,
                            media_type=media_type, max_tokens=1024)


# Случайный ракурс, чтобы два подряд вызова погоды не давали один шаблон.
_WEATHER_ANGLES = [
    "ráno, cestou do práce", "odpoledne v parku", "večer u okna doma",
    "o víkendu na výletě", "ve městě na náměstí", "na zahradě",
]

_WEATHER_KIND = {
    "good": "ХОРОШАЯ погода (svítí slunce, je teplo, je hezky)",
    "bad": "ПЛОХАЯ погода (prší, sněží, fouká vítr, je zima, je zataženo)",
}


def generate_story_weather(kind: str, vocab: list = None) -> str:
    """3–4 предложения о погоде. Настоящее время допустимо, без nejdřív/nakonec."""
    system = _story_system(
        f"Напиши 3–4 предложения о погоде. Погода — {_WEATHER_KIND[kind]}. "
        "Используй тематическую лексику: svítí slunce, je teplo, je zima, prší, "
        "sněží, fouká vítr, je zataženo. Каждый раз варьируй формулировки и детали, "
        "не повторяй один и тот же шаблон. "
        f"Ракурс для вдохновения: {random.choice(_WEATHER_ANGLES)}.",
        vocab,
        past_tense=False,
        narrative=False,
    )
    return _complete(system, "Napiš text o počasí.", max_tokens=600)


def generate_story_about_me(note_text: str, vocab: list = None) -> str:
    """Пересказ заметки пользователя как истории от первого лица на чешском."""
    system = _story_system(
        "Перескажи запись из дневника ученика (она на русском) как историю "
        "от первого лица на чешском, 6–8 предложений. Детали, которые нельзя "
        "выразить средствами A2, упрощай или опускай.",
        vocab,
    )
    return _complete(system, f"Запись из дневника:\n{note_text}", max_tokens=1024)


# ---------- разбор запроса about_me ----------

def parse_about_me_query(query: str, tz_name: str = None) -> dict:
    """Свободный текст после about_me → {selector, date, tags}. Даты разрешаются здесь.

    Пустой запрос — без похода в LLM: последняя заметка.
    """
    empty = {"selector": "latest", "date": None, "tags": []}
    query = (query or "").strip()
    if not query:
        return empty

    system = f"""Ты разбираешь запрос ученика: про какую его заметку сгенерировать историю.

Сейчас: {now_prompt_str(tz_name)} (таймзона пользователя).

Верни JSON:
{{
  "selector": "latest" или "date",
  "date": "ГГГГ-ММ-ДД" или null,
  "tags": ["тема"]
}}

Правила:
- selector="date" + конкретная дата, если в запросе есть указание на день
  (вчера, позавчера, в понедельник, 3 июня) — разреши его в абсолютную дату
  относительно «сейчас». Иначе selector="latest", date=null.
- tags — темы из запроса (тренировка, врач, покупки...), по-русски, в нижнем
  регистре, без пробелов (используй _). Нет тем — пустой список.
- Только JSON, без пояснений."""
    data = _parse_json(_complete(system, query, max_tokens=300, json_mode=False))
    selector = "date" if data.get("selector") == "date" and data.get("date") else "latest"
    parsed_date = None
    if selector == "date":
        try:
            parsed_date = date.fromisoformat(data["date"])
        except (ValueError, TypeError):
            selector, parsed_date = "latest", None
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    return {
        "selector": selector,
        "date": parsed_date,
        "tags": [t for t in (normalize_tag(t) for t in tags) if t],
    }


# ---------- выбор заметки ----------

def _cz_candidates(member_id, tz_name: str = None) -> list:
    """Заметки САМОГО пользователя с тегом cz (по значению, без namespace).

    Чужие заметки не берём никогда: история пересказывает личный дневник.
    """
    rows = get_user_notes(member_id)
    out = []
    for r in rows:
        if CZ_TAG_VALUE not in {tag_value(t) for t in _parse_tags(r["tags"])}:
            continue
        # эффективная дата: машинная дата события, иначе день создания (локальный)
        eff = r.get("event_date") or to_local(r["created_at"], tz_name).date()
        r["_eff_date"] = eff
        out.append(r)
    return out


def find_note_for_story(member_id, parsed: dict, tz_name: str = None) -> dict:
    """Заметка под разобранный запрос или None. Несколько подходящих → самая свежая."""
    rows = _cz_candidates(member_id, tz_name)

    if parsed.get("selector") == "date" and parsed.get("date"):
        rows = [r for r in rows if r["_eff_date"] == parsed["date"]]

    wanted = {tag_value(t) for t in parsed.get("tags", [])} - {""}
    if wanted:
        rows = [r for r in rows if wanted & {tag_value(t) for t in _parse_tags(r["tags"])}]

    if not rows:
        return None
    rows.sort(key=lambda r: (r["_eff_date"], r["created_at"]), reverse=True)
    return rows[0]


def get_cz_note_tags(member_id, tz_name: str = None) -> list:
    """(тег, количество) по cz-заметкам пользователя — для честного «не нашёл»."""
    counter = {}
    for r in _cz_candidates(member_id, tz_name):
        for t in _parse_tags(r["tags"]):
            if tag_value(t) != CZ_TAG_VALUE:
                counter[t] = counter.get(t, 0) + 1
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


def pick_vocab(member_id, tags: list = None, limit: int = 3) -> list:
    """До `limit` чешских фраз из словаря: по тегам, иначе случайные.

    Пустой словарь — нормальная ситуация: вернём [], vocab просто не передаём.
    """
    rows = get_phrases_by_tags(member_id, tags or [], limit) if tags else []
    if not rows:
        rows = get_random_phrases(member_id, limit)
    return [r["phrase"] for r in rows]
