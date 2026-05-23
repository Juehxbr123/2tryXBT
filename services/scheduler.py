"""
Планировщик задач (напоминания о подписке)
"""
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot
from database import db
from keyboards import extend_keyboard
from locales import get_text
import logging

logger = logging.getLogger(__name__)


class SubscriptionScheduler:
    """Планировщик для проверки подписок"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self._task: asyncio.Task = None
    
    async def start(self):
        """Запустить планировщик"""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Subscription scheduler started")
    
    async def stop(self):
        """Остановить планировщик"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Subscription scheduler stopped")
    
    async def _scheduler_loop(self):
        """Основной цикл планировщика (каждый час)"""
        while self.running:
            try:
                await self._check_subscriptions()
                # Ждём 1 час
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    async def _check_subscriptions(self):
        """Проверка подписок и отправка напоминаний"""
        logger.info("Checking subscriptions...")
        
        # Напоминание за 3 дня
        await self._send_reminders(3, "reminder_3_sent", "reminder_3_days")
        
        # Напоминание за 2 дня
        await self._send_reminders(2, "reminder_2_sent", "reminder_2_days")
        
        # Напоминание за 1 день
        await self._send_reminders(1, "reminder_1_sent", "reminder_1_day")
        
        # Истекшие подписки
        await self._process_expired()
    
    async def _send_reminders(self, days: int, sent_field: str, text_key: str):
        """Отправить напоминания"""
        users = await db.get_expiring_users(days)
        
        for user in users:
            if user.get(sent_field):
                continue
            
            try:
                await self.bot.send_message(
                    chat_id=user["user_id"],
                    text=get_text(text_key),
                    reply_markup=extend_keyboard(),
                    parse_mode="HTML"
                )
                
                # Отмечаем что отправили
                await db.update_user(user["user_id"], **{sent_field: 1})
                
                logger.info(f"Sent {days}-day reminder to {user['user_id']}")
                
            except Exception as e:
                logger.error(f"Send reminder to {user['user_id']} error: {e}")
    
    async def _process_expired(self):
        """Обработка истекших подписок"""
        users = await db.get_expired_users()
        
        for user in users:
            try:
                # Сбрасываем подписку
                await db.expire_subscription(user["user_id"])
                
                # Отправляем уведомление
                await self.bot.send_message(
                    chat_id=user["user_id"],
                    text=get_text("subscription_expired"),
                    reply_markup=extend_keyboard(),
                    parse_mode="HTML"
                )
                
                logger.info(f"Subscription expired for {user['user_id']}")
                
            except Exception as e:
                logger.error(f"Process expired for {user['user_id']} error: {e}")


# Глобальный инстанс
scheduler: SubscriptionScheduler = None


def init_scheduler(bot: Bot) -> SubscriptionScheduler:
    """Инициализация планировщика"""
    global scheduler
    scheduler = SubscriptionScheduler(bot)
    return scheduler
