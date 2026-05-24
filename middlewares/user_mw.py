from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Awaitable, Any

from config import ADMIN_IDS
from database import upsert_user


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            is_admin = user.id in ADMIN_IDS
            await upsert_user(user.id, user.username or "", user.full_name, is_admin)
            data["user_id"]  = user.id
            data["is_admin"] = is_admin

        return await handler(event, data)
