import requests
import telegram
from telegram.ext import Updater, CommandHandler
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
bot = telegram.Bot(token=bot_token)

# MEXC API endpoint
MEXC_FUNDING_RATE_URL = "https://contract.mexc.com/api/v1/contract/funding_rate"


# Async function to send message
async def send_message_async(chat_id, text):
    await bot.send_message(chat_id=chat_id, text=text)


# Check funding rates and send message
def check_funding_rates():
    try:
        # Fetch MEXC funding rate data
        for _ in range(3):  # Retry 3 times
            response = requests.get(MEXC_FUNDING_RATE_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("code") == 0:
                    break
            print(f"Retrying MEXC API... Attempt {_+1}")
            time.sleep(5)
        else:
            print("Failed to fetch MEXC funding rates after retries")
            return

        # Filter trading pairs with funding rate > 1.5%
        high_funding_pairs = []
        for item in data.get("data", []):
            funding_rate = float(item.get("fundingRate", 0))
            if funding_rate > 0.015:  # 1.5% = 0.015
                high_funding_pairs.append(f"{item['symbol']}: {funding_rate*100:.2f}%")

        # Send message if there are qualifying pairs
        if high_funding_pairs:
            message = (
                f"資金費率大於1.5%的交易對 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n"
                + "\n".join(high_funding_pairs)
            )
            # Run async send_message in a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(send_message_async(chat_id, message))
            loop.close()
        else:
            print("No funding rates above 1.5% found.")

    except Exception as e:
        print(f"Error in check_funding_rates: {e}")


# Scheduled tasks
def schedule_tasks():
    print("Scheduler started at", datetime.now())
    # Schedule checks at 03:55, 07:55, 11:55, 15:55, 19:55, 23:55
    schedule.every().day.at("03:55").do(check_funding_rates)
    schedule.every().day.at("07:55").do(check_funding_rates)
    schedule.every().day.at("11:55").do(check_funding_rates)
    schedule.every().day.at("15:55").do(check_funding_rates)
    schedule.every().day.at("19:55").do(check_funding_rates)
    schedule.every().day.at("23:55").do(check_funding_rates)

    # Run scheduled tasks
    while True:
        schedule.run_pending()
        time.sleep(60)


# Flask Webhook route
@app.route("/webhook", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)
    if update.message:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            send_message_async(update.message.chat_id, "Bot is running!")
        )
        loop.close()
    return "OK"


@app.route("/", methods=["GET"])
def index():
    return "Funding Rate Notify Bot is running!"


# Start scheduler thread
def start_scheduler():
    scheduler_thread = threading.Thread(target=schedule_tasks)
    scheduler_thread.daemon = True
    scheduler_thread.start()


# Main program
if __name__ == "__main__":
    start_scheduler()
    port = int(os.getenv("PORT", 8443))
    app.run(host="0.0.0.0", port=port)
