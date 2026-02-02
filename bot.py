import asyncio
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# ================== НАЛАШТУВАННЯ ==================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306
DISCUSS_CHAT_URL = "https://t.me/kiev_shat"

TZ = ZoneInfo("Europe/Kyiv")

NIGHT_START = time(23, 30)
NIGHT_END = time(7, 0)
MUTE_HOURS = 6

# =================================================

warned_short = set()
warned_night = set()
night_msg_id = None

# ================== ТЕКСТИ ==================

NIGHT_TEXT = (
    "🌒 <b>На майданчику оголошується нічний режим</b>\n\n"
    "До 07:00 всі повідомлення видаляються\n"
    "Повтор → обмеження в публікації на 6 год\n\n"
    "Тихої та спокійної ночі 💤"
)

# ================== ДОП ==================

def user_link(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'

def now_time():
    return datetime.now(TZ).time()

def is_night():
    t = now_time()
    return t >= NIGHT_START or t <= NIGHT_END

async def is_admin(update, context):
    m = await context.bot.get_chat_member(CHAT_ID, update.effective_user.id)
    return m.status in ("administrator", "creator")

async def delete_later(msg, sec):
    await asyncio.sleep(sec)
    try:
        await msg.delete()
    except:
        pass

async def restrict(context, user_id, hours=None, forever=False):
    until = None
    if hours:
        until = datetime.now(TZ) + timedelta(hours=hours)

    await context.bot.restrict_chat_member(
        CHAT_ID,
        user_id,
        ChatPermissions(can_send_messages=False),
        until_date=until,
    )

# ================== НІЧНИЙ КОНТРОЛЬ ==================

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

    await msg.delete()

    if user.id not in warned_night:
        warned_night.add(user.id)
        return

    await restrict(context, user.id, hours=MUTE_HOURS)

    m = await context.bot.send_message(
        CHAT_ID,
        f"🔇 {user_link(user)} обмежений в правах публікації\nЗверніться до адміністрації",
        parse_mode="HTML",
        disable_notification=True,
    )
    asyncio.create_task(delete_later(m, 15))

# ================== ЗАГАЛЬНА МОДЕРАЦІЯ ==================

async def moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    if await is_admin(update, context):
        return

    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    # join / leave
    if msg.new_chat_members or msg.left_chat_member:
        await msg.delete()
        return

    text = msg.text or msg.caption or ""

    # немає username
    if not user.username:
        await msg.delete()
        m = await context.bot.send_message(
            CHAT_ID,
            f"⚠️ {user_link(user)} ваш акаунт не підлягає правилам публікації\nЗверніться до адміністрації",
            parse_mode="HTML",
            disable_notification=True,
        )
        asyncio.create_task(delete_later(m, 10))
        return

    # лінки (крім google maps)
    if re.search(r"(t\.me/|http://|https://)", text):
        if "google.com/maps" not in text:
            await msg.delete()
            await restrict(context, user.id, forever=True)
            m = await context.bot.send_message(
                CHAT_ID,
                f"⛔️ {user_link(user)} обмежений в правах публікації\nЗверніться до адміністрації",
                parse_mode="HTML",
                disable_notification=True,
            )
            asyncio.create_task(delete_later(m, 15))
            return

    # емоджі >= 8
    emojis = re.findall(r"[\U00010000-\U0010ffff]", text)
    if len(emojis) >= 8:
        await msg.delete()
        await restrict(context, user.id, forever=True)
        m = await context.bot.send_message(
            CHAT_ID,
            f"⛔️ {user_link(user)} ваша публікація не підлягає правилам майданчика",
            parse_mode="HTML",
            disable_notification=True,
        )
        asyncio.create_task(delete_later(m, 15))
        return

    # текст < 50
    if len(text) < 50:
        await msg.delete()
        if user.id not in warned_short:
            warned_short.add(user.id)
            return
        await restrict(context, user.id, forever=True)
        m = await context.bot.send_message(
            CHAT_ID,
            f"🔇 {user_link(user)} обмежений в правах публікації\nЗверніться до адміністрації",
            parse_mode="HTML",
            disable_notification=True,
        )
        asyncio.create_task(delete_later(m, 15))

# ================== КОМАНДИ ==================

async def analitik(update, context):
    if update.effective_chat.id != CHAT_ID:
        return
    if not await is_admin(update, context):
        await update.effective_message.delete()
        return

    m = await context.bot.send_message(
        CHAT_ID,
        "🛡 Проблем не виявлено, все безпечно",
        disable_notification=True,
    )
    await update.effective_message.delete()
    asyncio.create_task(delete_later(m, 5))

# ================== НІЧНЕ ОГОЛОШЕННЯ ==================

async def night_watcher(app):
    global night_msg_id
    sent = False

    while True:
        t = now_time()
        if t.hour == NIGHT_START.hour and t.minute == NIGHT_START.minute and not sent:
            warned_night.clear()

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Чат обговорення", url=DISCUSS_CHAT_URL)]
            ])

            msg = await app.bot.send_message(
                CHAT_ID,
                NIGHT_TEXT,
                reply_markup=kb,
                parse_mode="HTML",
                disable_notification=True,
            )
            night_msg_id = msg.message_id
            sent = True

        if t.minute != NIGHT_START.minute:
            sent = False

        await asyncio.sleep(20)

# ================== MAIN ==================

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("analitik", analitik))
    app.add_handler(MessageHandler(filters.ALL, moderation))
    app.add_handler(MessageHandler(filters.ALL, night_guard))

    asyncio.create_task(night_watcher(app))

    print("Бот запущений")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
