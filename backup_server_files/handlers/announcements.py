#!/usr/bin/env python3
"""
Announcements handler for system announcements
Handles announcement creation, scheduling, and delivery
"""

import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from models import Announcement, AnnouncementDelivery, User
from services.i18n import get_text
from utils.auth import admin_required
from utils.keyboards import (
    get_announcement_menu_keyboard, get_announcement_targeting_keyboard,
    get_announcement_duration_keyboard, get_announcement_confirmation_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

class AnnouncementStates(StatesGroup):
    entering_title_ar = State()
    entering_title_en = State()
    entering_content_ar = State()
    entering_content_en = State()
    adding_image = State()
    selecting_target = State()
    setting_duration = State()
    confirming = State()

@router.message(F.text == "/announce_new")
@admin_required
async def start_announcement_creation(message: Message, state: FSMContext):
    """Start announcement creation process"""
    await message.answer(
        get_text("announcement_enter_title_ar", "ar")
    )
    await state.set_state(AnnouncementStates.entering_title_ar)

@router.message(AnnouncementStates.entering_title_ar)
@admin_required
async def receive_title_arabic(message: Message, state: FSMContext):
    """Receive Arabic title"""
    title_ar = message.text.strip()
    
    if not title_ar:
        await message.answer(get_text("title_required", "ar"))
        return
    
    await state.update_data(title_ar=title_ar)
    await message.answer(get_text("announcement_enter_title_en", "ar"))
    await state.set_state(AnnouncementStates.entering_title_en)

@router.message(AnnouncementStates.entering_title_en)
@admin_required
async def receive_title_english(message: Message, state: FSMContext):
    """Receive English title"""
    title_en = message.text.strip()
    
    if not title_en:
        await message.answer(get_text("title_required", "ar"))
        return
    
    await state.update_data(title_en=title_en)
    await message.answer(get_text("announcement_enter_content_ar", "ar"))
    await state.set_state(AnnouncementStates.entering_content_ar)

@router.message(AnnouncementStates.entering_content_ar)
@admin_required
async def receive_content_arabic(message: Message, state: FSMContext):
    """Receive Arabic content"""
    content_ar = message.text.strip()
    
    if not content_ar:
        await message.answer(get_text("content_required", "ar"))
        return
    
    await state.update_data(content_ar=content_ar)
    await message.answer(get_text("announcement_enter_content_en", "ar"))
    await state.set_state(AnnouncementStates.entering_content_en)

@router.message(AnnouncementStates.entering_content_en)
@admin_required
async def receive_content_english(message: Message, state: FSMContext):
    """Receive English content"""
    content_en = message.text.strip()
    
    if not content_en:
        await message.answer(get_text("content_required", "ar"))
        return
    
    await state.update_data(content_en=content_en)
    
    # Ask for optional image
    await message.answer(
        get_text("announcement_add_image_optional", "ar"),
        reply_markup=get_announcement_menu_keyboard("ar")
    )
    await state.set_state(AnnouncementStates.adding_image)

@router.callback_query(AnnouncementStates.adding_image, F.data == "skip_image")
@admin_required
async def skip_image(callback: CallbackQuery, state: FSMContext):
    """Skip image and proceed to targeting"""
    await callback.message.edit_text(
        get_text("announcement_select_target", "ar"),
        reply_markup=get_announcement_targeting_keyboard("ar")
    )
    await state.set_state(AnnouncementStates.selecting_target)
    await callback.answer()

@router.message(AnnouncementStates.adding_image, F.photo)
@admin_required
async def receive_announcement_image(message: Message, state: FSMContext):
    """Receive announcement image"""
    try:
        # Get the largest photo
        photo = message.photo[-1]
        file_id = photo.file_id
        
        await state.update_data(image_file_id=file_id)
        
        await message.answer(
            get_text("image_added_successfully", "ar"),
            reply_markup=get_announcement_targeting_keyboard("ar")
        )
        await state.set_state(AnnouncementStates.selecting_target)
        
    except Exception as e:
        logger.error(f"Error receiving image: {e}")
        await message.answer(get_text("error_occurred", "ar"))

@router.callback_query(AnnouncementStates.selecting_target, F.data == "announce_all")
@admin_required
async def target_all_users(callback: CallbackQuery, state: FSMContext, session_maker):
    """Target all users for announcement"""
    async with session_maker() as session:
        try:
            total_users = await session.scalar(
                select(func.count(User.id)).where(User.is_active == True)
            )
            
            await state.update_data(target_type="all", target_value=None)
            
            await callback.message.edit_text(
                get_text("announcement_set_duration", "ar").format(
                    target=f"All users ({total_users})"
                ),
                reply_markup=get_announcement_duration_keyboard("ar")
            )
            await state.set_state(AnnouncementStates.setting_duration)
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error targeting all users: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(AnnouncementStates.selecting_target, F.data == "announce_by_language")
@admin_required
async def target_by_language(callback: CallbackQuery, state: FSMContext):
    """Target by language selection (simplified - you can expand this)"""
    await state.update_data(target_type="language", target_value="ar")  # Default to Arabic
    
    await callback.message.edit_text(
        get_text("announcement_set_duration", "ar").format(
            target="Arabic speakers"
        ),
        reply_markup=get_announcement_duration_keyboard("ar")
    )
    await state.set_state(AnnouncementStates.setting_duration)
    await callback.answer()

@router.callback_query(AnnouncementStates.setting_duration, F.data.startswith("duration_"))
@admin_required
async def set_announcement_duration(callback: CallbackQuery, state: FSMContext):
    """Set announcement duration"""
    duration_str = callback.data.split("_")[1]
    
    # Convert duration to hours
    duration_mapping = {
        "1h": 1,
        "6h": 6,
        "24h": 24,
        "7d": 168,  # 7 days in hours
        "permanent": 0  # 0 means permanent
    }
    
    duration_hours = duration_mapping.get(duration_str, 0)
    await state.update_data(duration_hours=duration_hours)
    
    # Show confirmation
    await show_announcement_confirmation(callback, state)

async def show_announcement_confirmation(callback: CallbackQuery, state: FSMContext):
    """Show announcement confirmation"""
    try:
        data = await state.get_data()
        
        duration_text = ""
        if data["duration_hours"] == 0:
            duration_text = "Permanent"
        else:
            duration_text = f"{data['duration_hours']} hours"
        
        target_text = ""
        if data["target_type"] == "all":
            target_text = "All active users"
        elif data["target_type"] == "language":
            target_text = f"Language: {data.get('target_value', 'N/A')}"
        
        confirmation_text = get_text("announcement_confirmation", "ar").format(
            title_ar=data["title_ar"],
            title_en=data["title_en"],
            content_ar=data["content_ar"][:100] + "..." if len(data["content_ar"]) > 100 else data["content_ar"],
            content_en=data["content_en"][:100] + "..." if len(data["content_en"]) > 100 else data["content_en"],
            target=target_text,
            duration=duration_text,
            has_image="Yes" if data.get("image_file_id") else "No"
        )
        
        await callback.message.edit_text(
            confirmation_text,
            reply_markup=get_announcement_confirmation_keyboard("ar")
        )
        await state.set_state(AnnouncementStates.confirming)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing confirmation: {e}")
        await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(AnnouncementStates.confirming, F.data == "confirm_announcement")
@admin_required
async def confirm_announcement(callback: CallbackQuery, state: FSMContext, session_maker):
    """Confirm and create announcement"""
    async with session_maker() as session:
        try:
            data = await state.get_data()
            
            # Calculate expiration time
            expires_at = None
            if data["duration_hours"] > 0:
                expires_at = datetime.now(timezone.utc) + timedelta(hours=data["duration_hours"])
            
            # Create announcement
            announcement = Announcement(
                title_ar=data["title_ar"],
                title_en=data["title_en"],
                content_ar=data["content_ar"],
                content_en=data["content_en"],
                image_url=data.get("image_file_id"),  # Store file_id as URL for simplicity
                display_duration=data["duration_hours"],
                target_language=data.get("target_value") if data["target_type"] == "language" else None,
                expires_at=expires_at,
                scheduled_at=datetime.now(timezone.utc)
            )
            
            session.add(announcement)
            await session.flush()  # Get the ID
            
            # Create delivery records for target users
            if data["target_type"] == "all":
                # Get all active users
                result = await session.execute(
                    select(User.id).where(User.is_active == True)
                )
                user_ids = [row[0] for row in result.fetchall()]
            elif data["target_type"] == "language":
                # Get users by language
                result = await session.execute(
                    select(User.id).where(
                        User.is_active == True,
                        User.language_code == data["target_value"]
                    )
                )
                user_ids = [row[0] for row in result.fetchall()]
            else:
                user_ids = []
            
            # Create delivery records
            for user_id in user_ids:
                delivery = AnnouncementDelivery(
                    announcement_id=announcement.id,
                    user_id=user_id
                )
                session.add(delivery)
            
            await session.commit()
            
            await callback.message.edit_text(
                get_text("announcement_created", "ar").format(
                    announcement_id=announcement.id,
                    target_count=len(user_ids)
                )
            )
            
            await state.clear()
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error creating announcement: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(AnnouncementStates.confirming, F.data == "cancel_announcement")
@admin_required
async def cancel_announcement(callback: CallbackQuery, state: FSMContext):
    """Cancel announcement creation"""
    await callback.message.edit_text(
        get_text("announcement_cancelled", "ar")
    )
    await state.clear()
    await callback.answer()
