import logging
import os

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

from bot.handlers.commands import clear_my_notes, help_command, list_notes, members
from bot.handlers.messages import handle_message
from bot.handlers.start import ASKING_NAME, receive_name, start
from core.auth import ALLOWED_IDS

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN не задан в .env")
    if not ALLOWED_IDS:
        raise ValueError("ALLOWED_IDS не задан в .env — бот никого не пустит!")

    app = ApplicationBuilder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={ASKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)]},
        fallbacks=[],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("notes", list_notes))
    app.add_handler(CommandHandler("members", members))
    app.add_handler(CommandHandler("clear", clear_my_notes))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"✅ Робо запущен. Разрешённых ID: {len(ALLOWED_IDS)}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
