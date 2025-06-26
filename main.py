import os
import json
import requests
import asyncio
import threading
import time
import schedule
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, render_template_string
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
current_top3_rates = []
last_update_time = None

# HTML 模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>MEXC 資金費率監控</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="60">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 40px; 
            background-color: #f5f5f5; 
        }
        .container { 
            max-width: 800px; 
            margin: 0 auto; 
            background: white; 
            padding: 30px; 
            border-radius: 10px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
        }
        h1 { 
            color: #333; 
            text-align: center; 
            margin-bottom: 30px; 
        }
        .update-time { 
            text-align: center; 
            color: #666; 
            margin-bottom: 20px; 
        }
        .rate-item { 
            background: #f8f9fa; 
            padding: 15px; 
            margin: 10px 0; 
            border-radius: 5px; 
            border-left: 4px solid #007bff; 
        }
        .symbol { 
            font-weight: bold; 
            font-size: 18px; 
            color: #333; 
        }
        .rate { 
            font-size: 16px; 
            color: #666; 
        }
        .high-rate { 
            border-left-color: #dc3545; 
            background: #fff5f5; 
        }
        .status { 
            text-align: center; 
            padding: 20px; 
            color: #888; 
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>MEXC 資金費率絕對值排行榜</h1>
        {% if last_update_time %}
        <div class="update-time">
            最後更新: {{ last_update_time }}
        </div>
        {% endif %}
        
        {% if rates %}
            {% for rate in rates %}
            <div class="rate-item {% if rate.abs_rate > 1.0 %}high-rate{% endif %}">
                <div class="symbol">{{ loop.index }}. {{ rate.symbol }}</div>
                <div class="rate">
                    實際費率: {{ rate.actual_rate }}% | 
                    絕對值: {{ rate.abs_rate }}%
                    {% if rate.abs_rate > 1.0 %}
                    <strong style="color: #dc3545;"> (高風險)</strong>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        {% else %}
        <div class="status">
            正在獲取資金費率數據...
        </div>
        {% endif %}
        
        <div style="text-align: center; margin-top: 30px; color: #888; font-size: 14px;">
            頁面每分鐘自動刷新 | 
            監控時間: 03:55, 07:55, 11:55, 15:55, 19:55, 23:55
        </div>
    </div>
</body>
</html>
"""

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
                    abs_rate = abs(funding_rate)
                    
                    result.append({
                        'symbol': symbol,
                        'actual_rate': f"{funding_rate:+.4f}",
                        'abs_rate': abs_rate,
                        'raw_rate': funding_rate
                    })
                
                return result
    except Exception as e:
        print(f"Error fetching top3 funding rates: {e}")
    return None

# 更新資金費率數據
def update_funding_rates():
    global current_top3_rates, last_update_time
    try:
        rates = get_top3_funding_rates()
        if rates:
            current_top3_rates = rates
            last_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"Updated funding rates at {last_update_time}")
        else:
            print("Failed to update funding rates")
    except Exception as e:
        print(f"Error updating funding rates: {e}")

# 發送Telegram通知
async def send_telegram_notification(rates):
    try:
        if not bot or not chat_id:
            print("Bot or chat_id not configured")
            return
            
        message = f"🚨 高資金費率警報 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n\n"
        message += "發現資金費率絕對值超過1%的交易對:\n\n"
        
        for i, rate in enumerate(rates):
            if rate['abs_rate'] > 1.0:
                message += f"{i+1}. {rate['symbol']}: {rate['actual_rate']}% (絕對值: {rate['abs_rate']:.4f}%)\n"
        
        await bot.send_message(chat_id=chat_id, text=message)
        print("Telegram notification sent successfully")
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")

# 檢查並發送通知
def check_and_notify():
    try:
        current_time = datetime.now()
        current_minute = current_time.strftime('%H:%M')
        
        # 檢查是否為指定時間
        if current_minute in ['03:55', '07:55', '11:55', '15:55', '19:55', '23:55']:
            print(f"Checking rates at {current_minute}")
            
            if current_top3_rates:
                high_rates = [rate for rate in current_top3_rates if rate['abs_rate'] > 1.0]
                
                if high_rates:
                    print(f"Found {len(high_rates)} high funding rates")
                    # 在背景循環中發送通知
                    if background_loop and not background_loop.is_closed():
                        asyncio.run_coroutine_threadsafe(
                            send_telegram_notification(current_top3_rates), 
                            background_loop
                        )
                else:
                    print("No high funding rates found")
            else:
                print("No current rates data available")
    except Exception as e:
        print(f"Error in check_and_notify: {e}")

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

    if current_top3_rates:
        message = f"MEXC前3高資金費率絕對值 ({last_update_time}):\n\n"
        for i, rate in enumerate(current_top3_rates):
            message += f"{i+1}. {rate['symbol']}: {rate['actual_rate']}% (絕對值: {rate['abs_rate']:.4f}%)\n"

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

        if current_top3_rates:
            message = f"MEXC前3高資金費率絕對值 ({last_update_time}):\n\n"
            for i, rate in enumerate(current_top3_rates):
                message += f"{i+1}. {rate['symbol']}: {rate['actual_rate']}% (絕對值: {rate['abs_rate']:.4f}%)\n"

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

# 排程任務執行函數
def run_scheduler():
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            print(f"Error in scheduler: {e}")
            time.sleep(60)

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
        return future.result(timeout=30)
    else:
        raise RuntimeError("Background loop is not running")

# Webhook路由
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('UTF-8')
        update = Update.de_json(json.loads(json_str), bot)
        
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

# 主頁路由 - 顯示當前前3高資金費率
@app.route('/', methods=['GET'])
def home():
    return render_template_string(HTML_TEMPLATE, 
                                rates=current_top3_rates, 
                                last_update_time=last_update_time)

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
    
    # 初始更新資金費率數據
    update_funding_rates()
    
    # 設置排程任務
    schedule.every().minute.do(update_funding_rates)  # 每分鐘更新
    schedule.every().minute.do(check_and_notify)      # 每分鐘檢查通知
    
    # 啟動排程器
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
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