import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from states import AdminStates
from services.user_service import (
    get_user, get_user_by_username, ban_user, unban_user,
    get_top_balances, add_balance, set_balance, get_all_user_ids,
)
from services.task_service import get_task, cancel_task, create_task
from services.cooldown_service import reset_cooldown
from config import ADMIN_GROUP_ID, TASK_CONFIG

router = Router()
logger = logging.getLogger(__name__)


def _is_admin_group(message: Message) -> bool:
    return message.chat.id == ADMIN_GROUP_ID


async def _resolve_user(identifier: str):
    """Ищет пользователя по ID или @username."""
    identifier = identifier.strip().lstrip("@")
    if identifier.isdigit():
        return await get_user(int(identifier))
    return await get_user_by_username(identifier)


# ─── /ban ─────────────────────────────────────────────────────────────────

@router.message(Command("ban"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_ban(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Использование: /ban <id/@username>")
        return
    user = await _resolve_user(args[1])
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    await ban_user(user["id"])
    uname = f"@{user['username']}" if user.get("username") else str(user["id"])
    await message.reply(f"🚫 Пользователь {uname} заблокирован.")
    logger.info("Admin %s banned user %s", message.from_user.id, user["id"])


# ─── /unban ───────────────────────────────────────────────────────────────

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
    await message.reply(f"✅ Пользователь {uname} разблокирован.")


# ─── /balancecheck ────────────────────────────────────────────────────────

@router.message(Command("balancecheck"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_balancecheck(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        # Топ-10
        top = await get_top_balances(10)
        if not top:
            await message.reply("Пользователей нет.")
            return
        lines = ["🌟 ТОП-10 БАЛАНСОВ\n"]
        for i, u in enumerate(top, 1):
            uname = f"@{u['username']}" if u.get("username") else str(u["id"])
            lines.append(f"{i}. {uname} — {u['balance']}🌟")
        await message.reply("\n".join(lines))
        return

    user = await _resolve_user(args[1])
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    uname = f"@{user['username']}" if user.get("username") else str(user["id"])
    await message.reply(
        f"👤 {uname}\n"
        f"ID: {user['id']}\n"
        f"Баланс: {user['balance']}🌟\n"
        f"Бан: {'Да' if user['is_banned'] else 'Нет'}"
    )


# ─── /balancechange ───────────────────────────────────────────────────────

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
        await message.reply("❗ Сумма должна быть числом (например +10 или -5).")
        return

    new_bal = await add_balance(user["id"], amount)
    uname = f"@{user['username']}" if user.get("username") else str(user["id"])
    sign = "+" if amount >= 0 else ""
    await message.reply(f"✅ {uname}: {sign}{amount}🌟 → Баланс: {new_bal}🌟")
    logger.info("Admin %s changed balance of %s by %s", message.from_user.id, user["id"], amount)


# ─── /removecoldown ───────────────────────────────────────────────────────

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
    uname = f"@{user['username']}" if user.get("username") else str(user["id"])
    await message.reply(f"✅ Кулдауны пользователя {uname} сброшены.")


# ─── /deletefrompull ──────────────────────────────────────────────────────

@router.message(Command("deletefrompull"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_delete_from_pull(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.reply("Использование: /deletefrompull <task_id>")
        return
    task_id = int(args[1])
    task = await get_task(task_id)
    if not task:
        await message.reply("❌ Задание не найдено.")
        return
    await cancel_task(task_id)
    await message.reply(f"✅ Задание #{task_id} удалено из Pull.")
    logger.info("Admin %s cancelled task %s", message.from_user.id, task_id)


# ─── /addtopull ──────────────────────────────────────────────────────────

@router.message(Command("addtopull"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_add_to_pull(message: Message):
    """
    Формат: /addtopull <type> <slots> <url>
    Пример: /addtopull like 5 https://threads.com/post/123
    """
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        types = "/".join(TASK_CONFIG.keys())
        await message.reply(
            f"Использование: /addtopull <{types}> <слотов> <url>\n"
            f"Пример: /addtopull like 10 https://threads.net/@user/post/123"
        )
        return

    task_type = parts[1].lower()
    if task_type not in TASK_CONFIG:
        await message.reply(f"❌ Неверный тип. Доступны: {', '.join(TASK_CONFIG.keys())}")
        return

    try:
        slots = int(parts[2])
        if slots < 1:
            raise ValueError()
    except ValueError:
        await message.reply("❗ Количество слотов должно быть числом ≥ 1.")
        return

    url = parts[3].strip()
    admin_id = message.from_user.id

    task_id = await create_task(
        creator_id=admin_id,
        task_type=task_type,
        target_url=url,
        description="[Admin task]",
        total_slots=slots,
    )
    cfg = TASK_CONFIG[task_type]
    await message.reply(
        f"✅ Задание добавлено в Pull!\n"
        f"ID: {task_id} · {task_type.capitalize()} · {slots} слотов · {cfg['reward']}🌟/слот"
    )


# ─── /broadcast ───────────────────────────────────────────────────────────

@router.message(Command("broadcast"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_broadcast_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.broadcast)
    await message.reply(
        "📢 РАССЫЛКА\n\n"
        "Введи текст сообщения для отправки всем пользователям.\n"
        "(следующее сообщение будет разослано)"
    )


@router.message(AdminStates.broadcast, F.chat.id == ADMIN_GROUP_ID)
async def do_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    text = message.text
    if not text:
        await message.reply("❗ Только текстовые рассылки поддерживаются.")
        return

    user_ids = await get_all_user_ids()
    sent = 0
    failed = 0

    await message.reply(f"⏳ Рассылка для {len(user_ids)} пользователей...")

    for uid in user_ids:
        try:
            await bot.send_message(uid, f"📢 Сообщение от редакции:\n\n{text}")
            sent += 1
        except Exception:
            failed += 1

    await message.reply(
        f"✅ Рассылка завершена.\n"
        f"Отправлено: {sent}\nНе доставлено: {failed}"
    )
    logger.info("Broadcast by admin %s: %s sent, %s failed", message.from_user.id, sent, failed)
