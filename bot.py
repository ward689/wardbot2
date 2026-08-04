import asyncio
import time
import re
import json
from datetime import datetime
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
            f"📋 **Лог**\n📢 {channel_id}\n🔧 {action}\n📝 {details}"
        )
    except:
        pass

# === КНОПКИ ===
async def get_admin_keyboard(user_id: int):
    level = await get_user_level(user_id)
    buttons = []
    if level >= 2:
        buttons.append([InlineKeyboardButton(text="⚠️ Варн", callback_data="admin_warn")])
        buttons.append([InlineKeyboardButton(text="📋 Варны", callback_data="admin_check_warns")])
    if level >= 3:
        buttons.append([InlineKeyboardButton(text="🔨 Мут", callback_data="admin_mute")])
        buttons.append([InlineKeyboardButton(text="🔕 Тихий мут", callback_data="admin_silent_mute")])
        buttons.append([InlineKeyboardButton(text="🔓 Размут", callback_data="admin_unmute")])
    if level >= 4:
        buttons.append([InlineKeyboardButton(text="🗑️ Очистить варны", callback_data="admin_clear_warns")])
        buttons.append([InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")])
    if level >= 5:
        buttons.append([InlineKeyboardButton(text="🛡️ Назначить модератора", callback_data="admin_set_moderator")])
    if level >= 6:
        buttons.append([InlineKeyboardButton(text="👑 Назначить админа", callback_data="admin_set_admin")])
        buttons.append([InlineKeyboardButton(text="📢 Назначить оператора", callback_data="admin_set_channel_operator")])
        buttons.append([InlineKeyboardButton(text="👑 Назначить главу", callback_data="admin_set_channel_owner")])
        buttons.append([InlineKeyboardButton(text="📋 Список операторов", callback_data="admin_list_operators")])
        buttons.append([InlineKeyboardButton(text="🔗 Ссылки", callback_data="admin_manage_links")])
        buttons.append([InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_channel_settings")])
    if level >= 7:
        buttons.append([InlineKeyboardButton(text="⭐ Уровни", callback_data="admin_set_level")])
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# === СТАРТ (КОРОТКИЙ!) ===
@dp.message(Command("start"))
async def start(msg: types.Message):
    m = await msg.answer(
        "☀️ *Добро пожаловать!*\n"
        "━" * 20 + "\n\n"
        "✨ Я слежу за порядком.\n"
        "🚫 Защищаю от угроз.\n\n"
        "📌 *Команды:*\n"
        "👑 /admin — панель\n"
        "👤 /myrole — роль\n"
        "📊 /admins — админы\n"
        "🎁 /daily — бонус\n"
        "⚙️ /settings — настройки\n\n"
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
        m = await msg.answer(f"🎁 **Бонус!**\n💰 {amount} монет\n🔥 Стрик: {streak}")
        asyncio.create_task(delete_after(m, 30))
    else:
        remaining = 86400 - (int(time.time()) % 86400)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        m = await msg.answer(f"⏳ Бонус через: {hours}ч {minutes}м")
        asyncio.create_task(delete_after(m, 20))

# === MYROLE ===
@dp.message(Command("myrole"))
async def my_role(msg: types.Message):
    level = await get_user_level(msg.from_user.id)
    role = await get_user_role(msg.from_user.id)
    karma = await get_karma(msg.from_user.id)
    m = await msg.answer(f"👤 **Твоя роль**\n📊 Уровень: {level}\n👑 Роль: {role}\n⭐ Карма: {karma}", parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 30))

# === ADMINS ===
@dp.message(Command("admins"))
async def list_admins(msg: types.Message):
    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute("SELECT user_id, level FROM roles WHERE level > 0 ORDER BY level DESC")
        results = await cursor.fetchall()
    if not results:
        m = await msg.answer("📋 Админов нет")
        asyncio.create_task(delete_after(m, 15))
        return
    text = "👑 **Администраторы:**\n\n"
    for user_id, level in results:
        if level in ADMIN_LEVELS:
            name = ADMIN_LEVELS[level]["name"]
            emoji = ADMIN_LEVELS[level]["emoji"]
            username = await get_username_by_id(user_id)
            text += f"{emoji} {level}: {name} ({username})\n"
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
        [InlineKeyboardButton(text=f"{'✅' if settings['enabled'] else '❌'} Модерация", callback_data="sett_enabled")],
        [InlineKeyboardButton(text=f"⏱️ Мут: {settings['mute_duration']}с", callback_data="sett_mute_duration")],
        [InlineKeyboardButton(text=f"⚠️ Варны: {settings['warn_limit']}", callback_data="sett_warn_limit")],
        [InlineKeyboardButton(text=f"{'✅' if settings['block_new_accounts'] else '❌'} Блок новых", callback_data="sett_block_new")],
        [InlineKeyboardButton(text="📊 Показать", callback_data="sett_show")]
    ])
    m = await msg.answer("⚙️ **Настройки**", reply_markup=keyboard, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))

# === ADMIN ===
@dp.message(Command("admin"))
async def admin_panel(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 2:
        m = await msg.answer("⛔ Нет прав!")
        asyncio.create_task(delete_after(m, 10))
        return
    role = await get_user_role(user_id)
    keyboard = await get_admin_keyboard(user_id)
    m = await msg.answer(
        f"🛡️ *Админ-панель*\n👤 {role}\n📊 {level}\n\nВыбери:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# === ОБРАБОТКА КНОПОК ===
@dp.callback_query()
async def handle_callbacks(call: types.CallbackQuery):
    user_id = call.from_user.id
    level = await get_user_level(user_id)
    data = call.data
    
    if data == "admin_close":
        await call.message.delete()
        await call.answer("Закрыто")
        return
    
    # === НАСТРОЙКИ ===
    if data.startswith("sett_"):
        action = data.split("_")[1]
        chat_id = call.message.chat.id
        settings = await get_channel_settings(chat_id)
        
        if action == "enabled":
            settings['enabled'] = not settings['enabled']
            await update_channel_settings(chat_id, settings)
            await call.answer(f"Модерация {'вкл' if settings['enabled'] else 'выкл'}")
        elif action == "block_new":
            settings['block_new_accounts'] = not settings['block_new_accounts']
            await update_channel_settings(chat_id, settings)
            await call.answer(f"Блокировка {'вкл' if settings['block_new_accounts'] else 'выкл'}")
        elif action == "show":
            text = f"⚙️ Настройки\n📌 {chat_id}\n"
            text += f"{'✅' if settings['enabled'] else '❌'} Модерация\n"
            text += f"⏱️ Мут: {settings['mute_duration']}с\n"
            text += f"⚠️ Варны: {settings['warn_limit']}"
            m = await call.message.answer(text, parse_mode="Markdown")
            asyncio.create_task(delete_after(m, 30))
            await call.answer()
            return
        elif action == "mute_duration":
            await call.message.answer("📝 Введи длительность (сек):")
            current_action[user_id] = "set_mute_duration"
            target_user[user_id] = chat_id
            await call.answer()
            return
        elif action == "warn_limit":
            await call.message.answer("📝 Введи лимит варнов:")
            current_action[user_id] = "set_warn_limit"
            target_user[user_id] = chat_id
            await call.answer()
            return
        
        # Обновляем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'✅' if settings['enabled'] else '❌'} Модерация", callback_data="sett_enabled")],
            [InlineKeyboardButton(text=f"⏱️ Мут: {settings['mute_duration']}с", callback_data="sett_mute_duration")],
            [InlineKeyboardButton(text=f"⚠️ Варны: {settings['warn_limit']}", callback_data="sett_warn_limit")],
            [InlineKeyboardButton(text=f"{'✅' if settings['block_new_accounts'] else '❌'} Блок новых", callback_data="sett_block_new")],
            [InlineKeyboardButton(text="📊 Показать", callback_data="sett_show")]
        ])
        try:
            await call.message.edit_reply_markup(reply_markup=keyboard)
        except:
            pass
        await call.answer()
        return
    
    # === АДМИН-КНОПКИ ===
    if level < 2:
        await call.answer("⛔ Нет прав!", True)
        return
    
    # Список кнопок
    if data == "admin_list_operators":
        ops = await get_all_channel_operators()
        if not ops:
            m = await call.message.answer("📋 Операторов нет")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = "📢 **Операторы:**\n\n"
        for ch_id, op_id, op_name, ch_name in ops:
            text += f"📌 {ch_name or ch_id} -> {op_id}"
            if op_name:
                text += f" (@{op_name})"
            text += "\n"
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    if data == "admin_stats":
        violations = await get_violations_stats(call.message.chat.id, 10)
        if not violations:
            m = await call.message.answer("📊 Статистика пуста")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = "📊 **Статистика:**\n\n"
        for idx, (uid, count) in enumerate(violations, 1):
            username = await get_username_by_id(uid)
            text += f"{idx}. {username} — {count}\n"
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    if data == "admin_manage_links":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Белый список", callback_data="admin_show_whitelist")],
            [InlineKeyboardButton(text="➕ Добавить", callback_data="admin_add_whitelist")],
            [InlineKeyboardButton(text="➖ Удалить", callback_data="admin_remove_whitelist")]
        ])
        m = await call.message.answer("🔗 **Ссылки**", reply_markup=keyboard)
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
        m = await call.message.answer("📝 Введи домен (example.com):")
        current_action[user_id] = "add_whitelist"
        await call.answer()
        return
    
    if data == "admin_remove_whitelist":
        m = await call.message.answer("📝 Введи домен для удаления:")
        current_action[user_id] = "remove_whitelist"
        await call.answer()
        return
    
    # Остальные админ-команды
    if data in ["admin_warn", "admin_mute", "admin_silent_mute", "admin_unmute", "admin_clear_warns", "admin_check_warns", "admin_set_moderator", "admin_set_admin", "admin_set_level", "admin_user_stats"]:
        action_name = data.replace("admin_", "")
        m = await call.message.answer(f"📝 Введи ID или @username для: {action_name}")
        current_action[user_id] = action_name
        await call.answer()
        return
    
    if data == "admin_set_channel_operator":
        m = await call.message.answer("📝 Введи ID канала:")
        current_action[user_id] = "get_channel_for_operator"
        await call.answer()
        return
    
    if data == "admin_set_channel_owner":
        m = await call.message.answer("📝 Введи ID канала:")
        current_action[user_id] = "get_channel_for_owner"
        await call.answer()
        return
    
    if data == "admin_channel_settings":
        await channel_settings(call.message)
        await call.answer()
        return
    
    await call.answer("✅")

# === ФИЛЬТР СООБЩЕНИЙ ===
@dp.message(F.text)
async def filter_msg(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    settings = await get_channel_settings(msg.chat.id)
    if not settings['enabled']:
        return
    
    if level >= 2:
        return
    
    if settings['block_new_accounts'] and user_id > 1000000000:
        await msg.delete()
        m = await msg.answer("⛔ Аккаунт младше 1 дня!")
        asyncio.create_task(delete_after(m, 10))
        return
    
    if await is_muted(user_id):
        await msg.delete()
        m = await msg.answer("⛔ Ты в муте!")
        asyncio.create_task(delete_after(m, 5))
        return
    
    text = msg.text or ""
    has_photo = bool(msg.photo or msg.video)
    
    if has_violence(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "violence")
        await add_mute(user_id, settings['mute_duration'])
        m = await msg.answer("🚨 УГРОЗЫ ЗАПРЕЩЕНЫ!")
        asyncio.create_task(delete_after(m, 10))
        return
    
    if has_photo and has_bad_words(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "badwords_with_photo")
        m = await msg.answer("🚫 Мат с фото запрещён!")
        asyncio.create_task(delete_after(m, 10))
        return
    
    if await has_blocked_link(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "blocked_link")
        m = await msg.answer("🔗 Ссылка заблокирована!")
        asyncio.create_task(delete_after(m, 10))
        return

# === ОБРАБОТКА ВВОДА ===
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
            m = await msg.answer(f"✅ Мут: {duration}с")
            current_action[user_id] = None
            asyncio.create_task(delete_after(m, 15))
        except:
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
            current_action[user_id] = None
            asyncio.create_task(delete_after(m, 15))
        except:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    # === ПОЛУЧАЕМ ID ===
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
        except:
            m = await msg.answer("❌ Введи ID или @username!")
            asyncio.create_task(delete_after(m, 10))
            return
    
    # === ДЕЙСТВИЯ ===
    if action == "warn":
        await add_warning(target_id, msg.chat.id, "Нарушение", user_id)
        warns = await get_warnings(target_id, msg.chat.id)
        settings = await get_channel_settings(msg.chat.id)
        if warns >= settings['warn_limit']:
            await add_mute(target_id, settings['mute_duration'])
            m = await msg.answer(f"⚠️ {warns} варнов! Мут!")
        else:
            m = await msg.answer(f"✅ Варн {warns}/{settings['warn_limit']}")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "check_warns":
        warns = await get_warnings(target_id, msg.chat.id)
        m = await msg.answer(f"📋 Варнов: {warns}")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "clear_warns":
        await clear_warnings(target_id, msg.chat.id)
        m = await msg.answer(f"✅ Варны очищены")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "mute":
        target_user[user_id] = target_id
        current_action[user_id] = "mute_duration"
        m = await msg.answer(f"⏱️ Введи длительность (сек):")
        asyncio.create_task(delete_after(m, 30))
        return
    
    if action == "mute_duration":
        try:
            duration = int(text)
            await add_mute(target_user.get(user_id), duration)
            m = await msg.answer(f"✅ Замучен на {duration}с")
            current_action[user_id] = None
            asyncio.create_task(delete_after(m, 15))
        except:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    if action == "silent_mute":
        target_user[user_id] = target_id
        current_action[user_id] = "silent_mute_duration"
        m = await msg.answer(f"🔕 Введи длительность (сек):")
        asyncio.create_task(delete_after(m, 30))
        return
    
    if action == "silent_mute_duration":
        try:
            duration = int(text)
            await add_mute(target_user.get(user_id), duration)
            m = await msg.answer(f"🔕 Тихо замучен на {duration}с")
            current_action[user_id] = None
            asyncio.create_task(delete_after(m, 15))
        except:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    if action == "unmute":
        await remove_mute(target_id)
        m = await msg.answer(f"✅ Размучен")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "set_moderator":
        await set_user_level(target_id, 2)
        m = await msg.answer(f"🛡️ Модератор (уровень 2)")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "set_admin":
        await set_user_level(target_id, 5)
        m = await msg.answer(f"👑 Админ (уровень 5)")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "set_level":
        target_user[user_id] = target_id
        current_action[user_id] = "set_level_input"
        m = await msg.answer(
            f"📊 Уровень (0-7) для {target_id}:\n\n"
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
                name = ADMIN_LEVELS[new_level]["name"] if new_level > 0 else "Пользователь"
                m = await msg.answer(f"✅ Уровень {new_level} ({name})")
                current_action[user_id] = None
                asyncio.create_task(delete_after(m, 15))
            else:
                m = await msg.answer("❌ 0-7!")
                asyncio.create_task(delete_after(m, 10))
        except:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    # === ОПЕРАТОР ===
    if action == "get_channel_for_operator":
        try:
            channel_id = int(text)
            target_user[user_id] = channel_id
            current_action[user_id] = "setup_operator"
            m = await msg.answer(f"📝 Введи @username оператора для канала {channel_id}:")
            asyncio.create_task(delete_after(m, 30))
        except:
            m = await msg.answer("❌ Введи ID канала!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    if action == "setup_operator":
        channel_id = target_user.get(user_id)
        operator_id = await get_user_id_by_username(text)
        if not operator_id:
            m = await msg.answer("❌ Пользователь не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_operator(channel_id, operator_id, text.replace('@', ''))
        m = await msg.answer(f"✅ Оператор назначен")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    # === ГЛАВА ===
    if action == "get_channel_for_owner":
        try:
            channel_id = int(text)
            target_user[user_id] = channel_id
            current_action[user_id] = "setup_owner"
            m = await msg.answer(f"📝 Введи @username главы для канала {channel_id}:")
            asyncio.create_task(delete_after(m, 30))
        except:
            m = await msg.answer("❌ Введи ID канала!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    if action == "setup_owner":
        channel_id = target_user.get(user_id)
        owner_id = await get_user_id_by_username(text)
        if not owner_id:
            m = await msg.answer("❌ Пользователь не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_owner(channel_id, owner_id, text.replace('@', ''))
        m = await msg.answer(f"👑 Глава назначен")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    # === БЕЛЫЙ СПИСОК ===
    if action == "add_whitelist":
        domain = text.lower()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        await add_whitelist_domain(domain, user_id)
        m = await msg.answer(f"✅ Домен {domain} добавлен")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    if action == "remove_whitelist":
        domain = text.lower()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        await remove_whitelist_domain(domain)
        m = await msg.answer(f"✅ Домен {domain} удалён")
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
    has_photo = bool(msg.photo or msg.video)
    
    if has_violence(text) or (has_photo and has_bad_words(text)) or (await has_blocked_link(text)):
        try:
            await msg.delete()
        except:
            pass

# === ФОНОВЫЕ ЗАДАЧИ ===
async def background_tasks():
    while True:
        try:
            await auto_clear_expired_warnings()
            now = datetime.now()
            if now.hour == 0 and now.minute == 0:
                try:
                    await bot.send_message(LOG_CHANNEL_ID, "☀️ Ежедневный отчёт\n━" * 20 + f"\n📅 {now.strftime('%d.%m.%Y')}\n\n✨ Бот работает!")
                except:
                    pass
            async with aiosqlite.connect("bot.db") as db:
                cursor = await db.execute("SELECT user_id, until FROM mutes WHERE until <= ? AND until > ?", (int(time.time()), int(time.time()) - 10))
                expired = await cursor.fetchall()
                for user_id, _ in expired:
                    try:
                        await bot.send_message(user_id, "🔓 Мут снят!")
                    except:
                        pass
                    await remove_mute(user_id)
        except:
            pass
        await asyncio.sleep(3600)

# === ВЕБ-СЕРВЕР ===
async def health_check(request):
    return web.Response(text="Bot is running!")

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
    print("☀️ Запуск...")
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
