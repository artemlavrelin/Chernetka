import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_GROUP_ID: int = int(os.getenv("ADMIN_GROUP_ID", "-1003654223457"))
CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "-1003033694255"))
THREADS_URL: str = os.getenv(
    "THREADS_URL",
    "https://www.threads.com/@chernovikspace?igshid=NTc4MTIwNjQ2YQ=="
)
THREADS_POST_URL: str = os.getenv("THREADS_POST_URL", "")

# Список ID администраторов (ADMIN_IDS=111222,333444 в ENV)
_raw_admin_ids = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in _raw_admin_ids.split(",") if x.strip().isdigit()
]


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


STARTING_BALANCE: int = 2

TASK_CONFIG: dict = {
    "like":    {"cost": 2,  "reward": 1},
    "comment": {"cost": 8,  "reward": 6},
    "repost":  {"cost": 9,  "reward": 7},
    "follow":  {"cost": 10, "reward": 7},
}

COOLDOWNS: dict = {
    "like":       600,
    "comment":    3600,
    "repost":     10800,
    "follow":     7200,
    "execute":    1200,
    "create":     21600,
    "report":     21600,
    "submission": 21600,
}

DAILY_LIMITS: dict = {
    "like":    20,
    "comment": 15,
    "repost":  5,
    "follow":  15,
}

TASK_EMOJI: dict = {
    "like":    "👍",
    "comment": "✍️",
    "repost":  "🤝",
    "follow":  "👉",
}

CARD_EMOJIS: list[str] = [
    "🎆", "🎇", "🌅", "🌌", "🌁", "🌆", "🌠", "🌃",
    "🎑", "🏞️", "🗾", "🌄", "🏙️", "🌇", "🌉",
]

DB_PATH: str = "chernovik.db"

# Глобальный флаг остановки Pull (меняется через /pullstop / /pullstart)
PULL_ENABLED: bool = True
