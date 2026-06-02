from telegram import Update
from telegram.ext import ContextTypes

from core.auth import is_allowed
from core.memory import get_member_name, load_memory, save_memory


async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory = load_memory()
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(memory, user_id):
        await update.message.reply_text("Сначала напиши /start")
        return
    if not memory["notes"]:
        await update.message.reply_text("Заметок пока нет.")
        return

    lines = ["📋 *Все заметки семьи:*\n"]
    for note in memory["notes"][-20:]:
        ts = note["timestamp"][:16].replace("T", " ")
        tags_str = " ".join([f"#{t}" for t in note["tags"]])
        lines.append(f"*{note['author']}* [{ts}]\n{note['text']}\n{tags_str}")

    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n_(показаны последние записи)_"
    await update.message.reply_text(text, parse_mode="Markdown")


async def members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory = load_memory()
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not memory["members"]:
        await update.message.reply_text("Пока никто не зарегистрирован.")
        return

    names = [m["name"] for m in memory["members"].values()]
    await update.message.reply_text(
        "👨‍👩‍👧‍👦 *Члены семьи:*\n" + "\n".join([f"• {n}" for n in names]),
        parse_mode="Markdown",
    )


async def clear_my_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory = load_memory()
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(memory, user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    before = len(memory["notes"])
    memory["notes"] = [n for n in memory["notes"] if n["author_id"] != str(user_id)]
    save_memory(memory)
    await update.message.reply_text(f"🗑 Удалено {before - len(memory['notes'])} твоих заметок.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Робо — семейный помощник*\n\n"
        "*Просто пиши в свободной форме:*\n"
        "• Заметка → сохраню и отмечу тегом\n"
        "• Вопрос → отвечу на основе памяти семьи\n\n"
        "*Команды:*\n"
        "/start — регистрация\n"
        "/notes — все заметки\n"
        "/members — кто в боте\n"
        "/clear — удалить свои заметки\n"
        "/help — эта справка",
        parse_mode="Markdown",
    )
