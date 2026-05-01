import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states import ReportStates
from services.user_service import get_or_create_user, is_user_banned, get_balance
from services.task_service import get_user_active_tasks
from services.cooldown_service import check_cooldown, set_cooldown, get_cooldown_status
from services.card_service import get_artist_by_user, get_user_card_stats
from config import ADMIN_GROUP_ID, DAILY_LIMITS

router = Router()
logger = logging.getLogger(__name__)


# ── /acc + кнопка 📊 Аккаунт ─────────────────────────────────────────────────

@router.message(Command("acc"))
async def cmd_acc(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    if user["is_banned"]:
        await message.answer("🚫 Вы заблокированы.")
        return
    await _send_account(message.from_user.id, user, send_func=message.answer)


@router.callback_query(F.data == "my_account")
async def my_account_cb(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username)
    if user["is_banned"]:
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return
    await _send_account(callback.from_user.id, user, send_func=callback.message.answer)
    await callback.answer()


async def _send_account(user_id: int, user: dict, send_func):
    """
    Формат:
    📊 АККАУНТ
    🫵: @username
    🆔: 7811593067
    🫆: #7271   (artist_id если есть)
    🗂️: 7 ♥️   (активных карточек · суммарный рейтинг)
    📌: 2       (активных заданий)
    🌟: 18
    🪪: (@handle)  / статус верификации
    """
    active_tasks  = await get_user_active_tasks(user_id)
    artist        = await get_artist_by_user(user_id)
    card_stats    = await get_user_card_stats(artist["id"]) if artist else {"active_cards": 0, "total_rating": 0}

    uname_str     = f"@{user['username']}" if user.get("username") else "—"
    verified_str  = f"🪪 (@{user['threads_username']})" if user.get("is_verified") and user.get("threads_username") \
                    else ("🪪 верифицирован" if user.get("is_verified") else "❌ не верифицирован")

    artist_line   = f"🫆: #{artist['artist_id']}" if artist else "🫆: —"
    cards_line    = f"🗂️: {card_stats['active_cards']} · ♥️{card_stats['total_rating']}"

    text = (
        f"📊 АККАУНТ\n\n"
        f"🫵: {uname_str}\n"
        f"🆔: {user['id']}\n"
        f"{artist_line}\n"
        f"{cards_line}\n"
        f"📌: {len(active_tasks)}\n"
        f"🌟: {user['balance']}\n"
        f"{verified_str}"
    )
    await send_func(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ]),
    )


# ── /limit ────────────────────────────────────────────────────────────────────

@router.message(Command("limit"))
async def cmd_limit(message: Message):
    uid = message.from_user.id
    if await is_user_banned(uid):
        await message.answer("🚫 Вы заблокированы.")
        return
    s       = await get_cooldown_status(uid)
    balance = await get_balance(uid)
    await message.answer(
        f"📊 ЛИМИТЫ\n\n🌟: {balance}\n\n"
        f"⏳ Кулдауны:\n"
        f"  👍 {s['like_remaining_str']}  "
        f"✍️ {s['comment_remaining_str']}  "
        f"🤝 {s['repost_remaining_str']}  "
        f"👉 {s['follow_remaining_str']}\n"
        f"  ⚡️ выполнение: {s['execute_remaining_str']}\n"
        f"  ➕ создание:   {s['create_remaining_str']}\n\n"
        f"📅 Дневные (00:00 UTC):\n"
        f"  Like:    {s['like_today']}/{DAILY_LIMITS['like']}\n"
        f"  Comment: {s['comment_today']}/{DAILY_LIMITS['comment']}\n"
        f"  Repost:  {s['repost_today']}/{DAILY_LIMITS['repost']}\n"
        f"  Follow:  {s['follow_today']}/{DAILY_LIMITS['follow']}"
    )


# ── /report — FSM ─────────────────────────────────────────────────────────────

@router.message(Command("report"))
async def cmd_report_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    if await is_user_banned(uid):
        await message.answer("🚫 Вы заблокированы.")
        return
    ready, remaining = await check_cooldown(uid, "report")
    if not ready:
        h, m = remaining // 3600, (remaining % 3600) // 60
        await message.answer(f"⏳ Следующая жалоба через {h}ч {m}м.")
        return
    await state.set_state(ReportStates.enter_text)
    await message.answer(
        "🚨 ЖАЛОБА\n\nОпиши ситуацию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
        ]),
    )


@router.message(ReportStates.enter_text)
async def cmd_report_text(message: Message, state: FSMContext, bot: Bot):
    uid   = message.from_user.id
    text  = (message.text or "").strip()
    if not text:
        await message.answer("❗ Введи текст жалобы.")
        return
    await state.clear()
    user  = await get_or_create_user(uid, message.from_user.username)
    uname = f"@{user['username']}" if user.get("username") else f"ID:{uid}"
    await set_cooldown(uid, "report")
    try:
        await bot.send_message(
            ADMIN_GROUP_ID,
            f"🚨 ЖАЛОБА\n\nОт: {uname} (ID: {uid})\n\n{text}",
        )
        await message.answer("✅ Жалоба отправлена.")
    except Exception as e:
        logger.error("Report send failed: %s", e)
        await message.answer("❌ Ошибка отправки. Попробуй позже.")
