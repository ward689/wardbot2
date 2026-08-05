import asyncio
import time
import re
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, ADMIN_IDS, LOG_CHANNEL_ID, ADMIN_LEVELS, FORBIDDEN_WORDS, BAD_WORDS, WHITELIST_DOMAINS, STARS_PRICES, STARS_PACKAGES
from database import *
from aiohttp import web

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

current_action = {}
target_user = {}
user_selected_chat = {}

# ============================================================
# === УНИВЕРСАЛЬНЫЙ ПОИСК ПОЛЬЗОВАТЕЛЯ ===
# ============================================================
async def resolve_user(text: str, chat_id: int = None) -> int:
    text = text.strip()
    try:
        return int(text)
    except:
        pass
    if text.startswith("@"):
        username = text[1:]
    else:
        username = text
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
    if chat_id:
        try:
            member = await bot.get_chat_member(chat_id, f"@{username}")
            if member and member.user:
                return member.user.id
        except:
            pass
    return None

async def get_username_by_id(user_id: int) -> str:
    try:
        user = await bot.get_user(user_id)
        if user and user.username:
            return f"@{user.username}"
        elif user and user.first_name:
            return user.first_name
        return str(user_id)
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
        if domain not in whitelist:
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
        "🛍️ /shop — магазин\n"
        "⭐ /stars — звёзды\n"
        "💰 /buy_stars — купить звёзды\n\n"
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
        "/add_response — добавить авто-ответ (ЛС)\n"
        "/list_responses — список авто-ответов (ЛС)\n"
        "/remove_response — удалить авто-ответ (ЛС)",
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
        "🪙 Снять варн — 500 монет / 10 ⭐\n"
        "🔓 Снять мут — 1000 монет / 20 ⭐\n"
        "🔄 Разбан — 2500 монет / 50 ⭐\n"
        "🔗 Одноразовая ссылка — 150 монет\n\n"
        
        "**5. Получение монет**\n"
        "🎁 Ежедневный бонус — `/daily`\n"
        "💰 Выдача админом — `/givemoney 1000`\n\n"
        
        "**6. Авто-ответы**\n"
        "Настраиваются в ЛС командами:\n"
        "📝 /add_response\n"
        "📋 /list_responses\n"
        "🗑️ /remove_response\n\n"
        
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
# === МАГАЗИН С ВЫБОРОМ ЧАТА ===
# ============================================================
@dp.message(Command("shop"))
async def shop_cmd(msg: types.Message):
    user_id = msg.from_user.id
    user_username = await get_username_by_id(user_id)
    karma = await get_karma(user_id)
    stars = await get_user_stars(user_id)
    
    known_chats = [
        (-1003018474298, "анон чат"),
        (-1003881455978, "ришон чатик"),
        (-1003704771166, "анон кармиэль чат"),
    ]
    
    chat_buttons = []
    for chat_id, chat_name in known_chats:
        try:
            chat = await bot.get_chat(chat_id)
            if chat:
                chat_buttons.append([InlineKeyboardButton(
                    text=f"📢 {chat_name}",
                    callback_data=f"shop_select_chat_{chat_id}"
                )])
        except:
            pass
    
    if not chat_buttons:
        for chat_id, chat_name in known_chats:
            chat_buttons.append([InlineKeyboardButton(
                text=f"📢 {chat_name}",
                callback_data=f"shop_select_chat_{chat_id}"
            )])
    
    chat_buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="shop_close")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=chat_buttons)
    
    await msg.answer(
        f"🛍️ **Магазин**\n\n"
        f"👤 Пользователь: {user_username}\n"
        f"💰 Баланс: {karma} монет\n"
        f"⭐ Звёзды: {stars}\n\n"
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
    stars = await get_user_stars(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 Снять варн — 500 монет", callback_data="shop_buy_clear_warn")],
        [InlineKeyboardButton(text="🪙 Снять мут — 1000 монет", callback_data="shop_buy_clear_mute")],
        [InlineKeyboardButton(text="🪙 Разбан — 2500 монет", callback_data="shop_buy_unban")],
        [InlineKeyboardButton(text="🔗 Одноразовая ссылка — 150 монет", callback_data="shop_buy_invite")],
        [InlineKeyboardButton(text="⭐ Снять варн — 10 звёзд", callback_data="shop_buy_stars_clear_warn")],
        [InlineKeyboardButton(text="⭐ Снять мут — 20 звёзд", callback_data="shop_buy_stars_clear_mute")],
        [InlineKeyboardButton(text="⭐ Разбан — 50 звёзд", callback_data="shop_buy_stars_unban")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="shop_back")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="shop_close")]
    ])
    
    status_text = ""
    if warns > 0:
        status_text += f"\n⚠️ У тебя {warns} варнов"
    if is_muted_user:
        status_text += f"\n🔴 Ты в муте!"
    if warns == 0 and not is_muted_user:
        status_text += f"\n✅ Нарушений нет"
    
    await call.message.edit_text(
        f"🛍️ **Магазин**\n\n"
        f"📢 Чат: {chat_name}\n"
        f"👤 Пользователь: {await get_username_by_id(user_id)}\n"
        f"💰 Баланс: {karma} монет\n"
        f"⭐ Звёзды: {stars}{status_text}\n\n"
        f"📌 **Доступные товары:**\n"
        f"🪙 За монеты:\n"
        f"• Снять варн — 500 монет\n"
        f"• Снять мут — 1000 монет\n"
        f"• Разбан — 2500 монет\n"
        f"• Одноразовая ссылка — 150 монет\n\n"
        f"⭐ За звёзды:\n"
        f"• Снять варн — 10 ⭐\n"
        f"• Снять мут — 20 ⭐\n"
        f"• Разбан — 50 ⭐\n\n"
        f"Выбери действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await call.answer()

@dp.callback_query(F.data == "shop_back")
async def shop_back(call: types.CallbackQuery):
    await shop_cmd(call.message)
    await call.answer()

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
    
    if action == "clear_warn":
        if karma < 500:
            await call.answer("❌ Недостаточно монет! Нужно 500", show_alert=True)
            return
        warns = await get_warnings(user_id, chat_id)
        if warns == 0:
            await call.answer("❌ У тебя нет варнов в этом чате!", show_alert=True)
            return
        await clear_warnings(user_id, chat_id)
        await add_karma(user_id, -500)
        await call.answer("✅ Варны сняты! -500 монет", show_alert=True)
        await call.message.edit_text(
            f"✅ **Варны сняты!**\n\n"
            f"📢 Чат: {chat_name}\n"
            f"💰 Остаток: {await get_karma(user_id)} монет\n"
            f"🛍️ Для покупок используй /shop",
            parse_mode="Markdown"
        )
        return
    
    if action == "clear_mute":
        if karma < 1000:
            await call.answer("❌ Недостаточно монет! Нужно 1000", show_alert=True)
            return
        if not await is_muted(user_id):
            await call.answer("❌ Ты не в муте!", show_alert=True)
            return
        await remove_mute(user_id)
        await add_karma(user_id, -1000)
        await call.answer("✅ Мут снят! -1000 монет", show_alert=True)
        await call.message.edit_text(
            f"✅ **Мут снят!**\n\n"
            f"📢 Чат: {chat_name}\n"
            f"💰 Остаток: {await get_karma(user_id)} монет\n"
            f"🛍️ Для покупок используй /shop",
            parse_mode="Markdown"
        )
        return
    
    if action == "unban":
        if karma < 2500:
            await call.answer("❌ Недостаточно монет! Нужно 2500", show_alert=True)
            return
        if await is_muted(user_id):
            await remove_mute(user_id)
        await clear_warnings(user_id, chat_id)
        await add_karma(user_id, -2500)
        await call.answer("✅ Разбан выполнен! -2500 монет", show_alert=True)
        await call.message.edit_text(
            f"✅ **Разбан выполнен!**\n\n"
            f"📢 Чат: {chat_name}\n"
            f"💰 Остаток: {await get_karma(user_id)} монет\n"
            f"🛍️ Для покупок используй /shop",
            parse_mode="Markdown"
        )
        return
    
    if action == "invite":
        if karma < 150:
            await call.answer("❌ Недостаточно монет! Нужно 150", show_alert=True)
            return
        try:
            try:
                invite_link = await bot.create_chat_invite_link(chat_id, member_limit=1)
            except Exception as e:
                if "not enough rights" in str(e):
                    await call.answer("❌ У бота нет прав создавать ссылки! Добавьте бота админом с правами на создание ссылок.", show_alert=True)
                    return
                raise e
            
            await add_karma(user_id, -150)
            await call.answer("✅ Ссылка создана! -150 монет", show_alert=True)
            await call.message.edit_text(
                f"✅ **Одноразовая ссылка создана!**\n\n"
                f"📢 Чат: {chat_name}\n"
                f"🔗 Ссылка: {invite_link.invite_link}\n"
                f"⚠️ Ссылка действительна для одного пользователя!\n\n"
                f"💰 Остаток: {await get_karma(user_id)} монет\n"
                f"🛍️ Для покупок используй /shop",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            await call.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
        return
    
    # === ПОКУПКА ЗА ЗВЁЗДЫ ===
    if action.startswith("stars_"):
        action_type = action.replace("stars_", "")
        
        if action_type == "clear_warn":
            stars_needed = STARS_PRICES.get("clear_warn", 10)
            stars = await get_user_stars(user_id)
            if stars < stars_needed:
                await call.answer(f"❌ Недостаточно звёзд! Нужно {stars_needed} ⭐", show_alert=True)
                return
            warns = await get_warnings(user_id, chat_id)
            if warns == 0:
                await call.answer("❌ У тебя нет варнов!", show_alert=True)
                return
            await clear_warnings(user_id, chat_id)
            await remove_stars(user_id, stars_needed)
            await call.answer(f"✅ Варны сняты! -{stars_needed} ⭐", show_alert=True)
            await call.message.edit_text(
                f"✅ **Варны сняты за звёзды!**\n\n"
                f"📢 Чат: {chat_name}\n"
                f"⭐ Остаток звёзд: {await get_user_stars(user_id)}\n"
                f"🛍️ Для покупок используй /shop",
                parse_mode="Markdown"
            )
            return
        
        if action_type == "clear_mute":
            stars_needed = STARS_PRICES.get("clear_mute", 20)
            stars = await get_user_stars(user_id)
            if stars < stars_needed:
                await call.answer(f"❌ Недостаточно звёзд! Нужно {stars_needed} ⭐", show_alert=True)
                return
            if not await is_muted(user_id):
                await call.answer("❌ Ты не в муте!", show_alert=True)
                return
            await remove_mute(user_id)
            await remove_stars(user_id, stars_needed)
            await call.answer(f"✅ Мут снят! -{stars_needed} ⭐", show_alert=True)
            await call.message.edit_text(
                f"✅ **Мут снят за звёзды!**\n\n"
                f"📢 Чат: {chat_name}\n"
                f"⭐ Остаток звёзд: {await get_user_stars(user_id)}\n"
                f"🛍️ Для покупок используй /shop",
                parse_mode="Markdown"
            )
            return
        
        if action_type == "unban":
            stars_needed = STARS_PRICES.get("unban", 50)
            stars = await get_user_stars(user_id)
            if stars < stars_needed:
                await call.answer(f"❌ Недостаточно звёзд! Нужно {stars_needed} ⭐", show_alert=True)
                return
            if await is_muted(user_id):
                await remove_mute(user_id)
            await clear_warnings(user_id, chat_id)
            await remove_stars(user_id, stars_needed)
            await call.answer(f"✅ Разбан выполнен! -{stars_needed} ⭐", show_alert=True)
            await call.message.edit_text(
                f"✅ **Разбан за звёзды!**\n\n"
                f"📢 Чат: {chat_name}\n"
                f"⭐ Остаток звёзд: {await get_user_stars(user_id)}\n"
                f"🛍️ Для покупок используй /shop",
                parse_mode="Markdown"
            )
            return
    
    await call.answer("❌ Неизвестное действие")

@dp.callback_query(F.data == "shop_close")
async def shop_close(call: types.CallbackQuery):
    await call.message.delete()
    await call.answer("🛍️ Магазин закрыт")

# ============================================================
# === ЗВЁЗДЫ ===
# ============================================================
@dp.message(Command("stars"))
async def check_stars(msg: types.Message):
    user_id = msg.from_user.id
    stars = await get_user_stars(user_id)
    karma = await get_karma(user_id)
    await msg.answer(
        f"⭐ **Твои звёзды**\n\n"
        f"⭐ Звёзд: {stars}\n"
        f"💰 Монет: {karma}\n\n"
        f"📌 Для покупки звёзд используй `/buy_stars`",
        parse_mode="Markdown"
    )

@dp.message(Command("buy_stars"))
async def buy_stars_cmd(msg: types.Message):
    user_id = msg.from_user.id
    karma = await get_karma(user_id)
    stars = await get_user_stars(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 10 звёзд — 100 монет", callback_data="buy_stars_10")],
        [InlineKeyboardButton(text="⭐ 50 звёзд — 400 монет", callback_data="buy_stars_50")],
        [InlineKeyboardButton(text="⭐ 100 звёзд — 700 монет", callback_data="buy_stars_100")],
        [InlineKeyboardButton(text="⭐ 500 звёзд — 3000 монет", callback_data="buy_stars_500")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="buy_stars_close")]
    ])
    
    await msg.answer(
        f"⭐ **Купить звёзды**\n\n"
        f"💰 Твой баланс: {karma} монет\n"
        f"⭐ Твои звёзды: {stars}\n\n"
        f"📌 **Выбери пакет:**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("buy_stars_"))
async def buy_stars_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    amount = int(call.data.replace("buy_stars_", ""))
    
    price = STARS_PACKAGES.get(amount)
    if not price:
        await call.answer("❌ Неизвестный пакет!", show_alert=True)
        return
    
    karma = await get_karma(user_id)
    if karma < price:
        await call.answer(f"❌ Недостаточно монет! Нужно {price}", show_alert=True)
        return
    
    await add_karma(user_id, -price)
    await add_stars(user_id, amount)
    
    await call.answer(f"✅ Куплено {amount} звёзд за {price} монет!", show_alert=True)
    await call.message.edit_text(
        f"⭐ **Покупка звёзд!**\n\n"
        f"📌 Куплено: {amount} звёзд\n"
        f"💰 Стоимость: {price} монет\n"
        f"⭐ Всего звёзд: {await get_user_stars(user_id)}\n"
        f"💰 Остаток монет: {await get_karma(user_id)}\n\n"
        f"🛍️ Для покупок используй /shop",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "buy_stars_close")
async def buy_stars_close(call: types.CallbackQuery):
    await call.message.delete()
    await call.answer("Закрыто")

# ============================================================
# === АВТО-ОТВЕТЫ (НАСТРОЙКА В ЛС) ===
# ============================================================
@dp.message(Command("add_response"))
async def add_response_start(msg: types.Message):
    user_id = msg.from_user.id
    level = await get_user_level(user_id)
    if level < 3:
        await msg.answer("⛔ Нет прав!")
        return
    
    if msg.chat.type != "private":
        await msg.answer("❌ Эта команда работает только в ЛС!")
        return
    
    global current_action
    current_action[user_id] = "add_response_chat"
    await msg.answer(
        "📝 **Настройка авто-ответа**\n\n"
        "Введи ID канала, для которого хочешь настроить авто-ответ:\n"
        "Пример: `-1003018474298`"
    )

@dp.message(Command("list_responses"))
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

@dp.message(Command("remove_response"))
async def remove_response_start(msg: types.Message):
    user_id = msg.from_user.id
    if msg.chat.type != "private":
        await msg.answer("❌ Только в ЛС!")
        return
    
    level = await get_user_level(user_id)
    if level < 3:
        await msg.answer("⛔ Нет прав!")
        return
    
    global current_action
    current_action[user_id] = "remove_response_chat"
    await msg.answer(
        "📝 **Удаление авто-ответа**\n\n"
        "Введи ID канала, из которого хочешь удалить авто-ответ:\n"
        "Пример: `-1003018474298`"
    )

# ============================================================
# === ОБРАБОТЧИКИ ВВОДА ДЛЯ АВТО-ОТВЕТОВ ===
# ============================================================
@dp.message()
async def auto_response_input(msg: types.Message):
    user_id = msg.from_user.id
    action = current_action.get(user_id)
    
    if not action:
        return
    
    if msg.chat.type != "private":
        return
    
    if action == "add_response_chat":
        try:
            chat_id = int(msg.text.strip())
            try:
                chat = await bot.get_chat(chat_id)
                if chat:
                    current_action[user_id] = "add_response_keyword"
                    target_user[user_id] = chat_id
                    await msg.answer(
                        f"✅ Канал `{chat_id}` выбран!\n\n"
                        f"📝 Введи **ключевое слово**, на которое будет отвечать бот:\n"
                        f"Пример: `привет`, `правила`, `как дела`"
                    )
                else:
                    await msg.answer("❌ Бот не найден в этом канале!")
            except:
                await msg.answer("❌ Бот не найден в этом канале!")
        except ValueError:
            await msg.answer("❌ Введи корректный ID канала!")
        return
    
    if action == "add_response_keyword":
        keyword = msg.text.strip().lower()
        if not keyword:
            await msg.answer("❌ Введи ключевое слово!")
            return
        current_action[user_id] = "add_response_text"
        target_user[user_id] = {"chat": target_user.get(user_id), "keyword": keyword}
        await msg.answer(
            f"📝 Ключевое слово: `{keyword}`\n\n"
            f"Теперь введи **текст ответа**, который будет отправлять бот:\n"
            f"Можно использовать Markdown"
        )
        return
    
    if action == "add_response_text":
        response = msg.text.strip()
        if not response:
            await msg.answer("❌ Введи текст ответа!")
            return
        data = target_user.get(user_id)
        if isinstance(data, dict):
            chat_id = data.get("chat")
            keyword = data.get("keyword")
        else:
            chat_id = data
            keyword = ""
        
        await add_auto_response(chat_id, keyword, response, user_id)
        await msg.answer(
            f"✅ **Авто-ответ добавлен!**\n\n"
            f"📢 Канал: `{chat_id}`\n"
            f"🔑 Ключевое слово: `{keyword}`\n"
            f"📝 Ответ: {response[:100]}...\n\n"
            f"Для просмотра всех ответов используй `/list_responses`"
        )
        current_action[user_id] = None
        target_user[user_id] = None
        return
    
    if action == "remove_response_chat":
        try:
            chat_id = int(msg.text.strip())
            responses = await get_all_auto_responses(chat_id)
            if not responses:
                await msg.answer(f"📋 В канале `{chat_id}` нет авто-ответов!")
                return
            
            text = f"📋 **Авто-ответы в канале `{chat_id}`:**\n\n"
            for keyword, response, date in responses:
                text += f"• `{keyword}` → {response[:50]}...\n"
            text += f"\n📝 Введи **ключевое слово**, которое хочешь удалить:"
            
            current_action[user_id] = "remove_response_keyword"
            target_user[user_id] = chat_id
            await msg.answer(text, parse_mode="Markdown")
        except ValueError:
            await msg.answer("❌ Введи корректный ID канала!")
        return
    
    if action == "remove_response_keyword":
        keyword = msg.text.strip().lower()
        chat_id = target_user.get(user_id)
        await remove_auto_response(chat_id, keyword)
        await msg.answer(f"✅ Авто-ответ на `{keyword}` удалён!")
        current_action[user_id] = None
        target_user[user_id] = None
        return

# ============================================================
# === ФИЛЬТР АВТО-ОТВЕТОВ В ЧАТАХ ===
# ============================================================
@dp.message(F.text)
async def auto_response_filter(msg: types.Message):
    # Проверяем, есть ли авто-ответы для этого чата
    responses = await get_all_auto_responses(msg.chat.id)
    if not responses:
        return
    
    text = msg.text.lower()
    for keyword, response, date in responses:
        if keyword in text:
            await msg.answer(response)
            break

# ============================================================
# === КОМАНДА /id ===
# ============================================================
@dp.message(Command("id"))
async def get_user_id(msg: types.Message):
    args = msg.text.split()
    if len(args) >= 2:
        target = args[1]
        target_id = await resolve_user(target, msg.chat.id)
        if target_id:
            username = await get_username_by_id(target_id)
            await msg.answer(
                f"👤 **Пользователь найден!**\n\n"
                f"📌 Юзернейм: {username}\n"
                f"🆔 ID: `{target_id}`",
                parse_mode="Markdown"
            )
            return
        await msg.answer(f"❌ Пользователь {target} не найден!\n💡 Используйте @userinfobot")
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
            text += f"• `/add_response`\n"
            text += f"• `/list_responses`\n"
            text += f"• `/remove_response`\n"
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
    
    target_id = await resolve_user(target, msg.chat.id)
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
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
async def setup_operator_cmd(msg: types.Message):
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
    
    global current_action
    current_action[user_id] = "setup_operator"
    target_user[user_id] = msg.chat.id
    m = await msg.answer("📝 Введи @username или ID пользователя для назначения оператором:")
    asyncio.create_task(delete_after(m, 30))

# ============================================================
# === КОМАНДА /setowner ===
# ============================================================
@dp.message(Command("setowner"))
async def set_owner_cmd(msg: types.Message):
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
    
    global current_action
    current_action[user_id] = "setup_owner"
    target_user[user_id] = msg.chat.id
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
    
    chat = await bot.get_chat(chat_id)
    if chat.type not in ["group", "supergroup"]:
        await msg.answer("❌ Только в группах!")
        return
    
    try:
        count = 0
        try:
            offset = 0
            limit = 100
            while True:
                members = await bot.get_chat_members(chat_id, offset=offset, limit=limit)
                if not members:
                    break
                for member in members:
                    try:
                        await add_karma(member.user.id, amount)
                        count += 1
                    except:
                        pass
                offset += limit
                if len(members) < limit:
                    break
        except Exception as e:
            print(f"Ошибка при выдаче участникам: {e}")
            admins = await bot.get_chat_administrators(chat_id)
            for admin in admins:
                try:
                    await add_karma(admin.user.id, amount)
                    count += 1
                except:
                    pass
        
        if count == 0:
            await msg.answer("❌ Не удалось выдать монеты! Убедитесь, что бот имеет права администратора.")
            return
        
        await msg.answer(
            f"💰 **Монеты выданы!**\n\n"
            f"📌 Каждому участнику выдано: {amount} монет\n"
            f"👥 Получили: {count} участников\n"
            f"💳 Всего выдано: {amount * count} монет\n\n"
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
# === ОСТАЛЬНЫЕ КОМАНДЫ ===
# ============================================================
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
    target_id = await resolve_user(target, msg.chat.id)
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
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
    target_id = await resolve_user(target, msg.chat.id)
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
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
    target_id = await resolve_user(target, msg.chat.id)
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
        return
    target_level = await get_user_level(target_id)
    if target_level >= level:
        await msg.answer(f"❌ Нельзя варнить пользователя с уровнем {target_level}!")
        return
    was_auto_muted, mute_duration = await add_warning(target_id, msg.chat.id, reason, user_id)
    target_name = await get_username_by_id(target_id)
    await log_admin_action(user_id, "⚠️ Варн", target_id, reason)
    await send_log(msg.chat.id, "⚠️ Варн", f"👤 Пользователь: {target_name} ({target_id})\n📝 Причина: {reason}")
    warns = await get_warnings(target_id, msg.chat.id)
    if was_auto_muted:
        await msg.answer(
            f"⚠️ **Варн выдан!**\n\n"
            f"👤 Пользователь: {target_name}\n"
            f"📝 Причина: {reason}\n"
            f"🔥 Варнов: {warns}/10\n"
            f"🔒 **Автоматический мут на {mute_duration//60} минут!**"
        )
    else:
        await msg.answer(
            f"⚠️ **Варн выдан!**\n\n"
            f"👤 Пользователь: {target_name}\n"
            f"📝 Причина: {reason}\n"
            f"🔥 Варнов: {warns}/10"
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
    target_id = await resolve_user(target, msg.chat.id)
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
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
    target_id = await resolve_user(target, msg.chat.id)
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
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
    target_id = await resolve_user(target, msg.chat.id)
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
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
    target_id = await resolve_user(target, msg.chat.id)
    if not target_id:
        await msg.answer(f"❌ Пользователь {target} не найден!")
        return
    stats = await get_user_stats(target_id, msg.chat.id)
    username = await get_username_by_id(target_id)
    
    logs = []
    async with aiosqlite.connect("bot.db") as db:
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
        f"• ⭐ Карма: {stats['karma']}\n"
        f"• ⭐ Звёзды: {stats.get('stars', 0)}\n\n"
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
        current_action[user_id] = "add_whitelist"
        await call.answer()
        return
    
    if data == "admin_remove_whitelist":
        m = await call.message.answer("📝 Введи домен для удаления:")
        current_action[user_id] = "remove_whitelist"
        await call.answer()
        return

    if data in ["admin_warn", "admin_mute", "admin_unmute", "admin_clear_warns", "admin_check_warns", "admin_set_moderator", "admin_set_admin", "admin_set_level"]:
        action_name = data.replace("admin_", "")
        m = await call.message.answer(f"📝 Введи ID или @username для: {action_name}")
        current_action[user_id] = action_name
        await call.answer()
        return
    
    if data == "admin_give_admin":
        m = await call.message.answer("📝 Введи: `/giveadmin @user уровень`")
        asyncio.create_task(delete_after(m, 30))
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
    
    if level < 1:
        return
    
    text = msg.text.strip()
    if not text:
        return
    
    action = current_action.get(user_id)
    if not action:
        return
    
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

    target_id = await resolve_user(text, msg.chat.id)
    
    if not target_id:
        m = await msg.answer("❌ Пользователь не найден!")
        asyncio.create_task(delete_after(m, 10))
        return

    if action == "user_stats":
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
            f"• ⭐ Карма: {stats['karma']}\n"
            f"• ⭐ Звёзды: {stats.get('stars', 0)}\n\n"
            f"⚠️ **Нарушения:**\n"
            f"• 🚫 Всего нарушений: {stats['violations']}\n"
            f"• ⚠️ Варнов: {stats['warns']}\n"
            f"{'🔴 В муте' if stats['is_muted'] else '🟢 Не в муте'}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        m = await msg.answer(report, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 45))
        current_action[user_id] = None
        return

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
        await set_user_level(target_id, 3)
        m = await msg.answer(f"🔴 Администратор (уровень 3)")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return

    if action == "set_level":
        target_user[user_id] = target_id
        current_action[user_id] = "set_level_input"
        m = await msg.answer(
            f"📊 Введи уровень (0-4):\n\n"
            "0 - Участник\n"
            "1 - Наблюдатель 🟢\n"
            "2 - Модератор 🟠\n"
            "3 - Администратор 🔴\n"
            "4 - Главный администратор ⭐"
        )
        asyncio.create_task(delete_after(m, 60))
        return

    if action == "set_level_input":
        try:
            new_level = int(text)
            if 0 <= new_level <= 4:
                await set_user_level(target_user.get(user_id), new_level)
                name = ADMIN_LEVELS[new_level]["name"] if new_level > 0 else "Участник"
                m = await msg.answer(f"✅ Уровень {new_level} ({name})")
                current_action[user_id] = None
                asyncio.create_task(delete_after(m, 15))
            else:
                m = await msg.answer("❌ 0-4!")
                asyncio.create_task(delete_after(m, 10))
        except:
            m = await msg.answer("❌ Введи число!")
            asyncio.create_task(delete_after(m, 10))
        return

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
        operator_id = await resolve_user(text, channel_id)
        if not operator_id:
            m = await msg.answer("❌ Пользователь не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_operator(channel_id, operator_id, text.replace('@', ''))
        m = await msg.answer(f"✅ Оператор назначен для канала `{channel_id}`")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return

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
        owner_id = await resolve_user(text, channel_id)
        if not owner_id:
            m = await msg.answer("❌ Пользователь не найден!")
            asyncio.create_task(delete_after(m, 10))
            return
        await set_channel_owner(channel_id, owner_id, text.replace('@', ''))
        m = await msg.answer(f"👑 Глава назначен для канала `{channel_id}`")
        current_action[user_id] = None
        asyncio.create_task(delete_after(m, 15))
        return

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

    if level >= 1:
        return

    if await is_muted(user_id):
        await msg.delete()
        m = await msg.answer("⛔ Ты в муте!")
        asyncio.create_task(delete_after(m, 5))
        return

    text = msg.text or ""
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
            f"⚠️ Варнов: {await get_warnings(user_id, msg.chat.id)}/10"
        )
        
        if was_auto_muted:
            m = await msg.answer(f"🚫 **ЗАПРЕЩЁНКА 18+!**\n🔒 Автомут на {mute_duration//60} минут!")
        else:
            warns = await get_warnings(user_id, msg.chat.id)
            m = await msg.answer(f"🚫 **ЗАПРЕЩЁНКА 18+!**\n⚠️ Варн {warns}/10")
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
            async with aiosqlite.connect("bot.db") as db:
                await db.execute("DELETE FROM warnings WHERE date < datetime('now', '-7 day')")
                await db.commit()
            
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
