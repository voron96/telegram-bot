import re
from datetime import time
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== НАЛАШТУВАННЯ ==================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306  # ← ОБОВʼЯЗКОВО ВПИШИ ID ЧАТУ
TIMEZONE = ZoneInfo("Europe/Kyiv")

NIGHT_START = time(1, 0)   # 01:00
NIGHT_END = time(7, 0)     # 07:00

SECOND_CHAT_LINK = "https://t.me/kiev_shat"

MIN_TEXT_LEN = 50

# ================== СТАН ==================

user_last_short = {}  # user_id -> bool (чи вже було коротке)

# ================== ДОПОМІЖНІ ==================

def is_night(now):
    if NIGHT_START < NIGHT_END:
        return NIGHT_START <= now < NIGHT_END
    return now >= NIGHT_START or now < NIGHT_END


def has_forbidden_links(text: str) -> bool:
    if not text:
        return False

    if "maps.google" in text or "goo.gl/maps" in text:
        return False

    return bool(re.search(r"(http://|https://|t\.me/)", text))


# ================== ГОЛОВНА МОДЕРАЦІЯ ==================

async def main_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or message.chat_id != CHAT_ID:
        return

    user_id = message.from_user.id
    now = message.date.astimezone(TIMEZONE).time()

    # ===== НІЧНИЙ РЕЖИМ =====
    if is_night(now):
        await message.delete()

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👉 Перейти в нічний чат", url=SECOND_CHAT_LINK)]
        ])

        await context.bot.send_message(
            chat_id=CHAT_ID,
            text="🌙 Нічний режим\nПублікації з 01:00 до 07:00 заборонені",
            reply_markup=keyboard,
            disable_notification=True
        )
        return

    text = message.text or ""

    # ===== ПОСИЛАННЯ =====
    if has_forbidden_links(text):
        await message.delete()
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text="❌ Ваше оголошення не підлягає правилам майданчику.\nПосилання заборонені.",
            delete_after=10
        )
        return

    # ===== КОРОТКИЙ ТЕКСТ =====
    if message.text and len(text) < MIN_TEXT_LEN:
        if user_last_short.get(user_id):
            await message.delete()
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text="❌ Повторне коротке повідомлення. Ви обмежені в публікації.",
                delete_after=10
            )
            return
        else:
            user_last_short[user_id] = True
    else:
        user_last_short[user_id] = False


# ================== ЗАПУСК ==================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.Chat(CHAT_ID)
            & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL),
            main_moderation
        )
    )

    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
