#!/usr/bin/env python3
"""
Authentication utilities for admin verification
Handles admin permission checks and decorators
"""

import logging
from functools import wraps
from typing import Callable, Any
from aiogram.types import Message, CallbackQuery

from config import ADMIN_USER_IDS
from services.i18n import get_text

logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    """Check if user is an admin"""
    return user_id in ADMIN_USER_IDS

def admin_required(func: Callable) -> Callable:
    """Decorator to require admin privileges"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract user from message or callback
        user_id = None
        message_obj = None
        
        for arg in args:
            if isinstance(arg, Message):
                user_id = arg.from_user.id
                message_obj = arg
                break
            elif isinstance(arg, CallbackQuery):
                user_id = arg.from_user.id
                message_obj = arg.message if hasattr(arg, 'message') else arg
                break
        
        if not user_id:
            logger.warning("Could not extract user ID from arguments")
            return
        
        if not is_admin(user_id):
            logger.warning(f"Unauthorized admin access attempt by user {user_id}")
            
            # Send unauthorized message
            error_text = get_text("unauthorized_access", "ar")
            
            if isinstance(message_obj, Message):
                await message_obj.answer(error_text)
            elif hasattr(message_obj, 'answer'):
                await message_obj.answer(error_text)
            elif hasattr(message_obj, 'message') and hasattr(message_obj.message, 'answer'):
                await message_obj.message.answer(error_text)
            
            return
        
        # User is admin, proceed with function
        return await func(*args, **kwargs)
    
    return wrapper

async def check_admin_permissions(user_id: int, required_level: str = "basic") -> bool:
    """Check admin permissions with different levels"""
    if not is_admin(user_id):
        return False
    
    # For now, all admins have the same level
    # You can extend this to have different admin levels
    return True

def get_admin_level(user_id: int) -> str:
    """Get admin level for user"""
    if not is_admin(user_id):
        return "none"
    
    # For now, all admins are "super_admin"
    # You can extend this based on your needs
    return "super_admin"

async def log_admin_action(user_id: int, action: str, details: str = ""):
    """Log admin actions for audit trail"""
    logger.info(f"Admin action - User: {user_id}, Action: {action}, Details: {details}")
    
    # You can extend this to save to database for audit trail
    # Example:
    # async with session_maker() as session:
    #     audit_log = AdminAuditLog(
    #         admin_user_id=user_id,
    #         action=action,
    #         details=details,
    #         timestamp=datetime.now(timezone.utc)
    #     )
    #     session.add(audit_log)
    #     await session.commit()

class AdminContext:
    """Context manager for admin operations"""
    
    def __init__(self, user_id: int, action: str):
        self.user_id = user_id
        self.action = action
        self.start_time = None
    
    async def __aenter__(self):
        if not is_admin(self.user_id):
            raise PermissionError(f"User {self.user_id} is not an admin")
        
        await log_admin_action(self.user_id, f"Started: {self.action}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await log_admin_action(
                self.user_id, 
                f"Failed: {self.action}",
                f"Error: {exc_val}"
            )
        else:
            await log_admin_action(self.user_id, f"Completed: {self.action}")

# Example usage of AdminContext:
# async with AdminContext(user_id, "broadcast_creation"):
#     # Perform admin operation
#     pass
