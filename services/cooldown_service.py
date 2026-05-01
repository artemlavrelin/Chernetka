import logging
from datetime import datetime, timezone
from typing import Optional
from database.engine import get_db
from config import COOLDOWNS, DAILY_LIMITS

logger = logging.getLogger(__name__)


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _format_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}с"
    if seconds < 3600:
        return f"{seconds // 60}м"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}ч {m}м" if m else f"{h}ч"


async def check_cooldown(user_id: int, action_type: str) -> tuple[bool, int]:
    limit_seconds = COOLDOWNS.get(action_type, 0)
    if limit_seconds == 0:
        return True, 0
    async with get_db() as db:
        async with db.execute(
            "SELECT last_action FROM cooldowns WHERE user_id = ? AND action_type = ?",
            (user_id, action_type),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return True, 0
    last = datetime.fromisoformat(row["last_action"]).replace(tzinfo=timezone.utc)
    elapsed = int((datetime.now(timezone.utc) - last).total_seconds())
    remaining = limit_seconds - elapsed
    if remaining <= 0:
        return True, 0
    return False, remaining


async def set_cooldown(user_id: int, action_type: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO cooldowns (user_id, action_type, last_action)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, action_type) DO UPDATE SET last_action = excluded.last_action""",
            (user_id, action_type, now),
        )
        await db.commit()


async def reset_cooldown(user_id: int) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM cooldowns WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_daily_count(user_id: int, action_type: str) -> int:
    today = _utc_today()
    col   = f"{action_type}_count"
    async with get_db() as db:
        async with db.execute(
            f"SELECT {col} FROM daily_limits WHERE user_id = ? AND date = ?",
            (user_id, today),
        ) as cur:
            row = await cur.fetchone()
    return row[col] if row else 0


async def increment_daily_count(user_id: int, action_type: str) -> int:
    today = _utc_today()
    col   = f"{action_type}_count"
    async with get_db() as db:
        await db.execute(
            f"""INSERT INTO daily_limits (user_id, date, {col})
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, date) DO UPDATE SET {col} = {col} + 1""",
            (user_id, today),
        )
        await db.commit()
        async with db.execute(
            f"SELECT {col} FROM daily_limits WHERE user_id = ? AND date = ?",
            (user_id, today),
        ) as cur:
            row = await cur.fetchone()
    return row[col] if row else 1


async def check_daily_limit(user_id: int, action_type: str) -> tuple[bool, int]:
    limit   = DAILY_LIMITS.get(action_type, 9999)
    current = await get_daily_count(user_id, action_type)
    return current < limit, current


async def get_cooldown_status(user_id: int) -> dict:
    today  = _utc_today()
    status = {}
    for action in ["like", "comment", "repost", "follow", "execute", "create", "submission"]:
        ready, remaining = await check_cooldown(user_id, action)
        status[f"{action}_ready"]         = ready
        status[f"{action}_remaining"]     = remaining
        status[f"{action}_remaining_str"] = _format_time(remaining) if not ready else "✅"

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM daily_limits WHERE user_id = ? AND date = ?",
            (user_id, today),
        ) as cur:
            row = await cur.fetchone()

    status["like_today"]    = row["like_count"]    if row else 0
    status["comment_today"] = row["comment_count"] if row else 0
    status["repost_today"]  = row["repost_count"]  if row else 0
    status["follow_today"]  = row["follow_count"]  if row else 0
    return status
