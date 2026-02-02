import re
import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    ChatMemberHandler,
    filters,
)

# ================== НАСТРОЙКИ ==================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306          # ID основного чату
TIMEZONE = ZoneInfo("Europe/Kyiv")

NIGHT_START = time(23, 30)
NIGHT_END = time(8, 0)

SECOND_CHAT_URL = "https://t.me/kiev_shat"

MIN_TEXT_LEN = 50

# ===============================================


def is_night_now() -> bool:
    now = datetime.now(TIMEZONE).time()
    return now >= NIGHT_START or now <= NIGHT_END


# ---------- НІЧНЕ ПОВІДОМЛЕННЯ ----------

async def night_warning(context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("👉 Перейти в нічний чат", url=SECOND_CHAT_URL)]]
    )

    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="🌙 <b>Нічний режим</b>\nПублікації тимчасово обмежені.",
        reply_markup=keyboard,
        disable_notification=True,
    )


# ---------- ВИДАЛЕННЯ JOIN / LEAVE ----------

async def handle_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except Exception:
        pass


# ---------- ПЕРЕВІРКА ПОСИЛАНЬ ----------

def has_bad_links(text: str) -> bool:
    if not text:
        return False

    # дозволяємо ТІЛЬКИ google maps
    if "maps.google.com" in text or "goo.gl/maps" in text:
        return False

    return bool(re.search(r"(https?://|t\.me/)", text))


# ---------- ГОЛОВНА МОДЕРАЦІЯ ----------

async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user

    # адмінів не чіпаємо
    member = await context.bot.get_chat_member(message.chat_id, user.id)
    if member.status in ("administrator", "creator"):
        return

    text = message.text or ""

    # 🌙 нічний режим
    if is_night_now():
        await message.delete()
        return

    # ❌ акаунт без юзернейма
    if not user.username:
        await message.delete()
        warn = await context.bot.send_message(
            chat_id=message.chat_id,
            text=f"<b>{user.first_name}</b>, ваш акаунт не підлягає правилам публікації. Зверніться до адміністрації.",
            disable_notification=True,
        )
        await asyncio.sleep(10)
        await warn.delete()
        return

    # ❌ заборонені посилання
    if has_bad_links(text):
        await message.delete()
        await context.bot.restrict_chat_member(
            chat_id=message.chat_id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
        )

        warn = await context.bot.send_message(
            chat_id=message.chat_id,
            text=f"<b>{user.first_name}</b>, ваше оголошення не відповідає правилам. Ви обмежені в правах публікації.",
            disable_notification=True,
        )
        await asyncio.sleep(10)
        await warn.delete()
        return

    # ❌ короткий текст
    if len(text) < MIN_TEXT_LEN:
        await message.delete()

        count = context.chat_data.get(user.id, 0) + 1
        context.chat_data[user.id] = count

        if count >= 2:
            await context.bot.restrict_chat_member(
                chat_id=message.chat_id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False),
            )

            warn = await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"<b>{user.first_name}</b> обмежений в правах публікації. Зверніться до адміністрації.",
                disable_notification=True,
            )
            await asyncio.sleep(15)
            await warn.delete()


# ================== ЗАПУСК ==================

def main():
    app = Application.builder().token(TOKEN).build()

    # join / leave
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER,
            handle_members,
        )
    )

    # модерація повідомлень
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, moderate)
    )

    # нічне повідомлення щодня о 23:30
    app.job_queue.run_daily(
        night_warning,
        time=NIGHT_START,
        chat_id=CHAT_ID,
        name="night_warning",
    )

    print("✅ BOT STARTED")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
