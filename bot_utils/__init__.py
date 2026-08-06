# Boterx Code Splitting — Phase 1: Extract Utilities

"""
bot_utils package — extracted from comprehensive_bot.py
This package contains utility functions that don't depend on the bot class state.
They can be imported independently and tested separately.

Import pattern in comprehensive_bot.py:
    from bot_utils.telegram_api import make_inline_keyboard, transform_keyboard
    from bot_utils.csv_helpers import safe_csv_read, safe_csv_write
    from bot_utils.constants import ICON_MAP, ADMIN_ROLES, CURRENCIES
"""

# This file makes bot_utils a Python package
