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
import os
from datetime import datetime, timedelta


# ================= НАЛАШТУВАННЯ =================
TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306

MIN_TEXT_LEN = 50
MAX_EMOJI = 8
MUTE_HOURS = 3
KIEV_OFFSET = timedelta(hours=2)

warn_short_text = set()
daily_message_id = None


# ---------- ФУНКЦІЇ -------------
def count_emoji(text: str) -> int:
    """Рахує будь‑які емодзі (працює через regex)"""
    pat = re.compile(r"\p{Emoji=Yes}", flags=re.UNICODE)
    return len(pat.findall(text or ""))

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


# ---------- МОДЕРАЦІЯ -------------
LINK_RE = re.compile(r"(t\.me/|https?://)")
GOOGLE_MAPS_RE = re.compile(r"maps\.google\.com|goo\.gl/maps")


async def main_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or update.effective_chat.id != CHAT_ID:
        return
    user = update.effective_user
    msg = update.effective_message
    text = msg.text or ""
    if not user or await is_admin(update, context):
        return

    if msg.new_chat_members or msg.left_chat_member:
        await msg.delete(); return

    if not user.username:
        await msg.delete()
        m = await context.bot.send_message(
            CHAT_ID,
            f"⚠️ {user_link(user)} ваш акаунт не підлягає правилам публікації, зверніться до адміністрації",
            parse_mode="HTML", disable_notification=True)
        asyncio.create_task(delete_later(m,10)); return

    if LINK_RE.search(text) and not GOOGLE_MAPS_RE.search(text):
        await msg.delete()
        await mute_user(context,user.id,MUTE_HOURS)
        m = await context.bot.send_message(
            CHAT_ID,
            f"🚫 {user_link(user)} публікація можлива лише на правах реклами, зверніться до адміністрації",
            parse_mode="HTML", disable_notification=True)
        asyncio.create_task(delete_later(m,15)); return

    # --- EMOJI ---
    if count_emoji(text) > MAX_EMOJI:
        await msg.delete()
        await mute_user(context,user.id,MUTE_HOURS)
        m = await context.bot.send_message(
            CHAT_ID,
            f"🚫 {user_link(user)} публікація можлива лише на правах реклами, зверніться до адміністрації 😠",
            parse_mode="HTML", disable_notification=True)
        asyncio.create_task(delete_later(m,15)); return

    # --- SHORT TEXT ---
    if text and len(text)<MIN_TEXT_LEN:
        await msg.delete()
        if user.id in warn_short_text:
            await mute_user(context,user.id,MUTE_HOURS)
            m = await context.bot.send_message(
                CHAT_ID,
                f"🚫 {user_link(user)} публікація можлива лише на правах реклами, зверніться до адміністрації 📛",
                parse_mode="HTML", disable_notification=True)
            asyncio.create_task(delete_later(m,15))
        else:
            warn_short_text.add(user.id)
            m = await context.bot.send_message(
                CHAT_ID,
                f"⚠️ {user_link(user)} наступне подібне порушення призведе до обмеження в публікації, дотримуйтесь правил",
                parse_mode="HTML", disable_notification=True)
            asyncio.create_task(delete_later(m
