#!/usr/bin/env python3
"""
Main bot module with Aiogram v3 setup
Handles bot initialization, router registration, and polling
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers import start, admin, broadcast, user_settings, announcements
from services.broadcast_service import BroadcastService

logger = logging.getLogger(__name__)

# Global variables for dependency injection
bot_instance = None
session_maker = None
broadcast_service = None

async def main(async_session):
    """Main bot function"""
    global bot_instance, session_maker, broadcast_service
    
    try:
        # Validate bot token
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set in environment variables")
        
        # Initialize bot and dispatcher
        bot_instance = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        
        # Test bot token
        bot_info = await bot_instance.get_me()
        logger.info(f"Bot initialized: @{bot_info.username} ({bot_info.first_name})")
        
        # Set session maker for handlers
        session_maker = async_session
        
        # Initialize dispatcher with memory storage
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        # Initialize broadcast service
        broadcast_service = BroadcastService(bot_instance, async_session)
        
        # Register routers
        dp.include_routers(
            start.router,
            user_settings.router,
            admin.router,
            broadcast.router,
            announcements.router
        )
        
        # Set session maker and services for handlers
        for router in [start.router, user_settings.router, admin.router, 
                      broadcast.router, announcements.router]:
            router.message.middleware.register(SessionMiddleware(async_session))
            router.callback_query.middleware.register(SessionMiddleware(async_session))
        
        # Start broadcast service worker
        asyncio.create_task(broadcast_service.worker())
        logger.info("Broadcast service worker started")
        
        # Start polling
        logger.info("Starting bot polling...")
        await dp.start_polling(bot_instance)
        
    except Exception as e:
        logger.error(f"Bot startup failed: {e}")
        raise
    finally:
        if bot_instance:
            await bot_instance.session.close()

class SessionMiddleware:
    """Middleware to inject database session into handlers"""
    
    def __init__(self, session_maker):
        self.session_maker = session_maker
    
    async def __call__(self, handler, event, data):
        data['session_maker'] = self.session_maker
        data['broadcast_service'] = broadcast_service
        return await handler(event, data)

def get_bot():
    """Get bot instance for external use"""
    return bot_instance

def get_session_maker():
    """Get session maker for external use"""
    return session_maker

def get_broadcast_service():
    """Get broadcast service for external use"""
    return broadcast_service
