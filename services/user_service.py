import logging
from typing import Optional
from database.engine import get_db
from config import STARTING_BALANCE

logger = logging.getLogger(__name__)


async def get_or_create_user(user_id: int, username: Optional[str]) -> dict:
    async with get_db() as db:
        async with db.execute(
            "SELECT id, username, balance, is_banned FROM users WHERE id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            # Обновляем username если изменился
            if row["username"] != username:
                await db.execute(
                    "UPDATE users SET username = ? WHERE id = ?",
                    (username, user_id)
                )
                await db.commit()
            return dict(row)

        # Новый пользователь
        await db.execute(
            "INSERT INTO users (id, username, balance) VALUES (?, ?, ?)",
            (user_id, username, STARTING_BALANCE)
        )
        await db.commit()
        logger.info("New user registered: %s (@%s)", user_id, username)
        return {"id": user_id, "username": username, "balance": STARTING_BALANCE, "is_banned": 0}


async def get_user(user_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT id, username, balance, is_banned FROM users WHERE id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def get_user_by_username(username: str) -> Optional[dict]:
    uname = username.lstrip("@")
    async with get_db() as db:
        async with db.execute(
            "SELECT id, username, balance, is_banned FROM users WHERE username = ?",
            (uname,)
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def is_user_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    return bool(user and user["is_banned"])


async def get_balance(user_id: int) -> int:
    user = await get_user(user_id)
    return user["balance"] if user else 0


async def add_balance(user_id: int, amount: int) -> int:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?",
            (amount, user_id)
        )
        await db.commit()
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    return row["balance"] if row else 0


async def deduct_balance(user_id: int, amount: int) -> bool:
    """Списывает amount со счёта. Возвращает False если недостаточно средств."""
    async with get_db() as db:
        async with db.execute(
            "SELECT balance FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row or row["balance"] < amount:
            return False
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?",
            (amount, user_id)
        )
        await db.commit()
    return True


async def set_balance(user_id: int, amount: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET balance = ? WHERE id = ?",
            (amount, user_id)
        )
        await db.commit()


async def ban_user(user_id: int) -> None:
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE id = ?", (user_id,))
        await db.commit()


async def unban_user(user_id: int) -> None:
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE id = ?", (user_id,))
        await db.commit()


async def get_top_balances(limit: int = 10) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT id, username, balance FROM users WHERE is_banned = 0 "
            "ORDER BY balance DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_all_user_ids() -> list[int]:
    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM users WHERE is_banned = 0"
        ) as cursor:
            rows = await cursor.fetchall()
    return [r["id"] for r in rows]


async def daily_balance_topup() -> int:
    """Поднимает баланс до 1🌟 всем у кого < 1. Возвращает кол-во затронутых пользователей."""
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE users SET balance = 1 WHERE balance < 1 AND is_banned = 0"
        )
        await db.commit()
    return cursor.rowcount
