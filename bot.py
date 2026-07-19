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
import regex as re
import asyncio
from datetime import datetime, timedelta

# ================= НАЛАШТУВАННЯ =================
TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306  # ID твоєї групи

CHANNEL_ID = -1002375622983  # ID офіційного каналу
CHANNEL_LINK = "https://t.me/robota_kiev_workk"

MIN_TEXT_LEN = 50
MAX_EMOJI = 8
MUTE_HOURS = 6
KIEV_OFFSET = timedelta(hours=2)

warn_short_text = set()
daily_message_id = None

# ================= ПІДРАХУНОК ЕМОДЗІ =================
def count_emoji(text: str) -> int:
    if not text:
        return 0
    pattern = re.compile(r"[\p{Extended_Pictographic}]", flags=re.UNICODE)
    return len(pattern.findall(text))

# ================= СЛУЖБОВІ ФУНКЦІЇ =================
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

async def mute_user(context, user_id, hours):
    until = datetime.utcnow() + timedelta(hours=hours)
    try:
        await context.bot.restrict_chat_member(
            CHAT_ID,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until,
        )
    except:
        pass

# ================= МОДЕРАЦІЯ =================
LINK_RE = re.compile(r"(t\.me/|https?://)")
GOOGLE_MAPS_RE = re.compile(
    r"(maps\.google\.com|goo\.gl/maps|maps\.app\.goo\.gl)"
)

async def main_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_message or update.effective_chat.id != CHAT_ID:
        return

    user = update.effective_user
    msg = update.effective_message
    text = msg.text or ""

    # ----- ПОВІДОМЛЕННЯ З ОФІЦІЙНОГО КАНАЛУ -----
if msg.sender_chat and msg.sender_chat.id == CHANNEL_ID:

    # автоматично відкріпити повідомлення, якщо Telegram його прикріпив
    try:
        await context.bot.unpin_all_chat_messages(CHAT_ID)
    except:
        pass

    await context.bot.send_message(
        chat_id=CHAT_ID,
        text='⬆️ <a href="https://t.me/robota_kiev_workk"><b>Повідомлення з КАНАЛУ ↗️</b></a>',
        parse_mode="HTML",
        disable_notification=True,
        reply_to_message_id=msg.message_id,
        allow_sending_without_reply=True,
        disable_web_page_preview=True
    )

    return

    # ----- SYSTEM JOIN / LEFT -----
    if msg.new_chat_members or msg.left_chat_member:
        try:
            await msg.delete()
        except:
            pass
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
            disable_notification=True
        )
        asyncio.create_task(delete_later(m, 10))
        return

    # ----- LINKS -----
    if LINK_RE.search(text) and not GOOGLE_MAPS_RE.search(text):
        await msg.delete()
        await mute_user(context, user.id, MUTE_HOURS)
        m = await context.bot.send_message(
            CHAT_ID,
            f"🚫 {user_link(user)} публікація можлива лише на правах реклами, зверніться до адміністрації",
            parse_mode="HTML",
            disable_notification=True
        )
        asyncio.create_task(delete_later(m, 15))
        return

    # ----- EMOJI LIMIT -----
    emoji_count = count_emoji(text)
    if emoji_count > MAX_EMOJI:
        await msg.delete()
        await mute_user(context, user.id, MUTE_HOURS)
        m = await context.bot.send_message(
            CHAT_ID,
            f"🚫 {user_link(user)} публікація можлива лише на правах реклами, зверніться до адміністрації 😠",
            parse_mode="HTML",
            disable_notification=True
        )
        asyncio.create_task(delete_later(m, 15))
        return

    # ----- SHORT TEXT -----
    if text and len(text) < MIN_TEXT_LEN:
        await msg.delete()

        if user.id in warn_short_text:
            await mute_user(context, user.id, MUTE_HOURS)
            m = await context.bot.send_message(
                CHAT_ID,
                f"🚫 {user_link(user)} публікація можлива лише на правах реклами, зверніться до адміністрації 📛",
                parse_mode="HTML",
                disable_notification=True
            )
            asyncio.create_task(delete_later(m, 15))
        else:
            warn_short_text.add(user.id)
            m = await context.bot.send_message(
                CHAT_ID,
                f"⚠️ {user_link(user)} наступне подібне порушення призведе до обмеження в публікації, дотримуйтесь правил",
                parse_mode="HTML",
                disable_notification=True
            )
            asyncio.create_task(delete_later(m, 10))
        return

# ================= ЩОДЕННЕ ПОВІДОМЛЕННЯ =================
async def send_daily_message(bot):
    global daily_message_id
    if daily_message_id:
        try:
            await bot.delete_message(CHAT_ID, daily_message_id)
        except:
            pass

    text = (
        "📮 <b>Доброго ранку!</b>\n\n"
        "Перед публікацією оголошення, переконайтеся що ознайомилися з "
        "🔧 <b>правилами публікації</b> (прикріплені зверху чату) і нічого не порушуєте.\n\n"
        "Інакше адміністрація +написаний бот буде обмежувати в правах публікації.\n"
        "Всім працездатного дня! ☕💪"
    )

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Чат обговорення", url="https://t.me/kiev_shat")]]
    )

    msg = await bot.send_message(
        CHAT_ID,
        text,
        parse_mode="HTML",
        disable_notification=True,
        reply_markup=kb
    )

    asyncio.create_task(delete_later(msg, 60 * 60 * 12))

async def daily_scheduler(app):
    """Фоновий цикл для щоденного повідомлення"""
    while True:
        now_kiev = datetime.utcnow() + KIEV_OFFSET
        next_time = now_kiev.replace(hour=7, minute=0, second=0, microsecond=0)
        if now_kiev >= next_time:
            next_time += timedelta(days=1)
        await asyncio.sleep((next_time - now_kiev).total_seconds())
        await send_daily_message(app.bot)

# ================= ЗАПУСК =================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, main_moderation))

    loop = asyncio.get_event_loop()
    loop.create_task(daily_scheduler(app))

    print("BOT STARTED ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
