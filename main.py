import os
import json
import requests
import asyncio
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, BotCommand
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

# 全域變數
bot = None
application = None
initialized = False
background_loop = None
background_thread = None

# 獲取前3高資金費率絕對值的函數
def get_top3_funding_rates():
    try:
        response = requests.get(MEXC_FUNDING_RATE_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("code") == 0:
                rates = data.get("data", [])
                # 按資金費率絕對值排序並取前3
                sorted_rates = sorted(rates, key=lambda x: abs(float(x.get("fundingRate", 0))), reverse=True)
                top3 = sorted_rates[:3]
                
                result = []
                for rate in top3:
                    symbol = rate.get("symbol", "N/A")
                    funding_rate = float(rate.get("fundingRate", 0)) * 100
                    # 顯示實際數值（包含正負號）和絕對值
                    abs_rate = abs(funding_rate)
                    if funding_rate >= 0:
                        result.append(f"{symbol}: +{funding_rate:.4f}% (絕對值: {abs_rate:.4f}%)")
                    else:
                        result.append(f"{symbol}: {funding_rate:.4f}% (絕對值: {abs_rate:.4f}%)")
                
                return result
    except Exception as e:
        print(f"Error fetching top3 funding rates: {e}")
    return None

# 處理 /start 命令
async def start_command(update, context):
    keyboard = [
        [InlineKeyboardButton("查詢前3高資金費率絕對值", callback_data="top3_funding")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "歡迎使用資金費率通知機器人！\n點擊下方按鈕查詢當前MEXC前3高資金費率絕對值的交易對：",
        reply_markup=reply_markup,
    )

# 新增直接查詢指令
async def funding_command(update, context):
    loading_msg = await update.message.reply_text("正在查詢資金費率數據...")

    top3_rates = get_top3_funding_rates()

    if top3_rates:
        message = (
            f"MEXC前3高資金費率絕對值 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n\n"
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
            message = f"MEXC前3高資金費率絕對值 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n\n"
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

# 背景事件循環執行函數
def run_background_loop():
    global background_loop
    background_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(background_loop)
    background_loop.run_forever()

# 初始化函數
async def initialize_bot():
    global bot, application, initialized
    if not initialized:
        try:
            # 创建Bot和Application
            bot = Bot(token=bot_token)
            application = Application.builder().token(bot_token).build()
            
            # 初始化 Bot 和 Application
            await bot.initialize()
            await application.initialize()
            
            # 註冊處理器
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("funding", funding_command))
            application.add_handler(CallbackQueryHandler(button_callback))
            
            initialized = True
            print("Bot and Application initialized successfully!")
            
        except Exception as e:
            print(f"Error during initialization: {e}")
            raise

# 在背景事件循環中執行協程
def run_coroutine_in_background(coro):
    if background_loop and not background_loop.is_closed():
        future = asyncio.run_coroutine_threadsafe(coro, background_loop)
        return future.result(timeout=30)  # 30秒超時
    else:
        raise RuntimeError("Background loop is not running")

# Webhook路由
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # 獲取Telegram發送的數據
        json_str = request.get_data().decode('UTF-8')
        update = Update.de_json(json.loads(json_str), bot)
        
        # 在背景事件循環中處理更新
        async def process_update():
            await initialize_bot()
            await application.process_update(update)
        
        run_coroutine_in_background(process_update())
        
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
        await initialize_bot()
        
        if not webhook_url:
            print("Warning: WEBHOOK_URL not set, skipping webhook setup")
            return
        
        webhook_endpoint = f"{webhook_url.rstrip('/')}/webhook"
        await bot.set_webhook(url=webhook_endpoint)
        print(f"Webhook set to: {webhook_endpoint}")
        
        # 設置命令菜單
        await bot.set_my_commands([
            BotCommand("start", "開始使用機器人"),
            BotCommand("funding", "查詢前3高資金費率絕對值")
        ])
        print("Bot commands have been set!")
        
    except Exception as e:
        print(f"Error setting webhook: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Bot started in webhook mode!")
    print(f"Server running on port {port}")
    print(f"Webhook URL: {webhook_url}")
    
    # 啟動背景事件循環
    background_thread = threading.Thread(target=run_background_loop, daemon=True)
    background_thread.start()
    
    # 等待背景循環啟動
    time.sleep(1)
    
    # 設置webhook
    try:
        run_coroutine_in_background(set_webhook())
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
        if background_loop and not background_loop.is_closed():
            background_loop.call_soon_threadsafe(background_loop.stop)
    except Exception as e:
        print(f"Server error: {e}")