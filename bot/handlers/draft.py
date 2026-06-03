import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.handlers._send import safe_reply
from core.ai import ask_claude, classify_and_tag, refine_draft
from core.auth import is_allowed
from core.memory import (
    add_note,
    get_member_name,
    get_member_timezone,
    get_public_context,
)

logger = logging.getLogger(__name__)

DRAFTING = 1


# ---------- helpers ----------

def _draft_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💾 Сохранить", callback_data="draft_save"),
                InlineKeyboardButton("❌ Отмена", callback_data="draft_cancel"),
            ],
            [InlineKeyboardButton("❓ Это был вопрос", callback_data="draft_was_q")],
        ]
    )


async def _ensure_member(update: Update) -> str:
    """Вернёт имя автора или None (и отправит подсказку), если доступа/регистрации нет."""
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return None
    name = get_member_name(user_id)
    if not name:
        await update.message.reply_text("Сначала напиши /start")
        return None
    return name


async def _answer_question(update: Update, text: str, author_name: str):
    user_id = str(update.effective_user.id)
    tz = get_member_timezone(user_id)
    context_text = get_public_context(tz)
    answer = ask_claude(text, context_text, author_name, tz)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✍️ Я хотел записать это", callback_data="draft_from_q")]]
    )
    await update.message.reply_text(answer, reply_markup=keyboard)


async def _start_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, seed_text: str) -> int:
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    messages = [{"role": "user", "content": seed_text}]
    draft = refine_draft(messages)
    messages.append({"role": "assistant", "content": draft})
    context.user_data["draft"] = {"messages": messages, "text": draft}

    await update.message.reply_text(
        f"✏️ Черновик заметки:\n\n{draft}\n\nПоправь словами или сохрани.",
        reply_markup=_draft_keyboard(),
    )
    return DRAFTING


# ---------- entry points ----------

async def route_first_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Первое сообщение: вопрос → ответ (variant A), утверждение → черновик."""
    author_name = await _ensure_member(update)
    if not author_name:
        return ConversationHandler.END

    text = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    if classify_and_tag(text).get("type") == "question":
        context.user_data["last_question"] = text
        await _answer_question(update, text, author_name)
        return ConversationHandler.END

    return await _start_draft(update, context, text)


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Override: /note <текст> — сразу черновик, без классификации."""
    author_name = await _ensure_member(update)
    if not author_name:
        return ConversationHandler.END

    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Напиши текст после команды: /note <что записать>")
        return ConversationHandler.END

    return await _start_draft(update, context, text)


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Override: /ask <вопрос> — сразу ответ из памяти, в черновик не входим."""
    author_name = await _ensure_member(update)
    if not author_name:
        return ConversationHandler.END

    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Напиши вопрос после команды: /ask <вопрос>")
        return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    context.user_data["last_question"] = text
    await _answer_question(update, text, author_name)
    return ConversationHandler.END


async def draft_from_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Кнопка [✍️ Я хотел записать это] под ответом — старт черновика из текста вопроса."""
    query = update.callback_query
    await query.answer()

    seed = context.user_data.get("last_question")
    if not seed:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Не нашёл, что записать — просто напиши заметку заново.")
        return ConversationHandler.END

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    messages = [{"role": "user", "content": seed}]
    draft = refine_draft(messages)
    messages.append({"role": "assistant", "content": draft})
    context.user_data["draft"] = {"messages": messages, "text": draft}
    await query.message.reply_text(
        f"✏️ Черновик заметки:\n\n{draft}\n\nПоправь словами или сохрани.",
        reply_markup=_draft_keyboard(),
    )
    return DRAFTING


# ---------- DRAFTING state ----------

async def refine_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Внутри черновика любой текст = правка."""
    draft_state = context.user_data.get("draft")
    if not draft_state:
        # сессия потерялась (например, рестарт бота) — выходим
        await update.message.reply_text("Черновик потерялся, напиши заметку заново.")
        return ConversationHandler.END

    instruction = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    draft_state["messages"].append({"role": "user", "content": instruction})
    draft = refine_draft(draft_state["messages"])
    draft_state["messages"].append({"role": "assistant", "content": draft})
    draft_state["text"] = draft

    await update.message.reply_text(
        f"✏️ Черновик заметки:\n\n{draft}\n\nПоправь словами или сохрани.",
        reply_markup=_draft_keyboard(),
    )
    return DRAFTING


async def save_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Коммит финального текста в БД. Срабатывает и от кнопки, и от /save."""
    query = update.callback_query
    if query:
        await query.answer()

    draft_state = context.user_data.get("draft")
    if not draft_state or not draft_state.get("text"):
        msg = "Нет активного черновика."
        if query:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    author_name = get_member_name(user_id)
    text = draft_state["text"]
    tags = classify_and_tag(text).get("tags", ["прочее"])

    note = add_note(user_id=user_id, author_name=author_name, text=text, tags=tags)
    context.user_data.pop("draft", None)
    logger.info(f"Заметка #{note['id']} сохранена через диалог")

    tags_display = " ".join(f"#{t}" for t in tags)
    confirmation = f"✅ Сохранено!\n\n{text}\n\n{tags_display}"
    if query:
        await query.edit_message_text(confirmation)
    else:
        await update.message.reply_text(confirmation)
    return ConversationHandler.END


async def cancel_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
    context.user_data.pop("draft", None)
    msg = "❌ Черновик отменён."
    if query:
        await query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)
    return ConversationHandler.END


async def draft_was_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Кнопка [❓ Это был вопрос] — отменяем черновик и отвечаем на исходный текст."""
    query = update.callback_query
    await query.answer()

    draft_state = context.user_data.pop("draft", None)
    await query.edit_message_reply_markup(reply_markup=None)

    if not draft_state or not draft_state.get("messages"):
        await query.message.reply_text("Не нашёл исходный текст — задай вопрос заново.")
        return ConversationHandler.END

    seed = draft_state["messages"][0]["content"]
    user_id = str(update.effective_user.id)
    author_name = get_member_name(user_id)
    tz = get_member_timezone(user_id)
    answer = ask_claude(seed, get_public_context(tz), author_name, tz)
    await query.message.reply_text(answer)
    return ConversationHandler.END
