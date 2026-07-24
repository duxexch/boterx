#!/usr/bin/env python3
"""
Broadcast service for handling mass messaging
Manages broadcast queues, rate limiting, and delivery tracking
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, and_

from models import (
    User, Outbox, OutboxRecipient, OutboxStatus, 
    DeliveryStatus, OutboxType
)
from config import (
    BROADCAST_RATE_LIMIT, BROADCAST_CHUNK_SIZE, 
    BROADCAST_RETRY_ATTEMPTS, BROADCAST_RETRY_DELAY
)

logger = logging.getLogger(__name__)

class BroadcastService:
    """Service for handling broadcast operations"""
    
    def __init__(self, bot: Bot, session_maker: async_sessionmaker):
        self.bot = bot
        self.session_maker = session_maker
        self.broadcast_queue = asyncio.Queue()
        self.is_running = False
        
    async def queue_broadcast(self, outbox_id: int, target_type: str, 
                            target_value: Optional[str], message_text: str,
                            message_type: str = "text", file_id: Optional[str] = None,
                            message_entities: Optional[List] = None):
        """Queue a broadcast for delivery"""
        broadcast_data = {
            "outbox_id": outbox_id,
            "target_type": target_type,
            "target_value": target_value,
            "message_text": message_text,
            "message_type": message_type,
            "file_id": file_id,
            "message_entities": message_entities
        }
        
        await self.broadcast_queue.put(broadcast_data)
        logger.info(f"Queued broadcast {outbox_id} for delivery")
    
    async def worker(self):
        """Background worker for processing broadcast queue"""
        self.is_running = True
        logger.info("Broadcast service worker started")
        
        while self.is_running:
            try:
                # Get broadcast from queue with timeout
                try:
                    broadcast = await asyncio.wait_for(
                        self.broadcast_queue.get(), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                await self.process_broadcast(broadcast)
                
            except Exception as e:
                logger.error(f"Error in broadcast worker: {e}")
                await asyncio.sleep(1)
    
    async def process_broadcast(self, broadcast: Dict[str, Any]):
        """Process a single broadcast"""
        outbox_id = broadcast["outbox_id"]
        
        try:
            async with self.session_maker() as session:
                # Get target users
                users = await self.get_target_users(
                    session, broadcast["target_type"], broadcast.get("target_value")
                )
                
                if not users:
                    logger.warning(f"No target users found for broadcast {outbox_id}")
                    await self.update_broadcast_status(session, outbox_id, OutboxStatus.COMPLETED)
                    return
                
                # Create recipient records
                await self.create_recipient_records(session, outbox_id, users)
                await session.commit()
                
                logger.info(f"Starting delivery for broadcast {outbox_id} to {len(users)} users")
                
                # Process in chunks
                for chunk in self.chunk_list(users, BROADCAST_CHUNK_SIZE):
                    await self.send_to_chunk(session, outbox_id, chunk, broadcast)
                    
                    # Rate limiting
                    sleep_time = len(chunk) / BROADCAST_RATE_LIMIT
                    await asyncio.sleep(sleep_time)
                
                # Update broadcast status
                await self.update_broadcast_status(session, outbox_id, OutboxStatus.COMPLETED)
                logger.info(f"Completed broadcast {outbox_id}")
                
        except Exception as e:
            logger.error(f"Error processing broadcast {outbox_id}: {e}")
            async with self.session_maker() as session:
                await self.update_broadcast_status(session, outbox_id, OutboxStatus.FAILED)
    
    async def get_target_users(self, session: AsyncSession, target_type: str, 
                             target_value: Optional[str]) -> List[User]:
        """Get target users based on targeting criteria"""
        base_query = select(User).where(
            and_(User.is_active == True, User.is_banned == False)
        )
        
        if target_type == "all":
            result = await session.execute(base_query)
        elif target_type == "language":
            result = await session.execute(
                base_query.where(User.language_code == target_value)
            )
        elif target_type == "country":
            result = await session.execute(
                base_query.where(User.country_code == target_value)
            )
        else:
            logger.warning(f"Unknown target type: {target_type}")
            return []
        
        return list(result.scalars().all())
    
    async def create_recipient_records(self, session: AsyncSession, 
                                     outbox_id: int, users: List[User]):
        """Create recipient tracking records"""
        for user in users:
            recipient = OutboxRecipient(
                outbox_id=outbox_id,
                user_id=user.id,
                status=DeliveryStatus.PENDING
            )
            session.add(recipient)
    
    async def send_to_chunk(self, session: AsyncSession, outbox_id: int, 
                          users: List[User], broadcast: Dict[str, Any]):
        """Send broadcast to a chunk of users"""
        for user in users:
            try:
                success = await self.send_to_user(user, broadcast)
                
                # Update recipient status
                await self.update_recipient_status(
                    session, outbox_id, user.id,
                    DeliveryStatus.SENT if success else DeliveryStatus.FAILED
                )
                
            except Exception as e:
                logger.error(f"Error sending to user {user.telegram_id}: {e}")
                await self.update_recipient_status(
                    session, outbox_id, user.id, DeliveryStatus.FAILED, str(e)
                )
        
        await session.commit()
    
    async def send_to_user(self, user: User, broadcast: Dict[str, Any]) -> bool:
        """Send broadcast message to a single user"""
        try:
            message_text = broadcast["message_text"]
            message_type = broadcast.get("message_type", "text")
            file_id = broadcast.get("file_id")
            
            if message_type == "text":
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=message_text,
                    entities=broadcast.get("message_entities")
                )
            elif message_type == "photo" and file_id:
                await self.bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=file_id,
                    caption=message_text,
                    caption_entities=broadcast.get("message_entities")
                )
            elif message_type == "video" and file_id:
                await self.bot.send_video(
                    chat_id=user.telegram_id,
                    video=file_id,
                    caption=message_text,
                    caption_entities=broadcast.get("message_entities")
                )
            elif message_type == "document" and file_id:
                await self.bot.send_document(
                    chat_id=user.telegram_id,
                    document=file_id,
                    caption=message_text,
                    caption_entities=broadcast.get("message_entities")
                )
            
            return True
            
        except TelegramForbiddenError:
            # User blocked the bot
            logger.info(f"User {user.telegram_id} blocked the bot")
            return False
        except TelegramBadRequest as e:
            # Invalid user or other API error
            logger.warning(f"Bad request for user {user.telegram_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending to user {user.telegram_id}: {e}")
            return False
    
    async def update_broadcast_status(self, session: AsyncSession, 
                                    outbox_id: int, status: OutboxStatus):
        """Update broadcast status"""
        result = await session.execute(
            select(Outbox).where(Outbox.id == outbox_id)
        )
        outbox = result.scalar_one_or_none()
        
        if outbox:
            outbox.status = status
            outbox.updated_at = datetime.now(timezone.utc)
            await session.commit()
    
    async def update_recipient_status(self, session: AsyncSession, outbox_id: int,
                                    user_id: int, status: DeliveryStatus,
                                    error_message: Optional[str] = None):
        """Update recipient delivery status"""
        result = await session.execute(
            select(OutboxRecipient).where(
                and_(
                    OutboxRecipient.outbox_id == outbox_id,
                    OutboxRecipient.user_id == user_id
                )
            )
        )
        recipient = result.scalar_one_or_none()
        
        if recipient:
            recipient.status = status
            recipient.last_attempt = datetime.now(timezone.utc)
            recipient.attempts += 1
            
            if status == DeliveryStatus.SENT:
                recipient.delivered_at = datetime.now(timezone.utc)
            elif error_message:
                recipient.error_message = error_message
    
    @staticmethod
    def chunk_list(lst: List, chunk_size: int) -> List[List]:
        """Split list into chunks"""
        return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]
    
    async def stop(self):
        """Stop the broadcast service"""
        self.is_running = False
        logger.info("Broadcast service stopping...")
