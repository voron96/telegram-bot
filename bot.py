import asyncio
import re
from datetime import datetime, time, timedelta
from collections import defaultdict
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

# ================= НАСТРОЙКИ =================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306  # ID ГРУПИ
KYIV_TZ = ZoneInfo("Europe/Kyiv")

NIGHT_START = time(0, 25)
NIGHT_END = time(7, 0)

NIGHT_TEXT = (
    "🌙 <b>Увага!</b>\n\n"
    "На майданчику оголошується <b>нічний режим</b> 🌒\n"
    "До 07:00 всі повідомлення видаляються.\n\n"
    "Тихої та спокійної ночі 💫"
)

NIGHT_BUTTON = InlineKeyboardMarkup([
    [InlineKeyboardButton("➡️ Перейти в інший чат", url="https://t.me/your_second_chat")]
])

URL_RE = re.compile(r"(https://t.me/kiev_shat)", re.IGNORECASE)

user_violations = defaultdict(list)

# ================= ДОПОМІЖНЕ =================

def is_admin(member):
    return member.status in ("administrator", "creator")

def now_kyiv():
    return datetime.now(KYIV_TZ)

def is_night():
    t = now_kyiv().time()
    return NIGHT_START <= t or t < NIGHT_END

# ================= НІЧНЕ ОГОЛОШЕННЯ =================

async def night_announcement(app):
    sent = False
    while True:
        now = now_kyiv()
        if now.time().hour == NIGHT_START.hour and now.time().minute == NIGHT_START.minute and not sent:
            await app.bot.send_message(
                chat_id=CHAT_ID,
                text=NIGHT_TEXT,
                reply_markup=NIGHT_BUTTON,
                disable_notification=True,
            )
            sent = True
        if now.time().hour == 7 and now.time().minute == 1:
            sent = False
        await asyncio.sleep(30)

# ================= МОДЕРАЦІЯ =================

async def main_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user:
        return

    member = await chat.get_member(user.id)
    if is_admin(member):
        return

    # нічний режим
    if is_night():
        await message.delete()
        return

    now = now_kyiv()
    user_violations[user.id] = [
        t for t in user_violations[user.id]
        if now - t < timedelta(minutes=10)
    ]

    # ===== посилання =====
    if message.text and URL_RE.search(message.text):
        await message.delete()
        await chat.restrict_member(
            user.id,
            ChatPermissions(can_send_messages=False)
        )
        warn = await chat.send_message(
            f"⛔ <b>{user.first_name}</b>, ваше оголошення не підлягає правилам.\n"
            "Ви обмежені в правах публікації.",
            disable_notification=True
        )
        await asyncio.sleep(10)
        await warn.delete()
        return

    # ===== короткий текст =====
    text_len = len(message.text or "")
    if text_len > 0 and text_len < 50:
        user_violations[user.id].append(now)
        await message.delete()

        if len(user_violations[user.id]) >= 2:
            await chat.restrict_member(
                user.id,
                ChatPermissions(can_send_messages=False)
            )
            warn = await chat.send_message(
                f"⚠️ <b>{user.first_name}</b>, ви обмежені в правах публікації.\n"
                "Зверніться до адміністрації.",
                disable_notification=True
            )
            await asyncio.sleep(10)
            await warn.delete()
        return

# ================= JOIN / LEFT =================

async def clean_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.delete()

# ================= ЗАПУСК =================

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, clean_service))
    app.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        main_moderation
    ))

    asyncio.create_task(night_announcement(app))

    print("✅ BOT STARTED")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
