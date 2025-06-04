import requests
import telegram
from telegram.ext import Updater, CommandHandler
from flask import Flask, request
import schedule
import time
import threading
import os
from datetime import datetime

# 初始化 Flask 和 Telegram Bot
app = Flask(__name__)
# bot_token = os.getenv('BOT_TOKEN')  # 從環境變數獲取Bot Token
# chat_id = os.getenv('CHAT_ID')      # 從環境變數獲取Chat ID
bot_token = "7833872327:AAH7NmY907DxOn-h4RBJbpszJIfDyZY_ioo"
chat_id = "5974801553"
bot = telegram.Bot(token=bot_token)

# MEXC API 端點
MEXC_FUNDING_RATE_URL = "https://contract.mexc.com/api/v1/contract/funding_rate"


# 檢查資金費率並發送訊息
def check_funding_rates():
    try:
        # 獲取 MEXC 資金費率數據
        response = requests.get(MEXC_FUNDING_RATE_URL)
        data = response.json()

        if not data.get("success") or data.get("code") != 0:
            print("Error fetching MEXC funding rates:", data)
            return

        # 篩選資金費率大於 1.5% 的交易對
        high_funding_pairs = []
        for item in data.get("data", []):
            funding_rate = float(item.get("fundingRate", 0))
            if funding_rate > 0.015:  # 1.5% = 0.015
                high_funding_pairs.append(f"{item['symbol']}: {funding_rate*100:.2f}%")

        # 如果有符合條件的交易對，發送訊息
        if high_funding_pairs:
            message = (
                f"資金費率大於1.5%的交易對 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n"
                + "\n".join(high_funding_pairs)
            )
            bot.send_message(chat_id=chat_id, text=message)
        else:
            print("No funding rates above 1.5% found.")

    except Exception as e:
        print(f"Error in check_funding_rates: {e}")


# 定時任務
def schedule_tasks():
    # 設置每天的檢查時間：03:55、07:55、11:55、15:55、19:55、23:55
    schedule.every().day.at("03:55").do(check_funding_rates)
    schedule.every().day.at("07:55").do(check_funding_rates)
    schedule.every().day.at("11:55").do(check_funding_rates)
    schedule.every().day.at("15:55").do(check_funding_rates)
    schedule.every().day.at("19:55").do(check_funding_rates)
    schedule.every().day.at("23:55").do(check_funding_rates)

    # 無限循環執行定時任務
    while True:
        schedule.run_pending()
        time.sleep(60)  # 每分鐘檢查一次


# Flask Webhook 路由
@app.route("/webhook", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)
    if update.message:
        bot.send_message(chat_id=update.message.chat_id, text="Bot is running!")
    return "OK"


# 啟動定時任務的線程
def start_scheduler():
    scheduler_thread = threading.Thread(target=schedule_tasks)
    scheduler_thread.daemon = True
    scheduler_thread.start()


# 主程式
if __name__ == "__main__":
    # 啟動定時任務
    start_scheduler()

    # 啟動 Flask 伺服器
    port = int(os.getenv("PORT", 8443))
    app.run(host="0.0.0.0", port=port)
