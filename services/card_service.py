import logging
import random
from typing import Optional
from database.engine import get_db
from config import CARD_EMOJIS

logger = logging.getLogger(__name__)


# ── Авторы ──────────────────────────────────────────────────────────────────

async def add_artist(
    user_id: int,
    link: Optional[str] = None,
    display_id: Optional[str] = None,
    tg_username: Optional[str] = None,
) -> dict:
    """
    Создаёт артиста с уникальным числовым artist_id (1-9999).
    display_id — произвольный текстовый ID (напр. '#id1727').
    Возвращает полную запись dict.
    """
    async with get_db() as db:
        for _ in range(200):
            aid = random.randint(1, 9999)
            try:
                await db.execute(
                    """INSERT INTO artists (user_id, artist_id, display_id, link, tg_username)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, aid, display_id, link, tg_username)
                )
                await db.commit()
                async with db.execute(
                    "SELECT * FROM artists WHERE user_id = ?", (user_id,)
                ) as cur:
                    row = await cur.fetchone()
                return dict(row)
            except Exception:
                continue
    raise RuntimeError("Не удалось сгенерировать artist_id")


async def get_artist_by_user(user_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM artists WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_artist_by_id(artist_id: int) -> Optional[dict]:
    """Поиск по числовому artist_id (внутренний уникальный номер)."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM artists WHERE artist_id = ?", (artist_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_artist_by_db_id(db_id: int) -> Optional[dict]:
    """Поиск по первичному ключу artists.id."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM artists WHERE id = ?", (db_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def update_artist_fields(
    user_id: int,
    link: Optional[str]       = None,
    display_id: Optional[str] = None,
    tg_username: Optional[str]= None,
    clear_link: bool          = False,
    clear_display_id: bool    = False,
    clear_tg_username: bool   = False,
) -> Optional[dict]:
    """
    Обновляет указанные поля артиста.
    Если передан clear_* = True, поле обнуляется.
    """
    updates = []
    values  = []
    if link is not None:
        updates.append("link = ?");        values.append(link)
    elif clear_link:
        updates.append("link = NULL")
    if display_id is not None:
        updates.append("display_id = ?"); values.append(display_id)
    elif clear_display_id:
        updates.append("display_id = NULL")
    if tg_username is not None:
        updates.append("tg_username = ?"); values.append(tg_username)
    elif clear_tg_username:
        updates.append("tg_username = NULL")

    if not updates:
        return await get_artist_by_user(user_id)

    values.append(user_id)
    async with get_db() as db:
        await db.execute(
            f"UPDATE artists SET {', '.join(updates)} WHERE user_id = ?",
            values,
        )
        await db.commit()
    return await get_artist_by_user(user_id)


async def change_artist_id(old_id: int, new_id: int) -> bool:
    async with get_db() as db:
        try:
            await db.execute(
                "UPDATE artists SET artist_id = ? WHERE artist_id = ?", (new_id, old_id)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def remove_artist(user_id: int) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM artists WHERE user_id = ?", (user_id,))
        await db.commit()


# ── Карточки ────────────────────────────────────────────────────────────────

async def create_card(
    author_id: Optional[int],
    file_id: Optional[str],
    file_type: Optional[str],
    description: Optional[str],
    category: Optional[str],
    post_url: Optional[str],
) -> tuple[int, int]:
    """Возвращает (card_id, public_id)."""
    emoji = random.choice(CARD_EMOJIS)
    # Генерируем public_id
    async with get_db() as db:
        for _ in range(200):
            pid = random.randint(1, 9999)
            async with db.execute(
                "SELECT 1 FROM cards WHERE public_id = ?", (pid,)
            ) as cur:
                if await cur.fetchone():
                    continue
            cur2 = await db.execute(
                """INSERT INTO cards (public_id, author_id, file_id, file_type, description,
                   category, emoji, post_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (pid, author_id, file_id, file_type, description, category, emoji, post_url)
            )
            await db.commit()
            return cur2.lastrowid, pid
    raise RuntimeError("Не удалось создать карточку")


async def get_card(card_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM cards WHERE id = ?", (card_id,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_active_cards(author_id: Optional[int] = None) -> list[dict]:
    """Возвращает карточки: сначала приоритетные, затем остальные — в случайном порядке."""
    async with get_db() as db:
        if author_id:
            async with db.execute(
                """SELECT * FROM cards WHERE status = 'active' AND author_id = ?
                   ORDER BY is_priority DESC, RANDOM()""",
                (author_id,)
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                """SELECT * FROM cards WHERE status = 'active'
                   ORDER BY is_priority DESC, RANDOM()"""
            ) as cur:
                rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def vote_card(card_id: int, user_id: int, vote: int) -> tuple[bool, int]:
    """
    Голосует за карточку. vote: -3..+3
    Возвращает (success, new_rating).
    Если пользователь уже голосовал — обновляет голос.
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT vote FROM card_votes WHERE card_id = ? AND user_id = ?",
            (card_id, user_id)
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            old_vote = existing["vote"]
            delta = vote - old_vote
            await db.execute(
                "UPDATE card_votes SET vote = ? WHERE card_id = ? AND user_id = ?",
                (vote, card_id, user_id)
            )
        else:
            delta = vote
            await db.execute(
                "INSERT INTO card_votes (card_id, user_id, vote) VALUES (?, ?, ?)",
                (card_id, user_id, vote)
            )

        await db.execute(
            "UPDATE cards SET rating = rating + ? WHERE id = ?", (delta, card_id)
        )
        await db.commit()
        async with db.execute("SELECT rating FROM cards WHERE id = ?", (card_id,)) as cur:
            row = await cur.fetchone()
    return True, (row["rating"] if row else 0)


async def report_card(card_id: int, user_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO card_reports (card_id, user_id) VALUES (?, ?)",
            (card_id, user_id)
        )
        await db.commit()


async def set_priority(card_id: int, priority: bool) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE cards SET is_priority = ? WHERE id = ?", (1 if priority else 0, card_id)
        )
        await db.commit()


async def get_card_stats() -> dict:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) as cnt FROM cards WHERE status = 'active'") as cur:
            total_cards = (await cur.fetchone())["cnt"]
        async with db.execute("SELECT COUNT(*) as cnt FROM artists") as cur:
            total_artists = (await cur.fetchone())["cnt"]
        async with db.execute(
            "SELECT id, public_id, emoji, category, rating FROM cards "
            "WHERE status = 'active' ORDER BY rating DESC LIMIT 5"
        ) as cur:
            top_liked = [dict(r) for r in await cur.fetchall()]
        async with db.execute(
            "SELECT id, public_id, emoji, category, rating FROM cards "
            "WHERE status = 'active' ORDER BY rating ASC LIMIT 5"
        ) as cur:
            top_disliked = [dict(r) for r in await cur.fetchall()]
    return {
        "total_cards": total_cards,
        "total_artists": total_artists,
        "top_liked": top_liked,
        "top_disliked": top_disliked,
    }


async def get_priority_cards() -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM cards WHERE is_priority = 1 AND status = 'active' ORDER BY id"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]
