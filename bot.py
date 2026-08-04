# === DAILY ===
@dp.message(Command("daily"))
async def daily_bonus(msg: types.Message):
    user_id = msg.from_user.id
    can_claim, amount, streak = await get_daily_bonus(user_id)
    if can_claim:
        await claim_daily(user_id)
        await add_karma(user_id, amount // 10)
        m = await msg.answer(f"🎁 **Бонус!**\n💰 {amount} монет\n🔥 Стрик: {streak}\n⭐ Карма +{amount // 10}")
    else:
        remaining = 86400 - (int(time.time()) % 86400)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        m = await msg.answer(f"⏳ Бонус через: {hours}ч {minutes}м")
    asyncio.create_task(delete_after(m, 30))

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
        await msg.answer("📋 Админов нет")
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
        await msg.answer("⛔ Нужен уровень 6+!")
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
        await msg.answer("⛔ Нет прав!")
        return
    role = await get_user_role(user_id)
    keyboard = await get_admin_keyboard(user_id)
    m = await msg.answer(f"🛡️ *Админ-панель*\n👤 {role}\n📊 {level}\n\nВыбери:", reply_markup=keyboard, parse_mode="Markdown")
    asyncio.create_task(delete_after(m, 60))

# === ТЕКСТОВЫЕ КОМАНДЫ ДЛЯ АДМИНОВ ===
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
        await msg.answer("📝 Использование: `/мут @user 24ч причина`\nДоступно: 5м, 1ч, 24ч, 7д", parse_mode="Markdown")
        return
    target = args[1]
    duration_str = args[2] if len(args) > 2 else "5м"
    reason = args[3] if len(args) > 3 else "Нарушение"
    target_id = await get_user_id_by_username(target)
    if not target_id:
        try:
            target_id = int(target)
        except:
            await msg.answer(f"❌ Пользователь {target} не найден!")
            return
    duration = parse_duration(duration_str)
    if not duration:
        await msg.answer("❌ Неверный формат времени!")
        return
    target_level = await get_user_level(target_id)
    if target_level >= level and target_id not in ADMIN_IDS:
        await msg.answer(f"❌ Нельзя мутить пользователя с уровнем {target_level}!")
        return
    await add_mute(target_id, duration)
    await log_admin_action(user_id, "mute", target_id, f"{duration_str} - {reason}")
    await send_log(msg.chat.id, "🔨 Мут", f"Пользователь: {target}\nДлительность: {duration_str}\nПричина: {reason}")
    await msg.answer(f"🔨 **Мут выдан!**\n👤 {target}\n⏱️ {duration_str}\n📝 {reason}")

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
        await msg.answer("📝 Использование: `/размут @user`", parse_mode="Markdown")
        return
    target = args[1]
    target_id = await get_user_id_by_username(target)
    if not target_id:
        try:
            target_id = int(target)
        except:
            await msg.answer(f"❌ Пользователь {target} не найден!")
            return
    await remove_mute(target_id)
    await log_admin_action(user_id, "unmute", target_id, "")
    await send_log(msg.chat.id, "🔓 Размут", f"Пользователь: {target}")
    await msg.answer(f"🔓 **Размут снят!**\n👤 {target}")

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
        await msg.answer("📝 Использование: `/варн @user причина`", parse_mode="Markdown")
        return
    target = args[1]
    reason = args[2] if len(args) > 2 else "Нарушение"
    target_id = await get_user_id_by_username(target)
    if not target_id:
        try:
            target_id = int(target)
        except:
            await msg.answer(f"❌ Пользователь {target} не найден!")
            return
    target_level = await get_user_level(target_id)
    if target_level >= level and target_id not in ADMIN_IDS:
        await msg.answer(f"❌ Нельзя варнить пользователя с уровнем {target_level}!")
        return
    was_auto_muted = await add_warning(target_id, msg.chat.id, reason, user_id)
    await log_admin_action(user_id, "warn", target_id, reason)
    await send_log(msg.chat.id, "⚠️ Варн", f"Пользователь: {target}\nПричина: {reason}")
    warns = await get_warnings(target_id, msg.chat.id)
    settings = await get_channel_settings(msg.chat.id)
    if warns >= settings['warn_limit']:
        await add_mute(target_id, settings['mute_duration'])
        await msg.answer(f"⚠️ **Варн!**\n👤 {target}\n📝 {reason}\n🔥 {warns}/{settings['warn_limit']}\n⛔ Мут {settings['mute_duration']//60} мин!")
    else:
        await msg.answer(f"⚠️ **Варн!**\n👤 {target}\n📝 {reason}\n🔥 {warns}/{settings['warn_limit']}")

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
        await msg.answer("📝 Использование: `/бан @user причина`", parse_mode="Markdown")
        return
    target = args[1]
    reason = args[2] if len(args) > 2 else "Бан"
    target_id = await get_user_id_by_username(target)
    if not target_id:
        try:
            target_id = int(target)
        except:
            await msg.answer(f"❌ Пользователь {target} не найден!")
            return
    target_level = await get_user_level(target_id)
    if target_level >= level and target_id not in ADMIN_IDS:
        await msg.answer(f"❌ Нельзя банить пользователя с уровнем {target_level}!")
        return
    await add_mute(target_id, 2592000)
    await log_admin_action(user_id, "ban", target_id, reason)
    await send_log(msg.chat.id, "🚫 Бан", f"Пользователь: {target}\nПричина: {reason}")
    await msg.answer(f"🚫 **Бан!**\n👤 {target}\n📝 {reason}\n⏱️ 30 дней")

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
        await msg.answer("📝 Использование: `/кик @user причина`", parse_mode="Markdown")
        return
    target = args[1]
    reason = args[2] if len(args) > 2 else "Кик"
    target_id = await get_user_id_by_username(target)
    if not target_id:
        try:
            target_id = int(target)
        except:
            await msg.answer(f"❌ Пользователь {target} не найден!")
            return
    target_level = await get_user_level(target_id)
    if target_level >= level and target_id not in ADMIN_IDS:
        await msg.answer(f"❌ Нельзя кикать пользователя с уровнем {target_level}!")
        return
    await add_mute(target_id, 3600)
    await log_admin_action(user_id, "kick", target_id, reason)
    await send_log(msg.chat.id, "👢 Кик", f"Пользователь: {target}\nПричина: {reason}")
    await msg.answer(f"👢 **Кик!**\n👤 {target}\n📝 {reason}\n⏱️ 1 час")

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
        await msg.answer("📝 Использование: `/очистить @user`", parse_mode="Markdown")
        return
    target = args[1]
    target_id = await get_user_id_by_username(target)
    if not target_id:
        try:
            target_id = int(target)
        except:
            await msg.answer(f"❌ Пользователь {target} не найден!")
            return
    await clear_warnings(target_id, msg.chat.id)
    await log_admin_action(user_id, "clear_warns", target_id, "")
    await send_log(msg.chat.id, "🗑️ Очищены варны", f"Пользователь: {target}")
    await msg.answer(f"🗑️ **Варны очищены!**\n👤 {target}")

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
        await msg.answer("📝 Использование: `/инфо @user`", parse_mode="Markdown")
        return
    target = args[1]
    target_id = await get_user_id_by_username(target)
    if not target_id:
        try:
            target_id = int(target)
        except:
            await msg.answer(f"❌ Пользователь {target} не найден!")
            return
    stats = await get_user_stats(target_id, msg.chat.id)
    username = await get_username_by_id(target_id)
    report = f"📊 **Информация**\n━" * 25 + f"\n👤 {username}\n🆔 `{target_id}`\n\n"
    report += f"📌 Роль: {stats['role']}\n📊 Уровень: {stats['level']}\n⭐ Карма: {stats['karma']}\n\n"
    report += f"⚠️ Нарушений: {stats['violations']}\n⚠️ Варнов: {stats['warns']}\n"
    report += f"{'🔴 В муте' if stats['is_muted'] else '🟢 Не в муте'}\n"
    report += "\n━" * 25 + f"\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    await msg.answer(report, parse_mode="Markdown")

# === ОБРАБОТКА КНОПОК (CALLBACK) ===
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
            await call.answer(f"✅ Модерация {'вкл' if settings['enabled'] else 'выкл'}")
        elif action == "block_new":
            settings['block_new_accounts'] = not settings['block_new_accounts']
            await update_channel_settings(chat_id, settings)
            await call.answer(f"✅ Блокировка {'вкл' if settings['block_new_accounts'] else 'выкл'}")
        elif action == "show":
            text = f"⚙️ Настройки\n📌 {chat_id}\n{'✅' if settings['enabled'] else '❌'} Модерация\n⏱️ Мут: {settings['mute_duration']}с\n⚠️ Варны: {settings['warn_limit']}"
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
    
    if level < 2:
        await call.answer("⛔ Нет прав!", True)
        return
    
    if data == "admin_list_operators":
        ops = await get_all_channel_operators()
        if not ops:
            m = await call.message.answer("📋 Операторов нет")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = "📢 **Операторы:**\n\n"
        for ch_id, op_id, op_name, ch_name in ops:
            text += f"📌 {ch_name or ch_id} -> {op_id}\n"
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
    
    if data == "admin_logs":
        logs = await get_admin_logs(20)
        if not logs:
            m = await call.message.answer("📋 Логов нет")
            asyncio.create_task(delete_after(m, 15))
            await call.answer()
            return
        text = "📋 **Логи:**\n\n"
        for admin_id, action, target_id, details, date in logs:
            admin_name = await get_username_by_id(admin_id)
            text += f"• {admin_name} → {action}"
            if target_id:
                text += f" (пользователь: {await get_username_by_id(target_id)})"
            text += f"\n  🕐 {date[:16]}\n\n"
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 45))
        await call.answer()
        return
    
    # === ОСТАЛЬНЫЕ АДМИН КОМАНДЫ ===
    if data in ["admin_warn", "admin_mute", "admin_silent_mute", "admin_unmute", "admin_clear_warns", "admin_check_warns", "admin_set_moderator", "admin_set_admin", "admin_set_level"]:
        await call.message.answer(f"📝 Введи ID или @username для: {data.replace('admin_', '')}")
        current_action[user_id] = data.replace("admin_", "")
        await call.answer()
        return
    
    if data == "admin_user_stats":
        await call.message.answer("📝 Введи ID или @username пользователя:")
        current_action[user_id] = "user_stats"
        await call.answer()
        return
    
    if data == "admin_set_channel_operator":
        await call.message.answer("📝 Введи ID канала:")
        current_action[user_id] = "get_channel_for_operator"
        await call.answer()
        return
    
    if data == "admin_set_channel_owner":
        await call.message.answer("📝 Введи ID канала:")
        current_action[user_id] = "get_channel_for_owner"
        await call.answer()
        return
    
    if data == "admin_channel_settings":
        await channel_settings(call.message)
        await call.answer()
        return
    
    if data == "admin_manage_links":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список", callback_data="admin_show_whitelist")],
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
        text = "🔗 **Белый список:**\n\n" + "\n".join([f"• {d}" for d in domains])
        m = await call.message.answer(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(m, 30))
        await call.answer()
        return
    
    if data == "admin_add_whitelist":
        await call.message.answer("📝 Введи домен (example.com):")
        current_action[user_id] = "add_whitelist"
        await call.answer()
        return
    
    if data == "admin_remove_whitelist":
        await call.message.answer("📝 Введи домен для удаления:")
        current_action[user_id] = "remove_whitelist"
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
    if settings['block_new_accounts'] and not await check_account_age(user_id):
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
        m = await msg.answer(f"🚨 УГРОЗЫ ЗАПРЕЩЕНЫ!\n⛔ Мут {settings['mute_duration']//60} мин!")
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
    
    # Получаем ID
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
    
    if action == "user_stats":
        stats = await get_user_stats(target_id, msg.chat.id)
        username = await get_username_by_id(target_id)
        report = f"📊 **Статистика**\n━" * 25 + f"\n👤 {username}\n🆔 `{target_id}`\n\n"
        report += f"📌 Роль: {stats['role']}\n📊 Уровень: {stats['level']}\n⭐ Карма: {stats['karma']}\n\n"
        report += f"⚠️ Нарушений: {stats['violations']}\n⚠️ Варнов: {stats['warns']}\n"
        report += f"{'🔴 В муте' if stats['is_muted'] else '🟢 Не в муте'}\n"
        report += "\n━" * 25 + f"\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
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
            f"📊 Уровень (0-7):\n\n0 - Пользователь\n1 - Наблюдатель 🟢\n2 - Стажёр 🟡\n3 - Модератор 🟠\n4 - Старший модератор 🔵\n5 - Заместитель 🟣\n6 - Администратор 🔴\n7 - Главный админ ⭐"
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

# === КАНАЛЫ ===
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
        except:
            pass

# === ФОНОВЫЕ ЗАДАЧИ ===
async def background_tasks():
    while True:
        try:
            # Авто-снятие варнов
            async with aiosqlite.connect("bot.db") as db:
                await db.execute("DELETE FROM warnings WHERE date < datetime('now', '-1 day')")
                await db.commit()
            
            # Ежедневный отчёт
            now = datetime.now()
            if now.hour == 0 and now.minute == 0:
                try:
                    await bot.send_message(LOG_CHANNEL_ID, f"☀️ **Ежедневный отчёт**\n━" * 25 + f"\n📅 {now.strftime('%d.%m.%Y')}\n\n✨ Бот работает!\n🌴 Хорошего дня!", parse_mode="Markdown")
                except:
                    pass
            
            # Уведомления о снятии мута
            async with aiosqlite.connect("bot.db") as db:
                cursor = await db.execute("SELECT user_id, until FROM mutes WHERE until <= ? AND until > ?", (int(time.time()), int(time.time()) - 10))
                expired = await cursor.fetchall()
                for user_id, _ in expired:
                    try:
                        await bot.send_message(user_id, "🔓 **Мут снят!**\n🌴 Ты снова можешь писать.")
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
