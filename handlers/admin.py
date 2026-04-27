import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from states import AdminStates
import config as cfg
from services.user_service import (
    get_user, get_user_by_username, ban_user, unban_user,
    get_top_balances, add_balance, get_all_user_ids,
)
from services.task_service import get_task, cancel_task, create_task, clear_all_tasks
from services.cooldown_service import reset_cooldown
from config import ADMIN_GROUP_ID, TASK_CONFIG

router = Router()
logger = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

async def _resolve_user(identifier: str):
    identifier = identifier.strip().lstrip("@")
    if identifier.isdigit():
        return await get_user(int(identifier))
    return await get_user_by_username(identifier)


def _admin_only(message: Message) -> bool:
    return message.chat.id == ADMIN_GROUP_ID


# ── /ban ─────────────────────────────────────────────────────────────────────

@router.message(Command("ban"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_ban(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        # Показываем список забаненных
        async with __import__('aiosqlite').connect(cfg.DB_PATH) as db:
            db.row_factory = __import__('aiosqlite').Row
            async with db.execute(
                "SELECT id, username FROM users WHERE is_banned = 1 LIMIT 20"
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await message.reply("Забаненных пользователей нет.")
            return
        lines = "\n".join(
            f"  {r['id']} (@{r['username'] or '—'})" for r in rows
        )
        await message.reply(f"🚫 ЗАБЛОКИРОВАННЫЕ:\n{lines}")
        return
    user = await _resolve_user(args[1])
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    await ban_user(user["id"])
    uname = f"@{user['username']}" if user.get("username") else str(user["id"])
    await message.reply(f"🚫 {uname} заблокирован.")
    logger.info("Admin %s banned %s", message.from_user.id, user["id"])


@router.message(F.text.regexp(r"^/bantime\s+\S+\s+\d+$"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_bantime(message: Message):
    parts = message.text.split(maxsplit=2)
    user = await _resolve_user(parts[1])
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    minutes = int(parts[2])
    until = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    await ban_user(user["id"], until_iso=until)
    uname = f"@{user['username']}" if user.get("username") else str(user["id"])
    await message.reply(f"⏱ {uname} заблокирован на {minutes} минут.")


@router.message(Command("unban"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_unban(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Использование: /unban <id/@username>")
        return
    user = await _resolve_user(args[1])
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    await unban_user(user["id"])
    uname = f"@{user['username']}" if user.get("username") else str(user["id"])
    await message.reply(f"✅ {uname} разблокирован.")


# ── /balancecheck ─────────────────────────────────────────────────────────────

@router.message(Command("balancecheck"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_balancecheck(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        top = await get_top_balances(10)
        if not top:
            await message.reply("Пользователей нет.")
            return
        lines = [f"🌟 ТОП-10 БАЛАНСОВ\n"]
        for i, u in enumerate(top, 1):
            un = f"@{u['username']}" if u.get("username") else str(u["id"])
            lines.append(f"{i}. {un} — {u['balance']}🌟")
        await message.reply("\n".join(lines))
        return
    user = await _resolve_user(args[1])
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    un = f"@{user['username']}" if user.get("username") else str(user["id"])
    await message.reply(
        f"👤 {un}\nID: {user['id']}\n"
        f"Balance: {user['balance']}🌟\n"
        f"Бан: {'Да' if user['is_banned'] else 'Нет'}\n"
        f"Верификация: {'✅' if user.get('is_verified') else '❌'}"
    )


# ── /balancechange ────────────────────────────────────────────────────────────

@router.message(Command("balancechange"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_balancechange(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("Использование: /balancechange <id/@username> <±amount>")
        return
    user = await _resolve_user(parts[1])
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    try:
        amount = int(parts[2])
    except ValueError:
        await message.reply("❗ Сумма должна быть числом.")
        return
    new_bal = await add_balance(user["id"], amount)
    un = f"@{user['username']}" if user.get("username") else str(user["id"])
    sign = "+" if amount >= 0 else ""
    await message.reply(f"✅ {un}: {sign}{amount}🌟 → Balance: {new_bal}🌟")
    logger.info("Admin %s changed balance of %s by %s", message.from_user.id, user["id"], amount)


# ── /removecoldown ────────────────────────────────────────────────────────────

@router.message(Command("removecoldown"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_removecooldown(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Использование: /removecoldown <id/@username>")
        return
    user = await _resolve_user(args[1])
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    await reset_cooldown(user["id"])
    un = f"@{user['username']}" if user.get("username") else str(user["id"])
    await message.reply(f"✅ Кулдауны {un} сброшены.")


# ── Pull controls ─────────────────────────────────────────────────────────────

@router.message(Command("pullstop"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_pullstop(message: Message):
    cfg.PULL_ENABLED = False
    await message.reply("⏸ Pull остановлен. Пользователи не могут просматривать задания.")
    logger.info("Pull stopped by admin %s", message.from_user.id)


@router.message(Command("pullstart"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_pullstart(message: Message):
    cfg.PULL_ENABLED = True
    await message.reply("▶️ Pull возобновлён.")
    logger.info("Pull started by admin %s", message.from_user.id)


@router.message(Command("pullclear"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_pullclear(message: Message):
    count = await clear_all_tasks()
    await message.reply(f"🗑 Удалено активных заданий: {count}")
    logger.info("Pull cleared by admin %s (%s tasks)", message.from_user.id, count)


# ── /deletefrompull ───────────────────────────────────────────────────────────

@router.message(Command("deletefrompull"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_delete_from_pull(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.reply("Использование: /deletefrompull <task_id>")
        return
    task = await get_task(int(args[1]))
    if not task:
        await message.reply("❌ Задание не найдено.")
        return
    await cancel_task(int(args[1]))
    await message.reply(f"✅ Задание #{args[1]} удалено из Pull.")


# ── /addtopull ────────────────────────────────────────────────────────────────

@router.message(Command("addtopull"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_add_to_pull(message: Message):
    parts = message.text.split(maxsplit=3)
    types_str = "/".join(TASK_CONFIG.keys())
    if len(parts) < 4:
        await message.reply(
            f"Использование: /addtopull <{types_str}> <слотов> <url>\n"
            f"Пример: /addtopull like 10 https://threads.net/@user/post/123"
        )
        return
    task_type = parts[1].lower()
    if task_type not in TASK_CONFIG:
        await message.reply(f"❌ Неверный тип. Доступны: {types_str}")
        return
    try:
        slots = int(parts[2])
        if slots < 1:
            raise ValueError()
    except ValueError:
        await message.reply("❗ Количество слотов ≥ 1.")
        return
    url = parts[3].strip()
    task_id = await create_task(
        creator_id=message.from_user.id,
        task_type=task_type,
        target_url=url,
        description="[Admin task]",
        total_slots=slots,
    )
    cfg2 = TASK_CONFIG[task_type]
    await message.reply(
        f"✅ Задание добавлено!\n"
        f"ID: {task_id} · {task_type.capitalize()} · {slots} слотов · {cfg2['reward']}🌟/слот"
    )


# ── /broadcast ────────────────────────────────────────────────────────────────

@router.message(Command("broadcast"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_broadcast_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.broadcast)
    await message.reply(
        "📢 РАССЫЛКА\n\nВведи текст сообщения. Следующее сообщение будет разослано всем пользователям."
    )


@router.message(AdminStates.broadcast, F.chat.id == ADMIN_GROUP_ID)
async def do_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    text = message.text
    if not text:
        await message.reply("❗ Только текстовые рассылки поддерживаются.")
        return
    user_ids = await get_all_user_ids()
    await message.reply(f"⏳ Рассылка для {len(user_ids)} пользователей...")
    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, f"📢 Сообщение от редакции ЧЕРНОВИК:\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
    await message.reply(
        f"✅ Рассылка завершена.\nОтправлено: {sent}\nНе доставлено: {failed}"
    )
    logger.info("Broadcast by %s: sent=%s failed=%s", message.from_user.id, sent, failed)
