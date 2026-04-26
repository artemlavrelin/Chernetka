import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states import PullStates
from keyboards.promotion_kb import (
    promotion_menu_keyboard,
    task_card_keyboard,
    pull_empty_keyboard,
)
from services.user_service import is_user_banned
from services.task_service import get_available_tasks, get_task
from config import TASK_EMOJI

router = Router()
logger = logging.getLogger(__name__)


def _detect_platform(url: str) -> str:
    url = url.lower()
    if "threads" in url:    return "Threads"
    if "youtube" in url or "youtu.be" in url: return "YouTube"
    if "soundcloud" in url: return "SoundCloud"
    if "instagram" in url:  return "Instagram"
    if "t.me" in url:       return "Telegram"
    return "Внешний"


def _build_task_card(task: dict) -> str:
    emoji = TASK_EMOJI.get(task["task_type"], "⚡️")
    platform = _detect_platform(task["target_url"])
    desc = task.get("description") or "—"
    comment = task.get("comment_text")

    text = (
        f"⚡️ PULL\n\n"
        f"ID: {task['id']}\n"
        f"Тип: {emoji} {task['task_type'].capitalize()} ({platform})\n"
        f"Награда: {task['reward_per_slot']}🌟\n\n"
        f"Описание:\n{desc}\n\n"
    )
    if comment:
        text += f"💬 Текст для комментария:\n{comment}\n\n"
    text += f"🔗 {task['target_url']}"
    return text


# ─── Меню продвижения ──────────────────────────────────────────────────────

@router.callback_query(F.data == "promotion")
async def promotion_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if await is_user_banned(callback.from_user.id):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return
    await callback.message.edit_text(
        "🌀 ПУЛ ПРОДВИЖЕНИЯ\n\n"
        "выполняй задания → получай 🌟 → создавай свои задания\n\n"
        "📌 Типы: ⚡️ Pull  👍 Like  ✍️ Comment  🤝 Repost  👉 Follow",
        reply_markup=promotion_menu_keyboard(),
    )
    await callback.answer()


# ─── Запуск Pull ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "pull_start")
async def start_pull(callback: CallbackQuery, state: FSMContext):
    if await is_user_banned(callback.from_user.id):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return

    tasks = await get_available_tasks(callback.from_user.id)

    if not tasks:
        await callback.message.edit_text(
            "⚠️ заданий пока нет",
            reply_markup=pull_empty_keyboard(),
        )
        await callback.answer()
        return

    task_ids = [t["id"] for t in tasks]
    await state.set_state(PullStates.browsing)
    await state.update_data(task_ids=task_ids, pull_index=0)

    task = tasks[0]
    await callback.message.edit_text(
        _build_task_card(task),
        reply_markup=task_card_keyboard(task["id"]),
        disable_web_page_preview=True,
    )
    await callback.answer()


# ─── Следующее задание ─────────────────────────────────────────────────────

@router.callback_query(PullStates.browsing, F.data == "pull_next")
async def next_task(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_ids: list = data.get("task_ids", [])
    index: int = data.get("pull_index", 0) + 1

    if index >= len(task_ids):
        await state.clear()
        await callback.message.edit_text(
            "⚠️ заданий пока нет\n\nВы просмотрели все доступные задания.",
            reply_markup=pull_empty_keyboard(),
        )
        await callback.answer()
        return

    await state.update_data(pull_index=index)
    task = await get_task(task_ids[index])

    if not task or task["status"] != "active" or task["remaining_slots"] <= 0:
        # Задание стало недоступным — пропускаем
        # Просто имитируем нажатие next ещё раз через рекурсию состояний
        await state.update_data(pull_index=index)
        # Переходим к следующему
        new_index = index + 1
        while new_index < len(task_ids):
            task = await get_task(task_ids[new_index])
            if task and task["status"] == "active" and task["remaining_slots"] > 0:
                break
            new_index += 1
        else:
            await state.clear()
            await callback.message.edit_text(
                "⚠️ заданий пока нет",
                reply_markup=pull_empty_keyboard(),
            )
            await callback.answer()
            return
        await state.update_data(pull_index=new_index)

    await callback.message.edit_text(
        _build_task_card(task),
        reply_markup=task_card_keyboard(task["id"]),
        disable_web_page_preview=True,
    )
    await callback.answer()
