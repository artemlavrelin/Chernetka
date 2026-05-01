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
    enter_post_url  = State()
    preview         = State()
    edit_file       = State()
    edit_desc       = State()
    enter_category  = State()
    enter_author_id = State()


class AddArtistStates(StatesGroup):
    enter_link       = State()   # 1) ссылка
    enter_display_id = State()   # 2) #id1727
    enter_username   = State()   # 3) @username


class EditArtistStates(StatesGroup):
    choose_field     = State()   # выбор поля
    enter_link       = State()
    enter_display_id = State()
    enter_username   = State()
