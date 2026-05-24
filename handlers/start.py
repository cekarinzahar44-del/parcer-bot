from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from keyboards.kb import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        f"Я — бот для парсинга и агрегации данных.\n\n"
        f"<b>Что умею:</b>\n"
        f"• 👔 Парсить вакансии с HeadHunter\n"
        f"• 💱 Отслеживать курсы валют (ЦБ РФ)\n"
        f"• 📰 Мониторить RSS-новости\n"
        f"• 🐙 Собирать GitHub Trending\n"
        f"• 🌤 Получать прогноз погоды\n"
        f"• 📊 Строить Excel/CSV/JSON отчёты\n"
        f"• ⏰ Парсить по расписанию автоматически\n\n"
        f"Начните с добавления источника 👇",
        reply_markup=main_menu()
    )


@router.message(F.text == "❌ Отмена")
async def cancel(message: Message):
    from aiogram.fsm.context import FSMContext
    await message.answer("Отменено.", reply_markup=main_menu())
