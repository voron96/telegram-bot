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

   kb = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📢 Канал", url="https://t.me/robota_kiev_workk"),
        InlineKeyboardButton("💬 Чат", url="https://t.me/kiev_shat")
    ]
])

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

if name == "__main__":
    main()
