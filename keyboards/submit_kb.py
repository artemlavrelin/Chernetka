from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def content_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст (стихи / тексты)",  callback_data="stype_text")],
        [InlineKeyboardButton(text="🖼 Изображение (арт / фото)", callback_data="stype_image")],
        [InlineKeyboardButton(text="🎵 Аудио (музыка)",            callback_data="stype_audio")],
        [InlineKeyboardButton(text="◀️ Назад",                     callback_data="main_menu")],
    ])


def ask_description_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Добавить описание", callback_data="sub_add_desc")],
        [InlineKeyboardButton(text="➡️ Пропустить",        callback_data="sub_skip_desc")],
        [InlineKeyboardButton(text="◀️ Назад",             callback_data="submit_work")],
    ])


def ask_link_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Добавить ссылку", callback_data="sub_add_link")],
        [InlineKeyboardButton(text="➡️ Пропустить",      callback_data="sub_skip_link")],
        [InlineKeyboardButton(text="◀️ Назад",            callback_data="submit_work")],
    ])


def publication_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕶 Анонимно",     callback_data="sub_mode_anon")],
        [InlineKeyboardButton(text="👤 Telegram-имя", callback_data="sub_mode_public")],
        [InlineKeyboardButton(text="◀️ Назад",        callback_data="submit_work")],
    ])
