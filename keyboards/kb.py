from aiogram.types import (
    InlineKeyboardMarkup, ReplyKeyboardMarkup,
    KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from database import SOURCE_TYPES, REPORT_FORMATS


def main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📡 Источники"),  KeyboardButton(text="▶️ Запустить парсинг"))
    kb.row(KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📄 Отчёты"))
    kb.row(KeyboardButton(text="⏰ Расписание"), KeyboardButton(text="❓ Помощь"))
    return kb.as_markup(resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="❌ Отмена"))
    return kb.as_markup(resize_keyboard=True)


def skip_cancel_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="⏭ Пропустить"), KeyboardButton(text="❌ Отмена"))
    return kb.as_markup(resize_keyboard=True)


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


# ─── Источники ────────────────────────────────────────────

def source_type_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in SOURCE_TYPES.items():
        b.button(text=label, callback_data=f"stype:{key}")
    b.adjust(2)
    return b.as_markup()


def sources_list_kb(sources: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in sources:
        status = "✅" if s["active"] else "⏸"
        b.button(
            text=f"{status} {s['name']} [{s['type']}]",
            callback_data=f"source:{s['id']}"
        )
    b.button(text="➕ Добавить источник", callback_data="source:add")
    b.adjust(1)
    return b.as_markup()


def source_card_kb(source_id: int, active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="▶️ Парсить сейчас",  callback_data=f"parse_now:{source_id}")
    b.button(text="📄 Просмотр данных", callback_data=f"view_data:{source_id}:0")
    b.button(text="📊 Метрики",          callback_data=f"metrics:{source_id}")
    b.button(text="📥 Экспорт",          callback_data=f"export:{source_id}")
    b.button(text="⏰ Расписание",       callback_data=f"sched:{source_id}")
    b.button(text="📋 Лог",             callback_data=f"logs:{source_id}")
    toggle = "⏸ Приостановить" if active else "▶️ Возобновить"
    b.button(text=toggle, callback_data=f"toggle:{source_id}")
    b.button(text="🗑 Удалить",          callback_data=f"delete:{source_id}")
    b.button(text="◀️ Назад",           callback_data="source:list")
    b.adjust(2)
    return b.as_markup()


def paginate_kb(source_id: int, offset: int, total: int, per_page: int = 5) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if offset > 0:
        b.button(text="◀️ Назад", callback_data=f"view_data:{source_id}:{offset - per_page}")
    if offset + per_page < total:
        b.button(text="Вперёд ▶️", callback_data=f"view_data:{source_id}:{offset + per_page}")
    b.button(text="🔍 Поиск", callback_data=f"search:{source_id}")
    b.button(text="◀️ К источнику", callback_data=f"source:{source_id}")
    b.adjust(2)
    return b.as_markup()


# ─── Экспорт ──────────────────────────────────────────────

def export_format_kb(source_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    icons = {"xlsx": "📊", "csv": "📋", "json": "🔧", "txt": "📄"}
    for fmt in REPORT_FORMATS:
        b.button(text=f"{icons[fmt]} {fmt.upper()}", callback_data=f"do_export:{source_id}:{fmt}")
    b.adjust(2)
    return b.as_markup()


# ─── Расписание ───────────────────────────────────────────

def schedule_interval_kb(source_id: int) -> InlineKeyboardMarkup:
    intervals = [
        ("30 мин",  30), ("1 час",   60), ("2 часа",  120),
        ("6 часов", 360), ("12 часов", 720), ("24 часа", 1440),
    ]
    b = InlineKeyboardBuilder()
    for label, minutes in intervals:
        b.button(text=label, callback_data=f"sched_set:{source_id}:{minutes}")
    b.button(text="❌ Отключить", callback_data=f"sched_del:{source_id}")
    b.adjust(3)
    return b.as_markup()


# ─── Подтверждение ────────────────────────────────────────

def confirm_delete_kb(source_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Да, удалить", callback_data=f"confirm_delete:{source_id}")
    b.button(text="❌ Отмена",      callback_data=f"source:{source_id}")
    b.adjust(2)
    return b.as_markup()
