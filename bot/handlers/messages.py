import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.ai import ask_claude, classify_and_tag
from core.auth import is_allowed
from core.memory import add_note, format_for_ai, get_member_name, load_memory

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory = load_memory()
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    author_name = get_member_name(memory, user_id)
    if not author_name:
        await update.message.reply_text("Сначала напиши /start")
        return

    text = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    result = classify_and_tag(text)
    msg_type = result.get("type", "note")
    tags = result.get("tags", ["прочее"])

    if msg_type == "question":
        memory_text = format_for_ai(memory)
        answer = ask_claude(text, memory_text, author_name)
        await update.message.reply_text(answer)
    else:
        note = add_note(memory, user_id, author_name, text, tags)
        tags_display = " ".join([f"#{t}" for t in tags])
        await update.message.reply_text(f"✅ Запомнил!\n{tags_display}")
        logger.info(f"Заметка #{note['id']} от {author_name}: {text[:50]}...")
