import asyncio
import time
import re
import random
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

current_action = None
target_user = None
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
    except Exception as e:
        print(f"Ошибка получения пользователя {username}: {e}")
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
    if re.search(r'у[б6]', t) and re.search(r'(тебя|вас|его|ее|их|меня|нас)', t):
        return True
    if "смерть" in t and re.search(r'(тебе|вам|ему|ей|им|всем)', t):
        return True
    if "кровь" in t and re.search(r'(пущу|пролью|выпущу|вылью|прольем)', t):
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
        buttons.append([InlineKeyboardButton(text="⚠️ Варн", callback_data="warn")])
        buttons.append([InlineKeyboardButton(text="📋 Проверить варны", callback_data="check_warns")])
    if level >= 3:
        buttons.append([InlineKeyboardButton(text="🔨 Мут", callback_data="mute")])
        buttons.append([InlineKeyboardButton(text="🔕 Тихий мут", callback_data="silent_mute")])
        buttons.append([InlineKeyboardButton(text="🔓 Размут", callback_data="unmute")])
    if level >= 4:
        buttons.append([InlineKeyboardButton(text="🗑️ Очистить варны", callback_data="clear_warns")])
        buttons.append([InlineKeyboardButton(text="📊 Статистика", callback_data="stats")])
    if level >= 5:
        buttons.append([InlineKeyboardButton(text="🛡️ Назначить модератора", callback_data="set_moderator")])
    if level >= 6:
        buttons.append([InlineKeyboardButton(text="👑 Назначить админа", callback_data="set_admin")])
        buttons.append([InlineKeyboardButton(text="📢 Назначить оператора", callback_data="set_channel_operator")])
        buttons.append([InlineKeyboardButton(text="👑 Назначить главу канала", callback_data="set_channel_owner")])
        buttons.append([InlineKeyboardButton(text="📋 Список операторов", callback_data="list_operators")])
        buttons.append([InlineKeyboardButton(text="🔗 Управление ссылками", callback_data="manage_links")])
    if level >= 7:
        buttons.append([InlineKeyboardButton(text="⭐ Управление уровнями", callback_data="set_level")])
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# === START ===
@dp.message(Command("start"))
async def start(msg: types.Message):
    m = await msg.answer(
        "👋 **Бот-модератор v2.0**\n\n"
        "✅ Мат разрешён (без фото)\n"
        "🚫 Угрозы блокируются\n"
        "⚠️ 3 варна = мут 5 мин\n"
        "📢 Работает в каналах!\n"
        "👤 У каждого канала свой оператор\n"
        "📊 Есть статистика\n"
        "🎁 Ежедневный бонус\n\n"
        "📌 **Команды:**\n"
        "👑 /admin - панель управления\n"
        "👤 /myrole - узнать свою роль\n"
        "📊 /admins - список админов\n"
        "📢 /setup_operator - настроить оператора\n"
        "👑 /set_owner - назначить главу канала\n"
        "🎁 /daily - получить бонус\n"
        "📊 /stats - статистика чата\n"
        "📝 /poll - создать опрос\n"
        "🔗 /whitelist - белый список ссылок\n"
        "🔗 /whitelink <домен> - добавить в белый список"
    )
    asyncio.create_task(delete_after(m, 60))

# === DAILY BONUS ===
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
            f"Приходи завтра за новым бонусом!"
        )
        asyncio.create_task(delete_after(m, 30))
    else:
        remaining = 86400 - (int(time.time()) % 86400)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        m = await msg.answer(
            f"⏳ **Бонус уже получен!**\n\n"
            f"Следующий бонус через: {hours}ч {minutes}м\n"
            f"🔥 Стрик: {streak} дней"
        )
        asyncio.create_task(delete_after(m, 20))

# === MYROLE ===
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

# === ADMINS LIST ===
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

# === STATS ===
@dp.message(Command("stats"))
async def show_stats(msg: types.Message):
    chat_id = msg.chat.id
    violations = await get_violations_stats(chat_id, 10)
    if not violations:
        m = await msg.answer("📊 Статистика пуста")
        asyncio.create_task(delete_after(m, 15))
        return
    text = f"📊 **Статистика нарушений в чате**\n\n"
    for idx, (user_id, count) in enumerate(violations, 1):
        username = await get_username_by_id(user_id)
        text += f"{idx}. {username} — {count} нарушений\n"
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 30))

# === POLL ===
@dp.message(Command("poll"))
async def create_poll_cmd(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 2:
        m = await msg.answer("⛔ Нет прав для создания опросов!")
        asyncio.create_task(delete_after(m, 10))
        return
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        m = await msg.answer(
            "📝 **Создание опроса**\n\n"
            "Использование: `/poll Вопрос | Вариант1 | Вариант2 | Вариант3`\n\n"
            "Пример:\n"
            "`/poll Какой язык лучше? | Python | JavaScript | Go`"
        )
        asyncio.create_task(delete_after(m, 30))
        return
    parts = args[1].split('|')
    if len(parts) < 2:
        m = await msg.answer("❌ Нужно минимум 2 варианта!")
        asyncio.create_task(delete_after(m, 10))
        return
    question = parts[0].strip()
    options = [opt.strip() for opt in parts[1:]]
    if len(options) > 10:
        m = await msg.answer("❌ Максимум 10 вариантов!")
        asyncio.create_task(delete_after(m, 10))
        return
    poll_id = await create_poll(msg.chat.id, user_id, question, options)
    buttons = []
    for idx, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"poll_{poll_id}_{idx}")])
    buttons.append([InlineKeyboardButton(text="📊 Результаты", callback_data=f"poll_results_{poll_id}")])
    buttons.append([InlineKeyboardButton(text="🔒 Закрыть опрос", callback_data=f"poll_close_{poll_id}")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    m = await msg.answer(
        f"📊 **Опрос**\n\n"
        f"❓ {question}\n\n"
        f"Голосуйте!",
        reply_markup=keyboard
    )
    pending_polls[poll_id] = {"message_id": m.message_id, "chat_id": msg.chat.id}

# === WHITELIST ===
@dp.message(Command("whitelist"))
async def show_whitelist(msg: types.Message):
    domains = await get_whitelist_domains()
    if not domains:
        m = await msg.answer("🔗 Белый список ссылок пуст")
        asyncio.create_task(delete_after(m, 15))
        return
    text = "🔗 **Белый список ссылок:**\n\n"
    for domain in domains:
        text += f"• {domain}\n"
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 30))

@dp.message(Command("whitelink"))
async def add_whitelink(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 6:
        m = await msg.answer("⛔ Нет прав! Нужен уровень 6+")
        asyncio.create_task(delete_after(m, 10))
        return
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        m = await msg.answer("📝 Использование: `/whitelink domain.com`")
        asyncio.create_task(delete_after(m, 15))
        return
    domain = args[1].strip().lower()
    domain = re.sub(r'^https?://', '', domain)
    domain = re.sub(r'^www\.', '', domain)
    await add_whitelist_domain(domain, user_id)
    m = await msg.answer(f"✅ Домен `{domain}` добавлен в белый список!")
    await send_log(msg.chat.id, "🔗 Добавлен домен в белый список", f"Домен: {domain}\nДобавил: {user_id}")
    asyncio.create_task(delete_after(m, 15))

# === SETUP OPERATOR ===
@dp.message(Command("setup_operator"))
async def setup_operator_cmd(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if msg.chat.type not in ["channel", "supergroup"]:
        m = await msg.answer("❌ Эта команда работает только в каналах и группах!")
        asyncio.create_task(delete_after(m, 10))
        return
    channel_id = msg.chat.id
    if level < 6 and user_id not in ADMIN_IDS:
        m = await msg.answer("⛔ Только админы (уровень 6+) могут настраивать операторов!")
        asyncio.create_task(delete_after(m, 10))
        return
    current_op = await get_channel_operator(channel_id)
    global current_action
    current_action = "setup_operator"
    owner = await get_channel_owner(channel_id)
    text = f"📢 **Настройка оператора для канала**\n\n"
    text += f"📌 Канал: {msg.chat.title or channel_id}\n"
    text += f"🆔 ID: `{channel_id}`\n\n"
    if owner:
        owner_info = f"@{owner['owner_username']}" if owner['owner_username'] else f"ID: {owner['owner_id']}"
        text += f"👑 Глава канала: {owner_info}\n\n"
    if current_op:
        op_info = f"@{current_op['operator_username']}" if current_op['operator_username'] else f"ID: {current_op['operator_id']}"
        text += f"👤 Текущий оператор: {op_info}\n"
    else:
        text += f"👤 Оператор не назначен\n"
    text += f"\n📝 Введи ID или @username нового оператора:\n"
    text += f"   Или отправь `remove` чтобы удалить оператора"
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))

# === SET OWNER ===
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
    current_action = "set_owner"
    m = await msg.answer(
        f"👑 **Назначение главы канала**\n\n"
        f"📌 Канал: {msg.chat.title or msg.chat.id}\n\n"
        f"Введи ID или @username главы канала:"
    )
    asyncio.create_task(delete_after(m, 30))

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

# === КНОПКИ ===
@dp.callback_query()
async def buttons(call: types.CallbackQuery):
    global current_action
    user_id = call.from_user.id
    level = await get_user_level(user_id)
    
    if call.data.startswith("poll_"):
        parts = call.data.split("_")
        if len(parts) == 3:
            poll_id = int(parts[1])
            option_idx = int(parts[2])
            poll = await get_poll(poll_id)
            if not poll or not poll["is_active"]:
                await call.answer("❌ Опрос закрыт!", True)
                return
            success = await vote_poll(poll_id, user_id, option_idx)
            if success:
                await call.answer("✅ Ваш голос учтён!", show_alert=False)
                await update_poll_message(poll_id)
            else:
                await call.answer("⚠️ Вы уже голосовали!", True)
            return
        elif len(parts) == 3 and parts[1] == "results":
            poll_id = int(parts[2])
            await show_poll_results(call, poll_id)
            return
        elif len(parts) == 3 and parts[1] == "close":
            poll_id = int(parts[2])
            if level < 2:
                await call.answer("⛔ Нет прав!", True)
                return
            await close_poll(poll_id)
            await call.answer("🔒 Опрос закрыт!", True)
            await show_poll_results(call, poll_id)
            return
    
    if level < 2:
        await call.answer("⛔ Нет прав!", True)
        return
    if call.data == "close":
        await call.message.delete()
        await call.answer("Закрыто")
        return
    action = call.data
    if action == "warn" and level < 2:
        await call.answer("⛔ Нужен уровень 2+!", True)
        return
    if action in ["mute", "silent_mute", "unmute"] and level < 3:
        await call.answer("⛔ Нужен уровень 3+!", True)
        return
    if action in ["stats", "clear_warns"] and level < 4:
        await call.answer("⛔ Нужен уровень 4+!", True)
        return
    if action == "set_moderator" and level < 5:
        await call.answer("⛔ Нужен уровень 5+!", True)
        return
    if action in ["set_admin", "set_channel_operator", "set_channel_owner", "list_operators", "manage_links"] and level < 6:
        await call.answer("⛔ Нужен уровень 6+!", True)
        return
    if action == "set_level" and level < 7:
        await call.answer("⛔ Нужен уровень 7+!", True)
        return
    
    if action == "list_operators":
        ops = await get_all_channel_operators()
        if not ops:
            m = await call.message.answer("📋 Операторы не назначены ни для одного канала")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = "📢 **Список операторов каналов:**\n\n"
        for ch_id, op_id, op_name, ch_name in ops:
            owner = await get_channel_owner(ch_id)
            owner_info = f" (глава: @{owner['owner_username']})" if owner and owner['owner_username'] else ""
            text += f"📌 Канал: {ch_name or ch_id} (`{ch_id}`){owner_info}\n"
            text += f"👤 Оператор: `{op_id}`"
            if op_name:
                text += f" (@{op_name})"
            text += "\n\n"
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    if action == "stats":
        chat_id = call.message.chat.id
        violations = await get_violations_stats(chat_id, 10)
        if not violations:
            m = await call.message.answer("📊 Статистика пуста")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = f"📊 **Статистика нарушений в чате**\n\n"
        for idx, (uid, count) in enumerate(violations, 1):
            username = await get_username_by_id(uid)
            text += f"{idx}. {username} — {count} нарушений\n"
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    if action == "manage_links":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список белого списка", callback_data="show_whitelist")],
            [InlineKeyboardButton(text="➕ Добавить домен", callback_data="add_whitelist")],
            [InlineKeyboardButton(text="➖ Удалить домен", callback_data="remove_whitelist")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ])
        m = await call.message.answer("🔗 **Управление белым списком ссылок**", reply_markup=keyboard)
        await call.message.delete()
        await call.answer()
        return
    
    if action == "show_whitelist":
        domains = await get_whitelist_domains()
        if not domains:
            m = await call.message.answer("🔗 Белый список пуст")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = "🔗 **Белый список ссылок:**\n\n"
        for domain in domains:
            text += f"• {domain}\n"
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    if action == "add_whitelist":
        m = await call.message.answer("📝 Введи домен для добавления (например: example.com)")
        await call.message.delete()
        await call.answer()
        current_action = "add_whitelist"
        asyncio.create_task(delete_after(m, 30))
        return
    
    if action == "remove_whitelist":
        m = await call.message.answer("📝 Введи домен для удаления из белого списка")
        await call.message.delete()
        await call.answer()
        current_action = "remove_whitelist"
        asyncio.create_task(delete_after(m, 30))
        return
    
    if action == "set_channel_operator":
        m = await call.message.answer("📝 Введи ID канала, для которого назначить оператора:")
        await call.message.delete()
        await call.answer()
        current_action = "get_channel_for_operator"
        asyncio.create_task(delete_after(m, 30))
        return
    
    if action == "set_channel_owner":
        m = await call.message.answer("📝 Введи ID канала, для которого назначить главу:")
        await call.message.delete()
        await call.answer()
        current_action = "get_channel_for_owner"
        asyncio.create_task(delete_after(m, 30))
        return
    
    m = await call.message.answer(f"📝 Введи ID или @username для: {action}")
    await call.message.delete()
    await call.answer()
    current_action = action
    asyncio.create_task(delete_after(m, 30))

# === ОБНОВЛЕНИЕ СООБЩЕНИЯ С ОПРОСОМ ===
async def update_poll_message(poll_id: int):
    poll = await get_poll(poll_id)
    if not poll or poll_id not in pending_polls:
        return
    msg_data = pending_polls[poll_id]
    options = poll["options"]
    votes = poll["votes"]
    total = len(votes)
    text = f"📊 **Опрос**\n\n"
    text += f"❓ {poll['question']}\n\n"
    for idx, opt in enumerate(options):
        count = list(votes.values()).count(idx) if votes else 0
        percent = (count / total * 100) if total > 0 else 0
        bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
        text += f"{idx+1}. {opt}\n   {bar} {count} ({percent:.0f}%)\n\n"
    text += f"📊 Всего голосов: {total}"
    buttons = []
    if poll["is_active"]:
        for idx, opt in enumerate(options):
            buttons.append([InlineKeyboardButton(text=opt, callback_data=f"poll_{poll_id}_{idx}")])
        buttons.append([InlineKeyboardButton(text="📊 Обновить", callback_data=f"poll_results_{poll_id}")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await bot.edit_message_text(
            text,
            chat_id=msg_data["chat_id"],
            message_id=msg_data["message_id"],
            reply_markup=keyboard if poll["is_active"] else None
        )
    except:
        pass

# === ПОКАЗАТЬ РЕЗУЛЬТАТЫ ОПРОСА ===
async def show_poll_results(call: types.CallbackQuery, poll_id: int):
    poll = await get_poll(poll_id)
    if not poll:
        await call.answer("❌ Опрос не найден!", True)
        return
    options = poll["options"]
    votes = poll["votes"]
    total = len(votes)
    text = f"📊 **Результаты опроса**\n\n"
    text += f"❓ {poll['question']}\n\n"
    for idx, opt in enumerate(options):
        count = list(votes.values()).count(idx) if votes else 0
        percent = (count / total * 100) if total > 0 else 0
        bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
        text += f"{idx+1}. {opt}\n   {bar} {count} ({percent:.0f}%)\n\n"
    text += f"📊 Всего голосов: {total}"
    text += f"\n{'🔒 Опрос закрыт' if not poll['is_active'] else ''}"
    m = await call.message.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 30))

# === ОБРАБОТКА ПОСТОВ В КАНАЛЕ ===
@dp.channel_post()
async def filter_channel_posts(msg: types.Message):
    channel_id = msg.chat.id
    if not msg.text and not msg.caption:
        return
    text = msg.text or msg.caption or ""
    has_photo = bool(msg.photo or msg.video or msg.document or msg.animation)
    if has_violence(text):
        try:
            await msg.delete()
            await add_violation(msg.sender_chat.id if msg.sender_chat else 0, channel_id, "violence")
            operator = await get_channel_operator(channel_id)
            operator_info = f"@{operator['operator_username']}" if operator and operator['operator_username'] else f"ID: {operator['operator_id'] if operator else 'не назначен'}"
            await send_log(channel_id, "🚨 Удалён пост с угрозами", f"Текст: {text[:300]}...\n👤 Автор: @{msg.sender_chat.username if msg.sender_chat else 'Неизвестен'}\n👮 Оператор: {operator_info}")
            if operator:
                try:
                    await bot.send_message(operator['operator_id'], f"🚨 **В вашем канале удалён пост с угрозами!**\n\n📢 Канал: {msg.chat.title or channel_id}\n📝 Текст: {text[:300]}...\n👤 Автор: @{msg.sender_chat.username if msg.sender_chat else 'Неизвестен'}")
                except:
                    pass
        except Exception as e:
            print(f"Ошибка удаления поста: {e}")
        return
    if has_photo and has_bad_words(text):
        try:
            await msg.delete()
            await add_violation(msg.sender_chat.id if msg.sender_chat else 0, channel_id, "badwords_with_photo")
            m = await msg.answer("🚫 **Мат с фото запрещён!**\nТекст с матом можно писать без фото.")
            asyncio.create_task(delete_after(m, 10))
        except Exception as e:
            print(f"Ошибка удаления поста с матом: {e}")
        return
    if await has_blocked_link(text):
        try:
            await msg.delete()
            await add_violation(msg.sender_chat.id if msg.sender_chat else 0, channel_id, "blocked_link")
            m = await msg.answer("🔗 **Ссылка заблокирована!**\nРазрешены только ссылки из белого списка.")
            asyncio.create_task(delete_after(m, 10))
        except Exception as e:
            print(f"Ошибка удаления ссылки: {e}")
        return

# === ФИЛЬТР СООБЩЕНИЙ В ЧАТЕ ===
@dp.message(F.text)
async def filter_msg(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level >= 2:
        return
    if await is_muted(user_id):
        await msg.delete()
        m = await msg.answer("⛔ Ты в муте!")
        asyncio.create_task(delete_after(m, 5))
        return
    text = msg.text or ""
    has_photo = bool(msg.photo or msg.video or msg.document or msg.animation)
    if has_violence(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "violence")
        await add_mute(user_id, 300)
        m1 = await msg.answer("🚨 **УГРОЗЫ ЗАПРЕЩЕНЫ!**")
        m2 = await msg.answer("⛔ Автоматический мут 5 минут!")
        asyncio.create_task(delete_after(m1, 10))
        asyncio.create_task(delete_after(m2, 10))
        return
    if has_photo and has_bad_words(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "badwords_with_photo")
        m = await msg.answer("🚫 **Мат с фото запрещён!**\nТекст с матом можно писать без фото.")
        asyncio.create_task(delete_after(m, 10))
        return
    if await has_blocked_link(text):
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "blocked_link")
        m = await msg.answer("🔗 **Ссылка заблокирована!**\nИспользуй только разрешённые ссылки.")
        asyncio.create_task(delete_after(m, 10))
        return

# === ВВОД ОТ АДМИНА ===
@dp.message()
async def admin_input(msg: types.Message):
    global current_action, target_user
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 2 and current_action not in ["setup_operator", "get_channel_for_operator", "setup_operator_from_admin", "set_owner", "get_channel_for_owner", "add_whitelist", "remove_whitelist"]:
        return
    text = msg.text.strip()
    if not text:
        return

    if current_action == "add_whitelist":
        domain = text.lower()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        await add_whitelist_domain(domain, user_id)
        m = await msg.answer(f"✅ Домен `{domain}` добавлен в белый список!")
        await send_log(msg.chat.id, "🔗 Добавлен домен", f"Домен: {domain}")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return

    if current_action == "remove_whitelist":
        domain = text.lower()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        await remove_whitelist_domain(domain)
        m = await msg.answer(f"✅ Домен `{domain}` удалён из белого списка!")
        await send_log(msg.chat.id, "🔗 Удалён домен", f"Домен: {domain}")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return

    if current_action == "setup_operator":
        channel_id = msg.chat.id
        if text.lower() == "remove":
            await remove_channel_operator(channel_id)
            m = await msg.answer(f"✅ Оператор для канала {msg.chat.title or channel_id} удалён!")
            await send_log(channel_id, "🔄 Удалён оператор", f"Канал: {msg.chat.title or channel_id}")
            current_action = None
            asyncio.create_task(delete_after(m, 15))
            return
        operator_id = None
        operator_username = ""
        if text.startswith("@"):
            operator_id = await get_user_id_by_username(text)
            if operator_id:
                operator_username = text[1:]
        else:
            try:
                operator_id = int(text)
            except ValueError:
                pass
        if not operator_id:
            m = await msg.answer(f"❌ Пользователь {text} не найден! Попробуй ввести ID.")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_operator(channel_id, operator_id, operator_username, msg.chat.title or str(channel_id))
        owner = await get_channel_owner(channel_id)
        owner_info = f" (глава: @{owner['owner_username']})" if owner and owner['owner_username'] else ""
        m = await msg.answer(f"✅ **Оператор назначен!**\n\n📢 Канал: {msg.chat.title or channel_id}\n👤 Оператор: `{operator_id}`" + (f" (@{operator_username})" if operator_username else "") + f"\n{owner_info}")
        await send_log(channel_id, "👤 Назначен оператор", f"Канал: {msg.chat.title or channel_id}\nОператор: {operator_id} (@{operator_username})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return

    if current_action == "set_owner":
        channel_id = msg.chat.id
        owner_id = None
        owner_username = ""
        if text.startswith("@"):
            owner_id = await get_user_id_by_username(text)
            if owner_id:
                owner_username = text[1:]
        else:
            try:
                owner_id = int(text)
            except ValueError:
                pass
        if not owner_id:
            m = await msg.answer(f"❌ Пользователь {text} не найден! Попробуй ввести ID.")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_owner(channel_id, owner_id, owner_username)
        m = await msg.answer(f"👑 **Глава канала назначен!**\n\n📢 Канал: {msg.chat.title or channel_id}\n👑 Глава: `{owner_id}`" + (f" (@{owner_username})" if owner_username else ""))
        await send_log(channel_id, "👑 Назначен глава канала", f"Глава: {owner_id} (@{owner_username})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return

    if current_action == "get_channel_for_operator":
        try:
            channel_id = int(text)
            current_action = "setup_operator_from_admin"
            target_user = channel_id
            m = await msg.answer(f"📝 Введи ID или @username оператора для канала `{channel_id}`:")
            asyncio.create_task(delete_after(m, 30))
            return
        except ValueError:
            m = await msg.answer("❌ Введи корректный ID канала!")
            asyncio.create_task(delete_after(m, 10))
            return

    if current_action == "setup_operator_from_admin":
        channel_id = target_user
        operator_id = None
        operator_username = ""
        if text.startswith("@"):
            operator_id = await get_user_id_by_username(text)
            if operator_id:
                operator_username = text[1:]
        else:
            try:
                operator_id = int(text)
            except ValueError:
                pass
        if not operator_id:
            m = await msg.answer(f"❌ Пользователь {text} не найден! Попробуй ввести ID.")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_operator(channel_id, operator_id, operator_username, "")
        m = await msg.answer(f"✅ Оператор назначен для канала `{channel_id}`!\n👤 Оператор: `{operator_id}`" + (f" (@{operator_username})" if operator_username else ""))
        await send_log(channel_id, "👤 Назначен оператор", f"Оператор: {operator_id} (@{operator_username})")
        current_action = None
        target_user = None
        asyncio.create_task(delete_after(m, 15))
        return

    if current_action == "get_channel_for_owner":
        try:
            channel_id = int(text)
            current_action = "set_owner_from_admin"
            target_user = channel_id
            m = await msg.answer(f"📝 Введи ID или @username главы для канала `{channel_id}`:")
            asyncio.create_task(delete_after(m, 30))
            return
        except ValueError:
            m = await msg.answer("❌ Введи корректный ID канала!")
            asyncio.create_task(delete_after(m, 10))
            return

    if current_action == "set_owner_from_admin":
        channel_id = target_user
        owner_id = None
        owner_username = ""
        if text.startswith("@"):
            owner_id = await get_user_id_by_username(text)
            if owner_id:
                owner_username = text[1:]
        else:
            try:
                owner_id = int(text)
            except ValueError:
                pass
        if not owner_id:
            m = await msg.answer(f"❌ Пользователь {text} не найден! Попробуй ввести ID.")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_owner(channel_id, owner_id, owner_username)
        m = await msg.answer(f"👑 Глава назначен для канала `{channel_id}`!\n👑 Глава: `{owner_id}`" + (f" (@{owner_username})" if owner_username else ""))
        await send_log(channel_id, "👑 Назначен глава", f"Глава: {owner_id} (@{owner_username})")
        current_action = None
        target_user = None
        asyncio.create_task(delete_after(m, 15))
        return

    # Обработка остальных команд (мут, варн, уровни)
    target_user_id = None
    display_name = text
    if text.startswith("@"):
        target_user_id = await get_user_id_by_username(text)
        if not target_user_id:
            m = await msg.answer(f"❌ Пользователь {text} не найден! Попробуй ввести ID.")
            asyncio.create_task(delete_after(m, 10))
            return
    else:
        try:
            target_user_id = int(text)
        except ValueError:
            m = await msg.answer("❌ Введи ID или @username!")
            asyncio.create_task(delete_after(m, 10))
            return

    target_level = await get_user_level(target_user_id)
    if target_level >= level and target_user_id not in ADMIN_IDS and level < 7:
        m = await msg.answer(f"❌ Нельзя управлять пользователем с уровнем {target_level}!")
        asyncio.create_task(delete_after(m, 10))
        return

    action = current_action

    if action == "silent_mute":
        if level < 3:
            m = await msg.answer("⛔ Нужен уровень 3+!")
            asyncio.create_task(delete_after(m, 10))
            return
        target_user = target_user_id
        current_action = "silent_mute_duration"
        m = await msg.answer(f"🔕 Введи длительность тихого мута (сек) для {display_name}:")
        asyncio.create_task(delete_after(m, 30))
        return

    if action == "silent_mute_duration":
        try:
            duration = int(text)
            await add_mute(target_user, duration)
            m = await msg.answer(f"🔕 {target_user} замучен тихо на {duration} сек")
            await send_log(msg.chat.id, "🔕 Тихий мут", f"Пользователь: {target_user}\nДлительность: {duration} сек")
            current_action = None
            target_user = None
            asyncio.create_task(delete_after(m, 15))
        except ValueError:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return

    if action == "mute":
        if level < 3:
            m = await msg.answer("⛔ Нужен уровень 3+!")
            asyncio.create_task(delete_after(m, 10))
            return
        target_user = target_user_id
        current_action = "mute_duration"
        m = await msg.answer(f"⏱️ Введи длительность мута (сек) для {display_name}:")
        asyncio.create_task(delete_after(m, 30))
        return

    if action == "mute_duration":
        try:
            duration = int(text)
            await add_mute(target_user, duration)
            m = await msg.answer(f"✅ {target_user} замучен на {duration} сек")
            await send_log(msg.chat.id, "🔨 Мут", f"Пользователь: {target_user}\nДлительность: {duration} сек")
            current_action = None
            target_user = None
            asyncio.create_task(delete_after(m, 15))
        except ValueError:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return

    if action == "unmute":
        if level < 3:
            m = await msg.answer("⛔ Нужен уровень 3+!")
            asyncio.create_task(delete_after(m, 10))
            return
        await remove_mute(target_user_id)
        m = await msg.answer(f"✅ {display_name} размучен")
        await send_log(msg.chat.id, "🔓 Размут", f"Пользователь: {display_name} ({target_user_id})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return

    if action == "warn":
        target_user = target_user_id
        current_action = "warn_reason"
        m = await msg.answer(f"📝 Введи причину варна для {display_name}:")
        asyncio.create_task(delete_after(m, 30))
        return

    if action == "warn_reason":
        reason = text
        await add_warning(target_user, msg.chat.id, reason)
        warns = await get_warnings(target_user, msg.chat.id)
        if warns >= 3:
            await add_mute(target_user, 300)
            m = await msg.answer(f"⚠️ 3 варна! {target_user} замучен на 5 минут")
            await send_log(msg.chat.id, "⚠️ Автомут", f"Пользователь: {target_user}\nПричина: 3 варна")
            await clear_warnings(target_user, msg.chat.id)
        else:
            m = await msg.answer(f"✅ Варн {warns}/3 для {target_user}")
        current_action = None
        target_user = None
        asyncio.create_task(delete_after(m, 15))
        return

    if action == "check_warns":
        warns = await get_warnings(target_user_id, msg.chat.id)
        m = await msg.answer(f"📋 У {display_name} - {warns} варнов")
        current_action = None
        asyncio.create_task(delete_after(m, 20))
        return

    if action == "clear_warns":
        if level < 4:
            m = await msg.answer("⛔ Нужен уровень 4+!")
            asyncio.create_task(delete_after(m, 10))
            return
        await clear_warnings(target_user_id, msg.chat.id)
        m = await msg.answer(f"✅ Варны {display_name} очищены")
        await send_log(msg.chat.id, "🗑️ Очищены варны", f"Пользователь: {display_name} ({target_user_id})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return

    if action == "set_moderator":
        if level < 5:
            m = await msg.answer("⛔ Нужен уровень 5+!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_user_level(target_user_id, 2)
        m = await msg.answer(f"🛡️ {display_name} теперь МОДЕРАТОР (уровень 2)!")
        await send_log(msg.chat.id, "🛡️ Назначен модератор", f"Пользователь: {display_name} ({target_user_id})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return

    if action == "set_admin":
        if level < 6:
            m = await msg.answer("⛔ Нужен уровень 6+!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_user_level(target_user_id, 5)
        m = await msg.answer(f"👑 {display_name} теперь АДМИН (уровень 5)!")
        await send_log(msg.chat.id, "👑 Назначен админ", f"Пользователь: {display_name} ({target_user_id})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return

    if action == "set_level":
        if level < 7:
            m = await msg.answer("⛔ Нужен уровень 7+!")
            asyncio.create_task(delete_after(m, 10))
            return
        target_user = target_user_id
        current_action = "set_level_input"
        m = await msg.answer(
            f"📊 Введи уровень для {display_name} (0-7):\n\n"
            "0 - Пользователь\n"
            "1 - Наблюдатель 🟢\n"
            "2 - Стажёр 🟡\n"
            "3 - Модератор 🟠\n"
            "4 - Старший модератор 🔵\n"
            "5 - Заместитель 🟣\n"
            "6 - Администратор 🔴\n"
            "7 - Главный администратор ⭐"
        )
        asyncio.create_task(delete_after(m, 60))
        return

    if action == "set_level_input":
        try:
            new_level = int(text)
            if 0 <= new_level <= 7:
                await set_user_level(target_user, new_level)
                level_name = ADMIN_LEVELS[new_level]["name"] if new_level > 0 else "Пользователь"
                emoji = ADMIN_LEVELS[new_level]["emoji"] if new_level > 0 else "👤"
                m = await msg.answer(f"✅ Уровень {target_user} изменён на {new_level} ({emoji} {level_name})")
                await send_log(msg.chat.id, "⭐ Изменён уровень", f"Пользователь: {target_user}\nНовый уровень: {new_level}")
                current_action = None
                target_user = None
                asyncio.create_task(delete_after(m, 15))
            else:
                m = await msg.answer("❌ Введи число от 0 до 7!")
                asyncio.create_task(delete_after(m, 10))
        except ValueError:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return

# === ВЕБ-СЕРВЕР ДЛЯ RENDER ===
async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("✅ Веб-сервер запущен на порту 10000")
    await asyncio.Event().wait()

# === ЗАПУСК ===
async def main():
    print("🚀 Запуск МЕГА-БОТА v2.0...")
    print(f"📢 Лог-канал: {LOG_CHANNEL_ID}")
    await init_db()
    print("✅ База данных готова")
    print("👑 Главный администратор (уровень 7):", ADMIN_IDS)
    print(f"📊 Загружено {len(VIOLENCE_WORDS)} угроз")
    print(f"📊 Загружено {len(BAD_WORDS)} матов")
    print(f"🔗 Белый список: {len(WHITELIST_DOMAINS)} доменов")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот работает!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_until_complete(start_web())
