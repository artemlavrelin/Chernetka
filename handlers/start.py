import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.main_kb import main_keyboard
from services.user_service import get_or_create_user, is_user_banned

router = Router()
logger = logging.getLogger(__name__)

START_TEXT = (
    "ЧЕРНОВИК — пространство для творчества без фильтров.\n"
    "стихи, музыка, визуал, тексты. можно анонимно или с указанием Telegram-имени.\n\n"
    "отправь свою работу — мы рассмотрим её для публикации"
)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    if user["is_banned"]:
        await message.answer("🚫 Вы заблокированы в этом боте.")
        return
    await message.answer(START_TEXT, reply_markup=main_keyboard())


@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username)
    if user["is_banned"]:
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return
    await callback.message.edit_text(START_TEXT, reply_markup=main_keyboard())
    await callback.answer()
