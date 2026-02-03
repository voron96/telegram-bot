from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)
import re
import asyncio
import os
from datetime import datetime, timedelta

# ================= НАЛАШТУВАННЯ =================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306  # ID групи

MIN_TEXT_LEN = 50
MAX_EMOJI = 8
KIEV_OFFSET = timedelta(hours=2)  # Український час (UTC+2)

warn_short_text = set()
daily_message_id = None

# =============================================

LINK_RE = re.compile(r"(t\.me/|https?://)")
GOOGLE_MAPS_RE = re.compile(r"maps\.google\.com|goo\.gl/maps")

EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF]", flags=re.UNICODE
)

# =============================================

def user_link(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(CHAT_ID, update.effective_user.id)
    return member.status in ("administrator", "creator")


async def delete_later(msg, sec):
    await asyncio.sleep(sec)
    try:
        await msg.delete()
    except:
        pass


async def restrict_user(context, user_id):
    """Обмеження користувача в правах публікацій"""
    try:
        await context.bot.restrict_chat_member(
            CHAT_ID,
            user_id,
            ChatPermissions(can_send_messages=False),
        )
    except:
        pass


# =============================================
# ГОЛОВНА МОДЕРАЦІЯ
# =============================================

async def main_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_message:
        return
    if update.effective_chat.id != CHAT_ID:
        return

    user = update.effective_user
    msg = update.effective_message
    text = msg.text or ""

    if not user:
        return
    if await is_admin(update, context):
        return

    # ----- SYSTEM JOIN / LEFT -----
    if msg.new_chat_members or msg.left_chat_member:
        await msg.delete()
        return

    # ----- USERNAME REQUIRED -----
    if not user.username:
        await msg.delete()
        m = await context.bot.send_message(
            CHAT_ID,
            f"⚠️ {user_link(user)} ваш акаунт не підлягає правилам публікації, зверніться до адміністрації",
            parse_mode="HTML",
            disable_notification=True,
        )
        asyncio.create_task(delete_later(m, 10))
        return

    # ----- LINKS -----
    if LINK_RE.search(text) and not GOOGLE_MAPS_RE.search(text):
        await msg.delete()
        await restrict_user(context, user.id)
        m = await context.bot.send_message(
            CHAT_ID,
            f"🚫 {user_link(user)} обмежений у правах публікації з причин - порушень правил майданчика",
            parse_mode="HTML",
            disable_notification=True,
        )
        asyncio.create_task(delete_later(m, 15))
        return

    # ----- EMOJI LIMIT (нове) -----
    emoji_count = len(EMOJI_RE.findall(text))
    if emoji_count > MAX_EMOJI:
        await msg.delete()
        await restrict_user(context, user.id)
        m = await context.bot.send_message(
            CHAT_ID,
            f"🚫 {user_link(user)} ваша публікація не відповідає правилам майданчика 😠",
            parse_mode="HTML",
            disable_notification=True,
        )
        asyncio.create_task(delete_later(m, 15))
        return

    # ----- SHORT TEXT -----
    if text and len(text) < MIN_TEXT_LEN:
        await msg.delete()

        if user.id in warn_short_text:
            # друге порушення
            await restrict_user(context, user.id)
            m = await context.bot.send_message(
                CHAT_ID,
                f"🚫 {user_link(user)} обмежений у правах публікації з причини порушення правил майданчика ",
                parse_mode="HTML",
                disable_notification=True,
            )
            asyncio.create_task(delete_later(m, 15))
        else:
            warn_short_text.add(user.id)
            m = await context.bot.send_message(
                CHAT_ID,
                f"⚠️ {user_link(user)} Наступне подібне порушення призведе до обмеження прав на публікацію ",
                parse_mode="HTML",
                disable_notification=True,
            )
            asyncio.create_task(delete_later(m, 10))
        return


# =============================================
# ЩОДЕННЕ ПОВІДОМЛЕННЯ
# =============================================

async def send_daily_message(context: ContextTypes.DEFAULT_TYPE):
    """Публікація ранкового повідомлення та видалення старого"""
    global daily_message_id

    if daily_message_id:
        try:
            await context.bot.delete_message(CHAT_ID, daily_message_id)
        except:
            pass

    # ТВОЄЙ ТЕКСТ — без змін
    text = (
        "📮 <b>Доброго ранку!</b>\n\n"
        "Перед публікацією оголошення, переконайтеся що ознайомилися з "
        "🔧 <b>правилами публікації</b> (прикріплені зверху чату) і нічого не порушуєте.\n\n"
        "Інакше адміністрація +написаний бот буде обмежувати в правах публікації.\n"
        "Всім працездатного дня! ☕💪"
    )

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌐 Наш інший майданчик", url="https://t.me/kiev_shat")]]
    )

    msg = await context.bot.send_message(
        CHAT_ID,
        text,
        parse_mode="HTML",
        disable_notification=True,
        reply_markup=keyboard,
    )

    daily_message_id = msg.message_id


async def schedule_daily(context: ContextTypes.DEFAULT_TYPE):
    """Планування повідомлення на 7:00 за Києвом"""
    while True:
        now_utc = datetime.utcnow()
        now_kiev = now_utc + KIEV_OFFSET
        next_send = now_kiev.replace(hour=7, minute=0, second=0, microsecond=0)

        if now_kiev >= next_send:
            next_send += timedelta(days=1)

        delta = (next_send - now_kiev).total_seconds()
        await asyncio.sleep(delta)
        await send_daily_message(context)


# =============================================
# ЗАПУСК
# =============================================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, main_moderation))

    # запуск щоденного повідомлення
    app.job_queue.run_once(lambda ctx: asyncio.create_task(schedule_daily(ctx)), 1)

    print("BOT STARTED ✅")
    app.run_polling()


if __name__ == "__main__":
    main()
