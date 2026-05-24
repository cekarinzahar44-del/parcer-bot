import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile

from database import (
    get_sources, get_source, get_all_items_for_export, save_report,
    get_reports, get_global_stats, set_schedule, delete_schedule,
    advance_schedule, clear_items, get_latest_metrics
)
from reports.generator import generate_report
from keyboards.kb import (
    export_format_kb, schedule_interval_kb, source_card_kb, main_menu
)

router = Router()


# ═══════════════════════════════════════════════════════════
# 📥  ЭКСПОРТ
# ═══════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("export:"))
async def cb_export_menu(call: CallbackQuery):
    source_id = int(call.data.split(":")[1])
    s = await get_source(source_id)
    await call.message.edit_text(
        f"📥 Экспорт данных из <b>{s['name']}</b>\n\nВыберите формат:",
        reply_markup=export_format_kb(source_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("do_export:"))
async def cb_do_export(call: CallbackQuery, bot: Bot):
    _, source_id, fmt = call.data.split(":")
    source_id = int(source_id)

    s = await get_source(source_id)
    wait_msg = await call.message.answer(f"⏳ Генерирую {fmt.upper()} отчёт...")
    await call.answer()

    items = await get_all_items_for_export(source_id)
    if not items:
        await wait_msg.delete()
        await call.message.answer("❌ Нет данных для экспорта. Сначала запустите парсинг.")
        return

    try:
        filepath, row_count = await generate_report(s, items, fmt)
        await save_report(call.from_user.id, source_id, fmt, os.path.basename(filepath), row_count)

        await wait_msg.delete()
        file = FSInputFile(filepath, filename=os.path.basename(filepath))

        caption = (
            f"📥 <b>Отчёт: {s['name']}</b>\n"
            f"📋 Формат: {fmt.upper()}\n"
            f"📦 Записей: {row_count}"
        )
        await bot.send_document(call.from_user.id, file, caption=caption)

    except Exception as e:
        await wait_msg.delete()
        await call.message.answer(f"❌ Ошибка генерации: {e}")


@router.message(F.text == "📄 Отчёты")
async def show_reports(message: Message, user_id: int):
    reports = await get_reports(user_id, limit=10)
    if not reports:
        await message.answer("Отчётов пока нет. Экспортируйте данные из источника.")
        return
    lines = ["📄 <b>История отчётов:</b>\n"]
    for r in reports:
        lines.append(
            f"• {r['created_at'][:16]} | {r['format'].upper()} | "
            f"{r.get('source_name','?')} | {r['row_count']} строк"
        )
    await message.answer("\n".join(lines))


# ═══════════════════════════════════════════════════════════
# ⏰  РАСПИСАНИЕ
# ═══════════════════════════════════════════════════════════

@router.message(F.text == "⏰ Расписание")
async def show_schedule_info(message: Message, user_id: int):
    sources = await get_sources(user_id, active_only=True)
    if not sources:
        await message.answer("Нет активных источников для расписания.")
        return
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    for s in sources:
        b.button(text=f"⏰ {s['name']}", callback_data=f"sched:{s['id']}")
    b.adjust(1)
    await message.answer(
        "⏰ <b>Расписание авто-парсинга</b>\n\nВыберите источник:",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data.startswith("sched:"))
async def cb_schedule_menu(call: CallbackQuery):
    source_id = int(call.data.split(":")[1])
    s = await get_source(source_id)
    await call.message.edit_text(
        f"⏰ Расписание для <b>{s['name']}</b>\n\nВыберите интервал:",
        reply_markup=schedule_interval_kb(source_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("sched_set:"))
async def cb_schedule_set(call: CallbackQuery):
    _, source_id, interval = call.data.split(":")
    source_id, interval = int(source_id), int(interval)

    await set_schedule(source_id, interval)
    s = await get_source(source_id)
    hours = interval // 60
    mins  = interval % 60
    label = f"{hours}ч {mins}мин" if mins else f"{hours}ч"
    await call.message.edit_text(
        f"✅ Расписание установлено!\n\n"
        f"📡 Источник: {s['name']}\n"
        f"⏱ Интервал: каждые {label}",
        reply_markup=source_card_kb(source_id, True)
    )
    await call.answer("✅ Расписание сохранено")


@router.callback_query(F.data.startswith("sched_del:"))
async def cb_schedule_del(call: CallbackQuery):
    source_id = int(call.data.split(":")[1])
    await delete_schedule(source_id)
    s = await get_source(source_id)
    await call.message.edit_text(
        f"❌ Расписание отключено для <b>{s['name']}</b>",
        reply_markup=source_card_kb(source_id, True)
    )
    await call.answer("Расписание отключено")


# ═══════════════════════════════════════════════════════════
# 📊  СТАТИСТИКА
# ═══════════════════════════════════════════════════════════

@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message, user_id: int):
    stats = await get_global_stats(user_id)
    sources = await get_sources(user_id)

    lines = [
        "📊 <b>Общая статистика</b>\n",
        f"📡 Источников: <b>{stats['sources']}</b>",
        f"📦 Записей в базе: <b>{stats['total_items']}</b>",
        f"📄 Отчётов создано: <b>{stats['total_reports']}</b>",
        f"🕐 Последний парсинг: {(stats['last_parse'] or 'никогда')[:16]}",
    ]

    if sources:
        lines.append("\n📡 <b>Источники:</b>")
        for s in sources:
            status = "✅" if s["active"] else "⏸"
            last = (s.get("last_parsed") or "—")[:16]
            lines.append(f"  {status} {s['name']} | Запусков: {s.get('parse_count',0)} | Посл.: {last}")

    await message.answer("\n".join(lines))


# ═══════════════════════════════════════════════════════════
# ❓  ПОМОЩЬ
# ═══════════════════════════════════════════════════════════

@router.message(F.text == "❓ Помощь")
async def show_help(message: Message):
    await message.answer(
        "❓ <b>Справка по боту</b>\n\n"
        "<b>📡 Источники</b> — управление источниками парсинга.\n"
        "Добавляйте, удаляйте, приостанавливайте.\n\n"
        "<b>▶️ Запустить парсинг</b> — ручной запуск парсера.\n"
        "Данные сохраняются в базу, новые выделяются.\n\n"
        "<b>📊 Статистика</b> — общие метрики и состояние источников.\n\n"
        "<b>📄 Отчёты</b> — история экспортированных файлов.\n\n"
        "<b>⏰ Расписание</b> — авто-парсинг по расписанию.\n\n"
        "<b>Поддерживаемые источники:</b>\n"
        "👔 HeadHunter — вакансии с зарплатами и навыками\n"
        "💱 ЦБ РФ — актуальные курсы валют\n"
        "📰 RSS — новости с фильтром по ключевым словам\n"
        "🐙 GitHub Trending — топ репозитории дня\n"
        "🌤 Погода — прогноз до 3 дней\n\n"
        "<b>Форматы экспорта:</b> XLSX, CSV, JSON, TXT"
    )
