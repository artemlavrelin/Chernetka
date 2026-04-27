import logging
from typing import Optional
from database.engine import get_db
from config import STARTING_BALANCE

logger = logging.getLogger(__name__)


async def get_or_create_user(user_id: int, username: Optional[str]) -> dict:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            if row["username"] != username:
                await db.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
                await db.commit()
            return dict(row)
        await db.execute(
            "INSERT INTO users (id, username, balance) VALUES (?, ?, ?)",
            (user_id, username, STARTING_BALANCE)
        )
        await db.commit()
    return {"id": user_id, "username": username, "balance": STARTING_BALANCE,
            "is_banned": 0, "ban_until": None, "is_verified": 0, "threads_username": None}


async def get_user(user_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_user_by_username(username: str) -> Optional[dict]:
    uname = username.lstrip("@")
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE username = ?", (uname,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def is_user_banned(user_id: int) -> bool:
    from datetime import datetime, timezone
    user = await get_user(user_id)
    if not user:
        return False
    if user["is_banned"]:
        # Временный бан
        if user["ban_until"]:
            try:
                until = datetime.fromisoformat(user["ban_until"]).replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= until:
                    # Бан истёк — разбаниваем
                    async with get_db() as db:
                        await db.execute(
                            "UPDATE users SET is_banned = 0, ban_until = NULL WHERE id = ?",
                            (user_id,)
                        )
                        await db.commit()
                    return False
            except Exception:
                pass
        return True
    return False


async def get_balance(user_id: int) -> int:
    user = await get_user(user_id)
    return user["balance"] if user else 0


async def add_balance(user_id: int, amount: int) -> int:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id)
        )
        await db.commit()
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    return row["balance"] if row else 0


async def deduct_balance(user_id: int, amount: int) -> bool:
    async with get_db() as db:
        async with db.execute(
            "SELECT balance FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row or row["balance"] < amount:
            return False
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?", (amount, user_id)
        )
        await db.commit()
    return True


async def set_balance(user_id: int, amount: int) -> None:
    async with get_db() as db:
        await db.execute("UPDATE users SET balance = ? WHERE id = ?", (amount, user_id))
        await db.commit()


async def ban_user(user_id: int, until_iso: Optional[str] = None) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET is_banned = 1, ban_until = ? WHERE id = ?",
            (until_iso, user_id)
        )
        await db.commit()


async def unban_user(user_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET is_banned = 0, ban_until = NULL WHERE id = ?", (user_id,)
        )
        await db.commit()


async def set_verified(user_id: int, threads_username: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET is_verified = 1, threads_username = ? WHERE id = ?",
            (threads_username, user_id)
        )
        await db.commit()


async def unset_verified(user_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET is_verified = 0, threads_username = NULL WHERE id = ?",
            (user_id,)
        )
        await db.commit()


async def get_top_balances(limit: int = 10) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT id, username, balance FROM users WHERE is_banned = 0 "
            "ORDER BY balance DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_all_user_ids() -> list[int]:
    async with get_db() as db:
        async with db.execute("SELECT id FROM users WHERE is_banned = 0") as cur:
            rows = await cur.fetchall()
    return [r["id"] for r in rows]


async def daily_balance_topup() -> int:
    async with get_db() as db:
        cur = await db.execute(
            "UPDATE users SET balance = 1 WHERE balance < 1 AND is_banned = 0"
        )
        await db.commit()
    return cur.rowcount


async def get_verified_count() -> int:
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE is_verified = 1"
        ) as cur:
            row = await cur.fetchone()
    return row["cnt"] if row else 0
