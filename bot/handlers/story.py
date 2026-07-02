"""/story — тренировочные истории на чешском (уровень A2, подготовка к trvalý pobyt).

Режимы: фото с подписью /story (история по картинке), /story weather good|bad,
/story about_me <запрос> (пересказ своей заметки с тегом cz от первого лица).
"""
import asyncio
import base64
import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.auth import is_allowed
from core.memory import _parse_tags, get_member_name, get_member_timezone
from core.story import (
    find_note_for_story,
    generate_story_about_me,
    generate_story_from_image,
    generate_story_weather,
    get_cz_note_tags,
    parse_about_me_query,
    pick_vocab,
)

logger = logging.getLogger(__name__)

LLM_ERROR = "⚠️ Не получилось обратиться к ИИ, попробуй ещё раз чуть позже."

HELP_TEXT = (
    "🇨🇿 /story — тренировочные истории на чешском (уровень A2)\n\n"
    "• Пришли фото с подписью /story — составлю историю по картинке\n"
    "• /story weather good — история про хорошую погоду\n"
    "• /story weather bad — история про плохую погоду\n"
    "• /story about_me [запрос] — перескажу твою заметку с тегом #cz\n"
    "  (например: /story about_me вчера тренировка)"
)


async def _run_llm(fn, *args):
    """LLM-вызов в потоке, не роняющий хендлер. Логируем тип ошибки — НЕ содержимое."""
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as e:  # noqa: BLE001 — намеренно широко, чтобы бот не падал
        logger.error("LLM call failed (%s): %s: %s", fn.__name__, type(e).__name__, e)
        return None


def parse_story_args(args: list) -> tuple:
    """Роутинг аргументов /story, прощающий опечатки (wether/weater, g/b по префиксу).

    Возвращает ("help", None) | ("weather", "good"|"bad") | ("about_me", запрос).
    """
    if not args:
        return ("help", None)
    first = args[0].lower()
    if first.startswith("we"):
        kind = args[1].lower() if len(args) > 1 else ""
        if kind.startswith("g"):
            return ("weather", "good")
        if kind.startswith("b"):
            return ("weather", "bad")
        return ("help", None)
    if first.startswith("about"):
        return ("about_me", " ".join(args[1:]).strip())
    return ("help", None)


async def _ensure_member(update: Update) -> str:
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Нет доступа.")
        return None
    if not get_member_name(user_id):
        await update.message.reply_text("Сначала напиши /start")
        return None
    return user_id


async def story_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await _ensure_member(update)
    if not user_id:
        return

    mode, arg = parse_story_args(context.args or [])
    if mode == "help":
        await update.message.reply_text(HELP_TEXT)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    if mode == "weather":
        story = await _run_llm(generate_story_weather, arg)
        await update.message.reply_text(story if story else LLM_ERROR)
        return

    # about_me
    tz = get_member_timezone(user_id)
    if arg:
        parsed = await _run_llm(parse_about_me_query, arg, tz)
        if parsed is None:
            await update.message.reply_text(LLM_ERROR)
            return
    else:
        parsed = {"selector": "latest", "date": None, "tags": []}

    note = find_note_for_story(user_id, parsed, tz)
    if not note:
        tags = get_cz_note_tags(user_id, tz)
        hint = (
            "\n\nТеги твоих cz-заметок: " + "  ".join(f"#{t} ({c})" for t, c in tags)
            if tags else
            "\n\nПока нет ни одной заметки с тегом #cz — добавь тег через /addtag."
        )
        await update.message.reply_text("Не нашёл заметок с тегом cz под этот запрос." + hint)
        return

    vocab = pick_vocab(user_id, _parse_tags(note["tags"]))
    story = await _run_llm(generate_story_about_me, note["text"], vocab or None)
    await update.message.reply_text(story if story else LLM_ERROR)


async def story_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Фото с подписью /story → история по картинке. Изображение только в памяти."""
    user_id = await _ensure_member(update)
    if not user_id:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    photo = update.message.photo[-1]  # максимальное разрешение
    tg_file = await photo.get_file()
    data = await tg_file.download_as_bytearray()
    image_b64 = base64.b64encode(bytes(data)).decode("ascii")

    vocab = pick_vocab(user_id)
    story = await _run_llm(generate_story_from_image, image_b64, vocab or None)
    await update.message.reply_text(story if story else LLM_ERROR)
