import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import ExecuteTaskStates
from keyboards.promotion_kb import execute_confirm_keyboard, pull_empty_keyboard
from keyboards.moderation_kb import execution_moderation_keyboard
from services.user_service import is_user_banned, get_user, get_balance
from services.task_service import (
    get_task, create_execution, set_execution_admin_msg,
    get_execution_count, pop_comment_text,
)
from services.cooldown_service import (
    check_cooldown, set_cooldown, check_daily_limit,
    increment_daily_count, get_daily_count,
)
from config import ADMIN_GROUP_ID, TASK_EMOJI, DAILY_LIMITS

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("pull_exec_"))
async def start_execute(callback: CallbackQuery, state: FSMContext):
    if await is_user_banned(callback.from_user.id):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return

    task_id = int(callback.data.split("_")[2])
    task = await get_task(task_id)
    if not task or task["status"] != "active" or task["remaining_slots"] <= 0:
        await callback.answer("❌ Задание уже недоступно.", show_alert=True)
        return

    user_id = callback.from_user.id
    ready, remaining = await check_cooldown(user_id, "execute")
    if not ready:
        m, s = remaining // 60, remaining % 60
        await callback.answer(f"⏳ Следующее выполнение через {m}м {s}с", show_alert=True)
        return

    task_type = task["task_type"]
    within_limit, _ = await check_daily_limit(user_id, task_type)
    if not within_limit:
        await callback.answer(
            f"📊 Дневной лимит {task_type} ({DAILY_LIMITS[task_type]}/день) исчерпан.",
            show_alert=True,
        )
        return

    await state.set_state(ExecuteTaskStates.enter_account)
    await state.update_data(task_id=task_id, task_type=task_type)

    balance = await get_balance(user_id)
    emoji = TASK_EMOJI.get(task_type, "⚡️")

    # Показываем реальную ссылку только сейчас
    text = (
        f"🧠 ВЫПОЛНЕНИЕ ЗАДАНИЯ\n\n"
        f"Тип: {emoji} {task_type.capitalize()}\n"
        f"🔗 {task['target_url']}\n\n"
    )
    if task_type == "comment":
        comment = await pop_comment_text(task_id)
        if comment:
            text += f"💬 Текст комментария:\n{comment}\n\n"
            await state.update_data(assigned_comment=comment)

    text += (
        f"⚠️ Нарушение условий задания ведёт к бану.\n\n"
        f"Введи свой @username на платформе:\n\n"
        f"Balance: {balance}🌟"
    )
    await callback.message.edit_text(text)
    await callback.answer()


@router.message(ExecuteTaskStates.enter_account)
async def receive_account(message: Message, state: FSMContext):
    account = message.text.strip() if message.text else ""
    if not account:
        await message.answer("❗ Введи @username аккаунта.")
        return

    data = await state.get_data()
    task = await get_task(data.get("task_id"))
    if not task:
        await state.clear()
        await message.answer("❌ Задание не найдено.")
        return

    await state.update_data(target_account=account)
    await state.set_state(ExecuteTaskStates.confirm)

    balance = await get_balance(message.from_user.id)
    emoji = TASK_EMOJI.get(task["task_type"], "⚡️")
    await message.answer(
        f"📋 Подтверди выполнение:\n\n"
        f"Тип: {emoji} {task['task_type'].capitalize()}\n"
        f"🔗 {task['target_url']}\n"
        f"Аккаунт: {account}\n\n"
        f"⚠️ Фейковые выполнения = 🚫 бан.\n\n"
        f"Balance: {balance}🌟",
        reply_markup=execute_confirm_keyboard(task["id"]),
    )


@router.callback_query(ExecuteTaskStates.confirm, F.data.startswith("exec_confirm_"))
async def confirm_execution(callback: CallbackQuery, state: FSMContext, bot: Bot):
    task_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    target_account = data.get("target_account")
    task_type = data.get("task_type")
    await state.clear()

    user_id = callback.from_user.id
    task = await get_task(task_id)
    if not task or task["status"] != "active" or task["remaining_slots"] <= 0:
        await callback.answer("❌ Задание уже недоступно.", show_alert=True)
        return

    execution_id = await create_execution(task_id, user_id, target_account)
    await set_cooldown(user_id, "execute")
    await set_cooldown(user_id, task_type)
    await increment_daily_count(user_id, task_type)

    await callback.message.edit_text(
        "✅ Заявка на выполнение отправлена!\n\n"
        "Ожидай проверки администратора. Результат придёт в личные сообщения."
    )
    await callback.answer()
    await _send_execution_to_admin(bot, execution_id, task, user_id, target_account, data)


async def _send_execution_to_admin(
    bot: Bot, execution_id: int, task: dict,
    executor_id: int, target_account: str, data: dict
):
    try:
        executor = await get_user(executor_id)
        creator = await get_user(task["creator_id"])

        exec_num, total = await get_execution_count(task["id"])
        emoji = TASK_EMOJI.get(task["task_type"], "⚡️")
        exec_uname = f"@{executor['username']}" if executor and executor.get("username") else f"ID:{executor_id}"
        creator_uname = f"@{creator['username']}" if creator and creator.get("username") else f"ID:{task['creator_id']}"

        like_cnt    = await get_daily_count(executor_id, "like")
        comment_cnt = await get_daily_count(executor_id, "comment")
        repost_cnt  = await get_daily_count(executor_id, "repost")
        follow_cnt  = await get_daily_count(executor_id, "follow")

        text = (
            f"🧠 ПРОВЕРКА\n\n"
            f"Task ID: {task['id']}\n"
            f"Пункт: {exec_num}/{total}\n"
            f"Type: {emoji} {task['task_type'].capitalize()}\n\n"
            f"Заказчик: {creator_uname}\n"
            f"Исполнитель: {exec_uname}\n\n"
            f"Аккаунт исполнения: {target_account}\n"
            f"🔗 {task['target_url']}\n"
        )
        if data.get("assigned_comment"):
            text += f"\n💬 Текст комментария:\n{data['assigned_comment']}\n"
        text += (
            f"\n📊 ДНЕВНЫЕ ЛИМИТЫ (00:00 GMT):\n"
            f"Like: {like_cnt}/{DAILY_LIMITS['like']}\n"
            f"Comments: {comment_cnt}/{DAILY_LIMITS['comment']}\n"
            f"Repost: {repost_cnt}/{DAILY_LIMITS['repost']}\n"
            f"Follow: {follow_cnt}/{DAILY_LIMITS['follow']}"
        )
        msg = await bot.send_message(
            ADMIN_GROUP_ID, text,
            reply_markup=execution_moderation_keyboard(execution_id),
        )
        await set_execution_admin_msg(execution_id, msg.message_id)
    except Exception as e:
        logger.error("Failed to send execution to admin: %s", e)
