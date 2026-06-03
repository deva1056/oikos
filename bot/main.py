import logging
import os

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

from bot.handlers.commands import (
    addtag_command,
    clear_my_notes,
    help_command,
    list_notes,
    members,
    tag_command,
    tags_command,
    timezone_command,
)
from bot.handlers.draft import (
    DRAFTING,
    ask_command,
    cancel_draft,
    draft_from_question,
    draft_was_question,
    note_command,
    refine_message,
    route_first_message,
    save_draft,
)
from bot.handlers.location import handle_location
from bot.handlers.start import ASKING_NAME, receive_name, start
from core.auth import ALLOWED_IDS
from core.db import init_db

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    init_db()

    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN не задан в .env")
    if not ALLOWED_IDS:
        raise ValueError("ALLOWED_IDS не задан в .env — бот никого не пустит!")

    app = ApplicationBuilder().token(token).build()

    start_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={ASKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)]},
        fallbacks=[],
    )

    # Диалоговый черновик заметки. Сырой текст живёт только в user_data, не в БД.
    draft_conv = ConversationHandler(
        entry_points=[
            CommandHandler("note", note_command),
            CommandHandler("ask", ask_command),
            CallbackQueryHandler(draft_from_question, pattern=r"^draft_from_q$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, route_first_message),
        ],
        states={
            DRAFTING: [
                CommandHandler("save", save_draft),
                CommandHandler("cancel", cancel_draft),
                CallbackQueryHandler(save_draft, pattern=r"^draft_save$"),
                CallbackQueryHandler(cancel_draft, pattern=r"^draft_cancel$"),
                CallbackQueryHandler(draft_was_question, pattern=r"^draft_was_q$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, refine_message),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_draft)],
    )

    app.add_handler(start_conv)
    app.add_handler(CommandHandler("notes", list_notes))
    app.add_handler(CommandHandler("tags", tags_command))
    app.add_handler(CommandHandler("tag", tag_command))
    app.add_handler(CommandHandler("addtag", addtag_command))
    app.add_handler(CommandHandler("members", members))
    app.add_handler(CommandHandler("timezone", timezone_command))
    app.add_handler(CommandHandler("clear", clear_my_notes))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(draft_conv)

    logger.info(f"✅ Робо запущен. Разрешённых ID: {len(ALLOWED_IDS)}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
