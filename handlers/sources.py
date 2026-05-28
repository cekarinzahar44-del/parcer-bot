from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import (
    SOURCE_TYPES, get_sources, get_source, create_source,
    toggle_source, delete_source, get_logs
)
from keyboards.kb import (
    source_type_kb, sources_list_kb, source_card_kb,
    confirm_delete_kb, cancel_kb, skip_cancel_kb, main_menu
)

router = Router()

LOG_STATUS = {"ok": "✅", "error": "❌", "partial": "⚠️"}


def fmt_source_card(s: dict) -> str:
    cfg = s["config"]
    status = "✅ Активен" if s["active"] else "⏸ На паузе"
    last = s.get("last_parsed") or "никогда"
    if last != "никогда":
        last = last[:16]

    cfg_lines = []
    for k, v in cfg.items():
        if v:
            cfg_lines.append(f"  • {k}: {v}")

    return (
        f"📡 <b>{s['name']}</b>\n"
        f"🏷 Тип: {SOURCE_TYPES.get(s['type'], s['type'])}\n"
        f"📌 Статус: {status}\n"
        f"🕐 Последний парсинг: {last}\n"
        f"📦 Всего запусков: {s.get('parse_count', 0)}\n\n"
        f"⚙️ Конфигурация:\n" + "\n".join(cfg_lines)
    )


@router.message(F.text == "📡 Источники")
async def show_sources(message: Message, user_id: int):
    sources = await get_sources(user_id)
    if not sources:
        await message.answer(
            "У вас нет источников.\n\nНажмите кнопку ниже чтобы добавить первый!",
            reply_markup=sources_list_kb([])
        )
        return
    await message.answer(
        f"📡 <b>Ваши источники ({len(sources)}):</b>",
        reply_markup=sources_list_kb(sources)
    )


@router.callback_query(F.data == "source:list")
async def cb_sources_list(call: CallbackQuery, user_id: int):
    sources = await get_sources(user_id)
    await call.message.edit_text(
        f"📡 <b>Ваши источники ({len(sources)}):</b>",
        reply_markup=sources_list_kb(sources)
    )
    await call.answer()


@router.callback_query(F.data.startswith("source:") & ~F.data.in_({"source:add", "source:list"}))
async def cb_source_card(call: CallbackQuery):
    source_id = int(call.data.split(":")[1])
    s = await get_source(source_id)
    if not s:
        await call.answer("Источник не найден", show_alert=True)
        return
    await call.message.edit_text(fmt_source_card(s), reply_markup=source_card_kb(source_id, bool(s["active"])))
    await call.answer()


@router.callback_query(F.data.startswith("toggle:"))
async def cb_toggle(call: CallbackQuery):
    source_id = int(call.data.split(":")[1])
    new_state = await toggle_source(source_id)
    s = await get_source(source_id)
    await call.message.edit_text(fmt_source_card(s), reply_markup=source_card_kb(source_id, new_state))
    await call.answer("✅ Активирован" if new_state else "⏸ Приостановлен")


@router.callback_query(F.data.startswith("delete:"))
async def cb_delete_confirm(call: CallbackQuery):
    source_id = int(call.data.split(":")[1])
    s = await get_source(source_id)
    await call.message.edit_text(
        f"⚠️ Удалить источник <b>{s['name']}</b> и все данные?\nОтменить нельзя.",
        reply_markup=confirm_delete_kb(source_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_delete(call: CallbackQuery, user_id: int):
    source_id = int(call.data.split(":")[1])
    await delete_source(source_id)
    sources = await get_sources(user_id)
    await call.message.edit_text(
        f"🗑 Источник удалён.\n\n📡 <b>Ваши источники ({len(sources)}):</b>",
        reply_markup=sources_list_kb(sources)
    )
    await call.answer()


@router.callback_query(F.data.startswith("logs:"))
async def cb_logs(call: CallbackQuery):
    source_id = int(call.data.split(":")[1])
    logs = await get_logs(source_id, limit=5)
    if not logs:
        await call.answer("Лог пуст", show_alert=True)
        return
    lines = ["📋 <b>Последние запуски:</b>\n"]
    for log in logs:
        icon = LOG_STATUS.get(log["status"], "•")
        lines.append(
            f"{icon} {log['created_at'][:16]} | "
            f"+{log['new_items']} / {log['total_items']} | "
            f"{log['duration_ms']}мс"
            + (f"\n   ⚠️ {log['error_msg']}" if log.get("error_msg") else "")
        )
    await call.message.answer("\n".join(lines))
    await call.answer()


# ═══════════════════════════════════════════════════════════
# FSM — ДОБАВЛЕНИЕ ИСТОЧНИКА
# ═══════════════════════════════════════════════════════════

class AddSourceForm(StatesGroup):
    choose_type  = State()
    source_name  = State()
    # Currency
    curr_codes   = State()
    # News/RSS
    news_url     = State()
    news_kw      = State()
    # GitHub
    gh_lang      = State()
    # Weather
    wth_city     = State()


@router.callback_query(F.data == "source:add")
async def add_source_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddSourceForm.choose_type)
    await call.message.answer("Выберите тип источника:", reply_markup=source_type_kb())
    await call.answer()


@router.callback_query(AddSourceForm.choose_type, F.data.startswith("stype:"))
async def add_choose_type(call: CallbackQuery, state: FSMContext):
    stype = call.data.split(":")[1]
    await state.update_data(stype=stype)
    await state.set_state(AddSourceForm.source_name)
    await call.message.answer(
        f"Выбран: <b>{SOURCE_TYPES[stype]}</b>\n\nВведите название источника:",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(AddSourceForm.source_name)
async def add_source_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    data = await state.get_data()
    stype = data["stype"]

    if stype == "currency":
        await state.set_state(AddSourceForm.curr_codes)
        await message.answer(
            "💱 Коды валют через запятую (напр. USD,EUR,CNY):\n"
            "Доступны: USD, EUR, CNY, GBP, JPY, CHF, TRY, KZT",
            reply_markup=skip_cancel_kb()
        )
    elif stype == "news":
        await state.set_state(AddSourceForm.news_url)
        await message.answer(
            "📰 RSS-лента или пресет:\n"
            "<code>habr</code> / <code>rbc</code> / <code>lenta</code> / <code>vc</code>\n"
            "или полный URL RSS-ленты:"
        )
    elif stype == "github":
        await state.set_state(AddSourceForm.gh_lang)
        await message.answer(
            "🐙 Язык программирования (или пропустите для всех):\n"
            "python / javascript / rust / go / typescript / ...",
            reply_markup=skip_cancel_kb()
        )
    elif stype == "weather":
        await state.set_state(AddSourceForm.wth_city)
        await message.answer("🌤 Название города (на рус. или англ.):")
    else:
        await _save_source(message, state)


# Currency
@router.message(AddSourceForm.curr_codes)
async def add_curr_codes(message: Message, state: FSMContext):
    codes_raw = message.text if message.text != "⏭ Пропустить" else "USD,EUR,CNY"
    codes = [c.strip().upper() for c in codes_raw.split(",") if c.strip()]
    await state.update_data(config={"codes": codes})
    await _save_source(message, state)


# News
@router.message(AddSourceForm.news_url)
async def add_news_url(message: Message, state: FSMContext):
    await state.update_data(news_url=message.text.strip())
    await state.set_state(AddSourceForm.news_kw)
    await message.answer(
        "🔍 Ключевые слова через запятую (или пропустите):",
        reply_markup=skip_cancel_kb()
    )


@router.message(AddSourceForm.news_kw)
async def add_news_kw(message: Message, state: FSMContext):
    kw = []
    if message.text != "⏭ Пропустить":
        kw = [k.strip() for k in message.text.split(",") if k.strip()]
    data = await state.get_data()
    await state.update_data(config={"url": data["news_url"], "keywords": kw, "limit": 20})
    await _save_source(message, state)


# GitHub
@router.message(AddSourceForm.gh_lang)
async def add_gh_lang(message: Message, state: FSMContext):
    lang = "" if message.text == "⏭ Пропустить" else message.text.strip().lower()
    await state.update_data(config={"language": lang, "since": "daily"})
    await _save_source(message, state)


# Weather
@router.message(AddSourceForm.wth_city)
async def add_wth_city(message: Message, state: FSMContext):
    await state.update_data(config={"city": message.text.strip(), "days": 3})
    await _save_source(message, state)


async def _save_source(message: Message, state: FSMContext):
    from database import create_source
    data = await state.get_data()
    await state.clear()

    if "config" not in data:
        await message.answer("❌ Что-то пошло не так. Попробуйте снова.", reply_markup=main_menu())
        return

    user_id = message.from_user.id
    sid = await create_source(user_id, data["name"], data["stype"], data["config"])
    await message.answer(
        f"✅ Источник <b>«{data['name']}»</b> добавлен (ID: {sid})\n\n"
        f"Теперь можно запустить парсинг или настроить расписание.",
        reply_markup=main_menu()
    )
