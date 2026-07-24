#!/usr/bin/env python3
"""
Customer ID generation service
Generates unique customer codes for new users
"""

import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from models import User
from config import CUSTOMER_ID_PREFIX, CUSTOMER_ID_YEAR_FORMAT

logger = logging.getLogger(__name__)

async def generate_customer_code(session: AsyncSession) -> str:
    """Generate unique customer code"""
    try:
        # Get current year
        current_year = datetime.now().year
        year_str = CUSTOMER_ID_YEAR_FORMAT or str(current_year)
        
        # Get the highest existing number for this year
        pattern = f"{CUSTOMER_ID_PREFIX}-{year_str}-%"
        
        result = await session.execute(
            select(func.max(User.customer_code))
            .where(User.customer_code.like(pattern))
        )
        
        max_code = result.scalar_one_or_none()
        
        if max_code:
            try:
                # Extract the number part and increment
                parts = max_code.split('-')
                if len(parts) >= 3:
                    last_number = int(parts[-1])
                    next_number = last_number + 1
                else:
                    next_number = 1
            except (ValueError, IndexError):
                next_number = 1
        else:
            next_number = 1
        
        # Format with leading zeros (6 digits)
        customer_code = f"{CUSTOMER_ID_PREFIX}-{year_str}-{next_number:06d}"
        
        # Verify uniqueness (double-check)
        existing = await session.execute(
            select(User).where(User.customer_code == customer_code)
        )
        
        if existing.scalar_one_or_none():
            # If somehow exists, try with incremented number
            next_number += 1
            customer_code = f"{CUSTOMER_ID_PREFIX}-{year_str}-{next_number:06d}"
        
        logger.info(f"Generated customer code: {customer_code}")
        return customer_code
        
    except Exception as e:
        logger.error(f"Error generating customer code: {e}")
        # Fallback: use timestamp-based code
        timestamp = int(datetime.now().timestamp())
        fallback_code = f"{CUSTOMER_ID_PREFIX}-{year_str}-T{timestamp}"
        logger.warning(f"Using fallback customer code: {fallback_code}")
        return fallback_code

async def is_customer_code_unique(session: AsyncSession, customer_code: str) -> bool:
    """Check if customer code is unique"""
    try:
        result = await session.execute(
            select(User).where(User.customer_code == customer_code)
        )
        return result.scalar_one_or_none() is None
    except Exception as e:
        logger.error(f"Error checking customer code uniqueness: {e}")
        return False

async def get_user_by_customer_code(session: AsyncSession, customer_code: str) -> User:
    """Get user by customer code"""
    try:
        result = await session.execute(
            select(User).where(User.customer_code == customer_code)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting user by customer code: {e}")
        return None
