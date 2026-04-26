from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def promotion_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ Pull — лента заданий", callback_data="pull_start")],
        [InlineKeyboardButton(text="➕ Создать задание",       callback_data="create_task")],
        [InlineKeyboardButton(text="◀️ Назад",                callback_data="main_menu")],
    ])


def task_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 Like",    callback_data="ct_type_like")],
        [InlineKeyboardButton(text="✍️ Comment", callback_data="ct_type_comment")],
        [InlineKeyboardButton(text="🤝 Repost",  callback_data="ct_type_repost")],
        [InlineKeyboardButton(text="👉 Follow",  callback_data="ct_type_follow")],
        [InlineKeyboardButton(text="◀️ Назад",   callback_data="promotion")],
    ])


def task_card_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👉 Дальше",    callback_data="pull_next"),
            InlineKeyboardButton(text="✅ Выполнить", callback_data=f"pull_exec_{task_id}"),
        ],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="promotion")],
    ])


def pull_empty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Смотреть заново", callback_data="pull_start")],
        [InlineKeyboardButton(text="◀️ Назад",           callback_data="promotion")],
    ])


def execute_confirm_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выполнено",  callback_data=f"exec_confirm_{task_id}"),
            InlineKeyboardButton(text="❌ Отказаться", callback_data="pull_start"),
        ],
    ])


def confirm_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать",   callback_data="ct_confirm")],
        [InlineKeyboardButton(text="❌ Отменить",  callback_data="promotion")],
    ])


def skip_desc_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Пропустить описание", callback_data="ct_skip_desc")],
    ])
