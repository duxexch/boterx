#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام الثيمات — 3 ثيمات قابلة للتخصيص
يتحكم في: الأطر الزخرفية، الإيموجي، تنسيق الرسائل
"""

THEMES = {
    'gold': {
        'name': 'Dark Gold',
        'name_ar': 'الذهبي الداكن',
        'icon': '🥇',
        # أطر زخرفية
        'frame_top': '╔════════════════════╗',
        'frame_mid': '║',
        'frame_bot': '╚════════════════════╝',
        'box_top': '┌─────────────────────┐',
        'box_bot': '└─────────────────────┘',
        # أشرطة التقدم
        'bar_full': '▰',
        'bar_empty': '▱',
        # فاصل
        'separator': '▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️',
        # ألوان الحالة (إيموجي)
        'status_active': '🟢',
        'status_pending': '🟡',
        'status_used': '🔴',
        'status_expired': '⚫',
        # أزرار رئيسية
        'btn_deposit': '💰',
        'btn_withdraw': '💸',
        'btn_requests': '📋',
        'btn_profile': '👤',
        'btn_complaint': '📨',
        'btn_support': '🆘',
        'btn_currency': '💱',
        'btn_language': '🌐',
        'btn_recovery': '💎',
        'btn_referral': '🎁',
        'btn_help': '❓',
        'btn_notifications': '🔔',
        'btn_match': '🔄',
        'btn_reset': '🔄',
        # أيقونات الإدمن
        'admin_pending': '📋',
        'admin_approved': '✅',
        'admin_users': '👥',
        'admin_search': '🔍',
        'admin_companies': '🏢',
        'admin_payment': '💳',
        'admin_stats': '📊',
        'admin_excel': '📑',
        'admin_broadcast': '📢',
        'admin_complaints': '📨',
        'admin_support': '🛠️',
        'admin_settings': '⚙️',
        'admin_addresses': '📍',
        'admin_admins': '👥',
        'admin_buttons': '✏️',
        'admin_notifications': '🔔',
        'admin_backup': '💾',
        'admin_recovery': '💎',
        'admin_ban': '🚫',
        'admin_unban': '✅',
        'admin_home': '🏠',
        # تنسيق الرسائل
        'msg_format': 'code',  # code | bold | plain
    },

    'ocean': {
        'name': 'Ocean Blue',
        'name_ar': 'الأزرق المحيطي',
        'icon': '🌊',
        'frame_top': '╭─────────────────────╮',
        'frame_mid': '│',
        'frame_bot': '╰─────────────────────╯',
        'box_top': '┌─────────────────────┐',
        'box_bot': '└─────────────────────┘',
        'bar_full': '▮',
        'bar_empty': '▯',
        'separator': '─────────────────────',
        'status_active': '🔵',
        'status_pending': '🟡',
        'status_used': '🔴',
        'status_expired': '⚪',
        'btn_deposit': '💵',
        'btn_withdraw': '📤',
        'btn_requests': '📄',
        'btn_profile': '🧑',
        'btn_complaint': '📩',
        'btn_support': '🆘',
        'btn_currency': '💱',
        'btn_language': '🌍',
        'btn_recovery': '🔷',
        'btn_referral': '🎁',
        'btn_help': '❓',
        'btn_notifications': '🔔',
        'btn_match': '🔄',
        'btn_reset': '♻️',
        'admin_pending': '📄',
        'admin_approved': '✔️',
        'admin_users': '👥',
        'admin_search': '🔎',
        'admin_companies': '🏬',
        'admin_payment': '💳',
        'admin_stats': '📈',
        'admin_excel': '📊',
        'admin_broadcast': '📡',
        'admin_complaints': '📫',
        'admin_support': '🔧',
        'admin_settings': '⚙️',
        'admin_addresses': '📌',
        'admin_admins': '👥',
        'admin_buttons': '✏️',
        'admin_notifications': '🔔',
        'admin_backup': '💾',
        'admin_recovery': '🔷',
        'admin_ban': '⛔',
        'admin_unban': '✅',
        'admin_home': '🏠',
        'msg_format': 'bold',
    },

    'purple': {
        'name': 'Royal Purple',
        'name_ar': 'البنفسجي الملكي',
        'icon': '👑',
        'frame_top': '★━━━━━━━━━━━━━━━━━★',
        'frame_mid': '┃',
        'frame_bot': '★━━━━━━━━━━━━━━━━━★',
        'box_top': '╔════════════════════╗',
        'box_bot': '╚════════════════════╝',
        'bar_full': '⬛',
        'bar_empty': '⬜',
        'separator': '✦━━━━━━━━━━━━━━━━━━✦',
        'status_active': '💜',
        'status_pending': '💛',
        'status_used': '💔',
        'status_expired': '🖤',
        'btn_deposit': '💠',
        'btn_withdraw': '🔮',
        'btn_requests': '📜',
        'btn_profile': '🤴',
        'btn_complaint': '📯',
        'btn_support': '🆘',
        'btn_currency': '💱',
        'btn_language': '🌐',
        'btn_recovery': '👑',
        'btn_referral': '🎁',
        'btn_help': '❓',
        'btn_notifications': '🔔',
        'btn_match': '🔄',
        'btn_reset': '♻️',
        'admin_pending': '📜',
        'admin_approved': '✅',
        'admin_users': '👥',
        'admin_search': '🔍',
        'admin_companies': '🏰',
        'admin_payment': '💳',
        'admin_stats': '📊',
        'admin_excel': '📑',
        'admin_broadcast': '📣',
        'admin_complaints': '📨',
        'admin_support': '🛠️',
        'admin_settings': '⚙️',
        'admin_addresses': '📍',
        'admin_admins': '👥',
        'admin_buttons': '✏️',
        'admin_notifications': '🔔',
        'admin_backup': '💾',
        'admin_recovery': '👑',
        'admin_ban': '🚫',
        'admin_unban': '✅',
        'admin_home': '🏠',
        'msg_format': 'plain',
    },
}


def get_theme(theme_name):
    """الحصول على ثيم كامل بالاسم"""
    return THEMES.get(theme_name, THEMES['gold'])


def get_theme_list():
    """قائمة الثيمات المتاحة"""
    return [(key, t['name_ar'], t['icon']) for key, t in THEMES.items()]


def get_theme_value(theme_name, key):
    """الحصول على قيمة محددة من ثيم"""
    theme = get_theme(theme_name)
    return theme.get(key, THEMES['gold'].get(key, ''))


def format_message(theme_name, title, content):
    """تنسيق رسالة بالإطار الزخرفي للثيم"""
    theme = get_theme(theme_name)
    fmt = theme.get('msg_format', 'plain')

    frame_top = theme['frame_top']
    frame_mid = theme['frame_mid']
    frame_bot = theme['frame_bot']

    header = f"{frame_top}\n{frame_mid}  {title}  {frame_mid}\n{frame_bot}\n\n"

    if fmt == 'code':
        body = f"```\n{content}\n```"
    elif fmt == 'bold':
        body = f"*{content}*"
    else:
        body = content

    return header + body
