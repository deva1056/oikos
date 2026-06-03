import json
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.ai import ask_claude, classify_and_tag, generate_interpretation
from core.auth import is_allowed
from core.memory import add_note, get_member_name, get_member_timezone, get_public_context

logger = logging.getLogger(__name__)

CONFIRMING_INTERPRETATION = 2


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    author_name = get_member_name(user_id)
    if not author_name:
        await update.message.reply_text("Сначала напиши /start")
        return

    text = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    result = classify_and_tag(text)
    msg_type = result.get("type", "note")
    tags = result.get("tags", ["прочее"])

    if msg_type == "question":
        asker_tz = get_member_timezone(user_id)
        public_context = get_public_context(asker_tz)
        answer = ask_claude(text, public_context, author_name, asker_tz)
        await update.message.reply_text(answer)
    else:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        interpretation = generate_interpretation(text)

        keyboard = [
            [
                InlineKeyboardButton("🔒 Только я", callback_data=f"vis_private_{user_id}"),
                InlineKeyboardButton("👥 Показать суть", callback_data=f"vis_interp_{user_id}"),
            ],
            [InlineKeyboardButton("🌐 Показать всё", callback_data=f"vis_public_{user_id}")],
        ]

        context.user_data["pending_note"] = {
            "private_text": text,
            "interpretation": interpretation,
            "tags": tags,
            "author_id": user_id,
            "author_name": author_name,
        }

        await update.message.reply_text(
            f"✏️ Интерпретирую как:\n*{interpretation}*\n\nКак сохранить?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )


async def save_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get("pending_note")
    if not pending:
        await query.edit_message_text("⏰ Время истекло, напиши заметку заново")
        return

    callback_data = query.data
    if callback_data.startswith("vis_private_"):
        visibility = "private"
        public_interp = None
        public_text = None
    elif callback_data.startswith("vis_interp_"):
        visibility = "interpretation"
        public_interp = pending["interpretation"]
        public_text = None
    elif callback_data.startswith("vis_public_"):
        visibility = "public"
        public_interp = pending["interpretation"]
        public_text = pending["private_text"]
    else:
        await query.edit_message_text("❌ Ошибка")
        return

    note = add_note(
        user_id=pending["author_id"],
        author_name=pending["author_name"],
        private_text=pending["private_text"],
        tags=pending["tags"],
        visibility=visibility,
        interpretation=public_interp,
        public_text=public_text,
    )

    tags_display = " ".join([f"#{t}" for t in pending["tags"]])
    await query.edit_message_text(f"✅ Сохранена!\n{tags_display}")
    logger.info(f"Заметка #{note['id']} от {pending['author_name']}: {pending['private_text'][:50]}...")

    del context.user_data["pending_note"]
