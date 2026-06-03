import json
from zoneinfo import ZoneInfo

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.auth import is_allowed
from core.memory import (
    add_tag_to_note,
    delete_user_notes,
    get_all_members,
    get_all_tags,
    get_member_name,
    get_member_timezone,
    get_note,
    get_notes_by_tag,
    get_user_notes,
    set_member_timezone,
)
from core.timeutils import format_dt, now_prompt_str

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
        tags = json.loads(note["tags"]) if note.get("tags") else []
        tag_str = " ".join(f"#{t}" for t in tags)
        lines.append(f"#{note['id']} {note['text']}" + (f"\n{tag_str}" if tag_str else ""))

    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n(показаны последние записи)"
    await update.message.reply_text(text)


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    tags = get_all_tags()
    if not tags:
        await update.message.reply_text("Тегов пока нет.")
        return

    body = "  ".join(f"#{t} ({c})" for t, c in tags)
    await update.message.reply_text(
        f"🏷 Теги семьи:\n\n{body}\n\nЗаметки по тегу: /tag <тег>"
    )


async def tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    if not context.args:
        await update.message.reply_text("Укажи тег: /tag планы")
        return

    tag = context.args[0].lstrip("#")
    notes = get_notes_by_tag(tag)
    if not notes:
        await update.message.reply_text(f"Заметок с #{tag} нет.")
        return

    tz = get_member_timezone(user_id)
    lines = [f"🏷 Заметки с #{tag}:\n"]
    for n in notes:
        lines.append(f"#{n['id']} [{format_dt(n['created_at'], tz)}] {n['author_name']}: {n['text']}")
    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n(показаны последние записи)"
    await update.message.reply_text(text)


async def addtag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Формат: /addtag <id> <тег>\nID заметки видно в /notes")
        return

    try:
        note_id = int(context.args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("ID должен быть числом. Формат: /addtag <id> <тег>")
        return

    note = get_note(note_id)
    if not note:
        await update.message.reply_text(f"Заметка #{note_id} не найдена.")
        return
    if note["author_id"] != user_id:
        await update.message.reply_text("Добавлять теги можно только к своим заметкам.")
        return

    tag = context.args[1].lstrip("#")
    tags = add_tag_to_note(note_id, tag)
    tag_str = " ".join(f"#{t}" for t in tags)
    await update.message.reply_text(f"✅ Тег #{tag} добавлен к заметке #{note_id}.\nТеги: {tag_str}")


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
        "/tags — все теги семьи\n"
        "/tag <тег> — заметки с этим тегом\n"
        "/addtag <id> <тег> — добавить тег к заметке\n"
        "/members — кто в боте\n"
        "/timezone — задать таймзону (для «сегодня/вчера»)\n"
        "/clear — удалить все свои заметки\n"
        "/help — эта справка",
        parse_mode="Markdown",
    )
