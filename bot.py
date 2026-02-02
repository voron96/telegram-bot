import asyncio
import re
from datetime import datetime, time, timedelta

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

# =========================
# НАЛАШТУВАННЯ
# =========================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306
DISCUSS_CHAT_URL = "https://t.me/kiev_shat"

# ⏰ UTC
NIGHT_START = time(20, 40)
NIGHT_END = time(5, 0)

MUTE_HOURS = 6
MIN_TEXT_LEN = 50
MAX_EMOJI = 8

# =========================

warned_night = set()
warned_short = set()
night_msg_id = None
morning_msg_id = None

# ---------- ТЕКСТИ ----------

NIGHT_TEXT = (
    "🌒 <b>На майданчику оголошується нічний режим</b>\n\n"
    "До 07:00 всі повідомлення видаляються 🧹\n"
    "Повтор → обмеження прав на 6 годин ⛔\n\n"
    "Тихої та спокійної ночі 💤"
)

MORNING_TEXT = (
    "☀️ <b>Нічний режим вимкнено</b>\n\n"
    "Майданчик працює в штатному режимі ✅\n"
    "Дотримуйтеся правил 📜\n\n"
    "Працездатного дня 💼✨"
)

# =========================
# ДОП
# =========================

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "]",
    flags=re.UNICODE,
)

def count_emoji(text: str) -> int:
    return len(EMOJI_RE.findall(text))


def user_link(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'


def is_night():
    now = datetime.utcnow().time()
    return now >= NIGHT_START or now <= NIGHT_END


async def is_admin(user_id, context):
    m = await context.bot.get_chat_member(CHAT_ID, user_id)
    return m.status in ("administrator", "creator")


async def delete_later(msg, sec):
    await asyncio.sleep(sec)
    try:
        await msg.delete()
    except:
        pass


async def mute_user(context, user_id, hours=None):
    until = None
    if hours:
        until = datetime.utcnow() + timedelta(hours=hours)

    await context.bot.restrict_chat_member(
        CHAT_ID,
        user_id,
        ChatPermissions(can_send_messages=False),
        until_date=until,
    )


# =========================
# СИСТЕМНІ
# =========================

async def delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.effective_message.delete()
    except:
        pass


# =========================
# ПОСИЛАННЯ
# =========================

LINK_RE = re.compile(r"(https?://|t\.me/|@)")

async def link_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update.effective_user.id, context):
        return

    text = update.effective_message.text or ""
    if not LINK_RE.search(text):
        return
    if "google.com/maps" in text or "maps.app.goo.gl" in text:
        return

    await update.effective_message.delete()
    await mute_user(context, update.effective_user.id)

    m = await context.bot.send_message(
        CHAT_ID,
        f"🚫 {user_link(update.effective_user)} обмежений в правах публікації.\n"
        "Зверніться до адміністрації 👮",
        parse_mode="HTML",
        disable_notification=True,
    )
    asyncio.create_task(delete_later(m, 15))


# =========================
# ЕМОДЖІ
# =========================

async def emoji_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update.effective_user.id, context):
        return

    msg = update.effective_message
    if not msg.text:
        return

    if count_emoji(msg.text) <= MAX_EMOJI:
        return

    await msg.delete()
    await mute_user(context, update.effective_user.id)

    m = await context.bot.send_message(
        CHAT_ID,
        f"⚠️ {user_link(update.effective_user)}, ваша публікація не підлягає правилам майданчика.\n"
        "Зверніться до адміністрації 🚨",
        parse_mode="HTML",
        disable_notification=True,
    )
    asyncio.create_task(delete_later(m, 15))


# =========================
# АДМІН MUTE → ПОВІДОМЛЕННЯ
# =========================

async def admin_mute_notice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.chat_member is None:
        return

    old = update.chat_member.old_chat_member
    new = update.chat_member.new_chat_member
    actor = update.chat_member.from_user

    if not old or not new or not actor:
        return

    if old.can_send_messages and not new.can_send_messages:
        if not await is_admin(actor.id, context):
            return

        user = new.user

        m = await context.bot.send_message(
            CHAT_ID,
            f"🛑 {user_link(user)} обмежено в правах адміністрацією майданчика.\n"
            "Зверніться до адміністрації",
            parse_mode="HTML",
            disable_notification=True,
        )
        asyncio.create_task(delete_later(m, 15))


# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, link_guard))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, emoji_guard))
    app.add_handler(ChatMemberHandler(admin_mute_notice, ChatMemberHandler.CHAT_MEMBER))

    app.job_queue.run_daily(lambda c: None, NIGHT_START)
    app.job_queue.run_daily(lambda c: None, NIGHT_END)

    app.run_polling()

if __name__ == "__main__":
    main()

