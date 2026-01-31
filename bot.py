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

NIGHT_START = time(23, 0)
NIGHT_END = time(7, 0)
MUTE_HOURS = 6

# =========================

warned_users = set()
night_msg_id = None
morning_msg_id = None


# ---------- ТЕКСТИ ----------

NIGHT_TEXT = (
    "⁉️ <b>На майданчику оголошується нічний режим</b> ⚠️\n\n"
    "Всі повідомлення видаляються до 07:00\n"
    "Повтор → автоматичні обмеження в правах\n\n"
    "Тихої та спокійної ночі ✨"
)

MORNING_TEXT = (
    "🌔 <b>Нічний режим завершено</b>\n\n"
    "Група працює в штатному режимі\n"
    "Дотримуйтеся правил, щоб не бути обмеженим в правах\n"
    "Працездатного дня ☘️"
)


# ---------- ДОП ----------

def user_link(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'


def is_night():
    now = datetime.now().time()
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
# НІЧНИЙ ФІЛЬТР
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

    # перший раз — тихо
    if user.id not in warned_users:
        warned_users.add(user.id)
        return

    # повтор — обмеження
    until = datetime.now() + timedelta(hours=MUTE_HOURS)

    await context.bot.restrict_chat_member(
        CHAT_ID,
        user.id,
        ChatPermissions(can_send_messages=False),
        until_date=until,
    )

    m = await context.bot.send_message(
        CHAT_ID,
        f"🔇 {user_link(user)} отримав обмеження в правах публікації на 6 год",
        parse_mode="HTML",
        disable_notification=True,
    )

    asyncio.create_task(delete_later(m, 15))
    asyncio.create_task(unmute_later(context, user.id, until))


# =========================
# РОЗМУТ
# =========================

async def unmute_job(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data

    await context.bot.restrict_chat_member(
        CHAT_ID,
        user_id,
        ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        ),
    )

    user = await context.bot.get_chat_member(CHAT_ID, user_id)

    msg = await context.bot.send_message(
        CHAT_ID,
        f"🔊 {user_link(user.user)} обмеження зняті",
        parse_mode="HTML",
        disable_notification=True
    )

    context.job_queue.run_once(
        lambda c: c.bot.delete_message(CHAT_ID, msg.message_id),
        15
    )

    user = await context.bot.get_chat_member(CHAT_ID, user_id)

    m = await context.bot.send_message(
        CHAT_ID,
        f"🔊 {user_link(user.user)} обмеження зняті",
        parse_mode="HTML",
        disable_notification=True,
    )

    asyncio.create_task(delete_later(m, 15))


# =========================
# БАНЕР НОЧІ
# =========================

async def send_night_banner(context):
    global night_msg_id, morning_msg_id, warned_users

    warned_users.clear()

    if morning_msg_id:
        try:
            await context.bot.delete_message(CHAT_ID, morning_msg_id)
        except:
            pass
        morning_msg_id = None

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Чат обговорення «ЧС»", url=DISCUSS_CHAT_URL)]
    ])

    msg = await context.bot.send_photo(
        CHAT_ID,
        photo=open("night_banner.jpg", "rb"),
        caption=NIGHT_TEXT,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_notification=True,
    )

    night_msg_id = msg.message_id


# =========================
# РАНОК
# =========================

async def send_morning_banner(context):
    global night_msg_id, morning_msg_id, warned_users

    warned_users.clear()

    if night_msg_id:
        try:
            await context.bot.delete_message(CHAT_ID, night_msg_id)
        except:
            pass
        night_msg_id = None

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
        "🛡 Проблем не виявлено, все безпечно",
        disable_notification=True,
    )

    try:
        await update.effective_message.delete()
    except:
        pass

    await asyncio.sleep(5)

    try:
        await bot_msg.delete()
    except:
        pass


# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("analitik", analitik_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, night_guard))

    app.job_queue.run_daily(send_night_banner, NIGHT_START)
    app.job_queue.run_daily(send_morning_banner, NIGHT_END)

    print("БОТ ЗАПУЩЕНИЙ")
    app.run_polling()


if __name__ == "__main__":
    main()
