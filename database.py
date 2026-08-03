import aiosqlite
import time
from config import ADMIN_IDS

DB_NAME = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
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
        
        # Таблица ролей (глобальные)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                user_id INTEGER PRIMARY KEY,
                level INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user'
            )
        """)
        
        # === НОВАЯ ТАБЛИЦА: ОПЕРАТОРЫ КАНАЛОВ ===
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_operators (
                channel_id INTEGER PRIMARY KEY,
                operator_id INTEGER,
                operator_username TEXT,
                channel_name TEXT,
                set_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.commit()

# === ВАРНЫ ===
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

# === РОЛИ ===
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

# === ОПЕРАТОРЫ КАНАЛОВ ===
async def set_channel_operator(channel_id: int, operator_id: int, operator_username: str = "", channel_name: str = ""):
    """Назначает оператора для канала"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channel_operators (channel_id, operator_id, operator_username, channel_name) VALUES (?, ?, ?, ?)",
            (channel_id, operator_id, operator_username, channel_name)
        )
        await db.commit()

async def get_channel_operator(channel_id: int) -> dict:
    """Получает оператора канала"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT operator_id, operator_username, channel_name FROM channel_operators WHERE channel_id = ?",
            (channel_id,)
        )
        result = await cursor.fetchone()
        if result:
            return {
                "operator_id": result[0],
                "operator_username": result[1],
                "channel_name": result[2]
            }
        return None

async def remove_channel_operator(channel_id: int):
    """Удаляет оператора канала"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM channel_operators WHERE channel_id = ?", (channel_id,))
        await db.commit()

async def get_all_channel_operators() -> list:
    """Получает список всех операторов"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT channel_id, operator_id, operator_username, channel_name FROM channel_operators")
        return await cursor.fetchall()