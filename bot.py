import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, REPORTS_DIR
from database import init_db
from middlewares.user_mw import UserMiddleware
from utils.scheduler import scheduler_loop
from handlers import start, sources, parsing, export_sched

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

os.makedirs(REPORTS_DIR, exist_ok=True)


async def main():
    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    # Ð Ð¾ÑƒÑ‚ÐµÑ€Ñ‹
    dp.include_router(start.router)
    dp.include_router(sources.router)
    dp.include_router(parsing.router)
    dp.include_router(export_sched.router)

    # ÐŸÐ»Ð°Ð½Ð¸Ñ€Ð¾Ð²Ñ‰Ð¸Ðº
    asyncio.create_task(scheduler_loop(bot))

    logger.info("ðŸš€ Parser Bot Ð·Ð°Ð¿ÑƒÑ‰ÐµÐ½!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
