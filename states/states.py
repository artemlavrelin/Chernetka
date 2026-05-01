from aiogram.fsm.state import State, StatesGroup


class SubmitStates(StatesGroup):
    select_type   = State()
    send_content  = State()
    ask_desc      = State()
    add_desc      = State()
    ask_link      = State()
    add_link      = State()
    select_mode   = State()


class PullStates(StatesGroup):
    browsing = State()


class CreateTaskStates(StatesGroup):
    select_type          = State()
    enter_url            = State()
    enter_description    = State()
    enter_slots          = State()
    enter_comment_texts  = State()
    confirm              = State()


class ExecuteTaskStates(StatesGroup):
    enter_account = State()
    confirm       = State()


class ModerationStates(StatesGroup):
    reply_to_author = State()


class VerificationStates(StatesGroup):
    enter_username = State()


class ReportStates(StatesGroup):
    enter_text = State()


class AdminStates(StatesGroup):
    broadcast      = State()
    balance_change = State()


class CardBrowseStates(StatesGroup):
    browsing      = State()
    author_filter = State()


class AddCardStates(StatesGroup):
    # Шаг 1 — источник
    enter_post_url  = State()
    # Шаг 2 — предпросмотр (после авто-парсинга)
    preview         = State()
    # Шаг 3a — ручное редактирование медиа
    edit_file       = State()
    # Шаг 3b — ручное редактирование описания
    edit_desc       = State()
    # Шаг 4 — категория
    enter_category  = State()
    # Шаг 5 — artist_id
    enter_author_id = State()
