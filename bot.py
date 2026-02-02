import asyncio
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# ========= НАЛАШТУВАННЯ =========
TOKEN = "8354126069:AAHSDjqmoh9qDMzHtIr4-ZM1BYlBHYz3n4s"
CHAT_ID = -1002190311306
# ===============================


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id
    )
    return member.status in ("administrator", "creator")


# ======= /analitik =======
async def analitik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return

    if not await is_admin(update, context):
        return

    msg = await context.bot.send_message(
        CHAT_ID,
        "✅ Проблем не виявлено, все безпечно 🙂",
        disable_notification=True,
    )

    await asyncio.sleep(5)

    try:
        await msg.delete()
        await update.effective_message.delete()
    except:
        pass


# ======= ТЕСТОВИЙ ФІЛЬТР =======
async def test_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return

    user = update.effective_user
    msg = update.effective_message

    if not user or not msg:
        return

    if await is_admin(update, context):
        return

    if msg.text and len(msg.text) < 50:
        await msg.delete()

        warn = await context.bot.send_message(
            CHAT_ID,
            f"⚠️ {user.full_name}, повідомлення замале",
            disable_notification=True,
        )

        await asyncio.sleep(5)
        try:
            await warn.delete()
        except:
            pass


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("analitik", analitik))
    app.add_handler(MessageHandler(filters.ALL, test_guard))

    print("✅ БОТ ЗАПУЩЕНИЙ")
    app.run_polling()


if __name__ == "__main__":
    main()
