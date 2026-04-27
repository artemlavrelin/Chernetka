from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def submission_moderation_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💬 Ответить автору",
            callback_data=f"sub_reply_{submission_id}"
        )],
    ])


def execution_moderation_keyboard(execution_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять",   callback_data=f"exec_approve_{execution_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"exec_reject_{execution_id}"),
        ],
    ])


def verification_moderation_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять",   callback_data=f"ver_approve_{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"ver_reject_{user_id}"),
        ],
    ])
