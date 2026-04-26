import logging
from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Логирует каждое входящее сообщение и callback."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        if isinstance(event, Message):
            logger.debug(
                "MSG user=%s chat=%s text=%r",
                event.from_user.id if event.from_user else "?",
                event.chat.id,
                (event.text or "")[:80],
            )
        elif isinstance(event, CallbackQuery):
            logger.debug(
                "CBQ user=%s data=%r",
                event.from_user.id,
                event.data,
            )
        return await handler(event, data)
