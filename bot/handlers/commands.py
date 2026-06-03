from zoneinfo import ZoneInfo

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.auth import is_allowed
from core.memory import (
    delete_user_notes,
    get_all_members,
    get_member_name,
    get_member_timezone,
    get_user_notes,
    set_member_timezone,
)
from core.timeutils import now_prompt_str

from bot.handlers._send import safe_reply


def location_keyboard() -> ReplyKeyboardMarkup:
    """One-tap 'share location' keyboard used for timezone detection."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    # Manual override: /timezone Europe/Berlin
    if context.args:
        tz = context.args[0].strip()
        try:
            ZoneInfo(tz)
        except Exception:
            await update.message.reply_text(
                "Не знаю такую таймзону. Нужно название в формате IANA, например:\n"
                "/timezone Europe/Moscow\n/timezone Asia/Yekaterinburg"
            )
            return
        set_member_timezone(user_id, tz)
        await update.message.reply_text(f"✅ Таймзона: {tz}\nСейчас у тебя {now_prompt_str(tz)}.")
        return

    current = get_member_timezone(user_id)
    cur_txt = f"Текущая таймзона: *{current}*" if current else "Таймзона пока не задана."
    await safe_reply(
        update.message,
        f"🕒 {cur_txt}\n\n"
        "Отправь геолокацию кнопкой ниже — определю автоматически.\n"
        "Или задай вручную: /timezone Europe/Berlin",
        reply_markup=location_keyboard(),
        parse_mode="Markdown",
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

    lines = ["📝 Твои заметки:\n"]
    for note in notes:
        lines.append(f"• {note['text']}")

    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n(показаны последние записи)"
    await update.message.reply_text(text)


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
        "👨‍👩‍👧‍👦 Члены семьи:\n" + "\n".join([f"• {m}" for m in members_list]),
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
    await safe_reply(
        update.message,
        "🤖 *Робо — семейный помощник*\n\n"
        "*Просто пиши в свободной форме:*\n"
        "• Заметка → вместе доведём формулировку в диалоге, потом сохранишь\n"
        "• Вопрос → отвечу на основе памяти семьи\n\n"
        "*Во время черновика:* пиши правки словами, затем 💾 Сохранить или ❌ Отмена\n\n"
        "*Команды:*\n"
        "/start — регистрация\n"
        "/note <текст> — начать заметку\n"
        "/ask <вопрос> — спросить память\n"
        "/notes — все твои заметки\n"
        "/members — кто в боте\n"
        "/timezone — задать таймзону (для «сегодня/вчера»)\n"
        "/clear — удалить все свои заметки\n"
        "/help — эта справка",
        parse_mode="Markdown",
    )
