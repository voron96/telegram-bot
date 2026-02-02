import asyncio
import re
from datetime import datetime, time

from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
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

NIGHT_START = time(23, 30)
NIGHT_END = time(7, 0)

# =================================================

short_warn = {}
night_warn = set()
night_msg_id = None
morning_msg_id = None

# ================== ТЕКСТИ ==================

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

# =============================================

def user_link(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'

def is_night():
    now = datetime.now().time()
    return now >= NIGHT_START or now <= NIGHT_END

async def is_admin(update, context):
    m = await context.bot.get_chat_member(CHAT_ID, update.effective_user.id)
    return m.status in ("administrator", "creator")

def full_mute():
    return ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )

async def delete_later(msg, sec):
    await asyncio.sleep(sec)
    try:
        await msg.delete()
    except:
        pass

async def restrict(context, user, text):
    await context.bot.restrict_chat_member(CHAT_ID, user.id, full_mute())
    msg = await context.bot.send_message(
        CHAT_ID,
        f"🚫 {user_link(user)}\n{text}",
        parse_mode="HTML",
        disable_notification=True,
    )
    asyncio.create_task(delete_later(msg, 15))

# ================== ОСНОВНИЙ ФІЛЬТР ==================

async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return

    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    # службові join/left
    if msg.new_chat_members or msg.left_chat_member:
        await msg.delete()
        return

    if await is_admin(update, context):
        return

    text = msg.text or ""

    # посилання
    if re.search(r"(t\.me|http)", text) and "google.com/maps" not in text:
        await msg.delete()
        await restrict(context, user, "обмежений в правах публікації.\nЗверніться до адміністрації")
        return

    # короткі повідомлення
    if len(text) < 50:
        await msg.delete()
        short_warn[user.id] = short_warn.get(user.id, 0) + 1
        if short_warn[user.id] >= 2:
            await restrict(context, user, "обмежений в правах публікації.\nЗверніться до адміністрації")
            short_warn.pop(user.id, None)
        return

    # ніч
    if is_night():
        await msg.delete()
        if user.id in night_warn:
            await restrict(context, user, "обмежений в правах публікації (нічний режим)")
        else:
            night_warn.add(user.id)

# ================== КОМАНДИ ==================

async def analitik(update, context):
    if not await is_admin(update, context):
        await update.message.delete()
        return

    msg = await context.bot.send_message(
        CHAT_ID,
        "🛡 Проблем не виявлено, все безпечно ✅",
        disable_notification=True,
    )
    await asyncio.sleep(5)
    await msg.delete()
    await update.message.delete()

async def cmd_on(update, context):
    if not await is_admin(update, context):
        await update.message.delete()
        return

    if not update.message.reply_to_message:
        await update.message.delete()
        return

    user = update.message.reply_to_message.from_user
    await context.bot.restrict_chat_member(CHAT_ID, user.id, full_mute())

    msg = await context.bot.send_message(
        CHAT_ID,
        f"🚫 {user_link(user)} обмежено в правах адміністрацією",
        parse_mode="HTML",
        disable_notification=True,
    )
    await delete_later(msg, 15)
    await update.message.delete()

async def cmd_off(update, context):
    if not await is_admin(update, context):
        await update.message.delete()
        return

    if not update.message.reply_to_message:
        await update.message.delete()
        return

    user = update.message.reply_to_message.from_user
    await context.bot.restrict_chat_member(
        CHAT_ID,
        user.id,
        ChatPermissions(can_send_messages=True, can_send_media_messages=True,
                        can_send_other_messages=True, can_add_web_page_previews=True),
    )

    msg = await context.bot.send_message(
        CHAT_ID,
        f"🔓 {user_link(user)} обмеження зняті адміністрацією",
        parse_mode="HTML",
        disable_notification=True,
    )
    await delete_later(msg, 15)
    await update.message.delete()

# ================== MAIN ==================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("analitik", analitik))
    app.add_handler(CommandHandler("on", cmd_on))
    app.add_handler(CommandHandler("off", cmd_off))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, guard))

    app.run_polling()

if __name__ == "__main__":
    main()
