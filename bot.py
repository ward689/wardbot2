import asyncio
import time
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, ADMIN_IDS, LOG_CHANNEL_ID, VIOLENCE_WORDS, BAD_WORDS, WHITELIST_DOMAINS
from database import *
from aiohttp import web

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

current_action = {}
target_user = {}

# ============================================================
# === УНИВЕРСАЛЬНЫЙ ПОИСК ПОЛЬЗОВАТЕЛЯ ===
# ============================================================
async def get_user_by_username(username: str) -> types.User:
    try:
        username = username.replace('@', '').strip()
        if not username:
            return None
        try:
            user = await bot.get_user(username)
            if user:
                return user
        except:
            pass
        try:
            chat = await bot.get_chat(f"@{username}")
            if chat and chat.type == "private":
                return types.User(id=chat.id, first_name=chat.first_name, username=chat.username)
        except:
            pass
        try:
            chat = await bot.get_chat(username)
            if chat:
                return types.User(id=chat.id, first_name=chat.first_name, username=chat.username)
        except:
            pass
        return None
    except Exception as e:
        print(f"Ошибка поиска {username}: {e}")
        return None

async def get_user_id_by_username(username: str) -> int:
    try:
        user = await get_user_by_username(username)
        if user:
            return user.id
        try:
            chat = await bot.get_chat(username)
            if chat:
                return chat.id
        except:
            pass
        return None
    except:
        return None

async def resolve_user(text: str) -> int:
    text = text.strip()
    try:
        return int(text)
    except:
        pass
    if text.startswith("@"):
        user_id = await get_user_id_by_username(text)
        if user_id:
            return user_id
        try:
            chat = await bot.get_chat(text)
            if chat and chat.type == "private":
                return chat.id
        except:
            pass
    return None

async def get_username_by_id(user_id: int) -> str:
    try:
        user = await bot.get_user(user_id)
        return f"@{user.username}" if user and user.username else str(user_id)
    except:
        return str(user_id)

async def delete_after(msg, seconds=10):
    await asyncio.sleep(seconds)
    try:
        await msg.delete()
    except:
        pass

def parse_duration(duration_str: str) -> int:
    duration_str = duration_str.lower().strip()
    if duration_str.endswith('м'):
        try:
            return int(duration_str[:-1]) * 60
        except:
            return None
    elif duration_str.endswith('ч'):
        try:
            return int(duration_str[:-1]) * 3600
        except:
            return None
    elif duration_str.endswith('д'):
        try:
            return int(duration_str[:-1]) * 86400
        except:
            return None
    else:
        try:
            return int(duration_str)
        except:
            return None

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

def has_bad_words(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    for w in BAD_WORDS:
        if w in t:
            return True
    return False

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
        if domain not in whitelist:
            return True
    return False

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

# ============================================================
# === КНОПКИ ===
# ============================================================
async def get_admin_keyboard(user_id: int):
    level = await get_user_level(user_id)
    buttons = []
    if level >= 2:
        buttons.append([InlineKeyboardButton(text="⚠️ Варн", callback_data="admin_warn")])
        buttons.append([InlineKeyboardButton(text="📋 Варны пользователя", callback_data="admin_check_warns")])
    if level >= 3:
        buttons.append([InlineKeyboardButton(text="🔒 Мут", callback_data="admin_mute")])
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

# ============================================================
# === КОМАНДЫ ===
# ============================================================
@dp.message(Command("start"))
async def start(msg: types.Message):
    m = await msg.answer(
        "☀️ *Бот-модератор*\n\n"
        "✅ Мат разрешён\n"
        "🚫 Угрозы блокируются\n"
        "⚠️ 3 варна = мут 5 мин\n\n"
        "📌 *Команды:*\n"
        "👑 /admin — панель\n"
        "👤 /myrole — роль\n"
        "🎁 /daily — бонус\n"
        "/мут @user 24ч причина\n"
        "/размут @user\n"
        "/варн @user причина\n"
        "/бан @user причина\n"
        "/кик @user причина\n"
        "/инфо @user\n\n"
        "📌 *Кнопки:*\n"
        "/settings — настройки канала",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_after(m, 30))

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
            f"🔥 Стрик: {streak} дней",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after(m, 20))

@dp.message(Command("myrole"))
async def my_role(msg: types.Message):
    level = await get_user_level(msg.from_user.id)
    role = await get_user_role(msg.from_user.id)
    karma = await get_karma(msg.from_user.id)
    
    ops = []
    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute("SELECT channel_id, channel_name FROM channel_operators WHERE operator_id = ?", (msg.from_user.id,))
        ops = await cursor.fetchall()
    
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
        [InlineKeyboardButton(text=f"⏱️ Длительность мута: {settings['mute_duration']}с", callback_data="sett_mute_duration")],
        [InlineKeyboardButton(text=f"⚠️ Лимит варнов: {settings['warn_limit']}", callback_data="sett_warn_limit")],
        [InlineKeyboardButton(text=f"{'✅' if settings['block_new_accounts'] else '❌'} Блокировка новых", callback_data="sett_block_new")],
        [InlineKeyboardButton(text="📊 Показать настройки", callback_data="sett_show")]
    ])
    
    m = await msg.answer("⚙️ **Настройки канала**", reply_markup=keyboard, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))

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
    asyncio.create_task(delete_after(m, 60))

@dp.message(Command("setup_operator"))
async def setup_operator_cmd(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    if msg.chat.type not in ["channel", "supergroup"]:
        m = await msg.answer("❌ Эта команда работает только в каналах и группах!")
        asyncio.create_task(delete_after(m, 10))
        return
    
    if level < 6:
        m = await msg.answer("⛔ Нужен уровень 6+!")
        asyncio.create_task(delete_after(m, 10))
        return
    
    global current_action
    current_action["setup_operator"] = msg.chat.id
    m = await msg.answer("📝 Введи @username или ID пользователя для назначения оператором:")
    asyncio.create_task(delete_after(m, 30))

@dp.message(Command("set_owner"))
async def set_owner_cmd(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    if msg.chat.type not in ["channel", "supergroup"]:
        m = await msg.answer("❌ Эта команда работает только в каналах и группах!")
        asyncio.create_task(delete_after(m, 10))
        return
    
    if level < 6:
        m = await msg.answer("⛔ Нужен уровень 6+!")
        asyncio.create_task(delete_after(m, 10))
        return
    
    global current_action
    current_action["set_owner"] = msg.chat.id
    m = await msg.answer("📝 Введи @username или ID пользователя для назначения главой канала:")
    asyncio.create_task(delete_after(m, 30))

# ============================================================
# === ТЕКСТОВЫЕ КОМАНДЫ С КРАСИВЫМ ОФОРМЛЕНИЕМ ===
# ============================================================
@dp.message(Command("мут"))
@dp.message(Command("mute"))
async def cmd_mute(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 3:
        await msg.answer("⛔ Нужен уровень 3+!")
        return
    
    args = msg.text.split(maxsplit=3)
    if len(args) < 2:
        await msg.answer("📝 /мут @user 24ч причина")
        return
    
    target = args[1]
    duration_str = args[2] if len(args) > 2 else "5м"
    reason = args[3] if len(args) > 3 else "Нарушение"
    
    target_id = await resolve_user(target)
    
    if not target_id:
        await msg.answer(
            f"❌ Пользователь {target} не найден!\n"
            f"💡 Попросите пользователя написать боту `/start`\n"
            f"Или используйте ID пользователя"
        )
        return
    
    duration = parse_duration(duration_str)
    if not duration:
        await msg.answer("❌ Неверный формат времени!\nДоступно: 5м, 1ч, 24ч, 7д")
        return
    
    target_level = await get_user_level(target_id)
    if target_level >= level and target_id not in ADMIN_IDS:
        await msg.answer(f"❌ Нельзя мутить пользователя с уровнем {target_level}!")
        return
    
    await add_mute(target_id, duration)
    await log_admin_action(user_id, "🔒 Мут", target_id, f"{duration_str} - {reason}")
    await send_log(msg.chat.id, "🔒 Мут", f"Пользователь: {target}\nДлительность: {duration_str}\nПричина: {reason}")
    
    await msg.answer(
        f"🔒 **Мут выдан!**\n\n"
        f"👤 Пользователь: {target}\n"
        f"⏱️ Длительность: {duration_str}\n"
        f"📝 Причина: {reason}\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("размут"))
@dp.message(Command("unmute"))
async def cmd_unmute(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 3:
        await msg.answer("⛔ Нужен уровень 3+!")
        return
    
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("📝 /размут @user")
        return
    
    target = args[1]
    target_id = await resolve_user(target)
    
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
        return
    
    await remove_mute(target_id)
    await log_admin_action(user_id, "🔓 Размут", target_id, "")
    await send_log(msg.chat.id, "🔓 Размут", f"Пользователь: {target}")
    
    await msg.answer(
        f"🔓 **Размут снят!**\n\n"
        f"👤 Пользователь: {target}\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("варн"))
@dp.message(Command("warn"))
async def cmd_warn(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 2:
        await msg.answer("⛔ Нужен уровень 2+!")
        return
    
    args = msg.text.split(maxsplit=2)
    if len(args) < 2:
        await msg.answer("📝 /варн @user причина")
        return
    
    target = args[1]
    reason = args[2] if len(args) > 2 else "Нарушение"
    
    target_id = await resolve_user(target)
    
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
        return
    
    target_level = await get_user_level(target_id)
    if target_level >= level and target_id not in ADMIN_IDS:
        await msg.answer(f"❌ Нельзя варнить пользователя с уровнем {target_level}!")
        return
    
    await add_warning(target_id, msg.chat.id, reason, user_id)
    await log_admin_action(user_id, "⚠️ Варн", target_id, reason)
    await send_log(msg.chat.id, "⚠️ Варн", f"Пользователь: {target}\nПричина: {reason}")
    
    warns = await get_warnings(target_id, msg.chat.id)
    settings = await get_channel_settings(msg.chat.id)
    
    if warns >= settings['warn_limit']:
        await add_mute(target_id, settings['mute_duration'])
        await msg.answer(
            f"⚠️ **Варн выдан!**\n\n"
            f"👤 Пользователь: {target}\n"
            f"📝 Причина: {reason}\n"
            f"🔥 Варнов: {warns}/{settings['warn_limit']}\n"
            f"⛔ **Автоматический мут {settings['mute_duration']//60} минут!**"
        )
    else:
        await msg.answer(
            f"⚠️ **Варн выдан!**\n\n"
            f"👤 Пользователь: {target}\n"
            f"📝 Причина: {reason}\n"
            f"🔥 Варнов: {warns}/{settings['warn_limit']}"
        )

@dp.message(Command("бан"))
@dp.message(Command("ban"))
async def cmd_ban(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 6:
        await msg.answer("⛔ Нужен уровень 6+!")
        return
    
    args = msg.text.split(maxsplit=2)
    if len(args) < 2:
        await msg.answer("📝 /бан @user причина")
        return
    
    target = args[1]
    reason = args[2] if len(args) > 2 else "Бан"
    
    target_id = await resolve_user(target)
    
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
        return
    
    target_level = await get_user_level(target_id)
    if target_level >= level and target_id not in ADMIN_IDS:
        await msg.answer(f"❌ Нельзя банить пользователя с уровнем {target_level}!")
        return
    
    await add_mute(target_id, 2592000)
    await log_admin_action(user_id, "🚫 Бан", target_id, reason)
    await send_log(msg.chat.id, "🚫 Бан", f"Пользователь: {target}\nПричина: {reason}")
    
    await msg.answer(
        f"🚫 **Бан выдан!**\n\n"
        f"👤 Пользователь: {target}\n"
        f"📝 Причина: {reason}\n"
        f"⏱️ Срок: 30 дней\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("кик"))
@dp.message(Command("kick"))
async def cmd_kick(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 5:
        await msg.answer("⛔ Нужен уровень 5+!")
        return
    
    args = msg.text.split(maxsplit=2)
    if len(args) < 2:
        await msg.answer("📝 /кик @user причина")
        return
    
    target = args[1]
    reason = args[2] if len(args) > 2 else "Кик"
    
    target_id = await resolve_user(target)
    
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
        return
    
    target_level = await get_user_level(target_id)
    if target_level >= level and target_id not in ADMIN_IDS:
        await msg.answer(f"❌ Нельзя кикать пользователя с уровнем {target_level}!")
        return
    
    await add_mute(target_id, 3600)
    await log_admin_action(user_id, "👢 Кик", target_id, reason)
    await send_log(msg.chat.id, "👢 Кик", f"Пользователь: {target}\nПричина: {reason}")
    
    await msg.answer(
        f"👢 **Кик выдан!**\n\n"
        f"👤 Пользователь: {target}\n"
        f"📝 Причина: {reason}\n"
        f"⏱️ Срок: 1 час\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("очистить"))
@dp.message(Command("clear"))
async def cmd_clear(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 4:
        await msg.answer("⛔ Нужен уровень 4+!")
        return
    
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("📝 /очистить @user")
        return
    
    target = args[1]
    target_id = await resolve_user(target)
    
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
        return
    
    await clear_warnings(target_id, msg.chat.id)
    await log_admin_action(user_id, "🗑️ Очищены варны", target_id, "")
    await send_log(msg.chat.id, "🗑️ Очищены варны", f"Пользователь: {target}")
    
    await msg.answer(
        f"🗑️ **Варны очищены!**\n\n"
        f"👤 Пользователь: {target}\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("инфо"))
@dp.message(Command("info"))
async def cmd_info(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 4:
        await msg.answer("⛔ Нужен уровень 4+!")
        return
    
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("📝 /инфо @user")
        return
    
    target = args[1]
    target_id = await resolve_user(target)
    
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
        return
    
    stats = await get_user_stats(target_id, msg.chat.id)
    username = await get_username_by_id(target_id)
    
    report = (
        f"📊 **Информация о пользователе**\n"
        f"━" * 30 + "\n"
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
    
    report += f"\n📊 **Статистика действий:**\n"
    report += f"• 👮 Действий как админ: {stats['admin_actions']}\n"
    report += f"• 🎯 Попал под действия: {stats['target_actions']}\n"
    report += "\n━" * 30 + "\n"
    report += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    
    # Кнопка "Показать фулл" (только для админов Telegram)
    keyboard = None
    if user_id in ADMIN_IDS:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Показать фулл", callback_data=f"full_stats_{target_id}")]
        ])
    
    m = await msg.answer(report, parse_mode="Markdown", reply_markup=keyboard)
    asyncio.create_task(delete_after(m, 60))

# ============================================================
# === ОБРАБОТКА КНОПКИ "Показать фулл" ===
# ============================================================
@dp.callback_query(F.data.startswith("full_stats_"))
async def full_stats_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    # Проверяем, что админ
    if user_id not in ADMIN_IDS:
        await call.answer("⛔ Только главные админы!", True)
        return
    
    target_id = int(call.data.split("_")[2])
    stats = await get_user_stats(target_id, call.message.chat.id)
    username = await get_username_by_id(target_id)
    
    # Получаем логи по пользователю
    logs = await get_admin_logs_by_user(target_id, 20)
    
    report = (
        f"📊 **ПОЛНАЯ СТАТИСТИКА**\n"
        f"━" * 35 + "\n"
        f"👤 Пользователь: {username}\n"
        f"🆔 ID: `{target_id}`\n\n"
        f"📌 **ОБЩАЯ ИНФОРМАЦИЯ:**\n"
        f"• 👑 Роль: {stats['role']}\n"
        f"• 📊 Уровень: {stats['level']}\n"
        f"• ⭐ Карма: {stats['karma']}\n\n"
        f"⚠️ **НАРУШЕНИЯ:**\n"
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
    
    report += f"\n📊 **СТАТИСТИКА ДЕЙСТВИЙ:**\n"
    report += f"• 👮 Действий как админ: {stats['admin_actions']}\n"
    report += f"• 🎯 Попал под действия: {stats['target_actions']}\n"
    
    if logs:
        report += f"\n📋 **ПОСЛЕДНИЕ ДЕЙСТВИЯ:**\n"
        for admin_id, admin_name, action, t_id, t_name, details, date in logs[:10]:
            report += f"• {admin_name} → {action}"
            if t_id:
                report += f" → {t_name}"
            if details:
                report += f" ({details})"
            report += f"\n  🕐 {date[:16]}\n"
    
    report += "\n━" * 35 + "\n"
    report += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    
    m = await call.message.answer(report, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))
    await call.answer("📊 Полная статистика загружена!")

# ============================================================
# === ОБРАБОТКА КНОПОК ===
# ============================================================
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
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'✅' if settings['enabled'] else '❌'} Модерация", callback_data="sett_enabled")],
            [InlineKeyboardButton(text=f"⏱️ Длительность мута: {settings['mute_duration']}с", callback_data="sett_mute_duration")],
            [InlineKeyboardButton(text=f"⚠️ Лимит варнов: {settings['warn_limit']}", callback_data="sett_warn_limit")],
            [InlineKeyboardButton(text=f"{'✅' if settings['block_new_accounts'] else '❌'} Блокировка новых", callback_data="sett_block_new")],
            [InlineKeyboardButton(text="📊 Показать настройки", callback_data="sett_show")]
        ])
        try:
            await call.message.edit_reply_markup(reply_markup=keyboard)
        except:
            pass
        await call.answer()
        return

    if level < 2:
        await call.answer("⛔ Нет прав!", True)
        return

    # === ЛОГИ (НОВЫЕ, КРАСИВЫЕ) ===
    if data == "admin_logs":
        logs = await get_admin_logs(30)
        if not logs:
            m = await call.message.answer("📋 Логов пока нет")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        
        text = "📋 **Логи админов:**\n\n"
        for admin_id, admin_name, action, target_id, target_name, details, date in logs:
            text += f"• {admin_name} {action}"
            if target_id:
                text += f" → {target_name}"
            if details:
                text += f"\n  📝 {details[:60]}..."
            text += f"\n  🕐 {date[:16]}\n\n"
        
        # Кнопка для полных логов
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Полные логи", callback_data="admin_full_logs")]
        ])
        
        m = await call.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
        asyncio.create_task(delete_after(m, 45))
        await call.answer()
        return

    if data == "admin_full_logs":
        if user_id not in ADMIN_IDS:
            await call.answer("⛔ Только главные админы!", True)
            return
        
        logs = await get_admin_logs(50)
        if not logs:
            m = await call.message.answer("📋 Логов пока нет")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        
        text = "📊 **ПОЛНЫЕ ЛОГИ (последние 50):**\n\n"
        for admin_id, admin_name, action, target_id, target_name, details, date in logs:
            text += f"👤 {admin_name}\n"
            text += f"🔧 {action}"
            if target_id:
                text += f" → {target_name}"
            if details:
                text += f"\n📝 {details}"
            text += f"\n🕐 {date}\n\n"
        
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 60))
        await call.answer()
        return

    # === ОПЕРАТОРЫ ===
    if data == "admin_list_operators":
        ops = await get_all_channel_operators()
        if not ops:
            m = await call.message.answer("📋 Операторов нет")
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
    
    await call.answer("✅")

# ============================================================
# === ОБРАБОТКА ВВОДА ОТ АДМИНОВ ===
# ============================================================
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
    target_id = await resolve_user(text)
    
    if not target_id:
        m = await msg.answer("❌ Пользователь не найден!")
        asyncio.create_task(delete_after(m, 10))
        return

    # === СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ ===
    if action == "user_stats":
        stats = await get_user_stats(target_id, msg.chat.id)
        username = await get_username_by_id(target_id)
        report = (
            f"📊 **Статистика пользователя**\n"
            f"━" * 30 + "\n"
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
        report += "\n━" * 30 + "\n"
        report += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        # Кнопка "Показать фулл" для главных админов
        keyboard = None
        if user_id in ADMIN_IDS:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Показать фулл", callback_data=f"full_stats_{target_id}")]
            ])
        
        m = await msg.answer(report, parse_mode="Markdown", reply_markup=keyboard)
        asyncio.create_task(delete_after(m, 45))
        current_action[user_id] = None
        return

    # === ОСТАЛЬНЫЕ ДЕЙСТВИЯ ===
    if action == "warn":
        await add_warning(target_id, msg.chat.id, "Нарушение", user_id)
        warns = await get_warnings(target_id, msg.chat.id)
        settings = await get_channel_settings(msg.chat.id)
        if warns >= settings['warn_limit']:
            await add_mute(target_id, settings['mute_duration'])
            m = await msg.answer(f"⚠️ {warns} варнов! Мут {settings['mute_duration']//60} мин!")
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
            f"📊 Введи уровень (0-7):\n\n"
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

    # === НАСТРОЙКА ОПЕРАТОРА ===
    if action == "get_channel_for_operator":
        try:
            channel_id = int(text)
            target_user[user_id] = channel_id
            current_action[user_id] = "setup_operator"
            m = await msg.answer(f"📝 Введи @username оператора:")
            asyncio.create_task(delete_after(m, 30))
        except:
            m = await msg.answer("❌ Введи ID канала!")
            asyncio.create_task(delete_after(m, 10))
        return

    if action == "setup_operator":
        channel_id = target_user.get(user_id)
        operator_id = await resolve_user(text)
        if not operator_id:
            m = await msg.answer("❌ Пользователь не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_operator(channel_id, operator_id, text.replace('@', ''))
        m = await msg.answer(f"✅ Оператор назначен")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return

    if action == "setup_operator" and isinstance(target_user.get(user_id), int):
        channel_id = target_user.get(user_id)
        operator_id = await resolve_user(text)
        if not operator_id:
            m = await msg.answer("❌ Пользователь не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_operator(channel_id, operator_id, text.replace('@', ''))
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
            m = await msg.answer(f"📝 Введи @username главы:")
            asyncio.create_task(delete_after(m, 30))
        except:
            m = await msg.answer("❌ Введи ID канала!")
            asyncio.create_task(delete_after(m, 10))
        return

    if action == "setup_owner":
        channel_id = target_user.get(user_id)
        owner_id = await resolve_user(text)
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

# ============================================================
# === ФИЛЬТР СООБЩЕНИЙ ===
# ============================================================
@dp.message(F.text)
async def filter_msg(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)

    settings = await get_channel_settings(msg.chat.id)
    if not settings['enabled']:
        return

    if level >= 2:
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
        await log_admin_action(0, "🚨 Автомут (угрозы)", user_id, "Угрозы")
        m1 = await msg.answer("🚨 **УГРОЗЫ ЗАПРЕЩЕНЫ!**")
        m2 = await msg.answer(f"⛔ Мут {settings['mute_duration']//60} минут!")
        asyncio.create_task(delete_after(m1, 10))
        asyncio.create_task(delete_after(m2, 10))
        return

    if has_photo and has_bad_words(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "badwords_with_photo")
        await log_admin_action(0, "🚫 Мат с фото", user_id, "Мат с фото")
        m = await msg.answer("🚫 **Мат с фото запрещён!**")
        asyncio.create_task(delete_after(m, 10))
        return

    if await has_blocked_link(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "blocked_link")
        await log_admin_action(0, "🔗 Блокировка ссылки", user_id, "Запрещённая ссылка")
        m = await msg.answer("🔗 **Ссылка заблокирована!**")
        asyncio.create_task(delete_after(m, 10))
        return

# ============================================================
# === КАНАЛЫ ===
# ============================================================
@dp.channel_post()
async def filter_channel_posts(msg: types.Message):
    if not msg.text and not msg.caption:
        return
    settings = await get_channel_settings(msg.chat.id)
    if not settings['enabled']:
        return
    text = msg.text or msg.caption or ""
    has_photo = bool(msg.photo or msg.video)
    if has_violence(text) or (has_photo and has_bad_words(text)) or (await has_blocked_link(text)):
        try:
            await msg.delete()
            await add_violation(msg.sender_chat.id if msg.sender_chat else 0, msg.chat.id, "channel_violation")
        except:
            pass

# ============================================================
# === ФОНОВЫЕ ЗАДАЧИ ===
# ============================================================
async def background_tasks():
    while True:
        try:
            async with aiosqlite.connect("bot.db") as db:
                await db.execute("DELETE FROM warnings WHERE date < datetime('now', '-1 day')")
                await db.commit()
            
            now = datetime.now()
            if now.hour == 0 and now.minute == 0:
                try:
                    await bot.send_message(
                        LOG_CHANNEL_ID,
                        f"☀️ **Ежедневный отчёт**\n"
                        f"━" * 30 + "\n"
                        f"📅 {now.strftime('%d.%m.%Y')}\n\n"
                        f"✨ Бот работает стабильно!\n"
                        f"🌴 Хорошего дня!",
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

# ============================================================
# === ВЕБ-СЕРВЕР ===
# ============================================================
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

# ============================================================
# === ЗАПУСК ===
# ============================================================
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
