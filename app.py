import os
import logging
from flask import Flask, request
import telegram
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")


app = Flask(__name__)


bot = telegram.Bot(token=TOKEN)
telegram_app = Application.builder().token(TOKEN).build()


async def start(update, context):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        f"Я бот, работающий на Render.com.\n"
        f"Отправь мне любое сообщение, и я отвечу."
    )

async def help_command(update, context):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "Я простой бот-оболочка.\n"
        "Доступные команды:\n"
        "/start - Начать работу\n"
        "/help - Показать эту справку"
    )

async def echo(update, context):
    """Обработчик всех текстовых сообщений"""
    await update.message.reply_text(f"Ты написал: {update.message.text}")


telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))


@app.route('/')
def index():
    """Главная страница для проверки работы"""
    return "Бот работает! ✅"

@app.route('/health')
def health():
    """Эндпоинт для проверки здоровья (Render его пингует)"""
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Эндпоинт, куда Telegram отправляет обновления"""
    try:
       
        update_data = request.get_json(force=True)
        update = telegram.Update.de_json(update_data, bot)
        
        
        asyncio.run(telegram_app.process_update(update))
        
        return "OK", 200
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return "Error", 500


if __name__ == "__main__":
    import asyncio
    
   
    port = int(os.environ.get("PORT", 10000))
    
 
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        
        async def setup_webhook():
            await bot.delete_webhook()
            await bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook set to {webhook_url}")
        
        asyncio.run(setup_webhook())
    
   
    app.run(host="0.0.0.0", port=port)
