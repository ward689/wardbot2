import asyncio
import time
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, ADMIN_IDS, ADMIN_LEVELS, LOG_CHANNEL_ID, VIOLENCE_WORDS, BAD_WORDS
from database import *

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

current_action = None
target_user = None

# === ПОЛУЧИТЬ ID ПО USERNAME ===
async def get_user_id(username: str) -> int:
    try:
        user = await bot.get_user(username)
        return user.id
    except:
        return None

# === АВТОУДАЛЕНИЕ ===
async def delete_after(msg, seconds=10):
    await asyncio.sleep(seconds)
    try: await msg.delete()
    except: pass

# === ПРОВЕРКА УГРОЗ ===
def has_violence(text: str) -> bool:
    t = text.lower()
    for w in VIOLENCE_WORDS:
        if w in t: return True
    clean = re.sub(r'[.,!?;:\s]+', '', t)
    for w in VIOLENCE_WORDS:
        if re.sub(r'[.,!?;:\s]+', '', w) in clean: return True
    if re.search(r'у[б6]', t) and re.search(r'(тебя|вас|его|ее|их)', t): return True
    if "смерть" in t and re.search(r'(тебе|вам|ему|ей|им)', t): return True
    if "кровь" in t and re.search(r'(пущу|пролью|выпущу|вылью)', t): return True
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

# === КНОПКИ (ИСПРАВЛЕНО - ДОБАВЛЕН AWAIT) ===
async def get_admin_keyboard(user_id: int):
    level = await get_user_level(user_id)  # <-- ДОБАВЛЕН AWAIT!
    
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
    
    if level >= 5:
        buttons.append([InlineKeyboardButton(text="🛡️ Назначить модератора", callback_data="set_moderator")])
    
    if level >= 6:
        buttons.append([InlineKeyboardButton(text="👑 Назначить админа", callback_data="set_admin")])
        buttons.append([InlineKeyboardButton(text="📢 Назначить оператора канала", callback_data="set_channel_operator")])
        buttons.append([InlineKeyboardButton(text="📋 Список операторов", callback_data="list_operators")])
    
    if level >= 7:
        buttons.append([InlineKeyboardButton(text="⭐ Управление уровнями", callback_data="set_level")])
    
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="close")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# === START ===
@dp.message(Command("start"))
async def start(msg):
    m = await msg.answer(
        "👋 Бот-модератор!\n\n"
        "✅ Мат разрешён\n"
        "🚫 Угрозы блокируются\n"
        "⚠️ 3 варна = мут 5 мин\n"
        "📢 Работает в каналах!\n"
        "👤 У каждого канала свой оператор\n\n"
        "👑 /admin - панель управления\n"
        "👤 /myrole - узнать свою роль\n"
        "📊 /admins - список админов\n"
        "📢 /setup_operator - настроить оператора"
    )
    asyncio.create_task(delete_after(m, 30))

# === MYROLE ===
@dp.message(Command("myrole"))
async def my_role(msg):
    level = await get_user_level(msg.from_user.id)
    role = await get_user_role(msg.from_user.id)
    
    ops = []
    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute("SELECT channel_id, channel_name FROM channel_operators WHERE operator_id = ?", (msg.from_user.id,))
        ops = await cursor.fetchall()
    
    text = f"👤 Твоя роль: {role}\n📊 Уровень: {level}"
    if ops:
        text += "\n\n📢 Ты оператор каналов:\n"
        for ch_id, ch_name in ops:
            text += f"• {ch_name or ch_id} (`{ch_id}`)\n"
    
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 15))

# === ADMINS LIST ===
@dp.message(Command("admins"))
async def list_admins(msg):
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
            text += f"{emoji} Уровень {level}: {name} (ID: `{user_id}`)\n"
    
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 30))

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
    
    text = f"📢 **Настройка оператора для канала**\n\n"
    text += f"📌 Канал: {msg.chat.title or channel_id}\n"
    text += f"🆔 ID: `{channel_id}`\n\n"
    
    if current_op:
        text += f"👤 Текущий оператор: `{current_op['operator_id']}`\n"
        if current_op['operator_username']:
            text += f"   (@{current_op['operator_username']})\n"
    else:
        text += f"👤 Оператор не назначен\n"
    
    text += f"\n📝 Введи ID или @username нового оператора:\n"
    text += f"   Или отправь `remove` чтобы удалить оператора"
    
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))

# === ADMIN (ИСПРАВЛЕНО!) ===
@dp.message(Command("admin"))
async def admin_panel(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    if level < 2:
        m = await msg.answer("⛔ У тебя нет прав! Минимальный уровень: 2")
        asyncio.create_task(delete_after(m, 10))
        return
    
    role = await get_user_role(user_id)
    
    # Ждём результат async функции
    keyboard = await get_admin_keyboard(user_id)  # <-- ДОБАВЛЕН AWAIT!
    
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
    
    if level < 2:
        await call.answer("⛔ Нет прав!", True)
        return
    
    if call.data == "close":
        await call.message.delete()
        await call.answer("Закрыто")
        return
    
    action = call.data
    
    # Проверка прав
    if action == "warn" and level < 2:
        await call.answer("⛔ Нужен уровень 2+!", True)
        return
    if action in ["mute", "silent_mute", "unmute"] and level < 3:
        await call.answer("⛔ Нужен уровень 3+!", True)
        return
    if action == "clear_warns" and level < 4:
        await call.answer("⛔ Нужен уровень 4+!", True)
        return
    if action == "set_moderator" and level < 5:
        await call.answer("⛔ Нужен уровень 5+!", True)
        return
    if action in ["set_admin", "set_channel_operator", "list_operators"] and level < 6:
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
            text += f"📌 Канал: {ch_name or ch_id} (`{ch_id}`)\n"
            text += f"👤 Оператор: `{op_id}`"
            if op_name:
                text += f" (@{op_name})"
            text += "\n\n"
        
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    if action == "set_channel_operator":
        m = await call.message.answer("📝 Введи ID канала, для которого назначить оператора:\n(Получить можно через @userinfobot)")
        await call.message.delete()
        await call.answer()
        current_action = "get_channel_for_operator"
        asyncio.create_task(delete_after(m, 30))
        return
    
    m = await call.message.answer(f"📝 Введи ID или @username для: {action}")
    await call.message.delete()
    await call.answer()
    current_action = action
    asyncio.create_task(delete_after(m, 30))

# === ОБРАБОТКА ПОСТОВ В КАНАЛЕ ===
@dp.channel_post()
async def filter_channel_posts(msg: types.Message):
    channel_id = msg.chat.id
    
    if not msg.text and not msg.caption:
        return
    
    text = msg.text or msg.caption or ""
    
    if has_violence(text):
        try:
            await msg.delete()
            
            operator = await get_channel_operator(channel_id)
            operator_info = f"@{operator['operator_username']}" if operator and operator['operator_username'] else f"ID: {operator['operator_id'] if operator else 'не назначен'}"
            
            await send_log(
                channel_id,
                "🚨 Удалён пост с угрозами",
                f"Текст: {text[:300]}...\n👤 Автор: @{msg.sender_chat.username if msg.sender_chat else 'Неизвестен'}\n👮 Оператор: {operator_info}"
            )
            
            if operator:
                try:
                    await bot.send_message(
                        operator['operator_id'],
                        f"🚨 **В вашем канале удалён пост с угрозами!**\n\n"
                        f"📢 Канал: {msg.chat.title or channel_id}\n"
                        f"📝 Текст: {text[:300]}...\n"
                        f"👤 Автор: @{msg.sender_chat.username if msg.sender_chat else 'Неизвестен'}"
                    )
                except:
                    pass
            
        except Exception as e:
            print(f"Ошибка удаления поста: {e}")

# === ОБРАБОТКА ВВОДА ===
@dp.message()
async def admin_input(msg: types.Message):
    global current_action, target_user
    
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    if level < 2 and current_action not in ["setup_operator", "get_channel_for_operator", "setup_operator_from_admin"]:
        return
    
    text = msg.text.strip()
    
    # === НАСТРОЙКА ОПЕРАТОРА ===
    if current_action == "setup_operator":
        channel_id = msg.chat.id
        
        if text.lower() == "remove":
            await remove_channel_operator(channel_id)
            m = await msg.answer(f"✅ Оператор для канала {msg.chat.title or channel_id} удалён!")
            await send_log(channel_id, "🔄 Удалён оператор", f"Канал: {msg.chat.title or channel_id}")
            current_action = None
            asyncio.create_task(delete_after(m, 15))
            return
        
        if text.startswith("@"):
            operator_id = await get_user_id(text)
            if not operator_id:
                m = await msg.answer(f"❌ Пользователь {text} не найден!")
                asyncio.create_task(delete_after(m, 10))
                return
            operator_username = text[1:]
        else:
            try:
                operator_id = int(text)
                operator_username = ""
            except ValueError:
                m = await msg.answer("❌ Введи ID или @username!")
                asyncio.create_task(delete_after(m, 10))
                return
        
        await set_channel_operator(channel_id, operator_id, operator_username, msg.chat.title or str(channel_id))
        m = await msg.answer(f"✅ Оператор назначен!\n📢 Канал: {msg.chat.title or channel_id}\n👤 Оператор: `{operator_id}`" + (f" (@{operator_username})" if operator_username else ""))
        await send_log(channel_id, "👤 Назначен оператор", f"Канал: {msg.chat.title or channel_id}\nОператор: {operator_id} (@{operator_username})")
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
        if text.startswith("@"):
            operator_id = await get_user_id(text)
            if not operator_id:
                m = await msg.answer(f"❌ Пользователь {text} не найден!")
                asyncio.create_task(delete_after(m, 10))
                return
            operator_username = text[1:]
        else:
            try:
                operator_id = int(text)
                operator_username = ""
            except ValueError:
                m = await msg.answer("❌ Введи ID или @username!")
                asyncio.create_task(delete_after(m, 10))
                return
        
        await set_channel_operator(channel_id, operator_id, operator_username, "")
        m = await msg.answer(f"✅ Оператор назначен для канала `{channel_id}`!\n👤 Оператор: `{operator_id}`" + (f" (@{operator_username})" if operator_username else ""))
        await send_log(channel_id, "👤 Назначен оператор", f"Оператор: {operator_id} (@{operator_username})")
        current_action = None
        target_user = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    # === ОСТАЛЬНЫЕ КОМАНДЫ ===
    if text.startswith("@"):
        target = await get_user_id(text)
        if not target:
            m = await msg.answer(f"❌ Пользователь {text} не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
        display_name = text
    else:
        try:
            target = int(text)
            display_name = text
        except ValueError:
            m = await msg.answer("❌ Введи ID или @username!")
            asyncio.create_task(delete_after(m, 10))
            return
    
    target_level = await get_user_level(target)
    if target_level >= level and target not in ADMIN_IDS and level < 7:
        m = await msg.answer(f"❌ Нельзя управлять пользователем с уровнем {target_level}!")
        asyncio.create_task(delete_after(m, 10))
        return
    
    action = current_action
    
    # === ТИХИЙ МУТ ===
    if action == "silent_mute":
        if level < 3:
            m = await msg.answer("⛔ Нужен уровень 3+!")
            asyncio.create_task(delete_after(m, 10))
            return
        target_user = target
        current_action = "silent_mute_duration"
        m = await msg.answer(f"🔕 Введи длительность тихого мута (сек) для {display_name}:\n(Пользователь не получит уведомление)")
        asyncio.create_task(delete_after(m, 30))
        return
    
    if action == "silent_mute_duration":
        try:
            duration = int(text)
            await add_mute(target_user, duration)
            m = await msg.answer(f"🔕 {target_user} замучен тихо на {duration} сек")
            await send_log(msg.chat.id, "🔕 Тихий мут", f"Пользователь: {target_user}\nДлительность: {duration} сек\n(без уведомления)")
            current_action = None
            target_user = None
            asyncio.create_task(delete_after(m, 15))
        except ValueError:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return
    
    # === ОБЫЧНЫЙ МУТ ===
    if action == "mute":
        if level < 3:
            m = await msg.answer("⛔ Нужен уровень 3+!")
            asyncio.create_task(delete_after(m, 10))
            return
        target_user = target
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
    
    # === РАЗМУТ ===
    if action == "unmute":
        if level < 3:
            m = await msg.answer("⛔ Нужен уровень 3+!")
            asyncio.create_task(delete_after(m, 10))
            return
        await remove_mute(target)
        m = await msg.answer(f"✅ {display_name} размучен")
        await send_log(msg.chat.id, "🔓 Размут", f"Пользователь: {display_name} ({target})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    # === ВАРН ===
    if action == "warn":
        target_user = target
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
    
    # === ПРОВЕРКА ВАРНОВ ===
    if action == "check_warns":
        warns = await get_warnings(target, msg.chat.id)
        m = await msg.answer(f"📋 У {display_name} - {warns} варнов")
        current_action = None
        asyncio.create_task(delete_after(m, 20))
        return
    
    # === ОЧИСТКА ВАРНОВ ===
    if action == "clear_warns":
        if level < 4:
            m = await msg.answer("⛔ Нужен уровень 4+!")
            asyncio.create_task(delete_after(m, 10))
            return
        await clear_warnings(target, msg.chat.id)
        m = await msg.answer(f"✅ Варны {display_name} очищены")
        await send_log(msg.chat.id, "🗑️ Очищены варны", f"Пользователь: {display_name} ({target})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    # === НАЗНАЧИТЬ МОДЕРАТОРА ===
    if action == "set_moderator":
        if level < 5:
            m = await msg.answer("⛔ Нужен уровень 5+!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_user_level(target, 2)
        m = await msg.answer(f"🛡️ {display_name} теперь МОДЕРАТОР (уровень 2)!")
        await send_log(msg.chat.id, "🛡️ Назначен модератор", f"Пользователь: {display_name} ({target})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    # === НАЗНАЧИТЬ АДМИНА ===
    if action == "set_admin":
        if level < 6:
            m = await msg.answer("⛔ Нужен уровень 6+!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_user_level(target, 5)
        m = await msg.answer(f"👑 {display_name} теперь АДМИН (уровень 5)!")
        await send_log(msg.chat.id, "👑 Назначен админ", f"Пользователь: {display_name} ({target})")
        current_action = None
        asyncio.create_task(delete_after(m, 15))
        return
    
    # === УПРАВЛЕНИЕ УРОВНЯМИ ===
    if action == "set_level":
        if level < 7:
            m = await msg.answer("⛔ Нужен уровень 7+!")
            asyncio.create_task(delete_after(m, 10))
            return
        target_user = target
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

# === ФИЛЬТР СООБЩЕНИЙ ===
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
    
    if has_violence(msg.text):
        await msg.delete()
        m1 = await msg.answer("🚨 УГРОЗЫ ЗАПРЕЩЕНЫ!")
        await add_mute(user_id, 300)
        m2 = await msg.answer("⛔ Мут 5 минут!")
        asyncio.create_task(delete_after(m1, 10))
        asyncio.create_task(delete_after(m2, 10))

# === ЗАПУСК ===
async def main():
    print("🚀 Запуск бота с мультиканальной системой...")
    print(f"📢 Лог-канал: {LOG_CHANNEL_ID}")
    await init_db()
    print("✅ База данных готова")
    print("👑 Главный администратор (уровень 7):", ADMIN_IDS)
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот работает!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())