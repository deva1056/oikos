import asyncio
import json
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from core.ai import extract_note_metadata
from core.auth import is_allowed
from core.memory import (
    add_tag_to_note,
    delete_user_notes,
    extract_hashtags,
    get_all_members,
    get_all_tags,
    get_member_name,
    get_member_timezone,
    get_note,
    get_notes_by_tag,
    get_user_notes,
    get_wishes,
    normalize_tag,
    remove_tag_from_note,
    set_member_timezone,
    set_note_tags,
    set_wish_status,
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
        when = ""
        if note.get("event_date"):
            when = f"\n🗓 {note['event_date']}" + (f" {note['event_time']}" if note.get("event_time") else "")
        lines.append(
            f"#{note['id']} {note['text']}{when}"
            + (f"\n{tag_str}" if tag_str else "")
            + f"\n/edit_{note['id']}"
        )

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

    tag = normalize_tag(context.args[0])
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
        await update.message.reply_text("Формат: /addtag <id> <тег> [тег ...]\nID заметки видно в /notes")
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
        await update.message.reply_text("Менять теги можно только у своих заметок.")
        return

    tags = add_tag_to_note(note_id, context.args[1:])
    tag_str = " ".join(f"#{t}" for t in tags) or "(нет)"
    await update.message.reply_text(f"✅ Теги заметки #{note_id}: {tag_str}")


async def rmtag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Формат: /rmtag <id> <тег>")
        return

    try:
        note_id = int(context.args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("ID должен быть числом. Формат: /rmtag <id> <тег>")
        return

    note = get_note(note_id)
    if not note:
        await update.message.reply_text(f"Заметка #{note_id} не найдена.")
        return
    if note["author_id"] != user_id:
        await update.message.reply_text("Менять теги можно только у своих заметок.")
        return

    tag = normalize_tag(context.args[1])
    tags = remove_tag_from_note(note_id, tag)
    tag_str = " ".join(f"#{t}" for t in tags) or "(нет)"
    await update.message.reply_text(f"🗑 Убрал #{tag}. Теги заметки #{note_id}: {tag_str}")


async def retag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перетегировать заметку заново через LLM (меняет только теги, не event_date)."""
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return

    if not context.args:
        await update.message.reply_text("Формат: /retag <id>\nID заметки видно в /notes")
        return
    try:
        note_id = int(context.args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("ID должен быть числом. Формат: /retag <id>")
        return

    note = get_note(note_id)
    if not note:
        await update.message.reply_text(f"Заметка #{note_id} не найдена.")
        return
    if note["author_id"] != user_id:
        await update.message.reply_text("Перетегировать можно только свои заметки.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    known = [t for t, _ in get_all_tags()]
    meta = await asyncio.to_thread(
        extract_note_metadata, note["text"], get_member_timezone(user_id), known, note["author_name"]
    )
    auto = [t for t in (normalize_tag(t) for t in meta.get("tags", [])) if t]
    # явные #теги в тексте заметки переживают перетегирование
    explicit = extract_hashtags(note["text"])
    tags = explicit + [t for t in auto if t not in explicit]
    if not tags:
        await update.message.reply_text("Не удалось переосмыслить теги, попробуй ещё раз.")
        return

    set_note_tags(note_id, tags)
    tag_str = " ".join(f"#{t}" for t in tags)
    await update.message.reply_text(f"🏷 Перетегировано #{note_id}: {tag_str}")


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


async def _wish_member(update: Update):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return None
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return None
    return user_id


async def wishes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _wish_member(update):
        return
    person = context.args[0] if context.args else None
    wishes = get_wishes("open", person)
    if not wishes:
        who = f" у {person}" if person else ""
        await update.message.reply_text(f"Открытых желаний{who} нет.")
        return

    header = "💭 Открытые желания" + (f" ({person})" if person else "") + ":"
    lines = [header, ""]
    buttons = []
    for w in wishes:
        lines.append(f"#{w['id']} {w['text']}")
        buttons.append([InlineKeyboardButton(f"✅ #{w['id']} {w['text'][:28]}", callback_data=f"wishdone_{w['id']}")])
    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def fulfilled_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _wish_member(update):
        return
    person = context.args[0] if context.args else None
    wishes = get_wishes("fulfilled", person)
    if not wishes:
        await update.message.reply_text("Пока ничего из желаний не отмечено сбывшимся.")
        return

    lines = ["🌟 Сбывшиеся желания" + (f" ({person})" if person else "") + ":", ""]
    for w in wishes:
        by = f" — отметил(а): {w['fulfilled_by']}" if w.get("fulfilled_by") else ""
        lines.append(f"#{w['id']} {w['text']}{by}")
    await update.message.reply_text("\n".join(lines))


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await _wish_member(update)
    if not user_id:
        return
    if not context.args:
        await update.message.reply_text("Формат: /done <id> (id видно в /wishes)")
        return
    try:
        wish_id = int(context.args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("ID должен быть числом. Формат: /done <id>")
        return
    n = set_wish_status(wish_id, "fulfilled", get_member_name(user_id))
    await update.message.reply_text(
        f"🌟 Желание #{wish_id} сбылось!" if n else f"Желание #{wish_id} не найдено."
    )


async def cancelwish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _wish_member(update):
        return
    if not context.args:
        await update.message.reply_text("Формат: /cancelwish <id>")
        return
    try:
        wish_id = int(context.args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("ID должен быть числом. Формат: /cancelwish <id>")
        return
    n = set_wish_status(wish_id, "cancelled", None)
    await update.message.reply_text(
        f"Желание #{wish_id} отменено." if n else f"Желание #{wish_id} не найдено."
    )


async def wish_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    wish_id = int(query.data.split("_")[1])
    n = set_wish_status(wish_id, "fulfilled", get_member_name(str(update.effective_user.id)))
    note = get_note(wish_id)
    text = note["text"] if note else ""
    if n:
        await query.edit_message_text(f"🌟 Сбылось: {text}\n\n(остальные — /wishes)")
    else:
        await query.answer("Не получилось отметить", show_alert=True)


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
        "/addtag <id> <тег...> — добавить тег(и) к заметке\n"
        "/rmtag <id> <тег> — убрать тег\n"
        "/retag <id> — переосмыслить теги заметки\n"
        "/edit_<id> — редактировать заметку в диалоге\n"
        "/wishes [имя] — открытые желания\n"
        "/fulfilled [имя] — сбывшиеся желания\n"
        "/done <id> — отметить желание сбывшимся\n"
        "/cancelwish <id> — отменить желание\n"
        "/story — история на чешском (A2): фото с подписью /story,\n"
        "  /story weather good|bad, /story about_me <запрос>\n"
        "/t_cz <текст> — перевод на чешский (A2) или с чешского на русский\n"
        "/t_eng <текст> — перевод на английский (A2–B1) или обратно\n"
        "/members — кто в боте\n"
        "/timezone — задать таймзону (для «сегодня/вчера»)\n"
        "/clear — удалить все свои заметки\n"
        "/help — эта справка",
        parse_mode="Markdown",
    )
