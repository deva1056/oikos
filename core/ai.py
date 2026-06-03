import json
import os

from core.timeutils import now_prompt_str

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


def classify_and_tag(text: str) -> dict:
    system = """Ты помощник для классификации сообщений семейного бота.

Определи тип сообщения и верни JSON строго в таком формате:
{
  "type": "note" или "question",
  "tags": ["тег1", "тег2"]
}

Возможные теги: кафе, ресторан, здоровье, врач, подарки, кино, фильмы, расписание, планы, покупки, отпуск, прочее

Вопросы — это сообщения, начинающиеся с вопросительных слов (что, где, когда, есть ли, можно ли и т.д.) или заканчивающиеся на "?".
Всё остальное — заметки.

Верни ТОЛЬКО JSON, без пояснений."""
    raw = _complete(system, text, max_tokens=300, json_mode=True)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"type": "note", "tags": ["прочее"]}


def ask_claude(question: str, public_context: str, asker_name: str, tz_name: str = None) -> str:
    """Answer question based on ONLY public context. (Имя историческое — провайдер задаётся LLM_PROVIDER.)"""
    current = now_prompt_str(tz_name)
    system = f"""Ты Робо — семейный AI-ассистент. Тебя спрашивает {asker_name}.

Сейчас: {current}. Используй это, чтобы понимать «сегодня», «вчера», «на этой неделе», «в выходные», «в этом месяце» и подобное.

Ниже — публичные заметки семьи (что люди согласились показать всем).
Каждая строка начинается с метки времени создания в формате [ГГГГ-ММ-ДД ЧЧ:ММ], затем имя автора и текст.

Если в вопросе есть указание на время (сегодня, вчера, на прошлой неделе, в мае...) и/или автора (от Тани, что писал Андрей), отбирай только подходящие заметки: сравнивай их метки времени с текущей датой и сопоставляй имя автора.
Отвечай на русском языке, кратко и по делу.
Если подходящих заметок нет — честно скажи об этом, не выдумывай.

=== ПУБЛИЧНАЯ ПАМЯТЬ СЕМЬИ ===
{public_context}
================================="""
    return _complete(system, question, max_tokens=1000)
