import logging
import random
from typing import Optional
from database.engine import get_db
from config import TASK_CONFIG

logger = logging.getLogger(__name__)


# ── Уникальный публичный ID (1-9999) ───────────────────────────────────────

async def generate_public_id(table: str = "submission_ids") -> int:
    """Генерирует уникальный ID 1-9999 для submissions или cards."""
    async with get_db() as db:
        for _ in range(200):
            pid = random.randint(1, 9999)
            try:
                await db.execute(
                    f"INSERT INTO {table} (public_id) VALUES (?)", (pid,)
                )
                await db.commit()
                return pid
            except Exception:
                continue
    raise RuntimeError(f"Не удалось сгенерировать unique public_id для {table}")


# ── Submissions ─────────────────────────────────────────────────────────────

async def create_submission(
    user_id: int, content_type: str, content: Optional[str],
    file_id: Optional[str], description: Optional[str],
    original_link: Optional[str], publication_mode: str,
) -> tuple[int, int]:
    """Возвращает (submission_id, public_id)."""
    public_id = await generate_public_id("submission_ids")
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO submissions
               (public_id, user_id, content_type, content, file_id,
                description, original_link, publication_mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (public_id, user_id, content_type, content, file_id,
             description, original_link, publication_mode),
        )
        await db.commit()
    return cur.lastrowid, public_id


async def get_submission(submission_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM submissions WHERE id = ?", (submission_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


# ── Tasks ───────────────────────────────────────────────────────────────────

async def create_task(
    creator_id: int, task_type: str, target_url: str,
    description: Optional[str], total_slots: int,
    comment_texts: Optional[list[str]] = None,
) -> int:
    cfg = TASK_CONFIG[task_type]
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO tasks
               (creator_id, task_type, target_url, description,
                total_slots, remaining_slots, cost_per_slot, reward_per_slot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (creator_id, task_type, target_url, description,
             total_slots, total_slots, cfg["cost"], cfg["reward"]),
        )
        task_id = cur.lastrowid
        # Сохраняем тексты комментариев
        if comment_texts:
            for i, text in enumerate(comment_texts, 1):
                await db.execute(
                    "INSERT INTO task_comment_texts (task_id, slot_num, text) VALUES (?, ?, ?)",
                    (task_id, i, text),
                )
        await db.commit()
    return task_id


async def get_task(task_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_available_tasks(user_id: int) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT t.* FROM tasks t
            WHERE t.status = 'active'
              AND t.remaining_slots > 0
              AND t.creator_id != ?
              AND NOT EXISTS (
                  SELECT 1 FROM interactions i
                  WHERE i.creator_id = t.creator_id
                    AND i.executor_id = ?
                    AND i.interaction_type = t.task_type
              )
              AND NOT EXISTS (
                  SELECT 1 FROM task_executions te
                  WHERE te.task_id = t.id
                    AND te.executor_id = ?
                    AND te.status IN ('pending', 'approved')
              )
            ORDER BY t.created_at ASC
            """,
            (user_id, user_id, user_id),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_user_active_tasks(user_id: int) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM tasks WHERE creator_id = ? AND status = 'active' ORDER BY created_at DESC",
            (user_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def cancel_task(task_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE tasks SET status = 'cancelled' WHERE id = ?", (task_id,)
        )
        await db.commit()


async def clear_all_tasks() -> int:
    async with get_db() as db:
        cur = await db.execute(
            "UPDATE tasks SET status = 'cancelled' WHERE status = 'active'"
        )
        await db.commit()
    return cur.rowcount


# ── Получить уникальный текст комментария для исполнителя ──────────────────

async def pop_comment_text(task_id: int) -> Optional[str]:
    """Берёт первый неиспользованный текст комментария и помечает его как used."""
    async with get_db() as db:
        async with db.execute(
            "SELECT id, text FROM task_comment_texts WHERE task_id = ? AND used = 0 "
            "ORDER BY slot_num LIMIT 1",
            (task_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        await db.execute(
            "UPDATE task_comment_texts SET used = 1 WHERE id = ?", (row["id"],)
        )
        await db.commit()
    return row["text"]


# ── Task Executions ─────────────────────────────────────────────────────────

async def create_execution(task_id: int, executor_id: int, target_account: str) -> int:
    async with get_db() as db:
        await db.execute(
            "UPDATE tasks SET remaining_slots = remaining_slots - 1 WHERE id = ?", (task_id,)
        )
        cur = await db.execute(
            "INSERT INTO task_executions (task_id, executor_id, target_account) VALUES (?, ?, ?)",
            (task_id, executor_id, target_account),
        )
        await db.commit()
    return cur.lastrowid


async def set_execution_admin_msg(execution_id: int, msg_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE task_executions SET admin_msg_id = ? WHERE id = ?", (msg_id, execution_id)
        )
        await db.commit()


async def get_execution(execution_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM task_executions WHERE id = ?", (execution_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_execution_count(task_id: int) -> tuple[int, int]:
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM task_executions WHERE task_id = ? AND status = 'approved'",
            (task_id,)
        ) as cur:
            approved = (await cur.fetchone())["cnt"]
        async with db.execute("SELECT total_slots FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
    total = row["total_slots"] if row else 0
    return approved + 1, total


async def approve_execution(execution_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            """SELECT te.*, t.task_type, t.creator_id, t.reward_per_slot, t.id as tid
               FROM task_executions te
               JOIN tasks t ON te.task_id = t.id
               WHERE te.id = ? AND te.status = 'pending'""",
            (execution_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        data = dict(row)
        await db.execute(
            "UPDATE task_executions SET status = 'approved' WHERE id = ?", (execution_id,)
        )
        await db.execute(
            "UPDATE tasks SET status = 'completed' WHERE id = ? AND remaining_slots <= 0",
            (data["tid"],)
        )
        await db.commit()
    await record_interaction(data["creator_id"], data["executor_id"], data["task_type"])
    return data


async def reject_execution(execution_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            """SELECT te.*, t.task_type, t.creator_id, t.cost_per_slot, t.id as tid
               FROM task_executions te
               JOIN tasks t ON te.task_id = t.id
               WHERE te.id = ? AND te.status = 'pending'""",
            (execution_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        data = dict(row)
        await db.execute(
            "UPDATE task_executions SET status = 'rejected' WHERE id = ?", (execution_id,)
        )
        await db.execute(
            "UPDATE tasks SET remaining_slots = remaining_slots + 1 WHERE id = ?", (data["tid"],)
        )
        await db.commit()
    return data


# ── Interactions ────────────────────────────────────────────────────────────

async def has_interaction(creator_id: int, executor_id: int, interaction_type: str) -> bool:
    async with get_db() as db:
        async with db.execute(
            "SELECT 1 FROM interactions WHERE creator_id = ? AND executor_id = ? AND interaction_type = ?",
            (creator_id, executor_id, interaction_type)
        ) as cur:
            return await cur.fetchone() is not None


async def record_interaction(creator_id: int, executor_id: int, interaction_type: str) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO interactions (creator_id, executor_id, interaction_type) VALUES (?, ?, ?)",
            (creator_id, executor_id, interaction_type)
        )
        await db.commit()
