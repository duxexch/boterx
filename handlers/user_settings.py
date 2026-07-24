#!/usr/bin/env python3
"""
User settings handler for language and country selection
Handles user preference changes and localization updates
"""

import logging
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import User, Language, Country
from services.i18n import get_text, get_user_language, load_translations
from utils.keyboards import (
    get_language_selection_keyboard, get_country_selection_keyboard,
    get_settings_keyboard, get_main_menu_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.text.in_(["🌐 اللغة", "🌐 Language", "⚙️ الإعدادات", "⚙️ Settings"]))
async def show_settings_menu(message: Message, session_maker):
    """Show settings menu"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if not user:
                return
            
            lang = get_user_language(user.language_code)
            
            await message.answer(
                get_text("settings_menu", lang),
                reply_markup=get_settings_keyboard(lang)
            )
            
        except Exception as e:
            logger.error(f"Error showing settings menu: {e}")
            await message.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data == "change_language")
async def show_language_selection(callback: CallbackQuery, session_maker):
    """Show language selection menu"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if not user:
                await callback.answer()
                return
            
            # Get available languages
            result = await session.execute(
                select(Language).where(Language.is_active == True).order_by(Language.name)
            )
            languages = result.scalars().all()
            
            lang = get_user_language(user.language_code)
            
            await callback.message.edit_text(
                get_text("select_language", lang),
                reply_markup=get_language_selection_keyboard(languages, user.language_code, lang)
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error showing language selection: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data.startswith("lang_"))
async def change_language(callback: CallbackQuery, session_maker):
    """Change user language"""
    async with session_maker() as session:
        try:
            language_code = callback.data.split("_")[1]
            
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if not user:
                await callback.answer()
                return
            
            # Verify language exists and is active
            result = await session.execute(
                select(Language).where(
                    Language.code == language_code,
                    Language.is_active == True
                )
            )
            language = result.scalar_one_or_none()
            
            if not language:
                await callback.answer(get_text("language_not_available", "ar"))
                return
            
            # Update user language
            old_lang = user.language_code
            user.language_code = language_code
            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            
            # Get new language text
            new_lang = get_user_language(language_code)
            
            await callback.message.edit_text(
                get_text("language_changed", new_lang).format(
                    language_name=language.native_name
                )
            )
            
            # Show updated main menu
            await callback.message.answer(
                get_text("main_menu_updated", new_lang),
                reply_markup=get_main_menu_keyboard(new_lang)
            )
            
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error changing language: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data == "change_country")
async def show_country_selection(callback: CallbackQuery, session_maker):
    """Show country selection menu"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if not user:
                await callback.answer()
                return
            
            # Get available countries
            result = await session.execute(
                select(Country).where(Country.is_active == True).order_by(Country.name)
            )
            countries = result.scalars().all()
            
            lang = get_user_language(user.language_code)
            
            await callback.message.edit_text(
                get_text("select_country", lang),
                reply_markup=get_country_selection_keyboard(countries, user.country_code, lang)
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error showing country selection: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data.startswith("country_"))
async def change_country(callback: CallbackQuery, session_maker):
    """Change user country"""
    async with session_maker() as session:
        try:
            country_code = callback.data.split("_")[1]
            
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if not user:
                await callback.answer()
                return
            
            # Verify country exists and is active
            result = await session.execute(
                select(Country).where(
                    Country.code == country_code,
                    Country.is_active == True
                )
            )
            country = result.scalar_one_or_none()
            
            if not country:
                lang = get_user_language(user.language_code)
                await callback.answer(get_text("country_not_available", lang))
                return
            
            # Update user country
            user.country_code = country_code
            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            
            lang = get_user_language(user.language_code)
            
            country_name = country.native_name if lang == "ar" else country.name
            
            await callback.message.edit_text(
                get_text("country_changed", lang).format(
                    country_name=country_name
                )
            )
            
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error changing country: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(callback: CallbackQuery, session_maker):
    """Toggle user notifications"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if not user:
                await callback.answer()
                return
            
            # Toggle notifications
            user.notifications_enabled = not user.notifications_enabled
            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            
            lang = get_user_language(user.language_code)
            
            status = get_text("enabled", lang) if user.notifications_enabled else get_text("disabled", lang)
            
            await callback.message.edit_text(
                get_text("notifications_toggled", lang).format(status=status)
            )
            
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error toggling notifications: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: CallbackQuery, session_maker):
    """Go back to settings menu"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if not user:
                await callback.answer()
                return
            
            lang = get_user_language(user.language_code)
            
            await callback.message.edit_text(
                get_text("settings_menu", lang),
                reply_markup=get_settings_keyboard(lang)
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error going back to settings: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User:
    """Get user by telegram ID"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()
