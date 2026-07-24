#!/usr/bin/env python3
"""
Start handler for user registration, phone verification, and main menu
Handles /start command, phone number collection, and customer code generation
"""

import logging
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, Contact
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import User
from services.i18n import get_text, get_user_language
from services.customer_id import generate_customer_code
from utils.keyboards import (
    get_main_menu_keyboard, get_phone_share_keyboard, 
    get_contact_confirmation_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

class RegistrationStates(StatesGroup):
    waiting_for_phone = State()
    confirming_phone = State()

@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext, session_maker):
    """Handle /start command and user registration"""
    async with session_maker() as session:
        try:
            # Get or create user
            user = await get_or_create_user(session, message.from_user)
            await session.commit()
            
            # Get user's language for responses
            lang = get_user_language(user.language_code)
            
            if not user.phone_number:
                # First time user - request phone number
                await message.answer(
                    get_text("welcome_new_user", lang).format(
                        first_name=user.first_name
                    ),
                    reply_markup=get_phone_share_keyboard(lang)
                )
                await state.set_state(RegistrationStates.waiting_for_phone)
            else:
                # Returning user - show main menu
                await show_main_menu(message, user, session)
                
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await message.answer(get_text("error_occurred", "ar"))

@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def handle_phone_contact(message: Message, state: FSMContext, session_maker):
    """Handle phone number shared via contact"""
    async with session_maker() as session:
        try:
            contact: Contact = message.contact
            
            # Verify it's the user's own contact
            if contact.user_id != message.from_user.id:
                user = await get_user_by_telegram_id(session, message.from_user.id)
                lang = get_user_language(user.language_code if user else "ar")
                await message.answer(get_text("phone_must_be_yours", lang))
                return
            
            # Update user with phone number
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if user:
                user.phone_number = contact.phone_number
                user.updated_at = datetime.now(timezone.utc)
                
                # Generate customer code if not exists
                if not user.customer_code:
                    user.customer_code = await generate_customer_code(session)
                
                await session.commit()
                
                lang = get_user_language(user.language_code)
                
                # Show confirmation
                await message.answer(
                    get_text("phone_registered_success", lang).format(
                        phone=contact.phone_number,
                        customer_code=user.customer_code
                    ),
                    reply_markup=get_contact_confirmation_keyboard(lang)
                )
                
                await state.set_state(RegistrationStates.confirming_phone)
            
        except Exception as e:
            logger.error(f"Error handling phone contact: {e}")
            await message.answer(get_text("error_occurred", "ar"))

@router.callback_query(RegistrationStates.confirming_phone, F.data == "confirm_phone")
async def confirm_phone_registration(callback: CallbackQuery, state: FSMContext, session_maker):
    """Confirm phone registration and show main menu"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user:
                await callback.answer()
                await callback.message.delete()
                await show_main_menu(callback.message, user, session)
                await state.clear()
            
        except Exception as e:
            logger.error(f"Error confirming phone: {e}")
            await callback.answer(get_text("error_occurred", "ar"))

@router.message(F.text.in_(["💰 إيداع", "💰 Deposit"]))
async def handle_deposit(message: Message, session_maker):
    """Handle deposit request"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if not user:
                return
            
            lang = get_user_language(user.language_code)
            await message.answer(get_text("deposit_instructions", lang))
            
        except Exception as e:
            logger.error(f"Error handling deposit: {e}")
            await message.answer(get_text("error_occurred", "ar"))

@router.message(F.text.in_(["💸 سحب", "💸 Withdraw"]))
async def handle_withdraw(message: Message, session_maker):
    """Handle withdrawal request"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if not user:
                return
            
            lang = get_user_language(user.language_code)
            await message.answer(get_text("withdraw_instructions", lang))
            
        except Exception as e:
            logger.error(f"Error handling withdraw: {e}")
            await message.answer(get_text("error_occurred", "ar"))

@router.message(F.text.in_(["📨 شكاوى", "📨 Complaints"]))
async def handle_complaints(message: Message, session_maker):
    """Handle complaints submission"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if not user:
                return
            
            lang = get_user_language(user.language_code)
            await message.answer(get_text("complaints_instructions", lang))
            
        except Exception as e:
            logger.error(f"Error handling complaints: {e}")
            await message.answer(get_text("error_occurred", "ar"))

@router.message(F.text.in_(["👤 حسابي", "👤 My Account"]))
async def handle_my_account(message: Message, session_maker):
    """Show user account information"""
    async with session_maker() as session:
        try:
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if not user:
                return
            
            lang = get_user_language(user.language_code)
            
            # Format account information
            account_info = get_text("account_info", lang).format(
                first_name=user.first_name,
                last_name=user.last_name or "",
                username=f"@{user.username}" if user.username else get_text("not_set", lang),
                phone=user.phone_number or get_text("not_set", lang),
                customer_code=user.customer_code,
                language=user.language_code.upper(),
                country=user.country_code.upper(),
                notifications=get_text("enabled", lang) if user.notifications_enabled else get_text("disabled", lang)
            )
            
            await message.answer(account_info)
            
        except Exception as e:
            logger.error(f"Error showing account: {e}")
            await message.answer(get_text("error_occurred", "ar"))

async def get_or_create_user(session: AsyncSession, telegram_user) -> User:
    """Get existing user or create new one"""
    # Try to get existing user
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_user.id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Update user information
        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        user.last_activity = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)
    else:
        # Create new user
        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code or "ar",
            last_activity=datetime.now(timezone.utc)
        )
        session.add(user)
    
    return user

async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User:
    """Get user by telegram ID"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()

async def show_main_menu(message: Message, user: User, session: AsyncSession):
    """Show main menu to user"""
    lang = get_user_language(user.language_code)
    
    welcome_back_text = get_text("welcome_back", lang).format(
        first_name=user.first_name,
        customer_code=user.customer_code
    )
    
    await message.answer(
        welcome_back_text,
        reply_markup=get_main_menu_keyboard(lang)
    )
