"""/t_cz и /t_eng — карманный переводчик под уровень ученика.

Текст берётся после команды либо (если его нет) из сообщения, на которое
ответили командой — удобно для пересланных сообщений преподавателя.
"""
import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.auth import is_allowed
from core.memory import get_member_name
from core.translate import phrase_hint, translate

logger = logging.getLogger(__name__)

LLM_ERROR = "⚠️ Не получилось обратиться к ИИ, попробуй ещё раз чуть позже."

MAX_LEN = 1000  # утилита для фраз, не для документов

_USAGE = {
    "cz": "Пришли текст: /t_cz Мне нужно продлить проездной\n"
          "Или ответь командой /t_cz на сообщение, которое перевести.",
    "eng": "Пришли текст: /t_eng Мне нужно перенести встречу\n"
           "Или ответь командой /t_eng на сообщение, которое перевести.",
}


async def _run_llm(fn, *args):
    """LLM-вызов в потоке, не роняющий хендлер. Логируем тип ошибки — НЕ текст."""
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as e:  # noqa: BLE001 — намеренно широко, чтобы бот не падал
        logger.error("LLM call failed (%s): %s: %s", fn.__name__, type(e).__name__, e)
        return None


def extract_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Текст после команды; если его нет — текст reply-сообщения (или его подпись)."""
    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message.reply_to_message:
        src = update.message.reply_to_message
        text = (src.text or src.caption or "").strip()
    return text


async def _translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE, target: str):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    text = extract_text(update, context)
    if not text:
        await update.message.reply_text(_USAGE[target])
        return
    if len(text) > MAX_LEN:
        await update.message.reply_text("Слишком длинный текст, пришли кусок покороче.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    result = await _run_llm(translate, text, target)
    if result is None:
        await update.message.reply_text(LLM_ERROR)
        return

    # подсказка про словарь — только для коротких ru→cz (словарь чешский)
    if target == "cz":
        hint = phrase_hint(text, result)
        if hint:
            result = f"{result}\n\n{hint}"
    await update.message.reply_text(result)


async def t_cz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _translate_command(update, context, "cz")


async def t_eng_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _translate_command(update, context, "eng")
