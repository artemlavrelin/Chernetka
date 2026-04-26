import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.user_service import daily_balance_topup

logger = logging.getLogger(__name__)


async def _daily_topup_job():
    count = await daily_balance_topup()
    logger.info("Daily balance top-up: %s users topped up to 1🌟", count)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Каждый день в 00:00 UTC
    scheduler.add_job(
        _daily_topup_job,
        trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
        id="daily_topup",
        replace_existing=True,
        misfire_grace_time=300,
    )

    logger.info("Scheduler configured: daily balance top-up at 00:00 UTC")
    return scheduler
