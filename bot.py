import asyncio
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
    ContextTypes,
    filters,
)

# =========================
# НАЛАШТУВАННЯ
# =========================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306
DISCUSS_CHAT_URL = "https://t.me/kiev_shat"

# ⏰ ЧАС В UTC
# 23:30 Київ = 21:30 UTC
NIGHT_START = time(21, 30)
# 07:00 Київ = 05:00 UTC
NIGHT_END = time(5, 0)

MUTE_HOURS = 6

# =========================

warned_users = set()
night_msg_id = None
morning_msg_id = None

# ---------- ТЕКСТ ----------

NIGHT_TEXT = (
    "🌒 <b>На майданчику оголошується нічний режим</b>\n\n"
    "До 07:00 всі повідомлення видаляються\n"
    "Повторна публікація → заборона на публікацію на 6 годин\n\n"
    "Тихої та спокійної ночі 💤"
)

MORNING_TEXT = (
    "☀️ <b>Нічний режим завершено</b>\n\n"
    "Група працює у звичайному режимі"
)

# =========================

def user_link(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'


def is_night():
    now = datetime.utcnow().time()
    return now >= NIGHT_START or now <= NIGHT_END


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await context.bot.get_chat_member(CHAT_ID, update.effective_user.id)
    return m.status in ("administrator", "creator")


async def delete_later(msg, sec):
    await asyncio.sleep(sec)
    try:
        await msg.delete()
    except:
        pass

# =========================
# НІЧНИЙ КОНТРОЛЬ
# =========================

async def night_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return

    if not is_night():
        return

    if await is_admin(update, context):
        return

    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    try:
        await msg.delete()
    except:
        pass

    if user.id not in warned_users:
        warned_users.add(user.id)
        return

    until = datetime.utcnow() + timedelta(hours=MUTE_HOURS)

    await context.bot.restrict_chat_member(
        CHAT_ID,
        user.id,
        ChatPermissions(can_send_messages=False),
        until_date=until,
    )

    m = await context.bot.send_message(
        CHAT_ID,
        f"🔇 {user_link(user)} заборона на публікацію 6 годин",
        parse_mode="HTML",
        disable_notification=True,
    )

    asyncio.create_task(delete_later(m, 15))

# =========================
# БАНЕР НОЧІ
# =========================

async def send_night_banner(context: ContextTypes.DEFAULT_TYPE):
    global night_msg_id, morning_msg_id, warned_users
    warned_users.clear()

    if morning_msg_id:
        try:
            await context.bot.delete_message(CHAT_ID, morning_msg_id)
        except:
            pass

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Чат обговорення", url=DISCUSS_CHAT_URL)]
    ])

    msg = await context.bot.send_message(
        CHAT_ID,
        NIGHT_TEXT,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_notification=True,
    )

    night_msg_id = msg.message_id

# =========================
# РАНОК
# =========================

async def send_morning_banner(context: ContextTypes.DEFAULT_TYPE):
    global night_msg_id, morning_msg_id, warned_users
    warned_users.clear()

    if night_msg_id:
        try:
            await context.bot.delete_message(CHAT_ID, night_msg_id)
        except:
            pass

    msg = await context.bot.send_message(
        CHAT_ID,
        MORNING_TEXT,
        parse_mode="HTML",
        disable_notification=True,
    )

    morning_msg_id = msg.message_id

# =========================
# /ANALITIK
# =========================

async def analitik_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return

    if not await is_admin(update, context):
        return

    bot_msg = await context.bot.send_message(
        CHAT_ID,
        "🛡 Все під контролем",
        disable_notification=True,
    )

    await asyncio.sleep(5)
    await bot_msg.delete()
    await update.effective_message.delete()

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("analitik", analitik_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, night_guard))

    app.job_queue.run_daily(send_night_banner, NIGHT_START)
    app.job_queue.run_daily(send_morning_banner, NIGHT_END)

    app.run_polling()

if __name__ == "__main__":
    main()
