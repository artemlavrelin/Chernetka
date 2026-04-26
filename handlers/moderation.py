import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from states import ModerationStates
from services.task_service import approve_execution, reject_execution, get_execution, get_submission
from services.user_service import add_balance, get_user
from config import ADMIN_GROUP_ID

router = Router()
logger = logging.getLogger(__name__)


# ─── Выполнения заданий: Принять / Отклонить ──────────────────────────────

@router.callback_query(F.data.startswith("exec_approve_"), F.message.chat.id == ADMIN_GROUP_ID)
async def approve_exec(callback: CallbackQuery, bot: Bot):
    execution_id = int(callback.data.split("_")[2])
    data = await approve_execution(execution_id)

    if not data:
        await callback.answer("❌ Исполнение уже обработано или не найдено.", show_alert=True)
        return

    reward = data["reward_per_slot"]
    executor_id = data["executor_id"]
    creator_id = data["creator_id"]

    # Начисляем награду исполнителю
    new_balance = await add_balance(executor_id, reward)

    # Уведомляем исполнителя
    try:
        executor = await get_user(executor_id)
        await bot.send_message(
            executor_id,
            f"✅ Задание принято!\n\n"
            f"Награда: +{reward}🌟\n"
            f"Текущий баланс: {new_balance}🌟"
        )
    except Exception:
        logger.warning("Cannot notify executor %s", executor_id)

    # Обновляем сообщение в группе
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(
        f"✅ Принято администратором @{callback.from_user.username or callback.from_user.id}\n"
        f"Исполнитель: {executor_id} | +{reward}🌟"
    )
    await callback.answer("✅ Принято")
    logger.info("Execution %s approved by %s", execution_id, callback.from_user.id)


@router.callback_query(F.data.startswith("exec_reject_"), F.message.chat.id == ADMIN_GROUP_ID)
async def reject_exec(callback: CallbackQuery, bot: Bot):
    execution_id = int(callback.data.split("_")[2])
    data = await reject_execution(execution_id)

    if not data:
        await callback.answer("❌ Исполнение уже обработано или не найдено.", show_alert=True)
        return

    cost = data["cost_per_slot"]
    creator_id = data["creator_id"]
    executor_id = data["executor_id"]

    # Возвращаем монеты заказчику
    await add_balance(creator_id, cost)

    # Уведомляем исполнителя
    try:
        await bot.send_message(
            executor_id,
            f"❌ Задание отклонено.\n\n"
            f"Заявка на выполнение не прошла проверку. 🌟 не начислены.\n"
            f"Будь внимателен к условиям задания."
        )
    except Exception:
        logger.warning("Cannot notify executor %s", executor_id)

    # Уведомляем заказчика о возврате
    try:
        await bot.send_message(
            creator_id,
            f"ℹ️ Одно выполнение вашего задания отклонено.\n"
            f"Возврат: +{cost}🌟. Слот снова доступен."
        )
    except Exception:
        logger.warning("Cannot notify creator %s", creator_id)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(
        f"❌ Отклонено администратором @{callback.from_user.username or callback.from_user.id}"
    )
    await callback.answer("❌ Отклонено")
    logger.info("Execution %s rejected by %s", execution_id, callback.from_user.id)


# ─── Ответ автору творческой работы ───────────────────────────────────────

@router.callback_query(F.data.startswith("sub_reply_"), F.message.chat.id == ADMIN_GROUP_ID)
async def start_reply_to_author(callback: CallbackQuery, state: FSMContext):
    submission_id = int(callback.data.split("_")[2])
    submission = await get_submission(submission_id)

    if not submission:
        await callback.answer("❌ Заявка не найдена.", show_alert=True)
        return

    await state.set_state(ModerationStates.reply_to_author)
    await state.update_data(
        author_id=submission["user_id"],
        submission_id=submission_id,
    )
    await callback.message.reply(
        f"✉️ Введи ответ для автора заявки #{submission_id}:\n"
        f"(следующее сообщение будет отправлено пользователю)"
    )
    await callback.answer()


@router.message(
    ModerationStates.reply_to_author,
    F.chat.id == ADMIN_GROUP_ID,
)
async def send_reply_to_author(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    author_id = data.get("author_id")
    submission_id = data.get("submission_id")
    await state.clear()

    if not author_id or not message.text:
        await message.reply("❗ Ошибка: нет текста или ID автора.")
        return

    admin_name = f"@{message.from_user.username}" if message.from_user.username else "Редакция"

    try:
        await bot.send_message(
            author_id,
            f"✉️ Ответ от редакции ЧЕРНОВИК:\n\n{message.text}"
        )
        await message.reply(f"✅ Ответ отправлен автору (ID: {author_id})")
    except Exception as e:
        await message.reply(f"❌ Не удалось отправить: {e}")

    logger.info("Admin %s replied to submission %s author %s",
                message.from_user.id, submission_id, author_id)
