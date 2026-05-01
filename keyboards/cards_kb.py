from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ── Пользовательские клавиатуры ──────────────────────────────────────────────

def card_keyboard(card_id: int) -> InlineKeyboardMarkup:
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
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ])


def card_author_filter_keyboard(artist_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📂 Все работы автора",
            callback_data=f"card_filter_author_{artist_id}"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="card_back_to_current")],
    ])


# ── Админские клавиатуры (все callback с префиксом adm_) ─────────────────────

def adm_addcard_source_kb() -> InlineKeyboardMarkup:
    """Шаг 1 — выбор источника карточки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Ссылка на пост канала", callback_data="adm_addcard_src_url")],
        [InlineKeyboardButton(text="✏️ Ввести вручную",        callback_data="adm_addcard_src_manual")],
        [InlineKeyboardButton(text="↩️ Назад",                  callback_data="adm_addcard_cancel")],
    ])


def adm_addcard_preview_kb() -> InlineKeyboardMarkup:
    """Шаг 2 — предпросмотр карточки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оставить",  callback_data="adm_addcard_preview_keep")],
        [InlineKeyboardButton(text="✏️ Изменить",  callback_data="adm_addcard_preview_edit")],
        [InlineKeyboardButton(text="↩️ Назад",     callback_data="adm_addcard_cancel")],
    ])


def adm_addcard_edit_choose_kb() -> InlineKeyboardMarkup:
    """Выбор что редактировать."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Медиа",       callback_data="adm_addcard_edit_file")],
        [InlineKeyboardButton(text="📝 Описание",    callback_data="adm_addcard_edit_desc")],
        [InlineKeyboardButton(text="↩️ К предпросмотру", callback_data="adm_addcard_back_preview")],
    ])


def adm_addcard_skip_kb(back_cb: str) -> InlineKeyboardMarkup:
    """Пропустить шаг / назад."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Пропустить", callback_data="adm_addcard_skip")],
        [InlineKeyboardButton(text="↩️ Назад",       callback_data=back_cb)],
    ])


def adm_addcard_category_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="adm_addcard_cancel")],
    ])


def adm_addcard_author_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Без автора", callback_data="adm_addcard_no_author")],
        [InlineKeyboardButton(text="↩️ Назад",       callback_data="adm_addcard_cancel")],
    ])


def adm_panel_kb() -> InlineKeyboardMarkup:
    """Главная кнопка «назад» для admin-ответов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Готово", callback_data="adm_done")],
    ])
