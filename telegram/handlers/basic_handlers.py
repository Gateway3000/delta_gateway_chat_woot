from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message()
async def test_handler(message: Message) -> Message:
    return await message.answer("Your message has been delivered! ✅")
