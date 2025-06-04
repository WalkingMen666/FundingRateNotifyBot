import requests
import telegram
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from flask import Flask, request
import schedule
import time
import threading
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
# Initialize Flask and Telegram Bot
app = Flask(__name__)
bot_token = os.getenv("BOT_TOKEN")
chat_id = os.getenv("CHAT_ID")
webhook_url = os.getenv("WEBHOOK_URL")  # 新增 webhook URL
bot = telegram.Bot(token=bot_token)

# MEXC API endpoint
MEXC_FUNDING_RATE_URL = "https://contract.mexc.com/api/v1/contract/funding_rate"

# 創建 Application 實例
application = Application.builder().token(bot_token).build()


# Async function to send message
async def send_message_async(chat_id, text, reply_markup=None):
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


# 獲取前3高資金費率的函數
def get_top3_funding_rates():
    try:
        response = requests.get(MEXC_FUNDING_RATE_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("code") == 0:
                # 按資金費率排序，取前3名
                funding_data = data.get("data", [])
                sorted_data = sorted(
                    funding_data,
                    key=lambda x: float(x.get("fundingRate", 0)),
                    reverse=True,
                )
                top3 = sorted_data[:3]

                result = []
                for item in top3:
                    funding_rate = float(item.get("fundingRate", 0))
                    result.append(f"{item['symbol']}: {funding_rate*100:.4f}%")

                return result
    except Exception as e:
        print(f"Error fetching top3 funding rates: {e}")
    return None


# 處理 /start 命令
async def start_command(update, context):
    keyboard = [
        [InlineKeyboardButton("查詢前3高資金費率", callback_data="top3_funding")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "歡迎使用資金費率通知機器人！\n點擊下方按鈕查詢當前MEXC前3高資金費率：",
        reply_markup=reply_markup,
    )


# 新增直接查詢指令 - 不需要按鈕
async def funding_command(update, context):
    # 發送加載消息
    loading_msg = await update.message.reply_text("正在查詢資金費率數據...")

    # 獲取前3高資金費率
    top3_rates = get_top3_funding_rates()

    if top3_rates:
        message = (
            f"MEXC前3高資金費率 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n\n"
        )
        message += "\n".join([f"{i+1}. {rate}" for i, rate in enumerate(top3_rates)])

        # 添加按鈕供再次查詢
        keyboard = [[InlineKeyboardButton("重新查詢", callback_data="top3_funding")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await loading_msg.edit_text(text=message, reply_markup=reply_markup)
    else:
        await loading_msg.edit_text("查詢失敗，請稍後重試")


# 處理按鈕回調
async def button_callback(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "top3_funding":
        # 發送加載消息
        await query.edit_message_text(text="正在查詢資金費率數據...")

        # 獲取前3高資金費率
        top3_rates = get_top3_funding_rates()

        if top3_rates:
            message = f"MEXC前3高資金費率 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n\n"
            message += "\n".join(
                [f"{i+1}. {rate}" for i, rate in enumerate(top3_rates)]
            )

            # 重新添加按鈕
            keyboard = [
                [InlineKeyboardButton("重新查詢", callback_data="top3_funding")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(text=message, reply_markup=reply_markup)
        else:
            keyboard = [[InlineKeyboardButton("重試", callback_data="top3_funding")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="查詢失敗，請稍後重試", reply_markup=reply_markup
            )


# 註冊處理器
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("funding", funding_command))
application.add_handler(CallbackQueryHandler(button_callback))


# Flask Webhook 路由
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = telegram.Update.de_json(request.get_json(force=True), bot)
        # 創建新的事件循環來處理異步操作
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.process_update(update))
        loop.close()
        return "OK"
    except Exception as e:
        print(f"Webhook error: {e}")
        return "Error", 500


@app.route("/", methods=["GET"])
def index():
    return "Funding Rate Notify Bot is running!"


@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    try:
        if webhook_url:
            result = bot.set_webhook(url=f"{webhook_url}/webhook")
            return f"Webhook set successfully: {result}"
        else:
            return "WEBHOOK_URL not configured in .env"
    except Exception as e:
        return f"Failed to set webhook: {e}"


# 定時任務（如果需要）
def start_scheduler():
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(60)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    print(f"Scheduler started at {datetime.now()}")


# Main program
if __name__ == "__main__":
    print("Bot started in server mode!")
    print("Available endpoints:")
    print("/ - Bot status")
    print("/webhook - Telegram webhook")
    print("/set_webhook - Set webhook URL")

    # 啟動定時任務（如果需要）
    # start_scheduler()

    port = int(os.getenv("PORT", 8443))

    # 自動設置 webhook（如果配置了 WEBHOOK_URL）
    if webhook_url:
        try:
            result = bot.set_webhook(url=f"{webhook_url}/webhook")
            print(f"Webhook set: {result}")
        except Exception as e:
            print(f"Failed to set webhook: {e}")

    app.run(host="0.0.0.0", port=port, debug=False)
