import logging
from typing import Optional
from datetime import datetime, timezone
from database.engine import get_db

logger = logging.getLogger(__name__)


async def submit_verification(user_id: int, threads_username: str) -> int:
    """Создаёт заявку на верификацию. Возвращает id записи."""
    threads_username = threads_username.lstrip("@")
    async with get_db() as db:
        # Upsert — если уже есть pending, обновляем
        await db.execute(
            """INSERT INTO verifications (user_id, threads_username, status)
               VALUES (?, ?, 'pending')
               ON CONFLICT(user_id) DO UPDATE SET
                 threads_username = excluded.threads_username,
                 status = 'pending',
                 submitted_at = CURRENT_TIMESTAMP""",
            (user_id, threads_username)
        )
        await db.commit()
        async with db.execute(
            "SELECT id FROM verifications WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return row["id"] if row else 0


async def get_verification(user_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM verifications WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def approve_verification(user_id: int, reviewer_id: int) -> Optional[str]:
    """Одобряет верификацию. Возвращает threads_username."""
    from services.user_service import set_verified
    from services.cooldown_service import reset_cooldown
    async with get_db() as db:
        async with db.execute(
            "SELECT threads_username FROM verifications WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        threads_uname = row["threads_username"]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """UPDATE verifications SET status = 'approved', reviewed_at = ?, reviewer_id = ?
               WHERE user_id = ?""",
            (now, reviewer_id, user_id)
        )
        await db.commit()
    await set_verified(user_id, threads_uname)
    await reset_cooldown(user_id)
    return threads_uname


async def reject_verification(user_id: int, reviewer_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            """UPDATE verifications SET status = 'rejected', reviewed_at = ?, reviewer_id = ?
               WHERE user_id = ?""",
            (now, reviewer_id, user_id)
        )
        await db.commit()


async def get_verified_count() -> int:
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM verifications WHERE status = 'approved'"
        ) as cur:
            row = await cur.fetchone()
    return row["cnt"] if row else 0
