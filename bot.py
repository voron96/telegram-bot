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
    filters,
)
from datetime import time
import re
import asyncio

# ================= НАСТРОЙКИ =================

TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306  # ID групи

MIN_TEXT_LEN = 50
MAX_EMOJI = 8

# =============================================

warn_short_text = set()
morning_message_id = None

LINK_RE = re.compile(r"(t\.me/|https?://)")
GOOGLE_MAPS_RE = re.compile(r"maps\.google\.com|goo\.gl/maps")

EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF]"
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
    await context.bot.restrict_chat_member(
        CHAT_ID,
        user_id,
        ChatPermissions(can_send_messages=False),
    )

# =============================================
# РАНКОВЕ ПОВІДОМЛЕННЯ 07:00 (Київ = UTC+2)
# =============================================

async def morning_post(context: ContextTypes.DEFAULT_TYPE):
    global morning_message_id

    if morning_message_id:
        try:
            await context.bot.delete_message(CHAT_ID, morning_message_id)
        except:
            pass

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👉 Перейти в чат Києва", url="https://t.me/kiev_shat")]
    ])

    msg = await context.bot.send_message(
        CHAT_ID,
        "☀️ Доброго ранку!\n\n"
        "Перед публікацією оголошення ознайомтесь з правилами чату "
        "(закріплені зверху).\n"
        "Порушення правил призводить до обмеження публікацій.\n\n"
        "Гарного та продуктивного дня! 💼✨",
        reply_markup=keyboard,
        disable_notification=True
    )

    morning_message_id = msg.message_id

# =============================================
# ОСНОВНА МОДЕРАЦІЯ
# =============================================

async def main_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_message:
        return

    if update.effective_chat.id != CHAT_ID:
        return

    user = update.effective_user
    msg = update.effective_message

    if not user:
        return

    if await is_admin(update, context):
        return

    # JOIN / LEFT
    if msg.new_chat_members or msg.left_chat_member:
        await msg.delete()
        return

    text = msg.text or ""

    # USERNAME REQUIRED
    if not user.username:
        await msg.delete()
        m = await context.bot.send_message(
            CHAT_ID,
            f"⚠️ {user_link(user)} ваш акаунт не відповідає правилам публікації.",
            parse_mode="HTML",
            disable_notification=True
        )
        asyncio.create_task(delete_later(m, 10))
        return

    # LINKS
    if LINK_RE.search(text) and not GOOGLE_MAPS_RE.search(text):
        await msg.delete()
        await restrict_user(context, user.id)
        m = await context.bot.send_message(
            CHAT_ID,
            f"🚫 {user_link(user)} обмежений в правах публікації.",
            parse_mode="HTML",
            disable_notification=True
        )
        asyncio.create_task(delete_later(m, 15))
        return

    # EMOJI LIMIT
    if len(EMOJI_RE.findall(text)) >= MAX_EMOJI:
        await msg.delete()
        await restrict_user(context, user.id)
        return

    # SHORT TEXT
    if text and len(text) < MIN_TEXT_LEN:
        await msg.delete()
        if user.id in warn_short_text:
            await restrict_user(context, user.id)
        else:
            warn_short_text.add(user.id)
        return

# =============================================
# ЗАПУСК
# =============================================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Модерація
    app.add_handler(MessageHandler(filters.ALL, main_moderation))

    # Ранковий пост:
    # 05:00 UTC = 07:00 Київ
    app.job_queue.run_daily(
        morning_post,
        time=time(hour=5, minute=0)
    )

    print("BOT STARTED")
    app.run_polling()


if __name__ == "__main__":
    main()
