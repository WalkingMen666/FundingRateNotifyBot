import os
import json
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

load_dotenv()

# 配置
bot_token = os.getenv("BOT_TOKEN")
chat_id = os.getenv("CHAT_ID")
webhook_url = os.getenv("WEBHOOK_URL")
port = int(os.getenv("PORT", 10000))

# MEXC API endpoint
MEXC_FUNDING_RATE_URL = "https://contract.mexc.com/api/v1/contract/funding_rate"

# 创建Flask应用
app = Flask(__name__)

# 创建Bot和Application
bot = Bot(token=bot_token)
application = Application.builder().token(bot_token).build()

# 獲取前3高資金費率的函數
def get_top3_funding_rates():
    try:
        response = requests.get(MEXC_FUNDING_RATE_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("code") == 0:
                rates = data.get("data", [])
                # 按資金費率排序並取前3
                sorted_rates = sorted(rates, key=lambda x: float(x.get("fundingRate", 0)), reverse=True)
                top3 = sorted_rates[:3]
                
                result = []
                for rate in top3:
                    symbol = rate.get("symbol", "N/A")
                    funding_rate = float(rate.get("fundingRate", 0)) * 100
                    result.append(f"{symbol}: {funding_rate:.4f}%")
                
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

# 新增直接查詢指令
async def funding_command(update, context):
    loading_msg = await update.message.reply_text("正在查詢資金費率數據...")

    top3_rates = get_top3_funding_rates()

    if top3_rates:
        message = (
            f"MEXC前3高資金費率 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n\n"
        )
        message += "\n".join([f"{i+1}. {rate}" for i, rate in enumerate(top3_rates)])

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
        await query.edit_message_text(text="正在查詢資金費率數據...")

        top3_rates = get_top3_funding_rates()

        if top3_rates:
            message = f"MEXC前3高資金費率 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n\n"
            message += "\n".join(
                [f"{i+1}. {rate}" for i, rate in enumerate(top3_rates)]
            )

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

# 全域變數來追蹤初始化狀態
app_initialized = False

# 初始化 Application 的函數
async def initialize_application():
    global app_initialized
    if not app_initialized:
        await application.initialize()
        app_initialized = True
        print("Application initialized successfully!")

# Webhook路由 - 修復版本
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # 獲取Telegram發送的數據
        json_str = request.get_data().decode('UTF-8')
        update = Update.de_json(json.loads(json_str), bot)
        
        # 確保 application 已初始化後再處理更新
        async def process_update_wrapper():
            await initialize_application()
            await application.process_update(update)
        
        # 使用asyncio運行異步處理
        asyncio.run(process_update_wrapper())
        
        return 'OK'
    except Exception as e:
        print(f"Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return 'Error', 500

# 健康檢查路由
@app.route('/health', methods=['GET'])
def health():
    return 'Bot is running!', 200

# 添加根路由
@app.route('/', methods=['GET'])
def home():
    return 'MEXC Funding Rate Notify Bot is running!', 200

# 設置webhook
async def set_webhook():
    try:
        # 初始化 Application
        await initialize_application()
        
        if not webhook_url:
            print("Warning: WEBHOOK_URL not set, skipping webhook setup")
            return
        
        webhook_endpoint = f"{webhook_url.rstrip('/')}/webhook"
        await bot.set_webhook(url=webhook_endpoint)
        print(f"Webhook set to: {webhook_endpoint}")
        
        # 設置命令菜單
        from telegram import BotCommand
        await bot.set_my_commands([
            BotCommand("start", "開始使用機器人"),
            BotCommand("funding", "查詢前3高資金費率")
        ])
        print("Bot commands have been set!")
        
    except Exception as e:
        print(f"Error setting webhook: {e}")
        import traceback
        traceback.print_exc()

# 刪除webhook
async def delete_webhook():
    try:
        await bot.delete_webhook()
        print("Webhook deleted")
    except Exception as e:
        print(f"Error deleting webhook: {e}")

if __name__ == "__main__":
    print("Bot started in webhook mode!")
    print(f"Server running on port {port}")
    print(f"Webhook URL: {webhook_url}")
    
    # 設置webhook
    try:
        asyncio.run(set_webhook())
    except Exception as e:
        print(f"Webhook setup failed: {e}")
        print("Continuing to start Flask server...")
    
    try:
        # 啟動Flask服務器
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("Bot stopped by user")
        try:
            asyncio.run(delete_webhook())
        except:
            pass
    except Exception as e:
        print(f"Server error: {e}")