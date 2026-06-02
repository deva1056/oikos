from telegram import Update
from telegram.ext import ContextTypes

from core.auth import is_allowed
from core.memory import (
    delete_user_notes,
    get_all_members,
    get_member_name,
    get_user_notes,
)


async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    notes = get_user_notes(user_id)
    if not notes:
        await update.message.reply_text("Заметок пока нет.")
        return

    lines = ["📝 *Твои заметки:*\n"]
    for note in notes:
        if note["visibility"] == "private":
            icon = "🔒 ПРИВАТНАЯ"
            text = note["private_text"]
        elif note["visibility"] == "interpretation":
            icon = "👥 ИНТЕРПРЕТАЦИЯ"
            text = f"Суть: {note['public_interpretation']}"
        else:  # public
            icon = "🌐 ПУБЛИЧНАЯ"
            text = note["public_text"]

        lines.append(f"*{icon}*\n{text}\n/edit_{note['id']}")

    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n_(показаны последние записи)_"
    await update.message.reply_text(text, parse_mode="Markdown")


async def members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    members_list = get_all_members()
    if not members_list:
        await update.message.reply_text("Пока никто не зарегистрирован.")
        return

    await update.message.reply_text(
        "👨‍👩‍👧‍👦 *Члены семьи:*\n" + "\n".join([f"• {m}" for m in members_list]),
        parse_mode="Markdown",
    )


async def clear_my_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    notes_before = len(get_user_notes(user_id))
    delete_user_notes(user_id)
    await update.message.reply_text(f"🗑 Удалено {notes_before} твоих заметок.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Робо — семейный помощник*\n\n"
        "*Просто пиши в свободной форме:*\n"
        "• Заметка → сохраню и предложу уровень видимости\n"
        "• Вопрос → отвечу на основе памяти семьи\n\n"
        "*Команды:*\n"
        "/start — регистрация\n"
        "/notes — все твои заметки\n"
        "/members — кто в боте\n"
        "/clear — удалить все свои заметки\n"
        "/help — эта справка",
        parse_mode="Markdown",
    )
