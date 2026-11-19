from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)
import os
import html
import regex as re
import asyncio
import sqlite3
import json
import secrets
import hmac
import hashlib
from urllib.parse import parse_qsl
from aiohttp import web
from datetime import datetime, timedelta


# ================= НАЛАШТУВАННЯ =================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не знайдено в Railway Variables")

CHAT_ID = -1002190311306  # ID твоєї групи

CHANNEL_ID = -1002375622983  # ID офіційного каналу
CHANNEL_LINK = "https://t.me/robota_kiev_workk"

MIN_TEXT_LEN = 50
MAX_EMOJI = 8
MUTE_HOURS = 6
KIEV_OFFSET = timedelta(hours=3)

warn_short_text = set()
daily_message_id = None


# ================= СПІЛЬНА КАРТА =================

MAP_DB = "/data/markers.db"
MAP_PORT = int(os.getenv("PORT", "8080"))
MAP_WEBAPP_URL = "https://voron96.github.io/telegram-bot/"
MAP_START_PHOTO_URL = "https://voron96.github.io/telegram-bot/map-start.png"


def init_map_db():
    os.makedirs("/data", exist_ok=True)

    with sqlite3.connect(MAP_DB) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS vacancy_markers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                label TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                button_message_id INTEGER,
                is_closed INTEGER NOT NULL DEFAULT 0
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS pending_map_requests (
                request_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                button_message_id INTEGER
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS chat_permissions (
                chat_id INTEGER PRIMARY KEY,
                permissions_json TEXT NOT NULL
            )
        """)

        marker_columns = [
            row[1]
            for row in db.execute(
                "PRAGMA table_info(vacancy_markers)"
            ).fetchall()
        ]

        if "button_message_id" not in marker_columns:
            db.execute("""
                ALTER TABLE vacancy_markers
                ADD COLUMN button_message_id INTEGER
            """)

        if "is_closed" not in marker_columns:
            db.execute("""
                ALTER TABLE vacancy_markers
                ADD COLUMN is_closed INTEGER NOT NULL DEFAULT 0
            """)

        pending_columns = [
            row[1]
            for row in db.execute(
                "PRAGMA table_info(pending_map_requests)"
            ).fetchall()
        ]

        if "button_message_id" not in pending_columns:
            db.execute("""
                ALTER TABLE pending_map_requests
                ADD COLUMN button_message_id INTEGER
            """)

    print("MAP DATABASE READY ✅")
    
# ================= ВИДАЛЕННЯ ПРОСТРОЧЕНОЇ КНОПКИ =================

async def expire_map_request(context, request_id, chat_id, button_message_id):
    await asyncio.sleep(300)

    with sqlite3.connect(MAP_DB) as db:
        row = db.execute("""
            SELECT request_id
            FROM pending_map_requests
            WHERE request_id = ?
        """, (request_id,)).fetchone()

        if row:
            db.execute("""
                DELETE FROM pending_map_requests
                WHERE request_id = ?
            """, (request_id,))

    if row:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=button_message_id
            )
        except Exception as error:
            print("EXPIRED MAP BUTTON DELETE ERROR:", error)

async def cleanup_expired_map_requests(app):
    while True:
        try:
            now = datetime.utcnow().isoformat()

            with sqlite3.connect(MAP_DB) as db:
                rows = db.execute("""
                    SELECT request_id, chat_id, button_message_id
                    FROM pending_map_requests
                    WHERE expires_at <= ?
                """, (now,)).fetchall()

            for request_id, chat_id, button_message_id in rows:
                if button_message_id:
                    try:
                        await app.bot.delete_message(
                            chat_id=chat_id,
                            message_id=button_message_id
                        )
                    except Exception as error:
                        print("EXPIRED MAP BUTTON CLEANUP ERROR:", error)

                with sqlite3.connect(MAP_DB) as db:
                    db.execute("""
                        DELETE FROM pending_map_requests
                        WHERE request_id = ?
                    """, (request_id,))

        except Exception as error:
            print("PENDING MAP REQUEST CLEANUP ERROR:", error)

        await asyncio.sleep(30)

# ================= КНОПКА ДОДАВАННЯ МІТКИ =================

async def add_pin_button(update, context):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user or user.is_bot:
        return

    if msg.chat_id != CHAT_ID:
        return

    if msg.sender_chat:
        return

    if msg.text and msg.text.startswith("/"):
        return

    request_id = secrets.token_urlsafe(8)

    expires = (
        datetime.utcnow() + timedelta(minutes=5)
    ).isoformat()

    message_text = (
        msg.text or msg.caption or "[Повідомлення без тексту]"
    )

    try:
        app_url = (
            f"https://t.me/PartTimeJobHub_bot_bot"
            f"?startapp={request_id}"
        )

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📍 Розмістити оголошення на карті",
                url=app_url
            )
        ]])

        sent = await msg.reply_text(
            "🟢 PartTimeJobHub",
            reply_markup=keyboard,
            disable_notification=True
        )

        with sqlite3.connect(MAP_DB) as db:
            db.execute("""
                INSERT INTO pending_map_requests
                (request_id, user_id, chat_id, message_id, text,
                 expires_at, button_message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id,
                user.id,
                msg.chat_id,
                msg.message_id,
                message_text,
                expires,
                sent.message_id
            ))

        asyncio.create_task(
            expire_map_request(
                context,
                request_id,
                msg.chat_id,
                sent.message_id
            )
        )

    except Exception as error:
        print("MAP BUTTON ERROR:", error)

# ================= НАТИСКАННЯ КНОПКИ =================

async def map_button_callback(update, context):
    query = update.callback_query
    request_id = query.data.replace("map:", "", 1)

    with sqlite3.connect(MAP_DB) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("""
            SELECT * FROM pending_map_requests
            WHERE request_id = ?
        """, (request_id,)).fetchone()

    if not row:
        await query.answer(
            "Цей запит уже недоступний.",
            show_alert=True
        )
        return

    if row["user_id"] != query.from_user.id:
        await query.answer(
            "Ця кнопка доступна лише автору оголошення.",
            show_alert=True
        )
        return

    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        await query.answer(
            "Час дії кнопки минув.",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Відкрити карту та поставити мітку",
            web_app=WebAppInfo(
                url=MAP_WEBAPP_URL + "?mode=vacancy&request_id=" + request_id
            )
        )
    ]])

    try:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="📍 Відкрий карту, щоб поставити позначку вакансії.",
            reply_markup=keyboard,
            disable_notification=True
        )

        await query.answer("Перевір приватні повідомлення бота.")

    except Exception as error:
        print("MAP PRIVATE MESSAGE ERROR:", error)
        await query.answer(
            "Спочатку відкрий приватний чат із ботом і натисни /start.",
            show_alert=True
        )

# ================= ЗБЕРЕЖЕННЯ ВИБРАНОЇ ТОЧКИ =================

# ================= ПЕРЕВІРКА TELEGRAM WEBAPP =================

def verify_webapp_data(init_data):
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))

        received_hash = parsed.pop("hash", None)

        if not received_hash:
            return None

        auth_date = int(parsed.get("auth_date", "0"))

        if datetime.utcnow().timestamp() - auth_date > 86400:
            return None

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(parsed.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        user_data = json.loads(parsed.get("user", "{}"))

        return user_data

    except Exception as error:
        print("WEBAPP VERIFY ERROR:", error)
        return None

# ================= ЗАХИСТ РЕЖИМУ БОГА =================

map_admin_sessions = {}


# Вхід у режим бога
async def admin_unlock(request):
    try:
        data = await request.json()

        user = verify_webapp_data(data.get("initData", ""))

        if not user:
            return web.json_response(
                {"error": "Не вдалося перевірити Telegram"},
                status=403
            )

        admin_id = os.getenv("MAP_ADMIN_USER_ID", "")

        if str(user.get("id")) != admin_id:
            return web.json_response(
                {"error": "Доступ заборонено"},
                status=403
            )

        saved_password = os.getenv("MAP_ADMIN_PASSWORD", "")
        entered_password = str(data.get("password", ""))

        if not saved_password:
            return web.json_response(
                {"error": "Пароль не налаштований"},
                status=500
            )

        if not hmac.compare_digest(entered_password, saved_password):
            return web.json_response(
                {"error": "Неправильний пароль"},
                status=403
            )

        session_token = secrets.token_urlsafe(32)

        map_admin_sessions[session_token] = (
            int(user["id"]),
            datetime.utcnow() + timedelta(minutes=30)
        )

        return web.json_response({
            "success": True,
            "session": session_token
        })

    except Exception as error:
        print("ADMIN UNLOCK ERROR:", error)
        return web.json_response(
            {"error": "Помилка авторизації"},
            status=500
        )


# Видалення спільної мітки
async def admin_delete_marker(request):
    try:
        data = await request.json()

        user = verify_webapp_data(data.get("initData", ""))

        if not user:
            return web.json_response(
                {"error": "Не вдалося перевірити Telegram"},
                status=403
            )

        admin_id = os.getenv("MAP_ADMIN_USER_ID", "")

        if str(user.get("id")) != admin_id:
            return web.json_response(
                {"error": "Доступ заборонено"},
                status=403
            )

        session_token = str(data.get("session", ""))
        session = map_admin_sessions.get(session_token)

        if not session or session[0] != int(user["id"]):
            return web.json_response(
                {"error": "Потрібно знову ввести пароль"},
                status=403
            )

        if datetime.utcnow() > session[1]:
            map_admin_sessions.pop(session_token, None)

            return web.json_response(
                {"error": "Час авторизації минув"},
                status=403
            )

        marker_id = int(data.get("marker_id", 0))

        if marker_id <= 0:
            return web.json_response(
                {"error": "Некоректний номер мітки"},
                status=400
            )

        with sqlite3.connect(MAP_DB) as db:
            db.row_factory = sqlite3.Row

            row = db.execute("""
                SELECT chat_id, button_message_id
                FROM vacancy_markers
                WHERE id = ?
            """, (marker_id,)).fetchone()

            if not row:
                return web.json_response(
                    {"error": "Мітку не знайдено"},
                    status=404
                )

            chat_id = row["chat_id"]
            button_message_id = row["button_message_id"]

            db.execute("""
                DELETE FROM vacancy_markers
                WHERE id = ?
            """, (marker_id,))

        if map_bot and chat_id and button_message_id:
            try:
                await map_bot.delete_message(
                    chat_id=chat_id,
                    message_id=button_message_id
                )
            except Exception as error:
                print("ADMIN DELETE BUTTON ERROR:", error)

        return web.json_response({
            "success": True
        })

    except Exception as error:
        print("ADMIN DELETE ERROR:", error)
        return web.json_response(
            {"error": "Помилка видалення мітки"},
            status=500
        )

# ================= ЗАПУСК API-СЕРВЕРА =================

# Збереження вибраної позначки
async def save_map_marker(request):
    try:
        data = await request.json()

        init_data = data.get("initData", "")
        user = verify_webapp_data(init_data)

        if not user:
            return web.json_response(
                {"error": "Не вдалося перевірити користувача"},
                status=403
            )

        request_id = str(data.get("request_id", ""))
        latitude = float(data["lat"])
        longitude = float(data["lon"])
        label = str(data.get("label", ""))[:200]

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return web.json_response(
                {"error": "Некоректні координати"},
                status=400
            )

        marker_id = None
        button_message_id = None
        chat_id = None

        with sqlite3.connect(MAP_DB) as db:
            db.row_factory = sqlite3.Row

            row = db.execute("""
                SELECT * FROM pending_map_requests
                WHERE request_id = ?
            """, (request_id,)).fetchone()

            if not row:
                return web.json_response(
                    {"error": "Запит не знайдено"},
                    status=404
                )

            if row["user_id"] != int(user["id"]):
                return web.json_response(
                    {"error": "Це оголошення належить іншому користувачу"},
                    status=403
                )

            if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
                return web.json_response(
                    {"error": "Час дії запиту минув"},
                    status=410
                )

            created = datetime.utcnow()
            expires = created + timedelta(hours=8)

            button_message_id = row["button_message_id"]
            chat_id = row["chat_id"]

            cursor = db.execute("""
                INSERT INTO vacancy_markers
                (
                    user_id, chat_id, message_id, text,
                    latitude, longitude, label,
                    created_at, expires_at,
                    button_message_id, is_closed
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                user["id"],
                row["chat_id"],
                row["message_id"],
                row["text"],
                latitude,
                longitude,
                label,
                created.isoformat(),
                expires.isoformat(),
                button_message_id
            ))

            marker_id = cursor.lastrowid

            db.execute("""
                DELETE FROM pending_map_requests
                WHERE request_id = ?
            """, (request_id,))

        # ----- ЗАМІНА СТАРОЇ КНОПКИ -----
        if map_bot and button_message_id and marker_id:
            try:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🗺 Переглянути оголошення на карті",
                        url=f"https://t.me/PartTimeJobHub_bot_bot?startapp=marker_{marker_id}"
                    )
                ]])

                await map_bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=button_message_id,
                    reply_markup=keyboard
                )

            except Exception as error:
                print("MAP BUTTON UPDATE ERROR:", error)

        return web.json_response(
            {
                "success": True,
                "marker_id": marker_id
            },
            headers={"Access-Control-Allow-Origin": "*"}
        )

    except Exception as error:
        print("MAP SAVE ERROR:", error)

        return web.json_response(
            {"error": "Помилка збереження позначки"},
            status=500
        )


# Дозвіл на запити з GitHub Pages
async def map_options(request):
    return web.Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        }
    )

@web.middleware
async def map_cors_middleware(request, handler):
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# ================= API СПІЛЬНОЇ КАРТИ =================

async def get_map_markers(request):
    now = datetime.utcnow().isoformat()

    with sqlite3.connect(MAP_DB) as db:
        db.row_factory = sqlite3.Row

        rows = db.execute("""
            SELECT id, text, latitude, longitude, label,
                   message_id, created_at, expires_at, is_closed
            FROM vacancy_markers
            WHERE expires_at > ?
            ORDER BY created_at DESC
        """, (now,)).fetchall()

    markers = [dict(row) for row in rows]

    return web.json_response(
        {"markers": markers},
        headers={"Access-Control-Allow-Origin": "*"}
    )
    
async def start_map_server():
    init_map_db()

    app = web.Application(
        middlewares=[map_cors_middleware]
    )

    # Далі залишаються всі твої старі маршрути:
    # /api/markers
    # /api/admin/unlock
    # /api/admin/delete-marker

    # Завантаження спільних позначок
    app.router.add_get(
        "/api/markers",
        get_map_markers
    )

    # Збереження нової позначки
    app.router.add_post(
        "/api/markers",
        save_map_marker
    )

    # Дозвіл на запити з GitHub Pages
    app.router.add_options(
        "/api/markers",
        map_options
    )
    
    # Вхід у режим бога
    app.router.add_post(
        "/api/admin/unlock",
        admin_unlock
    )

    app.router.add_options(
        "/api/admin/unlock",
        map_options
    )

    # Видалення спільної мітки
    app.router.add_post(
        "/api/admin/delete-marker",
        admin_delete_marker
    )

    app.router.add_options(
        "/api/admin/delete-marker",
        map_options
    )

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        MAP_PORT
    )

    await site.start()

    print(f"MAP SERVER STARTED ON PORT {MAP_PORT} ✅")

    return runner


# ================= ПІДРАХУНОК ЕМОДЗІ =================

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
        
# ================= ЗАХИСТ ВІД СТОРОННІХ БОТІВ =================
async def ban_non_admin_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if not msg or not msg.new_chat_members:
        return

    for new_user in msg.new_chat_members:
        if not new_user.is_bot:
            continue

        try:
            member = await context.bot.get_chat_member(
                CHAT_ID,
                new_user.id
            )

            # Ботів-адміністраторів не чіпаємо
            if member.status in ("administrator", "creator"):
                continue

            # Видаляємо бота без прав адміністратора
            await context.bot.ban_chat_member(
                chat_id=CHAT_ID,
                user_id=new_user.id
            )

            print(f"BOT REMOVED: {new_user.username or new_user.id}")

        except Exception as e:
            print("BOT PROTECTION ERROR:", e)
            
# ================= МОДЕРАЦІЯ =================
LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|telegram\.dog/)",
    re.IGNORECASE
)

GOOGLE_MAPS_RE = re.compile(
    r"(https?://)?(www\.)?"
    r"(maps\.google\.com|google\.[a-z.]+/maps|"
    r"goo\.gl/maps|maps\.app\.goo\.gl)",
    re.IGNORECASE
)

async def main_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or update.effective_chat.id != CHAT_ID:
        return

    if update.edited_message or update.edited_channel_post:
        return

    user = update.effective_user
    msg = update.effective_message
    text = msg.text or msg.caption or ""

    # ----- ПОВІДОМЛЕННЯ З ОФІЦІЙНОГО КАНАЛУ -----
    if msg.sender_chat and msg.sender_chat.id == CHANNEL_ID:
        try:
            await context.bot.unpin_chat_message(
                chat_id=CHAT_ID,
                message_id=msg.message_id
            )
        except Exception as error:
            print("UNPIN CHANNEL ERROR:", error)

        try:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text='⬆️ <a href="https://t.me/robota_kiev_workk"><b>Повідомлення з КАНАЛУ ↗️</b></a>',
                parse_mode="HTML",
                disable_notification=True,
                disable_web_page_preview=True
            )
        except Exception as error:
            print("CHANNEL NOTICE ERROR:", error)

        return

    # ----- JOIN / LEFT -----
    if msg.new_chat_members or msg.left_chat_member:
        try:
            await msg.delete()
        except Exception:
            pass
        return

    if not user or user.is_bot or msg.sender_chat:
        return

    # ----- ПЕРЕВІРКА АДМІНІВ -----
    try:
        member = await context.bot.get_chat_member(CHAT_ID, user.id)

        if member.status in ("administrator", "creator"):
            await add_pin_button(update, context)
            return

    except Exception as error:
        print("ADMIN CHECK ERROR:", error)

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

    # ----- КНОПКА ДОДАВАННЯ НА КАРТУ -----
    await add_pin_button(update, context)

# ================= ОНОВЛЕННЯ СТАТУСУ ВАКАНСІЇ НА КАРТІ =================

CLOSED_VACANCY_RE = re.compile(
    r"(?<!\w)(?:закрит\w*|закрив\w*|закрила\w*|закрили\w*|"
    r"закриваю\w*|закриваємо\w*|не\s+актуально|неактуально)(?!\w)",
    re.IGNORECASE
)


async def handle_edited_vacancy(update, context):
    msg = update.edited_message

    if not msg or msg.chat_id != CHAT_ID:
        return

    if msg.sender_chat:
        return

    text = msg.text or msg.caption or ""
    is_closed = 1 if CLOSED_VACANCY_RE.search(text) else 0

    now = datetime.utcnow().isoformat()

    with sqlite3.connect(MAP_DB) as db:
        db.row_factory = sqlite3.Row

        marker = db.execute("""
            SELECT id, button_message_id
            FROM vacancy_markers
            WHERE chat_id = ?
              AND message_id = ?
              AND expires_at > ?
            LIMIT 1
        """, (
            msg.chat_id,
            msg.message_id,
            now
        )).fetchone()

        if not marker:
            return

        db.execute("""
            UPDATE vacancy_markers
            SET text = ?, is_closed = ?
            WHERE id = ?
        """, (
            text or "[Повідомлення без тексту]",
            is_closed,
            marker["id"]
        ))

        button_message_id = marker["button_message_id"]

    # ----- КНОПКА ДЛЯ АКТИВНОЇ ВАКАНСІЇ -----

    if not map_bot:
        return

    try:
        if is_closed:

            # Видаляємо повідомлення бота повністю
            if button_message_id:
                try:
                    await map_bot.delete_message(
                        chat_id=msg.chat_id,
                        message_id=button_message_id
                    )
                except Exception as error:
                    print("MAP BUTTON DELETE ERROR:", error)

                # Запам'ятовуємо, що повідомлення видалене
                with sqlite3.connect(MAP_DB) as db:
                    db.execute("""
                        UPDATE vacancy_markers
                        SET button_message_id = NULL
                        WHERE id = ?
                    """, (marker["id"],))

        else:

            # Створюємо кнопку переходу на карту
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🗺 Переглянути оголошення на карті",
                    url=f"https://t.me/PartTimeJobHub_bot_bot?startapp=marker_{marker['id']}"
                )
            ]])

            if button_message_id:

                # Якщо повідомлення ще існує — оновлюємо кнопку
                await map_bot.edit_message_reply_markup(
                    chat_id=msg.chat_id,
                    message_id=button_message_id,
                    reply_markup=keyboard
                )

            else:

                # Якщо вакансію відкрили повторно —
                # створюємо нове повідомлення бота під оголошенням
                sent = await msg.reply_text(
                    "🟢 PartTimeJobHub",
                    reply_markup=keyboard,
                    disable_notification=True
                )

                # Зберігаємо ID нового повідомлення
                with sqlite3.connect(MAP_DB) as db:
                    db.execute("""
                        UPDATE vacancy_markers
                        SET button_message_id = ?
                        WHERE id = ?
                    """, (
                        sent.message_id,
                        marker["id"]
                    ))

    except Exception as error:
        print("MAP BUTTON UPDATE ERROR:", error)

    print(
        f"MAP VACANCY UPDATED: {marker['id']} | CLOSED: {is_closed}"
    )

    
# ================= ЩОДЕННЕ ПОВІДОМЛЕННЯ =================
async def send_daily_message(bot):
    global daily_message_id

    if daily_message_id:
        try:
            await bot.delete_message(CHAT_ID, daily_message_id)
        except:
            pass

    text = (
    "👋 <b>Вітаємо у PartTimeJobHub!</b>\n\n"

    '📋 Перед публікацією оголошення ознайомтеся з '
    '<a href="https://telegram.me/kiev_part_time_job/68858"><b>правилами ↗️</b></a> '
    'та дотримуйтесь їх 🫡\n\n'

    "⚠️ За порушення правил бот або адміністрація можуть обмежити можливість "
    "публікації оголошень без додаткового попередження.\n\n"

    "✅ <b>Статус «Верифікований»</b> — це надійний замовник, який дотримується всіх зазначених умов.\n\n"

    "💬 <b>«Чат Київ»</b> — спілкування учасників та чорний список.\n"
    "📢 <b>«Канал»</b> — вакансії від перевірених замовників."
)

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💬 Чат Києва",
                url="https://t.me/kiev_shat"
            ),
            InlineKeyboardButton(
                "📢 Канал ↗️",
                url="https://t.me/robota_kiev_workk"
            )
        ]
    ])

    msg = await bot.send_message(
        CHAT_ID,
        text,
        parse_mode="HTML",
        disable_notification=True,
        disable_web_page_preview=True,
        reply_markup=kb
    )

    daily_message_id = msg.message_id

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


map_runner = None
map_bot = None

background_tasks = set()


def create_background_task(coro):
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task


async def post_init(app):
    global map_runner, map_bot

    await app.bot.delete_webhook(drop_pending_updates=True)

    map_bot = app.bot

    map_runner = await start_map_server()

    create_background_task(daily_scheduler(app))
    create_background_task(expire_vacancy_buttons(app))
    create_background_task(cleanup_expired_map_requests(app))

async def post_shutdown(app):
    global map_runner, map_bot

    for task in list(background_tasks):
        task.cancel()

    if background_tasks:
        await asyncio.gather(
            *background_tasks,
            return_exceptions=True
        )

    background_tasks.clear()

    if map_runner:
        await map_runner.cleanup()
        map_runner = None

    map_bot = None

    print("MAP SERVER STOPPED ✅")

# ================= АВТОМАТИЧНЕ ПРИБИРАННЯ КНОПОК ЧЕРЕЗ 8 ГОДИН =================

async def expire_vacancy_buttons(app):
    while True:
        try:
            now = datetime.utcnow().isoformat()

            with sqlite3.connect(MAP_DB) as db:
                rows = db.execute("""
                    SELECT id, chat_id, button_message_id
                    FROM vacancy_markers
                    WHERE expires_at <= ?
                    AND button_message_id IS NOT NULL
                """, (now,)).fetchall()

            for marker_id, chat_id, button_message_id in rows:
                try:
                    await app.bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=button_message_id,
                        reply_markup=None
                    )
                except Exception as error:
                    print("EXPIRED VACANCY BUTTON ERROR:", error)

                with sqlite3.connect(MAP_DB) as db:
                    db.execute("""
                        UPDATE vacancy_markers
                        SET button_message_id = NULL
                        WHERE id = ?
                    """, (marker_id,))

        except Exception as error:
            print("VACANCY BUTTON CLEANUP ERROR:", error)

        await asyncio.sleep(60)     

async def post_init(app):
    global map_runner, map_bot

    await app.bot.delete_webhook(drop_pending_updates=True)

    map_bot = app.bot

    map_runner = await start_map_server()

    create_background_task(daily_scheduler(app))
    create_background_task(expire_vacancy_buttons(app))
    create_background_task(cleanup_expired_map_requests(app))

# ================= ОГОЛОШЕННЯ КАРТИ =================

def map_announcement_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🗺 ВІДКРИТИ КАРТУ",
                url="https://t.me/PartTimeJobHub_bot_bot?startapp"
            )
        ]
    ])


def map_announcement_caption():
    return None


def map_announcement_photo_path():
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "docs",
        "map-start.png"
    )


async def send_map_announcement(bot, chat_id):
    with open(map_announcement_photo_path(), "rb") as photo:
        return await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=map_announcement_caption(),
            reply_markup=map_announcement_keyboard(),
            disable_notification=True
        )

# ================= ЗАПУСК КАРТИ =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_map_announcement(
        context.bot,
        update.effective_chat.id
    )
    
# ================= КЕРУВАННЯ ПУБЛІКАЦІЯМИ =================

OWNER_ID = int(os.getenv("MAP_ADMIN_USER_ID", "0"))


# ================= АВТОРИЗАЦІЯ ЧЕРЕЗ TELEGRAM =================

async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    if not user:
        return

    admin_sessions.discard(user.id)
    admin_password_wait.add(user.id)

    await update.effective_message.reply_text(
        "🔐 Введіть пароль адміністратора:"
    )


async def check_admin_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message

    if not user or update.effective_chat.type != "private":
        return

    if user.id not in admin_password_wait:
        return

    entered_password = message.text.strip()
    admin_password_wait.discard(user.id)

    context.user_data["skip_publication_message_id"] = message.message_id

    try:
        await message.delete()
    except Exception:
        pass

    saved_password = os.getenv("MAP_ADMIN_PASSWORD", "")

    if not saved_password:
        await context.bot.send_message(
            chat_id=user.id,
            text="❌ Пароль адміністратора не налаштований у Railway."
        )
        return

    if not hmac.compare_digest(entered_password, saved_password):
        await context.bot.send_message(
            chat_id=user.id,
            text="❌ Неправильний пароль. Напишіть /admin для повторної спроби."
        )
        return

    admin_sessions.add(user.id)

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            "✅ Авторизація успішна!\n\n"
            "Доступні команди:\n\n"
            "/post — створити публікацію\n"
            "/cancel — скасувати створення публікації\n"
            "/publish — опублікувати оголошення в каналі\n"
            "/chat_off — закрити групу для публікацій\n"
            "/chat_on — відкрити групу для публікацій"
        )
    )
    
# ================= АВТОРИЗАЦІЯ АДМІНІСТРАТОРА =================

admin_sessions = set()
admin_password_wait = set()


async def rozmistyty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (
        update.effective_chat.type != "private"
        or not update.effective_user
        or update.effective_user.id != OWNER_ID
    ):
        return

    if update.effective_user.id not in admin_sessions:
        return

    context.user_data["waiting_for_publication"] = True

    await update.effective_message.reply_text(
        "📝 Надішли текст публікації.\n\n"
        "Для кнопки карти напиши окремим рядком:\n"
        "/кнопка/\n\n"
        "Для клікабельного посилання напиши:\n"
        "Назва посилання /посилання https://адреса/\n\n"
        "Скасувати можна командою /cancel."
    )

async def cancel_publication(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (
        update.effective_chat.type != "private"
        or not update.effective_user
        or update.effective_user.id != OWNER_ID
    ):
        return

    if update.effective_user.id not in admin_sessions:
        return

    context.user_data["waiting_for_publication"] = False
    admin_sessions.discard(update.effective_user.id)

    await update.effective_message.reply_text(
        "Створення публікації скасовано."
    )

async def receive_publication(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (
        update.effective_message
        and context.user_data.get("skip_publication_message_id")
        == update.effective_message.message_id
    ):
        context.user_data.pop("skip_publication_message_id", None)
        return

    if (
        update.effective_chat.type != "private"
        or not update.effective_user
        or update.effective_user.id != OWNER_ID
        or update.effective_user.id not in admin_sessions
        or not context.user_data.get("waiting_for_publication")
    ):
        return

    raw_text = update.effective_message.text.strip()

    if not raw_text:
        return

    if len(raw_text) > 4096:
        await update.effective_message.reply_text(
            "❌ Текст задовгий. Максимум — 4096 символів."
        )
        return

    lines = raw_text.splitlines()
    result_lines = []
    buttons = []

    for line in lines:
        if line.strip() == "/кнопка/":
            buttons.append(
                InlineKeyboardButton(
                    "🗺 КАРТА",
                    url="https://t.me/PartTimeJobHub_bot_bot?startapp"
                )
            )
            continue

        match = re.match(
            r"^(.*?)\s*/посилання\s+(https?://\S+?)/\s*$",
            line.strip(),
            re.IGNORECASE
        )

        if match:
            link_text = match.group(1).strip()
            link_url = match.group(2).strip()

            if link_text and link_url:
                result_lines.append(
                    f'<a href="{html.escape(link_url, quote=True)}">'
                    f'{html.escape(link_text)}</a>'
                )
                continue

        result_lines.append(html.escape(line))

    final_text = "\n".join(result_lines).strip()

    if not final_text:
        await update.effective_message.reply_text(
            "❌ Додай текст публікації."
        )
        return

    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

    try:
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=final_text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_notification=True,
            disable_web_page_preview=True
        )

        context.user_data["waiting_for_publication"] = False
        admin_sessions.discard(update.effective_user.id)

        await update.effective_message.reply_text(
            "✅ Публікацію розміщено в групі."
        )

    except Exception as error:
        print("PUBLICATION ERROR:", repr(error))

        await update.effective_message.reply_text(
            "❌ Не вдалося опублікувати. Перевір текст і посилання."
        )

    # ================= ЗАКРИТТЯ ТА ВІДКРИТТЯ ГРУПИ =================

async def chat_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if (
        update.effective_chat.type != "private"
        or not user
        or user.id != OWNER_ID
        or user.id not in admin_sessions
    ):
        return

    try:
        chat = await context.bot.get_chat(CHAT_ID)

        permissions = chat.permissions

        if permissions is None:
            await update.effective_message.reply_text(
                "❌ Не вдалося отримати поточні дозволи групи."
            )
            return

        saved_permissions = permissions.to_dict()

        with sqlite3.connect(MAP_DB) as db:
            existing = db.execute(
                "SELECT permissions_json FROM chat_permissions WHERE chat_id = ?",
                (CHAT_ID,)
            ).fetchone()

            if existing is None:
                db.execute(
                    """
                    INSERT INTO chat_permissions (chat_id, permissions_json)
                    VALUES (?, ?)
                    """,
                    (CHAT_ID, json.dumps(saved_permissions))
                )

        await context.bot.set_chat_permissions(
            chat_id=CHAT_ID,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
        )

        admin_sessions.discard(user.id)

        await update.effective_message.reply_text(
            "🔒 Групу закрито для публікацій учасників.\n"
            "Адміністратори можуть продовжувати писати."
        )

    except Exception as error:
        print("CHAT OFF ERROR:", repr(error))
        await update.effective_message.reply_text(
            "❌ Не вдалося закрити групу. Перевір права бота адміністратора."
        )

async def chat_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if (
        update.effective_chat.type != "private"
        or not user
        or user.id not in admin_sessions
    ):
        return

    try:
        with sqlite3.connect(MAP_DB) as db:
            saved = db.execute(
                "SELECT permissions_json FROM chat_permissions WHERE chat_id = ?",
                (CHAT_ID,)
            ).fetchone()

        if saved is None:
            await update.effective_message.reply_text(
                "ℹ️ Немає збережених налаштувань. Спочатку потрібно закрити групу командою /chat_off."
            )
            return

        saved_permissions = json.loads(saved[0])

        # Видаляємо застарілий параметр, який не підтримує бібліотека
        saved_permissions.pop("can_send_media_messages", None)

        await context.bot.set_chat_permissions(
            chat_id=CHAT_ID,
            permissions=ChatPermissions(**saved_permissions)
        )

        with sqlite3.connect(MAP_DB) as db:
            db.execute(
                "DELETE FROM chat_permissions WHERE chat_id = ?",
                (CHAT_ID,)
            )

        admin_sessions.discard(user.id)

        await update.effective_message.reply_text(
            "🔓 Групу відкрито. Попередні дозволи учасників відновлено."
        )

    except Exception as error:
        print("CHAT ON ERROR:", repr(error))
        await update.effective_message.reply_text(
            "❌ Не вдалося відкрити групу. Перевір права бота адміністратора."
        )

# ================= КІНЕЦЬ КЕРУВАННЯ ГРУПОЮ =================

# ================= ПУБЛІКАЦІЯ ОГОЛОШЕННЯ =================

async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    if (
        not update.effective_user
        or update.effective_user.id != OWNER_ID
    ):
        return

    if update.effective_user.id not in admin_sessions:
        return

    try:
        await send_map_announcement(context.bot, CHANNEL_ID)

        admin_sessions.discard(update.effective_user.id)

        await update.effective_message.reply_text(
            "✅ Оголошення опубліковано в каналі.",
            disable_notification=True
        )

    except Exception as e:
        print(f"ПОМИЛКА ПУБЛІКАЦІЇ В КАНАЛ: {repr(e)}")

        await update.effective_message.reply_text(
            f"❌ Помилка публікації в канал: {e}"
        )

# ================= КІНЕЦЬ ПУБЛІКАЦІЇ =================

# ================= ЗАПУСК =================

def main():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            ban_non_admin_bots
        ),
        group=-1
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    # Команда входу в адміністративну панель
    app.add_handler(
        CommandHandler("admin", admin_login)
    )

    # Перевірка пароля адміністратора
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            check_admin_password
        ),
        group=-3
    )

    app.add_handler(
        CommandHandler("post", rozmistyty)
    )

    app.add_handler(
        CommandHandler("cancel", cancel_publication)
    )

    # Отримання тексту для публікації
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            receive_publication
        ),
        group=-2
    )

    app.add_handler(
        CommandHandler("publish", publish)
    )

    # Закриття та відкриття групи
    app.add_handler(
        CommandHandler("chat_off", chat_off)
    )

    app.add_handler(
        CommandHandler("chat_on", chat_on)
    )
    
    app.add_handler(
        CallbackQueryHandler(
            map_button_callback,
            pattern=r"^map:"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ALL,
            main_moderation
        ),
        group=0
    )

    # Обробка редагування оголошень на карті
    app.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & filters.Chat(CHAT_ID),
            handle_edited_vacancy
        ),
        group=1
    )

    print("BOT STARTED ✅")

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
