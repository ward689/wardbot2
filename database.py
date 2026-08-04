import aiosqlite
import time
from config import ADMIN_IDS

DB_NAME = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("PRAGMA table_info(roles)")
        columns = await cursor.fetchall()
        has_level = any(col[1] == 'level' for col in columns)
        if not has_level:
            await db.execute("DROP TABLE IF EXISTS roles")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                reason TEXT,
                admin_id INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id INTEGER PRIMARY KEY,
                until INTEGER
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                user_id INTEGER PRIMARY KEY,
                level INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user'
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_operators (
                channel_id INTEGER PRIMARY KEY,
                operator_id INTEGER,
                operator_username TEXT,
                channel_name TEXT,
                set_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                admin_name TEXT,
                action TEXT,
                target_id INTEGER,
                target_name TEXT,
                details TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_settings (
                channel_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                mute_duration INTEGER DEFAULT 300,
                warn_limit INTEGER DEFAULT 3,
                block_new_accounts INTEGER DEFAULT 1,
                min_account_age INTEGER DEFAULT 86400,
                log_enabled INTEGER DEFAULT 1
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_bonus (
                user_id INTEGER PRIMARY KEY,
                last_claim INTEGER,
                streak INTEGER DEFAULT 0
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS karma (
                user_id INTEGER PRIMARY KEY,
                karma INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                type TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT UNIQUE,
                added_by INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_owners (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                owner_username TEXT,
                set_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.commit()
    
    from config import WHITELIST_DOMAINS
    async with aiosqlite.connect(DB_NAME) as db:
        for domain in WHITELIST_DOMAINS:
            try:
                await db.execute("INSERT OR IGNORE INTO whitelist (domain, added_by) VALUES (?, ?)", (domain, 0))
            except:
                pass
        await db.commit()

# === ВАРНЫ ===
async def add_warning(user_id, chat_id, reason, admin_id=0):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO warnings (user_id, chat_id, reason, admin_id) VALUES (?, ?, ?, ?)", (user_id, chat_id, reason, admin_id))
        await db.commit()
    if admin_id:
        await log_admin_action(admin_id, "⚠️ Варн", user_id, reason)
    settings = await get_channel_settings(chat_id)
    warns = await get_warnings(user_id, chat_id)
    if warns >= settings["warn_limit"]:
        await add_mute(user_id, settings["mute_duration"])
        return True
    return False

async def get_warnings(user_id, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ? AND chat_id = ? AND date > datetime('now', '-1 day')", (user_id, chat_id))
        result = await cursor.fetchone()
        return result[0] if result else 0

async def clear_warnings(user_id, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM warnings WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        await db.commit()

async def get_user_warnings_details(user_id, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT reason, admin_id, date FROM warnings WHERE user_id = ? AND chat_id = ? ORDER BY date DESC", (user_id, chat_id))
        return await cursor.fetchall()

# === МУТЫ ===
async def add_mute(user_id, duration):
    until = int(time.time()) + duration
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO mutes (user_id, until) VALUES (?, ?)", (user_id, until))
        await db.commit()

async def remove_mute(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))
        await db.commit()

async def is_muted(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT until FROM mutes WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        if result and result[0] > time.time():
            return True
        return False

async def get_mute_until(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT until FROM mutes WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

# === РОЛИ ===
async def set_user_level(user_id: int, level: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO roles (user_id, level, role) VALUES (?, ?, ?)", (user_id, level, f"admin_{level}" if level > 0 else "user"))
        await db.commit()

async def get_user_level(user_id: int) -> int:
    if user_id in ADMIN_IDS:
        return 7
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT level FROM roles WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_user_role(user_id: int) -> str:
    level = await get_user_level(user_id)
    if level == 0:
        return "👤 Пользователь"
    from config import ADMIN_LEVELS
    if level in ADMIN_LEVELS:
        return f"{ADMIN_LEVELS[level]['emoji']} {ADMIN_LEVELS[level]['name']}"
    return "👤 Пользователь"

async def is_moderator(user_id: int) -> bool:
    return await get_user_level(user_id) >= 2

async def is_admin(user_id: int) -> bool:
    return await get_user_level(user_id) >= 6

# === НОВАЯ СИСТЕМА ЛОГОВ (С USERNAME) ===
async def get_username_by_id_safe(user_id: int) -> str:
    """Безопасное получение username, если не получается — возвращает ID"""
    try:
        from aiogram import Bot
        from config import BOT_TOKEN
        bot = Bot(token=BOT_TOKEN)
        user = await bot.get_user(user_id)
        if user and user.username:
            return f"@{user.username}"
        elif user and user.first_name:
            return user.first_name
        return str(user_id)
    except:
        return str(user_id)

async def log_admin_action(admin_id: int, action: str, target_id: int = None, details: str = ""):
    try:
        admin_name = await get_username_by_id_safe(admin_id)
        target_name = await get_username_by_id_safe(target_id) if target_id else ""
    except:
        admin_name = str(admin_id)
        target_name = str(target_id) if target_id else ""
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO admin_logs (admin_id, admin_name, action, target_id, target_name, details) VALUES (?, ?, ?, ?, ?, ?)",
            (admin_id, admin_name, action, target_id, target_name, details)
        )
        await db.commit()

async def get_admin_logs(limit: int = 50):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT admin_id, admin_name, action, target_id, target_name, details, date FROM admin_logs ORDER BY date DESC LIMIT ?",
            (limit,)
        )
        return await cursor.fetchall()

async def get_admin_logs_by_user(user_id: int, limit: int = 50):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT admin_id, admin_name, action, target_id, target_name, details, date FROM admin_logs WHERE admin_id = ? OR target_id = ? ORDER BY date DESC LIMIT ?",
            (user_id, user_id, limit)
        )
        return await cursor.fetchall()

# === КАРМА ===
async def add_karma(user_id: int, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO karma (user_id, karma) VALUES (?, COALESCE((SELECT karma FROM karma WHERE user_id = ?), 0) + ?)", (user_id, user_id, amount))
        await db.commit()

async def get_karma(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT karma FROM karma WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

# === СТАТИСТИКА ===
async def add_violation(user_id: int, chat_id: int, type: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO violations (user_id, chat_id, type) VALUES (?, ?, ?)", (user_id, chat_id, type))
        await db.commit()

async def get_violations_stats(chat_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, COUNT(*) as count FROM violations WHERE chat_id = ? GROUP BY user_id ORDER BY count DESC LIMIT ?", (chat_id, limit))
        return await cursor.fetchall()

async def get_user_stats(user_id: int, chat_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM violations WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        violations = (await cursor.fetchone())[0] or 0
        cursor = await db.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        warns = (await cursor.fetchone())[0] or 0
        karma = await get_karma(user_id)
        is_muted_flag = await is_muted(user_id)
        mute_until = await get_mute_until(user_id) if is_muted_flag else 0
        level = await get_user_level(user_id)
        role = await get_user_role(user_id)
        
        cursor = await db.execute("SELECT COUNT(*) FROM admin_logs WHERE admin_id = ?", (user_id,))
        admin_actions = (await cursor.fetchone())[0] or 0
        cursor = await db.execute("SELECT COUNT(*) FROM admin_logs WHERE target_id = ?", (user_id,))
        target_actions = (await cursor.fetchone())[0] or 0
        
        return {
            "violations": violations,
            "warns": warns,
            "karma": karma,
            "is_muted": is_muted_flag,
            "mute_until": mute_until,
            "level": level,
            "role": role,
            "admin_actions": admin_actions,
            "target_actions": target_actions
        }

# === ДЕЙЛИ ===
async def get_daily_bonus(user_id: int) -> tuple:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT last_claim, streak FROM daily_bonus WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        now = int(time.time())
        day = 86400
        if not result:
            return True, 100, 1
        last_claim, streak = result
        if now - last_claim >= day:
            return True, 100 + (streak * 10), streak + 1
        else:
            return False, 0, streak

async def claim_daily(user_id: int):
    now = int(time.time())
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT streak FROM daily_bonus WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        streak = (result[0] + 1) if result else 1
        await db.execute("INSERT OR REPLACE INTO daily_bonus (user_id, last_claim, streak) VALUES (?, ?, ?)", (user_id, now, streak))
        await db.commit()
    return streak

# === ОПЕРАТОРЫ ===
async def set_channel_operator(channel_id: int, operator_id: int, operator_username: str = "", channel_name: str = ""):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO channel_operators (channel_id, operator_id, operator_username, channel_name) VALUES (?, ?, ?, ?)", (channel_id, operator_id, operator_username, channel_name))
        await db.commit()

async def get_channel_operator(channel_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT operator_id, operator_username, channel_name FROM channel_operators WHERE channel_id = ?", (channel_id,))
        result = await cursor.fetchone()
        if result:
            return {"operator_id": result[0], "operator_username": result[1], "channel_name": result[2]}
        return None

async def remove_channel_operator(channel_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM channel_operators WHERE channel_id = ?", (channel_id,))
        await db.commit()

async def get_all_channel_operators() -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT channel_id, operator_id, operator_username, channel_name FROM channel_operators")
        return await cursor.fetchall()

# === ВЛАДЕЛЬЦЫ ===
async def set_channel_owner(channel_id: int, owner_id: int, owner_username: str = ""):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO channel_owners (channel_id, owner_id, owner_username) VALUES (?, ?, ?)", (channel_id, owner_id, owner_username))
        await db.commit()

async def get_channel_owner(channel_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT owner_id, owner_username FROM channel_owners WHERE channel_id = ?", (channel_id,))
        result = await cursor.fetchone()
        if result:
            return {"owner_id": result[0], "owner_username": result[1]}
        return None

# === БЕЛЫЙ СПИСОК ===
async def add_whitelist_domain(domain: str, added_by: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO whitelist (domain, added_by) VALUES (?, ?)", (domain, added_by))
        await db.commit()

async def remove_whitelist_domain(domain: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM whitelist WHERE domain = ?", (domain,))
        await db.commit()

async def get_whitelist_domains() -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT domain FROM whitelist ORDER BY domain")
        return [row[0] for row in await cursor.fetchall()]

async def is_domain_whitelisted(domain: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT 1 FROM whitelist WHERE domain = ?", (domain,))
        return await cursor.fetchone() is not None

# === НАСТРОЙКИ ===
async def get_channel_settings(channel_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT enabled, mute_duration, warn_limit, block_new_accounts, min_account_age, log_enabled FROM channel_settings WHERE channel_id = ?", (channel_id,))
        result = await cursor.fetchone()
        if result:
            return {
                "enabled": bool(result[0]),
                "mute_duration": result[1],
                "warn_limit": result[2],
                "block_new_accounts": bool(result[3]),
                "min_account_age": result[4],
                "log_enabled": bool(result[5])
            }
        return {
            "enabled": True,
            "mute_duration": 300,
            "warn_limit": 3,
            "block_new_accounts": True,
            "min_account_age": 86400,
            "log_enabled": True
        }

async def update_channel_settings(channel_id: int, settings: dict):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """INSERT OR REPLACE INTO channel_settings 
               (channel_id, enabled, mute_duration, warn_limit, block_new_accounts, min_account_age, log_enabled) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                channel_id,
                settings.get("enabled", 1),
                settings.get("mute_duration", 300),
                settings.get("warn_limit", 3),
                settings.get("block_new_accounts", 1),
                settings.get("min_account_age", 86400),
                settings.get("log_enabled", 1)
            )
        )
        await db.commit()
