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


def generate_interpretation(private_text: str) -> str:
    """Generate a delicate, public-safe interpretation of private text."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=100,
        system="""Ты помощник для семейного бота. Твоя задача — переформулировать заметку в безопасную версию.

Правила:
- Скрывай интимные/личные детали
- Сохраняй суть (о чём заметка)
- Используй общие, деликатные формулировки
- 1-2 короткие фразы
- Отвечай ТОЛЬКО переформулировкой, без пояснений""",
        messages=[{"role": "user", "content": private_text}],
    )
    return response.content[0].text.strip()


def ask_claude(question: str, public_context: str, asker_name: str) -> str:
    """Answer question based on ONLY public context."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=f"""Ты Робо — семейный AI-ассистент. Тебя спрашивает {asker_name}.

Ниже — публичные заметки семьи (что люди согласились показать всем).
Отвечай на русском языке, кратко и по делу.
Если информации нет — честно скажи об этом.
Если спрашивают о расписании — обращай внимание на даты и времена.

=== ПУБЛИЧНАЯ ПАМЯТЬ СЕМЬИ ===
{public_context}
=================================""",
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text.strip()
