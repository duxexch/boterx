#!/usr/bin/env python3
"""
Admin handler for administrative functions
Handles admin panel, user management, language/country management
"""

import logging
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from models import User, Language, Country, Outbox, OutboxType, OutboxStatus
from services.i18n import get_text, get_user_language
from utils.auth import admin_required
from utils.keyboards import (
    get_admin_panel_keyboard, get_admin_users_keyboard,
    get_admin_languages_keyboard, get_admin_countries_keyboard,
    get_user_management_keyboard, get_pagination_keyboard
)
from config import USERS_PER_PAGE

logger = logging.getLogger(__name__)
router = Router()

class AdminStates(StatesGroup):
    managing_user = State()
    adding_language = State()
    adding_country = State()
    viewing_outbox = State()

@router.message(Command("admin"))
@admin_required
async def show_admin_panel(message: Message, session_maker):
    """Show admin panel"""
    async with session_maker() as session:
        try:
            # Get statistics
            total_users = await session.scalar(select(func.count(User.id)))
            active_users = await session.scalar(
                select(func.count(User.id)).where(User.is_active == True)
            )
            pending_requests = await session.scalar(
                select(func.count(Outbox.id)).where(Outbox.status == OutboxStatus.PENDING)
            )
            
            admin_text = get_text("admin_panel", "ar").format(
                total_users=total_users,
                active_users=active_users,
                pending_requests=pending_requests
            )
            
            await message.answer(
                admin_text,
                reply_markup=get_admin_panel_keyboard("ar")
            )
            
        except Exception as e:
            logger.error(f"Error showing admin panel: {e}")
            await message.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data == "admin_users")
@admin_required
async def show_users_list(callback: CallbackQuery, session_maker):
    """Show users list with pagination"""
    await show_users_page(callback, session_maker, 0)

@router.callback_query(F.data.startswith("admin_users_page_"))
@admin_required
async def show_users_page(callback: CallbackQuery, session_maker, page: int = None):
    """Show specific page of users"""
    async with session_maker() as session:
        try:
            if page is None:
                page = int(callback.data.split("_")[-1])
            
            offset = page * USERS_PER_PAGE
            
            # Get users with pagination
            result = await session.execute(
                select(User)
                .order_by(desc(User.created_at))
                .offset(offset)
                .limit(USERS_PER_PAGE)
            )
            users = result.scalars().all()
            
            # Get total count for pagination
            total_users = await session.scalar(select(func.count(User.id)))
            total_pages = (total_users + USERS_PER_PAGE - 1) // USERS_PER_PAGE
            
            if not users:
                await callback.message.edit_text(
                    get_text("no_users_found", "ar")
                )
                await callback.answer()
                return
            
            # Format users list
            users_text = get_text("users_list_header", "ar").format(
                page=page + 1,
                total_pages=total_pages,
                total_users=total_users
            )
            
            for user in users:
                status = "🟢" if user.is_active else "🔴"
                banned = "🚫" if user.is_banned else ""
                admin_mark = "👑" if user.is_admin else ""
                
                users_text += f"\n\n{status} {admin_mark} {banned}\n"
                users_text += f"ID: {user.telegram_id}\n"
                users_text += f"Name: {user.first_name}"
                if user.last_name:
                    users_text += f" {user.last_name}"
                if user.username:
                    users_text += f" (@{user.username})"
                users_text += f"\nCustomer: {user.customer_code or 'N/A'}"
                users_text += f"\nLang: {user.language_code} | Country: {user.country_code}"
                users_text += f"\nJoined: {user.created_at.strftime('%Y-%m-%d')}"
            
            keyboard = get_pagination_keyboard("admin_users", page, total_pages, "ar")
            
            await callback.message.edit_text(
                users_text,
                reply_markup=keyboard
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error showing users page: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data == "admin_languages")
@admin_required
async def show_languages_management(callback: CallbackQuery, session_maker):
    """Show languages management"""
    async with session_maker() as session:
        try:
            # Get all languages
            result = await session.execute(
                select(Language).order_by(Language.name)
            )
            languages = result.scalars().all()
            
            if not languages:
                await callback.message.edit_text(
                    get_text("no_languages_found", "ar"),
                    reply_markup=get_admin_languages_keyboard([], "ar")
                )
                await callback.answer()
                return
            
            # Format languages list
            languages_text = get_text("languages_list", "ar")
            
            for lang in languages:
                status = "✅" if lang.is_active else "❌"
                rtl_mark = "🔄" if lang.rtl else ""
                
                languages_text += f"\n\n{status} {rtl_mark}\n"
                languages_text += f"Code: {lang.code}\n"
                languages_text += f"Name: {lang.name}\n"
                languages_text += f"Native: {lang.native_name}\n"
                languages_text += f"RTL: {'Yes' if lang.rtl else 'No'}\n"
                languages_text += f"Created: {lang.created_at.strftime('%Y-%m-%d')}"
            
            await callback.message.edit_text(
                languages_text,
                reply_markup=get_admin_languages_keyboard(languages, "ar")
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error showing languages: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data == "admin_countries")
@admin_required
async def show_countries_management(callback: CallbackQuery, session_maker):
    """Show countries management"""
    async with session_maker() as session:
        try:
            # Get all countries
            result = await session.execute(
                select(Country).order_by(Country.name)
            )
            countries = result.scalars().all()
            
            if not countries:
                await callback.message.edit_text(
                    get_text("no_countries_found", "ar"),
                    reply_markup=get_admin_countries_keyboard([], "ar")
                )
                await callback.answer()
                return
            
            # Format countries list
            countries_text = get_text("countries_list", "ar")
            
            for country in countries:
                status = "✅" if country.is_active else "❌"
                
                countries_text += f"\n\n{status}\n"
                countries_text += f"Code: {country.code}\n"
                countries_text += f"Name: {country.name}\n"
                countries_text += f"Native: {country.native_name}\n"
                countries_text += f"Phone: {country.phone_prefix}\n"
                countries_text += f"Created: {country.created_at.strftime('%Y-%m-%d')}"
            
            await callback.message.edit_text(
                countries_text,
                reply_markup=get_admin_countries_keyboard(countries, "ar")
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error showing countries: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data == "admin_outbox")
@admin_required
async def show_outbox_management(callback: CallbackQuery, session_maker):
    """Show outbox/requests management"""
    async with session_maker() as session:
        try:
            # Get pending requests
            result = await session.execute(
                select(Outbox)
                .where(Outbox.status == OutboxStatus.PENDING)
                .order_by(desc(Outbox.created_at))
                .limit(10)
            )
            requests = result.scalars().all()
            
            if not requests:
                await callback.message.edit_text(
                    get_text("no_pending_requests", "ar")
                )
                await callback.answer()
                return
            
            # Format requests list
            requests_text = get_text("pending_requests_header", "ar")
            
            for req in requests:
                type_emoji = {
                    OutboxType.DEPOSIT: "💰",
                    OutboxType.WITHDRAWAL: "💸", 
                    OutboxType.COMPLAINT: "📨",
                    OutboxType.SUPPORT: "🆘"
                }.get(req.type, "📄")
                
                requests_text += f"\n\n{type_emoji} ID: {req.id}\n"
                requests_text += f"Type: {req.type.value.title()}\n"
                requests_text += f"User ID: {req.user_id}\n"
                if req.subject:
                    requests_text += f"Subject: {req.subject}\n"
                requests_text += f"Content: {req.content[:100]}...\n" if len(req.content) > 100 else f"Content: {req.content}\n"
                requests_text += f"Created: {req.created_at.strftime('%Y-%m-%d %H:%M')}"
            
            await callback.message.edit_text(requests_text)
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error showing outbox: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data.startswith("toggle_lang_"))
@admin_required
async def toggle_language_status(callback: CallbackQuery, session_maker):
    """Toggle language active status"""
    async with session_maker() as session:
        try:
            lang_id = int(callback.data.split("_")[-1])
            
            # Get language
            result = await session.execute(
                select(Language).where(Language.id == lang_id)
            )
            language = result.scalar_one_or_none()
            
            if not language:
                await callback.answer(get_text("language_not_found", "ar"))
                return
            
            # Toggle status
            language.is_active = not language.is_active
            language.updated_at = datetime.now(timezone.utc)
            await session.commit()
            
            status = "activated" if language.is_active else "deactivated"
            await callback.answer(f"Language {language.name} {status}")
            
            # Refresh the languages list
            await show_languages_management(callback, session_maker)
            
        except Exception as e:
            logger.error(f"Error toggling language: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data.startswith("toggle_country_"))
@admin_required
async def toggle_country_status(callback: CallbackQuery, session_maker):
    """Toggle country active status"""
    async with session_maker() as session:
        try:
            country_id = int(callback.data.split("_")[-1])
            
            # Get country
            result = await session.execute(
                select(Country).where(Country.id == country_id)
            )
            country = result.scalar_one_or_none()
            
            if not country:
                await callback.answer(get_text("country_not_found", "ar"))
                return
            
            # Toggle status
            country.is_active = not country.is_active
            country.updated_at = datetime.now(timezone.utc)
            await session.commit()
            
            status = "activated" if country.is_active else "deactivated"
            await callback.answer(f"Country {country.name} {status}")
            
            # Refresh the countries list
            await show_countries_management(callback, session_maker)
            
        except Exception as e:
            logger.error(f"Error toggling country: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.callback_query(F.data == "back_to_admin")
@admin_required
async def back_to_admin_panel(callback: CallbackQuery, session_maker):
    """Go back to admin panel"""
    await show_admin_panel(callback.message, session_maker)
    await callback.answer()
