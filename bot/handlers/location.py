import logging

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from bot.handlers._send import safe_reply
from core.auth import is_allowed
from core.memory import get_member_name, set_member_timezone
from core.timeutils import now_prompt_str, tz_from_coords

logger = logging.getLogger(__name__)


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detect and store member timezone from a shared location."""
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id) or not get_member_name(user_id):
        return

    loc = update.message.location
    tz = tz_from_coords(loc.latitude, loc.longitude)

    if not tz:
        await update.message.reply_text(
            "Не смог определить таймзону по геолокации 🤔\n"
            "Попробуй ещё раз или задай вручную, например: /timezone Asia/Yekaterinburg",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    set_member_timezone(user_id, tz)
    logger.info("TZ для %s определена: %s", user_id, tz)
    await safe_reply(
        update.message,
        f"📍 Готово! Твоя таймзона: *{tz}*\nСейчас у тебя {now_prompt_str(tz)}.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )
