import aiosqlite
import logging
from contextlib import asynccontextmanager
from config import DB_PATH

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Создаёт все таблицы при старте."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY,
                username   TEXT,
                balance    INTEGER DEFAULT 2,
                is_banned  INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                content_type     TEXT NOT NULL,
                content          TEXT,
                file_id          TEXT,
                description      TEXT,
                original_link    TEXT,
                publication_mode TEXT NOT NULL,
                status           TEXT DEFAULT 'pending',
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id      INTEGER NOT NULL,
                task_type       TEXT NOT NULL,
                target_url      TEXT NOT NULL,
                description     TEXT,
                comment_text    TEXT,
                total_slots     INTEGER DEFAULT 1,
                remaining_slots INTEGER DEFAULT 1,
                cost_per_slot   INTEGER NOT NULL,
                reward_per_slot INTEGER NOT NULL,
                status          TEXT DEFAULT 'active',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (creator_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS task_executions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id        INTEGER NOT NULL,
                executor_id    INTEGER NOT NULL,
                target_account TEXT,
                status         TEXT DEFAULT 'pending',
                admin_msg_id   INTEGER,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id),
                FOREIGN KEY (executor_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS interactions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id       INTEGER NOT NULL,
                executor_id      INTEGER NOT NULL,
                interaction_type TEXT NOT NULL,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(creator_id, executor_id, interaction_type)
            );

            CREATE TABLE IF NOT EXISTS cooldowns (
                user_id     INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                last_action TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, action_type)
            );

            CREATE TABLE IF NOT EXISTS daily_limits (
                user_id       INTEGER NOT NULL,
                date          TEXT NOT NULL,
                like_count    INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                repost_count  INTEGER DEFAULT 0,
                follow_count  INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            );
        """)
        await db.commit()
    logger.info("Database initialised")


@asynccontextmanager
async def get_db():
    """Контекстный менеджер для подключения к БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db
