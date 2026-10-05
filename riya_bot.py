import logging
import os
import random
import sqlite3
import time
from datetime import datetime, timezone

from gtts import gTTS
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReactionTypeEmoji,
)
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    ConversationHandler,
    filters,
)

# ============================================================
# RIYA AI BOT v2
# Features:
# - Bengali romantic/help/joke commands
# - Text + optional Bengali voice replies
# - Random emoji reaction to messages
# - SQLite user/group/channel/admin tracking
# - Admin dashboard
# - Broadcast
# - Add/remove admin
# - Ban/unban users
# - Channel setup
# - Group setup
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("RIYA")

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

# Put your Telegram numeric user ID here in hosting Variables.
# Example: OWNER_ID=123456789
try:
    OWNER_ID = int(os.getenv("OWNER_ID", "0"))
except ValueError:
    OWNER_ID = 0

DB_PATH = os.getenv("DB_PATH", "riya.db")
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "true").lower() == "true"
REACTION_ENABLED = os.getenv("REACTION_ENABLED", "true").lower() == "true"

REACTIONS = ["❤️", "👍", "😂", "🥰", "🔥", "👏", "😍", "🤩", "💯", "✨"]

# Conversation states
BROADCAST = 1
ADD_ADMIN = 2
REMOVE_ADMIN = 3
BAN_USER = 4
UNBAN_USER = 5
SET_CHANNEL = 6
SET_GROUP = 7


# -------------------- DATABASE --------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            is_banned INTEGER DEFAULT 0,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            start_count INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            chat_type TEXT,
            title TEXT,
            username TEXT,
            enabled INTEGER DEFAULT 1,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            key TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0
        )
    """)

    if OWNER_ID:
        cur.execute(
            "INSERT OR IGNORE INTO admins(user_id, added_by, added_at) VALUES (?, ?, ?)",
            (OWNER_ID, OWNER_ID, now()),
        )

    conn.commit()
    conn.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def today_prefix():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def set_setting(key, value):
    conn = db()
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def inc_stat(key, amount=1):
    conn = db()
    conn.execute(
        "INSERT INTO stats(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=value+excluded.value",
        (key, amount),
    )
    conn.commit()
    conn.close()


def upsert_user(user, is_start=False):
    if not user:
        return

    t = now()
    conn = db()
    row = conn.execute(
        "SELECT user_id FROM users WHERE user_id=?", (user.id,)
    ).fetchone()

    if row:
        if is_start:
            conn.execute(
                "UPDATE users SET first_name=?, username=?, last_seen=?, "
                "start_count=start_count+1 WHERE user_id=?",
                (user.first_name or "", user.username or "", t, user.id),
            )
        else:
            conn.execute(
                "UPDATE users SET first_name=?, username=?, last_seen=? WHERE user_id=?",
                (user.first_name or "", user.username or "", t, user.id),
            )
    else:
        conn.execute(
            "INSERT INTO users("
            "user_id,first_name,username,is_banned,first_seen,last_seen,start_count"
            ") VALUES(?,?,?,?,?,?,?)",
            (
                user.id,
                user.first_name or "",
                user.username or "",
                0,
                t,
                t,
                1 if is_start else 0,
            ),
        )

    conn.commit()
    conn.close()


def upsert_chat(chat):
    if not chat:
        return

    t = now()
    title = chat.title or chat.first_name or ""
    username = chat.username or ""

    conn = db()
    conn.execute(
        "INSERT INTO chats(chat_id,chat_type,title,username,enabled,first_seen,last_seen) "
        "VALUES(?,?,?,?,1,?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, "
        "username=excluded.username, last_seen=excluded.last_seen",
        (chat.id, chat.type, title, username, t, t),
    )
    conn.commit()
    conn.close()


def is_admin(user_id):
    conn = db()
    row = conn.execute(
        "SELECT user_id FROM admins WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return bool(row)


def is_banned(user_id):
    conn = db()
    row = conn.execute(
        "SELECT is_banned FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return bool(row and row["is_banned"])


def set_banned(user_id, value):
    conn = db()
    conn.execute(
        "INSERT INTO users(user_id,first_name,username,is_banned,first_seen,last_seen,start_count) "
        "VALUES(?,?,?,?,?,?,0) "
        "ON CONFLICT(user_id) DO UPDATE SET is_banned=excluded.is_banned",
        (user_id, "", "", int(value), now(), now()),
    )
    conn.commit()
    conn.close()


def add_admin(user_id, added_by):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO admins(user_id,added_by,added_at) VALUES(?,?,?)",
        (user_id, added_by, now()),
    )
    conn.commit()
    conn.close()


def remove_admin(user_id):
    if user_id == OWNER_ID:
        return False
    conn = db()
    cur = conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_admin_ids():
    conn = db()
    rows = conn.execute("SELECT user_id FROM admins").fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def count_users():
    conn = db()
    n = conn.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    conn.close()
    return n


def count_banned():
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) n FROM users WHERE is_banned=1"
    ).fetchone()["n"]
    conn.close()
    return n


def count_started_today():
    prefix = today_prefix() + "%"
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) n FROM users WHERE first_seen LIKE ? AND start_count > 0",
        (prefix,),
    ).fetchone()["n"]
    conn.close()
    return n


def count_active_today():
    prefix = today_prefix() + "%"
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) n FROM users WHERE last_seen LIKE ?",
        (prefix,),
    ).fetchone()["n"]
    conn.close()
    return n


def count_chats(chat_type=None):
    conn = db()
    if chat_type:
        n = conn.execute(
            "SELECT COUNT(*) n FROM chats WHERE chat_type=?", (chat_type,)
        ).fetchone()["n"]
    else:
        n = conn.execute("SELECT COUNT(*) n FROM chats").fetchone()["n"]
    conn.close()
    return n


def get_broadcast_users():
    conn = db()
    rows = conn.execute(
        "SELECT user_id FROM users WHERE is_banned=0"
    ).fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


# -------------------- HELPERS --------------------

def admin_only(update: Update):
    return bool(
        update.effective_user
        and is_admin(update.effective_user.id)
    )


async def denied(update: Update):
    if update.effective_message:
        await update.effective_message.reply_text(
            "⛔ দুঃখিত! এই অংশটি শুধু RIYA Admin-দের জন্য। 👑"
        )


def text_to_voice(text, filename):
    tts = gTTS(text=text, lang="bn", slow=False)
    tts.save(filename)
    return filename


async def send_text_and_voice(update, text):
    if not update.effective_message:
        return

    await update.effective_message.reply_text(text)

    if not ENABLE_VOICE:
        return

    filename = f"riya_voice_{update.effective_user.id}_{int(time.time()*1000)}.mp3"

    try:
        text_to_voice(text, filename)
        with open(filename, "rb") as audio:
            await update.effective_message.reply_voice(voice=audio)
    except Exception:
        logger.exception("Voice generation failed")
    finally:
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except OSError:
            pass


async def safe_react(update):
    if not REACTION_ENABLED or not update.effective_message:
        return

    msg = update.effective_message
    if not msg.chat:
        return

    try:
        emoji = random.choice(REACTIONS)
        await msg.set_reaction(
            reaction=ReactionTypeEmoji(emoji=emoji),
            is_big=False,
        )
    except TelegramError:
        # Some chats can disable a reaction or otherwise reject it.
        pass
    except Exception:
        logger.exception("Reaction failed")


async def track_update(update):
    if update.effective_user:
        upsert_user(update.effective_user, False)
    if update.effective_chat:
        upsert_chat(update.effective_chat)


# -------------------- USER COMMANDS --------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        upsert_user(update.effective_user, True)
        inc_stat("starts")

    if is_banned(update.effective_user.id):
        await update.message.reply_text(
            "🚫 তোমার অ্যাকাউন্টটি বর্তমানে RIYA Bot-এ ব্লক করা আছে।"
        )
        return

    name = update.effective_user.first_name or "মেরি জান"

    keyboard = [
        [
            InlineKeyboardButton("🌹 Rose", callback_data="rose"),
            InlineKeyboardButton("❤️ Love Chat", callback_data="love"),
        ],
        [
            InlineKeyboardButton("😂 Joke", callback_data="joke"),
            InlineKeyboardButton("🤭 Naughty", callback_data="naughty"),
        ],
        [
            InlineKeyboardButton("📚 Help", callback_data="help"),
            InlineKeyboardButton("📣 Channel", callback_data="channel"),
        ],
    ]

    if is_admin(update.effective_user.id):
        keyboard.append(
            [InlineKeyboardButton("👑 Admin Dashboard", callback_data="dashboard")]
        )

    text = (
        f"🌟✨ হ্যালো {name}! 💖🌹\n\n"
        "🤖 আমি **RIYA AI Bot** — তোমার মিষ্টি chat companion! 🥰\n\n"
        "💬 যেকোনো message লিখলেই আমি reply দেওয়ার চেষ্টা করব।\n"
        "✨ Message-এ random emoji reaction-ও দেওয়ার চেষ্টা করব!\n\n"
        "📌 নিচের menu থেকে feature ব্যবহার করো। 👇"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚✨ **RIYA Help Menu**\n\n"
        "🌹 /rose — গোলাপ ও ভালোবাসা\n"
        "❤️ /lovechat — romantic message\n"
        "😂 /joke — মজার joke\n"
        "🤭 /naughty — দুষ্টু মিষ্টি গল্প\n"
        "📚 /help — এই menu\n"
        "👑 /admin — Admin dashboard (শুধু admin)\n\n"
        "💬 এছাড়া যেকোনো সাধারণ message লিখলেও RIYA reply করবে।"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def joke_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jokes = [
        "🤣 শিক্ষক: বলতো পল্টু, বক্তৃতা আর সংশোধনের পার্থক্য কী?\n🧠 পল্টু: দীর্ঘক্ষণ ভুল কথা বলা হলো বক্তৃতা, আর ভুল ধরে বকা খাওয়া হলো সংশোধন! 😜👏",
        "😂 ডাক্তার: এই সোফায় বসুন।\n😲 রোগী: কোনটায়? এখানে তো চারটা সোফা দেখা যাচ্ছে! 🤣",
        "🤭 মশা খুঁজে না পেয়ে শেষে মশার সাথেই আউশ-কাউশ করে ঘুমিয়ে পড়লাম! 🦟😂",
    ]
    await send_text_and_voice(update, random.choice(jokes))


async def naughty_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stories = [
        "🤭 দুষ্টু মিষ্টি কাহিনী:\n🥰 বয়ফ্রেন্ড: তোমাকে দেখলে আমার সব টাকা খরচ করতে ইচ্ছে করে!\n😏 গার্লফ্রেন্ড: সত্যি? শপিং?\n😂 বয়ফ্রেন্ড: না, চিপস আর আইসক্রিম! 🍦",
        "😜 বউ: তুমি এত হ্যান্ডসাম কেন?\n🥰 স্বামী: তোমার ভালোবাসার গুণ!\n😡 বউ: আরে আমি পাশের বাসার আন্টিকে বলছিলাম! 🤣",
    ]
    await send_text_and_voice(update, random.choice(stories))


async def lovechat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messages = [
        "❤️🥰 মেরি জান, তোমার সাথে কথা বললেই আমার virtual দুনিয়াটা সুন্দর হয়ে যায়! 🌹✨",
        "💖 তুমি হাসলে যেন RIYA-এর chat window-টাও একটু বেশি সুন্দর লাগে! 🥰🌸",
        "💘 হাজারো message-এর মাঝেও তোমার message আলাদা লাগে! 😘🌹",
    ]
    await send_text_and_voice(update, random.choice(messages))


async def rose_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    roses = [
        "🌹✨ এই নাও তোমার জন্য এক ঝুড়ি লাল গোলাপ! 💐🥰",
        "🌹💖 তোমার হাসির জন্য একটা তাজা গোলাপ! 🌸😘",
        "🌹🌹🌹 একটা নয়, হাজারটা গোলাপ তোমার জন্য! 💐✨",
    ]
    await send_text_and_voice(update, random.choice(roses))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_update(update)

    if not update.message or not update.message.text:
        return

    # In groups, RIYA only works after being promoted to admin.
    chat = update.effective_chat
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if get_setting(f"group:{chat.id}") != "enabled":
            return

    await safe_react(update)

    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text("🚫 তোমার account RIYA Bot-এ blocked.")
        return

    text = update.message.text.lower()
    user_input = update.message.text

    if "i love you" in text or "ভালোবাসি" in text:
        reply = (
            "❤️🥰 I love you too, মেরি জান! "
            "এই নাও এক বুক ভালোবাসা আর একগুচ্ছ গোলাপ! 🌹✨"
        )
    elif "meri jaan" in text or "মেরি জান" in text or "jan" in text:
        reply = (
            "💖💋 বলো আমার মেরি জান! "
            "আজ চাঁদ এনে দেবো নাকি এক বাক্স চকোলেট? 🍫🌹"
        )
    elif "রিলেশন" in text or "প্রেম" in text or "relationship" in text:
        reply = (
            "🥰❤️ প্রেম আর সম্পর্কের সবচেয়ে সুন্দর জিনিস হলো "
            "বিশ্বাস, সম্মান আর ভালো communication। 🌹"
        )
    elif "rose" in text or "গোলাপ" in text or "ফুল" in text:
        await rose_handler(update, context)
        return
    elif "দুষ্টু" in text or "naughty" in text:
        await naughty_handler(update, context)
        return
    elif "কেমন আছো" in text or "how are you" in text:
        reply = (
            "🌸✨ তোমার সাথে কথা বলে আমি দারুণ আছি! "
            "তুমি কেমন আছো, মেরি জান? 🥰💖"
        )
    elif "কে তুমি" in text or "who are you" in text:
        reply = (
            "🤖✨ আমি RIYA — তোমার emoji-packed Telegram chat companion! 💖"
        )
    elif "মজার কাহিনী" in text or "jokes" in text or "গল্প" in text:
        await joke_handler(update, context)
        return
    else:
        # This is keyword-based smart fallback, NOT a real LLM.
        reply = (
            f"🤖✨ **RIYA AI Chat** 🧠💬\n\n"
            f"তুমি বলেছো: \"{user_input}\"\n\n"
            "💡 আমি এখনো built-in smart reply mode-এ আছি। "
            "চাইলে পরে OpenAI/Gemini API যুক্ত করে real AI answer system করা যাবে। 🥰✨"
        )

    await send_text_and_voice(update, reply)


# -------------------- GROUP / CHANNEL --------------------

async def welcome_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_update(update)

    if not update.message or not update.message.new_chat_members:
        return

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue

        name = member.first_name or "বন্ধু"
        text = (
            f"🌟🎉 Welcome {name}! 🥳💖\n\n"
            "🤖 আমি RIYA Bot। তোমাদের group-এ আড্ডা দিতে প্রস্তুত! ✨\n"
            "💬 Message লিখলেই reply করার চেষ্টা করব। 🌹"
        )
        await send_text_and_voice(update, text)


async def my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Automatic group activation:
    When RIYA is promoted to administrator in a group/supergroup,
    the group is automatically enabled. No /setupgroup command needed.
    """
    await track_update(update)

    cm = update.my_chat_member
    if not cm or not cm.chat:
        return

    chat = cm.chat

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    new_status = cm.new_chat_member.status

    # Bot promoted to admin => automatically activate the group.
    if new_status in ("administrator", "creator"):
        set_setting(f"group:{chat.id}", "enabled")

        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "👑🤖 **RIYA Group Mode Activated!** 🎉\n\n"
                    "✅ আমাকে Group Admin করা হয়েছে।\n"
                    "💬 এখন group-এর messages-এ RIYA reply করবে।\n"
                    "✨ Random emoji reaction দেওয়ারও চেষ্টা করবে।\n\n"
                    "⚡ কোনো `/setupgroup` command লাগবে না! ❤️"
                ),
                parse_mode="Markdown",
            )
        except TelegramError:
            logger.exception("Could not send group activation message.")

    # Bot is demoted/removed => disable the group.
    elif new_status in ("member", "left", "kicked"):
        set_setting(f"group:{chat.id}", "disabled")


# -------------------- ADMIN DASHBOARD --------------------

def dashboard_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Statistics", callback_data="stats"),
            InlineKeyboardButton("📢 Broadcast", callback_data="broadcast"),
        ],
        [
            InlineKeyboardButton("👑 Add Admin", callback_data="add_admin"),
            InlineKeyboardButton("🗑️ Remove Admin", callback_data="remove_admin"),
        ],
        [
            InlineKeyboardButton("🚫 Ban User", callback_data="ban_user"),
            InlineKeyboardButton("✅ Unban User", callback_data="unban_user"),
        ],
        [
            InlineKeyboardButton("📣 Add Channel", callback_data="set_channel"),
            InlineKeyboardButton("👥 Setup Group", callback_data="set_group"),
        ],
        [
            InlineKeyboardButton("📋 Admin List", callback_data="admin_list"),
            InlineKeyboardButton("⚙️ Bot Status", callback_data="bot_status"),
        ],
    ])


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update):
        await denied(update)
        return

    await update.message.reply_text(
        "👑✨ **RIYA Admin Panel**\n\n"
        "নিচের button থেকে management করো। 🛠️💖",
        parse_mode="Markdown",
        reply_markup=dashboard_keyboard(),
    )


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("⛔ Admin only", show_alert=True)
        return

    data = q.data

    if data == "dashboard":
        await q.edit_message_text(
            "👑✨ **RIYA Admin Dashboard**\n\n"
            "🛠️ সব management option নিচে আছে:",
            parse_mode="Markdown",
            reply_markup=dashboard_keyboard(),
        )

    elif data == "stats":
        text = (
            "📊✨ **RIYA Statistics**\n\n"
            f"👤 Total Users: `{count_users()}`\n"
            f"🆕 Today Start Users: `{count_started_today()}`\n"
            f"🟢 Active Today: `{count_active_today()}`\n"
            f"🚫 Banned Users: `{count_banned()}`\n"
            f"👥 Groups/Supergroups: `{count_chats('group') + count_chats('supergroup')}`\n"
            f"📣 Channels: `{count_chats('channel')}`\n"
            f"👑 Admins: `{len(get_admin_ids())}`"
        )
        await q.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]
            ]),
        )

    elif data == "admin_list":
        ids = get_admin_ids()
        lines = "\n".join(f"👑 `{x}`" for x in ids) or "কোনো admin নেই"
        await q.edit_message_text(
            f"👑 **Admin List**\n\n{lines}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]
            ]),
        )

    elif data == "bot_status":
        await q.edit_message_text(
            "⚙️ **RIYA Bot Status**\n\n"
            "🟢 Bot: Running\n"
            f"🔊 Voice: {'ON' if ENABLE_VOICE else 'OFF'}\n"
            f"✨ Auto Reaction: {'ON' if REACTION_ENABLED else 'OFF'}\n"
            "💾 Database: SQLite\n"
            "🚀 Deployment: Polling",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Dashboard", callback_data="dashboard")]
            ]),
        )

    elif data == "channel":
        channel = get_setting("channel")
        if channel:
            text = (
                f"📣 **Our Channel**\n\n"
                f"🔗 {channel}\n\n"
                "❤️ Join করে RIYA-এর updates পেতে পারো!"
            )
        else:
            text = (
                "📣 **Channel এখনো সেট করা হয়নি।**\n\n"
                "Admin-কে channel add করতে হবে। 👑"
            )

        buttons = []
        if channel and channel.startswith("@"):
            buttons.append(
                [InlineKeyboardButton("📣 Open Channel", url=f"https://t.me/{channel[1:]}")]
            )
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="dashboard")])

        await q.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data == "rose":
        await q.message.reply_text("🌹✨ এই নাও তোমার জন্য একগুচ্ছ গোলাপ! 💖")

    elif data == "love":
        await q.message.reply_text("❤️🥰 Love Chat mode activated! /lovechat ব্যবহার করো।")

    elif data == "joke":
        await q.message.reply_text("😂 /joke লিখলে নতুন joke আসবে!")

    elif data == "naughty":
        await q.message.reply_text("🤭 /naughty লিখলে দুষ্টু মিষ্টি গল্প আসবে!")

    elif data == "help":
        await q.message.reply_text(
            "📚 /start /help /rose /lovechat /joke /naughty /admin"
        )

    elif data == "broadcast":
        await q.message.reply_text(
            "📢 Broadcast পাঠাতে নিচের message হিসেবে তোমার broadcast text পাঠাও।",
        )
        context.user_data["waiting"] = "broadcast"

    elif data == "add_admin":
        await q.message.reply_text(
            "👑 **Add New Admin**\n\n"
            "নতুন admin-এর numeric Telegram Chat ID পাঠাও।\n"
            "উদাহরণ: `123456789`",
            parse_mode="Markdown",
        )
        context.user_data["waiting"] = "add_admin"

    elif data == "remove_admin":
        await q.message.reply_text(
            "🗑️ যে admin-কে remove করতে চাও তার numeric Chat ID পাঠাও।"
        )
        context.user_data["waiting"] = "remove_admin"

    elif data == "ban_user":
        await q.message.reply_text(
            "🚫 যে user-কে ban করতে চাও তার numeric Telegram User ID পাঠাও।"
        )
        context.user_data["waiting"] = "ban_user"

    elif data == "unban_user":
        await q.message.reply_text(
            "✅ যে user-কে unban করতে চাও তার numeric Telegram User ID পাঠাও।"
        )
        context.user_data["waiting"] = "unban_user"

    elif data == "set_channel":
        await q.message.reply_text(
            "📣 তোমার channel username পাঠাও।\n\n"
            "উদাহরণ: `@mychannel`\n"
            "⚠️ Public channel username ব্যবহার করো।",
            parse_mode="Markdown",
        )
        context.user_data["waiting"] = "set_channel"

    elif data == "set_group":
        await q.message.reply_text(
            "👥 Group setup-এর জন্য bot-কে যে group-এ ব্যবহার করতে চাও, "
            "সেই group-এ `/setupgroup` command দাও।"
        )


async def admin_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return False

    if not admin_only(update):
        return False

    waiting = context.user_data.get("waiting")
    if not waiting:
        return False

    value = update.message.text.strip()
    uid = update.effective_user.id

    if waiting == "broadcast":
        context.user_data.pop("waiting", None)
        users = get_broadcast_users()
        sent = 0
        failed = 0

        status = await update.message.reply_text(
            f"📢 Broadcast শুরু হচ্ছে...\n👥 Target: {len(users)}"
        )

        for target in users:
            try:
                await context.bot.send_message(chat_id=target, text=value)
                sent += 1
            except TelegramError:
                failed += 1

        await status.edit_text(
            f"📢 **Broadcast Complete**\n\n"
            f"✅ Sent: `{sent}`\n"
            f"❌ Failed: `{failed}`",
            parse_mode="Markdown",
        )
        return True

    if waiting in {"add_admin", "remove_admin", "ban_user", "unban_user"}:
        try:
            target_id = int(value)
        except ValueError:
            await update.message.reply_text("❌ শুধু numeric Chat/User ID পাঠাও।")
            return True

        context.user_data.pop("waiting", None)

        if waiting == "add_admin":
            add_admin(target_id, uid)
            await update.message.reply_text(
                f"👑✅ `{target_id}` এখন RIYA Admin.",
                parse_mode="Markdown",
            )

        elif waiting == "remove_admin":
            if target_id == OWNER_ID:
                await update.message.reply_text(
                    "⛔ Owner admin remove করা যাবে না।"
                )
            else:
                ok = remove_admin(target_id)
                await update.message.reply_text(
                    "🗑️✅ Admin removed." if ok else "⚠️ ওই ID admin list-এ ছিল না।"
                )

        elif waiting == "ban_user":
            set_banned(target_id, True)
            await update.message.reply_text(
                f"🚫✅ User `{target_id}` banned.",
                parse_mode="Markdown",
            )

        elif waiting == "unban_user":
            set_banned(target_id, False)
            await update.message.reply_text(
                f"✅ User `{target_id}` unbanned.",
                parse_mode="Markdown",
            )

        return True

    if waiting == "set_channel":
        if not value.startswith("@"):
            await update.message.reply_text(
                "❌ Public channel username এভাবে দাও: `@channelusername`",
                parse_mode="Markdown",
            )
            return True

        try:
            chat = await context.bot.get_chat(value)
            if chat.type != ChatType.CHANNEL:
                await update.message.reply_text("❌ এটা Telegram channel নয়।")
                return True
        except TelegramError:
            await update.message.reply_text(
                "❌ Channel পাওয়া যায়নি। Username এবং bot-এর access check করো।"
            )
            return True

        set_setting("channel", value)
        context.user_data.pop("waiting", None)
        await update.message.reply_text(
            f"📣✅ Channel set হয়েছে: {value}"
        )
        return True

    return False


# -------------------- ERROR HANDLER --------------------

async def error_handler(update, context):
    logger.exception("Unhandled exception:", exc_info=context.error)


# -------------------- MAIN --------------------

def main():
    init_db()

    app: Application = ApplicationBuilder().token(TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rose", rose_handler))
    app.add_handler(CommandHandler("lovechat", lovechat_handler))
    app.add_handler(CommandHandler("joke", joke_handler))
    app.add_handler(CommandHandler("naughty", naughty_handler))
    app.add_handler(CommandHandler("admin", admin_command))

    # Admin/dashboard callbacks
    callback_names = [
        "dashboard", "stats", "broadcast", "add_admin", "remove_admin",
        "ban_user", "unban_user", "set_channel", "set_group",
        "admin_list", "bot_status", "channel", "rose", "love", "joke",
        "naughty", "help"
    ]
    app.add_handler(
        CallbackQueryHandler(
            dashboard_callback,
            pattern="^(" + "|".join(callback_names) + ")$"
        )
    )

    # Admin text actions must run before general text handler.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            admin_text_router,
        ),
        group=0,
    )

    # New members
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_member)
    )

    # Bot membership changes
    app.add_handler(
        MessageHandler(filters.StatusUpdate.MY_CHAT_MEMBER, my_chat_member)
    )

    # General messages.
    # In groups, Telegram privacy mode must be disabled for the bot
    # if you want it to receive every ordinary group message.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        ),
        group=1,
    )

    app.add_error_handler(error_handler)

    logger.info("RIYA Bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
