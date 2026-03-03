import os
import logging
import asyncio
import sys
from threading import Thread
from flask import Flask, request
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")

app = Flask(__name__)

bot = telegram.Bot(token=TOKEN)
telegram_app = Application.builder().token(TOKEN).build()

# --- Обработчики команд с подробным логированием ---
async def start(update, context):
    try:
        user = update.effective_user
        logger.info(f"🚀 /start received from user {user.id} (@{user.username})")
        sent = await update.message.reply_text(
            f"Привет, {user.first_name}! 👋\n\n"
            f"Я бот, работающий на Render.com.\n"
            f"Отправь мне любое сообщение, и я отвечу."
        )
        logger.info(f"✅ Reply sent to {user.id}, message_id: {sent.message_id}")
    except Exception as e:
        logger.error(f"❌ Error in start handler: {e}", exc_info=True)

async def help_command(update, context):
    try:
        user = update.effective_user
        logger.info(f"ℹ️ /help from user {user.id}")
        sent = await update.message.reply_text(
            "Я простой бот-оболочка.\n"
            "Доступные команды:\n"
            "/start - Начать работу\n"
            "/help - Показать эту справку"
        )
        logger.info(f"✅ Help reply sent to {user.id}")
    except Exception as e:
        logger.error(f"❌ Error in help handler: {e}", exc_info=True)

async def echo(update, context):
    try:
        user = update.effective_user
        text = update.message.text
        logger.info(f"💬 Echo from {user.id}: {text}")
        sent = await update.message.reply_text(f"Ты написал: {text}")
        logger.info(f"✅ Echo reply sent to {user.id}")
    except Exception as e:
        logger.error(f"❌ Error in echo handler: {e}", exc_info=True)

# Регистрируем обработчики
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# --- Запуск Telegram приложения в отдельном потоке ---
loop = asyncio.new_event_loop()

def run_bot():
    asyncio.set_event_loop(loop)
    try:
        logger.info("🔄 Initializing Telegram application...")
        loop.run_until_complete(telegram_app.initialize())
        logger.info("✅ Telegram application initialized")
        
        logger.info("🔄 Starting Telegram application...")
        loop.run_until_complete(telegram_app.start())
        logger.info("✅ Telegram application started successfully")
    except Exception as e:
        logger.error(f"💥 Failed to start Telegram app: {e}", exc_info=True)
        return
    loop.run_forever()

bot_thread = Thread(target=run_bot, daemon=True)
bot_thread.start()

# --- Flask маршруты ---
@app.route('/')
def index():
    return "Бот работает! ✅"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    # ========== ДИАГНОСТИЧЕСКАЯ ЗАГЛУШКА ==========
    # Эти строки будут логировать каждый запрос от Telegram
    logger.info(f"🔥🔥🔥 WEBHOOK HIT! Headers: {dict(request.headers)}")
    logger.info(f"🔥🔥🔥 Raw data: {request.get_data(as_text=True)}")
    # ==============================================
    
    try:
        update_data = request.get_json(force=True)
        update_id = update_data.get('update_id')
        logger.info(f"📨 Received update {update_id}")
        
        update = telegram.Update.de_json(update_data, bot)
        
        # Отправляем обработку в цикл событий бота
        future = asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), loop)
        
        # Ждём немного, чтобы поймать ошибки
        try:
            future.result(timeout=3)
            logger.info(f"✅ Update {update_id} processed successfully")
        except asyncio.TimeoutError:
            logger.warning(f"⏳ Update {update_id} processing is taking longer than 3 seconds")
        except Exception as e:
            logger.error(f"💥 Error processing update {update_id}: {e}", exc_info=True)
            
        return "OK", 200
    except Exception as e:
        logger.error(f"🔥 Webhook error: {e}", exc_info=True)
        return "Error", 500

# --- Завершение работы ---
import atexit

def shutdown():
    logger.info("🛑 Shutting down Telegram bot application...")
    try:
        future_stop = asyncio.run_coroutine_threadsafe(telegram_app.stop(), loop)
        future_stop.result(timeout=5)
        logger.info("✅ Application stopped")
        
        future_shutdown = asyncio.run_coroutine_threadsafe(telegram_app.shutdown(), loop)
        future_shutdown.result(timeout=5)
        logger.info("✅ Application shut down")
        
        loop.call_soon_threadsafe(loop.stop)
        logger.info("🛑 Loop stopped")
    except Exception as e:
        logger.error(f"💥 Error during shutdown: {e}", exc_info=True)

atexit.register(shutdown)

# --- Установка вебхука при старте ---
def setup_webhook():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        logger.info(f"🔗 Attempting to set webhook to {webhook_url}")
        
        async def _set_webhook():
            try:
                current = await bot.get_webhook_info()
                logger.info(f"📡 Current webhook: {current.url}")
                if current.url == webhook_url:
                    logger.info("✅ Webhook already set correctly")
                    return
                
                await bot.delete_webhook()
                logger.info("🗑️ Old webhook deleted")
                
                result = await bot.set_webhook(url=webhook_url)
                logger.info(f"✅ Webhook set result: {result}")
                
                new_info = await bot.get_webhook_info()
                logger.info(f"📡 New webhook info: {new_info}")
            except Exception as e:
                logger.error(f"💥 Failed to set webhook: {e}", exc_info=True)
        
        # Временный цикл
        temp_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(temp_loop)
        temp_loop.run_until_complete(_set_webhook())
        temp_loop.close()
    else:
        logger.error("❌ RENDER_EXTERNAL_URL is not set. Webhook not configured.")

setup_webhook()

# --- Для локального запуска (не используется на Render, но оставлено для тестов) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

