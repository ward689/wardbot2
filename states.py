from aiogram.fsm.state import State, StatesGroup


class AutoResponseStates(StatesGroup):
    add_response_chat = State()
    add_response_keyword = State()
    add_response_text = State()
    remove_response_chat = State()
    remove_response_keyword = State()


class AdminStates(StatesGroup):
    set_mute_duration = State()
    set_warn_limit = State()
    user_stats = State()
    warn = State()
    check_warns = State()
    clear_warns = State()
    mute = State()
    mute_duration = State()
    unmute = State()
    set_moderator = State()
    set_admin = State()
    set_level = State()
    set_level_input = State()
    get_channel_for_operator = State()
    setup_operator = State()
    get_channel_for_owner = State()
    setup_owner = State()
    add_whitelist = State()
    remove_whitelist = State()
