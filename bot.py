"""
Twitter → Telegram Tracker Bot
Точка входа
"""
import asyncio
import logging
import sys
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Добавляем директорию бота в путь
BOT_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(BOT_DIR))

from config import BOT_TOKEN, LOGS_DIR
from database import db
from handlers import setup_routers
from services.tracker_worker import init_tracker_worker
from services.scheduler import init_scheduler
from services.twitter import twitter_service
from services.payment import payment_service

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "bot.log", encoding="utf-8"),
    ]
)

# Уменьшаем шум от библиотек
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Действия при запуске"""
    logger.info("=" * 50)
    logger.info("Starting Twitter Tracker Bot...")
    
    # Подключаем БД
    await db.connect()
    logger.info("✓ Database connected")
    
    # Инициализируем и запускаем воркеры
    tracker = init_tracker_worker(bot)
    scheduler = init_scheduler(bot)
    
    await tracker.start()
    logger.info("✓ Tracker worker started")
    
    await scheduler.start()
    logger.info("✓ Scheduler started")
    
    # Информация о боте
    bot_info = await bot.get_me()
    logger.info(f"✓ Bot started: @{bot_info.username}")
    logger.info("=" * 50)


async def on_shutdown(bot: Bot):
    """Действия при остановке"""
    logger.info("Stopping bot...")
    
    # Останавливаем воркеры
    from services.tracker_worker import tracker_worker
    from services.scheduler import scheduler
    
    if tracker_worker:
        await tracker_worker.stop()
        logger.info("✓ Tracker worker stopped")
    
    if scheduler:
        await scheduler.stop()
        logger.info("✓ Scheduler stopped")
    
    # Закрываем соединения
    await twitter_service.close()
    await payment_service.close()
    await db.close()
    
    logger.info("✓ Bot stopped")


async def main():
    """Главная функция"""
    logger.info("Initializing bot...")
    
    # Создаём бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Создаём диспетчер
    dp = Dispatcher()
    
    # Регистрируем роутеры
    dp.include_router(setup_routers())
    
    # Регистрируем хуки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Запускаем
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
