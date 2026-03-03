import os
import logging
import asyncio
from threading import Thread
from flask import Flask, request
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")

# Создаём Flask приложение
app = Flask(__name__)

# Создаём Telegram Bot и Application
bot = telegram.Bot(token=TOKEN)
telegram_app = Application.builder().token(TOKEN).build()

# --- Обработчики команд ---
async def start(update, context):
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        f"Я бот, работающий на Render.com.\n"
        f"Отправь мне любое сообщение, и я отвечу."
    )

async def help_command(update, context):
    await update.message.reply_text(
        "Я простой бот-оболочка.\n"
        "Доступные команды:\n"
        "/start - Начать работу\n"
        "/help - Показать эту справку"
    )

async def echo(update, context):
    await update.message.reply_text(f"Ты написал: {update.message.text}")

# Регистрируем обработчики
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# --- Запуск Telegram приложения в отдельном потоке ---
loop = asyncio.new_event_loop()

def run_bot():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telegram_app.initialize())
    loop.run_until_complete(telegram_app.start())
    logger.info("Telegram bot application started")
    loop.run_forever()

# Запускаем поток с ботом (daemon=True, чтобы он завершился при остановке Flask)
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
    """Принимает обновления от Telegram и передаёт их в бота"""
    try:
        update_data = request.get_json(force=True)
        update = telegram.Update.de_json(update_data, bot)
        # Безопасно ставим обработку обновления в цикл событий бота
        asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), loop)
        return "OK", 200
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return "Error", 500

# --- Завершение работы (для корректной остановки при перезапуске) ---
import atexit

def shutdown():
    logger.info("Shutting down Telegram bot application...")
    # Останавливаем приложение и цикл событий
    asyncio.run_coroutine_threadsafe(telegram_app.stop(), loop).result(timeout=5)
    asyncio.run_coroutine_threadsafe(telegram_app.shutdown(), loop).result(timeout=5)
    loop.call_soon_threadsafe(loop.stop)
    logger.info("Shutdown complete.")

atexit.register(shutdown)

# --- Запуск Flask сервера ---
if __name__ == "__main__":
    # Устанавливаем вебхук при старте
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        async def set_webhook():
            await bot.delete_webhook()
            await bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook set to {webhook_url}")
        asyncio.run(set_webhook())
    else:
        logger.warning("RENDER_EXTERNAL_URL not set, webhook not configured.")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

