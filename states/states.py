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
    enter_comment_texts  = State()   # сбор текстов комментариев по одному
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
    enter_post_url   = State()
    enter_file       = State()
    enter_desc       = State()
    enter_category   = State()
    enter_author_id  = State()
    confirm          = State()
