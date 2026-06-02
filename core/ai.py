import json
import os

from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-5"


def classify_and_tag(text: str) -> dict:
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system="""Ты помощник для классификации сообщений семейного бота.

Определи тип сообщения и верни JSON строго в таком формате:
{
  "type": "note" или "question",
  "tags": ["тег1", "тег2"]
}

Возможные теги: кафе, ресторан, здоровье, врач, подарки, кино, фильмы, расписание, планы, покупки, отпуск, прочее

Вопросы — это сообщения, начинающиеся с вопросительных слов (что, где, когда, есть ли, можно ли и т.д.) или заканчивающиеся на "?".
Всё остальное — заметки.

Верни ТОЛЬКО JSON, без пояснений.""",
        messages=[{"role": "user", "content": text}],
    )
    raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"type": "note", "tags": ["прочее"]}


def ask_claude(question: str, memory_text: str, asker_name: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=f"""Ты Робо — семейный AI-ассистент. Тебя спрашивает {asker_name}.

Ниже — все заметки семьи (от всех её членов) в хронологическом порядке.
Отвечай на русском языке, кратко и по делу.
Если информации нет — честно скажи об этом.
Если спрашивают о расписании — обращай внимание на даты и времена в заметках.

=== СЕМЕЙНАЯ ПАМЯТЬ ===
{memory_text}
=======================""",
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text.strip()
