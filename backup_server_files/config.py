#!/usr/bin/env python3
"""
Configuration module for the LangSense Bot
Loads environment variables and provides configuration constants
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN must be set in environment variables")

# Admin Configuration
ADMIN_USER_IDS_STR = os.getenv("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = [int(uid.strip()) for uid in ADMIN_USER_IDS_STR.split(",") if uid.strip().isdigit()]

if not ADMIN_USER_IDS:
    raise ValueError("ADMIN_USER_IDS must be set with at least one valid user ID")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./langsense.db")

# Broadcast Configuration
BROADCAST_RATE_LIMIT = int(os.getenv("BROADCAST_RATE_LIMIT", "30"))  # messages per second
BROADCAST_CHUNK_SIZE = int(os.getenv("BROADCAST_CHUNK_SIZE", "100"))  # users per batch
BROADCAST_RETRY_ATTEMPTS = int(os.getenv("BROADCAST_RETRY_ATTEMPTS", "3"))
BROADCAST_RETRY_DELAY = int(os.getenv("BROADCAST_RETRY_DELAY", "5"))  # seconds

# Localization Configuration
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "ar")
DEFAULT_COUNTRY = os.getenv("DEFAULT_COUNTRY", "SA")
SUPPORTED_LANGUAGES = ["ar", "en"]

# Customer ID Configuration
CUSTOMER_ID_PREFIX = os.getenv("CUSTOMER_ID_PREFIX", "C")
CUSTOMER_ID_YEAR_FORMAT = os.getenv("CUSTOMER_ID_YEAR_FORMAT", "2025")

# File Upload Configuration
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "20")) * 1024 * 1024  # 20MB default
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]

# Pagination Configuration
USERS_PER_PAGE = int(os.getenv("USERS_PER_PAGE", "10"))
ANNOUNCEMENTS_PER_PAGE = int(os.getenv("ANNOUNCEMENTS_PER_PAGE", "5"))

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

# Rate Limiting Configuration
USER_RATE_LIMIT = int(os.getenv("USER_RATE_LIMIT", "5"))  # requests per minute
ADMIN_RATE_LIMIT = int(os.getenv("ADMIN_RATE_LIMIT", "30"))  # requests per minute

# Validation
def validate_config():
    """Validate configuration settings"""
    errors = []
    
    if not BOT_TOKEN or len(BOT_TOKEN) < 40:
        errors.append("Invalid BOT_TOKEN format")
    
    if not ADMIN_USER_IDS:
        errors.append("No valid admin user IDs configured")
    
    if BROADCAST_RATE_LIMIT > 30:
        errors.append("BROADCAST_RATE_LIMIT cannot exceed 30 messages/second (Telegram limit)")
    
    if errors:
        raise ValueError("Configuration errors: " + "; ".join(errors))

# Validate configuration on import
validate_config()
