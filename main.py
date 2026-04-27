import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from middlewares import BanCheckMiddleware, LoggingMiddleware
from scheduler import create_scheduler

from handlers.start import router as start_router
from handlers.submit import router as submit_router
from handlers.pull import router as pull_router
from handlers.execute_task import router as execute_router
from handlers.create_task import router as create_task_router
from handlers.moderation import router as moderation_router
from handlers.verification import router as verification_router
from handlers.user_commands import router as user_commands_router
from handlers.admin import router as admin_router
from handlers.cards import router as cards_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set. Exiting.")
        sys.exit(1)

    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())

    # Роутеры — порядок важен:
    # admin-group роутеры первыми, чтобы их фильтры F.chat.id обрабатывались раньше общих
    dp.include_router(moderation_router)
    dp.include_router(verification_router)
    dp.include_router(admin_router)
    dp.include_router(cards_router)
    dp.include_router(start_router)
    dp.include_router(submit_router)
    dp.include_router(pull_router)
    dp.include_router(execute_router)
    dp.include_router(create_task_router)
    dp.include_router(user_commands_router)

    scheduler = create_scheduler()
    scheduler.start()

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
