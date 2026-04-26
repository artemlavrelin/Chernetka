import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from services.user_service import get_or_create_user, is_user_banned
from services.cooldown_service import check_cooldown, set_cooldown, get_cooldown_status
from services.task_service import get_user_active_tasks
from config import ADMIN_GROUP_ID, DAILY_LIMITS

router = Router()
logger = logging.getLogger(__name__)


# ─── /acc ─────────────────────────────────────────────────────────────────

@router.message(Command("acc"))
async def cmd_acc(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    if user["is_banned"]:
        await message.answer("🚫 Вы заблокированы.")
        return

    active_tasks = await get_user_active_tasks(message.from_user.id)
    username_display = f"@{user['username']}" if user.get("username") else f"ID: {user['id']}"

    tasks_text = ""
    if active_tasks:
        tasks_text = "\n\n📌 Активные задания:\n"
        for t in active_tasks[:5]:
            tasks_text += (
                f"  • ID {t['id']} · {t['task_type'].capitalize()} "
                f"· {t['remaining_slots']}/{t['total_slots']} слотов\n"
            )
        if len(active_tasks) > 5:
            tasks_text += f"  ...и ещё {len(active_tasks) - 5}"

    await message.answer(
        f"👤 ПРОФИЛЬ\n\n"
        f"Имя: {username_display}\n"
        f"ID: {user['id']}\n"
        f"Баланс: {user['balance']}🌟\n"
        f"Активных заданий: {len(active_tasks)}"
        f"{tasks_text}"
    )


# ─── /limit ───────────────────────────────────────────────────────────────

@router.message(Command("limit"))
async def cmd_limit(message: Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer("🚫 Вы заблокированы.")
        return

    s = await get_cooldown_status(user_id)

    await message.answer(
        f"📊 ЛИМИТЫ И КУЛДАУНЫ\n\n"
        f"⏳ Кулдауны (до следующего действия):\n"
        f"  👍 Like:    {s['like_remaining_str']}\n"
        f"  ✍️ Comment: {s['comment_remaining_str']}\n"
        f"  🤝 Repost:  {s['repost_remaining_str']}\n"
        f"  👉 Follow:  {s['follow_remaining_str']}\n"
        f"  ⚡️ Выполнение: {s['execute_remaining_str']}\n"
        f"  ➕ Создание:   {s['create_remaining_str']}\n\n"
        f"📅 Дневные лимиты (обновление 00:00 GMT):\n"
        f"  Like:    {s['like_today']}/{DAILY_LIMITS['like']}\n"
        f"  Comment: {s['comment_today']}/{DAILY_LIMITS['comment']}\n"
        f"  Repost:  {s['repost_today']}/{DAILY_LIMITS['repost']}\n"
        f"  Follow:  {s['follow_today']}/{DAILY_LIMITS['follow']}"
    )


# ─── /report ──────────────────────────────────────────────────────────────

@router.message(Command("report"))
async def cmd_report(message: Message, bot: Bot):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer("🚫 Вы заблокированы.")
        return

    ready, remaining = await check_cooldown(user_id, "report")
    if not ready:
        h, m = remaining // 3600, (remaining % 3600) // 60
        await message.answer(f"⏳ Следующая жалоба доступна через {h}ч {m}м.")
        return

    # Получаем текст жалобы из команды
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "❗ Укажи текст жалобы:\n/report <текст жалобы>"
        )
        return

    report_text = args[1].strip()
    user = await get_or_create_user(user_id, message.from_user.username)
    username_display = f"@{user['username']}" if user.get("username") else f"ID:{user_id}"

    await set_cooldown(user_id, "report")

    try:
        await bot.send_message(
            ADMIN_GROUP_ID,
            f"🚨 ЖАЛОБА\n\n"
            f"От: {username_display} (ID: {user_id})\n\n"
            f"Текст:\n{report_text}"
        )
        await message.answer("✅ Жалоба отправлена администраторам. Спасибо!")
    except Exception as e:
        logger.error("Failed to send report: %s", e)
        await message.answer("❌ Не удалось отправить жалобу. Попробуй позже.")
