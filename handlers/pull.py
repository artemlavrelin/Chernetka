import logging
import config as cfg
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states import PullStates
from keyboards.promotion_kb import (
    promotion_menu_keyboard, task_card_keyboard, pull_empty_keyboard,
)
from services.user_service import is_user_banned, get_balance
from services.task_service import get_available_tasks, get_task
from config import TASK_EMOJI

router = Router()
logger = logging.getLogger(__name__)

PROMOTION_TEXT = (
    "📈 ПУЛ ПРОДВИЖЕНИЯ\n\n"
    "Здесь ты выполняешь задания других и получаешь 🌟\n"
    "за 🌟 создаёшь свои задания и продвигаешь посты\n\n"
    "как это работает: выполнил → получил 🌟 → запустил своё продвижение\n\n"
    "📌 Типы: 📱 Pull  👍 Like  ✍️ Comment  🤝 Repost  👉 Follow"
)


def _detect_platform(url: str) -> str:
    url = url.lower()
    if "threads" in url:    return "Threads"
    if "youtu" in url:      return "YouTube"
    if "soundcloud" in url: return "SoundCloud"
    if "instagram" in url:  return "Instagram"
    if "t.me" in url:       return "Telegram"
    return "Внешний"


def _build_task_card_hidden(task: dict, balance: int) -> str:
    """Карточка задания со скрытой ссылкой до нажатия Выполнить."""
    emoji = TASK_EMOJI.get(task["task_type"], "⚡️")
    platform = _detect_platform(task["target_url"])
    desc = task.get("description") or "—"

    return (
        f"📲 PULL\n\n"
        f"ID: {task['id']}\n"
        f"Тип: {emoji} {task['task_type'].capitalize()} ({platform})\n"
        f"Награда: {task['reward_per_slot']}🌟\n\n"
        f"Описание:\n{desc}\n\n"
        f"🔗 Ссылка скрыта.\n"
        f"Нажми ✅ Выполнить чтобы увидеть ссылку.\n\n"
        f"Balance: {balance}🌟"
    )


@router.callback_query(F.data == "promotion")
async def promotion_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if await is_user_banned(callback.from_user.id):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return
    balance = await get_balance(callback.from_user.id)
    await callback.message.edit_text(
        f"{PROMOTION_TEXT}\n\nBalance: {balance}🌟",
        reply_markup=promotion_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "pull_start")
async def start_pull(callback: CallbackQuery, state: FSMContext):
    if await is_user_banned(callback.from_user.id):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return
    if not cfg.PULL_ENABLED:
        await callback.answer("⏸ Pull временно остановлен администратором.", show_alert=True)
        return

    tasks = await get_available_tasks(callback.from_user.id)
    if not tasks:
        balance = await get_balance(callback.from_user.id)
        await callback.message.edit_text(
            f"⚠️ заданий пока нет\n\nBalance: {balance}🌟",
            reply_markup=pull_empty_keyboard(),
        )
        await callback.answer()
        return

    task_ids = [t["id"] for t in tasks]
    await state.set_state(PullStates.browsing)
    await state.update_data(task_ids=task_ids, pull_index=0)

    balance = await get_balance(callback.from_user.id)
    task = tasks[0]
    await callback.message.edit_text(
        _build_task_card_hidden(task, balance),
        reply_markup=task_card_keyboard(task["id"]),
    )
    await callback.answer()


@router.callback_query(PullStates.browsing, F.data == "pull_next")
async def next_task(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_ids: list = data.get("task_ids", [])
    index: int = data.get("pull_index", 0) + 1

    # Ищем следующее доступное задание
    task = None
    while index < len(task_ids):
        t = await get_task(task_ids[index])
        if t and t["status"] == "active" and t["remaining_slots"] > 0:
            task = t
            break
        index += 1

    if not task:
        await state.clear()
        balance = await get_balance(callback.from_user.id)
        await callback.message.edit_text(
            f"⚠️ Вы просмотрели все доступные задания.\n\nBalance: {balance}🌟",
            reply_markup=pull_empty_keyboard(),
        )
        await callback.answer()
        return

    await state.update_data(pull_index=index)
    balance = await get_balance(callback.from_user.id)
    await callback.message.edit_text(
        _build_task_card_hidden(task, balance),
        reply_markup=task_card_keyboard(task["id"]),
    )
    await callback.answer()
