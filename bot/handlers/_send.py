import logging

from telegram.error import BadRequest

logger = logging.getLogger(__name__)


async def safe_reply(message, text, **kwargs):
    """reply_text, устойчивый к битому Markdown.

    Если Telegram не смог разобрать разметку (например, LLM вернул
    несбалансированные * _ [ ), повторяем отправку тем же текстом, но
    без parse_mode — пользователь получает ответ, бот не падает.
    """
    try:
        return await message.reply_text(text, **kwargs)
    except BadRequest as e:
        if "parse" in str(e).lower() or "entit" in str(e).lower():
            logger.warning("Markdown parse failed, resending as plain text: %s", e)
            kwargs.pop("parse_mode", None)
            return await message.reply_text(text, **kwargs)
        raise
