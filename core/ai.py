import json
import os

from core.timeutils import now_local, now_prompt_str

# Провайдер LLM переключается одной переменной окружения, без правки кода.
PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

_openai_client = None
_anthropic_client = None


def _openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def _anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic

        _anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _anthropic_client


def _complete(system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
    """Single completion, routed to the configured provider."""
    if PROVIDER == "anthropic":
        resp = _anthropic().messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text.strip()

    # default: OpenAI / GPT
    kwargs = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # max_completion_tokens — совместимо и с gpt-4o, и с новыми reasoning-моделями
        "max_completion_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _openai().chat.completions.create(**kwargs)
    return resp.choices[0].message.content.strip()


def _chat(system: str, messages: list, max_tokens: int) -> str:
    """Мультитёрн-обмен (для диалоговой правки черновика)."""
    if PROVIDER == "anthropic":
        resp = _anthropic().messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return resp.content[0].text.strip()

    full = [{"role": "system", "content": system}] + messages
    resp = _openai().chat.completions.create(
        model=OPENAI_MODEL,
        messages=full,
        max_completion_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


REFINE_SYSTEM = """Ты помогаешь члену семьи составить заметку для общей семейной памяти.

Пользователь описывает ситуацию и затем уточняет правками («убери про деньги», «сделай мягче», «добавь дату»).
Твоя задача — собрать лаконичную, понятную заметку, которую увидят ВСЕ члены семьи.

Правила:
- Учитывай все правки пользователя, переписывай заметку целиком с их учётом.
- Сохраняй важные факты: даты, имена, договорённости, суть.
- Если пользователь просит убрать детали — убирай их полностью.
- Пиши на русском, 1-3 коротких фразы.
- Выводи ТОЛЬКО итоговый текст заметки — без пояснений, кавычек и префиксов."""


def refine_draft(messages: list) -> str:
    """Из истории диалога (реплики пользователя + прошлые черновики) выдаёт
    обновлённый текст заметки. История живёт в памяти процесса, не в БД."""
    return _chat(REFINE_SYSTEM, messages, max_tokens=400)


EDIT_SYSTEM = """Ты редактируешь существующую заметку семейной памяти по инструкции.

Дан текущий текст заметки и правка пользователя. Внеси ТОЛЬКО запрошенное изменение.
Всё остальное сохрани ДОСЛОВНО: формулировки, факты, детали, стиль, порядок.
НЕ переформулируй, НЕ сокращай, НЕ интерпретируй, ничего не добавляй от себя.
Верни ТОЛЬКО полный обновлённый текст заметки — без пояснений и кавычек."""


def edit_text(current_text: str, instruction: str) -> str:
    """Применить точечную правку к тексту, сохраняя оригинал дословно (для /edit)."""
    user = f"Текущая заметка:\n{current_text}\n\nПравка: {instruction}"
    return _complete(EDIT_SYSTEM, user, max_tokens=600)


def _parse_json(raw: str) -> dict:
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def extract_note_metadata(text: str, tz_name: str = None, known_tags: list = None,
                          author_name: str = None) -> dict:
    """Метаданные заметки для индекса памяти: typed-теги + машинная дата события."""
    known = ", ".join(known_tags or []) or "(пока нет)"
    author = author_name or "автор"
    system = f"""Ты извлекаешь поисковые метаданные заметки семейной памяти.

Сейчас: {now_prompt_str(tz_name)} (таймзона пользователя).
Автор заметки: {author}.
Уже используемые теги семьи: {known}
Переиспользуй существующие теги, если подходят по смыслу (доктор/приём → topic:врач). Новые добавляй только при необходимости.

Верни JSON:
{{
  "tags": ["topic:...", "person:...", "type:..."],
  "note_type": "wish" или "note",
  "event_date": "ГГГГ-ММ-ДД" или null,
  "event_time": "ЧЧ:ММ" или null
}}

Правила:
- note_type="wish", если заметка выражает ЖЕЛАНИЕ кого-то (хочет, мечтает, хотел бы, просит). Фиксация факта/события/покупки = "note". Отрицание («не хочет») — НЕ wish.
- namespace тега обязателен: topic: (тема), person: (человек/питомец, имя в нижнем регистре), type: (тип: событие/покупка/идея/факт/желание).
- Если заметка от первого лица (я, мне, мой/моя/моё, у меня) — она про автора: добавь person:{author} (имя в нижнем регистре).
- 2-5 тегов, по-русски, без пробелов (используй _).
- НЕ создавай теги вида time: — для дат есть отдельные поля.
- event_date/event_time: если в тексте есть дата/время события (завтра, в пятницу, 5-го, в 10:00) — разреши их в абсолютные относительно «сейчас». Нет даты события — null.

Только JSON, без пояснений."""
    data = _parse_json(_complete(system, text, max_tokens=800, json_mode=False))
    return {
        "tags": data.get("tags") if isinstance(data.get("tags"), list) else [],
        "note_type": "wish" if data.get("note_type") == "wish" else "note",
        "event_date": data.get("event_date") or None,
        "event_time": data.get("event_time") or None,
    }


def extract_search_profile(question: str, tz_name: str = None, known_tags: list = None,
                           history: list = None) -> dict:
    """Профиль поиска по вопросу: какие теги/люди/период искать. Даты-намерение, не арифметика."""
    known = ", ".join(known_tags or []) or "(пока нет)"
    system = f"""Ты строишь профиль поиска по семейной памяти из вопроса (НЕ отвечаешь на него).

Сейчас: {now_prompt_str(tz_name)}.
Существующие теги: {known}

Верни JSON:
{{
  "tags_any": ["topic:..."],   // темы, любая из которых релевантна
  "tags_all": ["type:..."],    // теги, которые должны быть все
  "people": ["имя"],           // про КОГО заметка (упомянут в тексте), нижний регистр
  "authors": ["имя"],          // от КОГО заметка / кто её писал, нижний регистр
  "note_type": "wish" или null,
  "period": "today|tomorrow|yesterday|this_week|next_week|last_week|this_month" или null,
  "date_from": "ГГГГ-ММ-ДД" или null,  // ТОЛЬКО для нестандартного периода (напр. «в мае»)
  "date_to": "ГГГГ-ММ-ДД" или null,
  "date_field": "event" | "created" | null
}}

Правила:
- note_type="wish" для вопросов о желаниях/хотелках («что хочет X», «какие желания у Y», «о чём мечтает»). Иначе null.
- people vs authors: «что у Вари», «про Борю» → people; «заметки от Тани», «что писал Андрей» → authors.
- period — для относительных дат; конкретные границы посчитает программа, ТЫ даты не вычисляешь.
- date_field: "event" для вопросов о событиях/расписании («что завтра», «когда»), "created" для «что записал вчера». null — если про даты речи нет.
- Учитывай недавний диалог: уточнения («а во сколько?», «а у Бори?») трактуй в его контексте.
- Пусто — оставляй [] или null. Только JSON, без пояснений."""
    if history:
        convo = "\n".join(
            f"{'Вопрос' if m['role'] == 'user' else 'Ответ'}: {m['content']}"
            for m in history[-4:]
        )
        user_content = f"Недавний диалог:\n{convo}\n\nТекущий вопрос: {question}"
    else:
        user_content = question
    data = _parse_json(_complete(system, user_content, max_tokens=600, json_mode=False))
    return {
        "tags_any": data.get("tags_any") if isinstance(data.get("tags_any"), list) else [],
        "tags_all": data.get("tags_all") if isinstance(data.get("tags_all"), list) else [],
        "people": data.get("people") if isinstance(data.get("people"), list) else [],
        "authors": data.get("authors") if isinstance(data.get("authors"), list) else [],
        "note_type": "wish" if data.get("note_type") == "wish" else None,
        "period": data.get("period") or None,
        "date_from": data.get("date_from") or None,
        "date_to": data.get("date_to") or None,
        "date_field": data.get("date_field") or None,
    }


def ask_claude(question: str, public_context: str, asker_name: str, tz_name: str = None,
               history: list = None) -> str:
    """Ответ по памяти семьи с учётом недавнего диалога (follow-up вопросы)."""
    current = now_prompt_str(tz_name)
    system = f"""Ты Робо — семейный AI-ассистент. Тебя спрашивает {asker_name}.

Сейчас: {current}. Используй это, чтобы понимать «сегодня», «вчера», «на этой неделе», «в выходные», «в этом месяце» и подобное.

Ниже — заметки семьи (общая память, все видят всё).
Каждая строка начинается с метки времени создания в формате [ГГГГ-ММ-ДД ЧЧ:ММ], затем имя автора и текст.

Если в вопросе есть указание на время (сегодня, вчера, на прошлой неделе, в мае...) и/или автора (от Тани, что писал Андрей), отбирай только подходящие заметки: сравнивай их метки времени с текущей датой и сопоставляй имя автора.
Отвечай на русском языке, кратко и по делу.
Если подходящих заметок нет — честно скажи об этом, не выдумывай.

=== ПАМЯТЬ СЕМЬИ ===
{public_context}
===================="""
    messages = list(history or []) + [{"role": "user", "content": question}]
    return _chat(system, messages, max_tokens=1000)
