import logging
import os
import random
import sqlite3
from pathlib import Path

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:
    from gtts import gTTS
except Exception:
    gTTS = None

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("RIYA")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = os.getenv("OWNER_ID", "").strip()
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "true").strip().lower() == "true"
REACTION_ENABLED = os.getenv("REACTION_ENABLED", "true").strip().lower() == "true"
DB_PATH = os.getenv("DB_PATH", "riya.db").strip() or "riya.db"

REACTION_EMOJIS = ["❤️", "👍", "🔥", "✨", "😊", "😂", "💯"]
VOICE_PREFIX = "riya_voice_"


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS groups "
        "(chat_id INTEGER PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1)"
    )
    conn.commit()
    return conn


def set_group_active(chat_id: int, active: bool):
    with db() as conn:
        conn.execute(
            "INSERT INTO groups(chat_id, active) VALUES(?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET active=excluded.active",
            (chat_id, 1 if active else 0),
        )
        conn.commit()


def is_group_active(chat_id: int) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT active FROM groups WHERE chat_id=?", (chat_id,)
        ).fetchone()
    return bool(row and row[0] == 1)


def owner_allowed(update: Update) -> bool:
    if not OWNER_ID:
        return False
    user = update.effective_user
    return bool(user and str(user.id) == OWNER_ID)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message:
        return
    await update.effective_message.reply_text(
        "👋 Hi! I’m RIYA.\n\n"
        "Add me to a group and promote me to administrator to activate group mode automatically."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message:
        return
    await update.effective_message.reply_text(
        "🤖 RIYA Help\n\n"
        "• Group mode activates automatically when RIYA becomes an administrator.\n"
        "• RIYA replies to ordinary group text messages.\n"
        "• Voice and reactions can be controlled with Railway variables."
    )


async def my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.my_chat_member
    if not cmu:
        return

    chat = update.effective_chat
    if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    status = cmu.new_chat_member.status
    if status == "administrator":
        set_group_active(chat.id, True)
        await context.bot.send_message(
            chat.id,
            "👑 RIYA activated!\n\n"
            "I’m now an administrator, so group mode is ON. ✨",
        )
    elif status in ("left", "kicked", "member"):
        # If the bot is no longer an administrator, group mode is off.
        set_group_active(chat.id, False)


async def group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not is_group_active(chat.id):
        return

    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    # Simple, safe conversational response. No external AI key is required.
    lower = text.lower()
    if any(x in lower for x in ("hi", "hello", "hey")) or "হাই" in text or "হ্যালো" in text:
        reply = "হাই! 😊 আমি RIYA। কী খবর?"
    elif "how are you" in lower or "কেমন আছ" in text:
        reply = "আমি ভালো আছি! ✨ তুমি কেমন আছ?"
    else:
        reply = random.choice(
            [
                "বুঝেছি 😊",
                "আচ্ছা! ✨",
                "হুম, ঠিক আছে ❤️",
                "Interesting! 👀",
            ]
        )

    await message.reply_text(reply)

    if REACTION_ENABLED:
        # Telegram reaction availability varies by chat/account permissions.
        try:
            await message.set_reaction(
                reaction=random.choice(REACTION_EMOJIS),
                is_big=False,
            )
        except Exception:
            pass

    if ENABLE_VOICE and gTTS is not None:
        await send_voice_reply(context, chat.id, reply)


async def send_voice_reply(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    filename = f"{VOICE_PREFIX}{chat_id}.mp3"
    try:
        gTTS(text=text, lang="bn").save(filename)
        with open(filename, "rb") as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)
    except Exception as exc:
        logger.warning("Voice generation failed: %s", exc)
    finally:
        try:
            Path(filename).unlink(missing_ok=True)
        except Exception:
            pass


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message:
        return
    if not owner_allowed(update):
        await update.effective_message.reply_text("⛔ Owner only.")
        return
    await update.effective_message.reply_text(
        "✅ RIYA is online.\n"
        f"Voice: {'ON' if ENABLE_VOICE else 'OFF'}\n"
        f"Reactions: {'ON' if REACTION_ENABLED else 'OFF'}"
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Update error: %s", context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Add BOT_TOKEN in Railway Variables."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))

    # Correct handler for the bot's own membership changes.
    app.add_handler(
        ChatMemberHandler(
            my_chat_member,
            ChatMemberHandler.MY_CHAT_MEMBER,
        )
    )

    # Ordinary group text messages.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            group_message,
        )
    )

    app.add_error_handler(error_handler)

    logger.info("RIYA Bot is starting...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
