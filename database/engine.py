import aiosqlite
import logging
from contextlib import asynccontextmanager
from config import DB_PATH

logger = logging.getLogger(__name__)


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            PRAGMA journal_mode=WAL;

            -- ── Пользователи ──────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY,
                username     TEXT,
                balance      INTEGER DEFAULT 2,
                is_banned    INTEGER DEFAULT 0,
                ban_until    TIMESTAMP,
                is_verified  INTEGER DEFAULT 0,
                threads_username TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Уникальные публичные ID заявок (1-9999)
            CREATE TABLE IF NOT EXISTS submission_ids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id INTEGER UNIQUE NOT NULL
            );

            -- ── Заявки (творческие работы) ────────────────────────────────
            CREATE TABLE IF NOT EXISTS submissions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id        INTEGER UNIQUE,
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

            -- ── Задания Pull ──────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id      INTEGER NOT NULL,
                task_type       TEXT NOT NULL,
                target_url      TEXT NOT NULL,
                description     TEXT,
                total_slots     INTEGER DEFAULT 1,
                remaining_slots INTEGER DEFAULT 1,
                cost_per_slot   INTEGER NOT NULL,
                reward_per_slot INTEGER NOT NULL,
                status          TEXT DEFAULT 'active',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (creator_id) REFERENCES users(id)
            );

            -- Тексты комментариев (один на слот)
            CREATE TABLE IF NOT EXISTS task_comment_texts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id   INTEGER NOT NULL,
                slot_num  INTEGER NOT NULL,
                text      TEXT NOT NULL,
                used      INTEGER DEFAULT 0,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );

            -- ── Исполнения заданий ────────────────────────────────────────
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

            -- ── Анти-дубль взаимодействий ─────────────────────────────────
            CREATE TABLE IF NOT EXISTS interactions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id       INTEGER NOT NULL,
                executor_id      INTEGER NOT NULL,
                interaction_type TEXT NOT NULL,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(creator_id, executor_id, interaction_type)
            );

            -- ── Кулдауны ──────────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS cooldowns (
                user_id     INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                last_action TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, action_type)
            );

            -- ── Дневные лимиты ────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS daily_limits (
                user_id       INTEGER NOT NULL,
                date          TEXT NOT NULL,
                like_count    INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                repost_count  INTEGER DEFAULT 0,
                follow_count  INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            );

            -- ── Верификация ───────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS verifications (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL UNIQUE,
                threads_username TEXT,
                status           TEXT DEFAULT 'pending',
                submitted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at      TIMESTAMP,
                reviewer_id      INTEGER
            );

            -- ── Карточки контента ─────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS cards (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id   INTEGER UNIQUE NOT NULL,
                author_id   INTEGER,
                file_id     TEXT,
                file_type   TEXT,
                description TEXT,
                category    TEXT,
                emoji       TEXT,
                post_url    TEXT,
                rating      INTEGER DEFAULT 0,
                is_priority INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'active',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (author_id) REFERENCES artists(id)
            );

            -- Голоса за карточки
            CREATE TABLE IF NOT EXISTS card_votes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id   INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                vote      INTEGER NOT NULL,
                voted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(card_id, user_id),
                FOREIGN KEY (card_id) REFERENCES cards(id)
            );

            -- Жалобы на карточки
            CREATE TABLE IF NOT EXISTS card_reports (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id    INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                reason     TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (card_id) REFERENCES cards(id)
            );

            -- ── Авторы ────────────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS artists (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER UNIQUE,
                artist_id    INTEGER UNIQUE NOT NULL,
                display_id   TEXT,
                link         TEXT,
                tg_username  TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.commit()

        # Миграция: добавляем новые колонки если их нет
        for col, typedef in [
            ("display_id",  "TEXT"),
            ("link",        "TEXT"),
            ("tg_username", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE artists ADD COLUMN {col} {typedef}")
                await db.commit()
                logger.info("Migrated artists: added column %s", col)
            except Exception:
                pass

        # Миграция card_reports — добавляем reason
        try:
            await db.execute("ALTER TABLE card_reports ADD COLUMN reason TEXT")
            await db.commit()
        except Exception:
            pass

    logger.info("Database initialised")


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db
