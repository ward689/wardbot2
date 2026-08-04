import asyncio
import time
import re
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, ADMIN_IDS, ADMIN_LEVELS, LOG_CHANNEL_ID, VIOLENCE_WORDS, BAD_WORDS, WHITELIST_DOMAINS
from database import *
from aiohttp import web

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
current_action = {}
target_user = {}
pending_polls = {}

# === ПОЛУЧИТЬ ID ПО USERNAME ===
async def get_user_id_by_username(username: str) -> int:
    try:
        username = username.replace('@', '').strip()
        if not username:
            return None
        try:
            user = await bot.get_user(username)
            if user and user.id:
                return user.id
        except:
            pass
        try:
            chat = await bot.get_chat(f"@{username}")
            if chat and chat.id:
                return chat.id
        except:
            pass
        return None
    except:
        return None

# === ПОЛУЧИТЬ USERNAME ПО ID ===
async def get_username_by_id(user_id: int) -> str:
    try:
        user = await bot.get_user(user_id)
        if user and user.username:
            return f"@{user.username}"
        return str(user_id)
    except:
        return str(user_id)

# === АВТОУДАЛЕНИЕ ===
async def delete_after(msg, seconds=10):
    await asyncio.sleep(seconds)
    try:
        await msg.delete()
    except:
        pass

# === ПРОВЕРКА УГРОЗ ===
def has_violence(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    for w in VIOLENCE_WORDS:
        if w in t:
            return True
    clean = re.sub(r'[.,!?;:\s]+', '', t)
    for w in VIOLENCE_WORDS:
        if re.sub(r'[.,!?;:\s]+', '', w) in clean:
            return True
    return False

# === ПРОВЕРКА МАТА ===
def has_bad_words(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    for w in BAD_WORDS:
        if w in t:
            return True
    return False

# === ПРОВЕРКА ССЫЛОК ===
async def has_blocked_link(text: str) -> bool:
    if not text:
        return False
    url_pattern = r'https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,}'
    links = re.findall(url_pattern, text)
    if not links:
        return False
    whitelist = await get_whitelist_domains()
    for link in links:
        domain = re.sub(r'^https?://', '', link)
        domain = re.sub(r'^www\.', '', domain)
        domain = domain.split('/')[0].split('?')[0].lower()
        is_whitelisted = False
        for wd in whitelist:
            if domain.endswith(wd) or domain == wd:
                is_whitelisted = True
                break
        if not is_whitelisted:
            return True
    return False

# === ОТПРАВКА ЛОГА ===
async def send_log(channel_id: int, action: str, details: str):
    try:
        await bot.send_message(
            LOG_CHANNEL_ID,
            f"📋 **Лог модерации**\n\n"
            f"📢 Канал: `{channel_id}`\n"
            f"🔧 Действие: {action}\n"
            f"📝 Детали: {details}\n"
            f"🕐 Время: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except:
        pass

# === КНОПКИ ===
async def get_admin_keyboard(user_id: int):
    level = await get_user_level(user_id)
    buttons = []
    
    if level >= 2:
        buttons.append([InlineKeyboardButton(text="⚠️ Варн", callback_data="admin_warn")])
        buttons.append([InlineKeyboardButton(text="📋 Варны пользователя", callback_data="admin_check_warns")])
    
    if level >= 3:
        buttons.append([InlineKeyboardButton(text="🔨 Мут", callback_data="admin_mute")])
        buttons.append([InlineKeyboardButton(text="🔕 Тихий мут", callback_data="admin_silent_mute")])
        buttons.append([InlineKeyboardButton(text="🔓 Размут", callback_data="admin_unmute")])
    
    if level >= 4:
        buttons.append([InlineKeyboardButton(text="🗑️ Очистить варны", callback_data="admin_clear_warns")])
        buttons.append([InlineKeyboardButton(text="📊 Статистика чата", callback_data="admin_stats")])
        buttons.append([InlineKeyboardButton(text="📊 Статистика пользователя", callback_data="admin_user_stats")])
    
    if level >= 5:
        buttons.append([InlineKeyboardButton(text="🛡️ Назначить модератора", callback_data="admin_set_moderator")])
    
    if level >= 6:
        buttons.append([InlineKeyboardButton(text="👑 Назначить админа", callback_data="admin_set_admin")])
        buttons.append([InlineKeyboardButton(text="📢 Назначить оператора", callback_data="admin_set_channel_operator")])
        buttons.append([InlineKeyboardButton(text="👑 Назначить главу канала", callback_data="admin_set_channel_owner")])
        buttons.append([InlineKeyboardButton(text="📋 Список операторов", callback_data="admin_list_operators")])
        buttons.append([InlineKeyboardButton(text="🔗 Управление ссылками", callback_data="admin_manage_links")])
        buttons.append([InlineKeyboardButton(text="⚙️ Настройки канала", callback_data="admin_channel_settings")])
        buttons.append([InlineKeyboardButton(text="📋 Логи админов", callback_data="admin_logs")])
    
    if level >= 7:
        buttons.append([InlineKeyboardButton(text="⭐ Управление уровнями", callback_data="admin_set_level")])
    
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# === СТАРТ ===
@dp.message(Command("start"))
async def start(msg: types.Message):
    m = await msg.answer(
        "☀️ *Добро пожаловать!*\n"
        "━" * 25 + "\n\n"
        "✨ Я слежу за порядком в чатах и каналах.\n"
        "🚫 Защищаю от угроз и агрессии.\n"
        "📊 Помогаю админам управлять сообществами.\n\n"
        "📌 *Команды:*\n"
        "👑 `/admin` — панель управления\n"
        "👤 `/myrole` — узнать свою роль\n"
        "📊 `/admins` — список админов\n"
        "📢 `/setup_operator` — настроить оператора\n"
        "👑 `/set_owner` — назначить главу канала\n"
        "🎁 `/daily` — получить бонус\n"
        "📊 `/stats` — статистика чата\n"
        "⚙️ `/settings` — настройки канала\n\n"
        "━" * 25 + "\n"
        "🌴 *Приятного общения!*",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_after(m, 60))

# === DAILY ===
@dp.message(Command("daily"))
async def daily_bonus(msg: types.Message):
    user_id = msg.from_user.id
    can_claim, amount, streak = await get_daily_bonus(user_id)
    if can_claim:
        await claim_daily(user_id)
        await add_karma(user_id, amount // 10)
        m = await msg.answer(
            f"🎁 **Ежедневный бонус!**\n\n"
            f"💰 Получено: {amount} монет\n"
            f"🔥 Стрик: {streak} дней\n"
            f"⭐ Карма +{amount // 10}\n\n"
            f"Приходи завтра! ☀️",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after(m, 30))
    else:
        remaining = 86400 - (int(time.time()) % 86400)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        m = await msg.answer(
            f"⏳ **Бонус уже получен!**\n\n"
            f"Следующий через: {hours}ч {minutes}м\n"
            f"🔥 Стрик: {streak} дней"
        )
        asyncio.create_task(delete_after(m, 20))

# === MYROLE ===
@dp.message(Command("myrole"))
async def my_role(msg: types.Message):
    level = await get_user_level(msg.from_user.id)
    role = await get_user_role(msg.from_user.id)
    karma = await get_karma(msg.from_user.id)
    
    # Проверяем оператора
    ops = []
    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute("SELECT channel_id, channel_name FROM channel_operators WHERE operator_id = ?", (msg.from_user.id,))
        ops = await cursor.fetchall()
    
    # Проверяем главу
    owner = []
    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute("SELECT channel_id FROM channel_owners WHERE owner_id = ?", (msg.from_user.id,))
        owner = await cursor.fetchall()
    
    text = f"👤 **Твоя информация**\n\n"
    text += f"📊 Уровень: {level}\n"
    text += f"👑 Роль: {role}\n"
    text += f"⭐ Карма: {karma}\n"
    
    if ops:
        text += "\n📢 **Ты оператор каналов:**\n"
        for ch_id, ch_name in ops:
            text += f"• {ch_name or ch_id} (`{ch_id}`)\n"
    
    if owner:
        text += "\n👑 **Ты глава каналов:**\n"
        for ch_id in owner:
            text += f"• `{ch_id}`\n"
    
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 30))

# === ADMINS ===
@dp.message(Command("admins"))
async def list_admins(msg: types.Message):
    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute("SELECT user_id, level FROM roles WHERE level > 0 ORDER BY level DESC")
        results = await cursor.fetchall()
    
    if not results:
        m = await msg.answer("📋 Администраторов пока нет")
        asyncio.create_task(delete_after(m, 15))
        return
    
    text = "👑 **Список администраторов:**\n\n"
    for user_id, level in results:
        if level in ADMIN_LEVELS:
            name = ADMIN_LEVELS[level]["name"]
            emoji = ADMIN_LEVELS[level]["emoji"]
            username = await get_username_by_id(user_id)
            text += f"{emoji} Уровень {level}: {name} ({username})\n"
    
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 30))

# === SETTINGS ===
@dp.message(Command("settings"))
async def channel_settings(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 6:
        m = await msg.answer("⛔ Нужен уровень 6+!")
        asyncio.create_task(delete_after(m, 10))
        return
    
    chat_id = msg.chat.id
    settings = await get_channel_settings(chat_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'✅' if settings['enabled'] else '❌'} Модерация",
            callback_data="sett_enabled"
        )],
        [InlineKeyboardButton(
            text=f"⏱️ Длительность мута: {settings['mute_duration']}с",
            callback_data="sett_mute_duration"
        )],
        [InlineKeyboardButton(
            text=f"⚠️ Лимит варнов: {settings['warn_limit']}",
            callback_data="sett_warn_limit"
        )],
        [InlineKeyboardButton(
            text=f"{'✅' if settings['block_new_accounts'] else '❌'} Блокировка новых",
            callback_data="sett_block_new"
        )],
        [InlineKeyboardButton(
            text=f"📊 Показать настройки",
            callback_data="sett_show"
        )]
    ])
    
    m = await msg.answer("⚙️ **Настройки канала**", reply_markup=keyboard, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))

# === ADMIN ===
@dp.message(Command("admin"))
async def admin_panel(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    if level < 2:
        m = await msg.answer("⛔ У тебя нет прав! Минимальный уровень: 2")
        asyncio.create_task(delete_after(m, 10))
        return
    
    role = await get_user_role(user_id)
    keyboard = await get_admin_keyboard(user_id)
    
    m = await msg.answer(
        f"🛡️ *Админ-панель*\n\n"
        f"👤 Твоя роль: {role}\n"
        f"📊 Уровень: {level}\n\n"
        f"Выбери действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# === СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ ===
@dp.callback_query(F.data == "admin_user_stats")
async def user_stats_callback(call: types.CallbackQuery):
    await call.message.answer("📝 Введи ID или @username пользователя:")
    current_action[call.from_user.id] = "user_stats"
    await call.answer()

# === ЛОГИ АДМИНОВ ===
@dp.callback_query(F.data == "admin_logs")
async def admin_logs_callback(call: types.CallbackQuery):
    logs = await get_admin_logs(20)
    if not logs:
        m = await call.message.answer("📋 Логов пока нет")
        asyncio.create_task(delete_after(m, 15))
        await call.answer()
        return
    
    text = "📋 **Логи админов:**\n\n"
    for admin_id, action, target_id, details, date in logs:
        admin_name = await get_username_by_id(admin_id)
        text += f"• {admin_name} → {action}"
        if target_id:
            text += f" (пользователь: {await get_username_by_id(target_id)})"
        if details:
            text += f"\n  📝 {details[:50]}..."
        text += f"\n  🕐 {date[:16]}\n\n"
    
    m = await call.message.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 45))
    await call.answer()

# === ОБРАБОТКА ВСЕХ CALLBACK ===
@dp.callback_query()
async def handle_callbacks(call: types.CallbackQuery):
    user_id = call.from_user.id
    level = await get_user_level(user_id)
    data = call.data
    
    # === ЗАКРЫТИЕ ===
    if data == "admin_close":
        await call.message.delete()
        await call.answer("Закрыто")
        return
    
    # === НАСТРОЙКИ (SETTINGS) ===
    if data.startswith("sett_"):
        action = data.split("_")[1]
        chat_id = call.message.chat.id
        settings = await get_channel_settings(chat_id)
        
        if action == "enabled":
            settings['enabled'] = not settings['enabled']
            await update_channel_settings(chat_id, settings)
            await call.answer(f"✅ Модерация {'включена' if settings['enabled'] else 'выключена'}")
        
        elif action == "block_new":
            settings['block_new_accounts'] = not settings['block_new_accounts']
            await update_channel_settings(chat_id, settings)
            await call.answer(f"✅ Блокировка {'включена' if settings['block_new_accounts'] else 'выключена'}")
        
        elif action == "show":
            text = f"⚙️ **Настройки канала**\n\n"
            text += f"📌 Канал: `{chat_id}`\n"
            text += f"{'✅' if settings['enabled'] else '❌'} Модерация: {'включена' if settings['enabled'] else 'выключена'}\n"
            text += f"⏱️ Длительность мута: {settings['mute_duration']} сек\n"
            text += f"⚠️ Лимит варнов: {settings['warn_limit']}\n"
            text += f"{'✅' if settings['block_new_accounts'] else '❌'} Блокировка новых: {'включена' if settings['block_new_accounts'] else 'выключена'}"
            m = await call.message.answer(text, parse_mode="Markdown")
            asyncio.create_task(delete_after(m, 30))
            await call.answer()
            return
        
        elif action == "mute_duration":
            await call.message.answer("📝 Введи новую длительность мута (в секундах):")
            current_action[user_id] = "set_mute_duration"
            target_user[user_id] = chat_id
            await call.answer()
            return
        
        elif action == "warn_limit":
            await call.message.answer("📝 Введи новый лимит варнов (число):")
            current_action[user_id] = "set_warn_limit"
            target_user[user_id] = chat_id
            await call.answer()
            return
        
        # Обновляем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{'✅' if settings['enabled'] else '❌'} Модерация",
                callback_data="sett_enabled"
            )],
            [InlineKeyboardButton(
                text=f"⏱️ Длительность мута: {settings['mute_duration']}с",
                callback_data="sett_mute_duration"
            )],
            [InlineKeyboardButton(
                text=f"⚠️ Лимит варнов: {settings['warn_limit']}",
                callback_data="sett_warn_limit"
            )],
            [InlineKeyboardButton(
                text=f"{'✅' if settings['block_new_accounts'] else '❌'} Блокировка новых",
                callback_data="sett_block_new"
            )],
            [InlineKeyboardButton(
                text=f"📊 Показать настройки",
                callback_data="sett_show"
            )]
        ])
        try:
            await call.message.edit_reply_markup(reply_markup=keyboard)
        except:
            pass
        await call.answer()
        return
    
    # === АДМИНСКИЕ ДЕЙСТВИЯ ===
    if level < 2:
        await call.answer("⛔ Нет прав!", True)
        return
    
    # === СПИСОК ОПЕРАТОРОВ ===
    if data == "admin_list_operators":
        ops = await get_all_channel_operators()
        if not ops:
            m = await call.message.answer("📋 Операторы не назначены")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = "📢 **Список операторов:**\n\n"
        for ch_id, op_id, op_name, ch_name in ops:
            text += f"📌 Канал: {ch_name or ch_id} (`{ch_id}`)\n"
            text += f"👤 Оператор: `{op_id}`"
            if op_name:
                text += f" (@{op_name})"
            text += "\n\n"
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    # === СТАТИСТИКА ===
    if data == "admin_stats":
        violations = await get_violations_stats(call.message.chat.id, 10)
        if not violations:
            m = await call.message.answer("📊 Статистика пуста")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = "📊 **Статистика нарушений:**\n\n"
        for idx, (uid, count) in enumerate(violations, 1):
            username = await get_username_by_id(uid)
            text += f"{idx}. {username} — {count} нарушений\n"
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    # === УПРАВЛЕНИЕ ССЫЛКАМИ ===
    if data == "admin_manage_links":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список белого списка", callback_data="admin_show_whitelist")],
            [InlineKeyboardButton(text="➕ Добавить домен", callback_data="admin_add_whitelist")],
            [InlineKeyboardButton(text="➖ Удалить домен", callback_data="admin_remove_whitelist")]
        ])
        m = await call.message.answer("🔗 **Управление ссылками**", reply_markup=keyboard)
        await call.message.delete()
        await call.answer()
        return
    
    if data == "admin_show_whitelist":
        domains = await get_whitelist_domains()
        if not domains:
            m = await call.message.answer("🔗 Белый список пуст")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = "🔗 **Белый список:**\n\n"
        for domain in domains:
            text += f"• {domain}\n"
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    if data == "admin_add_whitelist":
        m = await call.message.answer("📝 Введи домен для добавления (например: example.com):")
        current_action[user_id] = "add_whitelist"
        await call.answer()
        return
    
    if data == "admin_remove_whitelist":
        m = await call.message.answer("📝 Введи домен для удаления:")
        current_action[user_id] = "remove_whitelist"
        await call.answer()
        return
    
    # === ОСТАЛЬНЫЕ АДМИН-КОМАНДЫ ===
    if data in ["admin_warn", "admin_mute", "admin_silent_mute", "admin_unmute", "admin_clear_warns", "admin_check_warns", "admin_set_moderator", "admin_set_admin", "admin_set_level"]:
        action_name = data.replace("admin_", "")
        m = await call.message.answer(f"📝 Введи ID или @username для: {action_name}")
        current_action[user_id] = action_name
        await call.answer()
        return
    
    if data == "admin_user_stats":
        m = await call.message.answer("📝 Введи ID или @username пользователя:")
        current_action[user_id] = "user_stats"
        await call.answer()
        return
    
    if data == "admin_set_channel_operator":
        m = await call.message.answer("📝 Введи ID канала для назначения оператора:")
        current_action[user_id] = "get_channel_for_operator"
        await call.answer()
        return
    
    if data == "admin_set_channel_owner":
        m = await call.message.answer("📝 Введи ID канала для назначения главы:")
        current_action[user_id] = "get_channel_for_owner"
        await call.answer()
        return
    
    if data == "admin_channel_settings":
        await channel_settings(call.message)
        await call.answer()
        return
    
    if data == "admin_logs":
        await admin_logs_callback(call)
        return
    
    await call.answer("✅")

# === ФИЛЬТР СООБЩЕНИЙ ===
@dp.message(F.text)
async def filter_msg(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    # Проверяем настройки
    settings = await get_channel_settings(msg.chat.id)
    if not settings['enabled']:
        return
    
    # Админы пропускаются
    if level >= 2:
        return
    
    # Проверка возраста аккаунта
    if settings['block_new_accounts']:
        if user_id > 1000000000:  # Примерная проверка
            await msg.delete()
            m = await msg.answer("⛔ Аккаунт младше 1 дня!")
            asyncio.create_task(delete_after(m, 10))
            return
    
    # Проверка мута
    if await is_muted(user_id):
        await msg.delete()
        m = await msg.answer("⛔ Ты в муте!")
        asyncio.create_task(delete_after(m, 5))
        return
    
    text = msg.text or ""
    has_photo = bool(msg.photo or msg.video or msg.document)
    
    # УГРОЗЫ
    if has_violence(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "violence")
        await add_mute(user_id, settings['mute_duration'])
        await log_admin_action(0, "auto_mute", user_id, "Угрозы")
        m1 = await msg.answer("🚨 **УГРОЗЫ ЗАПРЕЩЕНЫ!**")
        m2 = await msg.answer(f"⛔ Мут {settings['mute_duration']//60} минут!")
        asyncio.create_task(delete_after(m1, 10))
        asyncio.create_task(delete_after(m2, 10))
        return
    
    # МАТ С ФОТО
    if has_photo and has_bad_words(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "badwords_with_photo")
        m = await msg.answer("🚫 **Мат с фото запрещён!**")
        asyncio.create_task(delete_after(m, 10))
        return
    
    # ССЫЛКИ
    if await has_blocked_link(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "blocked_link")
        m = await msg.answer("🔗 **Ссылка заблокирована!**")
        asyncio.create_task(delete_after(m, 10))
        return

# === ОБРАБОТКА ВВОДА ОТ АДМИНОВ ===
@dp.message()
async def admin_input(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    if level < 2:
        return
    
    text = msg.text.strip()
    if not text:
        return
    
    action = current_action.get(user_id)
    if not action:
        return
    
    # === НАСТРОЙКИ ===
    if action == "set_mute_duration":
        try:
            duration = int(text)
            chat_id = target_user.get(user_id)
            settings = await get_channel_settings(chat_id)
            settings['mute_duration'] = duration
            await update_channel_settings(chat_id, settings)
            m = await msg.answer(f"✅ Длительность мута: {duration} сек")
            await send_log(chat_id, "⚙️ Настройки", f"Мут: {duration} сек")
            current_action[user_id] = None
            asyncio.create_task(delete_after(m, 15))
        except ValueError:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    if action == "set_warn_limit":
        try:
            limit = int(text)
            chat_id = target_user.get(user_id)
            settings = await get_channel_settings(chat_id)
            settings['warn_limit'] = limit
            await update_channel_settings(chat_id, settings)
            m = await msg.answer(f"✅ Лимит варнов: {limit}")
            await send_log(chat_id, "⚙️ Настройки", f"Лимит варнов: {limit}")
            current_action[user_id] = None
            asyncio.create_task(delete_after(m, 15))
        except ValueError:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    # === ПОЛУЧАЕМ ID ПОЛЬЗОВАТЕЛЯ ===
    target_id = None
    if text.startswith("@"):
        target_id = await get_user_id_by_username(text)
        if not target_id:
            m = await msg.answer(f"❌ Пользователь {text} не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
    else:
        try:
            target_id = int(text)
        except ValueError:
            m = await msg.answer("❌ Введи ID или @username!")
            asyncio.create_task(delete_after(m, 10))
            return
    
    # === СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ ===
    if action == "user_stats":
        stats = await get_user_stats(target_id, msg.chat.id)
        username = await get_username_by_id(target_id)
        report = (
            f"📊 **Статистика пользователя**\n"
            f"━" * 25 + "\n"
            f"👤 Пользователь: {username}\n"
            f"🆔 ID: `{target_id}`\n\n"
            f"📌 **Общая информация:**\n"
            f"• 👑 Роль: {stats['role']}\n"
            f"• 📊 Уровень: {stats['level']}\n"
            f"• ⭐ Карма: {stats['karma']}\n\n"
            f"⚠️ **Нарушения:**\n"
            f"• 🚫 Всего нарушений: {stats['violations']}\n"
            f"• ⚠️ Варнов: {stats['warns']}\n\n"
        )
        if stats['is_muted']:
            remaining = stats['mute_until'] - int(time.time())
            minutes = remaining // 60
            seconds = remaining % 60
            report += f"🔴 **В муте:** {minutes}м {seconds}с\n"
        else:
            report += f"🟢 **Не в муте**\n"
        report += "\n━" * 25 + "\n"
        report += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        m = await msg.answer(report, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 45))
        current_action[user_id] = None
        return
    
    # === ОСТАЛЬНЫЕ ДЕЙСТВИЯ ===
    if action == "warn":
        was_auto_muted = await add_warning(target_id, msg.chat.id, "Нарушение правил", user_id)
        await log_admin_action(user_id, "warn", target_id, "Нарушение правил")
        warns = await get_warnings(target_id, msg.chat.id)
        settings = await get_channel_settings(msg.chat.id)
        if warns >= settings['warn_limit']:
            await add_mute(target_id, settings['mute_duration'])
            m = await msg.answer(f"⚠️ {warns} варнов! Мут {settings['mute_duration']//60} мин")
        else:
            m = await msg.answer(f"✅ Варн {warns}/{settings['warn_limit']}")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "check_warns":
        warns = await get_warnings(target_id, msg.chat.id)
        details = await get_user_warnings_details(target_id, msg.chat.id)
        text = f"📋 У {await get_username_by_id(target_id)} - {warns} варнов\n\n"
        if details:
            text += "📝 Последние варны:\n"
            for reason, admin_id, date in details[:5]:
                admin_name = await get_username_by_id(admin_id) if admin_id else "Система"
                text += f"• {reason[:30]}... (админ: {admin_name})\n  🕐 {date[:16]}\n"
        m = await msg.answer(text, parse_mode="Markdown")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 30))
        return
    
    if action == "clear_warns":
        await clear_warnings(target_id, msg.chat.id)
        await log_admin_action(user_id, "clear_warns", target_id, "")
        m = await msg.answer(f"✅ Варны очищены")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "mute":
        target_user[user_id] = target_id
        current_action[user_id] = "mute_duration"
        m = await msg.answer(f"⏱️ Введи длительность (сек) для {target_id}:")
        asyncio.create_task(delete_after(m, 30))
        return
    
    if action == "mute_duration":
        try:
            duration = int(text)
            await add_mute(target_user.get(user_id), duration)
            await log_admin_action(user_id, "mute", target_user.get(user_id), f"{duration} сек")
            m = await msg.answer(f"✅ Замучен на {duration} сек")
            await send_log(msg.chat.id, "🔨 Мут", f"Пользователь: {target_user.get(user_id)}\nДлительность: {duration} сек")
            current_action[user_id] = None
            asyncio.create_task(delete_after(m, 15))
        except ValueError:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    if action == "silent_mute":
        target_user[user_id] = target_id
        current_action[user_id] = "silent_mute_duration"
        m = await msg.answer(f"🔕 Введи длительность тихого мута (сек) для {target_id}:")
        asyncio.create_task(delete_after(m, 30))
        return
    
    if action == "silent_mute_duration":
        try:
            duration = int(text)
            await add_mute(target_user.get(user_id), duration)
            await log_admin_action(user_id, "silent_mute", target_user.get(user_id), f"{duration} сек")
            m = await msg.answer(f"🔕 Тихо замучен на {duration} сек")
            await send_log(msg.chat.id, "🔕 Тихий мут", f"Пользователь: {target_user.get(user_id)}\nДлительность: {duration} сек")
            current_action[user_id] = None
            asyncio.create_task(delete_after(m, 15))
        except ValueError:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    if action == "unmute":
        await remove_mute(target_id)
        await log_admin_action(user_id, "unmute", target_id, "")
        m = await msg.answer(f"✅ Размучен")
        await send_log(msg.chat.id, "🔓 Размут", f"Пользователь: {target_id}")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "set_moderator":
        await set_user_level(target_id, 2)
        await log_admin_action(user_id, "set_moderator", target_id, "")
        m = await msg.answer(f"🛡️ Модератор (уровень 2)")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "set_admin":
        await set_user_level(target_id, 5)
        await log_admin_action(user_id, "set_admin", target_id, "")
        m = await msg.answer(f"👑 Админ (уровень 5)")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "set_level":
        target_user[user_id] = target_id
        current_action[user_id] = "set_level_input"
        m = await msg.answer(
            f"📊 Введи уровень (0-7) для {await get_username_by_id(target_id)}:\n\n"
            "0 - Пользователь\n"
            "1 - Наблюдатель 🟢\n"
            "2 - Стажёр 🟡\n"
            "3 - Модератор 🟠\n"
            "4 - Старший модератор 🔵\n"
            "5 - Заместитель 🟣\n"
            "6 - Администратор 🔴\n"
            "7 - Главный админ ⭐"
        )
        asyncio.create_task(delete_after(m, 60))
        return
    
    if action == "set_level_input":
        try:
            new_level = int(text)
            if 0 <= new_level <= 7:
                await set_user_level(target_user.get(user_id), new_level)
                await log_admin_action(user_id, "set_level", target_user.get(user_id), f"{new_level}")
                level_name = ADMIN_LEVELS[new_level]["name"] if new_level > 0 else "Пользователь"
                m = await msg.answer(f"✅ Уровень {new_level} ({level_name})")
                current_action[user_id] = None
                asyncio.create_task(delete_after(m, 15))
            else:
                m = await msg.answer("❌ Введи число от 0 до 7!")
                asyncio.create_task(delete_after(m, 10))
        except ValueError:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    # === НАСТРОЙКА ОПЕРАТОРА ===
    if action == "get_channel_for_operator":
        try:
            channel_id = int(text)
            target_user[user_id] = channel_id
            current_action[user_id] = "setup_operator"
            m = await msg.answer(f"📝 Введи ID или @username оператора для канала `{channel_id}`:")
            asyncio.create_task(delete_after(m, 30))
        except ValueError:
            m = await msg.answer("❌ Введи корректный ID канала!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    if action == "setup_operator":
        channel_id = target_user.get(user_id)
        operator_id = None
        operator_name = ""
        if text.startswith("@"):
            operator_id = await get_user_id_by_username(text)
            if operator_id:
                operator_name = text[1:]
        else:
            try:
                operator_id = int(text)
            except:
                pass
        if not operator_id:
            m = await msg.answer("❌ Пользователь не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_operator(channel_id, operator_id, operator_name)
        await send_log(channel_id, "👤 Назначен оператор", f"Оператор: {operator_id} (@{operator_name})")
        m = await msg.answer(f"✅ Оператор назначен для канала `{channel_id}`")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    # === НАСТРОЙКА ГЛАВЫ ===
    if action == "get_channel_for_owner":
        try:
            channel_id = int(text)
            target_user[user_id] = channel_id
            current_action[user_id] = "setup_owner"
            m = await msg.answer(f"📝 Введи ID или @username главы для канала `{channel_id}`:")
            asyncio.create_task(delete_after(m, 30))
        except ValueError:
            m = await msg.answer("❌ Введи корректный ID канала!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    if action == "setup_owner":
        channel_id = target_user.get(user_id)
        owner_id = None
        owner_name = ""
        if text.startswith("@"):
            owner_id = await get_user_id_by_username(text)
            if owner_id:
                owner_name = text[1:]
        else:
            try:
                owner_id = int(text)
            except:
                pass
        if not owner_id:
            m = await msg.answer("❌ Пользователь не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_owner(channel_id, owner_id, owner_name)
        await send_log(channel_id, "👑 Назначен глава", f"Глава: {owner_id} (@{owner_name})")
        m = await msg.answer(f"👑 Глава назначен для канала `{channel_id}`")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    # === БЕЛЫЙ СПИСОК ===
    if action == "add_whitelist":
        domain = text.lower()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        await add_whitelist_domain(domain, user_id)
        m = await msg.answer(f"✅ Домен `{domain}` добавлен")
        await send_log(msg.chat.id, "🔗 Добавлен домен", f"Домен: {domain}")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "remove_whitelist":
        domain = text.lower()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        await remove_whitelist_domain(domain)
        m = await msg.answer(f"✅ Домен `{domain}` удалён")
        await send_log(msg.chat.id, "🔗 Удалён домен", f"Домен: {domain}")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return

# === ПОСТЫ В КАНАЛЕ ===
@dp.channel_post()
async def filter_channel_posts(msg: types.Message):
    channel_id = msg.chat.id
    if not msg.text and not msg.caption:
        return
    
    settings = await get_channel_settings(channel_id)
    if not settings['enabled']:
        return
    
    text = msg.text or msg.caption or ""
    has_photo = bool(msg.photo or msg.video or msg.document)
    
    if has_violence(text):
        try:
            await msg.delete()
            if msg.sender_chat:
                await add_violation(msg.sender_chat.id, channel_id, "violence")
        except:
            pass
        return
    
    if has_photo and has_bad_words(text):
        try:
            await msg.delete()
        except:
            pass
        return
    
    if await has_blocked_link(text):
        try:
            await msg.delete()
        except:
            pass
        return

# === ФОНОВЫЕ ЗАДАЧИ ===
async def background_tasks():
    while True:
        try:
            await auto_clear_expired_warnings()
            
            now = datetime.now()
            if now.hour == 0 and now.minute == 0:
                try:
                    await bot.send_message(
                        LOG_CHANNEL_ID,
                        "☀️ **Ежедневный отчёт**\n"
                        "━" * 25 + "\n"
                        f"📅 {now.strftime('%d.%m.%Y')}\n\n"
                        "✨ Бот работает стабильно!\n"
                        "🌴 Хорошего дня!",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            
            async with aiosqlite.connect("bot.db") as db:
                cursor = await db.execute(
                    "SELECT user_id, until FROM mutes WHERE until <= ? AND until > ?",
                    (int(time.time()), int(time.time()) - 10)
                )
                expired = await cursor.fetchall()
                for user_id, _ in expired:
                    try:
                        await bot.send_message(
                            user_id,
                            "🔓 **Мут снят!**\n"
                            "🌴 Ты снова можешь писать в чате.\n"
                            "Будь внимательнее! ☀️"
                        )
                    except:
                        pass
                    await remove_mute(user_id)
        except Exception as e:
            print(f"Ошибка: {e}")
        await asyncio.sleep(3600)

# === ВЕБ-СЕРВЕР ===
async def health_check(request):
    return web.Response(text="Bot is running! ☀️")

async def start_web():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("✅ Веб-сервер запущен")
    await asyncio.Event().wait()

# === ЗАПУСК ===
async def main():
    print("☀️ Запуск бота...")
    await init_db()
    print("✅ База готова")
    asyncio.create_task(background_tasks())
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот работает!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_until_complete(start_web())
