import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_GROUP_IDS = list(map(int, os.getenv("ADMIN_GROUP_ID").split(",")))
CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "-1003033694255"))
THREADS_URL: str = os.getenv(
    "THREADS_URL",
    "https://www.threads.com/@chernovikspace?igshid=NTc4MTIwNjQ2YQ=="
)

# Начальный баланс нового пользователя
STARTING_BALANCE: int = 2

# Стоимость создания задания и награда исполнителю (за 1 слот)
TASK_CONFIG: dict = {
    "like":    {"cost": 2,  "reward": 1},
    "comment": {"cost": 8,  "reward": 6},
    "repost":  {"cost": 9,  "reward": 7},
    "follow":  {"cost": 10, "reward": 7},
}

# Кулдауны в секундах
COOLDOWNS: dict = {
    "like":    600,    # 10 минут
    "comment": 3600,   # 60 минут
    "repost":  10800,  # 180 минут
    "follow":  7200,   # 120 минут
    "execute": 1200,   # 20 минут (выполнение заданий)
    "create":  21600,  # 6 часов  (создание задания)
    "report":  21600,  # 6 часов  (жалобы)
}

# Дневные лимиты
DAILY_LIMITS: dict = {
    "like":    20,
    "comment": 15,
    "repost":  5,
    "follow":  15,
}

# Эмодзи типов заданий
TASK_EMOJI: dict = {
    "like":    "👍",
    "comment": "✍️",
    "repost":  "🤝",
    "follow":  "👉",
}

DB_PATH: str = "chernovik.db"
