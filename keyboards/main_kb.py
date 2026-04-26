from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎭 Отправить работу",  callback_data="submit_work")],
        [InlineKeyboardButton(text="🌀 Продвижение",       callback_data="promotion")],
    ])
