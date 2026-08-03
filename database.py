import aiosqlite
import time
from config import ADMIN_IDS

DB_NAME = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Проверяем, есть ли колонка level в таблице roles
        cursor = await db.execute("PRAGMA table_info(roles)")
        columns = await cursor.fetchall()
        has_level = any(col[1] == 'level' for col in columns)
        
        if not has_level:
            # Удаляем старую таблицу
            await db.execute("DROP TABLE IF EXISTS roles")
            await db.commit()
            print("✅ Старая таблица roles удалена (не было колонки level)")
        
        # Таблица варнов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                reason TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица мутов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id INTEGER PRIMARY KEY,
                until INTEGER
            )
        """)
        
        # Таблица ролей (с колонкой level)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                user_id INTEGER PRIMARY KEY,
                level INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user'
            )
        """)
        
        # Таблица операторов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_operators (
                channel_id INTEGER PRIMARY KEY,
                operator_id INTEGER,
                operator_username TEXT,
                channel_name TEXT,
                set_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Daily бонусы
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_bonus (
                user_id INTEGER PRIMARY KEY,
                last_claim INTEGER,
                streak INTEGER DEFAULT 0
            )
        """)
        
        # Карма
        await db.execute("""
            CREATE TABLE IF NOT EXISTS karma (
                user_id INTEGER PRIMARY KEY,
                karma INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0
            )
        """)
        
        # Статистика нарушений
        await db.execute("""
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                type TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Голосования
        await db.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                creator_id INTEGER,
                question TEXT,
                options TEXT,
                votes TEXT,
                is_active INTEGER DEFAULT 1,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Белый список
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT UNIQUE,
                added_by INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Главы каналов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_owners (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                owner_username TEXT,
                set_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.commit()
    
    # Добавляем дефолтные домены
    from config import WHITELIST_DOMAINS
    async with aiosqlite.connect(DB_NAME) as db:
        for domain in WHITELIST_DOMAINS:
            try:
                await db.execute("INSERT OR IGNORE INTO whitelist (domain, added_by) VALUES (?, ?)", (domain, 0))
            except:
                pass
        await db.commit()
    
    print("✅ База данных инициализирована")

# === ОСТАЛЬНЫЕ ФУНКЦИИ (без изменений) ===
async def add_warning(user_id, chat_id, reason):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO warnings (user_id, chat_id, reason) VALUES (?, ?, ?)", (user_id, chat_id, reason))
        await db.commit()

async def get_warnings(user_id, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        result = await cursor.fetchone()
        return result[0] if result else 0

async def clear_warnings(user_id, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM warnings WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        await db.commit()

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

async def set_user_level(user_id: int, level: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO roles (user_id, level, role) VALUES (?, ?, ?)",
            (user_id, level, f"admin_{level}" if level > 0 else "user")
        )
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

async def has_permission(user_id: int, permission: str) -> bool:
    level = await get_user_level(user_id)
    from config import ADMIN_LEVELS
    if level == 0:
        return False
    if level in ADMIN_LEVELS:
        perms = ADMIN_LEVELS[level]["permissions"]
        if "all" in perms:
            return True
        return permission in perms
    return False

async def is_moderator(user_id: int) -> bool:
    level = await get_user_level(user_id)
    return level >= 2

async def is_admin(user_id: int) -> bool:
    level = await get_user_level(user_id)
    return level >= 6

# === DAILY BONUS ===
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
        await db.execute(
            "INSERT OR REPLACE INTO daily_bonus (user_id, last_claim, streak) VALUES (?, ?, ?)",
            (user_id, now, streak)
        )
        await db.commit()
    return streak

# === КАРМА ===
async def add_karma(user_id: int, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO karma (user_id, karma) VALUES (?, COALESCE((SELECT karma FROM karma WHERE user_id = ?), 0) + ?)",
            (user_id, user_id, amount)
        )
        await db.commit()

async def get_karma(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT karma FROM karma WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

# === СТАТИСТИКА ===
async def add_violation(user_id: int, chat_id: int, type: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO violations (user_id, chat_id, type) VALUES (?, ?, ?)",
            (user_id, chat_id, type)
        )
        await db.commit()

async def get_violations_stats(chat_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT user_id, COUNT(*) as count FROM violations WHERE chat_id = ? GROUP BY user_id ORDER BY count DESC LIMIT ?",
            (chat_id, limit)
        )
        return await cursor.fetchall()

# === ОПРОСЫ ===
async def create_poll(chat_id: int, creator_id: int, question: str, options: list):
    import json
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO polls (chat_id, creator_id, question, options, votes) VALUES (?, ?, ?, ?, ?)",
            (chat_id, creator_id, question, json.dumps(options), json.dumps({}))
        )
        poll_id = cursor.lastrowid
        await db.commit()
        return poll_id

async def get_poll(poll_id: int):
    import json
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, chat_id, creator_id, question, options, votes, is_active FROM polls WHERE id = ?",
            (poll_id,)
        )
        result = await cursor.fetchone()
        if result:
            return {
                "id": result[0],
                "chat_id": result[1],
                "creator_id": result[2],
                "question": result[3],
                "options": json.loads(result[4]),
                "votes": json.loads(result[5]),
                "is_active": bool(result[6])
            }
        return None

async def vote_poll(poll_id: int, user_id: int, option_index: int):
    import json
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT votes, options FROM polls WHERE id = ?", (poll_id,))
        result = await cursor.fetchone()
        if not result:
            return False
        votes = json.loads(result[0])
        options = json.loads(result[1])
        if str(user_id) in votes:
            return False
        if option_index < 0 or option_index >= len(options):
            return False
        votes[str(user_id)] = option_index
        await db.execute(
            "UPDATE polls SET votes = ? WHERE id = ?",
            (json.dumps(votes), poll_id)
        )
        await db.commit()
        return True

async def close_poll(poll_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE polls SET is_active = 0 WHERE id = ?", (poll_id,))
        await db.commit()

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

# === ГЛАВЫ КАНАЛОВ ===
async def set_channel_owner(channel_id: int, owner_id: int, owner_username: str = ""):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channel_owners (channel_id, owner_id, owner_username) VALUES (?, ?, ?)",
            (channel_id, owner_id, owner_username)
        )
        await db.commit()

async def get_channel_owner(channel_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT owner_id, owner_username FROM channel_owners WHERE channel_id = ?",
            (channel_id,)
        )
        result = await cursor.fetchone()
        if result:
            return {"owner_id": result[0], "owner_username": result[1]}
        return None

# === ОПЕРАТОРЫ ===
async def set_channel_operator(channel_id: int, operator_id: int, operator_username: str = "", channel_name: str = ""):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channel_operators (channel_id, operator_id, operator_username, channel_name) VALUES (?, ?, ?, ?)",
            (channel_id, operator_id, operator_username, channel_name)
        )
        await db.commit()

async def get_channel_operator(channel_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT operator_id, operator_username, channel_name FROM channel_operators WHERE channel_id = ?",
            (channel_id,)
        )
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
