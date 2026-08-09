import asyncio
import time
import re
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, Message
from config import BOT_TOKEN, ADMIN_IDS, LOG_CHANNEL_ID, DB_NAME, ADMIN_LEVELS, FORBIDDEN_WORDS, BAD_WORDS, COIN_PRICES, STARS_PRICES, SUBSCRIPTION_PRICE, SUBSCRIPTION_STARS, SHOP_CHANNEL_IDS, DAILY_BONUS_MIN, DAILY_BONUS_MAX
import database
from database import *
from states import AdminStates, AutoResponseStates
from aiohttp import web

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

user_selected_chat = {}


@dp.update.outer_middleware()
async def remember_users_middleware(handler, event, data):
    """Запоминает всех, кого видит бот, чтобы потом искать их по @username."""
    msg = event.message or event.edited_message
    users = []
    if msg:
        users.append(msg.from_user)
        if msg.reply_to_message:
            users.append(msg.reply_to_message.from_user)
        users.extend(msg.new_chat_members or [])
        for entity in (msg.entities or []) + (msg.caption_entities or []):
            if entity.user:
                users.append(entity.user)
    elif event.callback_query:
        users.append(event.callback_query.from_user)

    chat_id = msg.chat.id if msg else None
    for user in users:
        if user and not user.is_bot:
            try:
                await remember_user(user.id, user.username, user.first_name)
                if chat_id and msg.chat.type in ("group", "supergroup"):
                    await remember_chat_member(chat_id, user.id)
            except Exception as e:
                print(f"Ошибка кэша пользователя: {e}")
    return await handler(event, data)

# ============================================================
# === УНИВЕРСАЛЬНЫЙ ПОИСК ПОЛЬЗОВАТЕЛЯ ===
# ============================================================
async def resolve_user(text: str, chat_id: int = None) -> int:
    text = text.strip()
    try:
        return int(text)
    except ValueError:
        pass
    username = text[1:] if text.startswith("@") else text
    # Bot API не умеет искать людей по @username, поэтому сначала смотрим в свой кэш.
    cached_id = await get_user_id_by_username(username)
    if cached_id:
        return cached_id
    try:
        chat = await bot.get_chat(f"@{username}")
        if chat and chat.id:
            return chat.id
    except Exception:
        pass
    return None

async def resolve_target(msg: types.Message, text: str = None) -> int:
    """Цель команды: ответ на сообщение, упоминание без @username, или текстовый аргумент."""
    if msg.reply_to_message and msg.reply_to_message.from_user:
        return msg.reply_to_message.from_user.id
    for entity in (msg.entities or []):
        if entity.user:
            return entity.user.id
    if not text:
        return None
    return await resolve_user(text, msg.chat.id)

USER_NOT_FOUND_HINT = (
    "❌ Пользователь {target} не найден!\n"
    "💡 Telegram не позволяет ботам искать по @username — бот запоминает только тех, кто писал в чате после его добавления.\n"
    "Ответьте командой на сообщение пользователя или укажите его ID."
)

async def get_username_by_id(user_id: int) -> str:
    try:
        chat = await bot.get_chat(user_id)
        if chat.username:
            return f"@{chat.username}"
        if chat.first_name:
            return chat.first_name
    except Exception:
        pass
    return await get_cached_username(user_id) or str(user_id)

database.set_username_resolver(get_username_by_id)

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

def has_forbidden(text: str) -> tuple:
    if not text:
        return False, None
    t = text.lower()
    for word in FORBIDDEN_WORDS:
        if word in t:
            return True, word
    clean = re.sub(r'[.,!?;:\s]+', '', t)
    for word in FORBIDDEN_WORDS:
        if re.sub(r'[.,!?;:\s]+', '', word) in clean:
            return True, word
    return False, None

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
        if not any(domain == allowed or domain.endswith(f".{allowed}") for allowed in whitelist):
            return True
    return False

# ============================================================
# === КРАСИВЫЕ ЛОГИ ===
# ============================================================
async def send_log(channel_id: int, action: str, details: str):
    try:
        log_text = (
            f"📋 **Лог модерации**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 Канал: `{channel_id}`\n"
            f"🔧 Действие: {action}\n"
            f"{details}\n"
            f"🕐 Время: {time.strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await bot.send_message(LOG_CHANNEL_ID, log_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка лога: {e}")

# ============================================================
# === КНОПКИ ===
# ============================================================
async def get_admin_keyboard(user_id: int):
    level = await get_user_level(user_id)
    buttons = []
    if level >= 1:
        buttons.append([InlineKeyboardButton(text="⚠️ Варн", callback_data="admin_warn")])
        buttons.append([InlineKeyboardButton(text="📋 Варны пользователя", callback_data="admin_check_warns")])
    if level >= 2:
        buttons.append([InlineKeyboardButton(text="🔒 Мут", callback_data="admin_mute")])
        buttons.append([InlineKeyboardButton(text="🔓 Размут", callback_data="admin_unmute")])
    if level >= 3:
        buttons.append([InlineKeyboardButton(text="🗑️ Очистить варны", callback_data="admin_clear_warns")])
        buttons.append([InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")])
        buttons.append([InlineKeyboardButton(text="👑 Выдать админку", callback_data="admin_give_admin")])
    if level >= 4:
        buttons.append([InlineKeyboardButton(text="⭐ Управление уровнями", callback_data="admin_set_level")])
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ============================================================
# === КОМАНДА /id ===
# ============================================================
@dp.message(Command("id"))
async def get_user_id(msg: types.Message):
    args = msg.text.split()
    if len(args) >= 2 or msg.reply_to_message:
        target = args[1] if len(args) >= 2 else ""
        target_id = await resolve_target(msg, target)
        if target_id:
            username = await get_username_by_id(target_id)
            await msg.answer(
                f"👤 **Пользователь найден!**\n\n"
                f"📌 Юзернейм: {username}\n"
                f"🆔 ID: `{target_id}`",
                parse_mode="Markdown"
            )
            return
        await msg.answer(USER_NOT_FOUND_HINT.format(target=target))
        return
    if msg.reply_to_message:
        user = msg.reply_to_message.from_user
        if user:
            username = await get_username_by_id(user.id)
            await msg.answer(
                f"👤 {username}\n🆔 ID: `{user.id}`",
                parse_mode="Markdown"
            )
            return
    await msg.answer(
        "📝 **Как узнать ID:**\n\n"
        "1️⃣ `/id @username`\n"
        "2️⃣ Ответь на сообщение `/id`\n"
        "3️⃣ Используй @userinfobot",
        parse_mode="Markdown"
    )

# ============================================================
# === КОМАНДА /myrole ===
# ============================================================
@dp.message(Command("myrole"))
async def my_role(msg: types.Message):
    level = await get_user_level(msg.from_user.id)
    role = await get_user_role(msg.from_user.id)
    karma = await get_karma(msg.from_user.id)
    stars = await get_user_stars(msg.from_user.id)
    
    ops = []
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT channel_id, channel_name FROM channel_operators WHERE operator_id = ?", (msg.from_user.id,))
        ops = await cursor.fetchall()
    
    owner = []
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT channel_id FROM channel_owners WHERE owner_id = ?", (msg.from_user.id,))
        owner = await cursor.fetchall()
    
    text = f"👤 **Твоя информация**\n\n"
    text += f"📊 Уровень: {level}\n"
    text += f"👑 Роль: {role}\n"
    text += f"⭐ Карма: {karma}\n"
    text += f"⭐ Звёзды: {stars}\n"
    
    if ops:
        text += "\n📢 **Ты оператор каналов:**\n"
        for ch_id, ch_name in ops:
            text += f"• {ch_name or ch_id} (`{ch_id}`)\n"
    
    if owner:
        text += "\n👑 **Ты глава каналов:**\n"
        for ch_id in owner:
            text += f"• `{ch_id}`\n"
    
    if level == 0:
        text += f"\n💡 Ты участник. Доступны команды:\n"
        text += f"• `/daily` — бонус\n"
        text += f"• `/shop` — магазин\n"
        text += f"• `/stars` — звёзды\n"
        text += f"• `/myrole` — эта команда\n"
    else:
        text += f"\n🔧 Доступные команды:\n"
        if level >= 1:
            text += f"• `/варн @user причина`\n"
            text += f"• `/инфо @user`\n"
        if level >= 2:
            text += f"• `/мут @user 24ч причина`\n"
            text += f"• `/размут @user`\n"
        if level >= 3:
            text += f"• `/бан @user причина`\n"
            text += f"• `/очистить @user`\n"
            text += f"• `/giveadmin @user уровень`\n"
            text += f"• `/addresponse`\n"
            text += f"• `/listresponses`\n"
            text += f"• `/removeresponse`\n"
        if level >= 4:
            text += f"• `/setupoperator`\n"
            text += f"• `/setowner`\n"
            text += f"• `/givemoney 1000`\n"
    
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))

# ============================================================
# === КОМАНДА /giveadmin ===
# ============================================================
@dp.message(Command("giveadmin"))
async def give_admin(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    if level < 3:
        await msg.answer("⛔ Только администраторы (уровень 3+) могут выдавать админку!")
        return
    
    args = msg.text.split()
    if len(args) < 3:
        await msg.answer(
            "📝 **Использование:**\n"
            "`/giveadmin @user уровень`\n\n"
            "📊 **Уровни:**\n"
            "0 — Участник\n"
            "1 — Наблюдатель 🟢\n"
            "2 — Модератор 🟠\n"
            "3 — Администратор 🔴\n"
            "4 — Главный администратор ⭐",
            parse_mode="Markdown"
        )
        return
    
    target = args[1]
    try:
        new_level = int(args[2])
    except:
        await msg.answer("❌ Введи корректный уровень (0-4)!")
        return
    
    if new_level < 0 or new_level > 4:
        await msg.answer("❌ Уровень должен быть от 0 до 4!")
        return
    
    target_id = await resolve_target(msg, target)
    if not target_id:
        await msg.answer(USER_NOT_FOUND_HINT.format(target=target))
        return
    
    target_level = await get_user_level(target_id)
    if target_level >= level:
        await msg.answer(f"❌ Нельзя выдать уровень выше своего ({level})!")
        return
    
    await set_user_level(target_id, new_level)
    await log_admin_action(user_id, f"👑 Выдана админка ({new_level})", target_id, f"Новый уровень: {new_level}")
    
    target_name = await get_username_by_id(target_id)
    level_name = ADMIN_LEVELS.get(new_level, {}).get("name", "Участник")
    level_emoji = ADMIN_LEVELS.get(new_level, {}).get("emoji", "👤")
    
    await msg.answer(
        f"✅ **Админка выдана!**\n\n"
        f"👤 Пользователь: {target_name}\n"
        f"📊 Уровень: {new_level} {level_emoji}\n"
        f"👑 Роль: {level_name}\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )
    
    try:
        await bot.send_message(
            target_id,
            f"👑 **Вам выдана админка!**\n\n"
            f"📊 Уровень: {new_level} {level_emoji}\n"
            f"👑 Роль: {level_name}\n"
            f"👮 Выдал: {await get_username_by_id(user_id)}"
        )
    except:
        pass

# ============================================================
# === КОМАНДА /setupoperator ===
# ============================================================
@dp.message(Command("setupoperator"))
async def setup_operator_cmd(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)

    if msg.chat.type not in ["channel", "supergroup"]:
        m = await msg.answer("❌ Эта команда работает только в каналах и группах!")
        asyncio.create_task(delete_after(m, 10))
        return

    if level < 4:
        m = await msg.answer("⛔ Нужен уровень 4+!")
        asyncio.create_task(delete_after(m, 10))
        return

    await state.update_data(channel_id=msg.chat.id)
    await state.set_state(AdminStates.setup_operator)
    m = await msg.answer("📝 Введи @username или ID пользователя для назначения оператором:")
    asyncio.create_task(delete_after(m, 30))

# ============================================================
# === КОМАНДА /setowner ===
# ============================================================
@dp.message(Command("setowner"))
async def set_owner_cmd(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)

    if msg.chat.type not in ["channel", "supergroup"]:
        m = await msg.answer("❌ Эта команда работает только в каналах и группах!")
        asyncio.create_task(delete_after(m, 10))
        return

    if level < 4:
        m = await msg.answer("⛔ Нужен уровень 4+!")
        asyncio.create_task(delete_after(m, 10))
        return

    await state.update_data(channel_id=msg.chat.id)
    await state.set_state(AdminStates.setup_owner)
    m = await msg.answer("📝 Введи @username или ID пользователя для назначения главой канала:")
    asyncio.create_task(delete_after(m, 30))

# ============================================================
# === КОМАНДА /givemoney ===
# ============================================================
@dp.message(Command("givemoney"))
async def give_money(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    
    if level < 4 and user_id not in ADMIN_IDS:
        await msg.answer("⛔ Только главный администратор может выдавать монеты!")
        return
    
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("📝 Использование: `/givemoney 1000`", parse_mode="Markdown")
        return
    
    try:
        amount = int(args[1])
    except:
        await msg.answer("❌ Введи число монет!")
        return
    
    if amount <= 0 or amount > 10000:
        await msg.answer("❌ Введи число от 1 до 10000!")
        return
    
    chat_id = msg.chat.id
    
    if msg.chat.type not in ["group", "supergroup"]:
        await msg.answer("❌ Только в группах!")
        return
    
    try:
        # Telegram Bot API не отдаёт список всех участников чата, поэтому берём тех,
        # кого бот уже видел в этом чате, плюс администраторов.
        recipients = set(await get_known_chat_members(chat_id))
        try:
            for admin in await bot.get_chat_administrators(chat_id):
                if not admin.user.is_bot:
                    recipients.add(admin.user.id)
        except Exception as e:
            print(f"Ошибка получения админов: {e}")
        
        for member_id in recipients:
            await add_karma(member_id, amount)
        count = len(recipients)
        
        if count == 0:
            await msg.answer("❌ Не удалось выдать монеты! Бот ещё никого не видел в этом чате.")
            return
        
        await msg.answer(
            f"💰 **Монеты выданы!**\n\n"
            f"📌 Каждому выдано: {amount} монет\n"
            f"👥 Получили: {count} участников\n"
            f"💳 Всего выдано: {amount * count} монет\n\n"
            f"ℹ️ Telegram не даёт ботам список всех участников: монеты получают те, кого бот уже видел в чате.\n\n"
            f"👮 Выдал: {await get_username_by_id(user_id)}"
        )
        
        await send_log(
            chat_id,
            "💰 Выдача монет",
            f"👮 Админ: {await get_username_by_id(user_id)}\n"
            f"📌 Сумма: {amount} монет каждому\n"
            f"👥 Получили: {count} участников"
        )
        
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {str(e)[:200]}\n\n💡 Убедитесь, что бот имеет права администратора в группе!")
        print(f"Ошибка /givemoney: {e}")

# ============================================================
# === КОМАНДА START ===
# ============================================================
@dp.message(Command("start"))
async def start(msg: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Ознакомиться с политикой бота", callback_data="policy")]
    ])
    
    m = await msg.answer(
        "☀️ *Бот-модератор*\n\n"
        "✅ Мат разрешён\n"
        "🚫 Угрозы и насилие блокируются\n"
        "⚠️ 10 варнов = мут 5-30 минут\n"
        "🛍️ /shop — магазин\n\n"
        "📌 *Команды:*\n"
        "👑 /admin — панель\n"
        "👤 /myrole — роль\n"
        "🎁 /daily — бонус\n"
        "/мут @user 24ч причина\n"
        "/размут @user\n"
        "/варн @user причина\n"
        "/бан @user причина\n"
        "/кик @user причина\n"
        "/инфо @user\n"
        "/id @user — узнать ID\n"
        "/shop — магазин\n"
        "/addresponse — добавить авто-ответ (ЛС)\n"
        "/listresponses — список авто-ответов (ЛС)\n"
        "/removeresponse — удалить авто-ответ (ЛС)\n"
        "/buy_real_stars — купить за звёзды",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_after(m, 60))

# ============================================================
# === ПОЛИТИКА ===
# ============================================================
@dp.callback_query(F.data == "policy")
async def policy_callback(call: types.CallbackQuery):
    await call.answer()
    await call.message.answer(
        "📜 **Политика бота-модератора**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "**1. Общие положения**\n"
        "Бот создан для поддержания порядка в чатах и каналах.\n\n"
        
        "**2. Запрещённый контент**\n"
        "🚫 Угрозы и насилие\n"
        "🚫 Терроризм и экстремизм\n"
        "🚫 Наркотики и пропаганда наркотиков\n"
        "🚫 Мат с фото запрещён\n\n"
        
        "**3. Система наказаний**\n"
        "⚠️ 1 варн — предупреждение\n"
        "⚠️ 3 варна — мут 5-30 минут\n"
        "🔒 Мут — ограничение на отправку сообщений\n"
        "🚫 Бан — 30 дней\n\n"
        
        "**4. Магазин**\n"
        "🪙 За монеты:\n"
        "• Снять варн — 500 монет\n"
        "• Снять мут — 1000 монет\n"
        "• Разбан — 2500 монет\n"
        "• Одноразовая ссылка — 150 монет\n\n"
        "⭐ За звёзды:\n"
        "• Снять варн — 10 ⭐\n"
        "• Снять мут — 20 ⭐\n"
        "• Разбан — 50 ⭐\n\n"
        "📦 Подписка:\n"
        "• Безлимитные ссылки — 2000 монет/мес или 20 ⭐\n\n"
        
        "**5. Получение монет**\n"
        f"🎁 Ежедневный бонус — `/daily` (от {DAILY_BONUS_MIN} до {DAILY_BONUS_MAX} монет)\n"
        "💰 Выдача админом — `/givemoney 1000`\n\n"
        
        "**6. Авто-ответы**\n"
        "Настраиваются в ЛС командами:\n"
        "📝 /addresponse\n"
        "📋 /listresponses\n"
        "🗑️ /removeresponse\n\n"
        
        "**7. Администрация**\n"
        "👑 Главный администратор имеет полный доступ\n"
        "🔴 Администратор — может выдавать админку\n"
        "🟠 Модератор — может мутить и варнить\n"
        "🟢 Наблюдатель — может выдавать варны\n\n"
        
        "**8. Контакты**\n"
        "По всем вопросам обращайтесь к главному администратору.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌴 *Соблюдайте правила и будьте вежливы!*",
        parse_mode="Markdown"
    )

# ============================================================
# === КОМАНДА /shop ===
# ============================================================
@dp.message(Command("shop"))
async def shop_cmd(msg: types.Message, user_id: int = None):
    user_id = user_id or msg.from_user.id
    user_username = await get_username_by_id(user_id)
    karma = await get_karma(user_id)
    has_sub = await has_subscription(user_id)
    
    chat_buttons = []
    for chat_id in SHOP_CHANNEL_IDS:
        try:
            chat = await bot.get_chat(chat_id)
            chat_name = chat.title or str(chat_id)
        except Exception:
            chat_name = str(chat_id)
        chat_buttons.append([InlineKeyboardButton(
            text=f"📢 {chat_name}",
            callback_data=f"shop_select_chat_{chat_id}"
        )])
    
    chat_buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="shop_close")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=chat_buttons)
    
    sub_status = "✅ Активна" if has_sub else "❌ Неактивна"
    
    await msg.answer(
        f"🛍️ **Магазин**\n\n"
        f"👤 Пользователь: {user_username}\n"
        f"💰 Баланс: {karma} монет\n"
        f"📦 Подписка: {sub_status}\n\n"
        f"📌 **Выбери чат, в котором хочешь совершить покупку:**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("shop_select_chat_"))
async def shop_select_chat(call: types.CallbackQuery):
    user_id = call.from_user.id
    chat_id = int(call.data.replace("shop_select_chat_", ""))
    
    user_selected_chat[user_id] = chat_id
    
    try:
        chat = await bot.get_chat(chat_id)
        chat_name = chat.title or str(chat_id)
    except:
        chat_name = str(chat_id)
    
    warns = await get_warnings(user_id, chat_id)
    is_muted_user = await is_muted(user_id)
    karma = await get_karma(user_id)
    has_sub = await has_subscription(user_id)
    
    has_unlimited = has_sub
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="━━━ 🪙 За монеты ━━━", callback_data="ignore")],
        [InlineKeyboardButton(text=f"🗑️ Снять варн — {COIN_PRICES['clear_warn']} монет", callback_data="shop_buy_clear_warn")],
        [InlineKeyboardButton(text=f"🔓 Снять мут — {COIN_PRICES['clear_mute']} монет", callback_data="shop_buy_clear_mute")],
        [InlineKeyboardButton(text=f"🔄 Разбан — {COIN_PRICES['unban']} монет", callback_data="shop_buy_unban")],
        [InlineKeyboardButton(text=f"🔗 Одноразовая ссылка — {COIN_PRICES['invite']} монет", callback_data="shop_buy_invite")],
        [InlineKeyboardButton(text="━━━ ⭐ За звёзды ━━━", callback_data="ignore")],
        [InlineKeyboardButton(text=f"🗑️ Снять варн — {STARS_PRICES['clear_warn']} ⭐", callback_data="shop_buy_stars_clear_warn")],
        [InlineKeyboardButton(text=f"🔓 Снять мут — {STARS_PRICES['clear_mute']} ⭐", callback_data="shop_buy_stars_clear_mute")],
        [InlineKeyboardButton(text=f"🔄 Разбан — {STARS_PRICES['unban']} ⭐", callback_data="shop_buy_stars_unban")],
        [InlineKeyboardButton(text="━━━ 📦 Подписка ━━━", callback_data="ignore")],
        [InlineKeyboardButton(
            text=f"{'✅' if has_unlimited else '❌'} Безлимитные ссылки — {SUBSCRIPTION_PRICE} монет/мес",
            callback_data="shop_buy_subscription"
        )],
        [InlineKeyboardButton(text=f"⭐ Безлимитные ссылки — {SUBSCRIPTION_STARS} ⭐/мес", callback_data="shop_buy_stars_subscription")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="shop_back")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="shop_close")]
    ])
    
    status_text = ""
    if warns > 0:
        status_text += f"\n⚠️ У тебя {warns} варнов"
    if is_muted_user:
        status_text += f"\n🔴 Ты в муте!"
    if has_unlimited:
        status_text += f"\n📦 Безлимитные ссылки активны!"
    if warns == 0 and not is_muted_user:
        status_text += f"\n✅ Нарушений нет"
    
    await call.message.edit_text(
        f"🛍️ **Магазин**\n\n"
        f"📢 Чат: {chat_name}\n"
        f"👤 Пользователь: {await get_username_by_id(user_id)}\n"
        f"💰 Баланс: {karma} монет\n"
        f"📦 Подписка: {'✅ Активна' if has_unlimited else '❌ Неактивна'}{status_text}\n\n"
        f"📌 **Выбери действие:**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await call.answer()

@dp.callback_query(F.data == "shop_back")
async def shop_back(call: types.CallbackQuery):
    await shop_cmd(call.message)
    await call.answer()

@dp.callback_query(F.data == "ignore")
async def ignore_callback(call: types.CallbackQuery):
    await call.answer()

# ============================================================
# === ПОКУПКИ ===
# ============================================================
@dp.callback_query(F.data.startswith("shop_buy_"))
async def shop_buy(call: types.CallbackQuery):
    user_id = call.from_user.id
    action = call.data.replace("shop_buy_", "")
    chat_id = user_selected_chat.get(user_id)
    
    if not chat_id:
        await call.answer("❌ Сначала выбери чат!", show_alert=True)
        return
    
    try:
        chat = await bot.get_chat(chat_id)
        chat_name = chat.title or str(chat_id)
    except:
        chat_name = str(chat_id)
    
    karma = await get_karma(user_id)
    stars = await get_user_stars(user_id)
    
    # === ПОКУПКА ЗА МОНЕТЫ ===
    if action == "clear_warn":
        if karma < COIN_PRICES["clear_warn"]:
            await call.answer(f"❌ Нужно {COIN_PRICES['clear_warn']} монет!", show_alert=True)
            return
        warns = await get_warnings(user_id, chat_id)
        if warns == 0:
            await call.answer("❌ У тебя нет варнов!", show_alert=True)
            return
        await clear_warnings(user_id, chat_id)
        await add_karma(user_id, -COIN_PRICES["clear_warn"])
        await call.answer("✅ Варны сняты!", show_alert=True)
        await call.message.edit_text(
            f"✅ **Варны сняты!**\n\n"
            f"📢 Чат: {chat_name}\n"
            f"💰 Остаток: {await get_karma(user_id)} монет",
            parse_mode="Markdown"
        )
        return
    
    if action == "clear_mute":
        if karma < COIN_PRICES["clear_mute"]:
            await call.answer(f"❌ Нужно {COIN_PRICES['clear_mute']} монет!", show_alert=True)
            return
        if not await is_muted(user_id):
            await call.answer("❌ Ты не в муте!", show_alert=True)
            return
        await remove_mute(user_id)
        await add_karma(user_id, -COIN_PRICES["clear_mute"])
        await call.answer("✅ Мут снят!", show_alert=True)
        await call.message.edit_text(
            f"✅ **Мут снят!**\n\n"
            f"📢 Чат: {chat_name}\n"
            f"💰 Остаток: {await get_karma(user_id)} монет",
            parse_mode="Markdown"
        )
        return
    
    if action == "unban":
        if karma < COIN_PRICES["unban"]:
            await call.answer(f"❌ Нужно {COIN_PRICES['unban']} монет!", show_alert=True)
            return
        if await is_muted(user_id):
            await remove_mute(user_id)
        await clear_warnings(user_id, chat_id)
        await add_karma(user_id, -COIN_PRICES["unban"])
        await call.answer("✅ Разбан выполнен!", show_alert=True)
        await call.message.edit_text(
            f"✅ **Разбан выполнен!**\n\n"
            f"📢 Чат: {chat_name}\n"
            f"💰 Остаток: {await get_karma(user_id)} монет",
            parse_mode="Markdown"
        )
        return
    
    if action == "invite":
        if karma < COIN_PRICES["invite"]:
            await call.answer(f"❌ Нужно {COIN_PRICES['invite']} монет!", show_alert=True)
            return
        try:
            invite_link = await bot.create_chat_invite_link(chat_id, member_limit=1)
            await add_karma(user_id, -COIN_PRICES["invite"])
            await call.answer("✅ Ссылка создана!", show_alert=True)
            await call.message.edit_text(
                f"✅ **Одноразовая ссылка!**\n\n"
                f"📢 Чат: {chat_name}\n"
                f"🔗 {invite_link.invite_link}\n"
                f"💰 Остаток: {await get_karma(user_id)} монет",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            await call.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
        return
    
    if action == "subscription":
        if karma < SUBSCRIPTION_PRICE:
            await call.answer(f"❌ Нужно {SUBSCRIPTION_PRICE} монет!", show_alert=True)
            return
        await add_subscription(user_id, 30)
        await add_karma(user_id, -SUBSCRIPTION_PRICE)
        await call.answer("✅ Подписка оформлена на 30 дней!", show_alert=True)
        await call.message.edit_text(
            f"✅ **Подписка оформлена!**\n\n"
            f"📢 Чат: {chat_name}\n"
            f"📦 Безлимитные ссылки на 30 дней!\n"
            f"💰 Остаток: {await get_karma(user_id)} монет",
            parse_mode="Markdown"
        )
        return
    
    # === ПОКУПКА ЗА ЗВЁЗДЫ ===
    if action.startswith("stars_"):
        action_type = action.replace("stars_", "")
        
        if action_type == "clear_warn":
            stars_needed = STARS_PRICES["clear_warn"]
            if stars < stars_needed:
                await call.answer(f"❌ Нужно {stars_needed} ⭐!", show_alert=True)
                return
            warns = await get_warnings(user_id, chat_id)
            if warns == 0:
                await call.answer("❌ У тебя нет варнов!", show_alert=True)
                return
            await clear_warnings(user_id, chat_id)
            await remove_stars(user_id, stars_needed)
            await call.answer("✅ Варны сняты!", show_alert=True)
            await call.message.edit_text(
                f"✅ **Варны сняты за звёзды!**\n\n"
                f"📢 Чат: {chat_name}\n"
                f"⭐ Остаток: {await get_user_stars(user_id)} ⭐",
                parse_mode="Markdown"
            )
            return
        
        if action_type == "clear_mute":
            stars_needed = STARS_PRICES["clear_mute"]
            if stars < stars_needed:
                await call.answer(f"❌ Нужно {stars_needed} ⭐!", show_alert=True)
                return
            if not await is_muted(user_id):
                await call.answer("❌ Ты не в муте!", show_alert=True)
                return
            await remove_mute(user_id)
            await remove_stars(user_id, stars_needed)
            await call.answer("✅ Мут снят!", show_alert=True)
            await call.message.edit_text(
                f"✅ **Мут снят за звёзды!**\n\n"
                f"📢 Чат: {chat_name}\n"
                f"⭐ Остаток: {await get_user_stars(user_id)} ⭐",
                parse_mode="Markdown"
            )
            return
        
        if action_type == "unban":
            stars_needed = STARS_PRICES["unban"]
            if stars < stars_needed:
                await call.answer(f"❌ Нужно {stars_needed} ⭐!", show_alert=True)
                return
            if await is_muted(user_id):
                await remove_mute(user_id)
            await clear_warnings(user_id, chat_id)
            await remove_stars(user_id, stars_needed)
            await call.answer("✅ Разбан выполнен!", show_alert=True)
            await call.message.edit_text(
                f"✅ **Разбан за звёзды!**\n\n"
                f"📢 Чат: {chat_name}\n"
                f"⭐ Остаток: {await get_user_stars(user_id)} ⭐",
                parse_mode="Markdown"
            )
            return
        
        if action_type == "subscription":
            stars_needed = SUBSCRIPTION_STARS
            if stars < stars_needed:
                await call.answer(f"❌ Нужно {stars_needed} ⭐!", show_alert=True)
                return
            await add_subscription(user_id, 30)
            await remove_stars(user_id, stars_needed)
            await call.answer("✅ Подписка оформлена на 30 дней!", show_alert=True)
            await call.message.edit_text(
                f"✅ **Подписка за звёзды!**\n\n"
                f"📢 Чат: {chat_name}\n"
                f"📦 Безлимитные ссылки на 30 дней!\n"
                f"⭐ Остаток: {await get_user_stars(user_id)} ⭐",
                parse_mode="Markdown"
            )
            return
    
    await call.answer("❌ Неизвестное действие")

@dp.callback_query(F.data == "shop_close")
async def shop_close(call: types.CallbackQuery):
    await call.message.delete()
    await call.answer("🛍️ Магазин закрыт")

# ============================================================
# === НАСТОЯЩИЕ TELEGRAM STARS ===
# ============================================================
@dp.message(Command("buy_real_stars"))
async def buy_real_stars_cmd(msg: types.Message):
    user_id = msg.from_user.id
    
    if user_id not in user_selected_chat:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️ Выбрать чат в /shop", callback_data="go_shop")]
        ])
        await msg.answer(
            "❌ Сначала выбери чат в `/shop`!\n"
            "Нажми на кнопку ниже, чтобы перейти в магазин.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return
    
    chat_id = user_selected_chat.get(user_id)
    
    try:
        chat = await bot.get_chat(chat_id)
        chat_name = chat.title or str(chat_id)
    except:
        chat_name = str(chat_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Снять варн — {STARS_PRICES['clear_warn']} звёзд", callback_data="real_stars_clear_warn")],
        [InlineKeyboardButton(text=f"⭐ Снять мут — {STARS_PRICES['clear_mute']} звёзд", callback_data="real_stars_clear_mute")],
        [InlineKeyboardButton(text=f"⭐ Разбан — {STARS_PRICES['unban']} звёзд", callback_data="real_stars_unban")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="real_stars_close")]
    ])
    
    await msg.answer(
        f"⭐ **Купить за настоящие звёзды**\n\n"
        f"📢 Чат: {chat_name}\n"
        f"💰 Оплата происходит настоящими Telegram Stars.\n"
        f"После оплаты действие будет выполнено автоматически.\n\n"
        f"📌 **Выбери действие:**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "go_shop")
async def go_shop_callback(call: types.CallbackQuery):
    await shop_cmd(call.message, user_id=call.from_user.id)
    await call.answer()

@dp.callback_query(F.data.startswith("real_stars_"))
async def real_stars_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    action = call.data.replace("real_stars_", "")
    
    if action == "close":
        await call.message.delete()
        await call.answer("Закрыто")
        return
    
    chat_id = user_selected_chat.get(user_id)
    if not chat_id:
        await call.answer("❌ Сначала выбери чат в /shop!", show_alert=True)
        return
    
    # Проверяем наличие нарушений
    if action == "clear_warn":
        warns = await get_warnings(user_id, chat_id)
        if warns == 0:
            await call.answer("❌ У тебя нет варнов!", show_alert=True)
            return
    elif action == "clear_mute":
        if not await is_muted(user_id):
            await call.answer("❌ Ты не в муте!", show_alert=True)
            return
    
    labels = {
        "clear_warn": "Снять варн",
        "clear_mute": "Снять мут",
        "unban": "Разбан",
    }
    
    if action not in labels:
        await call.answer("❌ Неизвестное действие!", show_alert=True)
        return
    price_info = {"amount": STARS_PRICES[action], "label": labels[action]}

    try:
        await bot.send_invoice(
            chat_id=user_id,
            title=f"⭐ {price_info['label']}",
            description=f"Оплата {price_info['amount']} звёзд за {price_info['label']}",
            payload=f"stars_{action}_{chat_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=price_info['label'], amount=price_info['amount'])],
            start_parameter="stars_payment",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False,
        )
        await call.message.delete()
        await call.answer("💳 Счёт создан! Подтвердите оплату в ЛС бота.")
    except Exception as e:
        await call.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)

# ============================================================
# === ОБРАБОТКА УСПЕШНЫХ ПЛАТЕЖЕЙ ===
# ============================================================
@dp.pre_checkout_query()
async def pre_checkout_query_handler(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(msg: Message):
    user_id = msg.from_user.id
    payload = msg.successful_payment.invoice_payload
    # Для валюты XTR сумма приходит в звёздах, без множителя 100.
    total_amount = msg.successful_payment.total_amount
    
    parts = payload.split("_")
    if len(parts) >= 3 and parts[0] == "stars":
        action = parts[1]
        chat_id = int(parts[2])
        
        try:
            if action == "clear_warn":
                warns = await get_warnings(user_id, chat_id)
                if warns > 0:
                    await clear_warnings(user_id, chat_id)
                    await msg.answer(
                        f"✅ **Варны сняты!**\n\n"
                        f"📢 Чат: {chat_id}\n"
                        f"⭐ Оплачено: {total_amount} звёзд\n"
                        f"🛍️ Спасибо за покупку!",
                        parse_mode="Markdown"
                    )
                else:
                    await msg.answer("❌ У тебя нет варнов!")
                return
            
            if action == "clear_mute":
                if await is_muted(user_id):
                    await remove_mute(user_id)
                    await msg.answer(
                        f"✅ **Мут снят!**\n\n"
                        f"📢 Чат: {chat_id}\n"
                        f"⭐ Оплачено: {total_amount} звёзд\n"
                        f"🛍️ Спасибо за покупку!",
                        parse_mode="Markdown"
                    )
                else:
                    await msg.answer("❌ Ты не в муте!")
                return
            
            if action == "unban":
                if await is_muted(user_id):
                    await remove_mute(user_id)
                await clear_warnings(user_id, chat_id)
                await msg.answer(
                    f"✅ **Разбан выполнен!**\n\n"
                    f"📢 Чат: {chat_id}\n"
                    f"⭐ Оплачено: {total_amount} звёзд\n"
                    f"🛍️ Спасибо за покупку!",
                    parse_mode="Markdown"
                )
                return
                
        except Exception as e:
            await msg.answer(f"❌ Ошибка: {str(e)[:100]}")

# ============================================================
# === АВТО-ОТВЕТЫ ===
# ============================================================
@dp.message(Command("addresponse"))
async def add_response_start(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 3:
        await msg.answer("⛔ Нет прав!")
        return
    
    if msg.chat.type != "private":
        await msg.answer("❌ Эта команда работает только в ЛС!")
        return

    await state.set_state(AutoResponseStates.add_response_chat)
    await msg.answer(
        "📝 **Настройка авто-ответа**\n\n"
        "Введи ID канала, для которого хочешь настроить авто-ответ:\n"
        "Пример: `-1003018474298`"
    )

@dp.message(Command("listresponses"))
async def list_responses(msg: types.Message):
    user_id = msg.from_user.id
    if msg.chat.type != "private":
        await msg.answer("❌ Только в ЛС!")
        return
    
    level = await get_user_level(user_id)
    if level < 3:
        await msg.answer("⛔ Нет прав!")
        return
    
    chats = await get_all_chats_with_auto_responses()
    if not chats:
        await msg.answer("📋 Нет настроенных авто-ответов ни для одного канала.")
        return
    
    text = "📋 **Каналы с авто-ответами:**\n\n"
    for chat_id in chats:
        try:
            chat = await bot.get_chat(chat_id)
            chat_name = chat.title or str(chat_id)
        except:
            chat_name = str(chat_id)
        responses = await get_all_auto_responses(chat_id)
        text += f"📢 {chat_name} (`{chat_id}`) — {len(responses)} правил\n"
    
    await msg.answer(text, parse_mode="Markdown")

@dp.message(Command("removeresponse"))
async def remove_response_start(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id
    if msg.chat.type != "private":
        await msg.answer("❌ Только в ЛС!")
        return
    
    level = await get_user_level(user_id)
    if level < 3:
        await msg.answer("⛔ Нет прав!")
        return

    await state.set_state(AutoResponseStates.remove_response_chat)
    await msg.answer(
        "📝 **Удаление авто-ответа**\n\n"
        "Введи ID канала, из которого хочешь удалить авто-ответ:\n"
        "Пример: `-1003018474298`"
    )

# ============================================================
# === ОБРАБОТЧИКИ АВТО-ОТВЕТОВ ===
# ============================================================
@dp.message(StateFilter(AutoResponseStates.add_response_chat), F.chat.type == "private")
async def add_response_chat_handler(msg: types.Message, state: FSMContext):
    try:
        chat_id = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ Введи корректный ID канала!")
        return

    try:
        await bot.get_chat(chat_id)
    except Exception:
        await msg.answer("❌ Бот не найден в этом канале!")
        return

    await state.update_data(chat_id=chat_id)
    await state.set_state(AutoResponseStates.add_response_keyword)
    await msg.answer(
        f"✅ Канал `{chat_id}` выбран!\n\n"
        f"📝 Введи **ключевое слово**, на которое будет отвечать бот:\n"
        f"Пример: `привет`, `правила`, `как дела`"
    )

@dp.message(StateFilter(AutoResponseStates.add_response_keyword), F.chat.type == "private")
async def add_response_keyword_handler(msg: types.Message, state: FSMContext):
    keyword = msg.text.strip().lower()
    if not keyword:
        await msg.answer("❌ Введи ключевое слово!")
        return

    await state.update_data(keyword=keyword)
    await state.set_state(AutoResponseStates.add_response_text)
    await msg.answer(
        f"📝 Ключевое слово: `{keyword}`\n\n"
        f"Теперь введи **текст ответа**, который будет отправлять бот:\n"
        f"Можно использовать Markdown"
    )

@dp.message(StateFilter(AutoResponseStates.add_response_text), F.chat.type == "private")
async def add_response_text_handler(msg: types.Message, state: FSMContext):
    response = msg.text.strip()
    if not response:
        await msg.answer("❌ Введи текст ответа!")
        return

    data = await state.get_data()
    chat_id = data.get("chat_id")
    keyword = data.get("keyword")
    await add_auto_response(chat_id, keyword, response, msg.from_user.id)

    await msg.answer(
        f"✅ **Авто-ответ добавлен!**\n\n"
        f"📢 Канал: `{chat_id}`\n"
        f"🔑 Ключевое слово: `{keyword}`\n"
        f"📝 Ответ: {response[:100]}...\n\n"
        f"Для просмотра всех ответов используй `/listresponses`"
    )
    await state.clear()

@dp.message(StateFilter(AutoResponseStates.remove_response_chat), F.chat.type == "private")
async def remove_response_chat_handler(msg: types.Message, state: FSMContext):
    try:
        chat_id = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ Введи корректный ID канала!")
        return

    responses = await get_all_auto_responses(chat_id)
    if not responses:
        await msg.answer(f"📋 В канале `{chat_id}` нет авто-ответов!")
        return

    text = f"📋 **Авто-ответы в канале `{chat_id}`:**\n\n"
    for keyword, response, date in responses:
        text += f"• `{keyword}` → {response[:50]}...\n"
    text += f"\n📝 Введи **ключевое слово**, которое хочешь удалить:"

    await state.update_data(chat_id=chat_id)
    await state.set_state(AutoResponseStates.remove_response_keyword)
    await msg.answer(text, parse_mode="Markdown")

@dp.message(StateFilter(AutoResponseStates.remove_response_keyword), F.chat.type == "private")
async def remove_response_keyword_handler(msg: types.Message, state: FSMContext):
    keyword = msg.text.strip().lower()
    data = await state.get_data()
    chat_id = data.get("chat_id")
    await remove_auto_response(chat_id, keyword)
    await msg.answer(f"✅ Авто-ответ на `{keyword}` удалён!")
    await state.clear()

async def send_auto_response(msg: types.Message):
    responses = await get_all_auto_responses(msg.chat.id)
    if not responses:
        return
    
    text = (msg.text or msg.caption or "").lower()
    for keyword, response, date in responses:
        if keyword in text:
            await msg.answer(response)
            break

# ============================================================
# === ОСТАЛЬНЫЕ КОМАНДЫ ===
# ============================================================
@dp.message(Command("daily"))
async def daily_bonus(msg: types.Message):
    user_id = msg.from_user.id
    can_claim, amount, streak, remaining = await get_daily_bonus(user_id)
    if can_claim:
        await claim_daily(user_id)
        await add_karma(user_id, amount)
        m = await msg.answer(
            f"🎁 **Ежедневный бонус!**\n\n"
            f"💰 Получено: {amount} монет\n"
            f"🔥 Стрик: {streak} дней\n"
            f"🎲 Каждый день выпадает от {DAILY_BONUS_MIN} до {DAILY_BONUS_MAX} монет\n\n"
            f"Приходи завтра! ☀️",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after(m, 30))
    else:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        m = await msg.answer(
            f"⏳ **Бонус уже получен!**\n\n"
            f"Следующий через: {hours}ч {minutes}м\n"
            f"🔥 Стрик: {streak} дней",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after(m, 20))

@dp.message(Command("admins"))
async def list_admins(msg: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
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
    if level < 3:
        m = await msg.answer("⛔ Нужен уровень 3+!")
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
    level = await get_user_level(msg.from_user.id)
    if level < 1:
        await msg.answer("⛔ Нет прав!")
        return
    keyboard = await get_admin_keyboard(msg.from_user.id)
    m = await msg.answer("🛡️ *Админ-панель*", reply_markup=keyboard, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))

# ============================================================
# === ТЕКСТОВЫЕ КОМАНДЫ ===
# ============================================================
@dp.message(Command("мут"))
@dp.message(Command("mute"))
async def cmd_mute(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 2:
        await msg.answer("⛔ Нужен уровень 2+!")
        return
    args = msg.text.split(maxsplit=3)
    if len(args) < 2:
        await msg.answer("📝 /мут @user 24ч причина")
        return
    target = args[1]
    duration_str = args[2] if len(args) > 2 else "5м"
    reason = args[3] if len(args) > 3 else "Нарушение"
    target_id = await resolve_target(msg, target)
    if not target_id:
        await msg.answer(USER_NOT_FOUND_HINT.format(target=target))
        return
    duration = parse_duration(duration_str)
    if not duration:
        await msg.answer("❌ Неверный формат!\nДоступно: 5м, 1ч, 24ч, 7д")
        return
    target_level = await get_user_level(target_id)
    if target_level >= level:
        await msg.answer(f"❌ Нельзя мутить пользователя с уровнем {target_level}!")
        return
    await add_mute(target_id, duration)
    target_name = await get_username_by_id(target_id)
    await log_admin_action(user_id, "🔒 Мут", target_id, f"{duration_str} - {reason}")
    await send_log(msg.chat.id, "🔒 Мут", f"👤 Пользователь: {target_name} ({target_id})\n⏱️ Длительность: {duration_str}\n📝 Причина: {reason}")
    await msg.answer(
        f"🔒 **Мут выдан!**\n\n"
        f"👤 Пользователь: {target_name}\n"
        f"⏱️ Длительность: {duration_str}\n"
        f"📝 Причина: {reason}\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("размут"))
@dp.message(Command("unmute"))
async def cmd_unmute(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 2:
        await msg.answer("⛔ Нужен уровень 2+!")
        return
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("📝 /размут @user")
        return
    target = args[1]
    target_id = await resolve_target(msg, target)
    if not target_id:
        await msg.answer(USER_NOT_FOUND_HINT.format(target=target))
        return
    await remove_mute(target_id)
    target_name = await get_username_by_id(target_id)
    await log_admin_action(user_id, "🔓 Размут", target_id, "")
    await send_log(msg.chat.id, "🔓 Размут", f"👤 Пользователь: {target_name} ({target_id})")
    await msg.answer(
        f"🔓 **Размут снят!**\n\n"
        f"👤 Пользователь: {target_name}\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("варн"))
@dp.message(Command("warn"))
async def cmd_warn(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 1:
        await msg.answer("⛔ Нужен уровень 1+!")
        return
    args = msg.text.split(maxsplit=2)
    if len(args) < 2:
        await msg.answer("📝 /варн @user причина")
        return
    target = args[1]
    reason = args[2] if len(args) > 2 else "Нарушение"
    target_id = await resolve_target(msg, target)
    if not target_id:
        await msg.answer(USER_NOT_FOUND_HINT.format(target=target))
        return
    target_level = await get_user_level(target_id)
    if target_level >= level:
        await msg.answer(f"❌ Нельзя варнить пользователя с уровнем {target_level}!")
        return
    was_auto_muted, mute_duration = await add_warning(target_id, msg.chat.id, reason, user_id)
    target_name = await get_username_by_id(target_id)
    await send_log(msg.chat.id, "⚠️ Варн", f"👤 Пользователь: {target_name} ({target_id})\n📝 Причина: {reason}")
    warns = await get_warnings(target_id, msg.chat.id)
    settings = await get_channel_settings(msg.chat.id)
    if was_auto_muted:
        await msg.answer(
            f"⚠️ **Варн выдан!**\n\n"
            f"👤 Пользователь: {target_name}\n"
            f"📝 Причина: {reason}\n"
            f"🔥 Варнов: {warns}/{settings['warn_limit']}\n"
            f"🔒 **Автоматический мут на {mute_duration//60} минут!**"
        )
    else:
        await msg.answer(
            f"⚠️ **Варн выдан!**\n\n"
            f"👤 Пользователь: {target_name}\n"
            f"📝 Причина: {reason}\n"
            f"🔥 Варнов: {warns}/{settings['warn_limit']}"
        )

@dp.message(Command("бан"))
@dp.message(Command("ban"))
async def cmd_ban(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 3:
        await msg.answer("⛔ Нужен уровень 3+!")
        return
    args = msg.text.split(maxsplit=2)
    if len(args) < 2:
        await msg.answer("📝 /бан @user причина")
        return
    target = args[1]
    reason = args[2] if len(args) > 2 else "Бан"
    target_id = await resolve_target(msg, target)
    if not target_id:
        await msg.answer(USER_NOT_FOUND_HINT.format(target=target))
        return
    target_level = await get_user_level(target_id)
    if target_level >= level:
        await msg.answer(f"❌ Нельзя банить пользователя с уровнем {target_level}!")
        return
    await add_mute(target_id, 2592000)
    target_name = await get_username_by_id(target_id)
    await log_admin_action(user_id, "🚫 Бан", target_id, reason)
    await send_log(msg.chat.id, "🚫 Бан", f"👤 Пользователь: {target_name} ({target_id})\n📝 Причина: {reason}")
    await msg.answer(
        f"🚫 **Бан выдан!**\n\n"
        f"👤 Пользователь: {target_name}\n"
        f"📝 Причина: {reason}\n"
        f"⏱️ Срок: 30 дней\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("кик"))
@dp.message(Command("kick"))
async def cmd_kick(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 2:
        await msg.answer("⛔ Нужен уровень 2+!")
        return
    args = msg.text.split(maxsplit=2)
    if len(args) < 2:
        await msg.answer("📝 /кик @user причина")
        return
    target = args[1]
    reason = args[2] if len(args) > 2 else "Кик"
    target_id = await resolve_target(msg, target)
    if not target_id:
        await msg.answer(USER_NOT_FOUND_HINT.format(target=target))
        return
    target_level = await get_user_level(target_id)
    if target_level >= level:
        await msg.answer(f"❌ Нельзя кикать пользователя с уровнем {target_level}!")
        return
    await add_mute(target_id, 3600)
    target_name = await get_username_by_id(target_id)
    await log_admin_action(user_id, "👢 Кик", target_id, reason)
    await send_log(msg.chat.id, "👢 Кик", f"👤 Пользователь: {target_name} ({target_id})\n📝 Причина: {reason}")
    await msg.answer(
        f"👢 **Кик выдан!**\n\n"
        f"👤 Пользователь: {target_name}\n"
        f"📝 Причина: {reason}\n"
        f"⏱️ Срок: 1 час\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("очистить"))
@dp.message(Command("clear"))
async def cmd_clear(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 3:
        await msg.answer("⛔ Нужен уровень 3+!")
        return
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("📝 /очистить @user")
        return
    target = args[1]
    target_id = await resolve_target(msg, target)
    if not target_id:
        await msg.answer(USER_NOT_FOUND_HINT.format(target=target))
        return
    await clear_warnings(target_id, msg.chat.id)
    target_name = await get_username_by_id(target_id)
    await log_admin_action(user_id, "🗑️ Очищены варны", target_id, "")
    await send_log(msg.chat.id, "🗑️ Очищены варны", f"👤 Пользователь: {target_name} ({target_id})")
    await msg.answer(
        f"🗑️ **Варны очищены!**\n\n"
        f"👤 Пользователь: {target_name}\n"
        f"👮 Админ: {await get_username_by_id(user_id)}"
    )

@dp.message(Command("инфо"))
@dp.message(Command("info"))
async def cmd_info(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 1:
        await msg.answer("⛔ Нужен уровень 1+!")
        return
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("📝 /инфо @user")
        return
    target = args[1]
    target_id = await resolve_target(msg, target)
    if not target_id:
        await msg.answer(USER_NOT_FOUND_HINT.format(target=target))
        return
    stats = await get_user_stats(target_id, msg.chat.id)
    username = await get_username_by_id(target_id)
    
    logs = []
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT admin_name, action, target_name, details, date FROM admin_logs WHERE target_id = ? OR admin_id = ? ORDER BY date DESC LIMIT 5",
            (target_id, target_id)
        )
        logs = await cursor.fetchall()
    
    report = (
        f"📊 **Информация о пользователе**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Пользователь: {username}\n"
        f"🆔 ID: `{target_id}`\n\n"
        f"📌 **Общая информация:**\n"
        f"• 👑 Роль: {stats['role']}\n"
        f"• 📊 Уровень: {stats['level']}\n"
        f"• ⭐ Карма: {stats['karma']}\n\n"
        f"⚠️ **Нарушения:**\n"
        f"• 🚫 Всего нарушений: {stats['violations']}\n"
        f"• ⚠️ Варнов: {stats['warns']}\n"
        f"{'🔴 В муте' if stats['is_muted'] else '🟢 Не в муте'}\n\n"
    )
    
    if logs:
        report += f"📋 **Последние действия:**\n"
        for admin_name, action, target_name, details, date in logs:
            report += f"• {admin_name} {action}"
            if target_name:
                report += f" → {target_name}"
            if details:
                report += f" ({details[:30]}...)"
            report += f"\n  🕐 {date[:16]}\n"
    
    report += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    report += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    
    keyboard = None
    if await get_user_level(user_id) >= 3:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Полная статистика", callback_data=f"full_stats_{target_id}")]
        ])
    
    m = await msg.answer(report, parse_mode="Markdown", reply_markup=keyboard)
    asyncio.create_task(delete_after(m, 60))

@dp.message(Command("stats"))
async def show_stats(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 1:
        await msg.answer("⛔ Нужен уровень 1+!")
        return
    
    chat_id = msg.chat.id
    violations = await get_violations_stats(chat_id, 10)
    if not violations:
        m = await msg.answer("📊 Статистика пуста")
        asyncio.create_task(delete_after(m, 15))
        return
    
    text = "📊 **Статистика нарушений:**\n\n"
    for idx, (uid, count) in enumerate(violations, 1):
        username = await get_username_by_id(uid)
        text += f"{idx}. {username} — {count} нарушений\n"
    
    m = await msg.answer(text, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 30))

# ============================================================
# === КНОПКА "Полная статистика" ===
# ============================================================
@dp.callback_query(F.data.startswith("full_stats_"))
async def full_stats_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    level = await get_user_level(user_id)
    if level < 3:
        await call.answer("⛔ Нет прав!", True)
        return
    
    target_id = int(call.data.split("_")[2])
    stats = await get_user_stats(target_id, call.message.chat.id)
    username = await get_username_by_id(target_id)
    
    logs = []
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT admin_name, action, target_name, details, date FROM admin_logs WHERE target_id = ? OR admin_id = ? ORDER BY date DESC",
            (target_id, target_id)
        )
        logs = await cursor.fetchall()
    
    report = (
        f"📊 **ПОЛНАЯ СТАТИСТИКА**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Пользователь: {username}\n"
        f"🆔 ID: `{target_id}`\n\n"
        f"📌 **Общая информация:**\n"
        f"• 👑 Роль: {stats['role']}\n"
        f"• 📊 Уровень: {stats['level']}\n"
        f"• ⭐ Карма: {stats['karma']}\n\n"
        f"⚠️ **Нарушения:**\n"
        f"• 🚫 Всего нарушений: {stats['violations']}\n"
        f"• ⚠️ Варнов: {stats['warns']}\n"
        f"{'🔴 В муте' if stats['is_muted'] else '🟢 Не в муте'}\n\n"
    )
    
    if logs:
        report += f"📋 **ВСЕ ДЕЙСТВИЯ:**\n"
        for admin_name, action, target_name, details, date in logs[:20]:
            report += f"• {admin_name} {action}"
            if target_name:
                report += f" → {target_name}"
            if details:
                report += f" ({details})"
            report += f"\n  🕐 {date[:16]}\n"
    
    report += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    report += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    
    m = await call.message.answer(report, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))
    await call.answer("📊 Полная статистика загружена!")

# ============================================================
# === ОБРАБОТКА КНОПОК ===
# ============================================================
@dp.callback_query()
async def handle_callbacks(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    level = await get_user_level(user_id)
    data = call.data

    if data == "admin_close":
        await call.message.delete()
        await call.answer("Закрыто")
        return

    if data.startswith("sett_"):
        action = data[len("sett_"):]
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
            await state.update_data(channel_id=chat_id)
            await state.set_state(AdminStates.set_mute_duration)
            await call.answer()
            return
        elif action == "warn_limit":
            await call.message.answer("📝 Введи новый лимит варнов (число):")
            await state.update_data(channel_id=chat_id)
            await state.set_state(AdminStates.set_warn_limit)
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

    if level < 1:
        await call.answer("⛔ Нет прав!", True)
        return

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
        
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 45))
        await call.answer()
        return

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
        await state.set_state(AdminStates.add_whitelist)
        await call.answer()
        return
    
    if data == "admin_remove_whitelist":
        m = await call.message.answer("📝 Введи домен для удаления:")
        await state.set_state(AdminStates.remove_whitelist)
        await call.answer()
        return

    if data in ["admin_warn", "admin_mute", "admin_unmute", "admin_clear_warns", "admin_check_warns", "admin_set_moderator", "admin_set_admin", "admin_set_level"]:
        action_name = data.replace("admin_", "")
        m = await call.message.answer(f"📝 Введи ID или @username для: {action_name}")
        await state.set_state(getattr(AdminStates, action_name))
        await call.answer()
        return
    
    if data == "admin_give_admin":
        m = await call.message.answer("📝 Введи: `/giveadmin @user уровень`")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    if data == "admin_user_stats":
        m = await call.message.answer("📝 Введи ID или @username пользователя:")
        await state.set_state(AdminStates.user_stats)
        await call.answer()
        return
    
    if data == "admin_set_channel_operator":
        m = await call.message.answer("📝 Введи ID канала для назначения оператора:")
        await state.set_state(AdminStates.get_channel_for_operator)
        await call.answer()
        return
    
    if data == "admin_set_channel_owner":
        m = await call.message.answer("📝 Введи ID канала для назначения главы:")
        await state.set_state(AdminStates.get_channel_for_owner)
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
@dp.message(StateFilter(AdminStates.set_mute_duration))
async def set_mute_duration_handler(msg: types.Message, state: FSMContext):
    try:
        duration = int(msg.text.strip())
        data = await state.get_data()
        chat_id = data.get("channel_id")
        settings = await get_channel_settings(chat_id)
        settings['mute_duration'] = duration
        await update_channel_settings(chat_id, settings)
        m = await msg.answer(f"✅ Длительность мута: {duration} сек")
        asyncio.create_task(delete_after(m, 15))
        await state.clear()
    except ValueError:
        m = await msg.answer("❌ Введи число!")
        asyncio.create_task(delete_after(m, 10))

@dp.message(StateFilter(AdminStates.set_warn_limit))
async def set_warn_limit_handler(msg: types.Message, state: FSMContext):
    try:
        limit = int(msg.text.strip())
        data = await state.get_data()
        chat_id = data.get("channel_id")
        settings = await get_channel_settings(chat_id)
        settings['warn_limit'] = limit
        await update_channel_settings(chat_id, settings)
        m = await msg.answer(f"✅ Лимит варнов: {limit}")
        asyncio.create_task(delete_after(m, 15))
        await state.clear()
    except ValueError:
        m = await msg.answer("❌ Введи число!")
        asyncio.create_task(delete_after(m, 10))

@dp.message(StateFilter(AdminStates.user_stats))
async def admin_user_stats_handler(msg: types.Message, state: FSMContext):
    target_id = await resolve_target(msg, msg.text.strip())
    if not target_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=msg.text.strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    stats = await get_user_stats(target_id, msg.chat.id)
    username = await get_username_by_id(target_id)
    report = (
        f"📊 **Статистика пользователя**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Пользователь: {username}\n"
        f"🆔 ID: `{target_id}`\n\n"
        f"📌 **Общая информация:**\n"
        f"• 👑 Роль: {stats['role']}\n"
        f"• 📊 Уровень: {stats['level']}\n"
        f"• ⭐ Карма: {stats['karma']}\n\n"
        f"⚠️ **Нарушения:**\n"
        f"• 🚫 Всего нарушений: {stats['violations']}\n"
        f"• ⚠️ Варнов: {stats['warns']}\n"
        f"{'🔴 В муте' if stats['is_muted'] else '🟢 Не в муте'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    m = await msg.answer(report, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 45))
    await state.clear()

async def _resolve_target_from_text(msg: types.Message, chat_id: int = None):
    return await resolve_target(msg, (msg.text or "").strip())

@dp.message(StateFilter(AdminStates.warn))
async def admin_warn_handler(msg: types.Message, state: FSMContext):
    target_id = await _resolve_target_from_text(msg)
    if not target_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=(msg.text or "").strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    was_auto_muted, mute_duration = await add_warning(target_id, msg.chat.id, "Нарушение", msg.from_user.id)
    warns = await get_warnings(target_id, msg.chat.id)
    settings = await get_channel_settings(msg.chat.id)
    if was_auto_muted:
        m = await msg.answer(f"⚠️ {warns} варнов! Мут {mute_duration//60} мин!")
    else:
        m = await msg.answer(f"✅ Варн {warns}/{settings['warn_limit']}")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.check_warns))
async def admin_check_warns_handler(msg: types.Message, state: FSMContext):
    target_id = await _resolve_target_from_text(msg)
    if not target_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=(msg.text or "").strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    warns = await get_warnings(target_id, msg.chat.id)
    m = await msg.answer(f"📋 Варнов: {warns}")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.clear_warns))
async def admin_clear_warns_handler(msg: types.Message, state: FSMContext):
    target_id = await _resolve_target_from_text(msg)
    if not target_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=(msg.text or "").strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    await clear_warnings(target_id, msg.chat.id)
    m = await msg.answer(f"✅ Варны очищены")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.mute))
async def admin_mute_handler(msg: types.Message, state: FSMContext):
    target_id = await _resolve_target_from_text(msg)
    if not target_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=(msg.text or "").strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    await state.update_data(target_id=target_id)
    await state.set_state(AdminStates.mute_duration)
    m = await msg.answer(f"⏱️ Введи длительность (сек):")
    asyncio.create_task(delete_after(m, 30))

@dp.message(StateFilter(AdminStates.mute_duration))
async def admin_mute_duration_handler(msg: types.Message, state: FSMContext):
    try:
        duration = int(msg.text.strip())
    except ValueError:
        m = await msg.answer("❌ Введи число!")
        asyncio.create_task(delete_after(m, 10))
        return
    data = await state.get_data()
    target_id = data.get("target_id")
    await add_mute(target_id, duration)
    m = await msg.answer(f"✅ Замучен на {duration}с")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.unmute))
async def admin_unmute_handler(msg: types.Message, state: FSMContext):
    target_id = await _resolve_target_from_text(msg)
    if not target_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=(msg.text or "").strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    await remove_mute(target_id)
    m = await msg.answer(f"✅ Размучен")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.set_moderator))
async def admin_set_moderator_handler(msg: types.Message, state: FSMContext):
    target_id = await _resolve_target_from_text(msg)
    if not target_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=(msg.text or "").strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    await set_user_level(target_id, 2)
    m = await msg.answer(f"🛡️ Модератор (уровень 2)")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.set_admin))
async def admin_set_admin_handler(msg: types.Message, state: FSMContext):
    target_id = await _resolve_target_from_text(msg)
    if not target_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=(msg.text or "").strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    await set_user_level(target_id, 3)
    m = await msg.answer(f"🔴 Администратор (уровень 3)")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.set_level))
async def admin_set_level_handler(msg: types.Message, state: FSMContext):
    target_id = await _resolve_target_from_text(msg)
    if not target_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=(msg.text or "").strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    await state.update_data(target_id=target_id)
    await state.set_state(AdminStates.set_level_input)
    m = await msg.answer(
        f"📊 Введи уровень (0-4):\n\n"
        "0 - Участник\n"
        "1 - Наблюдатель 🟢\n"
        "2 - Модератор 🟠\n"
        "3 - Администратор 🔴\n"
        "4 - Главный администратор ⭐"
    )
    asyncio.create_task(delete_after(m, 60))

@dp.message(StateFilter(AdminStates.set_level_input))
async def admin_set_level_input_handler(msg: types.Message, state: FSMContext):
    try:
        new_level = int(msg.text.strip())
    except ValueError:
        m = await msg.answer("❌ Введи число!")
        asyncio.create_task(delete_after(m, 10))
        return
    if not 0 <= new_level <= 4:
        m = await msg.answer("❌ 0-4!")
        asyncio.create_task(delete_after(m, 10))
        return
    data = await state.get_data()
    target_id = data.get("target_id")
    await set_user_level(target_id, new_level)
    name = ADMIN_LEVELS[new_level]["name"] if new_level > 0 else "Участник"
    m = await msg.answer(f"✅ Уровень {new_level} ({name})")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.get_channel_for_operator))
async def admin_get_channel_for_operator_handler(msg: types.Message, state: FSMContext):
    try:
        channel_id = int(msg.text.strip())
    except ValueError:
        m = await msg.answer("❌ Введи ID канала!")
        asyncio.create_task(delete_after(m, 10))
        return
    await state.update_data(channel_id=channel_id)
    await state.set_state(AdminStates.setup_operator)
    m = await msg.answer("📝 Введи @username оператора:")
    asyncio.create_task(delete_after(m, 30))

@dp.message(StateFilter(AdminStates.setup_operator))
async def admin_setup_operator_handler(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data.get("channel_id")
    operator_id = await resolve_target(msg, msg.text.strip())
    if not operator_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=msg.text.strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    await set_channel_operator(channel_id, operator_id, msg.text.replace('@', ''))
    m = await msg.answer(f"✅ Оператор назначен для канала `{channel_id}`")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.get_channel_for_owner))
async def admin_get_channel_for_owner_handler(msg: types.Message, state: FSMContext):
    try:
        channel_id = int(msg.text.strip())
    except ValueError:
        m = await msg.answer("❌ Введи ID канала!")
        asyncio.create_task(delete_after(m, 10))
        return
    await state.update_data(channel_id=channel_id)
    await state.set_state(AdminStates.setup_owner)
    m = await msg.answer("📝 Введи @username главы:")
    asyncio.create_task(delete_after(m, 30))

@dp.message(StateFilter(AdminStates.setup_owner))
async def admin_setup_owner_handler(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data.get("channel_id")
    owner_id = await resolve_target(msg, msg.text.strip())
    if not owner_id:
        m = await msg.answer(USER_NOT_FOUND_HINT.format(target=msg.text.strip()))
        asyncio.create_task(delete_after(m, 10))
        return
    await set_channel_owner(channel_id, owner_id, msg.text.replace('@', ''))
    m = await msg.answer(f"👑 Глава назначен для канала `{channel_id}`")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.add_whitelist))
async def admin_add_whitelist_handler(msg: types.Message, state: FSMContext):
    domain = msg.text.strip().lower()
    domain = re.sub(r'^https?://', '', domain)
    domain = re.sub(r'^www\.', '', domain)
    await add_whitelist_domain(domain, msg.from_user.id)
    m = await msg.answer(f"✅ Домен {domain} добавлен")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

@dp.message(StateFilter(AdminStates.remove_whitelist))
async def admin_remove_whitelist_handler(msg: types.Message, state: FSMContext):
    domain = msg.text.strip().lower()
    domain = re.sub(r'^https?://', '', domain)
    domain = re.sub(r'^www\.', '', domain)
    await remove_whitelist_domain(domain)
    m = await msg.answer(f"✅ Домен {domain} удалён")
    asyncio.create_task(delete_after(m, 15))
    await state.clear()

# ============================================================
# === ФИЛЬТР СООБЩЕНИЙ ===
# ============================================================
@dp.message(F.text | F.caption)
async def filter_msg(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)

    settings = await get_channel_settings(msg.chat.id)
    if not settings['enabled'] or level >= 1:
        await send_auto_response(msg)
        return

    if await is_muted(user_id):
        await msg.delete()
        m = await msg.answer("⛔ Ты в муте!")
        asyncio.create_task(delete_after(m, 5))
        return

    text = msg.text or msg.caption or ""
    has_photo = bool(msg.photo or msg.video)

    found, word = has_forbidden(text)
    if found:
        await msg.delete()
        await add_violation(user_id, msg.chat.id, "forbidden")
        was_auto_muted, mute_duration = await add_warning(user_id, msg.chat.id, f"Запрещёнка 18+: {word}", 0)
        
        target_name = await get_username_by_id(user_id)
        await send_log(
            msg.chat.id,
            "🚫 Запрещёнка 18+",
            f"👤 Пользователь: {target_name} ({user_id})\n"
            f"📝 Текст: {text[:100]}...\n"
            f"🔍 Найдено слово: `{word}`\n"
            f"⚠️ Варнов: {await get_warnings(user_id, msg.chat.id)}/{settings['warn_limit']}"
        )
        
        if was_auto_muted:
            m = await msg.answer(f"🚫 **ЗАПРЕЩЁНКА 18+!**\n🔒 Автомут на {mute_duration//60} минут!")
        else:
            warns = await get_warnings(user_id, msg.chat.id)
            m = await msg.answer(f"🚫 **ЗАПРЕЩЁНКА 18+!**\n⚠️ Варн {warns}/{settings['warn_limit']}")
        asyncio.create_task(delete_after(m, 15))
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

    await send_auto_response(msg)

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
    
    found, word = has_forbidden(text)
    if found:
        try:
            post_id = msg.message_id
            await msg.delete()
            await send_log(
                msg.chat.id,
                "🗑️ Удалён пост",
                f"📌 Канал: {msg.chat.title or msg.chat.id}\n"
                f"🆔 ID поста: {post_id}\n"
                f"📝 Текст: {text[:100]}...\n"
                f"🔍 Причина: Найдено слово `{word}`"
            )
        except Exception as e:
            print(f"Ошибка удаления поста: {e}")
        return
    
    if await has_blocked_link(text):
        try:
            post_id = msg.message_id
            await msg.delete()
            await send_log(
                msg.chat.id,
                "🗑️ Удалён пост",
                f"📌 Канал: {msg.chat.title or msg.chat.id}\n"
                f"🆔 ID поста: {post_id}\n"
                f"📝 Текст: {text[:100]}...\n"
                f"🔍 Причина: Запрещённая ссылка"
            )
        except:
            pass
        return

# ============================================================
# === ФОНОВЫЕ ЗАДАЧИ ===
# ============================================================
async def background_tasks():
    while True:
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("DELETE FROM warnings WHERE date < datetime('now', '-7 day')")
                await db.commit()
            
            async with aiosqlite.connect(DB_NAME) as db:
                cursor = await db.execute(
                    "SELECT user_id, until FROM mutes WHERE until <= ?",
                    (int(time.time()),)
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
        await asyncio.sleep(60)

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

async def run_all():
    await asyncio.gather(
        main(),
        start_web()
    )

if __name__ == "__main__":
    asyncio.run(run_all())
