#!/usr/bin/env python3
"""
Main entry point for the LangSense Telegram Bot
Handles database initialization and starts the bot
"""

import asyncio
import logging
import sys
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from config import DATABASE_URL
from models import Base
import bot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def init_database():
    """Initialize database and create tables"""
    try:
        # Convert PostgreSQL URL to asyncpg if needed
        db_url = DATABASE_URL
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
        
        # Create async engine
        if "sqlite" in db_url:
            # SQLite specific configuration
            engine = create_async_engine(
                db_url,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
                echo=False
            )
        else:
            # PostgreSQL configuration
            engine = create_async_engine(db_url, echo=False)
        
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database initialized successfully")
        return engine
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

async def main():
    """Main application entry point"""
    try:
        logger.info("Starting LangSense Bot...")
        
        # Initialize database
        engine = await init_database()
        
        # Create session maker
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        
        # Start the bot
        await bot.main(async_session)
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
