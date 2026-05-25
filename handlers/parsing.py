from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import (
    get_sources, get_source, get_items, get_items_count,
    get_latest_metrics, clear_items
)
from parsers.dispatcher import run_parser
from parsers.hh_parser  import fmt_hh_item
from parsers.other_parsers import fmt_currency_item, fmt_github_item, fmt_news_item, fmt_weather_item
from keyboards.kb import (
    sources_list_kb, source_card_kb, paginate_kb, main_menu, cancel_kb
)
from utils.html_utils import escape_html, sanitize_html

router = Router()

FMT_FUNCS = {
    "hh":       fmt_hh_item,
    "currency": fmt_currency_item,
    "github":   fmt_github_item,
    "news":     fmt_news_item,
    "weather":  fmt_weather_item,
}
PER_PAGE = 5


def fmt_metrics(source: dict, metrics: dict) -> str:
    stype = source["type"]
    lines = [f"📊 <b>Метрики: {source['name']}</b>\n"]

    if stype == "hh":
        lines += [
            f"📋 Вакансий: {metrics.get('total_vacancies', '—')}",
            f"💰 Средняя з/п: {int(metrics['avg_salary']):,} ₽" if metrics.get("avg_salary") else "💰 З/п: нет данных",
            f"⬇️ Минимум: {int(metrics.get('min_salary',0)):,} ₽" if metrics.get("min_salary") else "",
            f"⬆️ Максимум: {int(metrics.get('max_salary',0)):,} ₽" if metrics.get("max_salary") else "",
            f"📊 Медиана: {int(metrics.get('median_salary',0)):,} ₽" if metrics.get("median_salary") else "",
            f"🛠 Топ навыки: {metrics.get('top_skills','—')}",
        ]
    elif stype == "currency":
        for k, v in metrics.items():
            if k.startswith("rate_"):
                code = k[5:]
                lines.append(f"💱 {code}: {v:,.4f} ₽")
        lines.append(f"📅 Дата ЦБ: {metrics.get('as_of_date','—')}")
    elif stype == "github":
        lines += [
            f"🐙 Репозиториев: {metrics.get('total_repos','—')}",
            f"💻 Язык: {metrics.get('language','all')}",
            f"📅 Период: {metrics.get('period','daily')}",
            f"🥇 Топ: {metrics.get('top_repo','—')}",
        ]
    elif stype == "news":
        lines += [
            f"📰 Новостей: {metrics.get('total_news','—')}",
            f"🔍 Фильтр: {metrics.get('filtered_by','—')}",
        ]
    elif stype == "weather":
        lines += [
            f"🌡 Температура: {metrics.get('temp_c','—')}°C",
            f"🤔 Ощущается: {metrics.get('feels_like','—')}°C",
            f"💧 Влажность: {metrics.get('humidity','—')}%",
            f"💨 Ветер: {metrics.get('wind_kmph','—')} км/ч",
            f"☁️ {metrics.get('description','—')}",
        ]
    else:
        for k, v in metrics.items():
            lines.append(f"  {k}: {v}")

    return "\n".join(l for l in lines if l)


# ─── Запустить парсинг ────────────────────────────────────

@router.message(F.text == "▶️ Запустить парсинг")
async def parse_choose_source(message: Message, user_id: int):
    sources = await get_sources(user_id, active_only=True)
    if not sources:
        await message.answer("Нет активных источников. Сначала добавьте источник в разделе 📡.")
        return
    await message.answer("Выберите источник для парсинга:", reply_markup=sources_list_kb(sources))


@router.callback_query(F.data.startswith("parse_now:"))
async def cb_parse_now(call: CallbackQuery):
    source_id = int(call.data.split(":")[1])
    s = await get_source(source_id)

    wait_msg = await call.message.answer(f"⏳ Парсю <b>{escape_html(s['name'])}</b>...")
    await call.answer()

    result = await run_parser(source_id)

    await wait_msg.delete()

    if not result["ok"]:
        from utils.html_utils import escape_html as _e
        await call.message.answer(f"❌ Ошибка: {_e(result['error'])}")
        return

    metrics_text = fmt_metrics(s, result["metrics"])
    await call.message.answer(
        f"✅ <b>Парсинг завершён за {result['duration']}мс</b>\n\n"
        f"🆕 Новых записей: <b>{result['new']}</b>\n"
        f"📦 Всего в базе: <b>{result['total']}</b>\n\n"
        f"{metrics_text}",
        reply_markup=source_card_kb(source_id, True)
    )


# ─── Просмотр данных ──────────────────────────────────────

@router.callback_query(F.data.startswith("view_data:"))
async def cb_view_data(call: CallbackQuery):
    _, source_id, offset = call.data.split(":")
    source_id, offset = int(source_id), int(offset)

    s = await get_source(source_id)
    items = await get_items(source_id, limit=PER_PAGE, offset=offset)
    total = await get_items_count(source_id)

    if not items:
        await call.answer("Данных нет. Запустите парсинг.", show_alert=True)
        return

    fmt = FMT_FUNCS.get(s["type"], lambda x: str(x.get("title", x)))
    lines = [
        f"📦 <b>{s['name']}</b> | {offset+1}–{min(offset+PER_PAGE, total)} из {total}\n"
    ]
    for item in items:
        lines.append(fmt(item["data"]))
        lines.append("─" * 30)

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=paginate_kb(source_id, offset, total, PER_PAGE),
        disable_web_page_preview=True
    )
    await call.answer()


# ─── Метрики ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("metrics:"))
async def cb_metrics(call: CallbackQuery):
    source_id = int(call.data.split(":")[1])
    s = await get_source(source_id)
    metrics = await get_latest_metrics(source_id)
    if not metrics:
        await call.answer("Метрик пока нет. Запустите парсинг.", show_alert=True)
        return
    await call.message.answer(fmt_metrics(s, metrics))
    await call.answer()


# ─── Поиск ───────────────────────────────────────────────

class SearchForm(StatesGroup):
    query = State()
    _source_id = State()


@router.callback_query(F.data.startswith("search:"))
async def search_start(call: CallbackQuery, state: FSMContext):
    source_id = int(call.data.split(":")[1])
    await state.set_data({"source_id": source_id})
    await state.set_state(SearchForm.query)
    await call.message.answer("🔍 Введите поисковый запрос:", reply_markup=cancel_kb())
    await call.answer()


@router.message(SearchForm.query, F.text != "❌ Отмена")
async def search_execute(message: Message, state: FSMContext):
    data = await state.get_data()
    source_id = data["source_id"]
    await state.clear()

    s = await get_source(source_id)
    items = await get_items(source_id, limit=10, search=message.text)

    if not items:
        await message.answer(f"🔍 По запросу «{message.text}» ничего не найдено.")
        return

    fmt = FMT_FUNCS.get(s["type"], lambda x: str(x.get("title", x)))
    lines = [f"🔍 Результаты по «{message.text}» ({len(items)}):\n"]
    for item in items[:5]:
        lines.append(fmt(item["data"]))
        lines.append("─" * 30)
    await message.answer("\n".join(lines), disable_web_page_preview=True, reply_markup=main_menu())
