import asyncio
import logging
import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    ChatMemberHandler,
    filters,
)

# ================= НАСТРОЙКИ =================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"

TIMEZONE = ZoneInfo("Europe/Kyiv")

NIGHT_TIME = time(23, 45)   # 23:45
MORNING_TIME = time(8, 0)   # 08:00

SECOND_CHAT_LINK = "https://t.me/kiev_shat"  # кнопка під нічним повідомленням

MIN_TEXT_LEN = 50

# ================= ЛОГИ =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ================= СТАН =================

warnings = set()  # user_id які вже отримали 1 попередження

# ================= ДОПОМІЖНІ =================

def is_night() -> bool:
    now = datetime.now(TIMEZONE).time()
    return now >= NIGHT_TIME or now < MORNING_TIME


def has_username(user) -> bool:
    return bool(user.username)


def has_forbidden_links(text: str) -> bool:
    if not text:
        return False

    text = text.lower()

    # дозволяємо тільки google maps
    if "maps.google" in text or "goo.gl/maps" in text:
        return False

    return bool(re.search(r"(t\.me/|https?://)", text))


async def silent_delete(message):
    try:
        await message.delete()
    except:
        pass


async def temp_message(context, chat_id, text, seconds=10):
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        disable_notification=True,
    )
    await asyncio.sleep(seconds)
    try:
        await msg.delete()
    except:
        pass


async def restrict_forever(context, chat_id, user_id):
    await context.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
    )

# ================= ОБРОБНИКИ =================

async def clean_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await silent_delete(update.message)


async def night_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_night():
        return

    if update.effective_user.id in [admin.user.id for admin in await context.bot.get_chat_administrators(update.effective_chat.id)]:
        return

    await silent_delete(update.message)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("➡️ Перейти в нічний чат", url=SECOND_CHAT_LINK)]]
    )

    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🌙 Нічний режим\nПублікації заборонені з 23:45 до 08:00",
        reply_markup=keyboard,
        disable_notification=True,
    )

    await asyncio.sleep(15)
    try:
        await msg.delete()
    except:
        pass


async def main_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    chat_id = msg.chat.id

    if user.id in [admin.user.id for admin in await context.bot.get_chat_administrators(chat_id)]:
        return

    # ❌ без username
    if not has_username(user):
        await silent_delete(msg)
        await temp_message(
            context,
            chat_id,
            f"{user.full_name}, ваш акаунт не підлягає правилам публікації. Зверніться до адміністрації",
            10,
        )
        return

    # ❌ заборонені посилання
    if has_forbidden_links(msg.text or ""):
        await silent_delete(msg)
        await restrict_forever(context, chat_id, user.id)
        await temp_message(
            context,
            chat_id,
            f"{user.full_name}, ваше оголошення не підлягає правилам майданчику. Ви обмежені в правах публікації",
            10,
        )
        return

    # ❌ короткий текст
    if msg.text and len(msg.text) < MIN_TEXT_LEN:
        await silent_delete(msg)

        if user.id in warnings:
            await restrict_forever(context, chat_id, user.id)
            await temp_message(
                context,
                chat_id,
                f"{user.full_name}, ви обмежені в правах публікації. Зверніться до адміністрації",
                15,
            )
        else:
            warnings.add(user.id)
        return


# ================= ЗАПУСК =================

def main():
    app = Application.builder().token(TOKEN).build()

    # видалення join/leave
    app.add_handler(ChatMemberHandler(clean_service_messages, ChatMemberHandler.CHAT_MEMBER))

    # нічний режим
    app.add_handler(MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, night_mode_handler))

    # основна модерація
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO | filters.DOCUMENT, main_moderation))

    print("✅ BOT STARTED")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()

