import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    ChatMemberHandler,
    filters,
)

# ================= НАСТРОЙКИ =================
TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306  # ID групи
TIMEZONE = ZoneInfo("Europe/Kyiv")

NIGHT_START = time(0, 0)   # 00:10
NIGHT_END = time(7, 0)     # 07:00

BUTTON_URL = "https://t.me/kiev_shat"
# ============================================

logging.basicConfig(level=logging.INFO)

restricted_users = set()


# ----------- НІЧНИЙ РЕЖИМ -----------
def is_night() -> bool:
    now = datetime.now(TIMEZONE).time()
    if NIGHT_START <= NIGHT_END:
        return NIGHT_START <= now < NIGHT_END
    return now >= NIGHT_START or now < NIGHT_END


async def send_night_message(app):
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("👉 Перейти в чат", url=BUTTON_URL)]]
    )
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text="🌙 Нічний режим активний.\nПублікації тимчасово заборонені.",
        reply_markup=keyboard,
        disable_notification=True,
    )


# ----------- МОДЕРАЦІЯ -----------
async def main_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    chat = message.chat

    if user.id in restricted_users:
        await message.delete()
        return

    if is_night() and not user.is_bot:
        await message.delete()
        return

    # якщо нема юзернейму
    if not user.username:
        await message.delete()
        warn = await context.bot.send_message(
            chat_id=chat.id,
            text=f"{user.first_name}, ваш акаунт не відповідає правилам публікації.",
            disable_notification=True,
        )
        context.job_queue.run_once(
            lambda _: warn.delete(), 10
        )
        return

    # мінімум 50 символів
    if message.text and len(message.text) < 50:
        await message.delete()
        restricted_users.add(user.id)
        warn = await context.bot.send_message(
            chat_id=chat.id,
            text=f"{user.first_name} обмежений в правах публікації. Зверніться до адміністрації.",
            disable_notification=True,
        )
        context.job_queue.run_once(
            lambda _: warn.delete(), 15
        )


# ----------- ВИДАЛЕННЯ JOIN / LEAVE -----------
async def clean_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.delete()


# ----------- СТАРТ -----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # повідомлення
    app.add_handler(
        MessageHandler(
            filters.TEXT
            | filters.PHOTO
            | filters.VIDEO
            | filters.Document.ALL,
            main_moderation,
        )
    )

    # join / leave
    app.add_handler(
        MessageHandler(filters.StatusUpdate.ALL, clean_service)
    )

    # нічне повідомлення о 00:00
    app.job_queue.run_daily(
        lambda ctx: send_night_message(app),
        time=NIGHT_START,
        chat_id=CHAT_ID,
        name="night_start",
    )

    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
