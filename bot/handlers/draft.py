import asyncio
import logging
import re
from datetime import date as _date, time as _time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from core.ai import ask_claude, extract_note_metadata, refine_draft
from core.auth import is_allowed
from core.memory import (
    add_note,
    get_all_tags,
    get_member_name,
    get_member_timezone,
    get_note,
    normalize_tag,
    update_note,
)
from core.retrieval import get_relevant_context

from bot.handlers.session import get_turns, remember_turn

logger = logging.getLogger(__name__)

DRAFTING = 1

LLM_ERROR = "⚠️ Не получилось обратиться к ИИ, попробуй ещё раз чуть позже."

# Эвристика «вопрос или заметка» на горячем пути — без лишнего LLM-вызова.
# Ошибки маршрутизации обратимы в один тап (variant A).
_QUESTION_WORDS = {
    "что", "где", "когда", "кто", "почему", "зачем", "как", "сколько",
    "какой", "какая", "какие", "какое", "чей", "куда", "откуда",
}

# императивы-запросы: «покажи/выведи заметки …» — это поиск, не заметка
_COMMAND_WORDS = {
    "покажи", "покажите", "выведи", "выведите", "найди", "найдите",
    "перечисли", "перечислите", "скинь", "дай", "список", "ищи", "поищи",
}


def looks_like_question(text: str) -> bool:
    t = text.strip().lower()
    if t.endswith("?"):
        return True
    words = t.split()
    return bool(words) and words[0] in (_QUESTION_WORDS | _COMMAND_WORDS)


async def _run_llm(fn, *args):
    """LLM-вызов в потоке, не роняющий хендлер. Логируем тип ошибки — НЕ текст пользователя."""
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as e:  # noqa: BLE001 — намеренно широко, чтобы бот не падал
        logger.error("LLM call failed (%s): %s: %s", fn.__name__, type(e).__name__, e)
        return None


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


def _draft_message(draft: str) -> str:
    return f"✏️ Черновик заметки:\n\n{draft}\n\nПоправь словами или сохрани."


def _owns_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Защита-в-глубину: черновик принадлежит тому, кто его создал."""
    draft = context.user_data.get("draft")
    return bool(draft) and draft.get("owner_id") == update.effective_user.id


async def _ensure_member(update: Update) -> str:
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return None
    name = get_member_name(user_id)
    if not name:
        await update.message.reply_text("Сначала напиши /start")
        return None
    return name


def _parse_date(s):
    try:
        return _date.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


def _parse_time(s):
    if not s:
        return None
    try:
        parts = [int(x) for x in str(s).split(":")]
        return _time(parts[0], parts[1] if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        return None


async def _answer_question(message, user_id: str, text: str, author_name: str, context):
    tz = get_member_timezone(user_id)
    history = get_turns(context)
    try:
        context_text = await asyncio.to_thread(get_relevant_context, text, tz, history)
    except Exception as e:  # noqa: BLE001
        logger.error("retrieval failed: %s", type(e).__name__)
        context_text = "Заметок пока нет."
    answer = await _run_llm(ask_claude, text, context_text, author_name, tz, history)
    if answer is None:
        await message.reply_text(LLM_ERROR)
        return
    remember_turn(context, text, answer)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✍️ Я хотел записать это", callback_data="draft_from_q")]]
    )
    await message.reply_text(answer, reply_markup=keyboard)


async def _begin_draft(message, chat_id, context, seed_text, author_name, owner_id) -> bool:
    """Сгенерировать первый черновик и положить состояние. False — если LLM не ответил."""
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    messages = [{"role": "user", "content": seed_text}]
    draft = await _run_llm(refine_draft, messages)
    if draft is None:
        await message.reply_text(LLM_ERROR)
        return False
    messages.append({"role": "assistant", "content": draft})
    context.user_data["draft"] = {
        "messages": messages,
        "text": draft,
        "author_name": author_name,
        "owner_id": owner_id,
    }
    await message.reply_text(_draft_message(draft), reply_markup=_draft_keyboard())
    return True


# ---------- entry points ----------

async def route_first_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    author_name = await _ensure_member(update)
    if not author_name:
        return ConversationHandler.END

    text = update.message.text.strip()
    user_id = str(update.effective_user.id)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    if looks_like_question(text):
        context.user_data["last_question"] = text
        await _answer_question(update.message, user_id, text, author_name, context)
        return ConversationHandler.END

    ok = await _begin_draft(
        update.message, update.effective_chat.id, context, text, author_name, update.effective_user.id
    )
    return DRAFTING if ok else ConversationHandler.END


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    author_name = await _ensure_member(update)
    if not author_name:
        return ConversationHandler.END

    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Напиши текст после команды: /note <что записать>")
        return ConversationHandler.END

    ok = await _begin_draft(
        update.message, update.effective_chat.id, context, text, author_name, update.effective_user.id
    )
    return DRAFTING if ok else ConversationHandler.END


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    author_name = await _ensure_member(update)
    if not author_name:
        return ConversationHandler.END

    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Напиши вопрос после команды: /ask <вопрос>")
        return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    context.user_data["last_question"] = text
    await _answer_question(update.message, str(update.effective_user.id), text, author_name, context)
    return ConversationHandler.END


async def draft_from_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    seed = context.user_data.get("last_question")
    if not seed:
        await query.message.reply_text("Не нашёл, что записать — просто напиши заметку заново.")
        return ConversationHandler.END

    author_name = get_member_name(str(update.effective_user.id))
    ok = await _begin_draft(
        query.message, query.message.chat_id, context, seed, author_name, update.effective_user.id
    )
    return DRAFTING if ok else ConversationHandler.END


async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/edit_<id> — открыть заметку как черновик и править её в том же диалоге."""
    author_name = await _ensure_member(update)
    if not author_name:
        return ConversationHandler.END

    m = re.match(r"^/edit_(\d+)", update.message.text.strip())
    if not m:
        return ConversationHandler.END
    note_id = int(m.group(1))

    note = get_note(note_id)
    if not note or note["author_id"] != str(update.effective_user.id):
        await update.message.reply_text("Это не твоя заметка или её нет.")
        return ConversationHandler.END

    context.user_data["draft"] = {
        "messages": [{"role": "assistant", "content": note["text"]}],
        "text": note["text"],
        "author_name": author_name,
        "owner_id": update.effective_user.id,
        "editing_id": note_id,
    }
    await update.message.reply_text(
        f"✏️ Редактируем заметку #{note_id}:\n\n{note['text']}\n\nНапиши правки словами или сохрани.",
        reply_markup=_draft_keyboard(),
    )
    return DRAFTING


# ---------- DRAFTING state ----------

async def refine_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _owns_draft(update, context):
        await update.message.reply_text("Черновик потерялся, напиши заметку заново.")
        return ConversationHandler.END

    draft_state = context.user_data["draft"]
    instruction = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    draft_state["messages"].append({"role": "user", "content": instruction})
    draft = await _run_llm(refine_draft, draft_state["messages"])
    if draft is None:
        draft_state["messages"].pop()  # откатываем неудавшуюся реплику
        await update.message.reply_text(LLM_ERROR)
        return DRAFTING
    draft_state["messages"].append({"role": "assistant", "content": draft})
    draft_state["text"] = draft

    await update.message.reply_text(_draft_message(draft), reply_markup=_draft_keyboard())
    return DRAFTING


async def save_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()

    if not _owns_draft(update, context):
        msg = "Нет активного черновика."
        await (query.edit_message_text(msg) if query else update.message.reply_text(msg))
        return ConversationHandler.END

    draft_state = context.user_data["draft"]
    text = draft_state["text"]
    user_id = str(update.effective_user.id)
    author_name = draft_state.get("author_name") or get_member_name(user_id)

    tz = get_member_timezone(user_id)
    known_tags = [t for t, _ in get_all_tags()]
    meta = await _run_llm(extract_note_metadata, text, tz, known_tags, author_name) or {}
    tags = [t for t in (normalize_tag(t) for t in meta.get("tags", [])) if t] or ["прочее"]
    event_date = _parse_date(meta.get("event_date"))
    event_time = _parse_time(meta.get("event_time"))

    editing_id = draft_state.get("editing_id")
    if editing_id:
        update_note(editing_id, user_id, text, tags, event_date, event_time)
        logger.info("Заметка #%s обновлена через диалог", editing_id)
        head = f"✏️ Обновлено #{editing_id}!"
    else:
        note = add_note(
            user_id=user_id,
            author_name=author_name,
            text=text,
            tags=tags,
            event_date=event_date,
            event_time=event_time,
        )
        logger.info(f"Заметка #{note['id']} сохранена через диалог")
        head = "✅ Сохранено!"
    context.user_data.pop("draft", None)

    tags_display = " ".join(f"#{t}" for t in tags)
    when = f"\n🗓 {event_date}" + (f" {event_time}" if event_time else "") if event_date else ""
    confirmation = f"{head}\n\n{text}\n\n{tags_display}{when}"
    await (query.edit_message_text(confirmation) if query else update.message.reply_text(confirmation))
    return ConversationHandler.END


async def cancel_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
    context.user_data.pop("draft", None)
    msg = "❌ Черновик отменён."
    await (query.edit_message_text(msg) if query else update.message.reply_text(msg))
    return ConversationHandler.END


async def draft_was_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    if not _owns_draft(update, context):
        await query.message.reply_text("Не нашёл исходный текст — задай вопрос заново.")
        return ConversationHandler.END

    draft_state = context.user_data.pop("draft")
    seed = draft_state["messages"][0]["content"]
    user_id = str(update.effective_user.id)
    author_name = draft_state.get("author_name") or get_member_name(user_id)
    context.user_data["last_question"] = seed
    await _answer_question(query.message, user_id, seed, author_name, context)
    return ConversationHandler.END
