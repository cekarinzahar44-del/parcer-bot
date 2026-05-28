"""
Диспетчер парсеров — вызывает нужный парсер по типу источника.
"""
import time
from database import (
    save_items, save_metrics, update_source_parsed,
    write_log, get_source
)
from parsers.other_parsers import parse_currency, parse_github, parse_news, parse_weather


PARSERS = {
    "currency": parse_currency,
    "github":   parse_github,
    "news":     parse_news,
    "weather":  parse_weather,
}


async def run_parser(source_id: int) -> dict:
    """
    Запускает парсер для source_id.
    Возвращает словарь с результатами.
    """
    source = await get_source(source_id)
    if not source:
        return {"ok": False, "error": "Источник не найден"}

    stype  = source["type"]
    config = source["config"]

    if stype not in PARSERS:
        return {"ok": False, "error": f"Неизвестный тип: {stype}"}

    t0 = time.monotonic()
    try:
        items, metrics = await PARSERS[stype](config)
        duration_ms = int((time.monotonic() - t0) * 1000)

        new_count, total = await save_items(source_id, items)
        await save_metrics(source_id, metrics)
        await update_source_parsed(source_id)
        await write_log(source_id, "ok", new_count, total, duration_ms=duration_ms)

        return {
            "ok":       True,
            "new":      new_count,
            "total":    total,
            "metrics":  metrics,
            "items":    items[:5],        # первые 5 для превью
            "duration": duration_ms,
        }

    except Exception as e:
        duration_ms = int((time.monotonic() - t0) * 1000)
        await write_log(source_id, "error", error_msg=str(e), duration_ms=duration_ms)
        return {"ok": False, "error": str(e)}
