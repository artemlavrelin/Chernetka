import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from states import ReportStates
from services.user_service import get_or_create_user, is_user_banned, get_balance
from services.task_service import get_user_active_tasks
from services.cooldown_service import check_cooldown, set_cooldown, get_cooldown_status
from config import ADMIN_GROUP_ID, DAILY_LIMITS

router = Router()
logger = logging.getLogger(__name__)


# ── /acc и кнопка 📊 Аккаунт ────────────────────────────────────────────────

@router.message(Command("acc"))
async def cmd_acc(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    if user["is_banned"]:
        await message.answer("🚫 Вы заблокированы.")
        return
    await _send_account(message.from_user.id, user, reply_func=message.answer)


@router.callback_query(F.data == "my_account")
async def my_account_cb(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username)
    if user["is_banned"]:
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return
    await _send_account(callback.from_user.id, user, reply_func=callback.message.answer)
    await callback.answer()


async def _send_account(user_id: int, user: dict, reply_func):
    active_tasks = await get_user_active_tasks(user_id)
    s = await get_cooldown_status(user_id)
    uname = f"@{user['username']}" if user.get("username") else f"ID: {user['id']}"
    verified = "🪪 Верифицирован" if user.get("is_verified") else "❌ Не верифицирован"
    threads = f" (@{user['threads_username']})" if user.get("threads_username") else ""

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

    await reply_func(
        f"📊 АККАУНТ\n\n"
        f"Имя: {uname}\n"
        f"ID: {user['id']}\n"
        f"Balance: {user['balance']}🌟\n"
        f"Статус: {verified}{threads}\n\n"
        f"📅 Дневные лимиты:\n"
        f"  Like:    {s['like_today']}/{DAILY_LIMITS['like']}\n"
        f"  Comment: {s['comment_today']}/{DAILY_LIMITS['comment']}\n"
        f"  Repost:  {s['repost_today']}/{DAILY_LIMITS['repost']}\n"
        f"  Follow:  {s['follow_today']}/{DAILY_LIMITS['follow']}\n"
        f"\nАктивных заданий: {len(active_tasks)}"
        f"{tasks_text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ])
    )


# ── /limit ───────────────────────────────────────────────────────────────────

@router.message(Command("limit"))
async def cmd_limit(message: Message):
    uid = message.from_user.id
    if await is_user_banned(uid):
        await message.answer("🚫 Вы заблокированы.")
        return
    s = await get_cooldown_status(uid)
    balance = await get_balance(uid)
    await message.answer(
        f"📊 ЛИМИТЫ И КУЛДАУНЫ\n\nBalance: {balance}🌟\n\n"
        f"⏳ Кулдауны:\n"
        f"  👍 Like:       {s['like_remaining_str']}\n"
        f"  ✍️ Comment:    {s['comment_remaining_str']}\n"
        f"  🤝 Repost:     {s['repost_remaining_str']}\n"
        f"  👉 Follow:     {s['follow_remaining_str']}\n"
        f"  ⚡️ Выполнение: {s['execute_remaining_str']}\n"
        f"  ➕ Создание:   {s['create_remaining_str']}\n\n"
        f"📅 Дневные лимиты (00:00 GMT):\n"
        f"  Like:    {s['like_today']}/{DAILY_LIMITS['like']}\n"
        f"  Comment: {s['comment_today']}/{DAILY_LIMITS['comment']}\n"
        f"  Repost:  {s['repost_today']}/{DAILY_LIMITS['repost']}\n"
        f"  Follow:  {s['follow_today']}/{DAILY_LIMITS['follow']}"
    )


# ── /report — двухшаговый FSM ─────────────────────────────────────────────────

@router.message(Command("report"))
async def cmd_report_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    if await is_user_banned(uid):
        await message.answer("🚫 Вы заблокированы.")
        return
    ready, remaining = await check_cooldown(uid, "report")
    if not ready:
        h, m = remaining // 3600, (remaining % 3600) // 60
        await message.answer(f"⏳ Следующая жалоба доступна через {h}ч {m}м.")
        return
    await state.set_state(ReportStates.enter_text)
    await message.answer(
        "🚨 ЖАЛОБА\n\nОпиши ситуацию подробно. Следующее сообщение будет отправлено администраторам:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
        ])
    )


@router.message(ReportStates.enter_text)
async def cmd_report_text(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    report_text = message.text or ""
    if not report_text.strip():
        await message.answer("❗ Введи текст жалобы.")
        return
    await state.clear()
    user = await get_or_create_user(uid, message.from_user.username)
    uname = f"@{user['username']}" if user.get("username") else f"ID:{uid}"
    await set_cooldown(uid, "report")
    try:
        await bot.send_message(
            ADMIN_GROUP_ID,
            f"🚨 ЖАЛОБА\n\nОт: {uname} (ID: {uid})\n\nТекст:\n{report_text}"
        )
        await message.answer("✅ Жалоба отправлена администраторам. Спасибо!")
    except Exception as e:
        logger.error("Failed to send report: %s", e)
        await message.answer("❌ Не удалось отправить жалобу. Попробуй позже.")
