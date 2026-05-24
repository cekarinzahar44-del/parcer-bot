import asyncio
import logging
from aiogram import Bot
from database import get_due_schedules, advance_schedule
from parsers.dispatcher import run_parser

logger = logging.getLogger(__name__)


async def scheduler_loop(bot: Bot):
    """
    Каждые 30 секунд проверяет расписание и запускает парсеры.
    Отправляет уведомление владельцу после успешного парсинга.
    """
    logger.info("⏰ Планировщик запущен")
    while True:
        try:
            due = await get_due_schedules()
            for sched in due:
                source_id   = sched["source_id"]
                interval_m  = sched["interval_m"]
                user_id     = sched["user_id"]
                source_name = sched["name"]

                logger.info(f"🔄 Авто-парсинг: {source_name} (id={source_id})")

                result = await run_parser(source_id)
                await advance_schedule(sched["id"], interval_m)

                # Уведомляем пользователя
                if result["ok"] and result["new"] > 0:
                    try:
                        await bot.send_message(
                            user_id,
                            f"🔔 <b>Авто-парсинг завершён</b>\n\n"
                            f"📡 {source_name}\n"
                            f"🆕 Новых записей: <b>{result['new']}</b>\n"
                            f"📦 Всего в базе: <b>{result['total']}</b>"
                        )
                    except Exception:
                        pass
                elif not result["ok"]:
                    try:
                        await bot.send_message(
                            user_id,
                            f"⚠️ Ошибка авто-парсинга <b>{source_name}</b>:\n{result['error']}"
                        )
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Scheduler error: {e}")

        await asyncio.sleep(30)
