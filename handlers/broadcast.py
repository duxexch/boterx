#!/usr/bin/env python3
"""
Broadcast handler for mass messaging
Handles broadcast creation, targeting, and delivery management
"""

import logging
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from models import User, Outbox, OutboxType, OutboxStatus, Language, Country
from services.i18n import get_text
from utils.auth import admin_required
from utils.keyboards import (
    get_broadcast_targeting_keyboard, get_broadcast_confirmation_keyboard,
    get_language_filter_keyboard, get_country_filter_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

class BroadcastStates(StatesGroup):
    selecting_target = State()
    entering_message = State()
    adding_media = State()
    confirming = State()

@router.message(F.text == "/broadcast")
@admin_required
async def start_broadcast(message: Message, state: FSMContext, session_maker):
    """Start broadcast creation process"""
    async with session_maker() as session:
        try:
            # Get statistics for targeting options
            total_users = await session.scalar(
                select(func.count(User.id)).where(User.is_active == True)
            )
            
            # Get language distribution
            lang_result = await session.execute(
                select(User.language_code, func.count(User.id))
                .where(User.is_active == True)
                .group_by(User.language_code)
            )
            lang_stats = dict(lang_result.fetchall())
            
            # Get country distribution
            country_result = await session.execute(
                select(User.country_code, func.count(User.id))
                .where(User.is_active == True)
                .group_by(User.country_code)
            )
            country_stats = dict(country_result.fetchall())
            
            # Format targeting options
            stats_text = get_text("broadcast_targeting_stats", "ar").format(
                total_users=total_users,
                lang_stats=", ".join([f"{k}: {v}" for k, v in lang_stats.items()]),
                country_stats=", ".join([f"{k}: {v}" for k, v in country_stats.items()])
            )
            
            await message.answer(
                stats_text,
                reply_markup=get_broadcast_targeting_keyboard("ar")
            )
            
            await state.set_state(BroadcastStates.selecting_target)
            await state.update_data(
                total_users=total_users,
                lang_stats=lang_stats,
                country_stats=country_stats
            )
            
        except Exception as e:
            logger.error(f"Error starting broadcast: {e}")
            await message.answer(get_text("error_occurred", "ar"))

@router.callback_query(BroadcastStates.selecting_target, F.data == "broadcast_all")
@admin_required
async def select_broadcast_all(callback: CallbackQuery, state: FSMContext, session_maker):
    """Select broadcast to all users"""
    await state.update_data(target_type="all")
    await callback.message.edit_text(
        get_text("broadcast_enter_message", "ar")
    )
    await state.set_state(BroadcastStates.entering_message)
    await callback.answer()

@router.callback_query(BroadcastStates.selecting_target, F.data == "broadcast_by_language")
@admin_required
async def select_broadcast_by_language(callback: CallbackQuery, state: FSMContext, session_maker):
    """Select broadcast by language"""
    async with session_maker() as session:
        try:
            # Get available languages with user counts
            result = await session.execute(
                select(Language.code, Language.native_name, func.count(User.id))
                .join(User, User.language_code == Language.code)
                .where(Language.is_active == True, User.is_active == True)
                .group_by(Language.code, Language.native_name)
            )
            languages = result.fetchall()
            
            if not languages:
                await callback.answer(get_text("no_languages_with_users", "ar"))
                return
            
            await callback.message.edit_text(
                get_text("select_target_language", "ar"),
                reply_markup=get_language_filter_keyboard(languages, "ar")
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error showing language selection: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(BroadcastStates.selecting_target, F.data == "broadcast_by_country")
@admin_required
async def select_broadcast_by_country(callback: CallbackQuery, state: FSMContext, session_maker):
    """Select broadcast by country"""
    async with session_maker() as session:
        try:
            # Get available countries with user counts
            result = await session.execute(
                select(Country.code, Country.native_name, func.count(User.id))
                .join(User, User.country_code == Country.code)
                .where(Country.is_active == True, User.is_active == True)
                .group_by(Country.code, Country.native_name)
            )
            countries = result.fetchall()
            
            if not countries:
                await callback.answer(get_text("no_countries_with_users", "ar"))
                return
            
            await callback.message.edit_text(
                get_text("select_target_country", "ar"),
                reply_markup=get_country_filter_keyboard(countries, "ar")
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error showing country selection: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(BroadcastStates.selecting_target, F.data.startswith("lang_filter_"))
@admin_required
async def select_language_filter(callback: CallbackQuery, state: FSMContext):
    """Select specific language for broadcast"""
    language_code = callback.data.split("_")[-1]
    await state.update_data(target_type="language", target_value=language_code)
    
    await callback.message.edit_text(
        get_text("broadcast_enter_message", "ar").format(
            target=f"Language: {language_code.upper()}"
        )
    )
    await state.set_state(BroadcastStates.entering_message)
    await callback.answer()

@router.callback_query(BroadcastStates.selecting_target, F.data.startswith("country_filter_"))
@admin_required
async def select_country_filter(callback: CallbackQuery, state: FSMContext):
    """Select specific country for broadcast"""
    country_code = callback.data.split("_")[-1]
    await state.update_data(target_type="country", target_value=country_code)
    
    await callback.message.edit_text(
        get_text("broadcast_enter_message", "ar").format(
            target=f"Country: {country_code.upper()}"
        )
    )
    await state.set_state(BroadcastStates.entering_message)
    await callback.answer()

@router.message(BroadcastStates.entering_message)
@admin_required
async def receive_broadcast_message(message: Message, state: FSMContext):
    """Receive broadcast message text"""
    try:
        broadcast_text = message.text or message.caption or ""
        
        if not broadcast_text.strip():
            await message.answer(get_text("broadcast_message_required", "ar"))
            return
        
        # Store message data
        await state.update_data(
            message_text=broadcast_text,
            message_entities=message.entities,
            message_type="text"
        )
        
        # Check if message has media
        if message.photo or message.video or message.document:
            if message.photo:
                file_id = message.photo[-1].file_id
                await state.update_data(message_type="photo", file_id=file_id)
            elif message.video:
                await state.update_data(message_type="video", file_id=message.video.file_id)
            elif message.document:
                await state.update_data(message_type="document", file_id=message.document.file_id)
        
        # Show confirmation
        await show_broadcast_confirmation(message, state)
        
    except Exception as e:
        logger.error(f"Error receiving broadcast message: {e}")
        await message.answer(get_text("error_occurred", "ar"))

async def show_broadcast_confirmation(message: Message, state: FSMContext):
    """Show broadcast confirmation with preview"""
    try:
        data = await state.get_data()
        
        # Calculate target audience
        target_info = ""
        if data["target_type"] == "all":
            target_info = f"All active users ({data.get('total_users', '?')} users)"
        elif data["target_type"] == "language":
            lang_code = data["target_value"]
            user_count = data.get("lang_stats", {}).get(lang_code, "?")
            target_info = f"Language: {lang_code.upper()} ({user_count} users)"
        elif data["target_type"] == "country":
            country_code = data["target_value"]
            user_count = data.get("country_stats", {}).get(country_code, "?")
            target_info = f"Country: {country_code.upper()} ({user_count} users)"
        
        confirmation_text = get_text("broadcast_confirmation", "ar").format(
            target=target_info,
            message_preview=data["message_text"][:200] + "..." if len(data["message_text"]) > 200 else data["message_text"]
        )
        
        await message.answer(
            confirmation_text,
            reply_markup=get_broadcast_confirmation_keyboard("ar")
        )
        
        await state.set_state(BroadcastStates.confirming)
        
    except Exception as e:
        logger.error(f"Error showing confirmation: {e}")
        await message.answer(get_text("error_occurred", "ar"))

@router.callback_query(BroadcastStates.confirming, F.data == "confirm_broadcast")
@admin_required
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, session_maker, broadcast_service):
    """Confirm and start broadcast"""
    async with session_maker() as session:
        try:
            data = await state.get_data()
            
            # Create outbox entry for broadcast
            outbox = Outbox(
                user_id=1,  # System user for broadcasts
                type=OutboxType.BROADCAST,
                status=OutboxStatus.PROCESSING,
                subject=f"Broadcast to {data['target_type']}",
                content=data["message_text"]
            )
            session.add(outbox)
            await session.flush()
            
            # Queue broadcast for delivery
            await broadcast_service.queue_broadcast(
                outbox_id=outbox.id,
                target_type=data["target_type"],
                target_value=data.get("target_value"),
                message_text=data["message_text"],
                message_type=data.get("message_type", "text"),
                file_id=data.get("file_id"),
                message_entities=data.get("message_entities")
            )
            
            await session.commit()
            
            await callback.message.edit_text(
                get_text("broadcast_queued", "ar").format(
                    broadcast_id=outbox.id
                )
            )
            
            await state.clear()
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error confirming broadcast: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(BroadcastStates.confirming, F.data == "cancel_broadcast")
@admin_required
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Cancel broadcast"""
    await callback.message.edit_text(
        get_text("broadcast_cancelled", "ar")
    )
    await state.clear()
    await callback.answer()
