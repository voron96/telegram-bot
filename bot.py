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
    ContextTypes,
    filters,
)

# ================= НАСТРОЙКИ =================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306
DISCUSS_CHAT_URL = "https://t.me/kiev_shat"

NIGHT_START = time(23, 30)
NIGHT_END = time(7, 0)

# ============================================

warned_short = set()
warned_night = set()
night_msg_id = None
morning_msg_id = None

# ================ ТЕКСТИ ====================

NIGHT_TEXT = (
    "🌒 <b>На майданчику оголошується нічний режим</b>\n\n"
    "До 07:00 всі повідомлення видаляються\n"
    "Повтор — обмеження публікації\n\n"
    "Тихої та спокійної ночі 💤"
)

MORNING_TEXT = (
    "☀️ <b>Нічний режим вимкнено</b>\n\n"
    "Майданчик працює в штатному режимі\n"
    "Дотримуйтесь правил\n"
    "Працездатного дня 💼"
)

# ============================================

def user_link(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'

def is_night():
    now = datetime.now().time()
    return now >= NIGHT_START or now <= NIGHT_END

async def is_admin(update, context):
    m = await context.bot.get_chat_member(CHAT_ID, update.effective_user.id)
    return m.status in ("administrator", "creator")

async def delete_later(msg, sec):
    await asyncio.sleep(sec)
    try:
        await msg.delete()
    except:
        pass

def full_mute():
    return ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )

# ================= ОБМЕЖЕННЯ =================

async def restrict(context, user, text):
    await context.bot.restrict_chat_member(CHAT_ID, user.id, full_mute())
    msg = await context.bot.send_message(
        CHAT_ID,
        f"🚫 {user_link(user)}\n{text}",
        parse_mode="HTML",
        disable_notification=True,
    )
    asyncio.create_task(delete_later(msg, 15))

# ============== ОСНОВНИЙ ФІЛЬТР ==============

async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return

    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    if msg.new_chat_members or msg.left_chat_member:
        await msg.delete()
        return

    if await is_admin(update, context):
        return

    text = msg.text or ""
    emojis = len(re.findall(r"[\U00010000-\U0010ffff]", text))

    # ЛІНКИ
    if re.search(r"(t\.me|http)", text) and "google.com/maps" not in text:
        await msg.delete()
        await restrict(context, user, "обмежений в правах публікації.\nЗверніться до адміністрації")
        return

    # 8+ емоджі
    if emojis > 8:
        await msg.delete()
        await restrict(context, user, "ваша публікація не відповідає правилам.\nЗверніться до адміністрації")
        return

    # <50 символів
    if len(text) < 50:
        await msg.delete()
        if user.id in warned_short:
            await restrict(context, user, "обмежений в правах публікації.\nЗверніться до адміністрації")
        else:
            warned_short.add(user.id)
        return

    # НІЧ
    if is_night():
        await msg.delete()
        if user.id in warned_night:
            await restrict(context, user, "обмежений в правах публікації (нічний режим)")
        else:
            warned_night.add(user.id)

# ================= КОМАНДИ ===================

async def analitik(update, context):
    if not await is_admin(update, context):
        return
    bot_msg = await context.bot.send_message(
        CHAT_ID,
        "🛡 Проблем не виявлено, все безпечно ✅",
        disable_notification=True,
    )
    await asyncio.sleep(5)
    await bot_msg.delete()
    await update.message.delete()

# ================= БАНЕРИ ====================

async def night_banner(context):
    global night_msg_id, morning_msg_id, warned_night
    warned_night.clear()

    if morning_msg_id:
        await context.bot.delete_message(CHAT_ID, morning_msg_id)
        morning_msg_id = None

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

async def morning_banner(context):
    global night_msg_id, morning_msg_id
    if night_msg_id:
        await context.bot.delete_message(CHAT_ID, night_msg_id)
        night_msg_id = None

    msg = await context.bot.send_message(
        CHAT_ID,
        MORNING_TEXT,
        parse_mode="HTML",
        disable_notification=True,
    )
    morning_msg_id = msg.message_id

# ================= MAIN ======================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("analitik", analitik))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, guard))

    app.job_queue.run_daily(night_banner, NIGHT_START)
    app.job_queue.run_daily(morning_banner, NIGHT_END)

    app.run_polling()

if __name__ == "__main__":
    main()
