import asyncio
from telegram import Bot

async def main():
    bot = Bot(token="7833872327:AAH7NmY907DxOn-h4RBJbpszJIfDyZY_ioo")
    await bot.send_message(chat_id="5974801553", text="Test message")

if __name__ == "__main__":
    asyncio.run(main())