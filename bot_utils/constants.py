"""
bot_utils/constants.py — Data constants extracted from comprehensive_bot.py
These are pure data, no logic, no class dependency.
"""

CURRENCIES = {
    'SAR': {'name': 'الريال السعودي', 'symbol': 'ر.س', 'flag': '🇸🇦'},
    'AED': {'name': 'الدرهم الإماراتي', 'symbol': 'د.إ', 'flag': '🇦🇪'},
    'EGP': {'name': 'الجنيه المصري', 'symbol': 'ج.م', 'flag': '🇪🇬'},
    'KWD': {'name': 'الدينار الكويتي', 'symbol': 'د.ك', 'flag': '🇰🇼'},
    'QAR': {'name': 'الريال القطري', 'symbol': 'ر.ق', 'flag': '🇶🇦'},
    'BHD': {'name': 'الدينار البحريني', 'symbol': 'د.ب', 'flag': '🇧🇭'},
    'OMR': {'name': 'الريال العماني', 'symbol': 'ر.ع', 'flag': '🇴🇲'},
    'JOD': {'name': 'الدينار الأردني', 'symbol': 'د.أ', 'flag': '🇯🇴'},
    'LBP': {'name': 'الليرة اللبنانية', 'symbol': 'ل.ل', 'flag': '🇱🇧'},
    'IQD': {'name': 'الدينار العراقي', 'symbol': 'د.ع', 'flag': '🇮🇶'},
    'SYP': {'name': 'الليرة السورية', 'symbol': 'ل.س', 'flag': '🇸🇾'},
    'MAD': {'name': 'الدرهم المغربي', 'symbol': 'د.م', 'flag': '🇲🇦'},
    'TND': {'name': 'الدينار التونسي', 'symbol': 'د.ت', 'flag': '🇹🇳'},
    'DZD': {'name': 'الدينار الجزائري', 'symbol': 'د.ج', 'flag': '🇩🇿'},
    'LYD': {'name': 'الدينار الليبي', 'symbol': 'د.ل', 'flag': '🇱🇾'},
    'USD': {'name': 'الدولار الأمريكي', 'symbol': '$', 'flag': '🇺🇸'},
    'EUR': {'name': 'اليورو', 'symbol': '€', 'flag': '🇪🇺'},
    'TRY': {'name': 'الليرة التركية', 'symbol': '₺', 'flag': '🇹🇷'},
}

# CSV encoding used throughout the project
CSV_ENCODING = 'utf-8-sig'

# Default admin roles
ADMIN_ROLES = {
    'full': '👑 مدير كامل',
    'transactions': '💰 مشرف معاملات',
    'support': '🆘 مشرف دعم',
    'companies': '🏢 مشرف شركات',
}
