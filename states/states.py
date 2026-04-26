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
    select_type         = State()
    enter_url           = State()
    enter_description   = State()
    enter_slots         = State()
    enter_comment_text  = State()
    confirm             = State()


class ExecuteTaskStates(StatesGroup):
    enter_account = State()
    confirm       = State()


class ModerationStates(StatesGroup):
    reply_to_author = State()


class AdminStates(StatesGroup):
    broadcast      = State()
    balance_change = State()
