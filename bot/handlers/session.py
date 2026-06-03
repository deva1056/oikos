"""Короткая сессия диалога с TTL по простою.

- chat_turns: последние реплики (для follow-up вопросов);
- sliding TTL: активность продлевает сессию, чистим только после простоя > TTL;
- по истечении TTL сбрасываем и историю, и незавершённый черновик.

Всё живёт в context.user_data (в памяти, по пользователю) — не в БД.
"""
import os
import time

from telegram import Update
from telegram.ext import ContextTypes

SESSION_TTL = int(os.getenv("SESSION_TTL_MIN", "15")) * 60
MAX_TURNS = 6  # последние 3 обмена (user+assistant)


async def touch_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group -1: на каждый апдейт продлеваем сессию или чистим по простою."""
    now = time.time()
    if now - context.user_data.get("last_active", 0) > SESSION_TTL:
        context.user_data.pop("chat_turns", None)
        context.user_data.pop("draft", None)
    context.user_data["last_active"] = now


def get_turns(context: ContextTypes.DEFAULT_TYPE) -> list:
    return context.user_data.get("chat_turns", [])


def remember_turn(context: ContextTypes.DEFAULT_TYPE, user_text: str, answer: str):
    turns = context.user_data.setdefault("chat_turns", [])
    turns.append({"role": "user", "content": user_text})
    turns.append({"role": "assistant", "content": answer})
    del turns[:-MAX_TURNS]  # оставляем последние MAX_TURNS
