import logging
from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from services.user_service import get_or_create_user

logger = logging.getLogger(__name__)


class BanCheckMiddleware(BaseMiddleware):
    """Блокирует забаненных пользователей на уровне middleware."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        user = None

        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            db_user = await get_or_create_user(user.id, user.username)
            if db_user["is_banned"]:
                # Молча отклоняем
                if isinstance(event, CallbackQuery):
                    await event.answer("🚫 Вы заблокированы в этом боте.", show_alert=True)
                elif isinstance(event, Message):
                    await event.answer("🚫 Вы заблокированы в этом боте.")
                logger.info("Blocked update from banned user %s", user.id)
                return

        return await handler(event, data)
