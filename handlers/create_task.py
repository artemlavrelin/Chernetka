import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import CreateTaskStates
from keyboards.promotion_kb import (
    task_type_keyboard,
    confirm_create_keyboard,
    skip_desc_keyboard,
    promotion_menu_keyboard,
)
from services.user_service import get_or_create_user, is_user_banned, get_balance, deduct_balance
from services.task_service import create_task
from services.cooldown_service import check_cooldown, set_cooldown
from config import TASK_CONFIG, TASK_EMOJI

router = Router()
logger = logging.getLogger(__name__)

MAX_SLOTS = 50
MAX_COMMENT_SLOTS = 5


# ─── Вход в создание задания ───────────────────────────────────────────────

@router.callback_query(F.data == "create_task")
async def start_create_task(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if await is_user_banned(user_id):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return

    ready, remaining = await check_cooldown(user_id, "create")
    if not ready:
        h, m = remaining // 3600, (remaining % 3600) // 60
        await callback.answer(
            f"⏳ Создание задания доступно через {h}ч {m}м",
            show_alert=True,
        )
        return

    await state.set_state(CreateTaskStates.select_type)
    await callback.message.edit_text(
        "➕ Создание задания\n\nВыбери тип:",
        reply_markup=task_type_keyboard(),
    )
    await callback.answer()


# ─── Шаг 1: Тип задания ───────────────────────────────────────────────────

@router.callback_query(CreateTaskStates.select_type, F.data.startswith("ct_type_"))
async def select_task_type(callback: CallbackQuery, state: FSMContext):
    task_type = callback.data.split("_")[2]  # like / comment / repost / follow
    cfg = TASK_CONFIG[task_type]
    emoji = TASK_EMOJI[task_type]
    await state.update_data(task_type=task_type)
    await state.set_state(CreateTaskStates.enter_url)

    hints = {
        "like":    "Ссылку на пост, который нужно лайкнуть",
        "comment": "Ссылку на пост, под которым нужен комментарий",
        "repost":  "Ссылку на пост, который нужно репостнуть",
        "follow":  "Ссылку на аккаунт или @username, на который нужно подписаться",
    }
    cost_info = (
        f"💰 Стоимость: {cfg['cost']}🌟/слот · Награда исполнителю: {cfg['reward']}🌟/слот"
    )
    await callback.message.edit_text(
        f"{emoji} Задание: {task_type.capitalize()}\n{cost_info}\n\n"
        f"📎 Отправь {hints[task_type]}:"
    )
    await callback.answer()


# ─── Шаг 2: URL ───────────────────────────────────────────────────────────

@router.message(CreateTaskStates.enter_url)
async def receive_url(message: Message, state: FSMContext):
    url = message.text.strip() if message.text else ""
    if not url or (not url.startswith("http") and not url.startswith("@")):
        await message.answer("❗ Отправь корректную ссылку или @username.")
        return
    await state.update_data(target_url=url)
    await state.set_state(CreateTaskStates.enter_description)
    await message.answer(
        "📝 Добавь описание задания (или пропусти):",
        reply_markup=skip_desc_keyboard(),
    )


# ─── Шаг 3: Описание (опционально) ────────────────────────────────────────

@router.callback_query(CreateTaskStates.enter_description, F.data == "ct_skip_desc")
async def skip_task_description(callback: CallbackQuery, state: FSMContext):
    await state.update_data(description=None)
    await _go_to_slots(callback.message, state, edit=True)
    await callback.answer()


@router.message(CreateTaskStates.enter_description)
async def receive_task_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await _go_to_slots(message, state, edit=False)


async def _go_to_slots(msg_or_callback, state: FSMContext, edit: bool):
    data = await state.get_data()
    task_type = data.get("task_type")

    if task_type == "comment":
        await state.set_state(CreateTaskStates.enter_slots)
        text = "✍️ Сколько комментариев нужно? (1–5):"
    else:
        await state.set_state(CreateTaskStates.enter_slots)
        text = f"🔢 Сколько слотов нужно? (1–{MAX_SLOTS}):\n\nКаждый слот = одно выполнение."

    if edit:
        await msg_or_callback.edit_text(text)
    else:
        await msg_or_callback.answer(text)


# ─── Шаг 4: Количество слотов ──────────────────────────────────────────────

@router.message(CreateTaskStates.enter_slots)
async def receive_slots(message: Message, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    max_s = MAX_COMMENT_SLOTS if task_type == "comment" else MAX_SLOTS

    try:
        slots = int(message.text.strip())
        if not (1 <= slots <= max_s):
            raise ValueError()
    except ValueError:
        await message.answer(f"❗ Введи число от 1 до {max_s}.")
        return

    await state.update_data(total_slots=slots)

    if task_type == "comment":
        await state.set_state(CreateTaskStates.enter_comment_text)
        await message.answer(
            "💬 Введи текст комментария, который будут оставлять исполнители:"
        )
    else:
        await _show_confirm(message, state, edit=False)


# ─── Шаг 4b: Текст комментария (только для comment) ───────────────────────

@router.message(CreateTaskStates.enter_comment_text)
async def receive_comment_text(message: Message, state: FSMContext):
    await state.update_data(comment_text=message.text)
    await _show_confirm(message, state, edit=False)


# ─── Шаг 5: Подтверждение ─────────────────────────────────────────────────

async def _show_confirm(msg, state: FSMContext, edit: bool):
    data = await state.get_data()
    task_type = data.get("task_type")
    slots = data.get("total_slots", 1)
    cfg = TASK_CONFIG[task_type]
    total_cost = cfg["cost"] * slots
    emoji = TASK_EMOJI[task_type]
    desc = data.get("description") or "—"
    comment = data.get("comment_text") or ""

    text = (
        f"📋 ПОДТВЕРЖДЕНИЕ ЗАДАНИЯ\n\n"
        f"Тип: {emoji} {task_type.capitalize()}\n"
        f"Ссылка: {data.get('target_url')}\n"
        f"Описание: {desc}\n"
    )
    if comment:
        text += f"💬 Комментарий: {comment}\n"
    text += (
        f"Слотов: {slots}\n"
        f"Стоимость: {total_cost}🌟 ({cfg['cost']}🌟 × {slots})\n"
        f"Награда исполнителю: {cfg['reward']}🌟/слот\n\n"
        f"Подтвердить?"
    )
    await state.set_state(CreateTaskStates.confirm)
    kb = confirm_create_keyboard()

    if edit:
        await msg.edit_text(text, reply_markup=kb)
    else:
        await msg.answer(text, reply_markup=kb)


@router.callback_query(CreateTaskStates.confirm, F.data == "ct_confirm")
async def confirm_create(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    await state.clear()

    task_type = data.get("task_type")
    slots = data.get("total_slots", 1)
    cfg = TASK_CONFIG[task_type]
    total_cost = cfg["cost"] * slots

    # Проверяем баланс
    balance = await get_balance(user_id)
    if balance < total_cost:
        await callback.answer(
            f"❌ Недостаточно 🌟. Нужно {total_cost}🌟, у вас {balance}🌟.",
            show_alert=True,
        )
        await callback.message.edit_text("❌ Недостаточно 🌟 для создания задания.")
        return

    # Списываем
    success = await deduct_balance(user_id, total_cost)
    if not success:
        await callback.answer("❌ Ошибка списания баланса.", show_alert=True)
        return

    # Создаём задание
    task_id = await create_task(
        creator_id=user_id,
        task_type=task_type,
        target_url=data.get("target_url"),
        description=data.get("description"),
        total_slots=slots,
        comment_text=data.get("comment_text"),
    )

    # Кулдаун на создание
    await set_cooldown(user_id, "create")

    emoji = TASK_EMOJI[task_type]
    await callback.message.edit_text(
        f"✅ Задание создано!\n\n"
        f"ID: {task_id}\n"
        f"Тип: {emoji} {task_type.capitalize()}\n"
        f"Слотов: {slots}\n"
        f"Списано: {total_cost}🌟\n\n"
        f"Задание появится в ленте Pull для других пользователей.",
        reply_markup=promotion_menu_keyboard(),
    )
    await callback.answer()
    logger.info("Task %s created by user %s (%s, %s slots, cost %s)",
                task_id, user_id, task_type, slots, total_cost)
