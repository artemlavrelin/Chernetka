from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def card_keyboard(card_id: int, prev_available: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура под карточкой контента."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="-3♥️", callback_data=f"card_vote_{card_id}_-3"),
            InlineKeyboardButton(text="-2♥️", callback_data=f"card_vote_{card_id}_-2"),
            InlineKeyboardButton(text="-1♥️", callback_data=f"card_vote_{card_id}_-1"),
            InlineKeyboardButton(text="+1♥️", callback_data=f"card_vote_{card_id}_1"),
            InlineKeyboardButton(text="+2♥️", callback_data=f"card_vote_{card_id}_2"),
            InlineKeyboardButton(text="+3♥️", callback_data=f"card_vote_{card_id}_3"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Предыдущая", callback_data="card_prev"),
            InlineKeyboardButton(text="➡️ Следующая",  callback_data="card_next"),
        ],
        [
            InlineKeyboardButton(text="💫 Автор",        callback_data=f"card_author_{card_id}"),
            InlineKeyboardButton(text="‼️ Пожаловаться", callback_data=f"card_report_{card_id}"),
        ],
        [InlineKeyboardButton(text="◀️ Назад",           callback_data="main_menu")],
    ])


def card_author_filter_keyboard(author_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Все работы автора", callback_data=f"card_filter_author_{author_id}")],
        [InlineKeyboardButton(text="◀️ Назад",             callback_data="card_back_to_current")],
    ])
