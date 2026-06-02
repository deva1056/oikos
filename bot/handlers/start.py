import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from core.auth import is_allowed
from core.memory import get_member_name, register_member

logger = logging.getLogger(__name__)

ASKING_NAME = 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not is_allowed(user_id):
        logger.warning(f"Попытка доступа от незнакомого ID: {user_id}")
        await update.message.reply_text("⛔ Извини, это закрытый семейный бот.")
        return ConversationHandler.END

    name = get_member_name(user_id)
    if name:
        await update.message.reply_text(
            f"Привет, {name}! 👋\n\n"
            "Просто напиши мне заметку или задай вопрос.\n\n"
            "Примеры заметок:\n"
            "• «Видела кафе Уют на Ленина 15, хотим сходить»\n"
            "• «Завтра я у врача с 8 до 10»\n"
            "• «Дочка хочет на ДР велосипед»\n\n"
            "Примеры вопросов:\n"
            "• «Что запланировано на завтра?»\n"
            "• «Какие кафе мы хотели посетить?»\n"
            "• «Что хочет дочка на день рождения?»"
        )
        return ConversationHandler.END

    await update.message.reply_text("👋 Привет! Я Робо — семейный помощник.\n\nКак тебя зовут?")
    return ASKING_NAME


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    name = update.message.text.strip()

    register_member(user_id, name)
    logger.info(f"Зарегистрирован: {name} (id={user_id})")

    await update.message.reply_text(
        f"Отлично, {name}! 🎉 Теперь ты в семейном боте.\n\n"
        "Просто пиши мне заметки или вопросы в свободной форме."
    )
    return ConversationHandler.END
