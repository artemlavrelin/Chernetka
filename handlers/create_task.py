import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import CreateTaskStates
from keyboards.promotion_kb import (
    task_type_keyboard, confirm_create_keyboard,
    skip_desc_keyboard, promotion_menu_keyboard,
)
from services.user_service import get_or_create_user, is_user_banned, get_balance, deduct_balance
from services.task_service import create_task
from services.cooldown_service import check_cooldown, set_cooldown
from config import TASK_CONFIG, TASK_EMOJI

router = Router()
logger = logging.getLogger(__name__)
MAX_SLOTS = 50
MAX_COMMENT_SLOTS = 5


@router.callback_query(F.data == "create_task")
async def start_create_task(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if await is_user_banned(uid):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return

    # Требуем верификацию
    from services.user_service import get_user
    user = await get_user(uid)
    if not user or not user.get("is_verified"):
        await callback.answer(
            "🪪 Для создания заданий необходима верификация.\n"
            "Нажми «🪪 Верификация» в меню продвижения.",
            show_alert=True,
        )
        return

    ready, remaining = await check_cooldown(uid, "create")
    if not ready:
        h, m = remaining // 3600, (remaining % 3600) // 60
        await callback.answer(f"⏳ Создание задания доступно через {h}ч {m}м", show_alert=True)
        return

    balance = await get_balance(uid)
    await state.set_state(CreateTaskStates.select_type)
    await callback.message.edit_text(
        f"➕ Создание задания\n\nВыбери тип:\n\nBalance: {balance}🌟",
        reply_markup=task_type_keyboard(),
    )
    await callback.answer()


@router.callback_query(CreateTaskStates.select_type, F.data.startswith("ct_type_"))
async def select_task_type(callback: CallbackQuery, state: FSMContext):
    task_type = callback.data.split("_")[2]
    cfg = TASK_CONFIG[task_type]
    emoji = TASK_EMOJI[task_type]
    await state.update_data(task_type=task_type)
    await state.set_state(CreateTaskStates.enter_url)

    hints = {
        "like":    "Ссылку на пост, который нужно лайкнуть",
        "comment": "Ссылку на пост, под которым нужен комментарий",
        "repost":  "Ссылку на пост, который нужно репостнуть",
        "follow":  "Ссылку на аккаунт или @username для подписки",
    }
    balance = await get_balance(callback.from_user.id)
    await callback.message.edit_text(
        f"{emoji} Задание: {task_type.capitalize()}\n"
        f"💰 Стоимость: {cfg['cost']}🌟/слот · Награда: {cfg['reward']}🌟/слот\n\n"
        f"📎 Отправь {hints[task_type]}:\n\nBalance: {balance}🌟"
    )
    await callback.answer()


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


@router.callback_query(CreateTaskStates.enter_description, F.data == "ct_skip_desc")
async def skip_task_description(callback: CallbackQuery, state: FSMContext):
    await state.update_data(description=None)
    await _go_to_slots(callback.message, state, edit=True,
                       user_id=callback.from_user.id)
    await callback.answer()


@router.message(CreateTaskStates.enter_description)
async def receive_task_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await _go_to_slots(message, state, edit=False, user_id=message.from_user.id)


async def _go_to_slots(msg, state: FSMContext, edit: bool, user_id: int):
    data = await state.get_data()
    task_type = data.get("task_type")
    balance = await get_balance(user_id)
    await state.set_state(CreateTaskStates.enter_slots)
    max_s = MAX_COMMENT_SLOTS if task_type == "comment" else MAX_SLOTS
    text = (
        f"🔢 Сколько слотов нужно? (1–{max_s})\n"
        f"Каждый слот = одно выполнение.\n\nBalance: {balance}🌟"
    )
    if edit:
        await msg.edit_text(text)
    else:
        await msg.answer(text)


@router.message(CreateTaskStates.enter_slots)
async def receive_slots(message: Message, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    max_s = MAX_COMMENT_SLOTS if task_type == "comment" else MAX_SLOTS
    cfg = TASK_CONFIG[task_type]

    try:
        slots = int(message.text.strip())
        if not (1 <= slots <= max_s):
            raise ValueError()
    except ValueError:
        await message.answer(f"❗ Введи число от 1 до {max_s}.")
        return

    total_cost = cfg["cost"] * slots
    balance = await get_balance(message.from_user.id)
    await state.update_data(total_slots=slots)

    if task_type == "comment":
        await state.update_data(comment_texts=[], comment_index=1)
        await state.set_state(CreateTaskStates.enter_comment_texts)
        await message.answer(
            f"💬 Комментарий 1 из {slots}:\n"
            f"(каждый исполнитель получит уникальный текст)\n\n"
            f"Стоимость: {total_cost}🌟 ({cfg['cost']}🌟 × {slots})\n"
            f"Balance: {balance}🌟"
        )
    else:
        await _show_confirm(message, state, edit=False, user_id=message.from_user.id)


@router.message(CreateTaskStates.enter_comment_texts)
async def receive_comment_text(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❗ Введи текст комментария.")
        return
    data = await state.get_data()
    texts: list = data.get("comment_texts", [])
    texts.append(message.text.strip())
    index: int = data.get("comment_index", 1) + 1
    total = data.get("total_slots", 1)
    await state.update_data(comment_texts=texts, comment_index=index)

    if index > total:
        await _show_confirm(message, state, edit=False, user_id=message.from_user.id)
    else:
        await message.answer(f"💬 Комментарий {index} из {total}:")


async def _show_confirm(msg, state: FSMContext, edit: bool, user_id: int):
    data = await state.get_data()
    task_type = data.get("task_type")
    slots = data.get("total_slots", 1)
    cfg = TASK_CONFIG[task_type]
    total_cost = cfg["cost"] * slots
    emoji = TASK_EMOJI[task_type]
    desc = data.get("description") or "—"
    balance = await get_balance(user_id)
    texts = data.get("comment_texts", [])

    text = (
        f"📋 ПОДТВЕРЖДЕНИЕ ЗАДАНИЯ\n\n"
        f"Тип: {emoji} {task_type.capitalize()}\n"
        f"Ссылка: {data.get('target_url')}\n"
        f"Описание: {desc}\n"
    )
    if texts:
        text += f"Комментариев: {len(texts)}\n"
    text += (
        f"Слотов: {slots}\n"
        f"Стоимость: {total_cost}🌟 ({cfg['cost']}🌟 × {slots})\n"
        f"Награда исполнителю: {cfg['reward']}🌟/слот\n\n"
        f"Balance: {balance}🌟\n\n"
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
    uid = callback.from_user.id
    data = await state.get_data()
    await state.clear()

    task_type = data.get("task_type")
    slots = data.get("total_slots", 1)
    cfg = TASK_CONFIG[task_type]
    total_cost = cfg["cost"] * slots

    balance = await get_balance(uid)
    if balance < total_cost:
        await callback.answer(
            f"❌ Недостаточно 🌟. Нужно {total_cost}🌟, у вас {balance}🌟.",
            show_alert=True,
        )
        return

    success = await deduct_balance(uid, total_cost)
    if not success:
        await callback.answer("❌ Ошибка списания баланса.", show_alert=True)
        return

    task_id = await create_task(
        creator_id=uid,
        task_type=task_type,
        target_url=data.get("target_url"),
        description=data.get("description"),
        total_slots=slots,
        comment_texts=data.get("comment_texts") or None,
    )
    await set_cooldown(uid, "create")

    new_balance = await get_balance(uid)
    emoji = TASK_EMOJI[task_type]
    await callback.message.edit_text(
        f"✅ Задание создано!\n\n"
        f"ID: {task_id}\n"
        f"Тип: {emoji} {task_type.capitalize()}\n"
        f"Слотов: {slots}\n"
        f"Списано: {total_cost}🌟\n\n"
        f"Balance: {new_balance}🌟",
        reply_markup=promotion_menu_keyboard(),
    )
    await callback.answer()
    logger.info("Task %s created by %s (%s, %s slots)", task_id, uid, task_type, slots)
