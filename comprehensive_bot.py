#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import csv
import secrets
import urllib.request
import urllib.parse
import logging
import threading
import time
import zipfile
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

# تحميل dotenv قبل استخدام أي متغيرات
from dotenv import load_dotenv

# استيراد نظام المطابقة
try:
    from matching import MatchManager
    MATCHING_AVAILABLE = True
except ImportError:
    MATCHING_AVAILABLE = False

# استيراد نظام 💎 تعويض 100%
try:
    from svrp import SVRPManager
    SVRP_AVAILABLE = True
except ImportError:
    SVRP_AVAILABLE = False

# استيراد نظام الثيمات
try:
    from theme_config import THEMES, get_theme, get_theme_list, get_theme_value
    THEME_AVAILABLE = True
except ImportError:
    THEME_AVAILABLE = False

# استيراد نظام إدارة البوتات المتعددة
try:
    from multi_bot import MultiBotManager
    MULTI_BOT_AVAILABLE = True
except ImportError:
    MULTI_BOT_AVAILABLE = False

# تحميل ملف .env من نفس المجلد
load_dotenv(".env")

# ===== bot_utils — extracted utilities =====
from bot_utils.constants import CURRENCIES, CSV_ENCODING
from bot_utils.validation import sanitize_input, validate_phone_number, validate_amount
from bot_utils.telegram_helpers import make_inline_btn, make_inline_keyboard, make_reply_keyboard, remove_keyboard
from bot_utils.rate_limiter import user_message_limiter, user_callback_limiter, start_cleanup_thread as _start_rl_cleanup
from bot_utils.notification_hub import hub as _notif_hub
from concurrent.futures import ThreadPoolExecutor

# إعداد نظام اللوج
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# التحقق من تحميل BOT_TOKEN بدون طباعته (أمان)
if not os.getenv("BOT_TOKEN"):
    logger.error("BOT_TOKEN غير موجود في متغيرات البيئة!")
else:
    logger.info("BOT_TOKEN loaded successfully ✓")

from handlers.deposit_withdraw import DepositWithdrawMixin
from handlers.message_dispatcher import MessageDispatcherMixin
from handlers.callback_handler import CallbackHandlerMixin
from handlers.admin_actions import AdminActionsMixin
from database import get_db, PersistentStateDict


class ComprehensiveDUXBot(DepositWithdrawMixin, MessageDispatcherMixin, CallbackHandlerMixin, AdminActionsMixin):
    def __init__(self, token):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self._db = get_db()
        self.user_states = PersistentStateDict(self._db)
        self.temp_company_data = {}  # إضافة المتغير المفقود
        self.init_files()
        self.init_button_labels()
        self.load_i18n_translations()
        self.match_manager = MatchManager() if MATCHING_AVAILABLE else None
        self.svrp = SVRPManager() if SVRP_AVAILABLE else None
        # فحص صلاحية إدارة البوتات: البوت الرئيسي فقط (من .env) يمكنه إدارة البوتات
        self.can_manage_bots = self._check_bot_management_permission(token)
        self.admin_ids = self.get_admin_ids()
        
        # نظام قفل ملفات CSV لمنع تلف البيانات عند الكتابة المتزامنة
        self.csv_locks = {}
        
        # ── In-memory user cache — eliminates CSV reads on every request ──
        self._user_cache = {}  # telegram_id -> user dict
        self._user_cache_by_phone = {}  # normalized_phone -> user dict
        self._user_cache_loaded = False
        self._user_cache_lock = threading.Lock()
        self._load_user_cache()
        
        # تهيئة البيانات المؤقتة للأدمن
        self.edit_company_data = {}
        self.temp_button_label_edit = {}
        
        # نظام الإحالات
        self.init_referral_files()
        # نظام التطبيقات
        self.init_app_links_file()
        
        # ملاحظة: المعاملات لا تنتهي صلاحيتها تلقائياً — تبقى معلقة حتى يرد الأدمن
        
        # تحميل معرفات الأدمن من متغيرات البيئة
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        if admin_ids_str:
            self.admin_user_ids = [int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip().isdigit()]
        else:
            self.admin_user_ids = []
        
        # إدارة الأدمن المؤقت (للجلسة الواحدة)
        self.temp_admin_user_ids = []

        # --- نظام صلاحيات المديرين (أزرار + أفعال) ---
        # سيتم حفظ الصلاحيات في ملف JSON مستقل حتى لا نلمس ملفات CSV الأصلية
        # البنية المتوقعة:
        # {
        #   "123456789": {
        #       "buttons": {"📋 الطلبات المعلقة": true, "🚫 حظر مستخدم": false, ...}
        #   },
        #   ...
        # }
        self.admin_permissions = self.load_admin_permissions()  # dict لكل مدير
        self.current_admin_id = None  # آخر مدير فتح لوحة الأدمن

        # تخزين انتهاء صلاحيات المدراء المؤقتين (بالثواني منذ epoch)
        # المفتاح: telegram_id للأدمن المؤقت
        self.temp_admin_expiry = {}
        # تنظيف أي مدير مؤقت منتهي عند بدء التشغيل
        self.cleanup_expired_temp_admins()

        # ── Notification hub — inject send callable ──────────────────────────
        _notif_hub.init(self.api_call)
        self.notif = _notif_hub  # convenience alias: self.notif.send(uid, text)

        # ── Rate limiter cleanup thread ──────────────────────────────────────
        _start_rl_cleanup(interval_sec=60.0)

        # ── Startup: refund bets stranded by a mid-game server crash ─────────
        # active_game_sessions rows survive restarts; credit_with_idempotency
        # in refund_expired_game_sessions() ensures idempotent double-restart safety.
        try:
            from db_manager import refund_expired_game_sessions as _rfs, _gdb as _gdb_inst
            _refunded = _rfs(_gdb_inst)
            if _refunded:
                logger.info(
                    f"[startup] Refunded {len(_refunded)} expired game session(s): {_refunded}"
                )
            else:
                logger.info("[startup] No expired game sessions to refund at startup.")
        except Exception as _rfs_err:
            logger.warning(f"[startup] refund_expired_game_sessions error: {_rfs_err}")

        # تخزين الأسباب المؤقتة لرفض المعاملات قبل التأكيد
        # المفتاح هو معرف الأدمن والقيمة عبارة عن قاموس يحتوي trans_id والسبب
        self.pending_reject_reasons = {}

        # نظام العملات: مستورد من bot_utils.constants
        self.currencies = CURRENCIES

        # تسجيل عدد المدراء الدائمين
        logger.info(f"تم تحميل {len(self.admin_user_ids)} مدير دائم: {self.admin_user_ids}")

        # بدء نظام النسخ الاحتياطي التلقائي
        self.start_backup_scheduler()

        # بدء استرداد المعاملات المعلّقة بعد 15 ثانية من انطلاق البوت
        # (نمنح وقتاً للبوت كي يتجهز ثم نرسل إشعارات الاسترداد)
        _recovery_timer = threading.Timer(15.0, self._recover_pending_states)
        _recovery_timer.daemon = True
        _recovery_timer.start()
        logger.info("مجدول: استرداد المعاملات المعلّقة بعد 15 ثانية")

        # قاموس الترجمات للنصوص الثابتة. يمكن إضافة المزيد لاحقاً.
        # يستخدم المفاتيح لتعريف النص، ويحتوي على ترجمات للعربية والانجليزية.
        self.translations = {
            # رسالة اختيار الخدمة الرئيسية للمستخدم
            'choose_service': {
                'ar': "🏠 مرحباً بك في النظام المالي\n\n👤 العميل: {name}\n🆔 رقم العميل: {customer_id}\n\nاختر الخدمة المطلوبة:",
                'en': "🏠 Welcome to the financial system\n\n👤 Customer: {name}\n🆔 Customer ID: {customer_id}\n\nChoose the required service:"
            },
            # تأكيد نجاح الإيداع للعميل
            'deposit_success': {
                'ar': "✅ تم إرسال طلب الإيداع بنجاح\n\n🆔 رقم المعاملة: {trans_id}\n👤 العميل: {name} ({customer_id})\n🏢 الشركة: {company_name}\n💳 رقم المحفظة: {wallet_number}\n💰 المبلغ: {amount}\n📅 التاريخ: {date}\n⏳ الحالة: في انتظار المراجعة\n\nسيتم إشعارك فور مراجعة طلبك.",
                'en': "✅ Deposit request sent successfully\n\n🆔 Transaction ID: {trans_id}\n👤 Customer: {name} ({customer_id})\n🏢 Company: {company_name}\n💳 Wallet number: {wallet_number}\n💰 Amount: {amount}\n📅 Date: {date}\n⏳ Status: Pending review\n\nYou will be notified once your request is reviewed."
            },
            # تأكيد نجاح السحب للعميل
            'withdraw_success': {
                'ar': "✅ تم إرسال طلب السحب بنجاح\n\n🆔 رقم المعاملة: {trans_id}\n👤 العميل: {name} ({customer_id})\n🏢 الشركة: {company_name}\n💳 رقم المحفظة: {wallet_number}\n💰 المبلغ: {amount}\n📍 عنوان السحب: {withdrawal_address}\n🔐 كود التأكيد: {confirmation_code}\n📅 التاريخ: {date}\n⏳ الحالة: في انتظار المراجعة\n\nسيتم إشعارك فور الموافقة على طلبك.",
                'en': "✅ Withdrawal request sent successfully\n\n🆔 Transaction ID: {trans_id}\n👤 Customer: {name} ({customer_id})\n🏢 Company: {company_name}\n💳 Wallet number: {wallet_number}\n💰 Amount: {amount}\n📍 Withdrawal address: {withdrawal_address}\n🔐 Confirmation code: {confirmation_code}\n📅 Date: {date}\n⏳ Status: Pending review\n\nYou will be notified once your request is approved."
            },
            # نص إلغاء السحب
            'cancel_withdraw': {
                'ar': "❌ تم إلغاء طلب السحب",
                'en': "❌ Withdrawal request cancelled"
            },
            # نص مطالبة الإدارة باختيار الإجراء
            'choose_action': {
                'ar': "اختر إجراء من الأزرار أدناه للتعامل مع الطلب.",
                'en': "Choose an action from the buttons below to handle the request."
            }
        }

    def tr(self, key: str, lang: str, **kwargs) -> str:
        """ترجمة مفتاح نصي وفقاً للغة. يعيد النص العربي إذا لم تتوفر ترجمة."""
        try:
            # 1) Try file-based i18n translations first
            file_text = self.get_i18n_text(key, lang)
            if file_text:
                return file_text.format(**kwargs)
            # 2) Fall back to inline translations dict
            template = self.translations.get(key, {}).get(lang) or self.translations.get(key, {}).get('ar')
            if not template:
                return key
            return template.format(**kwargs)
        except Exception:
            return key

    def load_i18n_translations(self):
        """تحميل ملفات الترجمة من مجلد i18n/"""
        self.i18n_translations = {}
        i18n_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n')
        if not os.path.isdir(i18n_dir):
            i18n_dir = 'i18n'
        try:
            for filename in os.listdir(i18n_dir):
                if filename.endswith('.json'):
                    lang_code = filename.replace('.json', '')
                    filepath = os.path.join(i18n_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self.i18n_translations[lang_code] = json.load(f)
            logger.info(f"Loaded i18n translations for {len(self.i18n_translations)} languages: {list(self.i18n_translations.keys())}")
        except Exception as e:
            logger.error(f"خطأ في تحميل ترجمات i18n: {e}")
            self.i18n_translations = {}

    def get_i18n_text(self, key: str, lang: str) -> str:
        """الحصول على نص مترجم من ملفات i18n"""
        if not hasattr(self, 'i18n_translations'):
            self.load_i18n_translations()
        lang_dict = self.i18n_translations.get(lang, {})
        text = lang_dict.get(key)
        if text is None and lang != 'ar':
            text = self.i18n_translations.get('ar', {}).get(key)
        if text is None:
            text = self.i18n_translations.get('en', {}).get(key)
        return text

    def get_language_names(self):
        """إرجاع قاموس بأسماء اللغات المدعومة وعلمها"""
        return {
            'ar': {'name': 'العربية', 'native': 'العربية', 'flag': '🇸🇦', 'rtl': True},
            'en': {'name': 'English', 'native': 'English', 'flag': '🇬🇧', 'rtl': False},
            'fr': {'name': 'Français', 'native': 'Français', 'flag': '🇫🇷', 'rtl': False},
            'es': {'name': 'Español', 'native': 'Español', 'flag': '🇪🇸', 'rtl': False},
            'de': {'name': 'Deutsch', 'native': 'Deutsch', 'flag': '🇩🇪', 'rtl': False},
            'it': {'name': 'Italiano', 'native': 'Italiano', 'flag': '🇮🇹', 'rtl': False},
            'pt': {'name': 'Português', 'native': 'Português', 'flag': '🇧🇷', 'rtl': False},
            'ru': {'name': 'Русский', 'native': 'Русский', 'flag': '🇷🇺', 'rtl': False},
            'zh': {'name': '中文', 'native': '中文', 'flag': '🇨🇳', 'rtl': False},
            'tr': {'name': 'Türkçe', 'native': 'Türkçe', 'flag': '🇹🇷', 'rtl': False},
            'ur': {'name': 'اردو', 'native': 'اردو', 'flag': '🇵🇰', 'rtl': True},
            'hi': {'name': 'हिन्दी', 'native': 'हिन्दी', 'flag': '🇮🇳', 'rtl': False},
            'fa': {'name': 'فارسی', 'native': 'فارسی', 'flag': '🇮🇷', 'rtl': True},
            'id': {'name': 'Indonesia', 'native': 'Indonesia', 'flag': '🇮🇩', 'rtl': False},
            'ja': {'name': '日本語', 'native': '日本語', 'flag': '🇯🇵', 'rtl': False},
            'ko': {'name': '한국어', 'native': '한국어', 'flag': '🇰🇷', 'rtl': False},
            'th': {'name': 'ไทย', 'native': 'ไทย', 'flag': '🇹🇭', 'rtl': False},
        }

    def get_supported_languages(self):
        """إرجاع قائمة أكواد اللغات المدعومة"""
        return list(self.get_language_names().keys())
        
    def _check_bot_management_permission(self, token):
        """فحص ما إذا كان هذا البوت يملك صلاحية إدارة البوتات الأخرى"""
        # البوت الرئيسي (من .env) دائماً يملك الصلاحية
        env_token = os.getenv('BOT_TOKEN', '')
        if token == env_token:
            return True

        # للبوتات المضافة: فحص bot_tokens.csv
        try:
            from multi_bot import MultiBotManager
            manager = MultiBotManager()
            for bot in manager.get_all_bots():
                if bot.get('token') == token:
                    return bot.get('can_manage_bots', 'no') == 'yes'
        except:
            pass
        return False

    def init_files(self):
        """إنشاء جميع ملفات النظام"""
        # ملف المستخدمين
        if not os.path.exists('users.csv'):
            with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['telegram_id', 'name', 'phone', 'customer_id', 'language', 'date', 'is_banned', 'ban_reason', 'currency', 'phone_verified', 'referral_earnings'])
        else:
            self.migrate_users_csv()

        # ملف سجل الإحالات التفصيلي
        if not os.path.exists('referral_log.csv'):
            with open('referral_log.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'referrer_id', 'referred_id', 'referred_name', 'referred_phone', 'phone_verified', 'bonus_amount', 'currency', 'status', 'created_at'])
        
        # ملف المعاملات المتقدم
        if not os.path.exists('transactions.csv'):
            with open('transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'customer_id', 'telegram_id', 'name', 'type', 'company', 'wallet_number', 'amount', 'exchange_address', 'status', 'date', 'admin_note', 'processed_by'])
        
        # ملف الشركات
        if not os.path.exists('companies.csv'):
            with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'type', 'details', 'is_active', 'icon', 'address', 'affiliate_link'])
                # شركات افتراضية
                companies = [
                    ['1', 'STC Pay', 'both', 'محفظة إلكترونية', 'active', '📡', '', ''],
                    ['2', 'البنك الأهلي', 'deposit', 'حساب بنكي رقم: 1234567890', 'active', '🏦', '', ''],
                    ['3', 'فودافون كاش', 'both', 'محفظة إلكترونية', 'active', '📱', '', ''],
                    ['4', 'بنك الراجحي', 'deposit', 'حساب بنكي رقم: 0987654321', 'active', '🏦', '', ''],
                    ['5', 'مدى البنك الأهلي', 'withdraw', 'رقم الحساب للسحب', 'active', '💳', '', '']
                ]
                for company in companies:
                    writer.writerow(company)
        
        # ترحيل ملف الشركات الموجود (إضافة أعمدة icon و address)
        self.migrate_companies_csv()
        self.migrate_wheel_rounds_csv()
        
        # ملف وسائل الدفع — مجموعة عامة (غير مرتبطة بشركة محددة)
        if not os.path.exists('payment_methods.csv'):
            with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon', 'currency'])
                defaults = [
                    ['1', '', 'حساب بنكي', 'حساب بنكي', '1234567890', 'البنك الأهلي', 'active', '2024-01-01', '🏦', 'SAR'],
                    ['2', '', 'محفظة STC', 'محفظة إلكترونية', '0501234567', 'STC Pay', 'active', '2024-01-01', '📱', 'SAR'],
                    ['3', '', 'فودافون كاش', 'محفظة إلكترونية', '01012345678', 'فودافون', 'active', '2024-01-01', '📱', 'EGP'],
                    ['4', '', 'حساب جاري', 'حساب بنكي', '0987654321', 'بنك الراجحي', 'active', '2024-01-01', '🏦', 'SAR'],
                ]
                for m in defaults:
                    writer.writerow(m)
        self.migrate_payment_methods_csv()

        # ملف ربط وسائل الدفع بالشركات (علاقة متعدد لمتعدد)
        if not os.path.exists('company_payment_links.csv'):
            with open('company_payment_links.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'company_id', 'method_id', 'created_at'])

        # ملف خطوات وسائل الدفع المخصصة (deposit/withdraw)
        if not os.path.exists('payment_method_steps.csv'):
            with open('payment_method_steps.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'method_id', 'flow_type', 'step_order', 'step_type', 'step_label'])

        # ملف طلبات التداول (USDT/MoneyGo)
        if not os.path.exists('trade_orders.csv'):
            with open('trade_orders.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'buyer_id', 'buyer_name', 'customer_id', 'order_type', 'asset_type',
                                 'network', 'account_address', 'payment_method', 'amount', 'currency',
                                 'usdt_amount', 'admin_payment_method', 'status', 'screenshot_payment',
                                 'screenshot_transfer', 'admin_id', 'created_at', 'completed_at'])
        
        # ملف روابط الإحالة (إدارية)
        if not os.path.exists('referral_links.csv'):
            with open('referral_links.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'url', 'is_active', 'created_at'])

        # ملف جولات اليانصيب
        if not os.path.exists('lottery_rounds.csv'):
            with open('lottery_rounds.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'status', 'ticket_price', 'currency', 'min_tickets',
                               'max_tickets_per_user', 'total_prize', 'admin_profit_pct',
                               'start_time', 'draw_time', 'winner_count', 'created_at'])

        # ملف تذاكر اليانصيب
        if not os.path.exists('lottery_tickets.csv'):
            with open('lottery_tickets.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'round_id', 'user_id', 'user_name', 'customer_id',
                               'ticket_number', 'purchase_time', 'payment_method', 'payment_verified'])

        # ملف الفائزين باليانصيب
        if not os.path.exists('lottery_winners.csv'):
            with open('lottery_winners.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'round_id', 'user_id', 'user_name', 'ticket_number',
                               'prize_amount', 'currency', 'rank', 'draw_time'])

        # ملف عجلة الحظ
        if not os.path.exists('wheel_rounds.csv'):
            with open('wheel_rounds.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'prizes', 'status', 'spin_cost', 'currency',
                               'min_spins', 'max_spins_per_user', 'game_speed_ms', 'max_relocations', 'created_at'])

        if not os.path.exists('wheel_spins.csv'):
            with open('wheel_spins.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'round_id', 'user_id', 'prize_won', 'spin_time'])

        if not os.path.exists('wheel_gifts.csv'):
            with open('wheel_gifts.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'gift_text', 'affiliate_link', 'is_active', 'created_at'])

        # ملف القنوات/المجموعات المرتبطة بالبوت
        if not os.path.exists('bot_channels.csv'):
            with open('bot_channels.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'chat_id', 'title', 'type', 'is_active', 'added_at'])

        # ملف عناوين الصرافة
        if not os.path.exists('exchange_addresses.csv'):
            with open('exchange_addresses.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'address', 'is_active'])
                writer.writerow(['1', 'شارع الملك فهد، الرياض، مقابل مول الرياض - الدور الأول', 'yes'])
        
        # ملف الشكاوى
        if not os.path.exists('complaints.csv'):
            with open('complaints.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'customer_id', 'message', 'status', 'date', 'admin_response'])
        
        # ملف إعدادات النظام
        if not os.path.exists('system_settings.csv'):
            with open('system_settings.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['setting_key', 'setting_value', 'description'])
                settings = [
                    ['min_deposit', '50', 'أقل مبلغ إيداع'],
                    ['min_withdrawal', '100', 'أقل مبلغ سحب'],
                    ['max_daily_withdrawal', '10000', 'أقصى سحب يومي'],
                    ['support_phone', '+966501234567', 'رقم الدعم'],
                    ['company_name', 'DUX', 'اسم الشركة'],
                    ['default_currency', 'SAR', 'العملة الافتراضية']
                ]
                for setting in settings:
                    writer.writerow(setting)
        
        # ملف مكتبة الرموز والاستيكرات
        if not os.path.exists('sticker_library.csv'):
            with open('sticker_library.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'type', 'file_id', 'emoji', 'set_name', 'category', 'added_by', 'added_at'])

        # ملف استبدال النصوص في القنوات
        if not os.path.exists('text_replacements.csv'):
            with open('text_replacements.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'find_text', 'replace_text', 'is_regex', 'channel_id', 'is_active', 'created_at'])

        # ملف بوستات AI المُعالجة
        if not os.path.exists('ai_processed_posts.csv'):
            with open('ai_processed_posts.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'source_channel', 'source_chat_id', 'original_text', 'processed_text',
                               'ai_model', 'status', 'created_at', 'published_at', 'users_reached', 'channels_reached'])

        # ملف التسويق — خُطط وتحليلات
        if not os.path.exists('marketing_plans.csv'):
            with open('marketing_plans.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'plan_type', 'content', 'ai_provider', 'status', 'approved_by',
                               'executed_at', 'results', 'created_at'])

        # ملف القنوات المصدرية (بوت مشترك لكن ليس أدمن)
        if not os.path.exists('source_channels.csv'):
            with open('source_channels.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'chat_id', 'title', 'type', 'is_active', 'added_at',
                               'brand_voice', 'target_channel_ids', 'schedule', 'last_scraped_at'])

        # ملف التقارير اليومية
        if not os.path.exists('daily_reports.csv'):
            with open('daily_reports.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'date', 'total_posts', 'total_users_reached', 'total_channels_reached',
                               'ai_usage_count', 'top_channels', 'recommendations', 'created_at'])

        logger.info("تم إنشاء جميع ملفات النظام بنجاح")
        
    # خريطة الأيقونات: تحويل نص/إيموجي إلى أيقونة مناسبة
    ICON_MAP = {
        'bank': '🏦', 'banks': '🏦', 'بنك': '🏦', 'مصرف': '🏦', 'البنك': '🏦', 'بنكي': '🏦',
        'wallet': '👛', 'e-wallet': '👛', 'ewallet': '👛', 'محفظة': '👛', 'محفظه': '👛',
        'phone': '📱', 'mobile': '📱', 'هاتف': '📱', 'جوال': '📱', 'موبايل': '📱',
        'cash': '💵', 'نقدي': '💵', 'كاش': '💵', 'نقد': '💵', 'مبلغ': '💵',
        'card': '💳', 'credit': '💳', 'debit': '💳', 'بطاقة': '💳', 'بطاقه': '💳', 'مدى': '💳', 'visa': '💳', 'mastercard': '💳',
        'crypto': '🪙', 'bitcoin': '🪙', 'بيتكوين': '🪙', 'عملة': '🪙', 'كريبتو': '🪙', 'usdt': '🪙', 'ethereum': '🪙', 'usd': '🪙',
        'paypal': '🅿️', 'باي بال': '🅿️',
        'stc': '📡', 'stc pay': '📡', 'stcpay': '📡', 'اس تي سي': '📡',
        'vodafone': '📱', 'فودافون': '📱', 'فودافون كاش': '📱',
        'company': '🏢', 'شركة': '🏢', 'business': '🏢', 'مؤسسة': '🏢', 'مؤسسه': '🏢',
        'exchange': '🔄', 'صرافة': '🔄', 'صرافه': '🔄', 'مقايضة': '🔄',
        'money': '💰', 'مال': '💰', 'أموال': '💰', 'رصيد': '💰',
        'transfer': '📤', 'تحويل': '📤', 'ارسال': '📤', 'إرسال': '📤',
        'store': '🏬', 'متجر': '🏬', 'shop': '🏬', 'سوق': '🏬',
        'online': '🌐', 'أونلاين': '🌐', 'انترنت': '🌐', 'موقع': '🌐',
        'gift': '🎁', 'هدية': '🎁', 'هدية': '🎁', 'مكافأة': '🎁',
        'gold': '🥇', 'ذهب': '🥇', 'ذهبية': '🥇',
        'rocket': '🚀', 'صاروخ': '🚀', 'سريع': '🚀',
        'star': '⭐', 'نجمة': '⭐', 'نجم': '⭐', 'مميز': '⭐',
        'check': '✅', 'صح': '✅', 'موافق': '✅',
        'invest': '📈', 'استثمار': '📈', 'استثمار': '📈',
        'shield': '🛡️', 'حماية': '🛡️', 'أمان': '🛡️',
        'crown': '👑', 'ملك': '👑', 'ملكي': '👑',
        'diamond': '💎', 'ماس': '💎', 'الماسة': '💎',
        'fire': '🔥', 'نار': '🔥', 'حار': '🔥',
        'bolt': '⚡', 'برق': '⚡', 'سريع': '⚡',
        'chart': '📊', 'رسم': '📊', 'إحصائيات': '📊', 'احصائيات': '📊',
        'bell': '🔔', 'جرس': '🔔', 'تنبيه': '🔔', 'إشعار': '🔔',
        'lock': '🔐', 'قفل': '🔐', 'مغلق': '🔐',
        'key': '🔑', 'مفتاح': '🔑', 'كود': '🔑',
        'user': '👤', 'مستخدم': '👤', 'عميل': '👤', 'شخص': '👤',
        'users': '👥', 'مستخدمين': '👥', 'عملاء': '👥', 'مجموعة': '👥',
        'gear': '⚙️', 'ترس': '⚙️', 'إعدادات': '⚙️', 'اعدادات': '⚙️',
        'robot': '🤖', 'بوت': '🤖', 'روبوت': '🤖',
        'game': '🎮', 'لعبة': '🎮', 'ألعاب': '🎮',
        'car': '🚗', 'سيارة': '🚗', 'سياره': '🚗',
        'plane': '✈️', 'طائرة': '✈️', 'طيران': '✈️', 'سفر': '✈️',
        'house': '🏠', 'منزل': '🏠', 'عقار': '🏠', 'عقارات': '🏠',
        'food': '🍔', 'طعام': '🍔', 'مطعم': '🍔', 'اكل': '🍔',
        'coffee': '☕', 'قهوة': '☕', 'كافيه': '☕',
        'book': '📚', 'كتاب': '📚', 'كتب': '📚', 'مكتبة': '📚',
        'globe': '🌍', 'عالم': '🌍', 'دولي': '🌍',
        'sun': '☀️', 'شمس': '☀️', 'صيف': '☀️',
        'moon': '🌙', 'قمر': '🌙', 'ليل': '🌙',
        'heart': '❤️', 'قلب': '❤️', 'حب': '❤️',
        'thumbsup': '👍', 'اعجاب': '👍', 'جيد': '👍',
        'warning': '⚠️', 'تحذير': '⚠️', 'انتباه': '⚠️',
        'screenshot': '📸', 'لقطة': '📸', 'صورة': '📸', 'صوره': '📸',
        # Animated/lively emoji for services
        'deposit': '⬇️', 'إيداع': '⬇️', 'ايداع': '⬇️', 'ايداع_فقط': '⬇️',
        'withdraw': '⬆️', 'سحب': '⬆️', 'سحب_فقط': '⬆️',
        'both': '🔄', 'كلاهما': '🔄', 'ايداع_وسحب': '🔄',
        'lottery': '🎰', 'يانصيب': '🎰',
        'wheel': '🎡', 'عجلة': '🎡', 'صيد': '🎯',
        'hunt': '🎯', 'جوائز': '🎯',
        'match': '🔗', 'مطابقة': '🔗',
        'trade': '💱', 'تداول': '💱',
        'compensation': '💎', 'تعويض': '💎', 'استرداد': '💎',
        'referral': '🎁', 'إحالة': '🎁', 'اربح': '🎁',
        'support': '🆘', 'دعم': '🆘', 'مساعدة': '❓',
        'notification': '🔔', 'إشعارات': '🔔', 'إشعاراتي': '🔔',
        'profile': '👤', 'الملف': '👤',
        'admin': '🔧', 'الإدارة': '🔧', 'الأدمن': '🔧',
        'apps': '📱', 'تطبيقات': '📱',
        'bots': '🤖', 'البوتات': '🤖',
        'channels': '📢', 'القنوات': '📢',
        'statistics': '📊', 'الإحصائيات': '📊', 'احصائيات': '📊',
        'excel': '📑', 'تقرير': '📑',
        'broadcast': '📢', 'إرسال': '📢', 'الإرسال': '📢',
        'complaints': '📨', 'الشكاوى': '📨', 'شكاوى': '📨',
        'payment': '💳', 'الدفع': '💳', 'وسائل_الدفع': '💳',
        'companies': '🏢', 'الشركات': '🏢',
        'addresses': '📍', 'العناوين': '📍',
        'themes': '🎨', 'الثيمات': '🎨',
        'settings': '⚙️', 'الإعدادات': '⚙️',
        'language': '🌐', 'اللغة': '🌐',
        'backup': '💾', 'نسخة': '💾', 'احتياطية': '💾',
        'stickers': '🗃️', 'الرموز': '🗃️', 'الاستيكرات': '🗃️',
        'manager': '👥', 'المديرين': '👥',
        'buttons': '✏️', 'الأزرار': '✏️',
        'trading': '💱', 'التداول': '💱',
        'matching': '🔗', 'المطابقات': '🔗',
        # Payment methods specific
        'mada': '💳', 'مدى': '💳',
        'iban': '🏦', 'ايبان': '🏦',
        'binance': '🟡', 'بايننس': '🟡',
        'binance_pay': '🟡', 'بايننس_باي': '🟡',
        'western_union': '🌍', 'ويسترن_يونيون': '🌍',
        'moneygram': '🌍', 'موني_جرام': '🌍',
        'moneygo': '🌍', 'موني_جو': '🌍',
        # Service types
        'deposit_service': '⬇️', 'withdraw_service': '⬆️',
        'deposit_withdraw': '🔄',
    }

    def normalize_icon(self, icon_input, default='🏢'):
        """تحويل أي صيغة إدخال إلى أيقونة مناسبة"""
        if not icon_input or not icon_input.strip():
            return default
        icon_input = icon_input.strip()
        # إذا كان إيموجي بالفعل (يحتوي على أحرف غير ASCII قصيرة)
        if len(icon_input) <= 4 and any(ord(c) > 127 for c in icon_input):
            return icon_input
        # إذا كان URL
        if icon_input.startswith('http'):
            return icon_input
        # البحث في خريطة الأيقونات
        lower = icon_input.lower()
        if lower in self.ICON_MAP:
            return self.ICON_MAP[lower]
        # البحث بدون مسافات
        no_space = lower.replace(' ', '').replace('-', '').replace('_', '')
        for key, val in self.ICON_MAP.items():
            if key.replace(' ', '').replace('-', '').replace('_', '') == no_space:
                return val
        # محاولة المطابقة الجزئية — ابحث عن أي كلمة في الاسم
        for key, val in self.ICON_MAP.items():
            if key in lower or lower in key:
                return val
        # إذا لم يوجد، استخدم 🏢
        return default

    def get_company_icon(self, company_name='', company_icon='', company_id=''):
        """
        الحصول على أيقونة الشركة — ذكي ومتطور
        1) إذا كان icon إيموجي صالح → استخدمه مباشرة
        2) إذا كان icon URL → استخدمه
        3) ابحث في sticker_library.csv عن إيموجي مرتبط بالشركة
        4) ابحث في ICON_MAP عن مطابقة لاسم الشركة
        5) استخدم 🏢 كافتراضي
        """
        # 1) إيموجي صالح من حقل icon
        if company_icon and company_icon.strip():
            icon = company_icon.strip()
            if len(icon) <= 4 and any(ord(c) > 127 for c in icon):
                return icon
            if icon.startswith('http'):
                return icon
            # حاول normalizing
            normalized = self.normalize_icon(icon, None)
            if normalized and normalized != '🏷️':
                return normalized

        # 2) ابحث في المكتبة
        if company_id:
            try:
                with open('sticker_library.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('category') == f'company_{company_id}' and row.get('type') == 'emoji':
                            emoji = row.get('emoji', '').strip()
                            if emoji:
                                return emoji
            except:
                pass

        # 3) ابحث في ICON_MAP باسم الشركة
        if company_name:
            icon = self.normalize_icon(company_name, None)
            if icon and icon != '🏷️':
                return icon

        return '🏢'

    def get_method_icon(self, method_name='', method_type='', method_id=''):
        """
        الحصول على أيقونة وسيلة الدفع — ذكي
        """
        # ابحث في ICON_MAP باسم الوسيلة
        if method_name:
            icon = self.normalize_icon(method_name, None)
            if icon and icon != '🏷️':
                return icon

        # ابحث في ICON_MAP بنوع الوسيلة
        if method_type:
            icon = self.normalize_icon(method_type, None)
            if icon and icon != '🏷️':
                return icon

        # ابحث في المكتبة
        if method_id:
            try:
                with open('sticker_library.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('category') == f'method_{method_id}' and row.get('type') == 'emoji':
                            emoji = row.get('emoji', '').strip()
                            if emoji:
                                return emoji
            except:
                pass

        return '💳'

    def migrate_users_csv(self):
        """ترحيل users.csv لإضافة أعمدة phone_verified و referral_earnings"""
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
            if 'phone_verified' in fieldnames:
                return
            new_fields = list(fieldnames) + ['phone_verified', 'referral_earnings']
            for row in rows:
                row['phone_verified'] = 'unknown'
                row['referral_earnings'] = '0'
            with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=new_fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in new_fields})
            logger.info("تم ترحيل users.csv لإضافة أعمدة phone_verified و referral_earnings")
        except Exception as e:
            logger.error(f"خطأ في ترحيل users.csv: {e}")

    def migrate_companies_csv(self):
        """ترحيل companies.csv لإضافة أعمدة icon, address, affiliate_link, icon_file_id"""
        try:
            with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
            need_migration = ('icon' not in fieldnames or 'address' not in fieldnames or
                              'affiliate_link' not in fieldnames or 'icon_file_id' not in fieldnames)
            if not need_migration:
                return
            new_fieldnames = list(fieldnames)
            for col in ['icon', 'address', 'affiliate_link', 'icon_file_id']:
                if col not in new_fieldnames:
                    new_fieldnames.append(col)
            for row in rows:
                if 'icon' not in row or not row.get('icon'):
                    row['icon'] = '🏢'
                if 'address' not in row:
                    row['address'] = ''
                if 'affiliate_link' not in row:
                    row['affiliate_link'] = ''
                if 'icon_file_id' not in row:
                    row['icon_file_id'] = ''
            with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=new_fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in new_fieldnames})
            logger.info("تم ترحيل companies.csv لإضافة أعمدة icon_file_id")
        except Exception as e:
            logger.error(f"خطأ في ترحيل companies.csv: {e}")

    def migrate_wheel_rounds_csv(self):
        """ترحيل wheel_rounds.csv لإضافة أعمدة game_speed_ms و max_relocations"""
        try:
            if not os.path.exists('wheel_rounds.csv'):
                return
            with open('wheel_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
            need_migration = 'game_speed_ms' not in fieldnames or 'max_relocations' not in fieldnames
            if not need_migration:
                return
            new_fieldnames = list(fieldnames)
            for col in ['game_speed_ms', 'max_relocations']:
                if col not in new_fieldnames:
                    new_fieldnames.append(col)
            for row in rows:
                if not row.get('game_speed_ms'):
                    row['game_speed_ms'] = '2500'
                if not row.get('max_relocations'):
                    row['max_relocations'] = '1'
            with open('wheel_rounds.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=new_fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in new_fieldnames})
            logger.info("تم ترحيل wheel_rounds.csv لإضافة أعمدة game_speed_ms و max_relocations")
        except Exception as e:
            logger.error(f"خطأ في ترحيل wheel_rounds.csv: {e}")

    def migrate_payment_methods_csv(self):
        """ترحيل payment_methods.csv لإضافة عمود icon و icon_file_id"""
        try:
            with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
            need_migration = 'icon' not in fieldnames or 'icon_file_id' not in fieldnames
            if not need_migration:
                return
            new_fieldnames = list(fieldnames)
            if 'icon' not in new_fieldnames:
                new_fieldnames.append('icon')
            if 'icon_file_id' not in new_fieldnames:
                new_fieldnames.append('icon_file_id')
            for row in rows:
                if 'icon' not in row or not row.get('icon'):
                    row['icon'] = self.normalize_icon(row.get('method_type', ''), default='💳')
                if 'icon_file_id' not in row:
                    row['icon_file_id'] = ''
            with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=new_fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in new_fieldnames})
            logger.info("تم ترحيل payment_methods.csv لإضافة أعمدة icon و icon_file_id")
        except Exception as e:
            logger.error(f"خطأ في ترحيل payment_methods.csv: {e}")
        
    def init_button_labels(self):
        """تحميل أو إنشاء ملف مسميات الأزرار القابلة للتعديل من لوحة الأدمن"""
        self.button_labels = {}
        try:
            file_name = 'button_labels.csv'
            if not os.path.exists(file_name):
                # إنشاء ملف جديد مع ترويسة الأعمدة
                with open(file_name, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['original_text', 'new_text', 'is_active'])
                return

            with open(file_name, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row:
                        continue
                    original = (row.get('original_text') or '').strip()
                    new_text = (row.get('new_text') or '').strip()
                    is_active = (row.get('is_active') or 'yes').strip().lower()
                    if original and new_text and is_active in ['yes', 'active', '1', 'true', '']:
                        self.button_labels[original] = new_text

            logger.info("تم تحميل مسميات الأزرار القابلة للتعديل، عددها: %s", len(self.button_labels))
        except Exception as e:
            logger.error("خطأ أثناء تحميل button_labels.csv: %s", e)
            self.button_labels = {}

    def update_button_label(self, original_text, new_text):
        """تحديث أو إضافة مسمى زر في ملف button_labels.csv"""
        try:
            file_name = 'button_labels.csv'
            rows = []
            found = False

            if os.path.exists(file_name):
                with open(file_name, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if not row:
                            continue
                        if (row.get('original_text') or '').strip() == original_text:
                            row['original_text'] = original_text
                            row['new_text'] = new_text
                            row['is_active'] = row.get('is_active') or 'yes'
                            found = True
                        rows.append(row)

            if not found:
                rows.append({
                    'original_text': original_text,
                    'new_text': new_text,
                    'is_active': 'yes'
                })

            with open(file_name, 'w', newline='', encoding='utf-8-sig') as f:
                fieldnames = ['original_text', 'new_text', 'is_active']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({
                        'original_text': (row.get('original_text') or '').strip(),
                        'new_text': (row.get('new_text') or '').strip(),
                        'is_active': (row.get('is_active') or 'yes').strip() or 'yes'
                    })

            logger.info("تم تحديث مسمى الزر: %s -> %s", original_text, new_text)
            return True
        except Exception as e:
            logger.error("خطأ أثناء تحديث button_labels.csv: %s", e)
            return False

    def apply_button_label(self, text):
        """إرجاع النص المعدل للزر إن وجد، أو النص الأصلي — مع اقتطاع لحد تليجرام"""
        try:
            mapping = getattr(self, 'button_labels', None) or {}
            result = mapping.get(text, text)
            # تليجرام حد 64 حرف لنص الزر
            if len(result) > 60:
                result = result[:57] + '...'
            return result
        except Exception:
            return text

    def normalize_button_text(self, text):
        """
        عند استقبال نص زر من المستخدم، نعيده إلى النص الأصلي
        إذا كان قد تم تعديله في لوحة الأدمن، حتى يستمر الكود في العمل على النصوص الأصلية.
        """
        try:
            mapping = getattr(self, 'button_labels', None) or {}
            for original, new_text in mapping.items():
                if text == new_text:
                    return original
        except Exception:
            pass
        return text

    def sanitize_input(self, text):
        """تنظيف مدخلات المستخدم — delegated to bot_utils.validation"""
        return sanitize_input(text)

    def check_rate_limit(self, user_id, action_type='general'):
        """فحص حد المعدل لمنع الإساءة — 30 طلب لكل دقيقة (مناسب للتدفقات متعددة الخطوات)"""
        if not hasattr(self, 'rate_limit_data'):
            self.rate_limit_data = {}
        key = f"{user_id}_{action_type}"
        now = time.time()
        if key in self.rate_limit_data:
            entries = self.rate_limit_data[key]
            # Remove entries older than 60 seconds
            entries = [t for t in entries if now - t < 60]
            if len(entries) >= 30:
                return False  # Rate limited
            entries.append(now)
            self.rate_limit_data[key] = entries
        else:
            self.rate_limit_data[key] = [now]
        return True

    def validate_phone_number(self, phone):
        """التحقق من صحة رقم الهاتف — delegated to bot_utils.validation"""
        return validate_phone_number(phone)

    def validate_amount(self, amount_str):
        """التحقق من صحة المبلغ المدخل — delegated to bot_utils.validation"""
        return validate_amount(amount_str)

    def transform_keyboard(self, keyboard):
        """تطبيق مسميات الأزرار المعدلة على أي لوحة مفاتيح قبل إرسالها لتليجرام"""
        try:
            if not isinstance(keyboard, dict):
                return keyboard

            kb = {**keyboard}

            if 'keyboard' in kb:
                new_keyboard = []
                for row in kb['keyboard']:
                    new_row = []
                    for btn in row:
                        if isinstance(btn, dict):
                            new_btn = dict(btn)
                            new_btn['text'] = self.apply_button_label(new_btn.get('text', ''))
                            new_row.append(new_btn)
                        else:
                            new_row.append(btn)
                    new_keyboard.append(new_row)
                kb['keyboard'] = new_keyboard

            if 'inline_keyboard' in kb:
                new_inline_keyboard = []
                for row in kb['inline_keyboard']:
                    new_row = []
                    for btn in row:
                        if isinstance(btn, dict):
                            new_btn = dict(btn)
                            new_btn['text'] = self.apply_button_label(new_btn.get('text', ''))
                            new_row.append(new_btn)
                        else:
                            new_row.append(btn)
                    new_inline_keyboard.append(new_row)
                kb['inline_keyboard'] = new_inline_keyboard

            return kb
        except Exception as e:
            logger.error("خطأ أثناء تعديل لوحة المفاتيح للأزرار: %s", e)
            return keyboard


    def api_call(self, method, data=None, retries=3):
        """استدعاء API مُحسن — مع إعادة المحاولة التلقائية"""
        url = f"{self.api_url}/{method}"
        last_error = None
        
        for attempt in range(retries):
            try:
                if data:
                    json_data = json.dumps(data).encode('utf-8')
                    req = urllib.request.Request(url, data=json_data)
                    req.add_header('Content-Type', 'application/json')
                else:
                    req = urllib.request.Request(url)
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    if result.get('ok'):
                        return result
                    else:
                        error_desc = result.get('description', 'unknown')
                        # أخطاء غير قابلة لإعادة المحاولة — تخطي فوراً
                        if 'chat not found' in error_desc or 'blocked' in error_desc or 'chat_id is empty' in error_desc:
                            return result
                        # HTTP 400 = خطأ في الطلب نفسه — لا فائدة من إعادة المحاولة
                        if 'Bad Request' in error_desc or 'message is not modified' in error_desc:
                            logger.warning(f"API {method} skipped (non-retryable): {error_desc}")
                            return result
                        last_error = f"API error: {error_desc}"
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
                # 400/403 = خطأ دائم — لا تعيد المحاولة
                if e.code in (400, 403):
                    logger.warning(f"API {method} skipped (HTTP {e.code}): {e.reason}")
                    return None
                if e.code == 429:  # Rate limited
                    retry_after = 1
                    logger.warning(f"Rate limited by Telegram, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue
            except Exception as e:
                last_error = str(e)
            
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))  # backoff تدريجي
        
        logger.error(f"API call failed after {retries} retries: {method} - {last_error}")
        return None
    
    def send_message(self, chat_id, text, keyboard=None):
        """إرسال رسالة"""
        data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
        if keyboard:
            if isinstance(keyboard, dict):
                data['reply_markup'] = self.transform_keyboard(keyboard)
            else:
                data['reply_markup'] = keyboard
        return self.api_call('sendMessage', data)
    
    def send_inline_message(self, chat_id, text, inline_buttons, web_app_button=None):
        """إرسال رسالة بأزرار Inline (داخل الدردشة)"""
        inline_keyboard = {'inline_keyboard': inline_buttons}
        data = {
            'chat_id': chat_id, 
            'text': text, 
            'parse_mode': 'HTML',
            'reply_markup': json.dumps(inline_keyboard)
        }
        return self.api_call('sendMessage', data)
    
    def answer_callback(self, callback_query_id, text=None):
        """الرد على callback query لإزالة loading"""
        data = {'callback_query_id': callback_query_id}
        if text:
            data['text'] = text
        return self.api_call('answerCallbackQuery', data)
    
    def edit_message(self, chat_id, message_id, text=None, inline_buttons=None, web_app_button=None):
        """تعديل رسالة موجودة (لتحديث الأزرار بعد الضغط)"""
        data = {'chat_id': chat_id, 'message_id': message_id}
        if text:
            data['text'] = text
            data['parse_mode'] = 'HTML'
        if inline_buttons:
            data['reply_markup'] = json.dumps({'inline_keyboard': inline_buttons})
        elif web_app_button:
            data['reply_markup'] = json.dumps({'inline_keyboard': [[web_app_button]]})
        return self.api_call('editMessageText', data)
    
    def make_inline_btn(self, text, callback_data):
        """إنشاء زر inline بسرعة — delegated to bot_utils.telegram_helpers"""
        return make_inline_btn(text, callback_data)
    
    def make_inline_keyboard(self, rows):
        """إنشاء لوحة inline من قائمة صفوف — delegated to bot_utils.telegram_helpers"""
        return make_inline_keyboard(rows)
    
    def get_updates(self):
        """جلب التحديثات — يشمل my_chat_member لتسجيل القنوات تلقائياً"""
        url = f"{self.api_url}/getUpdates?offset={self.offset + 1}&timeout=10&allowed_updates=%5B%22message%22%2C%22callback_query%22%2C%22my_chat_member%22%2C%22chat_member%22%2C%22channel_post%22%5D"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"خطأ في جلب التحديثات: {e}")
            return None
    
    def _get_csv_lock(self, filename):
        """الحصول على قفل لملف CSV محدد"""
        if filename not in self.csv_locks:
            self.csv_locks[filename] = threading.Lock()
        return self.csv_locks[filename]
    
    def safe_csv_write(self, filename, rows, fieldnames=None, mode='a'):
        """كتابة آمنة في SQLite (بدلاً من CSV)"""
        from database import csv_write
        return csv_write(filename, rows, fieldnames=fieldnames, mode=mode)

    def safe_csv_read(self, filename):
        """قراءة آمنة من SQLite (بدلاً من CSV)"""
        from database import csv_read
        return csv_read(filename)

    def read_csv_helper(self, filename):
        """مساعد قراءة من SQLite (بدلاً من CSV)"""
        from database import csv_read
        return csv_read(filename)
    
    def init_referral_files(self):
        """إنشاء ملفات نظام الإحالات"""
        if not os.path.exists('referrals.csv'):
            with open('referrals.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'referrer_id', 'referrer_customer_id', 'referred_id', 'referred_phone', 'status', 'created_at', 'reward_given'])
        if not os.path.exists('user_activity.csv'):
            with open('user_activity.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['telegram_id', 'last_login', 'total_transactions', 'total_deposits', 'total_withdrawals', 'rating_avg', 'last_activity'])

    APP_FIELDS = ['id', 'name', 'icon_url', 'icon_file_id', 'android_url', 'android_file_id', 'ios_url', 'ios_file_id', 'promo_code', 'referral_link', 'description', 'is_active', 'created_at']

    def init_app_links_file(self):
        """إنشاء وترحيل ملف التطبيقات"""
        if not os.path.exists('app_links.csv'):
            with open('app_links.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(self.APP_FIELDS)
        else:
            self.migrate_app_links_csv()

    def migrate_app_links_csv(self):
        """ترحيل app_links.csv — يدعم كل إصدارات الملف"""
        try:
            with open('app_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
            if 'promo_code' in fieldnames:
                return  # أحدث إصدار
            for row in rows:
                if 'android_url' not in row:
                    old_url = row.get('download_url', '')
                    old_apk = row.get('apk_file_id', '')
                    row['android_url'] = old_url if old_url else ''
                    row['android_file_id'] = old_apk if old_apk else ''
                if 'ios_url' not in row:
                    row['ios_url'] = ''
                if 'ios_file_id' not in row:
                    row['ios_file_id'] = ''
                if 'icon_file_id' not in row:
                    row['icon_file_id'] = ''
                if 'promo_code' not in row:
                    row['promo_code'] = ''
                if 'referral_link' not in row:
                    row['referral_link'] = ''
                if 'is_active' not in row:
                    row['is_active'] = 'yes'
            with open('app_links.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.APP_FIELDS)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in self.APP_FIELDS})
            logger.info("تم ترحيل app_links.csv لإضافة أعمدة promo_code/referral_link")
        except Exception as e:
            logger.error(f"خطأ في ترحيل app_links.csv: {e}")

    def get_app_links(self):
        """جلب جميع التطبيقات النشطة"""
        apps = []
        try:
            with open('app_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('is_active') == 'yes':
                        apps.append(row)
        except:
            pass
        return apps

    def get_all_app_links(self):
        """جلب جميع التطبيقات (للأدمن)"""
        apps = []
        try:
            with open('app_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    apps.append(row)
        except:
            pass
        return apps

    def add_app_link(self, name, icon_url='', icon_file_id='', android_url='', android_file_id='', ios_url='', ios_file_id='', promo_code='', referral_link='', description=''):
        """إضافة تطبيق جديد"""
        app_id = f"APP{str(int(datetime.now().timestamp()))[-6:]}"
        try:
            with open('app_links.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([app_id, name, icon_url, icon_file_id, android_url, android_file_id, ios_url, ios_file_id, promo_code, referral_link, description, 'yes', datetime.now().strftime('%Y-%m-%d %H:%M')])
            return app_id
        except Exception as e:
            logger.error(f"خطأ في إضافة تطبيق: {e}")
            return None

    def delete_app_link(self, app_id):
        """حذف تطبيق"""
        try:
            rows = []
            found = False
            with open('app_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row['id'] == app_id:
                        found = True
                        continue
                    rows.append(row)
            if found:
                with open('app_links.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
            return found
        except Exception as e:
            logger.error(f"خطأ في حذف تطبيق: {e}")
            return False

    def toggle_app_link(self, app_id):
        """تفعيل/إيقاف تطبيق"""
        try:
            rows = []
            with open('app_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row['id'] == app_id:
                        row['is_active'] = 'no' if row.get('is_active') == 'yes' else 'yes'
                    rows.append(row)
            with open('app_links.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            return True
        except Exception as e:
            logger.error(f"خطأ في تبديل حالة تطبيق: {e}")
            return False

    def get_app_by_id(self, app_id):
        """جلب تطبيق بالمعرف"""
        try:
            with open('app_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == app_id:
                        return row
        except:
            pass
        return None

    def _update_app_link(self, app_id, data):
        """تحديث تطبيق موجود"""
        try:
            rows = []
            with open('app_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row['id'] == app_id:
                        row['name'] = data.get('name', row.get('name', ''))
                        row['icon_url'] = data.get('icon_url', '')
                        row['icon_file_id'] = data.get('icon_file_id', '')
                        row['android_url'] = data.get('android_url', '')
                        row['android_file_id'] = data.get('android_file_id', '')
                        row['ios_url'] = data.get('ios_url', '')
                        row['ios_file_id'] = data.get('ios_file_id', '')
                        row['promo_code'] = data.get('promo_code', '')
                        row['referral_link'] = data.get('referral_link', '')
                        row['description'] = data.get('description', '')
                    rows.append(row)
            with open('app_links.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث تطبيق: {e}")
            return False
    
    def cleanup_old_transactions(self):
        """معطل — لا تنتهي صلاحية أي طلبات. تبقى معلقة حتى يرد الأدمن."""
        pass

    # ==================== نظام الإحالات ====================

    def generate_referral_code(self, customer_id):
        """توليد كود إحالة من رقم العميل"""
        return f"REF{customer_id}"

    def get_user_referral_code(self, user):
        """الحصول على كود إحالة المستخدم"""
        if not user:
            return None
        return self.generate_referral_code(user.get('customer_id', ''))

    def get_referral_count(self, telegram_id):
        """عدد الإحالات الناجحة لمستخدم"""
        try:
            rows = self.safe_csv_read('referrals.csv')
            return sum(1 for r in rows if r.get('referrer_id') == str(telegram_id) and r.get('status') == 'completed')
        except:
            return 0

    def show_referral_panel(self, message):
        """عرض لوحة اربح — كود الإحالة + روابط مشاركة"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        lang = user.get('language', 'ar')
        ref_code = self.get_user_referral_code(user)
        ref_count = self.get_referral_count(message['from']['id'])

        # كود الإحالة
        bot_username = ''
        try:
            me = self.api_call('getMe', {})
            if me and me.get('ok'):
                bot_username = me['result'].get('username', '')
        except:
            pass

        ref_url = f"https://t.me/{bot_username}?start={ref_code}" if bot_username else f"Code: {ref_code}"

        text = (
            f"🎁 <b>اربح</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 كود الإحالة الخاص بك:\n"
            f"<code>{ref_code}</code> 👈 اضغط للنسخ\n\n"
            f"🔗 رابط الإحالة:\n"
            f"<code>{ref_url}</code> 👈 اضغط للنسخ\n\n"
            f"👥 عدد الدعوات: <code>{ref_count}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
        )

        # عرض رصيد الإحالات من محفظة التعويض
        if self.svrp:
            wallet = self.svrp.get_wallet(message['from']['id'])
            frozen = float(wallet.get('balance', 0) or 0)
            available = float(wallet.get('total_used', 0) or 0)
            text += self.tr('a0001_رصيد_مجمد', lang, frozen=frozen)
            text += self.tr('a0002_رصيد_متاح', lang, available=available)

        # أزرار المشاركة (روابط إحالة من الأدمن)
        inline_btns = []
        try:
            with open('referral_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('is_active') == 'yes':
                        name = row.get('name', '')
                        url = row.get('url', '')
                        if url:
                            inline_btns.append([{'text': f"📤 {name}", 'url': url}])
        except:
            pass

        inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'ref_back_main'}])
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_referral_earnings_admin(self, message):
        """لوحة أرباح الإحالة — عرض الإحالات + إعدادات + تحرير الأرصدة"""
        # قراءة الإعدادات
        bonus_amount = self.get_setting('referral_bonus_amount') or '10'
        bonus_currency = self.get_setting('referral_bonus_currency') or 'SAR'

        # قراءة سجل الإحالات
        referrals = []
        try:
            with open('referral_log.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                referrals = list(reader)
        except:
            pass

        # إحصائيات
        total = len(referrals)
        verified = sum(1 for r in referrals if r.get('phone_verified') == 'yes')
        manual = sum(1 for r in referrals if r.get('phone_verified') == 'no')
        total_bonus = sum(float(r.get('bonus_amount', 0) or 0) for r in referrals)

        text = (
            f"🏆 <b>أرباح الإحالة</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ <b>الإعدادات الحالية:</b>\n"
            f"💰 ربح كل تسجيل: <code>{bonus_amount}</code> {bonus_currency}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>الإحصائيات:</b>\n"
            f"👥 إجمالي الإحالات: <code>{total}</code>\n"
            f"✅ هاتف حقيقي: <code>{verified}</code>\n"
            f"⚠️ رقم مكتوب: <code>{manual}</code>\n"
            f"💰 إجمالي الأرباح: <code>{total_bonus:.2f}</code> {bonus_currency}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

        inline_btns = [
            [{'text': '⚙️ تعديل ربح الإحالة', 'callback_data': 'ref_earnings_settings'}],
        ]

        # عرض آخر 10 إحالات
        if referrals:
            text += self.tr('a0003_آخر_الإحالات', 'ar')
            for r in referrals[-10:]:
                phone_icon = '✅' if r.get('phone_verified') == 'yes' else '⚠️'
                text += f"{phone_icon} <code>{r.get('referred_name', '')}</code> — {r.get('referred_phone', '')}\n"
                text += f"   💰 {r.get('bonus_amount', '')} {r.get('currency', '')} | 📊 {r.get('status', '')}\n"
                text += f"   📅 {r.get('created_at', '')}\n\n"
                # زر تحرير الرصيد لو الحالة earned
                if r.get('status') == 'earned':
                    inline_btns.append([{'text': f"🔓 تحرير رصيد {r.get('referred_name', '')}",
                                         'callback_data': f"ref_unfreeze_{r.get('referred_id', '')}"}])

        inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'app_back_admin'}])
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_referral_links_admin(self, message):
        """لوحة إدارة روابط الإحالة للأدمن"""
        links = []
        try:
            with open('referral_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                links = list(reader)
        except:
            pass

        text = f"🎁 <b>إدارة روابط الإحالة</b>\n\n📊 الإجمالي: <code>{len(links)}</code>\n"
        inline_btns = []

        if links:
            text += "\n━━━━━━━━━━━━━━━━━━\n"
            for link in links:
                status = '✅' if link.get('is_active') == 'yes' else '⏸️'
                text += f"\n{status} <b>{link.get('name', '')}</b>\n"
                text += f"  🔗 <code>{link.get('url', '')}</code>\n"
                inline_btns.append([{
                    'text': f"{status} {link.get('name', '')}",
                    'callback_data': f"ref_admin_toggle_{link['id']}"
                }, {
                    'text': '🗑️',
                    'callback_data': f"ref_admin_delete_{link['id']}"
                }])

        inline_btns.append([{'text': '➕ إضافة رابط', 'callback_data': 'ref_admin_add'}])
        inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'app_back_admin'}])

        if not links:
            text += self.tr('a0004_لا_توجد', 'ar')

        self.send_inline_message(message['chat']['id'], text, inline_btns)

    # ==================== 📱 التطبيقات — Panel Methods ====================

    def show_apps_panel(self, message):
        """عرض التطبيقات كشبكة أيقونات — مثل هاتف"""
        user = self.find_user(message['from']['id'])
        lang = user.get('language', 'ar') if user else 'ar'
        apps = self.get_app_links()

        if not apps:
            self.send_message(message['chat']['id'],
                self.tr('apps_empty', lang),
                self.main_keyboard(lang, message['from']['id']))
            return

        # بناء شبكة أزرار inline — 3 لكل صف (مثل شبكة هاتف)
        # كل زر = أيقونة التطبيق + اسمه
        inline_btns = []
        for i in range(0, len(apps), 3):
            row = []
            for j in range(3):
                if i + j < len(apps):
                    app = apps[i + j]
                    name = app.get('name', '')[:12]  # اسم قصير
                    # استخدام أيقونة من المكتبة أو افتراضية
                    icon = app.get('icon_url', '') or app.get('icon_file_id', '')
                    # لو عنده icon_file_id نرسل صورة لاحقاً، لكن في الأزرار نستخدم إيموجي
                    app_icon = '📱'  # افتراضي
                    # محاولة استخراج إيموجي من اسم التطبيق
                    guessed = self.normalize_icon(name, None)
                    if guessed and guessed != '🏷️':
                        app_icon = guessed
                    row.append({'text': f"{app_icon}\n{name}", 'callback_data': f"app_view_{app['id']}"})
            if row:
                inline_btns.append(row)

        inline_btns.append([{'text': self.tr('a0142_العودة', lang), 'callback_data': 'apps_back_main'}])

        # إرسال نص بسيط + شبكة الأزرار
        self.send_inline_message(message['chat']['id'],
            f"📱 <b>التطبيقات</b>\n\n"
            f"👇 اختر تطبيقاً:",
            inline_btns)

    def show_app_detail(self, chat_id, app_id, user_id=None):
        """عرض تفاصيل تطبيق — 4 أزرار فقط"""
        app = self.get_app_by_id(app_id)
        if not app:
            user_obj = self.find_user(user_id) if user_id else None
            lang = user_obj.get('language', 'ar') if user_obj else 'ar'
            self.send_message(chat_id, self.tr('a0006_التطبيق_غير', lang))
            return

        user_obj = self.find_user(user_id) if user_id else None
        lang = user_obj.get('language', 'ar') if user_obj else 'ar'

        name = app.get('name', '')
        desc = app.get('description', '')
        android_url = app.get('android_url', '')
        android_file_id = app.get('android_file_id', '')
        ios_url = app.get('ios_url', '')
        ios_file_id = app.get('ios_file_id', '')
        promo_code = app.get('promo_code', '').strip()
        referral_link = app.get('referral_link', '').strip()

        # نص بسيط — اسم التطبيق فقط
        text = f"📱 <b>{name}</b>\n"
        if desc:
            text += f"📝 {desc}\n"

        # بناء 4 أزرار
        row1 = []
        row2 = []

        # 1) أندرويد
        if android_url:
            row1.append({'text': '🤖 أندرويد', 'url': android_url})
        elif android_file_id:
            row1.append({'text': '🤖 أندرويد', 'callback_data': f"app_dl_android_{app_id}"})

        # 2) آيفون
        if ios_url:
            row1.append({'text': '🍎 آيفون', 'url': ios_url})
        elif ios_file_id:
            row1.append({'text': '🍎 آيفون', 'callback_data': f"app_dl_ios_{app_id}"})

        # 3) متصفح (رابط الموقع)
        if referral_link:
            row1.append({'text': '🌐 متصفح', 'url': referral_link})

        # 4) البرومو كود — زر يفتح صفحة نسخ
        if promo_code:
            row2.append({'text': f'🎟️ البرومو كود', 'callback_data': f"app_promo_{app_id}"})

        inline_btns = []
        if row1:
            inline_btns.append(row1)
        if row2:
            inline_btns.append(row2)
        inline_btns.append([{'text': self.tr('a0142_العودة', lang), 'callback_data': 'app_list_back'}])

        # إرسال أيقونة التطبيق كصورة إن وجدت
        icon_file_id = app.get('icon_file_id', '')
        icon_url = app.get('icon_url', '')
        if icon_file_id or icon_url:
            try:
                photo = icon_file_id if icon_file_id else icon_url
                self.api_call('sendPhoto', {
                    'chat_id': chat_id,
                    'photo': photo,
                    'caption': text,
                    'parse_mode': 'HTML',
                    'reply_markup': json.dumps({'inline_keyboard': inline_btns})
                })
                return
            except:
                pass

        # بدون صورة — نص فقط
        self.send_inline_message(chat_id, text, inline_btns)

    # ==================== Admin: Apps Management ====================

    def show_apps_admin_panel(self, message):
        """لوحة إدارة التطبيقات"""
        apps = self.get_all_app_links()

        text = f"📱 <b>إدارة التطبيقات</b>\n\n📊 الإجمالي: <code>{len(apps)}</code>\n"
        inline_btns = []

        if apps:
            for app in apps:
                status = '✅' if app.get('is_active') == 'yes' else '⏸️'
                android = '🤖' if (app.get('android_url') or app.get('android_file_id')) else '➖'
                ios = '🍎' if (app.get('ios_url') or app.get('ios_file_id')) else '➖'
                icon = '🖼️' if (app.get('icon_file_id') or app.get('icon_url')) else '➖'
                text += (
                    f"\n{status} <b>{app['name']}</b>\n"
                    f"  🆔 <code>{app['id']}</code> 👈 اضغط للنسخ\n"
                    f"  {icon} أيقونة | {android} أندرويد | {ios} آيفون\n"
                )
                inline_btns.append([{
                    'text': f"✏️ تعديل: {app['name']}",
                    'callback_data': f"app_edit_{app['id']}"
                }, {
                    'text': f"{'⏸️' if app.get('is_active') == 'yes' else '▶️'}",
                    'callback_data': f"app_toggle_{app['id']}"
                }, {
                    'text': f"🗑️",
                    'callback_data': f"app_delete_{app['id']}"
                }])

        inline_btns.append([{'text': '➕ إضافة تطبيق جديد', 'callback_data': 'app_add_new'}])
        inline_btns.append([{'text': '🔙 العودة للوحة الأدمن', 'callback_data': 'app_back_admin'}])

        if not apps:
            text += self.tr('a0008_لا_توجد', 'ar')

        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def start_app_wizard(self, message):
        """بدء معالج إضافة تطبيق"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']

        if not hasattr(self, 'temp_app_data'):
            self.temp_app_data = {}
        self.temp_app_data[user_id] = {'step': 'app_name'}

        self.send_message(chat_id,
            "➕ <b>إضافة تطبيق</b>\n\n"
            "📝 الخطوة 1: اكتب <b>اسم التطبيق</b>:",
            {'keyboard': [[{'text': '❌ إلغاء'}]], 'resize_keyboard': True, 'one_time_keyboard': True})
        self.user_states[user_id] = 'app_wizard_name'

    def handle_app_field_edit(self, message, state):
        """تعديل حقل واحد في التطبيق — مستقل عن باقي الحقول"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        field = state.get('field', '')
        app_id = state.get('app_id', '')

        if text in [self.tr('a0009_إلغاء', 'ar'), self.tr('a0010_إلغاء', 'ar'), self.tr('a0011_الغاء', 'ar'), '🔙']:
            del self.user_states[user_id]
            fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
            self.show_apps_admin_panel(fake_msg)
            return

        app = self.get_app_by_id(app_id)
        if not app:
            self.send_message(chat_id, self.tr('a0006_التطبيق_غير', 'ar'))
            del self.user_states[user_id]
            return

        # تحضير التحديث
        updates = {}

        if field == 'name':
            if len(text) < 2:
                self.send_message(chat_id, self.tr('a0012_الاسم_قصير', 'ar'))
                return
            updates['name'] = text

        elif field == 'icon':
            if 'photo' in message:
                photo = message['photo'][-1]
                updates['icon_file_id'] = photo['file_id']
                updates['icon_url'] = ''
            elif text.lower() in [self.tr('a0013_حذف', 'ar'), 'delete', self.tr('a0014_مسح', 'ar')]:
                updates['icon_file_id'] = ''
                updates['icon_url'] = ''
            elif text.startswith('http'):
                updates['icon_url'] = text
                updates['icon_file_id'] = ''
            else:
                self.send_message(chat_id, self.tr('a0015_أرسل_صورة', 'ar'))
                return

        elif field == 'android':
            if 'document' in message:
                updates['android_file_id'] = message['document']['file_id']
                updates['android_url'] = ''
            elif text.lower() in [self.tr('a0013_حذف', 'ar'), 'delete', self.tr('a0014_مسح', 'ar')]:
                updates['android_file_id'] = ''
                updates['android_url'] = ''
            elif text.startswith('http'):
                updates['android_url'] = text
                updates['android_file_id'] = ''
            else:
                self.send_message(chat_id, self.tr('a0016_أرسل_ملف', 'ar'))
                return

        elif field == 'ios':
            if text.lower() in [self.tr('a0013_حذف', 'ar'), 'delete', self.tr('a0014_مسح', 'ar')]:
                updates['ios_url'] = ''
            elif text.startswith('http'):
                updates['ios_url'] = text
            else:
                self.send_message(chat_id, self.tr('a0017_اكتب_رابط', 'ar'))
                return

        elif field == 'promo_code':
            if text.lower() in [self.tr('a0013_حذف', 'ar'), 'delete', self.tr('a0014_مسح', 'ar')]:
                updates['promo_code'] = ''
            else:
                updates['promo_code'] = text

        elif field == 'referral_link':
            if text.lower() in [self.tr('a0013_حذف', 'ar'), 'delete', self.tr('a0014_مسح', 'ar')]:
                updates['referral_link'] = ''
            elif text.startswith('http'):
                updates['referral_link'] = text
            else:
                self.send_message(chat_id, self.tr('a0017_اكتب_رابط', 'ar'))
                return

        elif field == 'description':
            if text.lower() in [self.tr('a0013_حذف', 'ar'), 'delete', self.tr('a0014_مسح', 'ar')]:
                updates['description'] = ''
            else:
                updates['description'] = text

        # حفظ التحديث
        if updates:
            self._update_app_link(app_id, updates)
            field_labels = {'name': '📝 الاسم', 'icon': '🖼️ الأيقونة', 'android': '🤖 أندرويد',
                          'ios': '🍎 آيفون', 'promo_code': '🎁 البرومو كود',
                          'referral_link': '🔗 رابط الإحالة', 'description': '📋 الوصف'}
            label = field_labels.get(field, field)
            self.send_message(chat_id, self.tr('a0018_تم_تحديث', 'ar', label=label))
        else:
            self.send_message(chat_id, self.tr('a0019_لم_يتم', 'ar'))

        del self.user_states[user_id]
        # العودة لقائمة تعديل التطبيق
        fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': f'app_edit_{app_id}'}
        # إعادة عرض قائمة التعديل
        app = self.get_app_by_id(app_id)
        if app:
            dl_android = '📦 APK' if app.get('android_file_id') else (self.tr('a0020_رابط', 'ar') if app.get('android_url') else '➖')
            dl_ios = self.tr('a0020_رابط', 'ar') if app.get('ios_url') else '➖'
            icon = '🖼️' if (app.get('icon_file_id') or app.get('icon_url')) else '➖'
            promo = '🎁' if app.get('promo_code') else '➖'
            ref = '🔗' if app.get('referral_link') else '➖'
            status = '✅' if app.get('is_active') == 'yes' else '⏸️'
            text = f"✏️ <b>تعديل التطبيق</b>\n\n📱 الاسم: <b>{app.get('name', '')}</b>\n🆔 <code>{app_id}</code>\n\nاختر الحقل:"
            inline_btns = [
                [{'text': f'📝 الاسم: {app.get("name", "")}', 'callback_data': f'app_edit_name_{app_id}'}],
                [{'text': f'{icon} الأيقونة', 'callback_data': f'app_edit_icon_{app_id}'}],
                [{'text': f'🤖 أندرويد: {dl_android}', 'callback_data': f'app_edit_android_{app_id}'}],
                [{'text': f'🍎 آيفون: {dl_ios}', 'callback_data': f'app_edit_ios_{app_id}'}],
                [{'text': f'{promo} برومو كود', 'callback_data': f'app_edit_promo_{app_id}'}],
                [{'text': f'{ref} رابط إحالة', 'callback_data': f'app_edit_reflink_{app_id}'}],
                [{'text': f'📋 الوصف: {app.get("description", "") or "بدون"}', 'callback_data': f'app_edit_desc_{app_id}'}],
                [{'text': f'{status} التفعيل', 'callback_data': f'app_toggle_{app_id}'},
                 {'text': '🗑️ حذف', 'callback_data': f'app_delete_{app_id}'}],
                [{'text': '🔙 رجوع', 'callback_data': 'app_refresh'}]
            ]
            self.send_inline_message(chat_id, text, inline_btns)

    def handle_app_wizard(self, message):
        """معالجة معالج إضافة تطبيق — يدعم رفع APK وصور"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()

        if text in [self.tr('a0009_إلغاء', 'ar'), self.tr('a0021_لوحة_الأدمن', 'ar'), self.tr('a0010_إلغاء', 'ar'), self.tr('a0011_الغاء', 'ar')]:
            if user_id in self.user_states:
                del self.user_states[user_id]
            if hasattr(self, 'temp_app_data') and user_id in self.temp_app_data:
                del self.temp_app_data[user_id]
            self.show_apps_admin_panel(message)
            return

        data = getattr(self, 'temp_app_data', {}).get(user_id, {})
        step = data.get('step', '')

        if step == 'app_name':
            if len(text) < 2:
                self.send_message(chat_id, self.tr('a0022_الاسم_قصير', 'ar'))
                return
            data['name'] = text
            data['step'] = 'app_icon'
            self.temp_app_data[user_id] = data
            self.send_message(chat_id,
                f"✅ الاسم: <code>{text}</code>\n\n"
                f"🖼️ الخطوة 2: أرسل <b>أيقونة التطبيق</b>:\n\n"
                f"• ارفع صورة (PNG/JPG) — ستُحفظ كأيقونة\n"
                f"• أو اكتب رابط صورة\n"
                f"• أو اكتب 'تخطي' بدون أيقونة")

        elif step == 'app_icon':
            if 'photo' in message:
                photo = message['photo'][-1]
                data['icon_file_id'] = photo['file_id']
                data['icon_url'] = ''
                self.send_message(chat_id, self.tr('a0023_تم_حفظ', 'ar'))
            elif text.lower() in [self.tr('a0024_تخطي', 'ar'), 'skip', self.tr('a0025_بدون', 'ar')]:
                data['icon_file_id'] = ''
                data['icon_url'] = ''
                self.send_message(chat_id, self.tr('a0026_بدون_أيقونة', 'ar'))
            elif text.startswith('http'):
                data['icon_url'] = text
                data['icon_file_id'] = ''
                self.send_message(chat_id, self.tr('a0027_تم_حفظ', 'ar'))
            else:
                self.send_message(chat_id, self.tr('a0028_أرسل_صورة', 'ar'))
                return

            data['step'] = 'app_android'
            self.temp_app_data[user_id] = data
            self.send_message(chat_id,
                f"\n🤖 الخطوة 3: أرسل <b>رابط تحميل أندرويد</b> أو <b>ملف APK</b>:\n\n"
                f"• ارفع ملف .apk\n"
                f"• أو اكتب رابط تحميل (http/https)\n"
                f"• أو اكتب 'تخطي'")

        elif step == 'app_android':
            if 'document' in message:
                doc = message['document']
                file_name = doc.get('file_name', '')
                data['android_file_id'] = doc['file_id']
                data['android_url'] = ''
                self.send_message(chat_id, self.tr('a0029_تم_حفظ', 'ar', file_name=file_name))
            elif text.startswith('http'):
                data['android_url'] = text
                data['android_file_id'] = ''
                self.send_message(chat_id, self.tr('a0030_تم_حفظ', 'ar'))
            elif text.lower() in [self.tr('a0024_تخطي', 'ar'), 'skip', self.tr('a0025_بدون', 'ar')]:
                data['android_url'] = ''
                data['android_file_id'] = ''
                self.send_message(chat_id, self.tr('a0031_بدون_رابط', 'ar'))
            else:
                self.send_message(chat_id, self.tr('a0032_أرسل_ملف', 'ar'))
                return

            data['step'] = 'app_ios'
            self.temp_app_data[user_id] = data
            self.send_message(chat_id,
                f"\n🍎 الخطوة 4: أرسل <b>رابط تحميل آيفون</b> (App Store):\n\n"
                f"• اكتب رابط App Store (http/https)\n"
                f"• أو اكتب 'تخطي'")

        elif step == 'app_ios':
            if text.startswith('http'):
                data['ios_url'] = text
                data['ios_file_id'] = ''
                self.send_message(chat_id, self.tr('a0033_تم_حفظ', 'ar'))
            elif text.lower() in [self.tr('a0024_تخطي', 'ar'), 'skip', self.tr('a0025_بدون', 'ar')]:
                data['ios_url'] = ''
                data['ios_file_id'] = ''
                self.send_message(chat_id, self.tr('a0034_بدون_رابط', 'ar'))
            else:
                self.send_message(chat_id, self.tr('a0035_اكتب_رابط', 'ar'))
                return

            data['step'] = 'app_promo'
            self.temp_app_data[user_id] = data
            self.send_message(chat_id,
                f"\n🎁 الخطوة 5: اكتب <b>برومو كود</b> للتطبيق:\n\n"
                f"• يظهر للعميل بالأزرق قابل للنسخ\n"
                f"• أو اكتب 'تخطي'")

        elif step == 'app_promo':
            if text.lower() in [self.tr('a0024_تخطي', 'ar'), 'skip', self.tr('a0025_بدون', 'ar')]:
                data['promo_code'] = ''
            else:
                data['promo_code'] = text.strip()
            data['step'] = 'app_referral'
            self.temp_app_data[user_id] = data
            self.send_message(chat_id,
                f"\n🔗 الخطوة 6: اكتب <b>رابط الإحالة</b> للتطبيق:\n\n"
                f"• يظهر للعميل كزر يفتح الرابط\n"
                f"• أو اكتب 'تخطي'")

        elif step == 'app_referral':
            if text.lower() in [self.tr('a0024_تخطي', 'ar'), 'skip', self.tr('a0025_بدون', 'ar')]:
                data['referral_link'] = ''
            elif text.startswith('http'):
                data['referral_link'] = text.strip()
            else:
                self.send_message(chat_id, self.tr('a0036_اكتب_رابط', 'ar'))
                return

            data['step'] = 'app_desc'
            self.temp_app_data[user_id] = data
            self.send_message(chat_id,
                self.tr('a0037_الخطوة_الأخيرة', 'ar'))

        elif step == 'app_desc':
            if text.lower() in [self.tr('a0024_تخطي', 'ar'), 'skip', self.tr('a0025_بدون', 'ar')]:
                data['description'] = ''
            else:
                data['description'] = text

            edit_id = data.get('edit_id', '')
            if edit_id:
                self._update_app_link(edit_id, data)
                app_id = edit_id
            else:
                app_id = self.add_app_link(
                    data['name'],
                    data.get('icon_url', ''),
                    data.get('icon_file_id', ''),
                    data.get('android_url', ''),
                    data.get('android_file_id', ''),
                    data.get('ios_url', ''),
                    data.get('ios_file_id', ''),
                    data.get('promo_code', ''),
                    data.get('referral_link', ''),
                    data.get('description', '')
                )

            if app_id:
                android_info = self.tr('a0038_مرفوع', 'ar') if data.get('android_file_id') else (self.tr('a0039_رابط_أندرويد', 'ar') if data.get('android_url') else self.tr('a0040_بدون_أندرويد', 'ar'))
                ios_info = self.tr('a0041_رابط_آيفون', 'ar') if data.get('ios_url') else self.tr('a0042_بدون_آيفون', 'ar')
                promo_info = f"🎁 كود: <code>{data.get('promo_code', '')}</code>" if data.get('promo_code') else self.tr('a0043_بدون_كود', 'ar')
                ref_info = self.tr('a0044_رابط_إحالة', 'ar') if data.get('referral_link') else self.tr('a0045_بدون_رابط', 'ar')
                icon_info = self.tr('a0046_أيقونة_مرفوعة', 'ar') if data.get('icon_file_id') else (self.tr('a0047_رابط_أيقونة', 'ar') if data.get('icon_url') else self.tr('a0048_بدون_أيقونة', 'ar'))
                summary = (
                    f"✅ <b>تم حفظ التطبيق!</b>\n\n"
                    f"📱 الاسم: <b>{data['name']}</b>\n"
                    f"🆔 <code>{app_id}</code> 👈 اضغط للنسخ\n"
                    f"{icon_info}\n"
                    f"{android_info}\n"
                    f"{ios_info}\n"
                    f"{promo_info}\n"
                    f"{ref_info}\n"
                )
                if data.get('description'):
                    summary += f"📝 {data['description']}\n"

                inline_btns = [
                    [{'text': '📋 عرض كل التطبيقات', 'callback_data': 'app_refresh'}],
                    [{'text': '➕ إضافة تطبيق آخر', 'callback_data': 'app_add_new'}],
                    [{'text': '🔙 لوحة الأدمن', 'callback_data': 'app_back_admin'}]
                ]
                self.send_inline_message(chat_id, summary, inline_btns)
            else:
                self.send_message(chat_id, self.tr('a0049_فشل_في', 'ar'), self.admin_keyboard())

            if user_id in self.user_states:
                del self.user_states[user_id]
            if hasattr(self, 'temp_app_data') and user_id in self.temp_app_data:
                del self.temp_app_data[user_id]

    # ==================== End 📱 التطبيقات ====================

    # ==================== 💎 تعويض 100% — Panel Methods ====================

    def show_svrp_panel(self, message):
        """عرض لوحة 💎 تعويض 100% — تصميم جديد بأزرار inline + شرح"""
        user = self.find_user(message['from']['id'])
        if not user or not self.svrp:
            lang = 'ar'
            self.send_message(message['chat']['id'],
                self.tr('svrp_not_available', lang),
                self.main_keyboard(lang, message['from']['id']))
            return

        user_id = message['from']['id']
        lang = user.get('language', 'ar')
        wallet = self.svrp.get_wallet(user_id)

        balance = float(wallet.get('balance', 0) or 0)
        pending = float(wallet.get('pending_balance', 0) or 0)
        total_earned = float(wallet.get('total_earned', 0) or 0)
        total_used = float(wallet.get('total_used', 0) or 0)

        # الرصيد المجمد = كل الرصيد حتى يُفك
        frozen = balance
        available = 0  # سيُحدّث في المراحل القادمة بناءً على الإرسال

        # جلب نص الشرح من الإعدادات (قابل للتعديل من لوحة الأدمن)
        intro_ar = self.get_setting('svrp_intro_ar') or (
            "📌 <b>كيف يعمل النظام؟</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ اضغط <b>💰 إيداع</b> ← أودع في حسابك بالشركة\n"
            "2️⃣ بعد الإيداع، اختر <b>🔄 استرداد</b> ← أرسل لقطة شاشة برصيدك\n"
            "3️⃣ يراجع الأدمن ← يُضاف <b>100% من المبلغ</b> لمحفظتك (<b>مجمد 🧊</b>)\n"
            "4️⃣ لفك التجميد: أرسل الرصيد لـ <b>4 أصدقاء على الأقل</b>\n"
            "   • الرصيد يُقسم لـ 4 أقسام (25% لكل صديق)\n"
            "   • عند إرسال مبلغ لصديق ← يُفك تجميد نفس المبلغ\n"
            "   • مثال: مجمد=1000، أرسل 250 لصديق ← يُفك 250\n"
            "5️⃣ الرصيد المتاح 🟢 ← اطلب إيداعه لحسابك"
        )
        intro_en = self.get_setting('svrp_intro_en') or (
            "📌 <b>How it works:</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ Press <b>💰 Deposit</b> ← deposit to your company account\n"
            "2️⃣ After deposit, choose <b>🔄 Recovery</b> ← send screenshot\n"
            "3️⃣ Admin reviews ← <b>100% of amount</b> added to wallet (<b>frozen 🧊</b>)\n"
            "4️⃣ To unfreeze: send credits to <b>at least 4 friends</b>\n"
            "   • Balance split into 4 parts (25% per friend)\n"
            "   • When you send X to a friend ← X gets unfrozen\n"
            "5️⃣ Available balance 🟢 ← request deposit to your account"
        )

        if lang == 'ar':
            panel_text = self.ui_card_pro('تعويض 100%', '💎', items=[
                {'label': 'الرصيد المجمد', 'value': f"{frozen:.2f}", 'icon': '🧊', 'highlight': True},
                {'label': 'الرصيد المتاح', 'value': f"{available:.2f}", 'icon': '🟢', 'highlight': True},
                {'label': 'بانتظار الأصدقاء', 'value': f"{pending:.2f}", 'icon': '⏳', 'highlight': True},
                {'label': 'إجمالي المكتسب', 'value': f"{total_earned:.2f}", 'icon': '📈'},
                {'label': 'إجمالي المستخدم', 'value': f"{total_used:.2f}", 'icon': '📉'},
            ])
            panel_text += self.ui_card_section('كيف يعمل النظام؟', '📌', color='blue')
            panel_text += intro_ar + "\n\n"
            panel_text += "👇 <b>اختر ما تريد:</b>"
        else:
            panel_text = self.ui_card_pro('Compensation 100%', '💎', items=[
                {'label': 'Frozen', 'value': f"{frozen:.2f}", 'icon': '🧊', 'highlight': True},
                {'label': 'Available', 'value': f"{available:.2f}", 'icon': '🟢', 'highlight': True},
                {'label': 'Pending friends', 'value': f"{pending:.2f}", 'icon': '⏳', 'highlight': True},
                {'label': 'Total earned', 'value': f"{total_earned:.2f}", 'icon': '📈'},
                {'label': 'Total used', 'value': f"{total_used:.2f}", 'icon': '📉'},
            ])
            panel_text += self.ui_card_section('How it works', '📌', color='blue')
            panel_text += intro_en + "\n\n"
            panel_text += "👇 <b>Select an option:</b>"

        # فحص التسجيل: هل سجّل العميل حسابات في الشركات؟
        user_accounts = self.svrp.get_user_company_accounts(user_id) if self.svrp else []
        is_registered = len(user_accounts) > 0

        # أزرار inline داخل الدردشة
        if not is_registered:
            # العميل غير مسجل — يظهر زر تسجيل فقط
            inline_btns = [
                [{'text': '📝 انقر لتسجيل حساب', 'callback_data': 'svrp_companies'}],
                [{'text': '🏠 القائمة الرئيسية', 'callback_data': 'svrp_main_menu'}]
            ]
            panel_text += (
                "\n\n⚠️ <b>لم تسجل حسابك بعد!</b>\n"
                "📝 اضغط الزر بالأسفل لتسجيل حسابك في الشركات المتاحة."
            )
        else:
            # العميل مسجل — تظهر كل الأزرار
            inline_btns = [
                [{'text': '💰 إيداع', 'callback_data': 'svrp_deposit'},
                 {'text': '💸 سحب', 'callback_data': 'svrp_withdraw'}],
                [{'text': '🔄 استرداد', 'callback_data': 'svrp_recovery_request'},
                 {'text': '📤 إرسال رصيد', 'callback_data': 'svrp_send_credits'}],
                [{'text': '💎 محفظتي', 'callback_data': 'svrp_wallet'},
                 {'text': '👥 دعوة صديق', 'callback_data': 'svrp_invite'}],
                [{'text': '🏢 تسجيل / تعديل الحسابات', 'callback_data': 'svrp_companies'}],
                [{'text': '🏠 القائمة الرئيسية', 'callback_data': 'svrp_main_menu'}]
            ]
        self.send_inline_message(message['chat']['id'], panel_text, inline_btns)

    def show_svrp_wallet(self, message):
        """عرض محفظة 💎 تعويض 100%"""
        user_id = message['from']['id']
        user = self.find_user(user_id)
        if not user or not self.svrp:
            return

        lang = user.get('language', 'ar')
        wallet = self.svrp.get_wallet(user_id)
        credits = self.svrp.get_user_credits_summary(user_id)
        wager_req = int(wallet.get('wagering_required', 3) or 3)
        wager_done = int(wallet.get('wagering_completed', 0) or 0)
        is_frozen = wager_done < wager_req

        bal = float(wallet.get('balance', 0) or 0)
        pend = float(wallet.get('pending_balance', 0) or 0)
        earned = float(wallet.get('total_earned', 0) or 0)
        used = float(wallet.get('total_used', 0) or 0)

        if lang == 'ar':
            title = self.tr('a0050_محفظتي', lang)
            frozen_lbl = self.tr('a0051_مجمد', lang) if is_frozen else self.tr('a0052_متاح', lang)
            pending_lbl = self.tr('a0053_بانتظار_الأصدقاء', lang)
            earned_lbl = self.tr('a0054_إجمالي_المكتسب', lang)
            used_lbl = self.tr('a0055_إجمالي_المستخدم', lang)
            keep_lbl = self.tr('a0056_أرصدة_الاحتفاظ', lang)
            shared_lbl = self.tr('a0057_أرصدة_المشاركة', lang)
            active_lbl = self.tr('a0058_نشط', lang)
            pending_status_lbl = self.tr('a0059_معلق', lang)
            used_lbl2 = self.tr('a0060_مستخدم', lang)
            expired_lbl = self.tr('a0061_منتهي', lang)
            hint = self.tr('a0062_يمكنك_إنشاء', lang)
        else:
            title = "💎 <b>My Wallet</b>"
            frozen_lbl = "🧊 Frozen" if is_frozen else "🟢 Available"
            pending_lbl = "⏳ Pending friends"
            earned_lbl = "📈 Total earned"
            used_lbl = "📉 Total used"
            keep_lbl = "📥 Keep credits"
            shared_lbl = "📤 Shared credits"
            active_lbl = "Active"
            pending_status_lbl = "Pending"
            used_lbl2 = "Used"
            expired_lbl = "Expired"
            hint = "💡 Create a promo code or redeem a friend's code"

        text = (
            f"{title}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{frozen_lbl}: <b><code>{bal:.2f}</code></b>\n"
            f"{pending_lbl}: <b><code>{pend:.2f}</code></b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{earned_lbl}: <b>{earned:.2f}</b>\n"
            f"{used_lbl}: <b>{used:.2f}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>{keep_lbl}</b>\n"
            f"  🟢 {active_lbl}: <b>{credits['keep']['active']}</b> | "
            f"🟡 {pending_status_lbl}: <b>{credits['keep']['pending']}</b>\n"
            f"  🔴 {used_lbl2}: <b>{credits['keep']['used']}</b> | "
            f"⚫ {expired_lbl}: <b>{credits['keep']['expired']}</b>\n\n"
            f"<b>{shared_lbl}</b>\n"
            f"  🟢 {active_lbl}: <b>{credits['shared']['active']}</b> | "
            f"🟡 {pending_status_lbl}: <b>{credits['shared']['pending']}</b>\n"
            f"  🔴 {used_lbl2}: <b>{credits['shared']['used']}</b> | "
            f"⚫ {expired_lbl}: <b>{credits['shared']['expired']}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{hint}"
        )
        self.send_message(message['chat']['id'], text, self.main_keyboard(lang, user_id))

    def show_svrp_tasks(self, message):
        """عرض مهام 💎 تعويض 100%"""
        user_id = message['from']['id']
        user = self.find_user(user_id)
        if not user or not self.svrp:
            return

        lang = user.get('language', 'ar')
        self.svrp.create_daily_tasks(user_id)
        tasks = self.svrp.get_user_tasks(user_id)

        if not tasks:
            self.send_message(message['chat']['id'],
                self.tr('svrp_no_tasks', lang),
                self.main_keyboard(lang, user_id))
            return

        task_labels = {
            'deposit_count': self.tr('svrp_task_deposit', lang),
            'deposit_amount': self.tr('svrp_task_deposit_amount', lang),
            'withdraw_count': self.tr('svrp_task_withdraw', lang),
            'referral_count': self.tr('svrp_task_referral', lang)
        }

        if lang == 'ar':
            title = self.tr('a0063_مهام_اليوم', lang)
            reward_lbl = self.tr('a0064_مكافأة', lang)
            claim_hint = self.tr('a0065_لديك_مهام', lang)
            pending_hint = self.tr('a0066_أكمل_معاملاتك', lang)
        else:
            title = "📋 <b>Today's Tasks</b>"
            reward_lbl = "reward"
            claim_hint = "🎉 You have completed tasks!\nType: <code>claim [task_id]</code>"
            pending_hint = "💡 Complete your transactions to finish tasks!"

        text = f"{title}\n\n━━━━━━━━━━━━━━━━━━\n\n"
        has_claimable = False
        for t in tasks:
            label = task_labels.get(t['task_type'], t['task_type'])
            progress = float(t.get('current_progress', 0) or 0)
            target = float(t.get('target_value', 1) or 1)
            status = t.get('status', 'active')
            reward = t.get('reward_amount', '0')

            pct = min(100, int(progress / target * 100)) if target > 0 else 0
            bar = '▰' * (pct // 20) + '▱' * (5 - pct // 20)
            status_icon = {'active': '⏳', 'completed': '✅', 'claimed': '🎉'}.get(status, '⏳')

            text += f"{status_icon} <b>{label}</b>\n"
            text += f"   {bar} {progress:.0f}/{target:.0f}\n"
            text += f"   🎁 {reward_lbl}: <b>{reward}</b>\n\n"
            if status == 'completed':
                has_claimable = True

        text += "━━━━━━━━━━━━━━━━━━\n"
        text += claim_hint if has_claimable else pending_hint

        self.send_message(message['chat']['id'], text, self.main_keyboard(lang, user_id))

    def show_svrp_promo_codes(self, message):
        """عرض أكواد ترويجية للمستخدم"""
        user_id = message['from']['id']
        user = self.find_user(user_id)
        if not user or not self.svrp:
            return

        lang = user.get('language', 'ar')
        codes = self.svrp.get_user_promo_codes(user_id)
        wallet = self.svrp.get_wallet(user_id)
        balance = float(wallet.get('balance', 0) or 0)
        wager_done = int(wallet.get('wagering_completed', 0) or 0)
        wager_req = int(wallet.get('wagering_required', 3) or 3)
        is_frozen = wager_done < wager_req

        if lang == 'ar':
            title = self.tr('a0067_أكوادي_الترويجية', lang)
            balance_lbl = self.tr('a0068_رصيدك', lang)
            empty = self.tr('a0069_لا_توجد', lang)
            create_hint = self.tr('a0070_لإنشاء_كود', lang)
            create_cmd = self.tr('a0071_انشاء_كود', lang)
            redeem_hint = self.tr('a0072_لاسترداد_كود', lang)
            redeem_cmd = self.tr('a0073_استرداد_كود', lang)
            frozen_warn = self.tr('a0074_رصيدك_مجمد', lang) if is_frozen else ""
        else:
            title = "🎟️ <b>My Promo Codes</b>"
            balance_lbl = "Your balance"
            empty = "📭 No codes yet"
            create_hint = "➕ To create a new code:"
            create_cmd = self.tr('a0071_انشاء_كود', lang)
            redeem_hint = "📥 To redeem a code:"
            redeem_cmd = self.tr('a0073_استرداد_كود', lang)
            frozen_warn = "⚠️ Your balance is frozen until you complete 3 transactions" if is_frozen else ""

        text = f"{title}\n\n━━━━━━━━━━━━━━━━━━\n"
        text += f"💰 {balance_lbl}: <b><code>{balance:.2f}</code></b>\n"
        if frozen_warn:
            text += f"{frozen_warn}\n"
        text += "━━━━━━━━━━━━━━━━━━\n\n"

        if codes:
            for c in codes:
                status_icon = {'active': '✅', 'fully_used': '🔴', 'expired': '⏰'}.get(c.get('status', 'active'), '✅')
                used = int(c.get('used_count', 0) or 0)
                max_u = int(c.get('max_uses', 10) or 10)
                pct = min(100, used * 100 // max_u) if max_u > 0 else 0
                bar = '▰' * (pct // 20) + '▱' * (5 - pct // 20)

                text += f"{status_icon} <code>{c['code']}</code>\n"
                text += f"   💵 <b>{c['amount']}</b> | 📊 {bar} ({used}/{max_u})\n"
                text += f"   ⏰ {c.get('expires_at', '')}\n\n"
        else:
            text += f"{empty}\n\n"

        text += "━━━━━━━━━━━━━━━━━━\n"
        text += f"{create_hint}\n{create_cmd}\n\n"
        text += f"{redeem_hint}\n{redeem_cmd}"

        self.send_message(message['chat']['id'], text, self.main_keyboard(lang, user_id))

    def show_svrp_referral_tree(self, message):
        """عرض شجرة الإحالات"""
        user_id = message['from']['id']
        user = self.find_user(user_id)
        if not user or not self.svrp:
            return

        lang = user.get('language', 'ar')
        tree = self.svrp.get_referral_tree(user_id)
        total = self.svrp.count_referrals_recursive(user_id)

        def render_tree(node, prefix="", is_last=True, depth=0):
            lines = []
            if depth == 0:
                lines.append(f"🌳 {node['user_id']}")
            else:
                connector = "└── " if is_last else "├── "
                status = node.get('status', 'unknown')
                status_icon = {'completed': '✅', 'registered': '⏳', 'unknown': '❓'}.get(status, '❓')
                lines.append(f"{prefix}{connector}{status_icon} {node['user_id']}")
            
            new_prefix = prefix + ("    " if is_last else "│   ")
            refs = node.get('referrals', [])
            for i, child in enumerate(refs):
                lines.extend(render_tree(child, new_prefix, i == len(refs) - 1, depth + 1))
            return lines

        tree_lines = render_tree(tree)
        text = (
            f"╔════════════════════╗\n"
            f"║  {self.tr('svrp_referral_tree_btn', lang)}  ║\n"
            f"╚════════════════════╝\n\n"
            + "\n".join(tree_lines)
        )
        text += f"\n\n📊 {self.tr('svrp_total_referrals', lang)}: {total}"
        text += f"\n{self.tr('svrp_share_hint', lang)}"

        self.send_message(message['chat']['id'], text, self.main_keyboard(lang, user_id))

    def show_svrp_group(self, message):
        """عرض مستوى المستخدم في 💎 تعويض 100%"""
        user_id = message['from']['id']
        user = self.find_user(user_id)
        if not user or not self.svrp:
            return

        lang = user.get('language', 'ar')
        self.svrp.update_user_group(user_id)
        group = self.svrp.get_user_group(user_id)
        group_name = group.get('group_name', 'bronze')
        group_icon = {'bronze': '🥉', 'silver': '🥈', 'gold': '🥇', 'platinum': '💎'}.get(group_name, '🥉')
        group_ar = {'bronze': 'برونزي' if lang=='ar' else 'Bronze', 'silver': 'فضي' if lang=='ar' else 'Silver', 'gold': 'ذهبي' if lang=='ar' else 'Gold', 'platinum': 'بلاتيني' if lang=='ar' else 'Platinum'}.get(group_name, self.tr('a0075_برونزي', lang))
        multiplier = {'bronze': '1.0x', 'silver': '1.2x', 'gold': '1.5x', 'platinum': '2.0x'}.get(group_name, '1.0x')
        score = float(group.get('tier_score', 0) or 0)

        text = (
            f"╔════════════════════╗\n"
            f"║  {self.tr('svrp_my_tier_btn', lang)}  ║\n"
            f"╚════════════════════╝\n\n"
            f"┌─────────────────────┐\n"
            f"│  {group_icon} {self.tr('svrp_tier_label', lang)}: {group_ar}\n"
            f"│  ⭐ {self.tr('svrp_tier_points', lang)}: {score:.0f}\n"
            f"│  🔢 {self.tr('svrp_tier_multiplier', lang)}: {multiplier}\n"
            f"└─────────────────────┘\n\n"
        )

        thresholds = [
            ('🥉 ' + (self.tr('a0075_برونزي', lang) if lang=='ar' else 'Bronze'), 'bronze', 0, '1.0x'),
            ('🥈 ' + (self.tr('a0076_فضي', lang) if lang=='ar' else 'Silver'), 'silver', 500, '1.2x'),
            ('🥇 ' + (self.tr('a0077_ذهبي', lang) if lang=='ar' else 'Gold'), 'gold', 2000, '1.5x'),
            ('💎 ' + (self.tr('a0078_بلاتيني', lang) if lang=='ar' else 'Platinum'), 'platinum', 5000, '2.0x'),
        ]
        text += f"📋 {self.tr('svrp_tier_levels', lang)}:\n"
        for label, gname, min_score, mult in thresholds:
            marker = f" {self.tr('svrp_tier_here', lang)}" if group_name == gname else ''
            bar = '▰' * 5 if group_name == gname else '▱' * 5
            text += f"  {label} {bar} {min_score}+ {self.tr('svrp_tier_points', lang)} ({mult}){marker}\n"

        text += f"\n{self.tr('svrp_tier_hint', lang)}"
        self.send_message(message['chat']['id'], text, self.main_keyboard(lang, user_id))

    def _handle_sticker_input(self, message, state):
        """حفظ استيكر أو رمز في المكتبة"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        category = state.replace('stk_waiting_', '')
        del self.user_states[user_id]

        sticker = message.get('sticker')
        emoji = message.get('text', '').strip() if message.get('text') else ''

        if sticker:
            file_id = sticker.get('file_id', '')
            set_name = sticker.get('set_name', '')
            emoji_val = sticker.get('emoji', '🎨') or '🎨'
            item_type = 'sticker'
        elif emoji and len(emoji) <= 10:
            file_id = ''
            set_name = ''
            emoji_val = emoji
            item_type = 'emoji'
        else:
            self.send_message(chat_id, self.tr('a0079_أرسل_استيكر', lang))
            return

        item_id = f"STK{str(int(datetime.now().timestamp()))[-6:]}"
        try:
            with open('sticker_library.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([item_id, item_type, file_id, emoji_val, set_name, category, user_id, datetime.now().strftime('%Y-%m-%d %H:%M')])
        except:
            pass

        self.send_message(chat_id,
            f"✅ <b>تم الحفظ في المكتبة!</b>\n\n"
            f"📂 الفئة: <b>{category}</b>\n"
            f"📦 النوع: {item_type}\n"
            f"🎨 الرمز: {emoji_val}\n"
            f"🆔 <code>{item_id}</code>")

        if sticker:
            self.send_message(chat_id, self.tr('a0080_المحفوظ', lang))

    def _handle_lottery_edit_input(self, message, state):
        """معالجة تعديل حقول جولة اليانصيب"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        del self.user_states[user_id]

        parts = state.replace('lot_edit_', '').split('_input_')
        if len(parts) != 2:
            return
        field = parts[0]
        round_id = parts[1]

        field_map = {
            'name': ('name', text),
            'price': ('ticket_price', text),
            'winners': ('winner_count', text),
            'drawtime': ('draw_time', text),
        }

        if field not in field_map:
            return

        csv_field, value = field_map[field]

        try:
            rows = []
            with open('lottery_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = list(reader)
            for row in rows:
                if row.get('id') == round_id:
                    row[csv_field] = value
                    break
            with open('lottery_rounds.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
        except Exception as e:
            self.send_message(chat_id, self.tr('a0081_خطأ', 'ar', e=e))
            return

        self.send_message(chat_id, self.tr('a0082_تم_تعديل', 'ar', field=field, value=value))
        fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
        self.show_lottery_admin(fake_msg)

    def handle_svrp_state(self, message, state):
        """معالجة حالات 💎 تعويض 100%"""
        user_id = message['from']['id']
        text = message.get('text', '').strip()
        chat_id = message['chat']['id']
        user = self.find_user(user_id)
        lang = user.get('language', 'ar') if user else 'ar'

        if text in ['🔙', self.tr('a0083_القائمة_الرئيسية', lang), self.tr('a0009_إلغاء', lang), self.tr('a0011_الغاء', lang), self.tr('a0010_إلغاء', lang)]:
            if user_id in self.user_states:
                del self.user_states[user_id]
            self.show_svrp_panel(message)
            return

        if state == 'svrp_create_promo_':
            try:
                amount = float(text)
                if amount <= 0:
                    self.send_message(chat_id, self.tr('svrp_invalid_amount_err', lang))
                    return
                code, err = self.svrp.create_promo_code(user_id, amount)
                if err:
                    self.send_message(chat_id, f"❌ {err}")
                else:
                    self.send_message(chat_id,
                        f"{self.tr('svrp_code_created_msg', lang)}\n\n"
                        f"🎟️ {self.tr('svrp_code_label', lang) if self.tr('svrp_code_label', lang) != 'svrp_code_label' else 'Code'}: `{code}`\n"
                        f"💰 {self.tr('svrp_code_amount', lang)}: {amount}\n"
                        f"📊 {self.tr('svrp_max_uses', lang)}: {self.svrp._get_config('promo_code_max_uses')}\n"
                        f"⏰ {self.tr('svrp_expires_in', lang)}: {self.svrp._get_config('promo_code_expiry_days')} {self.tr('svrp_days', lang)}")
            except ValueError:
                self.send_message(chat_id, self.tr('svrp_invalid_number_err', lang))
            if user_id in self.user_states:
                del self.user_states[user_id]

        elif state == 'svrp_redeem_promo_':
            code = text.strip()
            if code:
                success, msg = self.svrp.redeem_promo_code(user_id, code)
                icon = "✅" if success else "❌"
                self.send_message(chat_id, f"{icon} {msg}")
            if user_id in self.user_states:
                del self.user_states[user_id]

    def show_svrp_admin_panel(self, message):
        """لوحة إدارة 💎 التعويض — إدارة كاملة"""
        admin_user = self.find_user(message['from']['id'])
        admin_lang = admin_user.get('language', 'ar') if admin_user else 'ar'

        if not self.svrp:
            self.send_message(message['chat']['id'], self.tr('a0084_نظام_التعويض', lang), self.admin_keyboard())
            return

        stats = self.svrp.get_svrp_stats()
        config = {}
        for key in ['recovery_multiplier', 'max_recovery_cap', 'credit_expiry_days',
                     'wagering_requirement', 'promo_code_max_uses',
                     'promo_code_expiry_days', 'max_recovery_per_month']:
            config[key] = self.svrp._get_config(key)

        text = (
            f"💎 <b>إدارة التعويض</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>الإحصائيات</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 أرصدة مصدرة: <code>{stats['total_credits_issued']:.2f}</code>\n"
            f"📉 أرصدة مستخدمة: <code>{stats['total_credits_used']:.2f}</code>\n"
            f"✅ أرصدة نشطة: <code>{stats['active_credits']}</code>\n"
            f"👥 المحافظ: <code>{stats['total_wallets']}</code>\n"
            f"💵 إجمالي الأرصدة: <code>{stats['total_balance']:.2f}</code>\n"
            f"⏳ رصيد معلق: <code>{stats['total_pending']:.2f}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ <b>الإعدادات الحالية</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔢 مضاعف التعويض: <code>{config['recovery_multiplier']}x</code>\n"
            f"💎 الحد الأقصى لكل حدث: <code>{config['max_recovery_cap']}</code>\n"
            f"🎯 متطلبات الرهان: <code>{config['wagering_requirement']}</code> معاملة\n"
            f"📈 الحد الشهري: <code>{config['max_recovery_per_month']}</code>\n"
        )

        inline_btns = [
            [{'text': '⚙️ الإعدادات', 'callback_data': 'svrp_admin_settings'},
             {'text': '👥 المحافظ', 'callback_data': 'svrp_admin_wallets'}],
            [{'text': '🏢 الشركات والحسابات', 'callback_data': 'svrp_admin_companies'},
             {'text': '🏆 طلبات المكافآت', 'callback_data': 'svrp_admin_bonus_reqs'}],
            [{'text': '📸 طلبات الاسترداد', 'callback_data': 'svrp_admin_recovery_reqs'},
             {'text': '💰 طلبات الإيداع', 'callback_data': 'svrp_admin_dep_reqs'}],
            [{'text': '📝 تعديل النصوص', 'callback_data': 'svrp_edit_texts'},
             {'text': '📊 إحصائيات تفصيلية', 'callback_data': 'svrp_admin_detailed'}],
            [{'text': '🔙 العودة للوحة الأدمن', 'callback_data': 'svrp_admin_back'}]
        ]

        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def svrp_admin_view_wallets(self, chat_id):
        """عرض جميع محافظ تعويض 100%"""
        wallets = self.svrp._read_csv('svrp_wallets.csv')
        if not wallets:
            self.send_message(chat_id, self.tr('a0085_لا_توجد', 'ar'), self.admin_keyboard('ar'))
            return

        text = self.tr('a0086_المحافظ', 'ar')
        for w in wallets[:20]:  # أول 20 محفظة
            text += (
                f"👤 <code>{w.get('telegram_id', '')}</code>\n"
                f"  💰 الرصيد: {float(w.get('balance', 0) or 0):.2f}\n"
                f"  ⏳ معلق: {float(w.get('pending_balance', 0) or 0):.2f}\n"
                f"  📈 مكتسب: {float(w.get('total_earned', 0) or 0):.2f}\n"
                f"  🎯 رهان: {w.get('wagering_completed', '0')}/{w.get('wagering_required', '3')}\n\n"
            )
        if len(wallets) > 20:
            text += f"... و {len(wallets) - 20} محفظة أخرى"

        inline_btns = [[{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]]
        self.send_inline_message(chat_id, text, inline_btns)

    def svrp_admin_view_promos(self, chat_id):
        """عرض الأكواد الترويجية"""
        promos = self.svrp._read_csv('svrp_promo_codes.csv')
        if not promos:
            self.send_inline_message(chat_id, self.tr('a0087_لا_توجد', 'ar'),
                [[{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]])
            return

        text = self.tr('a0088_الأكواد_الترويجية', 'ar')
        for p in promos:
            status_icon = {'active': '✅', 'fully_used': '🔴', 'expired': '⏰'}.get(p.get('status', ''), '✅')
            text += (
                f"{status_icon} <code>{p['code']}</code>\n"
                f"  💰 {p.get('amount', '')} | 👤 {p.get('creator_id', '')}\n"
                f"  📊 {p.get('used_count', '0')}/{p.get('max_uses', '10')} | 📅 {p.get('expires_at', '')}\n\n"
            )

        inline_btns = [[{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]]
        self.send_inline_message(chat_id, text, inline_btns)

    def svrp_admin_view_tasks(self, chat_id):
        """عرض المهام"""
        tasks = self.svrp._read_csv('svrp_tasks.csv')
        if not tasks:
            self.send_inline_message(chat_id, self.tr('a0089_لا_توجد', 'ar'),
                [[{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]])
            return

        text = self.tr('a0090_المهام', 'ar')
        active = [t for t in tasks if t.get('status') == 'active']
        completed = [t for t in tasks if t.get('status') == 'completed']
        claimed = [t for t in tasks if t.get('status') == 'claimed']

        text += f"⏳ نشطة: {len(active)} | ✅ مكتملة: {len(completed)} | 🎉 مستلمة: {len(claimed)}\n\n"
        for t in active[:15]:
            text += (
                f"⏳ <code>{t['id']}</code> | {t.get('task_type', '')}\n"
                f"  {t.get('current_progress', '0')}/{t.get('target_value', '1')} → 🎁 {t.get('reward_amount', '0')}\n"
            )

        inline_btns = [[{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]]
        self.send_inline_message(chat_id, text, inline_btns)

    def svrp_admin_edit_settings(self, chat_id):
        """تعديل إعدادات تعويض 100% — بأزرار inline"""
        config_labels = {
            'recovery_multiplier': '🔢 مضاعف الاسترداد',
            'max_recovery_cap': '💎 الحد الأقصى/حدث',
            'credit_expiry_days': '📅 انتهاء الرصيد (يوم)',
            'wagering_requirement': '🎯 متطلبات الرهان',
            'promo_code_max_uses': '🎟️ حد استخدام الكود',
            'promo_code_expiry_days': '⏰ انتهاء الكود (يوم)',
            'max_recovery_per_month': '📈 الحد الشهري',
        }

        text = (
            "╔════════════════════╗\n"
            "║  ⚙️ إعدادات الاسترداد  ║\n"
            "╚════════════════════╝\n\n"
            "اضغط على أي إعداد لتعديله:\n"
        )

        inline_btns = []
        for key, label in config_labels.items():
            val = self.svrp._get_config(key)
            inline_btns.append([{
                'text': f"{label}: {val} ✏️",
                'callback_data': f"svrp_edit_{key}"
            }])
        inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}])

        self.send_inline_message(chat_id, text, inline_btns)

    def svrp_admin_edit_one_setting(self, chat_id, message_id, key):
        """تعديل إعداد واحد — عرض القيمة الحالية وأزرار + و -"""
        config_labels = {
            'recovery_multiplier': '🔢 مضاعف الاسترداد',
            'max_recovery_cap': '💎 الحد الأقصى/حدث',
            'credit_expiry_days': '📅 انتهاء الرصيد (يوم)',
            'wagering_requirement': '🎯 متطلبات الرهان',
            'promo_code_max_uses': '🎟️ حد استخدام الكود',
            'promo_code_expiry_days': '⏰ انتهاء الكود (يوم)',
            'max_recovery_per_month': '📈 الحد الشهري',
        }
        config_steps = {
            'recovery_multiplier': 0.5,
            'max_recovery_cap': 500,
            'credit_expiry_days': 5,
            'wagering_requirement': 1,
            'promo_code_max_uses': 1,
            'promo_code_expiry_days': 1,
            'max_recovery_per_month': 1000,
        }

        current_val = self.svrp._get_config(key)
        label = config_labels.get(key, key)
        step = config_steps.get(key, 1)

        text = (
            f"⚙️ تعديل: {label}\n\n"
            f"📊 القيمة الحالية: <b>{current_val}</b>\n\n"
            f"➕ زيادة بمقدار {step}\n"
            f"➖ نقصان بمقدار {step}\n\n"
            f"أو اكتب القيمة الجديدة مباشرة:"
        )

        inline_btns = [
            [{'text': f'➕ +{step}', 'callback_data': f'svrp_inc_{key}_{step}'},
             {'text': f'➖ -{step}', 'callback_data': f'svrp_dec_{key}_{step}'}],
            [{'text': '✅ تم', 'callback_data': 'svrp_admin_settings'},
             {'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]
        ]

        self.edit_message(chat_id, message_id, text)
        self.send_inline_message(chat_id, text, inline_btns)

    def svrp_admin_cleanup(self, chat_id):
        """تنظيف الأرصدة المنتهية"""
        expired = self.svrp.expire_old_credits()
        self.edit_or_send(chat_id,
            self.tr('a0091_تم_التنظيف', 'ar', expired=expired),
            [[{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]])

    def _update_svrp_config(self, key, new_val):
        """تحديث قيمة في إعدادات تعويض 100%"""
        try:
            from svrp import SVRP_CONFIG
            if isinstance(SVRP_CONFIG.get(key), float):
                SVRP_CONFIG[key] = float(new_val)
            elif isinstance(SVRP_CONFIG.get(key), int):
                SVRP_CONFIG[key] = int(new_val)
            else:
                SVRP_CONFIG[key] = new_val
            logger.info(f"SVRP config updated: {key} = {new_val}")
        except Exception as e:
            logger.error(f"خطأ في تحديث إعداد SVRP: {e}")

    def edit_or_send(self, chat_id, text, inline_btns=None):
        """إرسال أو تعديل رسالة"""
        if inline_btns:
            self.send_inline_message(chat_id, text, inline_btns)
        else:
            self.send_message(chat_id, text)

    # ==================== End 💎 تعويض 100% — Panel Methods ====================

    def track_user_activity(self, telegram_id, activity_type='login'):
        """تتبع نشاط المستخدم"""
        try:
            rows = self.safe_csv_read('user_activity.csv')
            found = False
            for row in rows:
                if row.get('telegram_id') == str(telegram_id):
                    row['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                    row['last_activity'] = activity_type
                    if activity_type == 'deposit':
                        row['total_deposits'] = str(int(row.get('total_deposits', 0)) + 1)
                    elif activity_type == 'withdraw':
                        row['total_withdrawals'] = str(int(row.get('total_withdrawals', 0)) + 1)
                    row['total_transactions'] = str(int(row.get('total_transactions', 0)) + 1)
                    found = True
                    break
            if not found:
                rows.append({
                    'telegram_id': str(telegram_id),
                    'last_login': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'total_transactions': '0',
                    'total_deposits': '0',
                    'total_withdrawals': '0',
                    'rating_avg': '',
                    'last_activity': activity_type
                })
            self.safe_csv_write('user_activity.csv', rows,
                fieldnames=['telegram_id','last_login','total_transactions','total_deposits','total_withdrawals','rating_avg','last_activity'], mode='w')
        except Exception as e:
            logger.error(f"خطأ في تتبع نشاط المستخدم: {e}")

    def get_user_daily_total(self, telegram_id, trans_type=None):
        """مجموع معاملات اليوم لمستخدم"""
        try:
            rows = self.safe_csv_read('transactions.csv')
            today = datetime.now().strftime('%Y-%m-%d')
            total = 0
            for row in rows:
                if row.get('telegram_id') == str(telegram_id) and row.get('date', '').startswith(today):
                    if row.get('status') in ('approved', 'pending', 'pending_code_verification'):
                        if trans_type is None or row.get('type') == trans_type:
                            total += float(row.get('amount', 0) or 0)
            return total
        except:
            return 0

    def check_daily_limit(self, user, amount, trans_type):
        """فحص الحد اليومي الذكي حسب التقييم"""
        telegram_id = user.get('telegram_id', '0')
        # الحصول على تقييم المستخدم
        rating = None
        if self.match_manager:
            rating = self.match_manager.get_user_rating(int(telegram_id))

        # تحديد الحد الأقصى حسب التقييم
        max_daily = float(self.get_setting('max_daily_withdrawal') or '10000')
        if rating and rating >= 4:
            max_daily *= 1.5  # عملاء موثوقين: +50%
        elif rating and rating < 3:
            max_daily *= 0.5  # عملاء أقل تقييماً: -50%

        current_total = self.get_user_daily_total(int(telegram_id), trans_type)
        if current_total + amount > max_daily:
            return False, max_daily, current_total
        return True, max_daily, current_total

    def show_help_guide(self, message):
        """دليل استخدام البوت"""
        user = self.find_user(message['from']['id'])
        lang = user.get('language', 'ar') if user else 'ar'

        help_text = (
            f"{self.tr('help_title', lang)}\n\n"
            f"{self.tr('help_deposit_title', lang)}\n"
            f"  {self.tr('help_deposit_steps', lang)}\n\n"
            f"{self.tr('help_withdraw_title', lang)}\n"
            f"  {self.tr('help_withdraw_steps', lang)}\n\n"
            f"{self.tr('help_match_title', lang)}\n"
            f"  {self.tr('help_match_steps', lang)}\n\n"
            f"{self.tr('help_referral_title', lang)}\n"
            f"  {self.tr('help_referral_steps', lang)}\n\n"
            f"{self.tr('help_notif_title', lang)}\n"
            f"  {self.tr('help_notif_steps', lang)}\n\n"
            f"{self.tr('help_complaint_title', lang)}\n"
            f"  {self.tr('help_complaint_steps', lang)}\n\n"
            f"{self.tr('help_support_title', lang)}\n"
            f"  {self.tr('help_support_steps', lang)}"
        )
        self.send_message(message['chat']['id'], help_text, self.main_keyboard(lang, message['from']['id']))

    def get_admin_ids(self):
        """جلب معرفات الأدمن"""
        admin_ids = os.getenv('ADMIN_USER_IDS', '').split(',')
        return [admin_id.strip() for admin_id in admin_ids if admin_id.strip()]
    
    def is_admin(self, telegram_id):
        """فحص صلاحية الأدمن — مع التحقق من انتهاء الصلاحية"""
        tid_str = str(telegram_id)
        # المدراء الدائمين من متغيرات البيئة
        if tid_str in self.admin_ids:
            return True
        try:
            tid = int(telegram_id)
            # المدراء الدائمين من الجلسة
            if tid in self.admin_user_ids:
                return True
            # المدراء المؤقتين — فحص انتهاء الصلاحية
            if tid in self.temp_admin_user_ids:
                if tid in self.temp_admin_expiry:
                    if self.temp_admin_expiry[tid] <= time.time():
                        self.temp_admin_user_ids.remove(tid)
                        del self.temp_admin_expiry[tid]
                        logger.info(f"انتهت صلاحية المدير المؤقت: {tid}")
                        return False
                return True
        except (ValueError, TypeError):
            pass
        return False
    
    def notify_admins(self, message, notification_type='general', inline_buttons=None):
        """إشعار جميع الأدمن — مع تسجيل في سجل الإشعارات"""
        self.log_notification('admin', 'all', notification_type, message)
        for admin_id in self.admin_ids:
            try:
                tid = int(admin_id)
                if inline_buttons:
                    self.send_inline_message(tid, message, inline_buttons)
                else:
                    self.send_message(tid, message, self.admin_keyboard())
            except:
                pass

    def notify_user(self, telegram_id, message, notification_type='general', inline_buttons=None):
        """إشعار مستخدم محدد — مع تسجيل وتحقق من تفضيلات الإشعارات"""
        user = self.find_user(telegram_id)
        if user and user.get('notifications_enabled', 'yes') == 'no':
            return  # المستخدم عطل الإشعارات
        self.log_notification('user', str(telegram_id), notification_type, message)
        try:
            if inline_buttons:
                self.send_inline_message(telegram_id, message, inline_buttons)
            else:
                self.send_message(telegram_id, message)
        except:
            pass

    # ==================== القنوات/المجموعات ====================

    def get_bot_channels(self, active_only=True):
        """جلب القنوات/المجموعات المرتبطة"""
        channels = []
        try:
            with open('bot_channels.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if active_only and row.get('is_active') != 'yes':
                        continue
                    channels.append(row)
        except:
            pass
        return channels

    def post_to_channels(self, text, photo=None, video=None, document=None, sticker=None, exclude_chat_id=None):
        """نشر محتوى في كل القنوات/المجموعات المرتبطة — مع استثناء القناة المصدر"""
        channels = self.get_bot_channels()
        sent = 0
        for ch in channels:
            chat_id = ch.get('chat_id', '')
            if not chat_id:
                continue
            # استثناء القناة المصدر لمنع التكرار اللانهائي
            if exclude_chat_id and str(chat_id) == str(exclude_chat_id):
                continue
            try:
                if photo:
                    self.api_call('sendPhoto', {
                        'chat_id': chat_id, 'photo': photo,
                        'caption': text[:1024] if text else '', 'parse_mode': 'HTML'
                    })
                elif video:
                    self.api_call('sendVideo', {
                        'chat_id': chat_id, 'video': video,
                        'caption': text[:1024] if text else '', 'parse_mode': 'HTML'
                    })
                elif document:
                    self.api_call('sendDocument', {
                        'chat_id': chat_id, 'document': document,
                        'caption': text[:1024] if text else '', 'parse_mode': 'HTML'
                    })
                elif sticker:
                    self.api_call('sendSticker', {
                        'chat_id': chat_id, 'sticker': sticker
                    })
                else:
                    self.api_call('sendMessage', {
                        'chat_id': chat_id, 'text': text[:4096], 'parse_mode': 'HTML'
                    })
                sent += 1
            except Exception as e:
                logger.error(f"خطأ في النشر للقناة {chat_id}: {e}")
            time.sleep(0.05)  # منع flood limit
        return sent

    def broadcast_to_all_users(self, text, photo=None, video=None, document=None, sticker=None):
        """بث محتوى لكل المستخدمين — في thread منفصل حتى لا يمنع معالجة رسائل المستخدمين"""
        import threading as _th
        def _do_broadcast():
            sent = 0
            failed = 0
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        tid = row.get('telegram_id', '')
                        if not tid:
                            continue
                        # تخطي المحظورين
                        if row.get('is_banned') == 'yes':
                            continue
                        try:
                            if photo:
                                result = self.api_call('sendPhoto', {
                                    'chat_id': int(tid), 'photo': photo,
                                    'caption': text[:1024] if text else '', 'parse_mode': 'HTML'
                                }, retries=1)  # retry=1 — لا تكرر الفشل
                            elif video:
                                result = self.api_call('sendVideo', {
                                    'chat_id': int(tid), 'video': video,
                                    'caption': text[:1024] if text else '', 'parse_mode': 'HTML'
                                }, retries=1)
                            elif document:
                                result = self.api_call('sendDocument', {
                                    'chat_id': int(tid), 'document': document,
                                    'caption': text[:1024] if text else '', 'parse_mode': 'HTML'
                                }, retries=1)
                            elif sticker:
                                result = self.api_call('sendSticker', {
                                    'chat_id': int(tid), 'sticker': sticker
                                }, retries=1)
                            else:
                                result = self.send_message(int(tid), text, None)
                            if result:
                                sent += 1
                            else:
                                failed += 1
                        except:
                            failed += 1
                        # rate limiting: 20 رسالة ثم انتظار 1 ثانية
                        if (sent + failed) % 20 == 0:
                            time.sleep(1)
                # تسجيل البث
                self._log_relay('broadcast', '', text[:100], sent, 0)
                logger.info(f"Broadcast done: {sent} sent, {failed} failed")
            except Exception as e:
                logger.error(f"خطأ في البث: {e}")
            return sent, failed
        # تشغيل في thread منفصل — لا يمنع البوت عن معالجة رسائل المستخدمين
        t = _th.Thread(target=_do_broadcast, daemon=True)
        t.start()
        return 0, 0  # يتم إرجاع 0 لأن البث غير متزامن

    def _log_relay(self, source_type, source_chat_id, preview, user_count, channel_count):
        """تسجيل عملية ترحيل في relay_log.csv"""
        try:
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'relay_log.csv')
            file_exists = os.path.exists(filepath)
            with open(filepath, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'source_type', 'source_chat_id', 'preview', 'users_relayed', 'channels_relayed'])
                writer.writerow([
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    source_type, source_chat_id, preview[:100],
                    user_count, channel_count
                ])
        except:
            pass

    def _apply_text_replacements(self, text, chat_id=''):
        """استبدال النصوص وفقاً لقواعد المسؤول"""
        import re
        try:
            with open('text_replacements.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('is_active') != 'yes':
                        continue
                    # فلترة بالقناة (فارغ = كل القنوات)
                    row_channel = row.get('channel_id', '')
                    if row_channel and row_channel != chat_id:
                        continue
                    find_text = row.get('find_text', '')
                    replace_text = row.get('replace_text', '')
                    if not find_text:
                        continue
                    if row.get('is_regex') == 'yes':
                        try:
                            text = re.sub(find_text, replace_text, text)
                        except:
                            pass
                    else:
                        text = text.replace(find_text, replace_text)
        except:
            pass
        return text

    def _process_with_ai(self, text, chat_id=''):
        """معالجة نص بوست باستخدام نظام AI متعدد المزودين"""
        try:
            from ai_providers import AIManager
        except ImportError:
            return None

        ai_manager = AIManager()

        # قراءة تعليمات AI من الإعدادات
        ai_instructions = ''
        try:
            with open('system_settings.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('setting_key') == 'ai_instructions':
                        ai_instructions = row.get('setting_value', '')
                        break
        except:
            pass

        if not ai_instructions:
            ai_instructions = (
                "أنت محرر محتوى احترافي للقنوات التيليجرام. "
                "أعد صياغة البوست التالي بأسلوب جذاب ومحترف. "
                "حافظ على المعنى والروابط. "
                "أضف إيموجي مناسب. "
                "اجعل العنوان بارزاً. "
                "لا تضف معلومات غير موجودة في النص الأصلي."
            )

        try:
            processed, used_provider = ai_manager.process(text, ai_instructions)
            if processed and len(processed) > 10:
                # حفظ في post_vault + ai_processed_posts
                post_id = f"AIP{str(int(datetime.now().timestamp()))[-6:]}"
                try:
                    with open('ai_processed_posts.csv', 'a', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow([post_id, '', chat_id, text[:200], processed[:200],
                                       used_provider or 'unknown', 'processed', datetime.now().strftime('%Y-%m-%d %H:%M'),
                                       '', 0, 0])
                    # حفظ في post_vault أيضاً
                    with open('post_vault.csv', 'a', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow([post_id, '', chat_id, text[:500], processed[:500],
                                       'text', '', used_provider or 'unknown', 'published',
                                       datetime.now().strftime('%Y-%m-%d %H:%M'), 0, 0, 0, ''])
                except:
                    pass
                return processed
        except Exception as e:
            logger.error(f"خطأ في معالجة AI: {e}")
        return None

    # ==================== نظام القنوات المصدرية (Content Scraping) ====================

    def scrape_source_channel(self, source_channel_id):
        """جلب آخر البوستات من قناة مصدرية (بوت مشترك فيها)"""
        try:
            # قراءة بيانات القناة المصدرية
            source_channels = read_csv_helper('source_channels.csv')
            source = None
            for s in source_channels:
                if s.get('id') == source_channel_id:
                    source = s
                    break
            if not source:
                return []

            chat_id = source.get('chat_id', '')
            if not chat_id:
                return []

            # جلب آخر 5 رسائل من القناة
            result = self.api_call('getChat', {'chat_id': chat_id})
            if not result or not result.get('ok'):
                return []

            # استخدام forwardMessage لنسخ آخر البوستات
            # Telegram API لا يدعم getHistory مباشرة، لكن يمكن استخدام getUpdates
            # للقنوات المشترك فيها، نحصل على آخر المشاركات عبر chat updates
            scraped = []
            # محاولة جلب آخر رسالة من القناة
            try:
                # استخدام sendMessage with disable_notification لجلب chat info
                # ثم getChatMemberCount
                count_result = self.api_call('getChatMemberCount', {'chat_id': chat_id})
                member_count = count_result.get('result', 0) if count_result else 0

                # حفظ عضو القناة في post_vault كـ "scraped"
                # الحل العملي: البوت يتلقى رسائل القناة عبر getUpdates (مستخدم مشترك)
                # عند استلام رسالة من قناة مصدرية، تُعالج وتُنشر في القنوات المستهدفة
                logger.info(f"Scraped source channel {source_channel_id}: {member_count} members")
            except:
                pass

            return scraped
        except Exception as e:
            logger.error(f"خطأ في scraping: {e}")
            return []

    def process_source_channel_post(self, message):
        """معالجة بوست من قناة — حسب دور القناة وإعدادات المحتوى"""
        chat_id = message.get('chat', {}).get('id', '')
        chat_title = message.get('chat', {}).get('title', '')

        # فحص هل القناة مسجلة (سواء مصدرية أو مدارة)
        channel_settings = self.get_channel_settings(chat_id)
        source_channel = None

        if not channel_settings:
            # فحص source_channels
            try:
                with open('source_channels.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('is_active') == 'yes' and row.get('chat_id') == str(chat_id):
                            source_channel = row
                            break
            except:
                pass
            if not source_channel:
                return False
            # استخدام إعدادات source_channels
            source = source_channel
            brand_voice = source.get('brand_voice', '')
            target_ids = source.get('target_channel_ids', '').split('|') if source.get('target_channel_ids') else []
            content_filter = source.get('content_filter', 'all')  # all, text_only, photo_only, video_only, text_photo, text_photo_video
            ai_edit_text = source.get('ai_edit_text', 'no') == 'yes'
            ai_edit_media = source.get('ai_edit_media', 'no') == 'yes'
            ai_provider = source.get('ai_provider', '')
            text_replacements_enabled = True
        else:
            # قناة مدارة (البوت مشرف)
            if channel_settings.get('channel_role', 'both') not in ('source', 'both'):
                return False  # قناة نشر فقط — لا نأخذ منها
            source = channel_settings
            brand_voice = source.get('brand_voice', '')
            target_ids = []  # النشر يتم عبر relay_to_users/relay_to_channels
            content_filter = source.get('forward_mode', 'all')
            ai_edit_text = source.get('ai_enabled', 'no') == 'yes'
            ai_edit_media = False  # تعديل الصور متاح فقط في القنوات المصدرية
            ai_provider = source.get('ai_provider', '')
            text_replacements_enabled = True

        # تطبيق فلتر المحتوى — تحديد ما نأخذه
        text = ''
        media_type = ''
        media_file_id = ''
        has_text = 'text' in message
        has_caption = 'caption' in message
        has_photo = 'photo' in message
        has_video = 'video' in message
        has_document = 'document' in message

        if has_text:
            text = message['text']
        elif has_caption:
            text = message['caption']

        if has_photo:
            media_type = 'photo'
            media_file_id = message['photo'][-1].get('file_id', '')
        elif has_video:
            media_type = 'video'
            media_file_id = message['video'].get('file_id', '')
        elif has_document:
            media_type = 'document'
            media_file_id = message['document'].get('file_id', '')

        # فلترة حسب نوع المحتوى المطلوب
        if content_filter == 'text_only':
            if not text or (has_photo or has_video):
                media_type = ''
                media_file_id = ''
        elif content_filter == 'photo_only':
            if not has_photo:
                return False
        elif content_filter == 'video_only':
            if not has_video:
                return False
        elif content_filter == 'text_photo':
            if not text or not has_photo:
                return False
        elif content_filter == 'text_photo_video':
            if not text or (not has_photo and not has_video):
                return False

        if not text and not media_file_id:
            return False

        # استبدال النصوص المخصصة
        if text and text_replacements_enabled:
            text = self._apply_text_replacements(text, str(chat_id))

        # تكييف النص بـ AI
        final_text = text
        used_provider = 'none'
        if ai_edit_text and text and len(text) > 10:
            try:
                from ai_providers import AIManager
                ai_manager = AIManager()
                instructions = brand_voice or (
                    "أنت محرر محتوى احترافي للقنوات التيليجرام. "
                    "أعد صياغة البوست بأسلوب جذاب ومحترف. "
                    "حافظ على المعنى والروابط. أضف إيموجي مناسب."
                )
                processed, used_provider = ai_manager.process(text, instructions)
                if processed and len(processed) > 10:
                    final_text = processed
            except Exception as e:
                logger.error(f"خطأ في AI للنص: {e}")

        # حفظ في post_vault
        post_id = f"SCR{str(int(datetime.now().timestamp()))[-6:]}"
        try:
            with open('post_vault.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([post_id, chat_title, str(chat_id), (text or '')[:500], final_text[:500],
                               media_type, media_file_id, used_provider, 'published',
                               datetime.now().strftime('%Y-%m-%d %H:%M'), 0, 0, 0, 'scraped'])
        except:
            pass

        # نشر في القنوات المستهدفة
        published = 0
        if target_ids:
            for tid in target_ids:
                tid = tid.strip()
                if not tid:
                    continue
                try:
                    if media_type == 'photo' and media_file_id:
                        self.api_call('sendPhoto', {
                            'chat_id': tid, 'photo': media_file_id,
                            'caption': final_text[:1024], 'parse_mode': 'HTML'
                        })
                    elif media_type == 'video' and media_file_id:
                        self.api_call('sendVideo', {
                            'chat_id': tid, 'video': media_file_id,
                            'caption': final_text[:1024], 'parse_mode': 'HTML'
                        })
                    elif media_type == 'document' and media_file_id:
                        self.api_call('sendDocument', {
                            'chat_id': tid, 'document': media_file_id,
                            'caption': final_text[:1024], 'parse_mode': 'HTML'
                        })
                    else:
                        self.api_call('sendMessage', {
                            'chat_id': tid, 'text': final_text[:4096], 'parse_mode': 'HTML'
                        })
                    published += 1
                except:
                    pass

        # نشر لكل المستخدمين (لو relay_to_users)
        users_reached = 0
        if source.get('relay_to_users', 'no') == 'yes' or (channel_settings and channel_settings.get('relay_to_users', 'no') == 'yes'):
            try:
                sent, _ = self.broadcast_to_all_users(final_text)
                users_reached = sent
            except:
                pass

        # تحديث post_vault بأرقام النشر
        try:
            rows = []
            with open('post_vault.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = list(reader)
            for row in rows:
                if row.get('id') == post_id:
                    row['published_to_users'] = str(users_reached)
                    row['published_to_channels'] = str(published)
                    row['status'] = 'published'
                    break
            with open('post_vault.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
        except:
            pass

        self._log_relay('source_scrape', str(chat_id), final_text[:100], users_reached, published)

        # إشعار الأدمن
        for admin_id in self.admin_ids:
            try:
                self.send_message(int(admin_id),
                    f"📥 <b>محتوى منقول من قناة مصدرية</b>\n\n"
                    f"📋 المصدر: <b>{chat_title}</b>\n"
                    f"✨ المعالج بـ AI: {'نعم' if processed else 'لا'}\n"
                    f"📤 نُشر في: {published} قناة + {users_reached} مستخدم\n\n"
                    f"📝 المعاينة:\n<i>{final_text[:200]}...</i>")
            except:
                pass

        return True

    # ==================== نظام التحليل والتقارير اليومية ====================

    def generate_daily_report(self):
        """توليد تقرير يومي + توصيات AI"""
        today = datetime.now().strftime('%Y-%m-%d')

        # جمع البيانات
        relay_logs = []
        try:
            with open('relay_log.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('timestamp', '').startswith(today):
                        relay_logs.append(row)
        except:
            pass

        ai_posts = []
        try:
            with open('ai_processed_posts.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('created_at', '').startswith(today):
                        ai_posts.append(row)
        except:
            pass

        channels = self.get_bot_channels(active_only=False)
        active_channels = [c for c in channels if c.get('is_active') == 'yes']

        total_users_reached = sum(int(l.get('users_relayed', 0) or 0) for l in relay_logs)
        total_channels_reached = sum(int(l.get('channels_relayed', 0) or 0) for l in relay_logs)

        # أكثر القنوات نشاطاً
        channel_activity = {}
        for log in relay_logs:
            src = log.get('source_chat_id', 'unknown')
            channel_activity[src] = channel_activity.get(src, 0) + 1
        top_channels = sorted(channel_activity.items(), key=lambda x: x[1], reverse=True)[:5]
        top_channels_str = ' | '.join([f"{c[0]}: {c[1]}" for c in top_channels])

        # توليد توصيات AI
        recommendations = self._generate_ai_recommendations(relay_logs, ai_posts, active_channels)

        report_id = f"RPT{str(int(datetime.now().timestamp()))[-6:]}"
        try:
            with open('daily_reports.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([report_id, today, len(relay_logs), total_users_reached,
                               total_channels_reached, len(ai_posts), top_channels_str[:200],
                               recommendations[:500], datetime.now().strftime('%Y-%m-%d %H:%M')])
        except:
            pass

        # إرسال للأدمن
        report_text = (
            f"📊 <b>التقرير اليومي — {today}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📨 البوستات المنشورة: <code>{len(relay_logs)}</code>\n"
            f"👥 وصل لـ: <code>{total_users_reached}</code> مستخدم\n"
            f"📢 نُشر في: <code>{total_channels_reached}</code> قناة\n"
            f"🤖 معالجة AI: <code>{len(ai_posts)}</code> بوست\n"
            f"📡 قنوات نشطة: <code>{len(active_channels)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        if top_channels:
            report_text += self.tr('a0092_أكثر_القنوات', 'ar')
            for ch, count in top_channels[:3]:
                report_text += self.tr('a0093_بوست', 'ar', ch=ch, count=count)

        if recommendations:
            report_text += f"\n🤖 <b>توصيات AI:</b>\n<i>{recommendations[:500]}</i>\n"

        report_text += f"\n━━━━━━━━━━━━━━━━━━\n🆔 <code>{report_id}</code>"

        for admin_id in self.admin_ids:
            try:
                self.send_message(int(admin_id), report_text)
            except:
                pass

        return report_text

    def _generate_ai_recommendations(self, relay_logs, ai_posts, active_channels):
        """توليد توصيات باستخدام AI"""
        try:
            from ai_providers import AIManager
            ai_manager = AIManager()

            # تحليل الأداء
            total_posts = len(relay_logs)
            total_ai = len(ai_posts)
            total_channels = len(active_channels)

            analysis_text = (
                f"حلل هذا البيانات وقدم 3 توصيات عملية لتحسين الأداء:\n\n"
                f"البوستات اليوم: {total_posts}\n"
                f"معالجة AI: {total_ai}\n"
                f"القنوات النشطة: {total_channels}\n\n"
                f"قدم توصيات قصيرة ومباشرة بالعربية."
            )

            result, _ = ai_manager.process(analysis_text,
                self.tr('a0094_أنت_مستشار', 'ar'))
            return result or self.tr('a0095_لا_توجد', 'ar')
        except:
            return self.tr('a0096_لا_يمكن', 'ar')

    def auto_relay_channel_post(self, message):
        """إعادة نشر بوست من قناة البوت مشرف لها لكل المستخدمين — مع احترام كل الإعدادات"""
        chat_id = message.get('chat', {}).get('id', '')
        chat_title = message.get('chat', {}).get('title', '')
        chat_type = message.get('chat', {}).get('type', '')

        # فحص هل القناة مسجلة
        channel_settings = self.get_channel_settings(chat_id)
        if not channel_settings:
            return False

        if channel_settings.get('is_active') != 'yes':
            return False

        relay_to_users = channel_settings.get('relay_to_users', 'yes') == 'yes'
        relay_to_channels = channel_settings.get('relay_to_channels', 'yes') == 'yes'
        forward_mode = channel_settings.get('forward_mode', 'all')  # all, text_only, media_only

        # تحديد نوع الرسالة
        has_text = 'text' in message
        has_media = any(k in message for k in ('photo', 'video', 'document', 'sticker', 'animation', 'voice', 'audio'))

        # تطبيق forward_mode — فلترة حقيقية
        if forward_mode == 'text_only':
            # نص فقط: تخطي الرسائل التي ليس فيها نص
            if not has_text:
                return False
            # لو في ميديا + نص، نرسل النص فقط (نتجاهل الميديا)
            if has_media:
                message = {'text': message.get('text', message.get('caption', '')), 'chat': message.get('chat', {}), 'from': message.get('from', {})}
                has_media = False
        elif forward_mode == 'media_only':
            # ميديا فقط: تخطي الرسائل النصية البحتة
            if has_text and not has_media:
                return False
            # لو في نص + ميديا، نرسل الميديا بدون الكابشن (نتجاهل النص)
            if has_text and has_media:
                # إزالة النص من الرسالة — نرسل الميديا فقط
                message = dict(message)
                message.pop('text', None)
                if 'caption' in message:
                    message['caption'] = ''
                has_text = False

        # استخراج المحتوى
        user_name = message.get('from', {}).get('first_name', '') or message.get('from', {}).get('title', '')
        welcome = channel_settings.get('welcome_text', '')
        relay_header = self.tr('a0097_إعلان_من', 'ar', chat_title=chat_title, user_name=user_name)
        if welcome:
            relay_header = f"{welcome}\n\n{relay_header}"

        # === نظام استبدال النصوص ===
        if 'text' in message:
            message['text'] = self._apply_text_replacements(message['text'], str(chat_id))
        if 'caption' in message and message['caption']:
            message['caption'] = self._apply_text_replacements(message['caption'], str(chat_id))

        # === نظام AI — معالجة البوست قبل النشر ===
        ai_enabled = channel_settings.get('ai_enabled', 'no') == 'yes'
        if ai_enabled and 'text' in message:
            processed = self._process_with_ai(message['text'], str(chat_id))
            if processed:
                message['text'] = processed

        users_relayed = 0
        channels_relayed = 0
        preview = ''

        try:
            if 'text' in message:
                text = message['text']
                preview = text[:100]
                if relay_to_users:
                    s, _ = self.broadcast_to_all_users(relay_header + text)
                    users_relayed = s
                if relay_to_channels:
                    channels_relayed = self.post_to_channels(relay_header + text, exclude_chat_id=chat_id)
                self._log_relay('channel_post', str(chat_id), preview, users_relayed, channels_relayed)
                return True

            elif 'photo' in message:
                photo = message['photo'][-1]['file_id']
                caption = message.get('caption', '')
                preview = self.tr('a0098_صورة', 'ar') + caption[:80]
                if relay_to_users:
                    s, _ = self.broadcast_to_all_users(relay_header + caption, photo=photo)
                    users_relayed = s
                if relay_to_channels:
                    channels_relayed = self.post_to_channels(relay_header + caption, photo=photo, exclude_chat_id=chat_id)
                self._log_relay('channel_post', str(chat_id), preview, users_relayed, channels_relayed)
                return True

            elif 'video' in message:
                video = message['video']['file_id']
                caption = message.get('caption', '')
                preview = self.tr('a0099_فيديو', 'ar') + caption[:80]
                if relay_to_users:
                    s, _ = self.broadcast_to_all_users(relay_header + caption, video=video)
                    users_relayed = s
                if relay_to_channels:
                    channels_relayed = self.post_to_channels(relay_header + caption, video=video, exclude_chat_id=chat_id)
                self._log_relay('channel_post', str(chat_id), preview, users_relayed, channels_relayed)
                return True

            elif 'document' in message:
                doc = message['document']['file_id']
                caption = message.get('caption', '')
                preview = self.tr('a0100_ملف', 'ar') + caption[:80]
                if relay_to_users:
                    s, _ = self.broadcast_to_all_users(relay_header + caption, document=doc)
                    users_relayed = s
                if relay_to_channels:
                    channels_relayed = self.post_to_channels(relay_header + caption, document=doc, exclude_chat_id=chat_id)
                self._log_relay('channel_post', str(chat_id), preview, users_relayed, channels_relayed)
                return True

            elif 'sticker' in message:
                sticker = message['sticker']['file_id']
                preview = self.tr('a0101_ملصق', 'ar')
                if relay_to_users:
                    s, _ = self.broadcast_to_all_users(relay_header + self.tr('a0102_ملصق', 'ar'), sticker=sticker)
                    users_relayed = s
                if relay_to_channels:
                    channels_relayed = self.post_to_channels('', sticker=sticker, exclude_chat_id=chat_id)
                self._log_relay('channel_post', str(chat_id), preview, users_relayed, channels_relayed)
                return True

            elif 'animation' in message:
                anim = message['animation']['file_id']
                caption = message.get('caption', '')
                preview = '[GIF] ' + caption[:80]
                if relay_to_users:
                    s, _ = self.broadcast_to_all_users(relay_header + caption)
                    users_relayed = s
                if relay_to_channels:
                    channels_relayed = self.post_to_channels(relay_header + caption, video=anim, exclude_chat_id=chat_id)
                self._log_relay('channel_post', str(chat_id), preview, users_relayed, channels_relayed)
                return True

            elif 'voice' in message:
                voice = message['voice']['file_id']
                preview = self.tr('a0103_رسالة_صوتية', 'ar')
                if relay_to_users:
                    s, _ = self.broadcast_to_all_users(relay_header + self.tr('a0104_رسالة_صوتية', 'ar'))
                    users_relayed = s
                if relay_to_channels:
                    channels_relayed = self.post_to_channels(relay_header + self.tr('a0104_رسالة_صوتية', 'ar'), document=voice, exclude_chat_id=chat_id)
                self._log_relay('channel_post', str(chat_id), preview, users_relayed, channels_relayed)
                return True

            elif 'audio' in message:
                audio = message['audio']['file_id']
                caption = message.get('caption', '')
                preview = self.tr('a0105_صوت', 'ar') + caption[:80]
                if relay_to_users:
                    s, _ = self.broadcast_to_all_users(relay_header + caption)
                    users_relayed = s
                if relay_to_channels:
                    channels_relayed = self.post_to_channels(relay_header + caption, document=audio, exclude_chat_id=chat_id)
                self._log_relay('channel_post', str(chat_id), preview, users_relayed, channels_relayed)
                return True

        except Exception as e:
            logger.error(f"خطأ في إعادة نشر البوست: {e}")
        return False

    def show_source_channels_admin(self, message):
        """لوحة القنوات المصدرية — قنوات البوت مشترك فيها"""
        sources = []
        try:
            with open('source_channels.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                sources = list(reader)
        except:
            pass

        text = (
            f"📥 <b>القنوات المصدرية</b>\n\n"
            f"📊 المسجلة: <code>{len(sources)}</code>\n"
            f"✅ النشطة: <code>{sum(1 for s in sources if s.get('is_active') == 'yes')}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
        )

        if sources:
            for s in sources[:10]:
                status = '✅' if s.get('is_active') == 'yes' else '⏸️'
                brand = s.get('brand_voice', '')[:30] if s.get('brand_voice') else '—'
                text += f"{status} <b>{s.get('title', '')}</b>\n"
                text += f"  🆔 <code>{s.get('chat_id', '')}</code>\n"
                text += self.tr('a0106_البراند', 'ar', brand=brand)
                text += f"  📅 آخر نسخ: {s.get('last_scraped_at', '—')}\n\n"
        else:
            text += self.tr('a0107_لا_توجد', 'ar')

        text += (
            "💡 <b>كيف تعمل:</b>\n"
            "1. أضف البوت كمشترك في قناة (ليس أدمن)\n"
            "2. البوت يتلقى البوستات\n"
            "3. AI يكيّف المحتوى على البراند\n"
            "4. يُنشر في القنوات المستهدفة + كل المستخدمين\n"
        )

        inline_btns = [
            [{'text': '➕ إضافة قناة مصدرية', 'callback_data': 'src_add'}],
            [{'text': '🔙 رجوع', 'callback_data': 'ch_back_admin'}]
        ]
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_sticker_library(self, message):
        """لوحة مكتبة الرموز والاستيكرات — محسّنة"""
        user_id = message['from']['id']
        admin_obj = self.find_user(user_id)
        lang = admin_obj.get('language', 'ar') if admin_obj else 'ar'

        stickers = []
        try:
            with open('sticker_library.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                stickers = list(reader)
        except:
            pass

        emojis = [s for s in stickers if s.get('type') == 'emoji']
        stickers_only = [s for s in stickers if s.get('type') == 'sticker']
        photos = [s for s in stickers if s.get('type') == 'photo']

        text = self.ui_card_pro('مكتبة الرموز', '🗃️', items=[
            {'label': 'إيموجي', 'value': str(len(emojis)), 'icon': '😀', 'highlight': True},
            {'label': 'استيكرات', 'value': str(len(stickers_only)), 'icon': '🎨', 'highlight': True},
            {'label': 'صور مخصصة', 'value': str(len(photos)), 'icon': '🖼️', 'highlight': True},
            {'label': 'الإجمالي', 'value': str(len(stickers)), 'icon': '📦'},
        ])
        text += "\n💡 <b>كيفية الاستخدام:</b>\n"
        text += "• ➕ <b>إضافة إيموجي</b> — اكتب أو الصق إيموجي\n"
        text += "• 📸 <b>رفع صورة</b> — أرسل صورة تتحول لأيقونة\n"
        text += "• 🎨 <b>استيكر جاهز</b> — أرسل استيكر يُضاف مباشرة\n"
        text += "• 🗑️ <b>حذف</b> — اختر أي عنصر واحذفه\n"

        # بناء شبكة الإيموجي من المكتبة (آخر 30)
        inline_btns = []
        if emojis:
            text += self.ui_card_section('آخر الإيموجي المضافة', '✨', color='blue')
            # شبكة 5 أعمدة
            recent_emojis = emojis[-30:]
            for i in range(0, len(recent_emojis), 5):
                row = []
                for j in range(5):
                    if i + j < len(recent_emojis):
                        em = recent_emojis[i + j].get('emoji', '❓').strip()
                        sid = recent_emojis[i + j].get('id', '')
                        if em:
                            row.append({'text': em, 'callback_data': f'stk_del_{sid}'})
                if row:
                    inline_btns.append(row)

        inline_btns.append([{'text': '➕ إضافة إيموجي', 'callback_data': 'stk_add_emoji'}])
        inline_btns.append([{'text': '📸 رفع صورة كأيقونة', 'callback_data': 'stk_add_photo'},
                            {'text': '🎨 إضافة استيكر', 'callback_data': 'stk_add_sticker'}])
        inline_btns.append([{'text': '📋 عرض الكل', 'callback_data': 'stk_list'},
                            {'text': '🔙 العودة', 'callback_data': 'app_back_admin'}])
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_channels_admin(self, message):
        """لوحة إدارة القنوات/المجموعات — مع كل الإعدادات"""
        channels = self.get_bot_channels(active_only=False)
        text = (
            f"📢 <b>القنوات/المجموعات</b>\n\n"
            f"📊 المرتبطة: <code>{len(channels)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        inline_btns = []
        if channels:
            for ch in channels:
                status = '✅' if ch.get('is_active') == 'yes' else '⏸️'
                relay_u = '👥✅' if ch.get('relay_to_users', 'yes') == 'yes' else '👥❌'
                relay_c = '📢✅' if ch.get('relay_to_channels', 'yes') == 'yes' else '📢❌'
                fwd = ch.get('forward_mode', 'all')
                fwd_icon = {'all': '📋', 'text_only': '📝', 'media_only': '📷'}.get(fwd, '📋')
                text += (
                    f"\n{status} <b>{ch.get('title', '')}</b>\n"
                    f"  🆔 <code>{ch.get('chat_id', '')}</code> | 📎 {ch.get('type', '')}\n"
                    f"  {relay_u} للمستخدمين | {relay_c} للقنوات | {fwd_icon} {fwd}\n"
                )
                if ch.get('welcome_text'):
                    text += f"  📝 ترحيب: <i>{ch.get('welcome_text', '')[:30]}</i>\n"
                inline_btns.append([
                    {'text': f"{'✅' if ch.get('is_active') == 'yes' else '⏸️'} تفعيل",
                     'callback_data': f'ch_toggle_{ch.get("id", "")}'},
                    {'text': f"{'👥✅' if ch.get('relay_to_users', 'yes') == 'yes' else '👥❌'} مستخدمين",
                     'callback_data': f'ch_relay_u_{ch.get("id", "")}'},
                ])
                inline_btns.append([
                    {'text': f"{'📢✅' if ch.get('relay_to_channels', 'yes') == 'yes' else '📢❌'} قنوات",
                     'callback_data': f'ch_relay_c_{ch.get("id", "")}'},
                    {'text': f"{fwd_icon} محتوى",
                     'callback_data': f'ch_fwd_{ch.get("id", "")}'},
                ])
        else:
            text += self.tr('a0109_لا_توجد', 'ar')

        inline_btns.append([{'text': '🔄 تحديث', 'callback_data': 'ch_refresh'}])
        inline_btns.append([
            {'text': '🔁 استبدال نصوص', 'callback_data': 'ch_text_replacements'},
            {'text': '🤖 إعدادات AI', 'callback_data': 'ch_ai_settings'}])
        inline_btns.append([
            {'text': '📥 القنوات المصدرية', 'callback_data': 'src_channels'},
            {'text': '📊 تقرير يومي', 'callback_data': 'ch_daily_report'}])
        inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'app_back_admin'}])
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_text_replacements_admin(self, message):
        """لوحة استبدال النصوص"""
        replacements = []
        try:
            with open('text_replacements.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                replacements = list(reader)
        except:
            pass

        text = (
            f"🔁 <b>استبدال النصوص</b>\n\n"
            f"📊 القواعد النشطة: <code>{sum(1 for r in replacements if r.get('is_active') == 'yes')}</code>\n"
            f"📦 الإجمالي: <code>{len(replacements)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
        )
        if replacements:
            for r in replacements[:10]:
                status = '✅' if r.get('is_active') == 'yes' else '⏸️'
                text += f"{status} <code>{r.get('find_text', '')[:30]}</code> → <code>{r.get('replace_text', '')[:30]}</code>\n"
        else:
            text += self.tr('a0110_لا_توجد', 'ar')

        text += self.tr('a0111_أضف_قاعدة', 'ar')

        inline_btns = [
            [{'text': '➕ إضافة قاعدة', 'callback_data': 'tr_add'}],
            [{'text': '🔙 رجوع', 'callback_data': 'ch_back_admin'}]
        ]
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_ai_settings_admin(self, message):
        """لوحة إعدادات AI"""
        api_key = os.getenv('OPENAI_API_KEY', '')
        ai_instructions = ''
        ai_enabled_count = 0
        try:
            with open('system_settings.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('setting_key') == 'ai_instructions':
                        ai_instructions = row.get('setting_value', '')
        except:
            pass
        try:
            with open('bot_channels.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('ai_enabled') == 'yes':
                        ai_enabled_count += 1
        except:
            pass

        key_status = self.tr('a0112_مفعّل', 'ar') if api_key else self.tr('a0113_غير_مفعّل', 'ar')
        text = (
            f"🤖 <b>إعدادات الذكاء الاصطناعي</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔑 OpenAI API: <b>{key_status}</b>\n"
            f"📡 القنوات المفعّل فيها AI: <code>{ai_enabled_count}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
        )
        if ai_instructions:
            text += f"📝 <b>تعليمات AI:</b>\n<i>{ai_instructions[:200]}</i>\n\n"
        else:
            text += self.tr('a0114_لم_يتم', 'ar')

        text += (
            "💡 <b>كيف يعمل:</b>\n"
            "1. القناة تنشر بوست\n"
            "2. AI يعيد صياغته حسب تعليماتك\n"
            "3. البوست المُعالج يُنشر للمستخدمين والقنوات\n\n"
            "⚙️ للتفعيل:\n"
            "• أضف OPENAI_API_KEY في ملف .env\n"
            "• فعّل AI لقناة محددة من إعدادات القناة\n"
        )

        inline_btns = [
            [{'text': '📝 تعديل تعليمات AI', 'callback_data': 'ai_edit_instructions'}],
            [{'text': '📜 سجل البوستات', 'callback_data': 'ai_log'}],
            [{'text': '🔙 رجوع', 'callback_data': 'ch_back_admin'}]
        ]
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def log_notification(self, target_type, target_id, notif_type, message):
        """تسجيل كل إشعار في سجل الإشعارات"""
        try:
            file_exists = os.path.exists('notifications_log.csv')
            with open('notifications_log.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'target_type', 'target_id', 'type', 'message_preview'])
                preview = message[:100] + '...' if len(message) > 100 else message
                writer.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                target_type, target_id, notif_type, preview])
        except:
            pass

    def get_recent_notifications(self, limit=20):
        """الحصول على أحدث الإشعارات (للأدمن)"""
        notifications = []
        try:
            with open('notifications_log.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                all_notifs = list(reader)
                notifications = all_notifs[-limit:]
        except:
            pass
        return notifications

    def get_user_notifications(self, telegram_id, limit=10):
        """الحصول على إشعارات مستخدم محدد"""
        notifications = []
        try:
            with open('notifications_log.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['target_type'] == 'user' and row['target_id'] == str(telegram_id):
                        notifications.append(row)
        except:
            pass
        return notifications[-limit:]
    
    def _load_user_cache(self):
        """تحميل كل المستخدمين في الذاكرة مرة واحدة — O(1) lookup بدلاً من O(n) CSV scan"""
        with self._user_cache_lock:
            self._user_cache.clear()
            self._user_cache_by_phone.clear()
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    for row in csv.DictReader(f):
                        tid = row.get('telegram_id', '')
                        if tid:
                            self._user_cache[str(tid)] = row
                            phone = row.get('phone', '').replace(' ', '').replace('-', '').replace('+', '')
                            if phone:
                                self._user_cache_by_phone[phone] = row
                self._user_cache_loaded = True
                logging.info(f"User cache loaded: {len(self._user_cache)} users")
            except Exception as e:
                logging.error(f"User cache load error: {e}")
                self._user_cache_loaded = True  # تجنب إعادة المحاولة
    
    def _refresh_user_in_cache(self, telegram_id):
        """تحديث مستخدم واحد في الكاش بعد الكتابة لـ users.csv"""
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('telegram_id') == str(telegram_id):
                        with self._user_cache_lock:
                            self._user_cache[str(telegram_id)] = row
                            phone = row.get('phone', '').replace(' ', '').replace('-', '').replace('+', '')
                            if phone:
                                self._user_cache_by_phone[phone] = row
                        return row
        except:
            pass
        return None
    
    def find_user(self, telegram_id):
        """البحث عن مستخدم — O(1) من الذاكرة (بدون قراءة CSV)"""
        tid = str(telegram_id)
        with self._user_cache_lock:
            if tid in self._user_cache:
                return dict(self._user_cache[tid])  # نسخة لمنع التعديل المباشر
        # Fallback: قراءة CSV لو الكاش فارغ أو المستخدم جديد
        if not self._user_cache_loaded:
            self._load_user_cache()
            with self._user_cache_lock:
                if tid in self._user_cache:
                    return dict(self._user_cache[tid])
        return None
    
    def find_user_by_phone(self, phone):
        """البحث عن مستخدم برقم الهاتف — O(1) من الذاكرة"""
        if not phone:
            return None
        phone_normalized = phone.replace(' ', '').replace('-', '').replace('+', '')
        with self._user_cache_lock:
            if phone_normalized in self._user_cache_by_phone:
                return dict(self._user_cache_by_phone[phone_normalized])
        return None

    def detect_language_from_phone(self, phone):
        """تحديد اللغة والدولة تلقائياً من رقم الهاتف"""
        if not phone:
            return 'ar', 'SA'
        phone_clean = phone.replace(' ', '').replace('-', '').replace('+', '').replace('00', '', 1) if phone.startswith('00') else phone.replace(' ', '').replace('-', '').replace('+', '')
        
        PHONE_TO_LANG = {
            '966': ('ar', 'SA'),   # السعودية
            '971': ('ar', 'AE'),   # الإمارات
            '20':  ('ar', 'EG'),   # مصر
            '965': ('ar', 'KW'),   # الكويت
            '974': ('ar', 'QA'),   # قطر
            '973': ('ar', 'BH'),   # البحرين
            '968': ('ar', 'OM'),   # عمان
            '962': ('ar', 'JO'),   # الأردن
            '961': ('ar', 'LB'),   # لبنان
            '964': ('ar', 'IQ'),   # العراق
            '963': ('ar', 'SY'),   # سوريا
            '212': ('ar', 'MA'),   # المغرب
            '216': ('ar', 'TN'),   # تونس
            '213': ('ar', 'DZ'),   # الجزائر
            '218': ('ar', 'LY'),   # ليبيا
            '967': ('ar', 'YE'),   # اليمن
            '970': ('ar', 'PS'),   # فلسطين
            '90':  ('tr', 'TR'),   # تركيا
            '98':  ('fa', 'IR'),   # إيران
            '92':  ('ur', 'PK'),   # باكستان
            '91':  ('hi', 'IN'),   # الهند
            '62':  ('id', 'ID'),   # إندونيسيا
            '7':   ('ru', 'RU'),   # روسيا
            '86':  ('zh', 'CN'),   # الصين
            '81':  ('ja', 'JP'),   # اليابان
            '82':  ('ko', 'KR'),   # كوريا
            '66':  ('th', 'TH'),   # تايلاند
            '49':  ('de', 'DE'),   # ألمانيا
            '33':  ('fr', 'FR'),   # فرنسا
            '34':  ('es', 'ES'),   # إسبانيا
            '39':  ('it', 'IT'),   # إيطاليا
            '55':  ('pt', 'BR'),   # البرازيل
            '1':   ('en', 'US'),   # أمريكا/كندا
            '44':  ('en', 'GB'),   # بريطانيا
        }
        
        for prefix, (lang, country) in sorted(PHONE_TO_LANG.items(), key=lambda x: -len(x[0])):
            if phone_clean.startswith(prefix):
                return lang, country
        return 'ar', 'SA'  # افتراضي

    def detect_currency_from_country(self, country_code):
        """تحديد العملة من كود الدولة"""
        COUNTRY_TO_CURRENCY = {
            'SA': 'SAR', 'AE': 'AED', 'EG': 'EGP', 'KW': 'KWD', 'QA': 'QAR',
            'BH': 'BHD', 'OM': 'OMR', 'JO': 'JOD', 'LB': 'LBP', 'IQ': 'IQD',
            'SY': 'SYP', 'MA': 'MAD', 'TN': 'TND', 'DZ': 'DZD', 'LY': 'LYD',
            'YE': 'YER', 'PS': 'ILS', 'TR': 'TRY', 'IR': 'IRR', 'PK': 'PKR',
            'IN': 'INR', 'ID': 'IDR', 'RU': 'RUB', 'CN': 'CNY', 'JP': 'JPY',
            'KR': 'KRW', 'TH': 'THB', 'DE': 'EUR', 'FR': 'EUR', 'ES': 'EUR',
            'IT': 'EUR', 'BR': 'BRL', 'US': 'USD', 'GB': 'GBP',
        }
        return COUNTRY_TO_CURRENCY.get(country_code, 'EGP')
    
    def link_telegram_to_user(self, phone, new_telegram_id):
        """ربط telegram_id جديد بحساب موجود برقم الهاتف — عند إعادة التسجيل"""
        try:
            phone_normalized = phone.replace(' ', '').replace('-', '').replace('+', '')
            rows = []
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    stored_phone = row.get('phone', '').replace(' ', '').replace('-', '').replace('+', '')
                    if stored_phone and stored_phone == phone_normalized:
                        # تحديث telegram_id فقط مع الحفاظ على كل البيانات
                        row['telegram_id'] = str(new_telegram_id)
                        logger.info(f"Linked telegram_id {new_telegram_id} to existing account: {row.get('customer_id')}")
                    rows.append(row)
            
            with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
            return True
        except Exception as e:
            logger.error(f"خطأ في ربط تليجرام بالمستخدم: {e}")
            return False
    
    def get_companies(self, service_type=None):
        """جلب الشركات النشطة"""
        companies = []
        try:
            # التأكد من وجود الملف
            with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # التأكد من أن الشركة نشطة
                    if row.get('is_active', '').lower() in ['active', 'yes', '1', 'true']:
                        # فلترة حسب نوع الخدمة
                        if not service_type:
                            companies.append(row)
                        elif row['type'] == service_type or row['type'] == 'both':
                            companies.append(row)
        except FileNotFoundError:
            # إنشاء ملف الشركات إذا لم يكن موجوداً
            with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'type', 'details', 'is_active'])
        except Exception as e:
            # تسجيل الخطأ للتشخيص
            logger.error(f"خطأ في قراءة ملف الشركات: {e}")
        
        return companies
    
    def get_exchange_address(self, company_id=None):
        """جلب عنوان الصرافة — أولوية لعنوان الشركة، ثم العنوان العام"""
        # 1) محاولة جلب عنوان الشركة المحددة
        if company_id:
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('id') == str(company_id) and row.get('address', '').strip():
                            return row['address'].strip()
            except:
                pass
        # 2) العنوان العام
        try:
            with open('exchange_addresses.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['is_active'] == 'yes':
                        return row['address']
        except:
            pass
        return self.tr('a0115_العنوان_غير', 'ar')
    
    def get_setting(self, key):
        """جلب إعداد النظام"""
        try:
            with open('system_settings.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['setting_key'] == key:
                        return row['setting_value']
        except:
            pass
        return None

    def get_current_theme(self):
        """الحصول على الثيم النشط حالياً"""
        theme_name = self.get_setting('active_theme') or 'gold'
        if THEME_AVAILABLE:
            return get_theme(theme_name)
        return {}

    def get_theme_emoji(self, key):
        """الحصول على إيموجي من الثيم النشط"""
        theme = self.get_current_theme()
        return theme.get(key, '')

    def fmt_deposit_amount(self, amount, currency=''):
        """تنسيق مبلغ إيداع — أخضر + Bold + Code"""
        emoji = self.get_theme_emoji('color_deposit') or '🟢'
        cur = f' {currency}' if currency else ''
        return f"{emoji} <b><code>{amount}</code></b>{cur}"

    def fmt_withdraw_amount(self, amount, currency=''):
        """تنسيق مبلغ سحب — أحمر + Bold + Code"""
        emoji = self.get_theme_emoji('color_withdraw') or '🔴'
        cur = f' {currency}' if currency else ''
        return f"{emoji} <b><code>{amount}</code></b>{cur}"

    def fmt_success(self, text):
        """تنسيق رسالة نجاح — أخضر + Bold"""
        emoji = self.get_theme_emoji('color_success') or '🟢'
        return f"{emoji} <b>{text}</b>"

    def fmt_error(self, text):
        """تنسيق رسالة خطأ — أحمر + Bold"""
        emoji = self.get_theme_emoji('color_error') or '🔴'
        return f"{emoji} <b>{text}</b>"

    def fmt_info(self, text):
        """تنسيق رسالة معلومات — أزرق"""
        emoji = self.get_theme_emoji('color_info') or '🔵'
        return f"{emoji} {text}"

    def fmt_warning(self, text):
        """تنسيق رسالة تحذير — أصفر"""
        emoji = self.get_theme_emoji('color_warning') or '🟡'
        return f"{emoji} {text}"

    # ==================== نظام التصميم الموحد (UI Design System) ====================

    def ui_header(self, title, icon='📋'):
        """رأس البطاقة — عنوان أنيق"""
        return f"<blockquote><b>{icon} {title}</b></blockquote>"

    def ui_separator(self):
        """فاصل أنيق"""
        return f"\n<b>━━━━━━━━━━━━━━━━━━</b>\n"

    def ui_stat_row(self, label, value, icon=''):
        """صف إحصائية — تسمية + قيمة في كود"""
        if icon:
            return f"{icon} {label}: <code>{value}</code>"
        return f"📊 {label}: <code>{value}</code>"

    def ui_stat_grid(self, stats):
        """شبكة إحصائيات — صفين متوازيين"""
        lines = []
        for i in range(0, len(stats), 2):
            left = stats[i]
            right = stats[i+1] if i+1 < len(stats) else ''
            left_text = f"{left.get('icon','📊')} <b>{left.get('label','')}</b>\n<code>{left.get('value','')}</code>"
            if right:
                right_text = f"{right.get('icon','📊')} <b>{right.get('label','')}</b>\n<code>{right.get('value','')}</code>"
                lines.append(f"<code>{left_text}</code>  ┃  <code>{right_text}</code>")
            else:
                lines.append(f"<code>{left_text}</code>")
        return '\n'.join(lines)

    def ui_table(self, headers, rows):
        """جدول محاكى باستخدام Monospace — يظهر كأنه جدول حقيقي"""
        # حساب عرض كل عمود
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))

        # بناء الجدول
        def format_row(cells):
            return '│ '.join(str(c).ljust(col_widths[i]) for i, c in enumerate(cells))

        top = '┌' + '┬'.join('─' * (w + 2) for w in col_widths) + '┐'
        header_line = '│ ' + format_row(headers) + ' │'
        mid = '├' + '┼'.join('─' * (w + 2) for w in col_widths) + '┤'
        data_lines = ['│ ' + format_row(row) + ' │' for row in rows]
        bottom = '└' + '┴'.join('─' * (w + 2) for w in col_widths) + '┘'

        return '<pre>' + '\n'.join([top, header_line, mid] + data_lines + [bottom]) + '</pre>'

    def ui_card(self, title, items, icon='📋'):
        """بطاقة كاملة — رأس + فاصل + صفوف"""
        lines = [self.ui_header(title, icon)]
        for item in items:
            label = item.get('label', '')
            value = item.get('value', '')
            item_icon = item.get('icon', '•')
            if value:
                lines.append(f"{item_icon} {label}: <code>{value}</code>")
            else:
                lines.append(f"{item_icon} {label}")
        return '\n'.join(lines)

    def ui_progress_bar(self, current, total, length=20):
        """شريط تقدم أنيق"""
        if total <= 0:
            return '░' * length
        filled = int((current / total) * length)
        filled = min(filled, length)
        return '█' * filled + '░' * (length - filled)

    def ui_status_badge(self, status):
        """شارة حالة ملونة"""
        badges = {
            'pending': '🟡 معلق',
            'approved': '🟢 موافق',
            'rejected': '🔴 مرفوض',
            'active': '🟢 نشط',
            'completed': '✅ مكتمل',
            'cancelled': '❌ ملغي',
            'waiting': '⏳ بانتظار',
            'yes': '✅ نعم',
            'no': '❌ لا',
        }
        return badges.get(status, f'⬜ {status}')

    def ui_section(self, title, icon='📌'):
        """عنوان قسم"""
        return f"\n<b>{icon} {title}</b>\n<b>━━━━━━━━━━━━━━━━━━</b>\n"

    def ui_value_box(self, value, currency=''):
        """صندوق قيمة بارز"""
        if currency:
            return f"┃ 💰 <code>{value}</code> {currency} ┃"
        return f"┃ <code>{value}</code> ┃"

    def ui_two_col(self, left_label, left_value, right_label, right_value):
        """صف من عمودين متوازنين"""
        return f"│ {left_label}: <code>{left_value}</code> │ {right_label}: <code>{right_value}</code> │"

    def ui_card_pro(self, title, icon='📋', items=None, actions=None):
        """
        كرت احترافي ثنائي الألوان — تصميم عصري موحّد
        
        items: قائمة dict بـ:
          - {'label': '...', 'value': '...', 'icon': '🔧', 'highlight': True/False}
          - highlight=True → الصف يظهر بلون بارز (code block)
          - highlight=False → الصف يظهر بلون عادي (bold)
        actions: نص أزرار الإجراءات
        
        التصميم:
        ┌─ blockquote header (title)
        │  🔧 label: <code>value</code>   ← highlighted rows
        │  📌 label: value               ← normal rows
        └─ separator + actions
        """
        lines = []
        # رأس الكرت — blockquote يعطي خلفية مميزة
        lines.append(f"<blockquote><b>{icon} {title}</b></blockquote>")
        
        if items:
            for item in items:
                label = item.get('label', '')
                value = item.get('value', '')
                item_icon = item.get('icon', '•')
                highlight = item.get('highlight', False)
                
                if value:
                    if highlight:
                        # صف بارز — code block (لون مختلف)
                        lines.append(f"<code>{item_icon} {label}: {value}</code>")
                    else:
                        # صف عادي — bold (لون آخر)
                        lines.append(f"{item_icon} <b>{label}:</b> <code>{value}</code>")
                else:
                    lines.append(f"{item_icon} {label}")
        
        # فاصل
        lines.append("<b>━━━━━━━━━━━━━━━━━━</b>")
        
        if actions:
            lines.append(actions)
        
        return '\n'.join(lines)

    def ui_card_row(self, label, value, icon='•', highlight=False, lang='ar'):
        """
        صف واحد في الكرت — بلونين مختلفين حسب نوعه
        highlight=True → أزرق (code block كامل)
        highlight=False → عادي (bold label + code value)
        """
        if highlight:
            return f"<code>{icon} {label}: {value}</code>"
        else:
            return f"{icon} <b>{label}:</b> <code>{value}</code>"

    def ui_card_section(self, title, icon='📌', color='blue'):
        """
        عنوان قسم داخل الكرت — بلون مختلف حسب color
        blue → code block (أزرق في بعض الثيمات)
        red → bold (أحمر/أسود حسب الثيم)
        """
        if color == 'blue':
            return f"\n<code>{icon} {title}</code>\n<b>━━━━━━━━━━━━━━━━━━</b>\n"
        else:
            return f"\n<b>{icon} {title}</b>\n<b>━━━━━━━━━━━━━━━━━━</b>\n"

    def ui_card_alert(self, text, icon='⚠️'):
        """صف تنبيه — يظهر بلون مختلف (code block مميز)"""
        return f"<code>{icon} {text}</code>"

    def ui_card_success(self, text, icon='✅'):
        """صف نجاح — يظهر بلون بارز"""
        return f"<code>{icon} {text}</code>"

    def ui_copy_hint(self, value):
        """قيمة قابلة للنسخ مع تلميح"""
        return self.tr('a0116_اضغط_للنسخ', 'ar', value=value)

    def fmt_amount(self, amount, trans_type='deposit', currency=''):
        """تنسيق مبلغ حسب نوع المعاملة"""
        if trans_type == 'deposit':
            return self.fmt_deposit_amount(amount, currency)
        elif trans_type == 'withdraw':
            return self.fmt_withdraw_amount(amount, currency)
        else:
            return f"<b><code>{amount}</code></b> {currency}".strip()

    def save_setting(self, key, value):
        """حفظ أو تحديث إعداد في system_settings.csv"""
        rows = []
        found = False
        try:
            with open('system_settings.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or ['setting_key', 'setting_value', 'updated_at']
                for row in reader:
                    if row.get('setting_key') == key:
                        row['setting_value'] = value
                        if 'updated_at' in row:
                            row['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                        found = True
                    rows.append(row)
        except:
            fieldnames = ['setting_key', 'setting_value', 'updated_at']

        if not found:
            rows.append({
                'setting_key': key,
                'setting_value': value,
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M')
            })

        with open('system_settings.csv', 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, '') for k in fieldnames})
    
    def main_keyboard(self, lang='ar', user_id=None):
        """القائمة الرئيسية — تصميم احترافي مع رموز مميزة"""
        t = self.get_current_theme() if THEME_AVAILABLE else {}
        
        deposit_btn = self.tr('deposit', lang)
        withdraw_btn = self.tr('withdraw', lang)
        requests_btn = self.tr('my_requests', lang)
        profile_btn = self.tr('profile', lang)
        complaint_btn = self.tr('complaint', lang)
        support_btn = self.tr('support', lang)
        currency_btn = self.tr('change_currency', lang)
        reset_btn = self.tr('reset_system', lang)
        match_btn = self.tr('match_btn', lang) if self.tr('match_btn', lang) != 'match_btn' else f"{t.get('btn_match', '🔄')} مطابقة"
        notif_btn = self.tr('notif_btn', lang) if self.tr('notif_btn', lang) != 'notif_btn' else f"{t.get('btn_notifications', '🔔')} إشعاراتي"
        ref_btn = self.tr('referral_btn', lang) if self.tr('referral_btn', lang) != 'referral_btn' else f"{t.get('btn_referral', '🎁')} اربح"
        help_btn = self.tr('help_btn_label', lang) if self.tr('help_btn_label', lang) != 'help_btn_label' else f"{t.get('btn_help', '❓')} مساعدة"
        svrp_btn = self.tr('svrp_title', lang)
        apps_btn = self.tr('apps_btn', lang) if self.tr('apps_btn', lang) != 'apps_btn' else self.tr('a0117_تطبيقات', lang)

        lang_names = self.get_language_names()
        lang_btn_text = f"{t.get('btn_language', '🌐')} {lang_names.get(lang, {}).get('native', 'Language')}"

        # تصميم منظم — اليانصيب وعجلة الحظ داخل مركز الألعاب
        more_btn = self.tr('a0238_المزيد', lang) if self.tr('a0238_المزيد', lang) != 'a0238_المزيد' else '⚙️ المزيد'
        wallet_btn = self.tr('a0237_محفظتي', lang) if self.tr('a0237_محفظتي', lang) != 'a0237_محفظتي' else '💎 محفظتي'

        keyboard = [
            [{'text': deposit_btn}, {'text': withdraw_btn}],
            [{'text': '💱 تداول USDT'}, {'text': svrp_btn}],
            [{'text': wallet_btn}, {'text': profile_btn}],
            [{'text': match_btn}, {'text': '🎮 ألعاب'}],
            [{'text': apps_btn}, {'text': ref_btn}],
            [{'text': notif_btn}, {'text': complaint_btn}],
            [{'text': more_btn}, {'text': lang_btn_text}],
            [{'text': reset_btn}],
        ]
        
        # زر التسجيل للمستخدمين غير المسجلين
        if user_id and not self.find_user(user_id):
            register_btn = self.tr('register_account', lang)
            keyboard.insert(0, [{'text': register_btn}])
        
        # زر الأدمن مخفي في الأسفل (لا يظهر للعملاء العاديين)
        if user_id and self.is_admin(user_id):
            keyboard.append([{'text': self.tr('admin_panel_btn', lang) if self.tr('admin_panel_btn', lang) != 'admin_panel_btn' else '🔧 Admin'}])
        
        return {
            'keyboard': keyboard,
            'resize_keyboard': True
        }
    
    
    def admin_keyboard(self, lang=None):
        """لوحة أدمن أنيقة — أزرار منظمة في مجموعات منطقية، مترجمة"""
        # اكتشاف لغة الأدمن تلقائياً إن لم تُمرر
        if lang is None or lang == 'admin_lang':
            admin_uid = getattr(self, 'current_admin_id', None)
            if admin_uid:
                admin_user = self.find_user(admin_uid)
                lang = admin_user.get('language', 'ar') if admin_user else 'ar'
            else:
                lang = 'ar'
        base_keyboard = [
            # المجموعة 1: المعاملات
            [{'text': self.tr('admin_pending_requests', lang)}, {'text': self.tr('admin_approved_requests', lang)}],
            # المجموعة 2: المستخدمين
            [{'text': self.tr('admin_users', lang)}, {'text': self.tr('admin_search', lang)}],
            # المجموعة 3: الشركات ووسائل الدفع
            [{'text': self.tr('admin_companies', lang)}, {'text': self.tr('admin_payment_methods', lang)}],
            # المجموعة 4: الإحصائيات والتقارير
            [{'text': self.tr('admin_statistics', lang)}, {'text': self.tr('admin_excel_report', lang)}],
            # المجموعة 5: التواصل
            [{'text': self.tr('admin_broadcast', lang)}, {'text': self.tr('admin_message_user', lang)}],
            # المجموعة 6: الشكاوى والدعم
            [{'text': self.tr('admin_complaints', lang)}, {'text': self.tr('admin_support_data', lang)}],
            # المجموعة 7: الإعدادات والثيمات
            [{'text': self.tr('admin_settings', lang)}, {'text': self.tr('admin_themes', lang)}, {'text': self.tr('admin_addresses', lang)}],
            # المجموعة 7b: التطبيقات والاسترداد والتداول
            [{'text': self.tr('admin_apps', lang)}, {'text': self.tr('admin_recovery', lang)}, {'text': '💱 تداول'}],
            # المجموعة 7c: الطلبات الموحدة + روابط الإحالة + أرباح الإحالة + اليانصيب + عجلة الحظ
            [{'text': '📋 كل الطلبات'}, {'text': '🎁 روابط الإحالة'}],
            [{'text': '🏆 أرباح الإحالة'}, {'text': '🎰 اليانصيب'}],
            [{'text': '🎡 عجلة الحظ'}, {'text': '📢 القنوات'}],
            # المجموعة 7d: المطابقات
            [{'text': '🔄 المطابقات'}],
            # المجموعة 8: الأدمن والأدوار
            [{'text': self.tr('admin_managers', lang)}, {'text': self.tr('admin_buttons', lang)}],
            # المجموعة 9: الحماية والنسخ
            [{'text': self.tr('admin_notifications', lang)}, {'text': self.tr('admin_backup', lang)}],
            # المجموعة 9b: مكتبة الرموز
            [{'text': '🗃️ مكتبة الرموز'}],
            # المجموعة 10: إجراءات المستخدم
            [{'text': self.tr('admin_ban_user', lang)}, {'text': self.tr('admin_unban_user', lang)}],
            # المجموعة 11: اللغة + البوتات + إعادة تعيين
            [{'text': self.tr('admin_change_language', lang)}, {'text': self.tr('admin_reset_system', lang)}],
            [{'text': self.tr('admin_main_menu', lang)}],
        ]

        # زر 🤖 البوتات يظهر فقط للبوت الرئيسي (الذي يملك صلاحية الإدارة)
        if getattr(self, 'can_manage_bots', False) and MULTI_BOT_AVAILABLE:
            base_keyboard.insert(-1, [{'text': '🤖 البوتات'}])

        current_admin_id = getattr(self, 'current_admin_id', None)
        if not current_admin_id:
            return {
                'keyboard': base_keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': False
            }

        # فلترة الأزرار حسب صلاحيات الأدمن
        filtered_keyboard = []
        for row in base_keyboard:
            new_row = []
            for btn in row:
                label = btn.get('text')
                if self.admin_has_button_permission(current_admin_id, label):
                    new_row.append(btn)
            if new_row:
                filtered_keyboard.append(new_row)

        if not filtered_keyboard:
            filtered_keyboard = base_keyboard

        return {
            'keyboard': filtered_keyboard,
            'resize_keyboard': True,
            'one_time_keyboard': False
        }

    def companies_keyboard(self, service_type):
        """لوحة اختيار الشركات مع أيقونات ذكية"""
        companies = self.get_companies(service_type)
        keyboard = []
        
        for company in companies:
            icon = self.get_company_icon(
                company.get('name', ''),
                company.get('icon', ''),
                company.get('id', '')
            )
            keyboard.append([{'text': f"{icon} {company['name']}"}])
        
        keyboard.append([{'text': '🔙'}])
        
        return {'keyboard': keyboard, 'resize_keyboard': True, 'one_time_keyboard': True}
    
    def get_live_stats(self):
        """إحصائيات حية — مشاركين اليانصيب + عجلة الحظ + الفائزين + الجوائز الموزعة"""
        stats = {
            'lottery_participants': 0,
            'lottery_winners_count': 0,
            'lottery_prize_pool': 0.0,
            'lottery_currency': '',
            'wheel_participants': 0,
            'total_distributed': 0.0,
            'distributed_currency': ''
        }

        # عد مشاركين اليانصيب (تذاكر موثقة في الجولة النشطة)
        try:
            active_lot_id = ''
            with open('lottery_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'active':
                        active_lot_id = row.get('id', '')
                        stats['lottery_currency'] = row.get('currency', '')
                        stats['lottery_winners_count'] = int(row.get('winner_count', 1))
                        break

            if active_lot_id:
                with open('lottery_tickets.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('round_id') == active_lot_id and row.get('payment_verified') == 'yes':
                            stats['lottery_participants'] += 1
        except:
            pass

        # عد مشاركين عجلة الحظ (في الجولة النشطة)
        try:
            active_wheel_id = ''
            with open('wheel_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'active':
                        active_wheel_id = row.get('id', '')
                        break

            if active_wheel_id:
                seen_users = set()
                with open('wheel_spins.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('round_id') == active_wheel_id:
                            seen_users.add(row.get('user_id', ''))
                stats['wheel_participants'] = len(seen_users)
        except:
            pass

        # إجمالي الجوائز الموزعة (من lottery_winners + wheel_spins)
        try:
            with open('lottery_winners.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        stats['total_distributed'] += float(row.get('prize_amount', 0))
                        if not stats['distributed_currency']:
                            stats['distributed_currency'] = row.get('currency', '')
                    except:
                        pass
        except:
            pass

        return stats

    def format_stats_bar(self):
        """شريط إحصائيات مختصر — يظهر أعلى البوت"""
        s = self.get_live_stats()
        parts = []

        if s['lottery_participants'] > 0 or s['lottery_winners_count'] > 0:
            parts.append(self.tr('a0118_مشارك', 'ar', s_lottery_participants=s['lottery_participants']))
            if s['lottery_winners_count'] > 0:
                parts.append(self.tr('a0119_فائزين', 'ar', s_lottery_winners_count=s['lottery_winners_count']))

        if s['wheel_participants'] > 0:
            parts.append(self.tr('a0120_لاعب', 'ar', s_wheel_participants=s['wheel_participants']))

        if s['total_distributed'] > 0:
            cur = s['distributed_currency'] or 'SAR'
            parts.append(self.tr('a0121_موزّعة', 'ar', s_total_distributed=s['total_distributed'], cur=cur))

        if not parts:
            return ''

        return f"📊 {' | '.join(parts)}"

    def send_welcome(self, chat_id, lang, user_id=None):
        """إرسال رسالة الترحيب مع شريط الإحصائيات الحية"""
        user = self.find_user(user_id) if user_id else None
        name = user.get('name', '') if user else ''
        customer_id = user.get('customer_id', '') if user else ''
        stats_bar = self.format_stats_bar()

        if lang == 'ar':
            text = (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👋 <b>أهلاً وسهلاً، {name}!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 رقم العميل: <b><code>{customer_id}</code></b>\n"
            )
            if stats_bar:
                text += f"\n{stats_bar}\n"
            text += (
                f"\n━━━━━━━━━━━━━━━━━━\n"
                f"👇 <b>اختر ما تريد من الأزرار بالأسفل</b>"
            )
        else:
            text = self.tr('choose_service', lang, name=name, customer_id=customer_id)
            if stats_bar:
                text = f"{stats_bar}\n\n" + text

        self.send_message(chat_id, text, self.main_keyboard(lang, user_id))

    def handle_start(self, message, ref_code=None):
        """معالج بداية المحادثة — اختيار اللغة أولاً ثم رقم الهاتف"""
        chat_id = message['chat']['id']
        user_id = message['from']['id']

        # ── Web auth: generate 6-digit code for website login ──
        if ref_code == 'web_auth':
            user = self.find_user(user_id)
            if not user:
                self.send_message(chat_id, "🔒 يجب التسجيل أولاً في البوت قبل الدخول للموقع.\n\nأرسل /start للتسجيل.")
                return
            import random as _r, time as _t, json as _json
            code = str(_r.randint(100000, 999999))
            name = user.get('name', '')
            auth_file = 'web_auth_codes.json'
            try:
                if os.path.exists(auth_file):
                    with open(auth_file, 'r') as f:
                        codes = _json.load(f)
                else:
                    codes = {}
                # Remove old codes for this user
                codes = {k: v for k, v in codes.items() if k != str(user_id)}
                codes[str(user_id)] = {'code': code, 'name': name, 'created': _t.time()}
                with open(auth_file, 'w') as f:
                    _json.dump(codes, f)
            except:
                pass
            self.send_message(chat_id,
                f"🔐 <b>رمز دخول الموقع</b>\n\n"
                f"<code>{code}</code>\n\n"
                f"⏰ صالح لمدة 5 دقائق\n"
                f"🌐 أدخل الرمز في: https://vex.deals",
                parse_mode='HTML')
            return

        # فحص إذا كان المستخدم موجود بـ telegram_id
        user = self.find_user(user_id)
        
        if user:
            if user.get('is_banned') == 'yes':
                ban_reason = user.get('ban_reason', self.tr('a0122_غير_محدد', lang))
                self.send_message(chat_id, self.tr('a0123_تم_حظر', lang, ban_reason=ban_reason))
                return
            
            lang = user.get('language', 'ar')
            name = user.get('name', '')
            customer_id = user.get('customer_id', '')
            stats_bar = self.format_stats_bar()
            if lang == 'ar':
                welcome_text = self.ui_header(self.tr('a0124_أهلاً_وسهلاً،', lang, name=name), '👋')
                welcome_text += '\n'
                # بطاقة العميل
                welcome_text += self.ui_card(self.tr('a0125_بيانات_العميل', lang), [
                    {'label': 'رقم العميل', 'value': customer_id, 'icon': '🆔'},
                ], '🪪')
                if stats_bar:
                    welcome_text += f"\n\n{stats_bar}\n"
                # قائمة الخدمات
                welcome_text += self.ui_section(self.tr('a0126_الخدمات_المتاحة', lang), '⚡')
                welcome_text += (
                    "🟢 <b>إيداع</b> — أودع أموالك بسهولة\n"
                    "🔴 <b>سحب</b> — اسحب أموالك بسرعة\n"
                    "📋 <b>طلباتي</b> — تابع حالة معاملاتك\n"
                    "🔄 <b>مطابقة</b> — طابق مع عميل آخر\n"
                    "💱 <b>تداول</b> — بيع وشراء USDT\n"
                    "💎 <b>تعويض 100%</b> — رصيد تعويضي\n"
                    "🎰 <b>يانصيب</b> — جوائز كبرى\n"
                    "🎡 <b>عجلة الحظ</b> — أدر واربح\n"
                    "🎁 <b>اربح</b> — ادعُ أصدقاءك\n"
                    "📱 <b>تطبيقات</b> — تحميل التطبيقات\n"
                )
                welcome_text += self.tr('a0127_اختر_ما', lang)
            else:
                welcome_text = self.tr('choose_service', lang, name=name, customer_id=customer_id)
                if stats_bar:
                    welcome_text = f"{stats_bar}\n\n" + welcome_text
            self.send_message(chat_id, welcome_text, self.main_keyboard(lang, user_id))
        else:
            # تخزين كود الإحالة مؤقتاً
            if ref_code and self.svrp:
                self._pending_referral = getattr(self, '_pending_referral', {})
                self._pending_referral[user_id] = ref_code

            # المستخدم الجديد: اختيار اللغة أولاً
            lang_names = self.get_language_names()
            lang_codes = list(lang_names.keys())

            welcome_text = (
                "👋 مرحباً بك في منصتنا المالية!\n\n"
                "🌍 Please choose your language / اختر لغتك:\n"
                "👇 اختر من القائمة أدناه"
            )

            keyboard = []
            for i in range(0, len(lang_codes), 3):
                row = []
                for j in range(3):
                    if i + j < len(lang_codes):
                        code = lang_codes[i + j]
                        info = lang_names[code]
                        row.append({'text': f"{info['flag']} {info['native']}"})
                keyboard.append(row)

            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            self.user_states[user_id] = 'choosing_start_language'
            self.send_message(chat_id, welcome_text, reply_keyboard)
    
    def handle_registration(self, message):
        """معالجة التسجيل"""
        user_id = message['from']['id']
        state = self.user_states.get(user_id)
        
        # فحص الحالة الجديدة: registering_name_{lang}_{phone}
        pre_lang = None
        pre_phone = None
        if isinstance(state, str) and state.startswith('registering_name_') and state != 'registering_name':
            parts = state.replace('registering_name_', '', 1).split('_', 1)
            if len(parts) == 2:
                pre_lang, pre_phone = parts[0], parts[1]
            state = 'registering_name'
        
        if state == 'registering_name':
            name = self.sanitize_input(message['text'])
            
            # التحقق من أزرار الإدارة
            skip_texts = {self.tr('skip_registration', l) for l in self.get_supported_languages()}
            if name in skip_texts:
                # إنهاء حالة التسجيل والانتقال للقائمة الرئيسية
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                skip_text = self.tr('a0128_تم_تخطي', 'ar')

                self.send_message(message['chat']['id'], skip_text, self.main_keyboard('ar', user_id))
                return
            elif name in {self.tr('cancel_registration', l) for l in self.get_supported_languages()}:
                # إلغاء التسجيل والعودة للقائمة الرئيسية
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                cancel_text = self.tr('a0129_تم_إلغاء', 'ar')

                self.send_message(message['chat']['id'], cancel_text, self.main_keyboard('ar', user_id))
                return
            
            if len(name) < 2:
                self.send_message(message['chat']['id'], self.tr('a0130_اسم_قصير', 'ar'))
                return
            
            # منع استخدام نصوص الأزرار كأسماء
            button_prefixes = ['📝', '🔐', '⏭️', '❌', '✅', '🔄', '🏠', '💰', '💸', '📋', '👤', '📨', '🆘', '💱', '🌐', '🎁', '❓', '🔔']
            if any(name.startswith(p) for p in button_prefixes):
                self.send_message(message['chat']['id'], 
                    self.tr('a0131_هذا_نص', 'ar'))
                return
            
            # منع الأسماء التي تحتوي على رموز فقط
            import re
            if not re.search(r'[\u0600-\u06FFa-zA-Z]', name):
                self.send_message(message['chat']['id'], 
                    self.tr('a0132_الاسم_يجب', 'ar'))
                return
            
            # إذا كان لدينا رقم هاتف مسبق (من التدفق الجديد) — انتقل مباشرة لإنشاء الحساب
            if pre_phone and pre_lang:
                # كشف الدولة/العملة من رقم الهاتف
                detected_lang, detected_country = self.detect_language_from_phone(pre_phone)
                detected_currency = self.detect_currency_from_country(detected_country)
                final_lang = pre_lang

                # إنشاء رقم عميل
                customer_id = f"C{str(int(datetime.now().timestamp()))[-6:]}"

                # حفظ المستخدم
                # حفظ المستخدم مباشرة في users.csv
                with open('users.csv', 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([str(user_id), name, pre_phone, customer_id, final_lang,
                                   datetime.now().strftime('%Y-%m-%d'), 'no', '', detected_currency])

                # معالجة كود الإحالة
                if self.svrp and hasattr(self, '_pending_referral'):
                    ref_code = self._pending_referral.pop(user_id, None)
                    if ref_code:
                        try:
                            self.svrp.process_referral_code(ref_code, user_id)
                        except Exception as e:
                            logger.error(f"خطأ في معالجة كود الإحالة: {e}")

                lang_names = self.get_language_names()
                lang_display = lang_names.get(final_lang, {}).get('native', final_lang)

                welcome_text = (
                    f"✅ {self.tr('registration_success', final_lang, name=name, phone=pre_phone, customer_id=customer_id, date=datetime.now().strftime('%Y-%m-%d'))}\n\n"
                    f"🌐 {lang_display}\n"
                    f"🌍 {detected_country}\n"
                    f"💱 {detected_currency}"
                )
                self.send_message(message['chat']['id'], welcome_text, self.main_keyboard(final_lang, user_id))
                if user_id in self.user_states:
                    del self.user_states[user_id]

                # إشعار الأدمن بعضو جديد
                admin_msg = self.tr('a0133_عضو_جديد', 'ar', name=name, pre_phone=pre_phone, customer_id=customer_id, final_lang=final_lang, detected_country=detected_country)
                self.notify_admins(admin_msg, notification_type='new_user')
                return

            self.user_states[user_id] = f'registering_phone_{name}'
            
            # كيبورد مشاركة جهة الاتصال
            share_phone_btn = self.tr('share_phone', 'ar')
            manual_btn = self.tr('enter_phone_manual', 'ar')
            reset_btn = self.tr('reset_system', 'ar')
            contact_keyboard = {
                'keyboard': [
                    [{'text': share_phone_btn, 'request_contact': True}],
                    [{'text': manual_btn}],
                    [{'text': reset_btn}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            phone_message = self.tr('enter_phone_prompt', 'ar')
            
            self.send_message(message['chat']['id'], phone_message, contact_keyboard)
            
        elif state.startswith('registering_phone_'):
            name = state.replace('registering_phone_', '')
            phone_verified = 'no'

            # التحقق من نوع الرسالة
            if 'contact' in message:
                # مشاركة جهة الاتصال — هاتف حقيقي
                phone = message['contact']['phone_number']
                if not phone.startswith('+'):
                    phone = '+' + phone
                phone_verified = 'yes'
            elif 'text' in message:
                text = message['text'].strip()
                
                if text in {self.tr('enter_phone_manual', l) for l in self.get_supported_languages()}:
                    manual_text = self.tr('a0134_اكتب_رقم', 'ar')
                    self.send_message(message['chat']['id'], manual_text)
                    return
                
                phone = text
                # منع استخدام نصوص الأزرار كأرقام هاتف
                if not self.validate_phone_number(phone):
                    self.send_message(message['chat']['id'], 
                        self.tr('a0135_رقم_هاتف', 'ar'))
                    return
            else:
                self.send_message(message['chat']['id'], self.tr('a0136_يرجى_مشاركة', 'ar'))
                return
            
            # إنشاء رقم عميل تلقائي
            customer_id = f"C{str(int(datetime.now().timestamp()))[-6:]}"
            
            # التحقق من وجود حساب سابق بنفس رقم الهاتف
            existing_user = self.find_user_by_phone(phone)
            if existing_user:
                # حساب موجود! ربط الـ telegram_id الجديد بالحساب القديم
                self.link_telegram_to_user(phone, user_id)
                # جلب البيانات المحدثة
                user = self.find_user(user_id)
                lang = user.get('language', 'ar')
                
                welcome_text = (
                    f"✅ تم استرجاع حسابك بنجاح!\n\n"
                    f"👤 الاسم: {user['name']}\n"
                    f"📱 الهاتف: {user['phone']}\n"
                    f"🆔 رقم العميل: {user['customer_id']}\n"
                    f"📅 تاريخ التسجيل: {user.get('date', '')}\n\n"
                    f"💡 تم ربط حسابك بهذا الجهاز. جميع بياناتك محفوظة."
                )
                self.send_message(message['chat']['id'], welcome_text, self.main_keyboard(lang, user_id))
                del self.user_states[user_id]
                return
            
            # حفظ مستخدم جديد — مع تحديد اللغة والدولة والعملة تلقائياً من رقم الهاتف
            detected_lang, detected_country = self.detect_language_from_phone(phone)
            detected_currency = self.detect_currency_from_country(detected_country)

            with open('users.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([user_id, name, phone, customer_id, detected_lang,
                               datetime.now().strftime('%Y-%m-%d'), 'no', '', detected_currency,
                               phone_verified, '0'])
            
            lang_names = self.get_language_names()
            lang_display = lang_names.get(detected_lang, {}).get('native', detected_lang)
            
            welcome_text = f"""✅ تم التسجيل بنجاح!

👤 الاسم: {name}
📱 الهاتف: {phone}
🆔 رقم العميل: {customer_id}
📅 تاريخ التسجيل: {datetime.now().strftime('%Y-%m-%d')}
🌐 اللغة: {lang_display}
🌍 الدولة: {detected_country}
💱 العملة: {detected_currency}

💡 تم تحديد اللغة والعملة تلقائياً من رقم هاتفك.
يمكنك تغييرها لاحقاً من الإعدادات.

يمكنك الآن استخدام جميع الخدمات المالية:"""
            
            self.send_message(message['chat']['id'], welcome_text, self.main_keyboard(detected_lang, user_id))
            del self.user_states[user_id]
            
            # 💎 تعويض 100%: معالجة كود الإحالة المخزن مؤقتاً
            if self.svrp and hasattr(self, '_pending_referral'):
                ref_code = self._pending_referral.pop(user_id, None)
                if ref_code:
                    try:
                        success, msg = self.svrp.process_referral_code(ref_code, user_id)
                        if success:
                            # منح ربح الإحالة للمُحيل
                            bonus_amount = float(self.get_setting('referral_bonus_amount') or '10')
                            bonus_currency = self.get_setting('referral_bonus_currency') or 'SAR'
                            # إضافة للرصيد المجمد في محفظة التعويض
                            self.svrp.add_frozen_balance(str(user_id), bonus_amount)
                            # تسجيل في سجل الإحالات
                            log_id = f"REF{str(int(datetime.now().timestamp()))[-6:]}"
                            try:
                                with open('referral_log.csv', 'a', newline='', encoding='utf-8-sig') as f:
                                    writer = csv.writer(f)
                                    writer.writerow([log_id, ref_code, str(user_id), name, phone,
                                                   phone_verified, bonus_amount, bonus_currency,
                                                   'earned', datetime.now().strftime('%Y-%m-%d %H:%M')])
                            except:
                                pass
                            self.send_message(message['chat']['id'],
                                f"🎁 تم ربطك بكود الإحالة!\nمُحيلك: <code>{ref_code}</code>\n\n"
                                f"💎 ربحت <code>{bonus_amount}</code> {bonus_currency} (مجمد)\n"
                                f"⏳ سيتم تفعيله من الإدارة")
                    except Exception as e:
                        logger.error(f"خطأ في معالجة كود الإحالة: {e}")

            # إشعار الأدمن بعضو جديد
            lang = detected_lang
            phone_status = self.tr('a0137_هاتف_حقيقي', lang) if phone_verified == 'yes' else self.tr('a0138_رقم_مكتوب', lang)
            admin_msg = f"""🆕 عضو جديد انضم للنظام

👤 الاسم: {name}
📱 الهاتف: {phone} ({phone_status})
🆔 رقم العميل: {customer_id}
🌐 اللغة: {detected_lang}
🌍 الدولة: {detected_country}
💱 العملة: {detected_currency}
📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
            self.notify_admins(admin_msg, notification_type='new_user')
    
    def process_deposit_flow(self, message):
        """معالجة تدفق الإيداع الكامل"""
        user_id = message['from']['id']
        state = self.user_states.get(user_id, '')
        text = message.get('text', '')
        
        user = self.find_user(user_id)
        lang = user.get('language', 'ar') if user else 'ar'

        # فحص أزرار الإلغاء والعودة أولاً — قبل أي معالجة للبيانات
        all_langs = self.get_supported_languages()
        cancel_texts = {self.tr('cancel_btn', l) for l in all_langs} | {self.tr('cancel_registration', l) for l in all_langs} | {self.tr('a0009_إلغاء', lang), '❌ Cancel', self.tr('a0011_الغاء', lang), self.tr('a0010_إلغاء', lang)}
        main_menu_texts = {self.tr('main_menu', l) for l in all_langs} | {self.tr('main_menu_btn', l) for l in all_langs} | {self.tr('a0083_القائمة_الرئيسية', lang), self.tr('a0141_الرئيسية', lang), '🏠 Main Menu'}
        back_texts = {self.tr('back_btn', l) for l in all_langs} | {self.tr('back_to_main', l) for l in all_langs} | {'🔙', self.tr('a0142_العودة', lang), '🔙 Back'}

        if text in cancel_texts or text in main_menu_texts or text in back_texts:
            if user_id in self.user_states:
                del self.user_states[user_id]
            user = self.find_user(user_id)
            lang = user.get('language', 'ar') if user else 'ar'
            welcome = self.tr('choose_service', lang, name=user.get('name', ''), customer_id=user.get('customer_id', '')) if user else self.tr('welcome_new', 'ar', name='')
            self.send_message(message['chat']['id'], welcome, self.main_keyboard(lang, user_id))
            return

        if state == 'selecting_deposit_company':
            # إزالة الرمز التعبيري من اسم الشركة
            selected_company_name = text
            # إزالة أيقونة الشركة من بداية النص
            for emoji in ['🏢', '🏦', '📡', '📱', '💳', '👛', '💵', '🔄', '🏷️', '⭐', '🚀', '🏬', '🌐', '🥇', '🎁']:
                if selected_company_name.startswith(emoji):
                    selected_company_name = selected_company_name[len(emoji):].strip()
                    break
            
            # البحث عن الشركة المختارة
            companies = self.get_companies('deposit')
            selected_company = None
            for company in companies:
                if company['name'] == selected_company_name:
                    selected_company = company
                    break
            
            if not selected_company:
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                # إعادة عرض قائمة الشركات بدلاً من رسالة خطأ فقط
                self.send_message(message['chat']['id'], self.tr('invalid_wallet', lang),
                    self.companies_keyboard('deposit'))
                return
            
            # عرض وسائل الدفع للشركة المختارة
            self.show_payment_method_selection(message, selected_company['id'], 'deposit')
            
        elif state.startswith('deposit_wallet_'):
            """
            معالجة خطوة إدخال رقم المحفظة للإيداع.

            صيغة الحالة السابقة تكون:
            deposit_wallet_<company_id>_<company_name>_<method_id>

            قد يحتوي اسم الشركة أو المعرف على فواصل سفلية، لذا نستخدم تقسيم ديناميكي
            بحيث يكون العنصر الأول هو company_id، والعنصر الأخير هو method_id، وما بينهما هو اسم الشركة.
            """
            # تقسيم الحالة إلى أجزاء والتقاط الشركة والمعرف بطريقة أكثر أماناً
            parts = state.split('_')
            # مثال: ['deposit', 'wallet', '1', 'STC', 'Pay', '3']
            # company_id هو الجزء الثالث
            company_id = parts[2] if len(parts) > 2 else ''
            # method_id هو الجزء الأخير
            method_id = parts[-1] if len(parts) > 3 else ''
            # اسم الشركة هو ما بين company_id و method_id
            if len(parts) > 4:
                company_name = '_'.join(parts[3:-1])
            else:
                company_name = parts[3] if len(parts) > 3 else ''

            wallet_number = self.sanitize_input(text.strip())
            user = self.find_user(user_id)
            if len(wallet_number) < 5:
                lang = user.get('language', 'ar') if user else 'ar'
                self.send_message(message['chat']['id'], self.tr('invalid_wallet', lang))
                return

            # الانتقال لمرحلة إدخال المبلغ
            user = self.find_user(user_id)
            user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
            min_deposit = self.get_setting('min_deposit') or '50'
            currency_symbol = self.get_currency_symbol(user_currency)
            lang = user.get('language', 'ar')
            amount_text = self.tr('enter_amount', lang, min=min_deposit, max=self.get_setting('max_daily_withdrawal') or '10000', currency=currency_symbol)

            # إضافة لوحة مفاتيح بها زر إلغاء
            cancel_kb = {
                'keyboard': [[{'text': '❌ إلغاء'}, {'text': '🏠 القائمة الرئيسية'}]],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            self.send_message(message['chat']['id'], amount_text, cancel_kb)
            # حفظ كل البيانات في الحالة التالية بطريقة ديناميكية لمنع مشاكل الفواصل السفلية
            self.user_states[user_id] = f'deposit_amount_{company_id}_{company_name}_{method_id}_{wallet_number}'
            
        elif state.startswith('deposit_amount_'):
            """
            معالجة خطوة إدخال مبلغ الإيداع.

            صيغة الحالة:
            deposit_amount_<company_id>_<company_name>_<method_id>_<wallet_number>

            قد تحتوي بعض العناصر على فواصل سفلية، لذا نقوم بالتقسيم ديناميكياً. الجزء الأخير هو wallet_number، الذي قبله هو method_id، وما بينهما اسم الشركة.
            """
            parts = state.split('_')
            # company_id هو الجزء الثالث
            company_id = parts[2] if len(parts) > 2 else ''
            # wallet_number هو آخر جزء
            wallet_number = parts[-1] if len(parts) > 4 else ''
            # method_id هو الجزء قبل الأخير
            method_id = parts[-2] if len(parts) > 4 else ''
            # اسم الشركة هو الأجزاء من 3 إلى قبل عنصرين من النهاية
            if len(parts) > 5:
                company_name = '_'.join(parts[3:-2])
            else:
                company_name = parts[3] if len(parts) > 3 else ''

            try:
                amount = self.validate_amount(text.strip())
                if amount is None:
                    lang = user.get('language', 'ar') if user else 'ar'
                    self.send_message(message['chat']['id'], self.tr('invalid_amount', lang))
                    return
                user = self.find_user(user_id)
                user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
                min_deposit = float(self.get_setting('min_deposit') or '50')
                lang = user.get('language', 'ar')
                
                if amount < min_deposit:
                    currency_symbol = self.get_currency_symbol(user_currency)
                    self.send_message(message['chat']['id'], self.tr('amount_too_low', lang, min=min_deposit, currency=currency_symbol))
                    return
                    
            except (ValueError, TypeError):
                lang_d = user.get('language', 'ar') if user else 'ar'
                self.send_message(message['chat']['id'], self.tr('invalid_amount', lang_d))
                return

            # الحصول على تفاصيل وسيلة الدفع (إن وجدت)
            method_name_display = ''
            if method_id:
                method = self.get_payment_method_by_id(method_id)
                if method:
                    # نضيف اسم الوسيلة ونوعها إذا كانت متاحة
                    name = method.get('method_name') or ''
                    mtype = method.get('method_type') or ''
                    method_name_display = self.tr('a0143_الوسيلة', lang, name=name, mtype=mtype)

            # إنشاء معرف المعاملة
            trans_id = f"DEP{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # حفظ المعاملة مع جميع البيانات بما في ذلك العملة
            with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    trans_id,
                    user['customer_id'],
                    user['telegram_id'],
                    user['name'],
                    'deposit',
                    company_name,
                    wallet_number,
                    amount,
                    '',  # exchange_address فارغ للإيداع
                    'pending',
                    datetime.now().strftime('%Y-%m-%d %H:%M'),
                    '',  # admin_note
                    '',  # processed_by
                    user_currency
                ])
            
            # رسالة تأكيد للعميل باستخدام الترجمة حسب اللغة
            lang = user.get('language', 'ar')
            company_icon = '🏢'
            companies_list = self.get_companies()
            for c in companies_list:
                if c['name'] == company_name:
                    company_icon = c.get('icon', '🏢') or '🏢'
                    break
            confirmation = (
                f"✅ <b>تم تقديم طلب الإيداع!</b>\n\n"
                f"🆔 رقم العملية: <code>{trans_id}</code> 👈 اضغط للنسخ\n"
                f"👤 {user['name']} — <code>{user['customer_id']}</code>\n"
                f"🏢 الشركة: {company_icon} {company_name}\n"
                f"💳 المحفظة: <code>{wallet_number}</code> 👈 اضغط للنسخ\n"
                f"💰 المبلغ: <code>{amount}</code> {user_currency}{method_name_display}\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"⏳ بانتظار مراجعة الإدارة"
            )
            
            self.send_message(message['chat']['id'], confirmation, self.main_keyboard(lang))
            # إزالة الحالة بعد إتمام العملية
            if user_id in self.user_states:
                del self.user_states[user_id]
            
            # إشعار فوري للأدمن بطلب الإيداع مع جميع البيانات
            for admin_id in self.admin_ids:
                try:
                    admin_notification = (
                        f"🔔 {self.tr('deposit_title', 'ar')}\n\n"
                        f"🆔 رقم العملية: <code>{trans_id}</code> 👈 اضغط للنسخ\n"
                        f"👤 {user['name']} — <code>{user['customer_id']}</code>\n"
                        f"🏢 {company_name}\n"
                        f"💳 المحفظة: <code>{wallet_number}</code> 👈 اضغط للنسخ\n"
                        f"💰 المبلغ: <code>{amount}</code> {user_currency}{method_name_display}\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                    )
                    # لوحة مفاتيح للتأكيد أو الرفض بنقرة واحدة
                    # أزرار inline داخل الدردشة للموافقة/الرفض
                    inline_btns = [
                        [{'text': f'✅ موافقة', 'callback_data': f'approve_{trans_id}'},
                         {'text': f'❌ رفض', 'callback_data': f'reject_{trans_id}'}],
                        [{'text': '👁️ التفاصيل', 'callback_data': f'details_{trans_id}'}]
                    ]
                    self.send_inline_message(admin_id, admin_notification, inline_btns)
                except Exception as e:
                    logger.error(f"فشل في إرسال إشعار الإدمن: {e}")
    
    def process_withdrawal_flow(self, message):
        """معالجة تدفق السحب الكامل"""
        user_id = message['from']['id']
        state = self.user_states.get(user_id, '')
        text = message.get('text', '')

        # فحص أزرار الإلغاء والعودة أولاً
        all_langs = self.get_supported_languages()
        cancel_texts = {self.tr('cancel_btn', l) for l in all_langs} | {self.tr('cancel_registration', l) for l in all_langs} | {self.tr('a0009_إلغاء', lang), '❌ Cancel', self.tr('a0011_الغاء', lang), self.tr('a0010_إلغاء', lang)}
        main_menu_texts = {self.tr('main_menu', l) for l in all_langs} | {self.tr('main_menu_btn', l) for l in all_langs} | {self.tr('a0083_القائمة_الرئيسية', lang), self.tr('a0141_الرئيسية', lang), '🏠 Main Menu'}
        back_texts = {self.tr('back_btn', l) for l in all_langs} | {self.tr('back_to_main', l) for l in all_langs} | {'🔙', self.tr('a0142_العودة', lang), '🔙 Back'}

        if text in cancel_texts or text in main_menu_texts or text in back_texts:
            if user_id in self.user_states:
                del self.user_states[user_id]
            user = self.find_user(user_id)
            lang = user.get('language', 'ar') if user else 'ar'
            welcome = self.tr('choose_service', lang, name=user.get('name', ''), customer_id=user.get('customer_id', '')) if user else self.tr('welcome_new', 'ar', name='')
            self.send_message(message['chat']['id'], welcome, self.main_keyboard(lang, user_id))
            return

        if state == 'selecting_withdraw_company':
            # إزالة الرمز التعبيري من اسم الشركة
            selected_company_name = text
            # إزالة أيقونة الشركة من بداية النص
            for emoji in ['🏢', '🏦', '📡', '📱', '💳', '👛', '💵', '🔄', '🏷️', '⭐', '🚀', '🏬', '🌐', '🥇', '🎁']:
                if selected_company_name.startswith(emoji):
                    selected_company_name = selected_company_name[len(emoji):].strip()
                    break
            
            # البحث عن الشركة المختارة
            companies = self.get_companies('withdraw')
            selected_company = None
            for company in companies:
                if company['name'] == selected_company_name:
                    selected_company = company
                    break
            
            if not selected_company:
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                self.send_message(message['chat']['id'], self.tr('invalid_wallet', lang),
                    self.companies_keyboard('withdraw'))
                return
            
            # عرض وسائل الدفع للشركة المختارة
            self.show_payment_method_selection(message, selected_company['id'], 'withdraw')

        elif isinstance(state, str) and state.startswith('wd_step_amount_'):
            # السحب خطوة 1: المبلغ
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text_msg = message.get('text', '').strip()

            if text_msg in [self.tr('a0009_إلغاء', lang), self.tr('a0010_إلغاء', lang), self.tr('a0011_الغاء', lang), '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                self.handle_start(message)
                return

            try:
                amount = float(text_msg)
                if amount <= 0:
                    self.send_message(chat_id, self.tr('a0144_المبلغ_يجب', lang))
                    return
            except ValueError:
                self.send_message(chat_id, self.tr('a0145_اكتب_مبلغاً', lang))
                return

            parts = state.replace('wd_step_amount_', '').split('_', 1)
            if len(parts) != 2:
                return
            company_id = parts[0]
            company_name = parts[1]

            kb = {'keyboard': [[{'text': '❌ إلغاء'}]], 'resize_keyboard': True, 'one_time_keyboard': True}
            self.send_message(chat_id,
                f"✅ المبلغ: <code>{amount}</code>\n\n"
                f"2️⃣ اكتب <b>رقم المحفظة</b> للاستلام:", kb)
            self.user_states[user_id] = f'wd_step_wallet_{company_id}_{company_name}_{amount}'

        elif isinstance(state, str) and state.startswith('wd_step_wallet_'):
            # السحب خطوة 2: رقم المحفظة
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text_msg = message.get('text', '').strip()

            if text_msg in [self.tr('a0009_إلغاء', lang), self.tr('a0010_إلغاء', lang), self.tr('a0011_الغاء', lang), '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                self.handle_start(message)
                return

            wallet_number = self.sanitize_input(text_msg)
            if len(wallet_number) < 5:
                self.send_message(chat_id, self.tr('a0146_رقم_المحفظة', lang))
                return

            parts = state.replace('wd_step_wallet_', '').split('_', 2)
            if len(parts) != 3:
                return
            company_id = parts[0]
            company_name = parts[1]
            amount = parts[2]

            kb = {'keyboard': [[{'text': '❌ إلغاء'}]], 'resize_keyboard': True, 'one_time_keyboard': True}
            self.send_message(chat_id,
                f"✅ المحفظة: <code>{wallet_number}</code> 👈 اضغط للنسخ\n\n"
                f"3️⃣ اكتب <b>معرف حسابك</b> (ID):", kb)
            self.user_states[user_id] = f'wd_step_account_{company_id}_{company_name}_{amount}_{wallet_number}'

        elif isinstance(state, str) and state.startswith('wd_step_account_'):
            # السحب خطوة 3: معرف الحساب
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text_msg = message.get('text', '').strip()

            if text_msg in [self.tr('a0009_إلغاء', lang), self.tr('a0010_إلغاء', lang), self.tr('a0011_الغاء', lang), '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                self.handle_start(message)
                return

            account_id = self.sanitize_input(text_msg)
            if len(account_id) < 2:
                self.send_message(chat_id, self.tr('a0147_معرف_الحساب', 'ar'))
                return

            parts = state.replace('wd_step_account_', '').split('_', 3)
            if len(parts) != 4:
                return
            company_id = parts[0]
            company_name = parts[1]
            amount = parts[2]
            wallet_number = parts[3]

            kb = {'keyboard': [[{'text': '❌ إلغاء'}]], 'resize_keyboard': True, 'one_time_keyboard': True}
            self.send_message(chat_id,
                f"✅ معرف الحساب: <code>{account_id}</code> 👈 اضغط للنسخ\n\n"
                f"4️⃣ اكتب <b>كود السحب</b>:", kb)
            self.user_states[user_id] = f'wd_step_code_{company_id}_{company_name}_{amount}_{wallet_number}_{account_id}'

        elif isinstance(state, str) and state.startswith('wd_step_code_'):
            # السحب خطوة 4: كود السحب — إنشاء المعاملة
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text_msg = message.get('text', '').strip()

            if text_msg in [self.tr('a0009_إلغاء', 'ar'), self.tr('a0010_إلغاء', 'ar'), self.tr('a0011_الغاء', 'ar'), '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                self.handle_start(message)
                return

            confirmation_code = self.sanitize_input(text_msg)
            if len(confirmation_code) < 3:
                self.send_message(chat_id, self.tr('a0148_كود_السحب', 'ar'))
                return

            parts = state.replace('wd_step_code_', '').split('_', 4)
            if len(parts) != 5:
                return
            company_id = parts[0]
            company_name = parts[1]
            amount = float(parts[2])
            wallet_number = parts[3]
            account_id = parts[4]

            user = self.find_user(user_id)
            if not user:
                self.send_message(chat_id, self.tr('a0149_يجب_التسجيل', 'ar'))
                return

            user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
            trans_id = f"WTH{datetime.now().strftime('%Y%m%d%H%M%S')}"

            with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    trans_id, user['customer_id'], user['telegram_id'], user['name'],
                    'withdraw', company_name, wallet_number, amount,
                    account_id, 'pending_code_verification',
                    datetime.now().strftime('%Y-%m-%d %H:%M'),
                    confirmation_code, '', user_currency
                ])

            lang = user.get('language', 'ar')
            self.send_message(chat_id,
                f"✅ <b>تم تقديم طلب السحب!</b>\n\n"
                f"🆔 رقم العملية: <code>{trans_id}</code> 👈 اضغط للنسخ\n"
                f"🏢 الشركة: <b>{company_name}</b>\n"
                f"💳 المحفظة: <code>{wallet_number}</code> 👈 اضغط للنسخ\n"
                f"🆔 معرف الحساب: <code>{account_id}</code> 👈 اضغط للنسخ\n"
                f"🔑 الكود: <code>{confirmation_code}</code> 👈 اضغط للنسخ\n"
                f"💰 المبلغ: <code>{amount}</code> {user_currency}\n\n"
                f"⏳ {self.tr('code_pending_verification', lang)}",
                self.main_keyboard(lang, user_id))

            for admin_id in self.admin_ids:
                try:
                    admin_msg = (
                        f"💸 <b>طلب سحب جديد</b>\n\n"
                        f"🆔 رقم العملية: <code>{trans_id}</code> 👈 اضغط للنسخ\n"
                        f"👤 {user.get('name', '')} — <code>{user.get('customer_id', '')}</code>\n"
                        f"🏢 {company_name}\n"
                        f"💳 المحفظة: <code>{wallet_number}</code> 👈 اضغط للنسخ\n"
                        f"🆔 معرف الحساب: <code>{account_id}</code> 👈 اضغط للنسخ\n"
                        f"💰 المبلغ: <code>{amount}</code> {user_currency}\n"
                        f"🔑 الكود: <code>{confirmation_code}</code> 👈 اضغط للنسخ\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                    )
                    inline_btns = [
                        [{'text': '✅ تأكيد الكود', 'callback_data': f'verify_code_{trans_id}'},
                         {'text': '❌ رفض الكود', 'callback_data': f'reject_code_{trans_id}'}]
                    ]
                    self.send_inline_message(admin_id, admin_msg, inline_btns)
                except:
                    pass

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        elif state.startswith('withdraw_wallet_'):
            """
            معالجة خطوة إدخال رقم المحفظة للسحب.
            صيغة الحالة:
            withdraw_wallet_<company_id>_<company_name>_<method_id>
            وقد يحتوي اسم الشركة أو الوسيلة على فواصل سفلية، لذا نستخدم تقسيم ديناميكي.
            """
            parts = state.split('_')
            # company_id
            company_id = parts[2] if len(parts) > 2 else ''
            # method_id في نهاية القائمة
            method_id = parts[-1] if len(parts) > 3 else ''
            # اسم الشركة: كل الأجزاء بين company_id و method_id
            if len(parts) > 4:
                company_name = '_'.join(parts[3:-1])
            else:
                company_name = parts[3] if len(parts) > 3 else ''

            wallet_number = self.sanitize_input(text.strip())
            user = self.find_user(user_id)
            if len(wallet_number) < 5:
                lang = user.get('language', 'ar') if user else 'ar'
                self.send_message(message['chat']['id'], self.tr('invalid_wallet', lang))
                return
            
            # الانتقال لمرحلة إدخال المبلغ
            user = self.find_user(user_id)
            user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
            min_withdrawal = self.get_setting('min_withdrawal') or '100'
            max_withdrawal = self.get_setting('max_daily_withdrawal') or '10000'
            currency_symbol = self.get_currency_symbol(user_currency)
            lang = user.get('language', 'ar')
            amount_text = self.tr('enter_amount', lang, min=min_withdrawal, max=max_withdrawal, currency=currency_symbol)
            
            # إضافة لوحة مفاتيح بها زر إلغاء
            cancel_kb = {
                'keyboard': [[{'text': '❌ إلغاء'}, {'text': '🏠 القائمة الرئيسية'}]],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            self.send_message(message['chat']['id'], amount_text, cancel_kb)
            # حفظ البيانات في الحالة التالية
            self.user_states[user_id] = f'withdraw_amount_{company_id}_{company_name}_{method_id}_{wallet_number}'
            
        elif state.startswith('withdraw_amount_'):
            """
            معالجة خطوة إدخال مبلغ السحب.
            صيغة الحالة:
            withdraw_amount_<company_id>_<company_name>_<method_id>_<wallet_number>
            حيث قد تحتوي اسم الشركة على فواصل سفلية، لذلك نقوم بالتقسيم ديناميكياً.
            """
            parts = state.split('_')
            company_id = parts[2] if len(parts) > 2 else ''
            wallet_number = parts[-1] if len(parts) > 4 else ''
            method_id = parts[-2] if len(parts) > 4 else ''
            if len(parts) > 5:
                company_name = '_'.join(parts[3:-2])
            else:
                company_name = parts[3] if len(parts) > 3 else ''

            try:
                amount = self.validate_amount(text.strip())
                if amount is None:
                    lang = user.get('language', 'ar') if user else 'ar'
                    self.send_message(message['chat']['id'], self.tr('invalid_amount', lang))
                    return
                user = self.find_user(user_id)
                user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
                min_withdrawal = float(self.get_setting('min_withdrawal') or '100')
                max_withdrawal = float(self.get_setting('max_daily_withdrawal') or '10000')
                lang = user.get('language', 'ar')

                if amount < min_withdrawal:
                    currency_symbol = self.get_currency_symbol(user_currency)
                    self.send_message(message['chat']['id'], self.tr('amount_too_low', lang, min=min_withdrawal, currency=currency_symbol))
                    return

                if amount > max_withdrawal:
                    currency_symbol = self.get_currency_symbol(user_currency)
                    self.send_message(message['chat']['id'], self.tr('amount_too_high', lang, max=max_withdrawal, currency=currency_symbol))
                    return

            except (ValueError, TypeError):
                lang_w = user.get('language', 'ar') if user else 'ar'
                self.send_message(message['chat']['id'], self.tr('invalid_amount', lang_w))
                return

            # عرض عنوان السحب للشركة المحددة وطلب كود التأكيد
            withdrawal_address = self.get_exchange_address(company_id)
            lang = user.get('language', 'ar')
            company = self.get_company_by_id(company_id)
            company_icon = company.get('icon', '🏢') if company else '🏢'
            confirm_text = (
                f"{company_icon} {company_name}\n\n"
                + self.tr('enter_withdrawal_address', lang, address=withdrawal_address)
            )

            cancel_kb = {
                'keyboard': [[{'text': '❌ إلغاء'}, {'text': '🏠 القائمة الرئيسية'}]],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            self.send_message(message['chat']['id'], confirm_text, cancel_kb)
            # حفظ المعلومات للتأكد لاحقاً
            self.user_states[user_id] = f'withdraw_confirmation_code_{company_id}_{company_name}_{wallet_number}_{amount}_{withdrawal_address}'
            

        elif state.startswith('withdraw_confirmation_code_'):
            """
            معالجة خطوة إدخال كود التأكيد للسحب.
            صيغة الحالة:
            withdraw_confirmation_code_<company_id>_<company_name>_<wallet_number>_<amount>_<withdrawal_address>
            حيث قد تحتوي بعض العناصر على فواصل سفلية، لذا نقوم بالتقسيم بطريقة ديناميكية:
            - العنصر الأول: company_id
            - العنصر الأخير: withdrawal_address
            - العنصر قبل الأخير: amount
            - العنصر الثاني: بداية company_name حتى العنصر قبل العنصرين الأخيرين
            """
            data_part = state.replace('withdraw_confirmation_code_', '', 1)
            parts = data_part.split('_')
            company_id = parts[0] if len(parts) > 0 else ''
            # withdrawal_address هو آخر جزء
            withdrawal_address = parts[-1] if len(parts) > 2 else ''
            # amount هو الجزء قبل الأخير
            amount = parts[-2] if len(parts) > 2 else ''
            # wallet_number هو العنصر الثالث إذا كان الطول على الأقل 4
            wallet_number = parts[2] if len(parts) > 4 else ''
            # company_name هو ما بين company_id و wallet_number
            if len(parts) > 5:
                company_name = '_'.join(parts[1:-3])
            else:
                company_name = parts[1] if len(parts) > 1 else ''

            confirmation_code = text.strip()
            if len(confirmation_code) < 3:
                lang = user.get('language', 'ar') if user else 'ar'
                self.send_message(message['chat']['id'], self.tr('invalid_code', lang))
                return

            # التأكيد النهائي مع أزرار inline للسرعة
            user = self.find_user(user_id)
            user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
            currency_symbol = self.get_currency_symbol(user_currency)
            lang = user.get('language', 'ar')
            company = self.get_company_by_id(company_id)
            company_icon = company.get('icon', '🏢') if company else '🏢'
            final_confirm_text = self.tr('final_confirmation', lang,
                company=f"{company_icon} {company_name}", wallet=wallet_number,
                amount=f"{amount} {currency_symbol}",
                address=withdrawal_address, code=confirmation_code)

            # أزرار inline للتأكيد السريع (داخل الدردشة)
            confirm_btn = self.tr('confirm_request', lang)
            cancel_btn = self.tr('cancel_request', lang)
            inline_btns = [
                [{'text': confirm_btn, 'callback_data': 'withdraw_confirm'},
                 {'text': cancel_btn, 'callback_data': 'withdraw_cancel'}],
                [{'text': self.tr('main_menu', lang), 'callback_data': 'main_menu'}]
            ]
            
            self.send_inline_message(message['chat']['id'], final_confirm_text, inline_btns)
            # حفظ البيانات مع كود التأكيد للتحقق في الخطوة النهائية
            self.user_states[user_id] = f'withdraw_final_confirm_{company_id}_{company_name}_{wallet_number}_{amount}_{withdrawal_address}_{confirmation_code}'
            
        elif state.startswith('withdraw_final_confirm_'):
            """
            معالجة الخطوة النهائية للسحب بعد التأكيد.
            الصيغة:
            withdraw_final_confirm_<company_id>_<company_name>_<wallet_number>_<amount>_<withdrawal_address>_<confirmation_code>
            وقد تحتوي بعض العناصر (كاسم الشركة) على فواصل سفلية.
            نستخدم تقسيم ديناميكي لتحديد كل عنصر:
            - company_id: أول عنصر بعد البادئة
            - confirmation_code: آخر عنصر
            - withdrawal_address: العنصر قبل الأخير
            - amount: العنصر قبل عنصرين من النهاية
            - wallet_number: العنصر بعد company_name مباشرة
            - company_name: العناصر بين company_id و wallet_number
            """
            data_part = state.replace('withdraw_final_confirm_', '', 1)
            parts = data_part.split('_')
            company_id = parts[0] if len(parts) > 0 else ''
            confirmation_code = parts[-1] if len(parts) > 4 else ''
            withdrawal_address = parts[-2] if len(parts) > 4 else ''
            amount = parts[-3] if len(parts) > 4 else ''
            # wallet_number هو العنصر بعد اسم الشركة مباشرة
            wallet_number = parts[-4] if len(parts) > 4 else ''
            # company_name: العناصر من index 1 إلى العنصر قبل wallet_number
            if len(parts) > 5:
                company_name = '_'.join(parts[1:-4])
            else:
                company_name = parts[1] if len(parts) > 1 else ''

            # معالجة الأزرار
            confirm_texts = {self.tr('confirm_request', l) for l in self.get_supported_languages()}
            cancel_texts = {self.tr('cancel_request', l) for l in self.get_supported_languages()}
            main_menu_texts = {self.tr('main_menu', l) for l in self.get_supported_languages()}
            if text in confirm_texts:
                user = self.find_user(user_id)
                trans_id = f"WTH{datetime.now().strftime('%Y%m%d%H%M%S')}"
                # العملة
                user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
                
                # حفظ المعاملة بحالة pending_code_verification — بانتظار تأكيد الكود من الأدمن
                with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        trans_id,
                        user['customer_id'],
                        user['telegram_id'],
                        user['name'],
                        'withdraw',
                        company_name,
                        wallet_number,
                        amount,
                        withdrawal_address,
                        'pending_code_verification',
                        datetime.now().strftime('%Y-%m-%d %H:%M'),
                        confirmation_code,
                        '',  # processed_by
                        user_currency
                    ])
                
                # رسالة للعميل: طلبك قيد التحقق من الكود
                lang = user.get('language', 'ar')
                pending_msg = self.tr('withdraw_success', lang,
                    trans_id=trans_id, name=user['name'], customer_id=user['customer_id'],
                    company_name=company_name, wallet_number=wallet_number,
                    amount=self.fmt_withdraw_amount(amount, user_currency),
                    withdrawal_address=withdrawal_address,
                    confirmation_code=confirmation_code,
                    date=datetime.now().strftime('%Y-%m-%d %H:%M'))
                pending_msg += f"\n\n⏳ {self.tr('code_pending_verification', lang)}"
                self.send_message(message['chat']['id'], pending_msg, self.main_keyboard(lang))
                # إزالة الحالة
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
            # إشعار الأدمن بطلب التحقق من الكود
            for admin_id in self.admin_ids:
                try:
                    admin_notification = (
                        f"🔔 {self.tr('withdraw_title', 'ar')}\n\n"
                        f"🆔 {trans_id}\n"
                        f"👤 {user['name']} ({user['customer_id']})\n"
                        f"🏢 {company_name}\n"
                        f"💳 {wallet_number}\n"
                        f"💰 {amount} {self.get_currency_symbol(user_currency)}\n"
                        f"📍 {withdrawal_address}\n"
                        f"🔐 الكود: {confirmation_code}\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                        f"⚠️ بانتظار تأكيد الكود"
                    )
                    # أزرار inline: تأكيد الكود / رفض الكود (طلب كود جديد)
                    inline_btns = [
                        [{'text': '✅ تأكيد الكود', 'callback_data': f'verify_code_{trans_id}'},
                         {'text': '🔁 طلب كود جديد', 'callback_data': f'reject_code_{trans_id}'}],
                        [{'text': '👁️ التفاصيل', 'callback_data': f'details_{trans_id}'}]
                    ]
                    self.send_inline_message(admin_id, admin_notification, inline_btns)
                except Exception as e:
                    logger.error(f"فشل في إرسال إشعار الإدمن: {e}")

            if text in cancel_texts:
                # إلغاء عملية السحب وإرسال رسالة حسب اللغة المختارة
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                cancel_text = self.tr('cancel_withdraw', lang)
                self.send_message(message['chat']['id'], cancel_text, self.main_keyboard(lang))
                if user_id in self.user_states:
                    del self.user_states[user_id]

            elif text in main_menu_texts:
                # عرض الشاشة الرئيسية (اختيار الخدمة) باستخدام الترجمة
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                # حذف الحالة الحالية إن وجدت
                if user_id in self.user_states:
                    del self.user_states[user_id]
                # بناء نص الترحيب حسب اللغة
                welcome_text = self.tr(
                    'choose_service',
                    lang,
                    name=user.get('name', self.tr('a0122_غير_محدد', lang)) if user else self.tr('a0122_غير_محدد', lang),
                    customer_id=user.get('customer_id', self.tr('a0122_غير_محدد', lang)) if user else self.tr('a0122_غير_محدد', lang)
                )
                self.send_message(message['chat']['id'], welcome_text, self.main_keyboard(lang))
            else:
                self.send_message(message['chat']['id'], self.tr('unknown_command', user.get('language', 'ar')))
            
        # (معالج قديم محذوف لأن نظام السحب تم تحديثه)
    
    def show_user_transactions(self, message):
        """عرض معاملات المستخدم"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        
        lang = user.get('language', 'ar')
        user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
        transactions_text = f"{self.tr('transactions_title', lang)}: {user['name']}\n\n"
        found_transactions = False
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['customer_id'] == user['customer_id']:
                        found_transactions = True
                        status_emoji = "⏳" if row['status'] == 'pending' else "✅" if row['status'] == 'approved' else "❌"
                        type_emoji = "💰" if row['type'] == 'deposit' else "💸"
                        
                        transactions_text += f"{status_emoji} {type_emoji} <b>{row['id']}</b>\n"
                        transactions_text += f"🏢 {row['company']}\n"
                        transactions_text += f"{self.fmt_amount(row['amount'], row['type'], user_currency)}\n"
                        transactions_text += f"📅 {row['date']}\n"
                        
                        if row['status'] == 'rejected' and row.get('admin_note'):
                            transactions_text += f"{self.fmt_error(self.tr('transactions_reason', lang) + ': ' + row['admin_note'])}\n"
                        elif row['status'] == 'approved':
                            transactions_text += f"{self.fmt_success(self.tr('transactions_approved', lang))}\n"
                        elif row['status'] == 'pending':
                            transactions_text += f"{self.fmt_warning(self.tr('transactions_pending', lang))}\n"
                        
                        transactions_text += "\n"
        except:
            pass
        
        if not found_transactions:
            transactions_text += self.tr('transactions_empty', lang)
        
        self.send_message(message['chat']['id'], transactions_text, self.main_keyboard(user.get('language', 'ar')))
    
    def show_user_profile(self, message):
        """عرض ملف المستخدم — تصميم احترافي ببطاقات"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        
        lang = user.get('language', 'ar')
        lang_names = self.get_language_names()
        lang_display = lang_names.get(lang, {}).get('native', lang)

        phone_verified = user.get('phone_verified', 'unknown')
        phone_icon = '✅' if phone_verified == 'yes' else '⚠️'

        # بطاقة البيانات الأساسية
        profile_text = self.ui_header(self.tr('a0150_الملف_الشخصي', lang), '👤')
        profile_text += '\n'
        profile_text += self.ui_card(self.tr('a0151_البيانات_الأساسية', lang), [
            {'label': 'رقم العميل', 'value': user['customer_id'], 'icon': '🆔'},
            {'label': 'الاسم', 'value': user['name'], 'icon': '📛'},
            {'label': 'الهاتف', 'value': user.get('phone', '—'), 'icon': f'📱 {phone_icon}'},
            {'label': 'تاريخ التسجيل', 'value': user.get('date', '—'), 'icon': '📅'},
            {'label': 'اللغة', 'value': lang_display, 'icon': '🌐'},
            {'label': 'العملة', 'value': user.get('currency', 'SAR'), 'icon': '💱'},
        ], '🪪')

        # بطاقة المحفظة — جدول أنيق
        if self.svrp:
            wallet = self.svrp.get_wallet(message['from']['id'])
            svrp_frozen   = float(wallet.get('balance', 0) or 0)
            svrp_available = float(wallet.get('total_used', 0) or 0)
            svrp_pending  = float(wallet.get('pending_balance', 0) or 0)
            total_earned  = float(wallet.get('total_earned', 0) or 0)
            wager_done    = int(wallet.get('wagering_completed', 0) or 0)
            wager_req     = int(wallet.get('wagering_required', 3) or 3)
            currency = user.get('currency', 'SAR')

            # رصيد اللعب (SQLite)
            game_balance = 0.0
            try:
                from game_engine import GameManager as _GM
                game_balance = float(_GM().get_balance(message['from']['id']) or 0)
            except Exception:
                pass

            profile_text += self.ui_section(self.tr('a0152_المحفظة', lang), '💳')
            # دلالات الحقول:
            #   svrp_frozen   = أرصدة SVRP (مجمدة حتى اكتمال الرهان، ثم قابلة للنقل)
            #   svrp_pending  = ينتظر إكمال الأصدقاء للرهان
            #   total_earned  = مجموع تراكمي تاريخي لكل ما اكتُسب (للعرض فقط)
            wager_status = '✅ مكتمل' if wager_done >= wager_req else f'{wager_done}/{wager_req}'
            wallet_rows = [
                ['🎮 رصيد اللعب', f'{game_balance:.2f}', currency],
                ['💎 SVRP (تعويض)', f'{svrp_frozen:.2f}', currency],
            ]
            if svrp_pending > 0:
                wallet_rows.append(['⏳ معلق (أصدقاء)', f'{svrp_pending:.2f}', currency])
            if svrp_frozen > 0:
                wallet_rows.append([f'🔓 الرهان', wager_status, ''])
            profile_text += self.ui_table(['الحالة', 'المبلغ', 'العملة'], wallet_rows)

        # بطاقة حسابات الشركات
        profile_text += self.ui_section(self.tr('a0153_حسابات_الشركات', lang), '🏢')
        try:
            accounts = self.svrp.get_user_company_accounts(message['from']['id']) if self.svrp else []
            if accounts:
                company_rows = []
                for acc in accounts:
                    company_rows.append([acc.get('company_name', ''), acc.get('account_number', '')])
                profile_text += self.ui_table([self.tr('a0154_الشركة', lang), self.tr('a0155_رقم_الحساب', lang)], company_rows)
            else:
                profile_text += self.tr('a0156_لا_توجد', lang)
        except:
            profile_text += self.tr('a0156_لا_توجد', lang)

        # أزرار inline
        inline_btns = [
            [{'text': '💎 محفظتي', 'callback_data': 'svrp_wallet'},
             {'text': '🏢 تسجيل حساب جديد', 'callback_data': 'svrp_companies'}],
            [{'text': '🔙 رجوع', 'callback_data': 'profile_back_main'}]
        ]
        self.send_inline_message(message['chat']['id'], profile_text, inline_btns)
    

    def handle_admin_panel(self, message):
        """لوحة تحكم الأدمن الرئيسية"""
        user_id = message['from']['id']
        if not self.is_admin(user_id):
            return

        admin_user = self.find_user(user_id)
        admin_lang = admin_user.get('language', 'ar') if admin_user else 'ar'

        # تحديد الأدمن الحالي لتطبيق صلاحيات الأزرار عليه
        self.current_admin_id = user_id

        # تسجيل فتح لوحة الأدمن
        try:
            self.log_admin_action(user_id, "open_admin_panel", "")
        except Exception:
            pass
        
        admin_welcome = self.tr('admin_panel', admin_lang)
        
        self.send_message(message['chat']['id'], admin_welcome, self.admin_keyboard())
    
    def show_match_admin_panel(self, message):
        """لوحة أدمن المطابقات — نشطة + معلقة + سجلات + بوتات"""
        chat_id = message['chat']['id']
        active_count = 0
        pending_count = 0
        completed_count = 0

        try:
            with open('matches.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') not in ('completed', 'cancelled'):
                        active_count += 1
                    else:
                        completed_count += 1
        except:
            pass

        try:
            with open('match_requests.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'waiting':
                        pending_count += 1
        except:
            pass

        # عد بوتات المطابقة
        match_bots = []
        if self.match_manager:
            match_bots = self.match_manager.get_match_bot_config()
        active_bots_count = sum(1 for b in match_bots if b.get('is_active') == 'yes')

        text = (
            f"🔄 <b>لوحة المطابقات</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🟢 نشطة: <b>{active_count}</b>\n"
            f"⏳ معلقة: <b>{pending_count}</b>\n"
            f"✅ مكتملة: <b>{completed_count}</b>\n"
            f"🤖 بوتات المطابقة: <b>{active_bots_count}/{len(match_bots)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

        inline_btns = [
            [{'text': '🟢 المطابقات النشطة', 'callback_data': 'match_admin_active'}],
            [{'text': '⏳ الطلبات المعلقة', 'callback_data': 'match_admin_pending'}],
            [{'text': '📜 السجلات', 'callback_data': 'match_admin_logs'}],
            [{'text': '🤖 بوتات المطابقة', 'callback_data': 'match_admin_bots'}],
            [{'text': '🔙 لوحة الأدمن', 'callback_data': 'match_back_admin'}]
        ]
        self.send_inline_message(chat_id, text, inline_btns)
    
    def run(self):
        """تشغيل البوت — نظام متوازي مع ThreadPoolExecutor (20 عامل)

        كل تحديث يُعالج في thread منفصل؛ الحلقة الرئيسية لا تنتظر أحداً.
        ميزات الأمان:
          • per-user semaphore: أقصى 2 handler متزامن لنفس المستخدم
          • sliding-window rate limit: max 10 رسائل / 10 ثواني للمستخدم
          • broadcast في thread مستقل — لا يؤثر على الحلقة أبداً
        """
        logger.info(
            "✅ DUX Bot starting (concurrent mode, 20 workers): "
            "@%s", os.getenv('BOT_TOKEN', '').split(':')[0] or 'unknown'
        )

        # ── Per-user semaphore: أقصى تزامن لنفس المستخدم ───────────────────
        _user_sems: dict = {}
        _user_sems_lock = threading.Lock()
        MAX_CONCURRENT_PER_USER = 2

        def _user_sem(uid):
            uid = str(uid)
            with _user_sems_lock:
                if uid not in _user_sems:
                    _user_sems[uid] = threading.Semaphore(MAX_CONCURRENT_PER_USER)
                return _user_sems[uid]

        # ── Processed-update dedup ring ──────────────────────────────────────
        processed_updates: set = set()
        _pu_lock = threading.Lock()

        def _mark_seen(uid):
            with _pu_lock:
                processed_updates.add(uid)
                if len(processed_updates) > 3000:
                    processed_updates.clear()

        # ── Single update handler (runs inside thread pool) ──────────────────
        def _handle_update(update):
            try:
                # ── web_app_data is nested inside 'message' ──────────────────
                if 'message' in update and 'web_app_data' in update['message']:
                    wa_msg = update['message']
                    uid = str(wa_msg.get('from', {}).get('id', ''))
                    sem = _user_sem(uid)
                    if not sem.acquire(blocking=False):
                        return
                    try:
                        wa_raw = wa_msg.get('web_app_data', {}).get('data', '')
                        logger.info("WebApp data: %.200s", wa_raw)
                        try:
                            wa_parsed = json.loads(wa_raw)
                            if 'gifts' in wa_parsed or 'score' in wa_parsed:
                                self.handle_snatch_webapp_data(wa_msg)
                            elif 'deposit' in wa_parsed or 'amount' in wa_parsed:
                                self.handle_game_deposit_request(wa_msg)
                            else:
                                self.handle_wheel_webapp_data(wa_msg)
                        except json.JSONDecodeError:
                            self.handle_wheel_webapp_data(wa_msg)
                    finally:
                        sem.release()

                elif 'message' in update:
                    message = update['message']
                    uid = str(message.get('from', {}).get('id', ''))

                    # Sliding-window rate limit
                    if not user_message_limiter.is_allowed(uid):
                        logger.warning("Rate limited (msg): %s", uid)
                        return

                    if 'text' in message:
                        logger.info("MSG %.60s from %s", message['text'], uid)

                    sem = _user_sem(uid)
                    if not sem.acquire(blocking=True, timeout=5):
                        # User has too many handlers already — skip silently
                        return
                    try:
                        self.process_message(message)
                    except Exception as exc:
                        logger.error("process_message error: %s", exc, exc_info=True)
                        try:
                            del self.user_states[uid]
                        except Exception:
                            pass
                        try:
                            u = self.find_user(uid)
                            lang = (u or {}).get('language', 'ar')
                            kb = {'keyboard': [[{'text': self.tr('reset_system', lang)}],
                                               [{'text': self.tr('main_menu', lang)}]],
                                  'resize_keyboard': True}
                            self.send_message(message['chat']['id'],
                                              self.tr('error_occurred', lang), kb)
                        except Exception:
                            pass
                    finally:
                        sem.release()

                elif 'callback_query' in update:
                    cb = update['callback_query']
                    uid = str(cb.get('from', {}).get('id', ''))

                    if not user_callback_limiter.is_allowed(uid):
                        try:
                            self.answer_callback(cb.get('id'), '⏳ انتظر قليلاً')
                        except Exception:
                            pass
                        return

                    sem = _user_sem(uid)
                    if not sem.acquire(blocking=False):
                        try:
                            self.answer_callback(cb.get('id'), '⏳')
                        except Exception:
                            pass
                        return
                    try:
                        self.handle_callback_query(cb)
                    except Exception as exc:
                        logger.error("callback error: %s", exc, exc_info=True)
                        try:
                            self.answer_callback(cb.get('id'), self.tr('a0486_خطأ', 'ar'))
                        except Exception:
                            pass
                    finally:
                        sem.release()

                elif 'my_chat_member' in update:
                    try:
                        self.handle_my_chat_member(update['my_chat_member'])
                    except Exception as exc:
                        logger.error("my_chat_member error: %s", exc, exc_info=True)

                elif 'channel_post' in update:
                    # Forward channel posts to users/channels per relay settings
                    try:
                        self.auto_relay_channel_post(update['channel_post'])
                    except Exception as exc:
                        logger.error("channel_post relay error: %s", exc, exc_info=True)

            except Exception as exc:
                logger.error("_handle_update uncaught: %s", exc, exc_info=True)

        # ── Dedicated broadcast thread — never blocks the main loop ──────────
        def _broadcast_worker():
            while True:
                try:
                    self._process_broadcast_queue()
                except Exception as exc:
                    logger.error("broadcast_worker: %s", exc)
                time.sleep(30)

        _bt = threading.Thread(target=_broadcast_worker, daemon=True, name='broadcast_worker')
        _bt.start()

        # ── Periodic stale-semaphore cleanup ─────────────────────────────────
        def _cleanup_sems():
            while True:
                time.sleep(300)
                cutoff = time.monotonic() - 300
                with _user_sems_lock:
                    stale = [k for k, s in _user_sems.items() if s._value >= MAX_CONCURRENT_PER_USER]
                    for k in stale[:200]:
                        del _user_sems[k]

        threading.Thread(target=_cleanup_sems, daemon=True, name='sem_cleanup').start()

        # ── Periodic FSM stale-state cleanup (#16) ────────────────────────────
        # Deposit/withdraw FSM states older than FSM_STALE_MINUTES are automatically
        # cleared so a user who walks away mid-flow is never permanently stuck.
        # The cleanup only touches deposit_* / withdraw_* / selecting_deposit /
        # selecting_withdraw states; it never touches game or other states.
        FSM_STALE_MINUTES = 45
        FSM_FLOW_PREFIXES = (
            'deposit_', 'withdraw_', 'selecting_deposit', 'selecting_withdraw',
        )

        def _fsm_cleanup_worker():
            import time as _t
            from datetime import datetime, timezone, timedelta
            while True:
                _t.sleep(900)  # check every 15 minutes
                try:
                    cutoff = (
                        datetime.now(timezone.utc) - timedelta(minutes=FSM_STALE_MINUTES)
                    ).isoformat()
                    rows = self._db._conn().execute(
                        "SELECT user_id, state FROM user_states WHERE updated_at < ?",
                        (cutoff,)
                    ).fetchall()
                    cleared = 0
                    for row in rows:
                        uid, state = row[0], row[1]
                        if any(state.startswith(p) for p in FSM_FLOW_PREFIXES):
                            self._db.del_user_state(uid)
                            logger.info(
                                "[fsm-cleanup] Cleared stale '%s' state for user %s "
                                "(idle >%d min)", state, uid, FSM_STALE_MINUTES)
                            cleared += 1
                    if cleared:
                        logger.info("[fsm-cleanup] Cleared %d stale FSM state(s).", cleared)
                except Exception as _fce:
                    logger.error("[fsm-cleanup] error: %s", _fce, exc_info=True)

        threading.Thread(target=_fsm_cleanup_worker, daemon=True, name='fsm-cleanup').start()

        # ── Main polling loop — submits to thread pool, never blocks ─────────
        with ThreadPoolExecutor(max_workers=20, thread_name_prefix='bot_worker') as pool:
            while True:
                try:
                    updates = self.get_updates()
                    if not updates or not updates.get('ok'):
                        time.sleep(0.3)
                        continue

                    for update in updates['result']:
                        uid = update['update_id']
                        with _pu_lock:
                            if uid in processed_updates:
                                continue
                        _mark_seen(uid)
                        self.offset = uid
                        pool.submit(_handle_update, update)

                except KeyboardInterrupt:
                    logger.info("Bot stopped by user.")
                    break
                except Exception as exc:
                    logger.error("Main loop error: %s", exc, exc_info=True)
                    time.sleep(1)

    def handle_game_deposit_request(self, message):
        """معالجة طلب إيداع سريع من الألعاب"""
        user_id = message.get('from', {}).get('id', '')
        chat_id = message.get('chat', {}).get('id', '')
        user_obj = self.find_user(user_id)
        lang = user_obj.get('language', 'ar') if user_obj else 'ar'
        user_name = user_obj.get('name', '') if user_obj else str(user_id)

        try:
            raw = message.get('web_app_data', {}).get('data', '{}')
            data = json.loads(raw)
            amount = float(data.get('amount', 0))
            account_number = data.get('account_number', '')
            method_name = data.get('method_name', '')
        except:
            return

        if amount <= 0:
            return

        # إنشاء طلب إيداع عبر game_engine
        dep_id = ''
        try:
            from game_engine import GameManager
            gm = GameManager()
            dep_id = gm.create_quick_deposit(user_id, amount, '', account_number)
        except:
            pass

        # إشعار العميل
        self.send_message(chat_id,
            f"⏳ <b>طلب إيداع سريع</b>\n\n"
            f"💰 المبلغ: <code>{amount}</code>\n"
            f"🏦 الحساب: <code>{account_number}</code>\n"
            f"🆔 الطلب: <code>{dep_id}</code>\n\n"
            f"⏳ بانتظار تأكيد الإدارة...",
            self.main_keyboard(lang, user_id))

        # إشعار الأدمن بأزرار موافقة/رفض
        for admin_id in self.admin_ids:
            try:
                self.send_inline_message(int(admin_id),
                    f"💰 <b>طلب إيداع سريع — ألعاب</b>\n\n"
                    f"👤 {user_name} (<code>{user_id}</code>)\n"
                    f"💰 المبلغ: <code>{amount}</code>\n"
                    f"🏦 الحساب: <code>{account_number}</code>\n"
                    f"📱 الوسيلة: {method_name}\n"
                    f"🆔 الطلب: <code>{dep_id}</code>\n"
                    f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    [
                        [{'text': '✅ موافقة وإضافة الرصيد', 'callback_data': f'gamedep_approve_{dep_id}'}],
                        [{'text': '❌ رفض', 'callback_data': f'gamedep_reject_{dep_id}'}]
                    ])
            except:
                pass

    def handle_snatch_webapp_data(self, message):
        """معالجة نتيجة لعبة اختطف من Web App"""
        user_id = message.get('from', {}).get('id', '')
        chat_id = message.get('chat', {}).get('id', '')
        user_obj = self.find_user(user_id)
        lang = user_obj.get('language', 'ar') if user_obj else 'ar'

        logger.info(f"Snatch WebApp data from user {user_id}")

        try:
            raw = message.get('web_app_data', {}).get('data', '{}')
            data = json.loads(raw)
            caught_gifts = data.get('gifts', [])
            score = data.get('score', 0)
            logger.info(f"Snatch results: score={score}, gifts={len(caught_gifts)}")
        except Exception as e:
            logger.error(f"Snatch data parse error: {e}")
            self.send_message(chat_id, "❌ خطأ في معالجة نتائج اللعبة", self.main_keyboard(lang, user_id))
            return

        if not caught_gifts:
            self.send_message(chat_id,
                f"😔 <b>انتهت اللعبة!</b>\n\n"
                f"لم تتمكن من اصطياد أي هدية هذه المرة\n"
                f"🍀 حظ أوفر في المرة القادمة!",
                self.main_keyboard(lang, user_id))
            return

        # قراءة الجولة النشطة
        round_id = ''
        try:
            with open('wheel_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'active':
                        round_id = row.get('id', '')
                        break
        except:
            pass

        # تسجيل كل هدية + إضافة الرصيد
        total_prize = 0.0
        processed_gifts = []
        for gift in caught_gifts:
            gift_text = gift.get('text', '')
            gift_id = gift.get('id', '')
            gift_link = gift.get('link', '')

            # تسجيل في wheel_spins.csv
            spin_id = f"SPN{str(int(datetime.now().timestamp()))[-6:]}_{gift_id[-4:]}"
            try:
                with open('wheel_spins.csv', 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([spin_id, round_id, str(user_id), gift_text, datetime.now().strftime('%Y-%m-%d %H:%M')])
            except:
                pass

            # استخراج المبلغ الرقمي وإضافته للمحفظة
            prize_amount = 0.0
            try:
                import re as _re
                numbers = _re.findall(r'[\d,.]+', gift_text.replace(',', ''))
                if numbers:
                    prize_amount = float(numbers[0])
            except:
                pass

            if prize_amount > 0 and self.svrp:
                try:
                    self.svrp.add_frozen_balance(str(user_id), prize_amount)
                    total_prize += prize_amount
                    logger.info(f"Added {prize_amount} to user {user_id} wallet")
                except Exception as e:
                    logger.error(f"Error adding frozen balance: {e}")

            processed_gifts.append({'text': gift_text, 'link': gift_link, 'amount': prize_amount})

        # التحقق من الرصيد بعد الإضافة
        wallet_balance = 0.0
        if self.svrp:
            try:
                wallet = self.svrp.get_wallet(str(user_id))
                wallet_balance = float(wallet.get('balance', 0) or 0)
            except:
                pass

        # عرض النتائج
        result_text = f"🎉🎉🎉 <b>اخترفت {score} هدية!</b> 🎉🎉🎉\n\n"
        result_text += f"━━━━━━━━━━━━━━━━━━\n"
        for i, gift in enumerate(processed_gifts, 1):
            result_text += f"{i}️⃣ 🎁 {gift['text']}\n"
            if gift['amount'] > 0:
                result_text += f"   💰 +{gift['amount']:.0f} لرصيدك\n"
        result_text += f"━━━━━━━━━━━━━━━━━━\n"
        if total_prize > 0:
            result_text += f"💎 <b>تم إضافة {total_prize:.0f} لرصيدك المجمد!</b>\n"
        result_text += f"💰 رصيدك الحالي: <code>{wallet_balance:.0f}</code>\n\n"
        result_text += f"💡 يمكنك سحب الرصيد أو استخدامه في الإيداع"

        # أزرار الاستلام
        inline_btns = []
        for gift in processed_gifts:
            if gift['link'] and gift['link'] != 'https://example.com':
                inline_btns.append([{'text': f"🔗 استلام: {gift['text'][:20]}", 'url': gift['link']}])
        inline_btns.append([{'text': '💎 محفظتي', 'callback_data': 'svrp_wallet'}])
        inline_btns.append([{'text': self.tr('a0141_الرئيسية', lang), 'callback_data': 'wheel_back_main'}])

        self.send_message(chat_id, result_text, self.main_keyboard(lang, user_id))
        if inline_btns:
            self.send_inline_message(chat_id, "🔗 استلم جوائزك:", inline_btns)

        # إشعار الأدمن
        user_name = user_obj.get('name', '') if user_obj else str(user_id)
        for admin_id in self.admin_ids:
            try:
                self.send_message(int(admin_id),
                    f"🎁 <b>اختطف — فائز!</b>\n\n"
                    f"👤 {user_name} ({user_id})\n"
                    f"🎁 اصطاد {score} هدية:\n"
                    + "\n".join([f"  • {g['text']}" for g in processed_gifts]))
            except:
                pass

    def handle_wheel_webapp_data(self, message):
        """معالجة نتيجة صيد الجوائز من Web App — اختيار الجائزة server-side لمنع الغش"""
        user_id = message.get('from', {}).get('id', '')
        chat_id = message.get('chat', {}).get('id', '')
        user_obj = self.find_user(user_id)
        lang = user_obj.get('language', 'ar') if user_obj else 'ar'

        try:
            raw = message.get('web_app_data', {}).get('data', '{}')
            data = json.loads(raw)
            round_id = data.get('round_id', '')
            # تجاهل prize من العميل — نختاره server-side
        except:
            return

        # قراءة بيانات الجولة
        round_data = None
        try:
            with open('wheel_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('id') == round_id and row.get('status') == 'active':
                        round_data = row
                        break
        except:
            pass

        if not round_data:
            self.send_message(chat_id, self.tr('a0640_الجولة_غير', lang))
            return

        # فحص حد الدورات
        my_spins = 0
        try:
            with open('wheel_spins.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('round_id') == round_id and row.get('user_id') == str(user_id):
                        my_spins += 1
        except:
            pass

        max_spins = int(round_data.get('max_spins_per_user', 1))
        spin_cost = float(round_data.get('spin_cost', 0) or 0)
        currency = round_data.get('currency', 'SAR')

        free_left = max(0, max_spins - my_spins)
        is_free = free_left > 0

        # خصم تكلفة الدورة لو مدفوعة — التحقق server-side
        if not is_free and spin_cost > 0 and self.svrp:
            wallet = None
            try:
                wallets = self.svrp.get_all_wallets()
                for w in wallets:
                    if str(w.get('telegram_id', '')) == str(user_id):
                        wallet = w
                        break
            except:
                pass

            if not wallet:
                self.send_message(chat_id, self.tr('a0641_لا_يوجد', lang))
                return

            balance = float(wallet.get('balance', 0) or 0)
            if balance < spin_cost:
                self.send_message(chat_id, self.tr('a0642_رصيدك_غير', lang, balance=balance, currency=currency, spin_cost=spin_cost))
                return

            # خصم الرصيد
            try:
                rows = []
                with open('svrp_wallets.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames
                    rows = list(reader)
                for row in rows:
                    if row.get('telegram_id') == str(user_id):
                        row['balance'] = str(balance - spin_cost)
                        break
                with open('svrp_wallets.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        writer.writerow({k: row.get(k, '') for k in fieldnames})
            except Exception as e:
                logger.error(f"خطأ في خصم رصيد العجلة: {e}")

        # ===== اختيار الجائزة server-side (منع الغش) =====
        import random
        prizes = round_data.get('prizes', '').split('|')
        prizes = [p.strip() for p in prizes if p.strip()]
        if not prizes:
            self.send_message(chat_id, self.tr('a0492_لا_توجد', lang))
            return
        prize = random.choice(prizes)

        # حفظ الدوران
        spin_id = f"SPN{str(int(datetime.now().timestamp()))[-6:]}"
        try:
            with open('wheel_spins.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([spin_id, round_id, user_id, prize, datetime.now().strftime('%Y-%m-%d %H:%M')])
        except:
            pass

        # توزيع الجائزة على المحفظة — استخراج المبلغ من النص
        prize_distributed = 0.0
        try:
            import re
            numbers = re.findall(r'[\d,.]+', prize.replace(',', ''))
            if numbers:
                prize_amount = float(numbers[0])
                if prize_amount > 0 and self.svrp:
                    self.svrp.add_frozen_balance(str(user_id), prize_amount)
                    prize_distributed = prize_amount
        except:
            pass

        # رسالة للعميل
        result_text = (
            f"🎯 <b>نتيجة صيد الجوائز!</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎁 الجائزة: <b>{prize}</b>\n"
        )
        if prize_distributed > 0:
            result_text += self.tr('a0643_تم_إضافة', lang, prize_distributed=prize_distributed, currency=currency)
        if not is_free and spin_cost > 0:
            result_text += self.tr('a0644_تم_خصم', lang, spin_cost=spin_cost, currency=currency)
        result_text += f"━━━━━━━━━━━━━━━━━━\n\n"

        free_after = max(0, max_spins - my_spins - 1)
        result_text += self.tr('a0645_دوراتك_المجانية', lang, free_after=free_after)

        self.send_message(chat_id, result_text, self.main_keyboard(lang, user_id))

        # إشعار الأدمن
        user_name = user_obj.get('name', '') if user_obj else str(user_id)
        for admin_id in self.admin_ids:
            try:
                self.send_message(int(admin_id),
                    f"🎯 <b>صيد الجوائز — نتيجة</b>\n\n"
                    f"👤 {user_name} (<code>{user_id}</code>)\n"
                    f"🎁 الجائزة: <b>{prize}</b>\n"
                    f"{'💎 مبلغ: ' + str(prize_distributed) + ' ' + currency if prize_distributed > 0 else ''}\n"
                    f"{'🎟️ مدفوعة: ' + str(spin_cost) + ' ' + currency if not is_free and spin_cost > 0 else '🆓 مجانية'}\n"
                    f"🎯 الجولة: {round_data.get('name', '')}")
            except:
                pass

        # نشر في القنوات
        try:
            self.post_to_channels(self.tr('a0646_عجلة_الحظ', lang, user_name=user_name, prize=prize))
        except:
            pass

    def handle_my_chat_member(self, update_data):
        """معالجة إضافة/إزالة البوت من القنوات/المجموعات"""
        chat = update_data.get('chat', {})
        chat_id = str(chat.get('id', ''))
        chat_title = chat.get('title', '')
        chat_type = chat.get('type', '')  # channel, group, supergroup

        old_status = update_data.get('old_chat_member', {}).get('status', '')
        new_status = update_data.get('new_chat_member', {}).get('status', '')

        # البوت أصبح مشرفاً/عضواً
        if new_status in ('member', 'administrator') and old_status not in ('member', 'administrator'):
            # تسجيل القناة تلقائياً
            self._register_channel(chat_id, chat_title, chat_type)
            logger.info(f"تم تسجيل قناة تلقائياً: {chat_title} ({chat_id})")
            # إشعار الأدمن
            for admin_id in self.admin_ids:
                try:
                    self.send_message(int(admin_id),
                        f"📢 <b>قناة جديدة مرتبطة!</b>\n\n"
                        f"📋 الاسم: <b>{chat_title}</b>\n"
                        f"🆔 <code>{chat_id}</code>\n"
                        f"📎 النوع: {chat_type}\n"
                        f"✅ تم التسجيل تلقائياً")
                except:
                    pass

        # البوت تمت إزالته
        elif new_status in ('left', 'kicked') and old_status not in ('left', 'kicked'):
            self._unregister_channel(chat_id)
            logger.info(f"تم إلغاء تسجيل قناة: {chat_title} ({chat_id})")
            for admin_id in self.admin_ids:
                try:
                    self.send_message(int(admin_id),
                        self.tr('a0647_تمت_إزالة', 'ar', chat_title=chat_title, chat_id=chat_id))
                except:
                    pass

    def _register_channel(self, chat_id, title, chat_type):
        """تسجيل قناة في bot_channels.csv"""
        # فحص عدم التكرار — في كل القنوات (ليس فقط النشطة)
        all_channels = self.get_bot_channels(active_only=False)
        for ch in all_channels:
            if ch.get('chat_id') == str(chat_id):
                # القناة موجودة — فعّلها لو كانت معطلة
                if ch.get('is_active') != 'yes':
                    self.update_channel_settings(ch.get('id'), 'is_active', 'yes')
                return  # موجودة بالفعل

        ch_id = f"CH{str(int(datetime.now().timestamp()))[-6:]}"
        try:
            # قراءة fieldnames الحالية + ترحيل
            fieldnames = ['id', 'chat_id', 'title', 'type', 'is_active', 'added_at',
                         'relay_to_users', 'relay_to_channels', 'forward_mode', 'welcome_text']
            rows = []
            need_header = True
            if os.path.exists('bot_channels.csv'):
                with open('bot_channels.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    old_fields = reader.fieldnames or fieldnames
                    rows = list(reader)
                    # ترحيل: إضافة أعمدة جديدة
                    for row in rows:
                        for col in fieldnames:
                            if col not in row:
                                row[col] = 'yes' if col in ('relay_to_users', 'relay_to_channels') else ('all' if col == 'forward_mode' else '')
                    # دمج fieldnames
                    merged = list(old_fields)
                    for col in fieldnames:
                        if col not in merged:
                            merged.append(col)
                    fieldnames = merged

            with open('bot_channels.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
                # إضافة القناة الجديدة
                writer.writerow({
                    'id': ch_id, 'chat_id': chat_id, 'title': title, 'type': chat_type,
                    'is_active': 'yes', 'added_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'relay_to_users': 'yes', 'relay_to_channels': 'yes',
                    'forward_mode': 'all', 'welcome_text': ''
                })
        except Exception as e:
            logger.error(f"خطأ في تسجيل القناة: {e}")

    def _unregister_channel(self, chat_id):
        """حذف قناة من bot_channels.csv"""
        try:
            rows = []
            fieldnames = ['id', 'chat_id', 'title', 'type', 'is_active', 'added_at',
                         'relay_to_users', 'relay_to_channels', 'forward_mode', 'welcome_text']
            if os.path.exists('bot_channels.csv'):
                with open('bot_channels.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    old_fields = reader.fieldnames or fieldnames
                    rows = [r for r in reader if r.get('chat_id') != chat_id]
                    fieldnames = old_fields
            with open('bot_channels.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
        except Exception as e:
            logger.error(f"خطأ في حذف القناة: {e}")

    def get_channel_settings(self, chat_id):
        """جلب إعدادات قناة محددة"""
        try:
            with open('bot_channels.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('chat_id') == str(chat_id):
                        return row
        except:
            pass
        return None

    def update_channel_settings(self, ch_id, key, value):
        """تحديث إعداد قناة"""
        try:
            rows = []
            fieldnames = ['id', 'chat_id', 'title', 'type', 'is_active', 'added_at',
                         'relay_to_users', 'relay_to_channels', 'forward_mode', 'welcome_text']
            with open('bot_channels.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                old_fields = reader.fieldnames or fieldnames
                rows = list(reader)
                fieldnames = old_fields
            for row in rows:
                if row.get('id') == ch_id:
                    row[key] = value
                    break
            with open('bot_channels.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث إعداد القناة: {e}")
            return False

    def _process_broadcast_queue(self):
        """معالجة طابور البث — في thread منفصل حتى لا يوقف البوت"""
        import threading as _th
        def _do_process():
            if not os.path.exists('broadcast_queue.csv'):
                return
            try:
                rows = []
                pending = []
                with open('broadcast_queue.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames or ['id', 'message', 'type', 'created_at', 'created_by', 'status']
                    for row in reader:
                        if row.get('status') == 'pending':
                            pending.append(row)
                        else:
                            rows.append(row)

                for item in pending:
                    msg = item.get('message', '')
                    target = item.get('target_chat_id', '')
                    item_id = item.get('id', '')
                    try:
                        if target:
                            # إرسال لقناة محددة — retry=1 فقط
                            self.api_call('sendMessage', {
                                'chat_id': target,
                                'text': msg,
                                'parse_mode': 'HTML'
                            }, retries=1)
                        else:
                            # بث عام — يعمل في thread منفصل داخل broadcast_to_all_users
                            self.broadcast_to_all_users(msg)
                        item['status'] = 'sent'
                    except Exception as e:
                        logger.error(f"خطأ في إرسال {item_id}: {e}")
                        item['status'] = 'failed'
                    rows.append(item)

                # كتابة مرة واحدة
                with open('broadcast_queue.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        writer.writerow({k: row.get(k, '') for k in fieldnames})
            except Exception as e:
                logger.error(f"خطأ في _process_broadcast_queue: {e}")
        # تشغيل في thread منفصل
        t = _th.Thread(target=_do_process, daemon=True)
        t.start()

    def handle_complaint_start(self, message):
        """بدء عملية الشكوى"""
        user = self.find_user(message['from']['id'])
        lang = user.get('language', 'ar') if user else 'ar'
        self.send_message(message['chat']['id'], self.tr('complaint_prompt_custom', lang))
        self.user_states[message['from']['id']] = 'writing_complaint'
    
    def show_language_selection(self, message, return_to_admin=False):
        """عرض قائمة اختيار اللغة لجميع اللغات المدعومة"""
        lang_names = self.get_language_names()
        
        lang_text = self.tr('select_language', 'ar')
        
        keyboard = []
        # ترتيب اللغات في صفوف من 3
        lang_codes = list(lang_names.keys())
        for i in range(0, len(lang_codes), 3):
            row = []
            for j in range(3):
                if i + j < len(lang_codes):
                    code = lang_codes[i + j]
                    info = lang_names[code]
                    row.append({'text': f"{info['flag']} {info['native']}"})
            keyboard.append(row)
        
        keyboard.append([{'text': self.tr('main_menu', 'ar')}])
        
        reply_keyboard = {
            'keyboard': keyboard,
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        
        # تخزين ما إذا كان الأدمن هو من طلب تغيير اللغة
        if return_to_admin:
            self.user_states[message['from']['id']] = 'selecting_language_admin'
        else:
            self.user_states[message['from']['id']] = 'selecting_language'
        self.send_message(message['chat']['id'], lang_text, reply_keyboard)
    
    def handle_language_change(self, message, text, return_to_admin=False):
        """تغيير اللغة — يدعم جميع اللغات"""
        user_id = message['from']['id']
        lang_names = self.get_language_names()
        
        # تحديد اللغة الجديدة من نص الزر
        new_lang = None
        for code, info in lang_names.items():
            if text.startswith(info['flag']):
                new_lang = code
                break
        
        if not new_lang:
            new_lang = 'ar'  # افتراضي
        
        # تحديث لغة المستخدم في الملف
        users = []
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['telegram_id'] == str(user_id):
                        row['language'] = new_lang
                    users.append(row)
            
            with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                fieldnames = ['telegram_id', 'name', 'phone', 'customer_id', 'language', 'date', 'is_banned', 'ban_reason', 'currency']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in users:
                    if 'currency' not in row or not row['currency']:
                        row['currency'] = self.get_setting('default_currency') or 'SAR'
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
            
            welcome_msg = self.tr('language_changed', new_lang)
            if return_to_admin:
                # العودة للوحة الأدمن مترجمة باللغة الجديدة
                admin_msg = self.tr('admin_panel', new_lang)
                self.send_message(message['chat']['id'], f"{welcome_msg}\n\n{admin_msg}", self.admin_keyboard(new_lang))
            else:
                self.send_message(message['chat']['id'], welcome_msg, self.main_keyboard(new_lang))
            if user_id in self.user_states:
                del self.user_states[user_id]
        except Exception as e:
            logger.error(f"خطأ في تغيير اللغة: {e}")
            self.send_message(message['chat']['id'], self.tr('a0648_حدث_خطأ', 'ar'), self.main_keyboard('ar'))
    
    def prompt_admin_search(self, message):
        """طلب البحث من الأدمن"""
        search_help = self.tr('a0649_البحث_في', 'ar')
        self.send_message(message['chat']['id'], search_help, self.admin_keyboard())
        
    def search_users_admin(self, message, query):
        """البحث في المستخدمين للأدمن"""
        try:
            results = []
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # البحث في الاسم أو رقم العميل أو الهاتف
                    if (query.lower() in row.get('name', '').lower() or 
                        query in row.get('customer_id', '') or 
                        query in row.get('phone', '')):
                        results.append(row)
            
            if not results:
                self.send_message(message['chat']['id'], self.tr('a0650_لم_يتم', 'ar', query=query), self.admin_keyboard())
                return
            
            response = self.tr('a0651_نتائج_البحث', 'ar', query=query)
            for user in results:
                ban_status = self.tr('a0652_محظور', 'ar') if user.get('is_banned') == 'yes' else self.tr('a0653_نشط', 'ar')
                response += f"👤 {user.get('name', 'غير محدد')}\n"
                response += f"🆔 {user.get('customer_id', 'غير محدد')}\n"
                response += f"📱 {user.get('phone', 'غير محدد')}\n"
                response += f"🔸 {ban_status}\n\n"
            
            if len(response) > 4000:
                response = response[:4000] + self.tr('a0654_والمزيد_من', 'ar')
            
            self.send_message(message['chat']['id'], response, self.admin_keyboard())
            
        except Exception as e:
            logger.error(f"خطأ في البحث: {e}")
            self.send_message(message['chat']['id'], self.tr('a0655_حدث_خطأ', 'ar'), self.admin_keyboard())

    def add_admin_user(self, message, user_id_to_add):
        """إضافة أدمن جديد — مع فحوصات أمنية"""
        try:
            if not user_id_to_add.isdigit():
                self.send_message(message['chat']['id'], self.tr('a0656_معرف_المستخدم', 'ar'), self.admin_keyboard())
                return

            new_admin_id = int(user_id_to_add)
            requester_id = message['from']['id']

            if new_admin_id == requester_id:
                self.send_message(message['chat']['id'], self.tr('a0657_أنت_أدمن', 'ar'), self.admin_keyboard())
                return

            if new_admin_id in self.admin_user_ids:
                self.send_message(message['chat']['id'], self.tr('a0658_المستخدم_أدمن', 'ar', user_id_to_add=user_id_to_add), self.admin_keyboard())
                return

            if new_admin_id in self.temp_admin_user_ids:
                self.send_message(message['chat']['id'], self.tr('a0659_المستخدم_مدير', 'ar', user_id_to_add=user_id_to_add), self.admin_keyboard())
                return

            self.admin_user_ids.append(new_admin_id)
            self.log_admin_action(requester_id, "add_admin", f"added admin: {user_id_to_add}")

            success_msg = self.tr('a0660_تم_إضافة', 'ar', user_id_to_add=user_id_to_add)

            self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
            logger.info(f"تم إضافة أدمن جديد: {user_id_to_add} بواسطة: {requester_id}")

        except Exception as e:
            logger.error(f"خطأ في إضافة الأدمن: {e}")
            self.send_message(message['chat']['id'], self.tr('a0661_حدث_خطأ', 'ar'), self.admin_keyboard())
    
    def prompt_add_admin(self, message):
        """طلب إضافة أدمن جديد"""
        add_admin_help = self.tr('a0662_إضافة_أدمن', 'ar')
        self.send_message(message['chat']['id'], add_admin_help, self.admin_keyboard())
    
    def show_admin_list(self, message):
        """عرض قائمة الأدمن"""
        admin_text = self.tr('a0663_قائمة_المديرين', 'ar')
        
        for i, admin_id in enumerate(self.admin_user_ids, 1):
            admin_text += f"{i}. 🆔 {admin_id}\n"
        
        admin_text += f"\n📊 العدد الإجمالي: {len(self.admin_user_ids)} مدير"
        
        self.send_message(message['chat']['id'], admin_text, self.admin_keyboard())
    
    
    def start_button_label_editor(self, message):
        """عرض قائمة بكل أزرار المشروع لتعديل مسماها"""
        chat_id = message['chat']['id']
        user_id = message['from']['id']

        all_buttons = set()

        # 1) أزرار القائمة الرئيسية (كل اللغات)
        for lang in ['ar', 'en']:
            try:
                kb = self.main_keyboard(lang).get('keyboard', [])
                for row in kb:
                    for btn in row:
                        if isinstance(btn, dict):
                            txt = btn.get('text', '').strip()
                            if txt:
                                all_buttons.add(txt)
            except:
                pass

        # 2) أزرار لوحة الأدمن
        try:
            admin_kb = self.admin_keyboard('ar').get('keyboard', [])
            for row in admin_kb:
                for btn in row:
                    if isinstance(btn, dict):
                        txt = btn.get('text', '').strip()
                        if txt:
                            all_buttons.add(txt)
        except:
            pass

        # 3) أزرار نظام التعويض (inline)
        svrp_buttons = [
            self.tr('a0664_إيداع', 'ar'), self.tr('a0665_سحب', 'ar'), self.tr('a0666_استرداد', 'ar'), self.tr('a0667_إرسال_رصيد', 'ar'),
            self.tr('a0237_محفظتي', 'ar'), self.tr('a0540_دعوة_صديق', 'ar'), self.tr('a0668_تسجيل_حساب', 'ar'), self.tr('a0083_القائمة_الرئيسية', 'ar'),
            self.tr('a0669_تسجيل_تعديل', 'ar'), self.tr('a0670_رجوع', 'ar')
        ]
        all_buttons.update(svrp_buttons)

        # 3b) أزرار التداول
        trade_buttons = [self.tr('a0234_تداول', 'ar'), self.tr('a0671_شراء', 'ar'), self.tr('a0672_بيع', 'ar'), self.tr('a0302_كل_الطلبات', 'ar')]
        all_buttons.update(trade_buttons)

        # 4) أزرار نظام التطبيقات (inline)
        app_buttons = [self.tr('a0673_إضافة_تطبيق', 'ar'), self.tr('a0281_تحديث_القائمة', 'ar'), self.tr('a0674_العودة_للوحة', 'ar')]
        all_buttons.update(app_buttons)

        # 5) أزرار نظام البوتات (inline)
        bot_buttons = [self.tr('a0675_إضافة_بوت', 'ar'), self.tr('a0281_تحديث_القائمة', 'ar'), self.tr('a0674_العودة_للوحة', 'ar')]
        all_buttons.update(bot_buttons)

        # 6) أزرار تسجيل الدخول
        login_buttons = [self.tr('a0218_تسجيل_حساب', 'ar'), self.tr('a0220_تسجيل_الدخول', 'ar'), self.tr('a0676_تخطي_التسجيل', 'ar')]
        all_buttons.update(login_buttons)

        # 7) أزرار تم تعديلها سابقاً
        try:
            for original in getattr(self, 'button_labels', {}).keys():
                if original:
                    all_buttons.add(original)
        except:
            pass

        if not all_buttons:
            self.send_message(chat_id, self.tr('a0677_لا_توجد', 'ar'), self.admin_keyboard())
            return

        sorted_buttons = sorted(all_buttons)

        # إنشاء كيبورد inline بدلاً من reply keyboard
        inline_btns = []
        for i in range(0, len(sorted_buttons), 2):
            row = []
            for j in range(2):
                if i + j < len(sorted_buttons):
                    row.append({'text': sorted_buttons[i + j][:50], 'callback_data': f'btn_edit_{i+j}'})
            inline_btns.append(row)

        # تخزين الأزرار للاستخدام لاحقاً
        if not hasattr(self, '_editable_buttons'):
            self._editable_buttons = {}
        self._editable_buttons[user_id] = sorted_buttons

        inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'btn_edit_cancel'}])

        self.user_states[user_id] = 'choose_button_to_edit'

        self.send_inline_message(chat_id,
            "✏️ <b>تعديل مسميات الأزرار</b>\n\n"
            f"📊 إجمالي الأزرار: <b>{len(sorted_buttons)}</b>\n\n"
            "اختر الزر الذي تريد تعديل اسمه أو رمزه:",
            inline_btns)

    def handle_button_label_edit(self, message):
        """معالجة حوار تعديل مسمى زر من الأدمن"""
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        state = self.user_states.get(user_id)
        text = (message.get('text') or '').strip()

        # تأكد من وجود المخزن المؤقت
        if not hasattr(self, 'temp_button_label_edit'):
            self.temp_button_label_edit = {}

        # إلغاء العملية في أي مرحلة
        if text in [self.tr('a0010_إلغاء', 'ar'), self.tr('a0011_الغاء', 'ar'), self.tr('a0009_إلغاء', 'ar'), self.tr('a0678_الغاء', 'ar'), 'cancel', self.tr('a0258_الغاء_العملية', 'ar')]:
            if user_id in self.temp_button_label_edit:
                del self.temp_button_label_edit[user_id]
            if user_id in self.user_states:
                del self.user_states[user_id]
            self.send_message(chat_id, self.tr('a0679_تم_إلغاء', 'ar'), self.admin_keyboard())
            return

        # المرحلة 1: اختيار الزر من القائمة
        if state == 'choose_button_to_edit':
            if not text:
                self.send_message(chat_id, self.tr('a0680_يرجى_اختيار', 'ar'), self.admin_keyboard())
                return

            # حفظ النص القديم مؤقتاً
            self.temp_button_label_edit[user_id] = {'old': text}
            self.user_states[user_id] = 'enter_new_button_label'

            msg = (
                f"✅ تم اختيار الزر:\n<code>{text}</code>\n\n"
                "الآن أرسل الاسم <b>الجديد</b> الذي تريد أن يظهر للمستخدم لهذا الزر."
            )
            self.send_message(chat_id, msg)
            return

        # المرحلة 2: استلام الاسم الجديد
        if state in ['enter_new_button_label', 'editing_button_label_new']:
            if not text:
                self.send_message(chat_id, self.tr('a0681_يرجى_إرسال', 'ar'))
                return

            data = self.temp_button_label_edit.get(user_id, {})
            old_label = data.get('old')
            if not old_label:
                # في حالة فقدان السياق نبدأ من جديد
                self.send_message(chat_id, self.tr('a0682_حدث_خطأ', 'ar'), self.admin_keyboard())
                self.start_button_label_editor(message)
                return

            # تحديث ملف الأزرار
            success = self.update_button_label(old_label, text)
            # إعادة تحميل الخريطة في الذاكرة
            self.init_button_labels()

            # تنظيف الحالة المؤقتة
            if user_id in self.temp_button_label_edit:
                del self.temp_button_label_edit[user_id]
            if user_id in self.user_states:
                del self.user_states[user_id]

            if success:
                msg = (
                    "✅ <b>تم حفظ مسمى الزر الجديد بنجاح</b>\n\n"
                    f"النص القديم: <code>{old_label}</code>\n"
                    f"النص الجديد: <code>{text}</code>\n\n"
                    "✨ التغيير فعال فوراً — سيظهر للمستخدمين في الرسالة القادمة."
                )
            else:
                msg = (
                    "⚠️ حدثت مشكلة أثناء حفظ مسمى الزر الجديد.\n"
                    "يرجى المحاولة مرة أخرى لاحقًا."
                )

            self.send_message(chat_id, msg, self.admin_keyboard())
            return
    def show_admin_management(self, message):
            """لوحة إدارة المديرين المتقدمة"""
            admin_text = self.tr('a0683_إدارة_المديرين', 'ar')

            keyboard = [
                [{'text': '📋 عرض قائمة المديرين'}, {'text': '➕ إضافة مدير دائم'}],
                [{'text': '🕐 إضافة مدير مؤقت'}, {'text': '🎭 تخصيص صلاحيات'}],
                [{'text': '➖ إزالة مدير'}, {'text': '📊 إحصائيات المديرين'}],
                [{'text': '🆔 معرف المستخدم'}],
                [{'text': '↩️ العودة للوحة الأدمن'}]
            ]
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': False
            }
            
            self.send_message(message['chat']['id'], admin_text, reply_keyboard)
            
    # أدوار جاهزة — كل دور يحدد أي أزرار يراها المدير
    # ملاحظة: buttons تُعبأ ديناميكياً في admin_keyboard() وليس هنا (self غير متاح على مستوى الكلاس)
    ADMIN_ROLES = {
        'full': {
            'name': 'مدير كامل',
            'icon': '👑',
            'buttons': None,  # None = كل الأزرار متاحة
        },
        'transactions': {
            'name': 'مشرف معاملات',
            'icon': '💰',
            'buttons': ['pending', 'approved', 'users', 'search', 'stats', 'excel'],
        },
        'support': {
            'name': 'مشرف دعم',
            'icon': '🆘',
            'buttons': ['complaints', 'support', 'users', 'search'],
        },
        'companies': {
            'name': 'مشرف شركات',
            'icon': '🏢',
            'buttons': ['companies', 'payment_methods', 'addresses', 'settings', 'themes', 'language'],
        },
    }

    def add_temp_admin(self, message, user_id_to_add, role='full', duration_hours=0):
            """إضافة مدير مؤقت — مع دور ومدة انتهاء"""
            try:
                if not user_id_to_add.isdigit():
                    self.send_message(message['chat']['id'], self.tr('a0656_معرف_المستخدم', 'ar'), self.admin_keyboard())
                    return
                
                user_id = int(user_id_to_add)
                
                if user_id in self.temp_admin_user_ids:
                    self.send_message(message['chat']['id'], self.tr('a0659_المستخدم_مدير', 'ar', user_id_to_add=user_id_to_add), self.admin_keyboard())
                    return
                
                if user_id in self.admin_user_ids:
                    self.send_message(message['chat']['id'], self.tr('a0695_المستخدم_مدير', 'ar', user_id_to_add=user_id_to_add), self.admin_keyboard())
                    return

                # التحقق من صحة الدور
                if role not in self.ADMIN_ROLES:
                    role = 'full'

                # إضافة المدير المؤقت
                self.temp_admin_user_ids.append(user_id)

                # ضبط وقت الانتهاء (إن وجد)
                if duration_hours > 0:
                    expiry_ts = time.time() + (duration_hours * 3600)
                    self.temp_admin_expiry[user_id] = expiry_ts
                    expiry_display = self.tr('a0696_ساعة', 'ar', duration_hours=duration_hours)
                else:
                    expiry_display = self.tr('a0697_حتى_إعادة', 'ar')

                # ضبط الصلاحيات حسب الدور
                role_info = self.ADMIN_ROLES[role]
                if role_info['buttons'] is not None:
                    # تعيين الصلاحيات: الأزرار المسموحة فقط
                    buttons_dict = {}
                    for btn in role_info['buttons']:
                        buttons_dict[btn] = True
                    # باقي الأزرار = False
                    self.admin_permissions[str(user_id)] = {'buttons': buttons_dict}
                    self.save_admin_permissions()
                else:
                    # مدير كامل — لا تقييد
                    if str(user_id) in self.admin_permissions:
                        del self.admin_permissions[str(user_id)]
                        self.save_admin_permissions()

                role_name = role_info['name']
                role_icon = role_info['icon']

                success_msg = self.tr('a0698_تم_إضافة', 'ar', user_id_to_add=user_id_to_add, role_icon=role_icon, role_name=role_name, expiry_display=expiry_display)

                self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                self.log_admin_action(message['from']['id'], "add_temp_admin",
                    f"user={user_id_to_add}, role={role}, duration={duration_hours}h")
                logger.info(f"تم إضافة مدير مؤقت: {user_id_to_add} (دور: {role}, مدة: {duration_hours}h)")
                
            except Exception as e:
                logger.error(f"خطأ في إضافة المدير المؤقت: {e}")
                self.send_message(message['chat']['id'], self.tr('a0699_حدث_خطأ', 'ar'), self.admin_keyboard())
        
    def remove_admin_user(self, message, user_id_to_remove):
            """إزالة مدير — مع منع إزالة النفس"""
            try:
                if not user_id_to_remove.isdigit():
                    self.send_message(message['chat']['id'], self.tr('a0656_معرف_المستخدم', 'ar'), self.admin_keyboard())
                    return
                
                user_id = int(user_id_to_remove)
                requester_id = message['from']['id']
                
                # أمان: منع إزالة النفس
                if user_id == requester_id:
                    self.send_message(message['chat']['id'], self.tr('a0700_لا_يمكنك', 'ar'), self.admin_keyboard())
                    return
                
                # أمان: منع إزالة آخر أدمن دائم
                if user_id in self.admin_user_ids and len(self.admin_user_ids) <= 1:
                    self.send_message(message['chat']['id'], self.tr('a0701_لا_يمكن', 'ar'), self.admin_keyboard())
                    return
                
                removed = False
                admin_type = ""
                
                # إزالة من المديرين المؤقتين
                if user_id in self.temp_admin_user_ids:
                    self.temp_admin_user_ids.remove(user_id)
                    removed = True
                    admin_type = self.tr('a0702_مؤقت', 'ar')
                
                # إزالة من المديرين الدائمين (للجلسة الحالية فقط)
                elif user_id in self.admin_user_ids:
                    self.admin_user_ids.remove(user_id)
                    removed = True
                    admin_type = self.tr('a0703_دائم_من', 'ar')
                
                if removed:
                    success_msg = self.tr('a0704_تم_إزالة', 'ar', user_id_to_remove=user_id_to_remove, admin_type=admin_type)
                    
                    self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    logger.info(f"تم إزالة مدير {admin_type}: {user_id_to_remove}")
                else:
                    self.send_message(message['chat']['id'], self.tr('a0705_المستخدم_ليس', 'ar', user_id_to_remove=user_id_to_remove), self.admin_keyboard())
                
            except Exception as e:
                logger.error(f"خطأ في إزالة المدير: {e}")
                self.send_message(message['chat']['id'], self.tr('a0706_حدث_خطأ', 'ar'), self.admin_keyboard())
        
    def show_detailed_admin_list(self, message):
            """عرض قائمة المديرين المفصلة"""
            admin_text = self.tr('a0707_قائمة_المديرين', 'ar')
            
            # المديرين الدائمين
            if self.admin_user_ids:
                admin_text += self.tr('a0708_المديرين_الدائمين', 'ar')
                for i, admin_id in enumerate(self.admin_user_ids, 1):
                    admin_text += self.tr('a0709_دائم', 'ar', i=i, admin_id=admin_id)
                admin_text += f"   📊 العدد: {len(self.admin_user_ids)}\n\n"
            
            # المديرين المؤقتين
            if self.temp_admin_user_ids:
                admin_text += self.tr('a0710_المديرين_المؤقتين', 'ar')
                for i, admin_id in enumerate(self.temp_admin_user_ids, 1):
                    admin_text += self.tr('a0711_مؤقت', 'ar', i=i, admin_id=admin_id)
                admin_text += f"   📊 العدد: {len(self.temp_admin_user_ids)}\n\n"
            
            # المديرين من متغيرات البيئة
            if self.admin_ids:
                admin_text += self.tr('a0712_مديرين_البيئة', 'ar')
                for i, admin_id in enumerate(self.admin_ids, 1):
                    admin_text += self.tr('a0713_بيئة', 'ar', i=i, admin_id=admin_id)
                admin_text += f"   📊 العدد: {len(self.admin_ids)}\n\n"
            
            total_admins = len(self.admin_user_ids) + len(self.temp_admin_user_ids) + len(self.admin_ids)
            admin_text += self.tr('a0714_إجمالي_المديرين', 'ar', total_admins=total_admins)
            
            self.send_message(message['chat']['id'], admin_text, self.admin_keyboard())
        
    def prompt_add_permanent_admin(self, message):
            """طلب إضافة مدير دائم"""
            help_text = self.tr('a0715_إضافة_مدير', 'ar')
            
            self.send_message(message['chat']['id'], help_text, self.admin_keyboard())
        
    def prompt_add_temp_admin(self, message):
            """طلب إضافة مدير مؤقت — مع اختيار الدور والمدة"""
            help_text = self.tr('a0716_إضافة_مدير', 'ar')
            
            self.send_message(message['chat']['id'], help_text, self.admin_keyboard())
        
    def start_permission_editor(self, message):
            """بدء تخصيص صلاحيات مدير"""
            # عرض الأدوار الجاهزة
            roles_text = self.tr('a0717_تخصيص_صلاحيات', 'ar')
            roles_text += self.tr('a0718_اختر_دوراً', 'ar')
            for code, info in self.ADMIN_ROLES.items():
                icon = info['icon']
                name = info['name']
                if info['buttons'] is None:
                    roles_text += self.tr('a0719_كل_الأزرار', 'ar', icon=icon, name=name, code=code)
                else:
                    roles_text += f"{icon} {name} ({code}) — {len(info['buttons'])} أزرار\n"
            roles_text += self.tr('a0720_الصيغة', 'ar')
            roles_text += self.tr('a0721_صلاحيات_المستخدم', 'ar')
            roles_text += self.tr('a0722_مثال', 'ar')
            roles_text += self.tr('a0723_صلاحيات', 'ar')

            self.send_message(message['chat']['id'], roles_text, self.admin_keyboard())

    def set_admin_role(self, message, admin_id_str, role):
            """تعيين دور لمدير"""
            try:
                if role not in self.ADMIN_ROLES:
                    self.send_message(message['chat']['id'], self.tr('a0724_دور_غير', 'ar'), self.admin_keyboard())
                    return

                role_info = self.ADMIN_ROLES[role]
                if role_info['buttons'] is None:
                    # مدير كامل — إزالة القيود
                    if admin_id_str in self.admin_permissions:
                        del self.admin_permissions[admin_id_str]
                        self.save_admin_permissions()
                else:
                    # تعيين الأزرار المسموحة فقط
                    buttons_dict = {}
                    for btn in role_info['buttons']:
                        buttons_dict[btn] = True
                    self.admin_permissions[admin_id_str] = {'buttons': buttons_dict}
                    self.save_admin_permissions()

                self.log_admin_action(message['from']['id'], "set_admin_role",
                    f"admin={admin_id_str}, role={role}")
                self.send_message(message['chat']['id'],
                    self.tr('a0725_تم_تعيين', 'ar', role_info_icon=role_info['icon'], role_info_name=role_info['name'], admin_id_str=admin_id_str),
                    self.admin_keyboard())
                logger.info(f"Set admin role {role} for {admin_id_str}")
            except Exception as e:
                logger.error(f"خطأ في تعيين دور المدير: {e}")
                self.send_message(message['chat']['id'], self.tr('a0726_خطأ_في', 'ar'), self.admin_keyboard())

    def prompt_remove_admin(self, message):
            """طلب إزالة مدير"""
            help_text = self.tr('a0727_إزالة_مدير', 'ar')
            
            self.send_message(message['chat']['id'], help_text, self.admin_keyboard())
        
    def show_admin_statistics(self, message):
            """عرض إحصائيات المديرين"""
            stats_text = self.tr('a0728_إحصائيات_المديرين', 'ar')
            
            # إحصائيات المديرين
            permanent_count = len(self.admin_user_ids)
            temp_count = len(self.temp_admin_user_ids)
            env_count = len(self.admin_ids)
            total_count = permanent_count + temp_count + env_count
            
            stats_text += self.tr('a0729_مديرين_دائمين', 'ar', permanent_count=permanent_count)
            stats_text += self.tr('a0730_مديرين_مؤقتين', 'ar', temp_count=temp_count)
            stats_text += self.tr('a0731_ديرين_البيئة', 'ar', env_count=env_count)
            stats_text += self.tr('a0732_إجمالي_المديرين', 'ar', total_count=total_count)
            
            # إحصائيات الأمان
            stats_text += self.tr('a0733_مستوى_الأمان', 'ar')
            if total_count >= 3:
                stats_text += self.tr('a0734_ممتاز_عدد', 'ar')
            elif total_count >= 2:
                stats_text += self.tr('a0735_جيد_يُنصح', 'ar')
            else:
                stats_text += self.tr('a0736_منخفض_يُنصح', 'ar')
            
            # توصيات
            stats_text += self.tr('a0737_التوصيات', 'ar')
            if temp_count > permanent_count:
                stats_text += self.tr('a0738_تحويل_بعض', 'ar')
            if total_count < 2:
                stats_text += self.tr('a0739_إضافة_مديرين', 'ar')
            if env_count == 0:
                stats_text += self.tr('a0740_إضافة_مدير', 'ar')
            
            self.send_message(message['chat']['id'], stats_text, self.admin_keyboard())
        
    def prompt_broadcast(self, message):
            """طلب الإرسال الجماعي — يدعم جميع أنواع الوسائط"""
            broadcast_help = self.tr('a0741_الإرسال_الجماعي', 'ar')
            self.send_message(message['chat']['id'], broadcast_help)
            self.user_states[message['from']['id']] = 'admin_broadcasting'
        
    def prompt_ban_user(self, message):
            """طلب حظر مستخدم"""
            ban_help = self.tr('a0742_حظر_مستخدم', 'ar')
            self.send_message(message['chat']['id'], ban_help, self.admin_keyboard())
        
    def prompt_unban_user(self, message):
            """طلب إلغاء حظر مستخدم مع عرض المستخدمين المحظورين"""
            # البحث عن المستخدمين المحظورين
            banned_users = []
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('is_banned', 'no') == 'yes':
                            banned_users.append({
                                'customer_id': row['customer_id'],
                                'name': row['name'],
                                'ban_reason': row.get('ban_reason', self.tr('a0122_غير_محدد', 'ar'))
                            })
            except:
                pass
            
            unban_help = self.tr('a0743_إلغاء_حظر', 'ar')
            
            if banned_users:
                unban_help += self.tr('a0744_المستخدمين_المحظورين', 'ar')
                for user in banned_users:
                    unban_help += f"\n🆔 {user['customer_id']}\n"
                    unban_help += f"👤 {user['name']}\n"
                    unban_help += self.tr('a0745_السبب', 'ar', user_ban_reason=user['ban_reason'])
                    unban_help += self.tr('a0746_الغاء_حظر', 'ar', user_customer_id=user['customer_id'])
                    unban_help += "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n"
            else:
                unban_help += self.tr('a0747_لا_يوجد', 'ar')
            
            self.send_message(message['chat']['id'], unban_help, self.admin_keyboard())
        
    def prompt_add_company(self, message):
            """بدء معالج إضافة شركة التفاعلي"""
            help_text = self.tr('a0748_معالج_إضافة', 'ar')
            
            self.send_message(message['chat']['id'], help_text)
            self.user_states[message['from']['id']] = 'adding_company_name'
        
    def handle_company_wizard(self, message):
            """معالج إضافة الشركة التفاعلي"""
            user_id = message['from']['id']
            state = self.user_states.get(user_id)
            text = message.get('text', '').strip()
            
            if state == 'adding_company_name':
                # حفظ اسم الشركة
                if not hasattr(self, 'temp_company_data'):
                    self.temp_company_data = {}
                if user_id not in self.temp_company_data:
                    self.temp_company_data[user_id] = {}
                
                self.temp_company_data[user_id]['name'] = text
                
                # طلب نوع الخدمة
                service_keyboard = {
                    'keyboard': [
                        [{'text': '💳 إيداع فقط'}, {'text': '💰 سحب فقط'}],
                        [{'text': '🔄 إيداع وسحب معاً'}],
                        [{'text': '❌ إلغاء'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': True
                }
                
                self.send_message(message['chat']['id'], 
                    self.tr('a0749_تم_حفظ', 'ar', text=text), 
                    service_keyboard)
                self.user_states[user_id] = 'adding_company_type'
                
            elif state == 'adding_company_type':
                # حفظ نوع الخدمة
                if text == self.tr('a0750_إيداع_فقط', 'ar'):
                    service_type = 'deposit'
                    service_display = self.tr('a0751_إيداع_فقط', 'ar')
                elif text == self.tr('a0752_سحب_فقط', 'ar'):
                    service_type = 'withdraw'
                    service_display = self.tr('a0753_سحب_فقط', 'ar')
                elif text == self.tr('a0754_إيداع_وسحب', 'ar'):
                    service_type = 'both'
                    service_display = self.tr('a0755_إيداع_وسحب', 'ar')
                elif text == self.tr('a0009_إلغاء', 'ar'):
                    del self.user_states[user_id]
                    if hasattr(self, 'temp_company_data') and user_id in self.temp_company_data:
                        del self.temp_company_data[user_id]
                    self.send_message(message['chat']['id'], self.tr('a0756_تم_إلغاء', 'ar'), self.admin_keyboard())
                    return
                else:
                    self.send_message(message['chat']['id'], self.tr('a0757_اختر_نوع', 'ar'))
                    return
                
                self.temp_company_data[user_id]['type'] = service_type
                self.temp_company_data[user_id]['type_display'] = service_display
                
                # طلب التفاصيل
                self.send_message(message['chat']['id'], 
                    self.tr('a0758_نوع_الخدمة', 'ar', service_display=service_display))
                self.user_states[user_id] = 'adding_company_details'
                
            elif state == 'adding_company_details':
                # حفظ التفاصيل وطلب الأيقونة
                self.temp_company_data[user_id]['details'] = text
                self.send_message(message['chat']['id'], 
                    self.tr('a0759_اختر_أيقونة', 'ar'))
                self.user_states[user_id] = 'adding_company_icon'
                
            elif state == 'adding_company_icon':
                # حفظ الأيقونة وطلب العنوان
                if text.lower().strip() in ['skip', self.tr('a0024_تخطي', 'ar'), '']:
                    icon = '🏢'
                else:
                    icon = self.normalize_icon(text.strip(), default='🏢')
                self.temp_company_data[user_id]['icon'] = icon
                self.send_message(message['chat']['id'], 
                    self.tr('a0760_أدخل_عنوان', 'ar'))
                self.user_states[user_id] = 'adding_company_address'
                
            elif state == 'adding_company_address':
                # حفظ العنوان وطلب رابط الإحالة
                if text.lower().strip() in ['skip', self.tr('a0024_تخطي', 'ar'), '']:
                    address = ''
                else:
                    address = self.sanitize_input(text.strip())
                self.temp_company_data[user_id]['address'] = address
                
                self.send_message(message['chat']['id'], 
                    "🔗 أدخل رابط الإحالة (affiliate link) لهذه الشركة:\n"
                    "(الرابط الذي يضغط عليه العميل للتسجيل في الشركة)\n"
                    "أو اكتب 'skip' لتخطي")
                self.user_states[user_id] = 'adding_company_affiliate'
                
            elif state == 'adding_company_affiliate':
                if text.lower().strip() in ['skip', self.tr('a0024_تخطي', 'ar'), '']:
                    affiliate = ''
                else:
                    affiliate = text.strip()
                self.temp_company_data[user_id]['affiliate_link'] = affiliate
                
                company_data = self.temp_company_data[user_id]
                icon = company_data.get('icon', '🏢')
                address_display = company_data.get('address', '') or self.tr('a0761_عنوان_عام', 'ar')
                affiliate_display = company_data.get('affiliate_link', '') or self.tr('a0762_لا_يوجد', 'ar')
                confirm_text = self.tr('a0763_ملخص_الشركة', 'ar', icon=icon, company_data_name=company_data['name'], company_data_type_display=company_data['type_display'], company_data_details=company_data['details'], address_display=address_display, affiliate_display=affiliate_display)
                
                # أزرار inline للتأكيد
                inline_btns = [
                    [{'text': '✅ حفظ الشركة', 'callback_data': 'confirm_company_save'},
                     {'text': '❌ إلغاء', 'callback_data': 'confirm_company_cancel'}],
                    [{'text': '🔄 تعديل الاسم', 'callback_data': 'edit_company_name'},
                     {'text': '🔧 تعديل النوع', 'callback_data': 'edit_company_type'},
                     {'text': '📝 تعديل التفاصيل', 'callback_data': 'edit_company_details'}]
                ]
                
                self.send_inline_message(message['chat']['id'], confirm_text, inline_btns)
                self.user_states[user_id] = 'confirming_company'
                
            elif state == 'confirming_company':
                company_data = self.temp_company_data[user_id]
                
                if text == self.tr('a0351_حفظ_الشركة', 'ar'):
                    # تجنب تشغيل نفس الكود مرتين - هذا يُعالج الآن في handle_admin_actions
                    pass
                        
                elif text == self.tr('a0009_إلغاء', 'ar'):
                    del self.user_states[user_id]
                    if user_id in self.temp_company_data:
                        del self.temp_company_data[user_id]
                    self.send_message(message['chat']['id'], self.tr('a0756_تم_إلغاء', 'ar'), self.admin_keyboard())
                    
                elif text == self.tr('a0764_تعديل_الاسم', 'ar'):
                    self.send_message(message['chat']['id'], self.tr('a0765_الاسم_الحالي', 'ar', company_data_name=company_data['name']))
                    self.user_states[user_id] = 'adding_company_name'
                    
                elif text == self.tr('a0766_تعديل_النوع', 'ar'):
                    service_keyboard = {
                        'keyboard': [
                            [{'text': '💳 إيداع فقط'}, {'text': '💰 سحب فقط'}],
                            [{'text': '🔄 إيداع وسحب معاً'}],
                            [{'text': '❌ إلغاء'}]
                        ],
                        'resize_keyboard': True,
                        'one_time_keyboard': True
                    }
                    self.send_message(message['chat']['id'], self.tr('a0767_النوع_الحالي', 'ar', company_data_type_display=company_data['type_display']), service_keyboard)
                    self.user_states[user_id] = 'adding_company_type'
                    
                elif text == self.tr('a0768_تعديل_التفاصيل', 'ar'):
                    self.send_message(message['chat']['id'], self.tr('a0769_التفاصيل_الحالية', 'ar', company_data_details=company_data['details']))
                    self.user_states[user_id] = 'adding_company_details'
                    
                else:
                    self.send_message(message['chat']['id'], self.tr('a0770_اختر_من', 'ar'))
        
    def prompt_edit_company(self, message):
            """بدء معالج تعديل الشركة"""
            # عرض الشركات المتاحة للتعديل
            companies_text = self.tr('a0771_تعديل_الشركات', 'ar')
            
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        status = "✅" if row.get('is_active') == 'active' else "❌"
                        companies_text += f"{status} {row['id']} - {row['name']}\n"
                        companies_text += f"   📋 {row['type']} - {row['details']}\n\n"
            except:
                companies_text += self.tr('a0772_لا_توجد', 'ar')
            
            companies_text += self.tr('a0773_أرسل_رقم', 'ar')
            
            self.send_message(message['chat']['id'], companies_text)
            self.user_states[message['from']['id']] = 'selecting_company_edit'
        
    def handle_company_edit_wizard(self, message):
            """معالج تعديل الشركة التفاعلي"""
            user_id = message['from']['id']
            state = self.user_states.get(user_id)
            text = message.get('text', '').strip()
            
            if state == 'selecting_company_edit':
                # البحث عن الشركة
                company_found = None
                try:
                    with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row['id'] == text:
                                company_found = row
                                break
                except:
                    pass
                
                if not company_found:
                    self.send_message(message['chat']['id'], self.tr('a0774_لم_يتم', 'ar', text=text))
                    return
                
                # حفظ بيانات الشركة للتعديل
                if not hasattr(self, 'edit_company_data'):
                    self.edit_company_data = {}
                self.edit_company_data[user_id] = company_found
                
                # عرض بيانات الشركة الحالية
                type_display = {'deposit': 'إيداع فقط', 'withdraw': 'سحب فقط', 'both': 'إيداع وسحب'}.get(company_found['type'], company_found['type'])
                
                edit_options = f"""📊 بيانات الشركة الحالية:
    
    🆔 المعرف: {company_found['id']}
    🏢 الاسم: {company_found['name']}
    ⚡ النوع: {type_display}
    📋 التفاصيل: {company_found['details']}
    🔘 الحالة: {'نشط' if company_found.get('is_active') == 'active' else 'غير نشط'}
    
    ماذا تريد تعديل؟"""
                
                edit_keyboard = {
                    'keyboard': [
                        [{'text': '📝 تعديل الاسم'}, {'text': '🔧 تعديل النوع'}],
                        [{'text': '📋 تعديل التفاصيل'}, {'text': '🔘 تغيير الحالة'}],
                        [{'text': '✅ حفظ التغييرات'}, {'text': '❌ إلغاء'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': True
                }
                
                self.send_message(message['chat']['id'], edit_options, edit_keyboard)
                self.user_states[user_id] = 'editing_company_menu'
                
            elif state == 'editing_company_menu':
                if text == self.tr('a0775_تعديل_الاسم', 'ar'):
                    current_name = self.edit_company_data[user_id]['name']
                    self.send_message(message['chat']['id'], self.tr('a0776_الاسم_الحالي', 'ar', current_name=current_name))
                    self.user_states[user_id] = 'editing_company_name'
                    
                elif text == self.tr('a0766_تعديل_النوع', 'ar'):
                    service_keyboard = {
                        'keyboard': [
                            [{'text': '💳 إيداع فقط'}, {'text': '💰 سحب فقط'}],
                            [{'text': '🔄 إيداع وسحب معاً'}],
                            [{'text': '↩️ العودة للقائمة'}]
                        ],
                        'resize_keyboard': True,
                        'one_time_keyboard': True
                    }
                    current_type = {'deposit': 'إيداع فقط', 'withdraw': 'سحب فقط', 'both': 'إيداع وسحب'}.get(self.edit_company_data[user_id]['type'])
                    self.send_message(message['chat']['id'], self.tr('a0777_النوع_الحالي', 'ar', current_type=current_type), service_keyboard)
                    self.user_states[user_id] = 'editing_company_type'
                    
                elif text == self.tr('a0778_تعديل_التفاصيل', 'ar'):
                    current_details = self.edit_company_data[user_id]['details']
                    self.send_message(message['chat']['id'], self.tr('a0779_التفاصيل_الحالية', 'ar', current_details=current_details))
                    self.user_states[user_id] = 'editing_company_details'
                    
                elif text == self.tr('a0780_تغيير_الحالة', 'ar'):
                    current_status = self.edit_company_data[user_id].get('is_active', 'active')
                    new_status = 'inactive' if current_status == 'active' else 'active'
                    status_text = self.tr('a0058_نشط', 'ar') if new_status == 'active' else self.tr('a0781_غير_نشط', 'ar')
                    
                    self.edit_company_data[user_id]['is_active'] = new_status
                    self.send_message(message['chat']['id'], self.tr('a0782_تم_تغيير', 'ar', status_text=status_text))
                    self.show_edit_menu(message, user_id)
                    
                elif text == self.tr('a0783_تعديل_العنوان', 'ar'):
                    current_address = self.edit_company_data[user_id].get('address', '') or ''
                    self.send_message(message['chat']['id'],
                        f"📍 العنوان الحالي: {current_address or 'غير محدد'}\n\n"
                        "أرسل العنوان الجديد:\n"
                        "(هذا العنوان يظهر للعميل أثناء عملية السحب)\n\n"
                        "أو اكتب 'حذف' لإزالة العنوان")
                    self.user_states[user_id] = 'editing_company_address'
                    
                elif text == self.tr('a0784_تعديل_رابط', 'ar'):
                    current_affiliate = self.edit_company_data[user_id].get('affiliate_link', '') or ''
                    self.send_message(message['chat']['id'],
                        f"🔗 رابط الإحالة الحالي: {current_affiliate or 'غير محدد'}\n\n"
                        "أرسل الرابط الجديد:\n"
                        "(هذا الرابط يظهر للعميل كزر للتسجيل في الشركة)\n\n"
                        "أو اكتب 'حذف' لإزالة الرابط")
                    self.user_states[user_id] = 'editing_company_affiliate'
                    
                elif text == self.tr('a0785_ربط_وسائل', 'ar'):
                    self.show_company_payment_methods_link(message, user_id)
                    
                elif text == '🏷️ أيقونة الشركة':
                    # عرض شبكة إيموجي من المكتبة + افتراضية
                    company_id = self.edit_company_data[user_id].get('id', '')
                    current_icon = self.edit_company_data[user_id].get('icon', '🏢') or '🏢'
                    # قراءة كل الإيموجي من المكتبة
                    lib_emojis = []
                    try:
                        with open('sticker_library.csv', 'r', encoding='utf-8-sig') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                if row.get('type') == 'emoji' and row.get('emoji', '').strip():
                                    lib_emojis.append(row.get('emoji', '').strip())
                    except:
                        pass

                    # إيموجي افتراضية شائعة للشركات
                    default_emojis = ['🏦', '💳', '📱', '💵', '👛', '🏢', '💰', '💱', '🪙', '📡',
                                     '🌍', '🟡', '✈️', '🚀', '⭐', '🏪', '🏬', '🛒', '💎', '🔗']
                    # دمج بدون تكرار
                    all_emojis = list(dict.fromkeys(lib_emojis + default_emojis))[:50]

                    # بناء أزرار inline — 5 لكل صف
                    inline_btns = []
                    for i in range(0, len(all_emojis), 5):
                        row = []
                        for j in range(5):
                            if i + j < len(all_emojis):
                                em = all_emojis[i + j]
                                marker = '✅' if em == current_icon else ''
                                row.append({'text': f"{em}{marker}", 'callback_data': f'company_icon_{em}_{company_id}'})
                        if row:
                            inline_btns.append(row)
                    inline_btns.append([{'text': '🖼️ رفع صورة مخصصة', 'callback_data': f'company_photo_{company_id}'}])
                    inline_btns.append([{'text': '↩️ العودة', 'callback_data': 'company_icon_back'}])

                    self.send_inline_message(message['chat']['id'],
                        f"🏷️ <b>اختر أيقونة للشركة</b>\n\n"
                        f"الأيقونة الحالية: {current_icon}\n\n"
                        f"💡 اختر من الشبكة أو اضغط <b>🖼️ رفع صورة</b> لأيقونة مخصصة\n"
                        f"📊 المتاح: <code>{len(all_emojis)}</code> إيموجي",
                        inline_btns)
                    self.user_states[user_id] = 'editing_company_icon'
                    
                elif text == self.tr('a0355_حفظ_التغييرات', 'ar'):
                    self.save_company_changes(message)
                    
                elif text == self.tr('a0009_إلغاء', 'ar'):
                    del self.user_states[user_id]
                    if user_id in self.edit_company_data:
                        del self.edit_company_data[user_id]
                    self.send_message(message['chat']['id'], self.tr('a0786_تم_إلغاء', 'ar'), self.admin_keyboard())
                    
            elif state == 'editing_company_name':
                self.edit_company_data[user_id]['name'] = text
                self.send_message(message['chat']['id'], self.tr('a0787_تم_تحديث', 'ar', text=text))
                self.show_edit_menu(message, user_id)
                
            elif state == 'editing_company_type':
                if text == self.tr('a0750_إيداع_فقط', 'ar'):
                    self.edit_company_data[user_id]['type'] = 'deposit'
                    self.send_message(message['chat']['id'], self.tr('a0788_تم_تحديث', 'ar'))
                elif text == self.tr('a0752_سحب_فقط', 'ar'):
                    self.edit_company_data[user_id]['type'] = 'withdraw'
                    self.send_message(message['chat']['id'], self.tr('a0789_تم_تحديث', 'ar'))
                elif text == self.tr('a0754_إيداع_وسحب', 'ar'):
                    self.edit_company_data[user_id]['type'] = 'both'
                    self.send_message(message['chat']['id'], self.tr('a0790_تم_تحديث', 'ar'))
                elif text == self.tr('a0791_العودة_للقائمة', 'ar'):
                    pass
                else:
                    self.send_message(message['chat']['id'], self.tr('a0757_اختر_نوع', 'ar'))
                    return
                
                self.show_edit_menu(message, user_id)
                
            elif state == 'editing_company_details':
                self.edit_company_data[user_id]['details'] = text
                self.send_message(message['chat']['id'], self.tr('a0792_تم_تحديث', 'ar', text=text))
                self.show_edit_menu(message, user_id)
                
            elif state == 'editing_company_address':
                if text.lower() in [self.tr('a0013_حذف', 'ar'), 'delete', self.tr('a0014_مسح', 'ar')]:
                    self.edit_company_data[user_id]['address'] = ''
                    self.send_message(message['chat']['id'], self.tr('a0793_تم_حذف', 'ar'))
                else:
                    self.edit_company_data[user_id]['address'] = text
                    self.send_message(message['chat']['id'], self.tr('a0794_تم_تحديث', 'ar', text=text))
                self.show_edit_menu(message, user_id)
                
            elif state == 'editing_company_affiliate':
                if text.lower() in [self.tr('a0013_حذف', 'ar'), 'delete', self.tr('a0014_مسح', 'ar')]:
                    self.edit_company_data[user_id]['affiliate_link'] = ''
                    self.send_message(message['chat']['id'], self.tr('a0795_تم_حذف', 'ar'))
                else:
                    self.edit_company_data[user_id]['affiliate_link'] = text
                    self.send_message(message['chat']['id'], self.tr('a0796_تم_تحديث', 'ar', text=text))
                self.show_edit_menu(message, user_id)
                
            elif state == 'editing_company_icon':
                # العميل أرسل إيموجي مخصص يدوياً
                if text and len(text) <= 4 and any(ord(c) > 127 for c in text):
                    self.edit_company_data[user_id]['icon'] = text
                    self.send_message(message['chat']['id'],
                        f"✅ تم تحديث الأيقونة: {text}")
                    self.show_edit_menu(message, user_id)
                else:
                    self.send_message(message['chat']['id'],
                        "❌ أرسل إيموجي صحيح فقط:\n\n"
                        "💡 مثال: 🏦 📱 💳 💰")
        
    def show_company_payment_methods_link(self, message, user_id):
        """عرض وسائل الدفع المرتبطة بالشركة — أزرار toggle للربط/فصل"""
        company = self.edit_company_data.get(user_id, {})
        company_id = company.get('id', '')

        # جلب كل وسائل الدفع النشطة (المجموعة العامة)
        all_methods = []
        try:
            with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'active':
                        all_methods.append(row)
        except:
            pass

        # الوسائل المرتبطة بهذه الشركة
        linked_ids = self.get_linked_method_ids(company_id)

        text = f"💳 <b>وسائل الدفع — {company.get('name', '')}</b>\n\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += self.tr('a0797_مرتبطة_متاحة', 'ar')

        inline_btns = []
        if not all_methods:
            text += self.tr('a0798_لا_توجد', 'ar')
        else:
            for m in all_methods:
                icon = m.get('icon', '💳') or '💳'
                name = m.get('method_name', '')
                mid = m.get('id', '')
                is_linked = mid in linked_ids
                prefix = '✅' if is_linked else '⬜'
                text += f"{prefix} {icon} {name} — <code>{m.get('account_data', '')}</code>\n"
                btn_text = f"{prefix} {icon} {name}"[:50]
                if is_linked:
                    inline_btns.append([{'text': btn_text, 'callback_data': f'pm_unlink_{company_id}_{mid}'}])
                else:
                    inline_btns.append([{'text': btn_text, 'callback_data': f'pm_link_{company_id}_{mid}'}])

        inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'pm_link_back'}])
        self.send_inline_message(message['chat']['id'], text, inline_btns)
    
    def show_edit_menu(self, message, user_id):
            """عرض قائمة تعديل الشركة"""
            company_data = self.edit_company_data[user_id]
            type_display = {'deposit': 'إيداع فقط', 'withdraw': 'سحب فقط', 'both': 'إيداع وسحب'}.get(company_data['type'], company_data['type'])
            address = company_data.get('address', '') or self.tr('a0122_غير_محدد', 'ar')
            affiliate = company_data.get('affiliate_link', '') or self.tr('a0122_غير_محدد', 'ar')
            
            edit_options = f"""📊 بيانات الشركة المحدثة:
    
    🆔 المعرف: {company_data['id']}
    🏢 الاسم: {company_data['name']}
    ⚡ النوع: {type_display}
    📋 التفاصيل: {company_data['details']}
    📍 العنوان: {address}
    🔗 رابط الإحالة: {affiliate}
    🔘 الحالة: {'نشط' if company_data.get('is_active') == 'active' else 'غير نشط'}
    
    ماذا تريد تعديل؟"""
            
            edit_keyboard = {
                'keyboard': [
                    [{'text': '📝 تعديل الاسم'}, {'text': '🔧 تعديل النوع'}],
                    [{'text': '📋 تعديل التفاصيل'}, {'text': '📍 تعديل العنوان'}],
                    [{'text': '🔗 تعديل رابط الإحالة'}, {'text': '💳 ربط وسائل الدفع'}],
                    [{'text': '🏷️ أيقونة الشركة'}, {'text': '🔘 تغيير الحالة'}],
                    [{'text': '✅ حفظ التغييرات'}, {'text': '❌ إلغاء'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], edit_options, edit_keyboard)
            self.user_states[user_id] = 'editing_company_menu'
        
    def save_company_changes(self, message):
            """حفظ تغييرات الشركة"""
            user_id = message['from']['id']
            try:
                companies = []
                updated_company = self.edit_company_data[user_id]
                
                # قراءة جميع الشركات
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames or ['id', 'name', 'type', 'details', 'is_active', 'icon', 'address', 'affiliate_link']
                    for row in reader:
                        if row['id'] == updated_company['id']:
                            # دمج التحديثات مع الصف الأصلي
                            row.update({k: updated_company.get(k, row.get(k, '')) for k in fieldnames})
                            companies.append(row)
                        else:
                            companies.append(row)
                
                # كتابة الملف المحدث
                with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in companies:
                        writer.writerow({k: row.get(k, '') for k in fieldnames})
                
                type_display = {'deposit': 'إيداع فقط', 'withdraw': 'سحب فقط', 'both': 'إيداع وسحب'}.get(updated_company['type'])
                
                success_msg = f"""✅ تم حفظ التغييرات بنجاح!
    
    🆔 المعرف: {updated_company['id']}
    🏢 الاسم: {updated_company['name']}
    ⚡ النوع: {type_display}
    📋 التفاصيل: {updated_company['details']}
    📍 العنوان: {updated_company.get('address', 'غير محدد') or 'غير محدد'}
    🔗 رابط الإحالة: {updated_company.get('affiliate_link', 'غير محدد') or 'غير محدد'}
    🔘 الحالة: {'نشط' if updated_company.get('is_active') == 'active' else 'غير نشط'}"""
                
                self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                
            except Exception as e:
                self.send_message(message['chat']['id'], f"❌ فشل في حفظ التغييرات: {str(e)}", self.admin_keyboard())
            
            # تنظيف البيانات المؤقتة
            del self.user_states[user_id]
            if user_id in self.edit_company_data:
                del self.edit_company_data[user_id]
        
    def show_companies_management_enhanced(self, message):
            """عرض إدارة الشركات — مع الأيقونات والعناوين"""
            companies_text = self.tr('a0799_إدارة_الشركات', 'ar')
            
            try:
                companies = []
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    companies = list(reader)
                
                if len(companies) == 0:
                    companies_text += self.tr('a0800_لا_توجد', 'ar')
                else:
                    companies_text += f"📊 الإجمالي: {len(companies)}\n\n"
                    
                    for i, row in enumerate(companies, 1):
                        status = "✅" if row.get('is_active', '').lower() == 'active' else "❌"
                        icon = row.get('icon', '🏢') or '🏢'
                        type_display = {'deposit': 'إيداع', 'withdraw': 'سحب', 'both': 'الكل'}.get(row.get('type', ''), row.get('type', ''))
                        address = row.get('address', '')
                        companies_text += f"{i}. {status} {icon} {row.get('name', '?')} (ID: {row.get('id', '?')})\n"
                        companies_text += f"   🔧 {type_display} | 📋 {row.get('details', '-')}\n"
                        if address:
                            companies_text += f"   📍 {address}\n"
                        companies_text += "\n"
                        
            except Exception as e:
                companies_text += f"❌ خطأ: {str(e)}\n\n"
            
            # أزرار الإدارة المتقدمة
            management_keyboard = {
                'keyboard': [
                    [{'text': '➕ إضافة شركة جديدة'}, {'text': '✏️ تعديل شركة'}],
                    [{'text': '🗑️ حذف شركة'}, {'text': '🔄 تحديث القائمة'}],
                    [{'text': '📋 تصدير البيانات'}, {'text': '↩️ العودة للوحة الأدمن'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            companies_text += self.tr('a0801_خيارات_الإدارة', 'ar')
            
            self.send_message(message['chat']['id'], companies_text, management_keyboard)
        
    def prompt_delete_company(self, message):
            """بدء معالج حذف الشركة بأمان"""
            companies_text = self.tr('a0802_حذف_الشركات', 'ar')
            
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        status = "✅" if row.get('is_active') == 'active' else "❌"
                        companies_text += f"{status} {row['id']} - {row['name']}\n"
                        companies_text += f"   📋 {row['type']} - {row['details']}\n\n"
            except:
                companies_text += self.tr('a0772_لا_توجد', 'ar')
            
            companies_text += self.tr('a0803_أرسل_رقم', 'ar')
            
            self.send_message(message['chat']['id'], companies_text)
            self.user_states[message['from']['id']] = 'confirming_company_delete'
        
    def handle_company_delete_confirmation(self, message):
            """معالج تأكيد حذف الشركة"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            company_id = text
            
            # البحث عن الشركة
            company_found = None
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == company_id:
                            company_found = row
                            break
            except:
                pass
            
            if not company_found:
                self.send_message(message['chat']['id'], self.tr('a0804_لم_يتم', 'ar', company_id=company_id))
                del self.user_states[user_id]
                return
            
            # عرض تأكيد الحذف
            confirm_text = self.tr('a0805_تأكيد_حذف', 'ar', company_found_id=company_found['id'], company_found_name=company_found['name'], company_found_type=company_found['type'], company_found_details=company_found['details'])
            
            # أزرار inline لتأكيد الحذف
            inline_btns = [
                [{'text': '🗑️ نعم، احذف', 'callback_data': f'confirm_delete_company_{company_id}'},
                 {'text': '❌ إلغاء', 'callback_data': 'cancel_delete_company'}]
            ]
            
            self.send_inline_message(message['chat']['id'], confirm_text, inline_btns)
            self.user_states[user_id] = f'deleting_company_{company_id}'
        
    def finalize_company_delete(self, message, company_id):
            """إنهاء حذف الشركة"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text == self.tr('a0806_نعم،_احذف', 'ar'):
                # تنفيذ الحذف
                companies = []
                deleted_company = None
                
                try:
                    with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row['id'] != company_id:
                                companies.append(row)
                            else:
                                deleted_company = row
                    
                    # كتابة الملف بدون الشركة المحذوفة
                    with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['id', 'name', 'type', 'details', 'is_active']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(companies)
                    
                    if deleted_company:
                        success_msg = self.tr('a0807_تم_حذف', 'ar', deleted_company_id=deleted_company['id'], deleted_company_name=deleted_company['name'], deleted_company_type=deleted_company['type'])
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], self.tr('a0808_فشل_في', 'ar'), self.admin_keyboard())
                        
                except Exception as e:
                    self.send_message(message['chat']['id'], f"❌ فشل في حذف الشركة: {str(e)}", self.admin_keyboard())
            
            elif text == self.tr('a0009_إلغاء', 'ar'):
                self.send_message(message['chat']['id'], self.tr('a0809_تم_إلغاء', 'ar'), self.admin_keyboard())
            
            # تنظيف الحالة
            del self.user_states[user_id]
        
    def show_quick_copy_commands(self, message):
            """عرض أوامر نسخ سريعة للأدمن"""
            commands_text = self.tr('a0810_أوامر_نسخ', 'ar')
            
            self.send_message(message['chat']['id'], commands_text, self.admin_keyboard())
        
    def get_linked_method_ids(self, company_id):
        """جلب معرفات وسائل الدفع المرتبطة بشركة"""
        ids = set()
        try:
            with open('company_payment_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('company_id') == str(company_id):
                        ids.add(row.get('method_id', ''))
        except:
            pass
        return ids

    def link_payment_method(self, company_id, method_id):
        """ربط وسيلة دفع بشركة"""
        linked = self.get_linked_method_ids(company_id)
        if method_id in linked:
            return False
        link_id = f"LNK{str(int(datetime.now().timestamp()))[-6:]}"
        try:
            with open('company_payment_links.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([link_id, company_id, method_id, datetime.now().strftime('%Y-%m-%d %H:%M')])
            return True
        except:
            return False

    def unlink_payment_method(self, company_id, method_id):
        """فصل وسيلة دفع عن شركة"""
        try:
            rows = []
            found = False
            with open('company_payment_links.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('company_id') == str(company_id) and row.get('method_id') == str(method_id):
                        found = True
                        continue
                    rows.append(row)
            if found:
                with open('company_payment_links.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
            return found
        except:
            return False

    # ==================== خطوات وسائل الدفع المخصصة ====================

    PM_STEP_FIELDS = ['id', 'method_id', 'flow_type', 'step_order', 'step_type', 'step_label']

    def get_method_steps(self, method_id, flow_type):
        """جلب خطوات وسيلة دفع لنوع تدفق (deposit/withdraw)"""
        steps = []
        try:
            with open('payment_method_steps.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('method_id') == str(method_id) and row.get('flow_type') == flow_type:
                        steps.append(row)
            steps.sort(key=lambda s: int(s.get('step_order', 0)))
        except:
            pass
        return steps

    def add_method_step(self, method_id, flow_type, step_type, step_label, step_order):
        """إضافة خطوة لوسيلة دفع"""
        step_id = f"STP{str(int(datetime.now().timestamp()))[-6:]}_{step_order}"
        try:
            with open('payment_method_steps.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([step_id, method_id, flow_type, step_order, step_type, step_label])
            return step_id
        except:
            return None

    def delete_method_steps(self, method_id):
        """حذف كل خطوط وسيلة دفع"""
        try:
            rows = []
            with open('payment_method_steps.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('method_id') != str(method_id):
                        rows.append(row)
            with open('payment_method_steps.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            return True
        except:
            return False

    def has_custom_steps(self, method_id, flow_type):
        """فحص هل لوسيلة الدفع خطوات مخصصة"""
        return len(self.get_method_steps(method_id, flow_type)) > 0

    # ==================== نظام التداول USDT/MoneyGo ====================

    TRADE_FIELDS = ['id', 'buyer_id', 'buyer_name', 'customer_id', 'order_type', 'asset_type',
                    'network', 'account_address', 'payment_method', 'amount', 'currency',
                    'usdt_amount', 'admin_payment_method', 'status', 'screenshot_payment',
                    'screenshot_transfer', 'admin_id', 'created_at', 'completed_at']

    def create_trade_order(self, buyer_id, buyer_name, customer_id, order_type, asset_type,
                           network, account_address, payment_method, amount, currency):
        """إنشاء طلب تداول"""
        order_id = f"TRD{datetime.now().strftime('%Y%m%d%H%M%S')}"
        try:
            with open('trade_orders.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([order_id, buyer_id, buyer_name, customer_id, order_type, asset_type,
                                network, account_address, payment_method, amount, currency,
                                '', '', 'pending', '', '', '', datetime.now().strftime('%Y-%m-%d %H:%M'), ''])
            return order_id
        except Exception as e:
            logger.error(f"خطأ في إنشاء طلب تداول: {e}")
            return None

    def get_trade_order(self, order_id):
        """جلب طلب تداول بالمعرف"""
        try:
            with open('trade_orders.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == order_id:
                        return row
        except:
            pass
        return None

    def get_pending_trade_orders(self):
        """جلب كل طلبات التداول المعلقة (للأدمن)"""
        orders = []
        try:
            with open('trade_orders.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') not in ('completed', 'rejected', 'cancelled'):
                        orders.append(row)
        except:
            pass
        return orders

    def update_trade_order(self, order_id, **kwargs):
        """تحديث حقل في طلب تداول"""
        try:
            rows = []
            with open('trade_orders.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row['id'] == order_id:
                        for k, v in kwargs.items():
                            if k in row:
                                row[k] = str(v)
                    rows.append(row)
            with open('trade_orders.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث طلب تداول: {e}")
            return False

    def show_trade_panel(self, message):
        """لوحة التداول للعميل"""
        user = self.find_user(message['from']['id'])
        lang = user.get('language', 'ar') if user else 'ar'

        text = (
            f"💱 <b>بيع وشراء USDT / MoneyGo</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>شراء</b> — اشترِ USDT أو MoneyGo\n"
            f"💰 <b>بيع</b> — بِع USDT أو MoneyGo\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"اختر العملية:"
        )
        inline_btns = [
            [{'text': '📦 شراء', 'callback_data': 'trade_buy'},
             {'text': '💰 بيع', 'callback_data': 'trade_sell'}],
            [{'text': '🔙 رجوع', 'callback_data': 'trade_back_main'}]
        ]
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def start_trade_buy(self, chat_id, user_id):
        """بدء تدفق الشراء"""
        self.send_inline_message(chat_id,
            "📦 <b>شراء USDT / MoneyGo</b>\n\n"
            "اختر العملة الرقمية:",
            [
                [{'text': '🪙 USDT', 'callback_data': 'trade_asset_usdt'},
                 {'text': '💎 MoneyGo', 'callback_data': 'trade_asset_moneygo'}],
                [{'text': '🔙 رجوع', 'callback_data': 'trade_back_panel'}]
            ])

    def start_trade_sell(self, chat_id, user_id):
        """بدء تدفق البيع — العميل يبيع USDT/MoneyGo للأدمن"""
        self.send_inline_message(chat_id,
            "💰 <b>بيع USDT / MoneyGo</b>\n\n"
            "اختر العملة الرقمية التي تريد بيعها:",
            [
                [{'text': '🪙 USDT', 'callback_data': 'trade_sell_asset_usdt'},
                 {'text': '💎 MoneyGo', 'callback_data': 'trade_sell_asset_moneygo'}],
                [{'text': '🔙 رجوع', 'callback_data': 'trade_back_panel'}]
            ])

    # ==================== 🎡 عجلة الحظ ====================

    def show_wheel_panel(self, message):
        """لوحة صيد الجوائز للعميل"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        lang = user.get('language', 'ar')

        # فحص الهاتف الحقيقي
        phone_verified = user.get('phone_verified', 'unknown')
        user_phone = user.get('phone', '')
        has_real_phone = phone_verified == 'yes' or (user_phone and user_phone.startswith('+'))
        if not has_real_phone:
            inline_btns = [[{'text': '📱 تسجيل برقم هاتفي الحقيقي', 'callback_data': 'verify_phone_start'}]]
            inline_btns.append([{'text': self.tr('a0142_العودة', lang), 'callback_data': 'wheel_back_main'}])
            self.send_inline_message(message['chat']['id'],
                f"🎯 <b>صيد الجوائز</b>\n\n⚠️ <b>يجب التسجيل برقم هاتف حقيقي للمشاركة</b>\n\n"
                f"📱 اضغط الزر بالأسفل لتسجيل رقم هاتفك الحقيقي",
                inline_btns)
            return

        # جلب الجولة النشطة
        active_round = None
        try:
            with open('wheel_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'active':
                        active_round = row
                        break
        except:
            pass

        if not active_round:
            self.send_message(message['chat']['id'],
                self.tr('a0811_عجلة_الحظ', lang),
                self.main_keyboard(lang, message['from']['id']))
            return

        # عد دورات المستخدم + إجمالي المشاركين
        my_spins = 0
        total_participants = set()
        try:
            with open('wheel_spins.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('round_id') == active_round['id']:
                        total_participants.add(row.get('user_id', ''))
                        if row.get('user_id') == str(message['from']['id']):
                            my_spins += 1
        except:
            pass

        max_spins = int(active_round.get('max_spins_per_user', 1))
        prizes = active_round.get('prizes', '').split('|')

        # قراءة الرصيد من المحفظة
        wallet_balance = 0.0
        if self.svrp:
            try:
                wallets = self.svrp.get_all_wallets()
                for w in wallets:
                    if str(w.get('telegram_id', '')) == str(message['from']['id']):
                        wallet_balance = float(w.get('balance', 0) or 0)
                        break
            except:
                pass

        spin_cost = float(active_round.get('spin_cost', 0) or 0)
        currency = active_round.get('currency', 'SAR')
        free_spins_left = max(0, max_spins - my_spins)
        can_spin_paid = spin_cost > 0 and wallet_balance >= spin_cost

        # قراءة إعدادات اللعبة من الجولة
        game_speed_ms = int(active_round.get('game_speed_ms', 2500) or 2500)
        max_relocations = int(active_round.get('max_relocations', 1) or 1)
        speed_sec = game_speed_ms / 1000.0
        reloc_text = "مرة" if max_relocations == 1 else "مرتين"

        text = self.ui_card_pro(
            f"صيد الجوائز — {active_round.get('name', '')}",
            icon='🎯',
            items=[
                {'label': 'المشاركين', 'value': str(len(total_participants)), 'icon': '👥', 'highlight': True},
            ]
        )
        text += "\n"
        # الجوائز — صفوف عادية
        for i, prize in enumerate(prizes, 1):
            text += f"  {i}️⃣ {prize.strip()}\n"
        text += self.ui_card_section('معلومات اللعب', '📊', color='blue')
        text += self.ui_card_row('دوراتك المجانية', str(free_spins_left), '🎯', lang=lang) + "\n"
        if spin_cost > 0:
            text += self.ui_card_row('رصيدك', f"{wallet_balance:.0f} {currency}", '💰', lang=lang) + "\n"
            text += self.ui_card_row('دورة إضافية', f"{spin_cost:.0f} {currency}", '🎟️', lang=lang) + "\n"
        text += self.ui_card_row('سرعة اللعبة', f"{speed_sec:.1f} ثانية", '⚡', highlight=True, lang=lang) + "\n"
        text += self.ui_card_row('هروب الهدية', reloc_text, '🏃', highlight=True, lang=lang) + "\n"
        text += self.ui_card_section('كيف تلعب؟', '⚡', color='red')
        text += "  🎁 اضغط <b>ابدأ</b> → تظهر أزرار\n"
        text += f"  ⚡ اصطد الهدية بسرعة في <b>{speed_sec:.1f} ثانية</b>\n"
        text += f"  🏃 الهدية تهرب <b>{reloc_text}</b> — اتبعها!\n"
        text += f"  🎯 الهدايا الحقيقية مخلوطة مع فخاخ!\n\n"

        inline_btns = []
        if free_spins_left > 0 or can_spin_paid:
            inline_btns.append([{'text': '🎮 ابدأ — اصطد هديتك!', 'callback_data': 'wheel_start_game'}])
            inline_btns.append([{'text': self.tr('a0299_تحديث', lang), 'callback_data': 'wheel_refresh'},
                                {'text': self.tr('a0142_العودة', lang), 'callback_data': 'wheel_back_main'}])
            self.send_inline_message(message['chat']['id'], text, inline_btns)
        else:
            text += self.tr('a0814_وصلت_للحد', lang)
            inline_btns.append([{'text': '🔄 تحديث', 'callback_data': 'wheel_refresh'}])
            inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'wheel_back_main'}])
            self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_games_hub(self, message):
        """مركز الألعاب — يفتح WebApp خارجي مرتبط بمحفظة العميل"""
        try:
            user = self.find_user(message['from']['id'])
            if not user:
                self.handle_start(message)
                return
            lang = user.get('language', 'ar')
            user_id = message['from']['id']
            currency = user.get('currency', 'SAR')

            # قراءة رصيد محفظة الألعاب
            wallet_balance = 0.0
            try:
                from game_engine import GameManager
                gm = GameManager()
                wallet_balance = gm.get_balance(user_id)
            except Exception as e:
                logger.error(f"games_hub balance error: {e}")
                if self.svrp:
                    try:
                        for w in self.svrp.get_all_wallets():
                            if str(w.get('telegram_id', '')) == str(user_id):
                                wallet_balance = float(w.get('balance', 0) or 0)
                                break
                    except:
                        pass

            # قراءة شريحة اللاعب
            player_segment = 'جديد'
            is_vex_partner = False
            try:
                from player_tracker import PlayerTracker
                pt = PlayerTracker()
                profile = pt.get_profile(user_id)
                segment = pt.get_segment(profile)
                seg_labels = {
                    'new': '🟢 جديد', 'winner': '🔴 رابح', 'loser': '🟡 خاسر',
                    'hot': '🔥 ساخن', 'churning': '⚠️ قد يغادر',
                    'vip': '💎 VIP', 'regular': '👤 عادي'
                }
                player_segment = seg_labels.get(segment, '👤 عادي')
                is_vex_partner = profile.get('is_vex_partner') == 'yes'
                if 'currency' not in profile or profile.get('currency') != currency:
                    pt._save_profile({**profile, 'currency': currency})
            except:
                pass

            text = self.ui_card_pro('مركز الألعاب', '🎮', items=[
                {'label': 'رصيدك', 'value': f"{wallet_balance:.0f} {currency}", 'icon': '💰', 'highlight': True},
                {'label': 'شريحتك', 'value': player_segment, 'icon': '📊'},
            ])
            text += "\n⚡ كل لعبة مرتبطة بمحفظتك\n"
            text += f"💰 عملتك: {currency}\n"
            if is_vex_partner:
                text += "💎 تعويض متاح أثناء اللعب!\n"

            base_url = self.get_setting('dashboard_url') or 'https://vex.deals'

            # Generate encrypted session for this user (no uid in URL — ALWAYS encrypted)
            import urllib.request, urllib.parse, json as _json
            encrypted_session = ''
            for _retry in range(3):
                try:
                    sess_data = json.dumps({"uid": str(user_id)}).encode('utf-8')
                    sess_req = urllib.request.Request(
                        f"{base_url}/api/auth/create-token?uid={user_id}",
                        data=sess_data,
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    sess_resp = urllib.request.urlopen(sess_req, timeout=8)
                    sess_result = _json.loads(sess_resp.read().decode())
                    encrypted_session = sess_result.get('s', '')
                    if encrypted_session:
                        break
                except Exception as e:
                    logger.error(f"Session generation attempt {_retry+1} failed: {e}")
                    import time as _t; _t.sleep(1)

            if encrypted_session:
                games_url = f"{base_url}/webapp/games?s={encrypted_session}&lang={lang}&currency={currency}"
            else:
                # All retries failed — still use encrypted (generate locally)
                import secrets as _sec, base64 as _b64, time as _t2
                _ts = str(int(_t2.time()))
                _raw = f"{user_id}:{_ts}"
                _key = _sec.token_hex(16)
                _enc = ''.join(chr(ord(c) ^ ord(_key[i % len(_key)])) for i, c in enumerate(_raw))
                _b64enc = _b64.urlsafe_b64encode(_enc.encode('latin-1')).decode().rstrip('=')
                logger.warning(f"All session retries failed — generated local encrypted fallback for {user_id}")
                games_url = f"{base_url}/webapp/games?s=LOCAL_{_b64enc}&lang={lang}&currency={currency}"

            kb = {'inline_keyboard': [
                [{'text': '🎮 ادخل مركز الألعاب', 'url': games_url}],
                [{'text': '💰 إيداع للمحفظة', 'callback_data': 'game_wallet_deposit'},
                 {'text': '💸 سحب من المحفظة', 'callback_data': 'game_wallet_withdraw'}]
            ]}
            result = self.api_call('sendMessage', {
                'chat_id': message['chat']['id'],
                'text': text,
                'parse_mode': 'HTML',
                'reply_markup': kb
            })
            if not result or not result.get('ok'):
                logger.error(f"games_hub sendMessage failed: {result.get('description', 'unknown') if result else 'no response'}")
            else:
                logger.info(f"games_hub sent to {user_id}")
        except Exception as e:
            logger.error(f"show_games_hub crashed: {e}")

    def show_more_menu(self, message):
        """قائمة المزيد — أزرار إضافية منظمة"""
        user = self.find_user(message['from']['id'])
        lang = user.get('language', 'ar') if user else 'ar'

        all_langs = self.get_supported_languages()
        requests_btn = self.tr('my_requests', lang)
        help_btn = self.tr('help_btn_label', lang) if self.tr('help_btn_label', lang) != 'help_btn_label' else self.tr('a0231_مساعدة', lang)
        currency_btn = self.tr('change_currency', lang)
        complaint_btn = self.tr('complaint', lang)
        notif_btn = self.tr('notif_btn', lang) if self.tr('notif_btn', lang) != 'notif_btn' else self.tr('a0228_إشعاراتي', lang)

        text = (
            f"⚙️ <b>المزيد</b>\n\n"
            f"اختر ما تريد:"
        )
        inline_btns = [
            [{'text': requests_btn}, {'text': currency_btn}],
            [{'text': notif_btn}, {'text': complaint_btn}],
            [{'text': help_btn}, {'text': self.tr('main_menu', lang)}],
        ]
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_wheel_admin(self, message):
        """لوحة إدارة صيد الجوائز للأدمن"""
        user_id = message['from']['id']
        admin_obj = self.find_user(user_id)
        lang = admin_obj.get('language', 'ar') if admin_obj else 'ar'

        rounds_list = []
        try:
            with open('wheel_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rounds_list = list(reader)
        except:
            pass

        active = [r for r in rounds_list if r.get('status') == 'active']

        # عد الهدايا المتاحة
        gift_count = 0
        try:
            with open('wheel_gifts.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('is_active') == 'yes':
                        gift_count += 1
        except:
            pass

        text = f"🎯 <b>صيد الجوائز — الإدارة</b>\n\n"
        text += f"📊 جولات نشطة: <code>{len(active)}</code>\n"
        text += f"🎁 هدايا متاحة: <code>{gift_count}</code>\n\n"

        inline_btns = []
        if active:
            text += "━━━━━━━━━━━━━━━━━━\n"
            for r in active:
                spin_count = 0
                try:
                    with open('wheel_spins.csv', 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for s in reader:
                            if s.get('round_id') == r['id']:
                                spin_count += 1
                except:
                    pass
                text += f"🎯 <b>{r.get('name', '')}</b>\n"
                text += f"  🆔 <code>{r['id']}</code>\n"
                text += f"  🎁 {r.get('prizes', '')}\n"
                text += f"  🎫 دورات: <code>{spin_count}</code>\n"
                text += f"  💰 تكلفة: <code>{r.get('spin_cost', '0')} {r.get('currency', 'SAR')}</code>\n\n"
                inline_btns.append([{'text': f"🏁 إنهاء: {r.get('name', '')}", 'callback_data': f'wheel_end_{r["id"]}'}])

        inline_btns.append([{'text': '➕ إنشاء جولة', 'callback_data': 'wheel_create'}])
        inline_btns.append([{'text': '🎁 إدارة الهدايا', 'callback_data': 'wheel_gifts_menu'}])
        inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'app_back_admin'}])

        if not active:
            text += "📭 لا توجد جولات نشطة"

        self.send_inline_message(message['chat']['id'], text, inline_btns)

    # ==================== 🎰 اليانصيب ====================

    def show_lottery_panel(self, message):
        """لوحة اليانصيب للعميل — تصميم احترافي مع FOMO وأرقام حقيقية"""
        user = self.find_user(message['from']['id'])
        if not user:
            self.handle_start(message)
            return
        lang = user.get('language', 'ar')

        # جلب الجولة النشطة
        active_round = None
        try:
            with open('lottery_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'active':
                        active_round = row
                        break
        except:
            pass

        if not active_round:
            self.send_message(message['chat']['id'],
                "🎰 <b>يانصيب</b>\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📭 لا توجد جولة نشطة حالياً\n"
                "⏳ ترقبوا الجولة القادمة!\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "💡 سيتم إشعارك فور بدء جولة جديدة",
                self.main_keyboard(lang, message['from']['id']))
            return

        # قراءة كل البيانات الحقيقية
        all_tickets = []
        unique_participants = set()
        my_tickets = []
        recent_buyers = []
        try:
            with open('lottery_tickets.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('round_id') == active_round['id']:
                        all_tickets.append(row)
                        unique_participants.add(row.get('user_id', ''))
                        if row.get('user_id') == str(message['from']['id']):
                            my_tickets.append(row)
                        if row.get('payment_verified') == 'yes':
                            recent_buyers.append(row)
        except:
            pass

        verified_tickets = [t for t in all_tickets if t.get('payment_verified') == 'yes']
        tickets_sold = len(verified_tickets)
        participants_count = len(unique_participants)

        # الأرقام الحقيقية من بيانات الأدمن
        ticket_price = float(active_round.get('ticket_price', 0))
        currency = active_round.get('currency', 'SAR')
        prize_pool = ticket_price * tickets_sold
        admin_pct = float(active_round.get('admin_profit_pct', 0))
        net_prize = prize_pool * (1 - admin_pct / 100)
        winner_count = int(active_round.get('winner_count', 1))
        max_per_user = int(active_round.get('max_tickets_per_user', 1))
        draw_time = active_round.get('draw_time', '')
        round_name = active_round.get('name', '')

        # حساب العد التنازلي
        countdown_text = ''
        if draw_time:
            try:
                draw_dt = datetime.strptime(draw_time, '%Y-%m-%d %H:%M')
                now = datetime.now()
                if draw_dt > now:
                    diff = draw_dt - now
                    days = diff.days
                    hours = diff.seconds // 3600
                    minutes = (diff.seconds % 3600) // 60
                    if days > 0:
                        countdown_text = self.tr('a0818_السحب_بعد', lang, days=days, hours=hours)
                    elif hours > 0:
                        countdown_text = self.tr('a0819_السحب_بعد', lang, hours=hours, minutes=minutes)
                    else:
                        countdown_text = self.tr('a0820_السحب_بعد', lang, minutes=minutes)
                else:
                    countdown_text = self.tr('a0821_السحب_قريباً', lang)
            except:
                countdown_text = self.tr('a0822_موعد_السحب', lang, draw_time=draw_time)

        # حساب نسب التوزيع — أرقام حقيقية
        if winner_count == 1:
            shares = [100]
            share_labels = ['100%']
        elif winner_count == 2:
            shares = [60, 40]
            share_labels = ['60%', '40%']
        elif winner_count == 3:
            shares = [50, 30, 20]
            share_labels = ['50%', '30%', '20%']
        else:
            extra = round(20 / (winner_count - 3), 1)
            shares = [40, 25, 15] + [round(100 * 0.2 / (winner_count - 3))] * (winner_count - 3)
            share_labels = ['40%', '25%', '15%'] + [f'{extra}%'] * (winner_count - 3)

        rank_emojis = ['🥇', '🥈', '🥉'] + ['🏅'] * max(0, winner_count - 3)

        # حساب فرصة الفوز — فقط التذاكر الموثقة
        my_verified_tickets = [t for t in my_tickets if t.get('payment_verified') == 'yes']
        my_ticket_count = len(my_verified_tickets)
        total_odds = 0
        if tickets_sold > 0 and my_ticket_count > 0:
            total_odds = (my_ticket_count / tickets_sold) * 100

        # === بناء النص الاحترافي — تصميم كرت ثنائي الألوان ===
        text = self.ui_card_pro(round_name, icon='🎰', items=[
            {'label': 'الجائزة الكبرى', 'value': f"{net_prize:.0f} {currency}", 'icon': '🔥', 'highlight': True},
        ])
        text += "\n"

        # العد التنازلي
        if countdown_text:
            text += self.ui_card_alert(countdown_text, '⏰') + "\n\n"

        # إحصائيات — صفوف بارزة (code block)
        text += self.ui_card_row('المشاركين', f"{participants_count} شخص", '👥', highlight=True, lang=lang) + "\n"
        text += self.ui_card_row('التذاكر المباعة', str(tickets_sold), '🎫', highlight=True, lang=lang) + "\n"
        text += self.ui_card_row('سعر التذكرة', f"{ticket_price:.0f} {currency}", '🎟️', lang=lang) + "\n"
        text += self.ui_card_row('عدد الفائزين', str(winner_count), '🏆', lang=lang) + "\n"

        # شريط التقدم
        if tickets_sold > 0:
            text += f"📊 <code>{self.ui_progress_bar(tickets_sold, max(tickets_sold * 2, 20))}</code>\n"

        text += self.ui_card_section('توزيع الجوائز', '💰', color='blue')
        text += self.tr('a0824_كل_تذكرة', lang, ticket_price=ticket_price, currency=currency)
        if admin_pct > 0:
            text += self.tr('a0825_رسوم_الإدارة', lang, admin_pct=admin_pct)
        text += f"💎 للمشاركين: <code>{100 - admin_pct:.0f}%</code>\n\n"

        for i in range(winner_count):
            emoji = rank_emojis[i] if i < len(rank_emojis) else '🏅'
            prize_amount = net_prize * shares[i] / 100
            text += self.ui_card_row(f"الفائز #{i+1}", f"{share_labels[i]} ← {prize_amount:.0f} {currency}", emoji, lang=lang) + "\n"

        # تذاكري
        if my_ticket_count > 0:
            text += self.ui_card_section('تذاكري', '🍀', color='red')
            text += self.tr('a0826_أرقامك_المحظوظة', lang, my_ticket_count=my_ticket_count)
            for t in my_verified_tickets:
                tn = t.get('ticket_number', '')
                if tn:
                    text += f"  🎫 <code>#{tn}</code>\n"
            if total_odds > 0:
                text += self.tr('a0827_فرصة_فوزك', lang, total_odds=total_odds)
                text += self.tr('a0828_كلما_زادت', lang)

        # آخر المشترين
        if len(recent_buyers) >= 2:
            text += self.ui_card_section('آخر المشاركين', '🟢', color='blue')
            for buyer in recent_buyers[-3:]:
                name = buyer.get('user_name', self.tr('a0060_مستخدم', lang))
                if name and len(name) > 15:
                    name = name[:12] + '...'
                text += f"  • {name} 🎫\n"

        text += "<b>━━━━━━━━━━━━━━━━━━</b>\n"

        # أزرار الإجراءات
        inline_btns = []
        phone_verified = user.get('phone_verified', 'unknown')
        if phone_verified == 'yes':
            if my_ticket_count < max_per_user:
                remaining = max_per_user - my_ticket_count
                inline_btns.append([{'text': f'🎫 شراء تذكرة ({remaining} متبقية)',
                                     'callback_data': f'lot_buy_{active_round["id"]}'}])
            else:
                text += self.tr('a0830_وصلت_للحد', lang, max_per_user=max_per_user)
        else:
            text += self.tr('a0831_سجّل_برقم', lang)
            inline_btns.append([{'text': '📱 تسجيل برقم هاتفي الحقيقي', 'callback_data': 'verify_phone_start'}])

        inline_btns.append([{'text': '🔄 تحديث الأرقام', 'callback_data': 'lot_refresh'}])
        inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'lot_back_main'}])
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_lottery_admin(self, message):
        """لوحة إدارة اليانصيب — تحكم كامل"""
        rounds_list = []
        try:
            with open('lottery_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rounds_list = list(reader)
        except:
            pass

        active = [r for r in rounds_list if r.get('status') == 'active']
        completed = [r for r in rounds_list if r.get('status') == 'completed']

        # إحصائيات شاملة
        total_revenue = 0
        total_profit = 0
        total_tickets_all = 0
        for r in completed:
            try:
                tc = 0
                with open('lottery_tickets.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for t in reader:
                        if t.get('round_id') == r.get('id') and t.get('payment_verified') == 'yes':
                            tc += 1
                price = float(r.get('ticket_price', 0))
                admin_pct = float(r.get('admin_profit_pct', 0))
                total_revenue += price * tc
                total_profit += price * tc * admin_pct / 100
                total_tickets_all += tc
            except:
                pass

        text = (
            f"🎰 <b>إدارة اليانصيب</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>الإحصائيات</b>\n"
            f"🎯 نشطة: <code>{len(active)}</code> | ✅ مكتملة: <code>{len(completed)}</code>\n"
            f"💰 إجمالي الإيرادات: <code>{total_revenue:.0f}</code>\n"
            f"🏢 إجمالي الأرباح: <code>{total_profit:.0f}</code>\n"
            f"🎫 إجمالي التذاكر: <code>{total_tickets_all}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

        inline_btns = []

        if active:
            text += self.tr('a0832_الجولات_النشطة', 'ar')
            for r in active:
                # عد التذاكر الموثقة + المشاركين
                verified_count = 0
                pending_count = 0
                participants = set()
                try:
                    with open('lottery_tickets.csv', 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for t in reader:
                            if t.get('round_id') == r['id']:
                                participants.add(t.get('user_id', ''))
                                if t.get('payment_verified') == 'yes':
                                    verified_count += 1
                                elif t.get('payment_verified') == 'pending_admin':
                                    pending_count += 1
                except:
                    pass

                price = float(r.get('ticket_price', 0))
                admin_pct = float(r.get('admin_profit_pct', 0))
                pool = price * verified_count
                profit = pool * admin_pct / 100
                net = pool - profit

                text += (
                    f"\n🎰 <b>{r.get('name', '')}</b>\n"
                    f"  🆔 <code>{r['id']}</code>\n"
                    f"  🎫 موثقة: <code>{verified_count}</code>"
                )
                if pending_count > 0:
                    text += self.tr('a0833_معلقة', 'ar', pending_count=pending_count)
                text += (
                    f"\n  👥 مشاركين: <code>{len(participants)}</code>\n"
                    f"  💰 الجائزة: <code>{net:.0f}</code> {r.get('currency', '')}\n"
                    f"  🏢 ربحك: <code>{profit:.0f}</code> {r.get('currency', '')}\n"
                    f"  ⏰ السحب: {r.get('draw_time', '—')}\n"
                )

                # أزرار لكل جولة
                row_btns = [{'text': f'🎲 سحب', 'callback_data': f'lot_draw_{r["id"]}'}]
                if pending_count > 0:
                    row_btns.append({'text': f'⏳ موافقة ({pending_count})', 'callback_data': f'lot_pending_{r["id"]}'})
                row_btns.append({'text': '🎫 تذاكر', 'callback_data': f'lot_tickets_{r["id"]}'})
                inline_btns.append(row_btns)
                inline_btns.append([
                    {'text': '✏️ تعديل', 'callback_data': f'lot_edit_{r["id"]}'},
                    {'text': '❌ إلغاء', 'callback_data': f'lot_cancel_{r["id"]}'},
                ])

        inline_btns.append([{'text': '➕ إنشاء جولة جديدة', 'callback_data': 'lot_create'}])

        if completed:
            text += f"\n━━━━━━━━━━━━━━━━━━\n📜 <b>الجولات المكتملة:</b> {len(completed)}\n"
            for r in completed[-3:]:
                text += f"  ✅ {r.get('name', '')} — {r.get('draw_time', '')}\n"
            inline_btns.append([{'text': '📜 كل الجولات', 'callback_data': 'lot_history'}])

        inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'app_back_admin'}])
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def execute_lottery_draw(self, chat_id, admin_id, round_id):
        """تنفيذ السحب — خوارزمية عادلة + seed commitment + بدون blocking"""
        import random as _r
        import hashlib
        import threading

        admin_obj = self.find_user(admin_id)
        lang = admin_obj.get('language', 'ar') if admin_obj else 'ar'

        # قراءة الجولة
        round_data = None
        try:
            with open('lottery_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == round_id:
                        round_data = row
                        break
        except:
            pass

        if not round_data:
            self.send_message(chat_id, self.tr('a0488_الجولة_غير', lang))
            return

        # قراءة كل التذاكر — فقط الموثقة (payment_verified = yes)
        tickets = []
        try:
            with open('lottery_tickets.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('round_id') == round_id and row.get('payment_verified') == 'yes':
                        tickets.append(row)
        except:
            pass

        if not tickets:
            self.send_message(chat_id, self.tr('a0834_لا_توجد', lang))
            return

        winner_count = int(round_data.get('winner_count', 1))
        if winner_count > len(tickets):
            winner_count = len(tickets)

        # === Provably Fair: seed commitment ===
        # 1. توليد server seed قبل السحب
        server_seed = secrets.token_hex(16)
        server_seed_hash = hashlib.sha256(server_seed.encode()).hexdigest()

        # 2. إعلان hash للشفافية
        self.send_message(chat_id,
            f"🎰 <b>جارٍ السحب...</b>\n\n"
            f"🎲 التذاكر: <code>{len(tickets)}</code>\n"
            f"🏆 الفائزون: <code>{winner_count}</code>\n"
            f"🔐 Seed Hash: <code>{server_seed_hash[:16]}...</code>\n\n"
            f"⚡ جارٍ اختيار الفائزين...")

        # === بدون time.sleep — نتيجة فورية ===
        # 3. توليد seed من server_seed + round_id + ticket_count
        seed_string = f"{server_seed}_{round_id}_{len(tickets)}"
        seed = int(hashlib.sha256(seed_string.encode()).hexdigest(), 16)
        _r.seed(seed)

        shuffled = tickets.copy()
        _r.shuffle(shuffled)
        winners = shuffled[:winner_count]

        # حساب الجوائز
        ticket_price = float(round_data.get('ticket_price', 0))
        total_pool = ticket_price * len(tickets)
        admin_pct = float(round_data.get('admin_profit_pct', 0))
        admin_profit = total_pool * admin_pct / 100
        net_prize = total_pool - admin_profit

        # توزيع الجوائز
        if winner_count == 1:
            shares = [1.0]
        elif winner_count == 2:
            shares = [0.6, 0.4]
        elif winner_count == 3:
            shares = [0.5, 0.3, 0.2]
        else:
            shares = [0.4, 0.25, 0.15] + [0.2 / (winner_count - 3)] * (winner_count - 3)

        # === إعلان الفائزين ===
        results_text = (
            f"🎉🎉🎉 <b>النتائج النهائية!</b> 🎉🎉🎉\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎰 الجولة: <b>{round_data.get('name', '')}</b>\n"
            f"🎫 التذاكر المباعة: <code>{len(tickets)}</code>\n"
            f"💰 إجمالي الجائزة: <code>{net_prize:.2f}</code> {round_data.get('currency', '')}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
        )

        for i, winner in enumerate(winners):
            rank = i + 1
            prize = net_prize * shares[i]
            rank_emojis = ['🥇', '🥈', '🥉'] + ['🏅'] * (winner_count - 3)
            emoji = rank_emojis[i] if i < len(rank_emojis) else '🏅'

            results_text += self.tr('a0836_الفائز', lang, emoji=emoji, rank=rank)
            results_text += f"👤 {winner.get('user_name', '')}\n"
            results_text += f"🎫 التذكرة: <code>#{winner.get('ticket_number', '')}</code>\n"
            results_text += f"💰 الجائزة: <code>{prize:.2f}</code> {round_data.get('currency', '')}\n\n"

            # حفظ الفائز
            try:
                with open('lottery_winners.csv', 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([f"WIN{str(int(datetime.now().timestamp()))[-6:]}_{rank}",
                                   round_id, winner.get('user_id', ''), winner.get('user_name', ''),
                                   winner.get('ticket_number', ''), f"{prize:.2f}",
                                   round_data.get('currency', ''), str(rank),
                                   datetime.now().strftime('%Y-%m-%d %H:%M')])
            except:
                pass

            # إضافة الجائزة للمحفظة المجمدة
            if self.svrp and winner.get('user_id'):
                try:
                    self.svrp.add_frozen_balance(str(winner.get('user_id', '')), prize)
                except Exception as e:
                    logger.error(f"خطأ في إضافة جائزة اليانصيب: {e}")

            # إشعار الفائز
            try:
                uid = winner.get('user_id', '0')
                if uid and uid != '0':
                    self.notify_user(int(uid),
                        f"🎉 <b>مبروك! ربحت في اليانصيب!</b>\n\n"
                        f"{emoji} المرتبة: #{rank}\n"
                        f"🎫 التذكرة: <code>#{winner.get('ticket_number', '')}</code>\n"
                        f"💰 الجائزة: <code>{prize:.2f}</code> {round_data.get('currency', '')}\n\n"
                        f"💎 تم إضافة الجائزة لرصيدك المجمد")
            except:
                pass

        results_text += f"━━━━━━━━━━━━━━━━━━\n"
        results_text += f"📊 ربح الأدمن: <code>{admin_profit:.2f}</code> {round_data.get('currency', '')}\n"
        results_text += f"🔐 Server Seed: <code>{server_seed}</code>\n"
        results_text += f"🔐 Hash: <code>{server_seed_hash[:32]}...</code>\n"
        results_text += self.tr('a0837_للفائزين', lang)

        self.send_message(chat_id, results_text, self.admin_keyboard())

        # تسجيل السحب
        logger.info(f"Lottery draw executed — Round: {round_id}, Admin: {admin_id}, Tickets: {len(tickets)}, Winners: {winner_count}")

        # بث النتائج لكل المستخدمين — في thread منفصل
        broadcast_text = (
            f"🎉 <b>نتائج اليانصيب!</b>\n\n"
            f"🎰 {round_data.get('name', '')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        for i, winner in enumerate(winners):
            rank_emojis = ['🥇', '🥈', '🥉'] + ['🏅'] * (winner_count - 3)
            emoji = rank_emojis[i] if i < len(rank_emojis) else '🏅'
            prize = net_prize * shares[i]
            broadcast_text += f"{emoji} {winner.get('user_name', '')} — <code>#{winner.get('ticket_number', '')}</code> — {prize:.2f} {round_data.get('currency', '')}\n"

        def broadcast_results():
            """بث النتائج في thread منفصل — بدون blocking"""
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        tid = row.get('telegram_id', '')
                        if tid:
                            try:
                                self.send_message(int(tid), broadcast_text, None)
                            except:
                                pass
            except:
                pass

        t = threading.Thread(target=broadcast_results, daemon=True)
        t.start()

        # تحديث حالة الجولة
        try:
            rows = []
            with open('lottery_rounds.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row['id'] == round_id:
                        row['status'] = 'completed'
                    rows.append(row)
            with open('lottery_rounds.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except:
            pass

    def show_unified_orders(self, message):
        """لوحة موحدة لكل الطلبات المعلقة — إيداع + سحب + تداول + استرداد"""
        all_orders = []

        # 1) طلبات الإيداع والسحب المعلقة
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') in ('pending', 'pending_code_verification'):
                        all_orders.append({
                            'id': row['id'],
                            'type': 'deposit' if row['type'] == 'deposit' else 'withdraw',
                            'icon': '💰' if row['type'] == 'deposit' else '💸',
                            'name': row.get('name', ''),
                            'amount': row.get('amount', ''),
                            'currency': row.get('currency', 'SAR'),
                            'company': row.get('company', ''),
                            'status': row.get('status', ''),
                            'date': row.get('date', ''),
                            'callback': f'approve_{row["id"]}' if row['status'] == 'pending' else f'verify_code_{row["id"]}',
                            'callback_view': f'uni_view_trans_{row["id"]}'
                        })
        except:
            pass

        # 2) طلبات التداول المعلقة
        try:
            with open('trade_orders.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') not in ('completed', 'rejected', 'cancelled'):
                        all_orders.append({
                            'id': row['id'],
                            'type': 'trade',
                            'icon': '💱',
                            'name': row.get('buyer_name', ''),
                            'amount': row.get('amount', ''),
                            'currency': row.get('currency', ''),
                            'company': f"{row.get('asset_type', '').upper()} {row.get('order_type', '')}",
                            'status': row.get('status', ''),
                            'date': row.get('created_at', ''),
                            'callback_view': f'trade_admin_view_{row["id"]}'
                        })
        except:
            pass

        # 3) طلبات الاسترداد المعلقة
        if self.svrp:
            try:
                for row in self.svrp._read_csv('recovery_requests.csv'):
                    if row.get('status') == 'pending':
                        all_orders.append({
                            'id': row['id'],
                            'type': 'recovery',
                            'icon': '📸',
                            'name': row.get('user_id', ''),
                            'amount': '',
                            'currency': '',
                            'company': 'استرداد',
                            'status': row.get('status', ''),
                            'date': row.get('created_at', ''),
                            'callback_view': f'svrp_recovery_approve_{row["id"]}'
                        })
            except:
                pass

        # 4) طلبات المكافآت المعلقة
        if self.svrp:
            try:
                for row in self.svrp._read_csv('bonus_requests.csv'):
                    if row.get('status') == 'pending':
                        all_orders.append({
                            'id': row['id'],
                            'type': 'bonus',
                            'icon': '🏆',
                            'name': row.get('user_id', ''),
                            'amount': '',
                            'currency': '',
                            'company': row.get('company_name', ''),
                            'status': row.get('status', ''),
                            'date': row.get('created_at', ''),
                            'callback_view': f'svrp_bonus_approve_{row["id"]}'
                        })
            except:
                pass

        if not all_orders:
            self.send_message(message['chat']['id'],
                self.tr('a0838_لا_توجد', 'ar'),
                self.admin_keyboard())
            return

        # ترتيب حسب التاريخ (الأقدم أولاً)
        all_orders.sort(key=lambda o: o.get('date', ''))

        # بناء النص والأزرار
        text = f"📋 <b>كل الطلبات المعلقة ({len(all_orders)})</b>\n"
        text += f"━━━━━━━━━━━━━━━━━━\n\n"

        inline_btns = []
        for i, order in enumerate(all_orders, 1):
            status_short = {
                'pending': '🟡', 'pending_code_verification': '🔐',
                'admin_accepted': '🔵', 'buyer_pays': '💸',
                'buyer_sends_screenshot': '📸', 'admin_confirms_payment': '✅',
                'admin_transfers': '📤', 'admin_sends_screenshot': '📤'
            }.get(order['status'], '🟡')

            type_label = {'deposit': 'إيداع', 'withdraw': 'سحب', 'trade': 'تداول',
                         'recovery': 'استرداد', 'bonus': 'مكافأة'}.get(order['type'], '')

            text += f"{status_short} {order['icon']} <code>{order['id']}</code> | {type_label}\n"
            if order['amount']:
                text += f"   💰 {order['amount']} {order['currency']}\n"
            if order['company']:
                text += f"   🏢 {order['company']}\n"
            text += f"   👤 {order['name']}\n\n"

            inline_btns.append([{
                'text': f"{status_short} {order['icon']} {order['id']} — {type_label}",
                'callback_data': order['callback_view']
            }])

        inline_btns.append([{'text': '🔄 تحديث', 'callback_data': 'uni_refresh'}])
        inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'uni_back'}])

        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_trade_admin_queue(self, message):
        """لوحة طلبات التداول للأدمن — قائمة منظمة"""
        orders = self.get_pending_trade_orders()
        if not orders:
            self.send_message(message['chat']['id'],
                self.tr('a0839_لا_توجد', 'ar'),
                self.admin_keyboard())
            return

        text = f"💱 <b>طلبات التداول المعلقة ({len(orders)})</b>\n\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        inline_btns = []

        for order in orders:
            status = order.get('status', 'pending')
            status_icons = {
                'pending': '🟡', 'admin_accepted': '🔵', 'admin_sets_rate': '🔢',
                'buyer_pays': '💸', 'buyer_sends_screenshot': '📸',
                'admin_confirms_payment': '✅', 'admin_transfers': '📤',
                'admin_sends_screenshot': '📸'
            }
            icon = status_icons.get(status, '🟡')
            otype = self.tr('a0840_شراء', 'ar') if order.get('order_type') == 'buy' else self.tr('a0841_بيع', 'ar')
            asset = order.get('asset_type', '').upper()
            amount = order.get('amount', '')
            currency = order.get('currency', '')

            text += f"{icon} <code>{order['id']}</code> | {otype} {asset}\n"
            text += f"   💰 {amount} {currency} | 👤 {order.get('buyer_name', '')}\n"
            text += self.tr('a0842_الحالة', 'ar', status=status)

            inline_btns.append([{'text': f"{icon} {order['id']} — {otype} {asset} {amount}",
                                 'callback_data': f"trade_admin_view_{order['id']}"}])

        inline_btns.append([{'text': '🔄 تحديث', 'callback_data': 'trade_admin_refresh'},
                            {'text': '🔙 العودة', 'callback_data': 'uni_back'}])

        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def handle_trade_buy_step(self, message, state):
        """معالجة خطوات تدفق شراء العميل"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        step = state.get('step', '')

        if text in [self.tr('a0009_إلغاء', 'ar'), self.tr('a0010_إلغاء', 'ar'), self.tr('a0011_الغاء', 'ar'), '🔙']:
            if user_id in self.user_states: del self.user_states[user_id]
            self.handle_start(message)
            return

        if step == 'trade_buy_account':
            if len(text) < 3:
                self.send_message(chat_id, self.tr('a0843_العنوان_الحساب', 'ar'))
                return
            state['account_address'] = text
            state['step'] = 'trade_buy_method'
            self.user_states[user_id] = state

            # عرض وسائل الدفع النشطة (المجموعة العامة)
            methods = self.get_all_payment_methods()
            active = [m for m in methods if m.get('status') == 'active']
            if not active:
                self.send_message(chat_id, self.tr('a0844_لا_توجد', 'ar'))
                return
            inline_btns = []
            for m in active:
                icon = m.get('icon', '💳') or '💳'
                inline_btns.append([{'text': f"{icon} {m['method_name']} — {m.get('account_data', '')}",
                                     'callback_data': f"trade_method_{m['id']}"}])
            inline_btns.append([{'text': '🔙 إلغاء', 'callback_data': 'trade_buy_cancel'}])
            self.send_inline_message(chat_id, self.tr('a0578_اختر_وسيلة', 'ar'), inline_btns)

        elif step == 'trade_buy_amount':
            try:
                amount = float(text)
                if amount <= 0:
                    self.send_message(chat_id, self.tr('a0845_المبلغ_يجب', 'ar'))
                    return
            except ValueError:
                self.send_message(chat_id, self.tr('a0846_اكتب_مبلغاً', 'ar'))
                return
            state['amount'] = amount
            state['step'] = 'trade_buy_currency'
            self.user_states[user_id] = state

            # عرض قائمة العملات
            currencies = self.currencies
            inline_btns = []
            row = []
            for code, info in currencies.items():
                row.append({'text': f"{info.get('flag', '')} {code}", 'callback_data': f'trade_currency_{code}'})
                if len(row) >= 3:
                    inline_btns.append(row)
                    row = []
            if row:
                inline_btns.append(row)
            inline_btns.append([{'text': '🔙 إلغاء', 'callback_data': 'trade_buy_cancel'}])
            self.send_inline_message(chat_id, self.tr('a0847_اختر_العملة', 'ar'), inline_btns)

        elif step == 'trade_buy_currency':
            # يتم معالجته عبر callback في handle_callback_query
            pass

    def handle_trade_admin_step(self, message, state):
        """معالجة خطوات تدفق الأدمن للتداول"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        step = state.get('step', '')
        order_id = state.get('order_id', '')

        if text in [self.tr('a0009_إلغاء', 'ar'), self.tr('a0010_إلغاء', 'ar'), self.tr('a0011_الغاء', 'ar')]:
            if user_id in self.user_states: del self.user_states[user_id]
            self.show_trade_admin_queue(message)
            return

        if step == 'trade_admin_rate':
            # الأدمن يكتب: وسيلة الدفع + كمية USDT
            parts = text.split()
            if len(parts) < 2:
                self.send_message(chat_id, self.tr('a0848_الصيغة_وسيلة', 'ar'))
                return
            usdt_amount = parts[-1]
            payment_method = ' '.join(parts[:-1])
            try:
                float(usdt_amount)
            except ValueError:
                self.send_message(chat_id, self.tr('a0849_كمية_يجب', 'ar'))
                return

            self.update_trade_order(order_id,
                status='buyer_pays', usdt_amount=usdt_amount, admin_payment_method=payment_method)

            # إشعار العميل
            order = self.get_trade_order(order_id)
            if order:
                buyer_msg = (
                    f"✅ <b>تم قبول طلبك!</b>\n\n"
                    f"🆔 <code>{order_id}</code> 👈 اضغط للنسخ\n"
                    f"{'📦 شراء' if order.get('order_type') == 'buy' else '💰 بيع'} "
                    f"{'🪙 USDT' if order.get('asset_type') == 'usdt' else '💎 MoneyGo'}\n\n"
                    f"💰 المبلغ المطلوب: <code>{order.get('amount', '')}</code> {order.get('currency', '')}\n"
                    f"🏦 وسيلة الدفع: <code>{payment_method}</code>\n"
                    f"🪙 ستحصل على: <code>{usdt_amount}</code> USDT\n\n"
                    f"📤 حوّل المال إلى وسيلة الدفع أعلاه\n"
                    f"📸 ثم أرسل لقطة شاشة الدفع"
                )
                self.notify_user(int(order.get('buyer_id', 0)), buyer_msg)
                # تعيين حالة العميل لانتظار لقطة الشاشة
                self.user_states[int(order.get('buyer_id', 0))] = {
                    'step': 'trade_buyer_screenshot', 'order_id': order_id
                }

            del self.user_states[user_id]
            self.send_message(chat_id,
                f"✅ تم إرسال تعليمات الدفع للعميل\n\n"
                f"🆔 <code>{order_id}</code>\n⏳ بانتظار لقطة شاشة الدفع من العميل\n\n"
                f"📋 الطلب محفوظ — يمكنك معالجة طلبات أخرى والعودة له لاحقاً")
            # العودة للوحة الموحدة
            fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
            self.show_unified_orders(fake_msg)

        elif step == 'trade_admin_transfer':
            # الأدمن يرسل لقطة شاشة التحويل
            if 'photo' not in message:
                self.send_message(chat_id, self.tr('a0850_أرسل_لقطة', 'ar'))
                return
            photo = message['photo'][-1]
            self.update_trade_order(order_id, status='admin_sends_screenshot',
                                    screenshot_transfer=photo['file_id'])
            del self.user_states[user_id]
            # إرسال لقطة الشاشة للعميل + زر تأكيد
            order = self.get_trade_order(order_id)
            if order:
                self.notify_user(int(order.get('buyer_id', 0)),
                    f"📤 <b>تم تحويل USDT إليك!</b>\n\n"
                    f"🆔 <code>{order_id}</code> 👈 اضغط للنسخ\n"
                    f"🪙 الكمية: <code>{order.get('usdt_amount', '')}</code> USDT\n\n"
                    f"📸 لقطة شاشة التحويل:\n"
                    f"تأكد من استلام USDT ثم اضغط تأكيد")
                try:
                    self.api_call('sendPhoto', {
                        'chat_id': int(order.get('buyer_id', 0)),
                        'photo': photo['file_id'],
                        'caption': f"📸 تحويل USDT — <code>{order_id}</code>",
                        'parse_mode': 'HTML',
                        'reply_markup': self.transform_keyboard({'inline_keyboard': [
                            [{'text': '✅ تأكيد الاستلام', 'callback_data': f'trade_confirm_receipt_{order_id}'}]
                        ]})
                    })
                except:
                    pass
            self.send_message(chat_id,
                self.tr('a0535_تم_إرسال', 'ar', order_id=order_id))
            fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
            self.show_unified_orders(fake_msg)

    def get_payment_methods_by_company(self, company_id, transaction_type=None):
            """الحصول على وسائل الدفع لشركة معينة — من جدول الربط + السجل القديم"""
            methods = []
            seen_ids = set()
            # 1) من جدول الربط الجديد
            linked_ids = self.get_linked_method_ids(company_id)
            if linked_ids:
                try:
                    with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row['id'] in linked_ids and row.get('status') == 'active' and row['id'] not in seen_ids:
                                methods.append(row)
                                seen_ids.add(row['id'])
                except:
                    pass
            # 2) من السجل القديم (company_id مباشر) — للتوافق الخلفي
            if not methods:
                try:
                    with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if (row.get('company_id') == str(company_id) and
                                row.get('status') == 'active' and row['id'] not in seen_ids):
                                methods.append(row)
                                seen_ids.add(row['id'])
                except:
                    pass
            return methods

    def start_custom_flow(self, message, method_id, flow_type, company_id, company_name):
        """بدء تدفق مخصص لوسيلة دفع"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        steps = self.get_method_steps(method_id, flow_type)
        if not steps:
            return False

        user = self.find_user(user_id)
        lang = user.get('language', 'ar') if user else 'ar'

        self.user_states[user_id] = {
            'step': 'custom_flow',
            'method_id': method_id,
            'flow_type': flow_type,
            'company_id': company_id,
            'company_name': company_name,
            'current_step_idx': 0,
            'collected_data': [],
            'lang': lang
        }

        # تسجيل المعاملة في pending_transactions عند بدء الجلسة
        # (قبل أن يكتمل الإدخال — للاسترداد عند إعادة التشغيل)
        pending_tx_id = f"FLOW_{user_id}_{flow_type}"
        try:
            self._db.record_pending_transaction(
                tx_id=pending_tx_id,
                user_id=str(user_id),
                tx_type=flow_type,
                amount='',
                currency='',
                company=company_name,
            )
        except Exception as _e:
            logger.warning(f"start_custom_flow: فشل تسجيل pending_transaction: {_e}")

        # عرض الخطوة الأولى
        self._show_custom_step(chat_id, steps[0], 1, len(steps), lang)
        return True

    def _show_custom_step(self, chat_id, step, current, total, lang):
        """عرض خطوة من التدفق المخصص"""
        step_type = step.get('step_type', 'text')
        label = step.get('step_label', '')
        type_icons = {'text': '📝', 'amount': '💰', 'screenshot': '📸', 'info': 'ℹ️'}
        icon = type_icons.get(step_type, '📝')

        text = f"━━━━━━━━━━━━━━━━━━\n"
        text += self.tr('a0851_الخطوة_من', lang, current=current, total=total)
        text += f"━━━━━━━━━━━━━━━━━━\n\n"
        text += f"{icon} <b>{label}</b>\n"

        if step_type == 'screenshot':
            text += self.tr('a0852_أرسل_لقطة', lang)
        elif step_type == 'amount':
            text += self.tr('a0853_اكتب_المبلغ', lang)
        elif step_type == 'info':
            text += self.tr('a0854_اقرأ_المعلومات', lang)
        else:
            text += self.tr('a0855_اكتب_إجابتك', lang)

        if step_type == 'info':
            inline_btns = [[{'text': '✅ متابعة', 'callback_data': 'custom_flow_continue'}]]
            self.send_inline_message(chat_id, text, inline_btns)
        else:
            kb = {'keyboard': [[{'text': '❌ إلغاء'}]], 'resize_keyboard': True, 'one_time_keyboard': True}
            self.send_message(chat_id, text, kb)

    def handle_custom_flow_step(self, message, state):
        """معالجة خطوة من التدفق المخصص"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()

        if text in [self.tr('a0009_إلغاء', lang), self.tr('a0010_إلغاء', lang), self.tr('a0011_الغاء', lang), '🔙']:
            if user_id in self.user_states:
                del self.user_states[user_id]
            self.handle_start(message)
            return

        method_id = state.get('method_id', '')
        flow_type = state.get('flow_type', 'deposit')
        company_id = state.get('company_id', '')
        company_name = state.get('company_name', '')
        lang = state.get('lang', 'ar')
        current_idx = state.get('current_step_idx', 0)
        collected = state.get('collected_data', [])

        steps = self.get_method_steps(method_id, flow_type)
        if not steps or current_idx >= len(steps):
            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        current_step = steps[current_idx]
        step_type = current_step.get('step_type', 'text')

        # التحقق من الإدخال حسب نوع الخطوة
        if step_type == 'screenshot':
            if 'photo' not in message:
                self.send_message(chat_id, self.tr('a0856_أرسل_صورة', lang))
                return
            photo = message['photo'][-1]
            collected.append({'type': 'screenshot', 'value': photo['file_id'], 'label': current_step.get('step_label', '')})
        elif step_type == 'amount':
            try:
                amount = float(text)
                if amount <= 0:
                    self.send_message(chat_id, self.tr('a0845_المبلغ_يجب', lang))
                    return
                collected.append({'type': 'amount', 'value': text, 'label': current_step.get('step_label', '')})
            except ValueError:
                self.send_message(chat_id, self.tr('a0846_اكتب_مبلغاً', lang))
                return
        elif step_type == 'info':
            # info steps are handled by callback, not text
            return
        else:
            if len(text) < 2:
                self.send_message(chat_id, self.tr('a0857_الإجابة_قصيرة', lang))
                return
            collected.append({'type': 'text', 'value': text, 'label': current_step.get('step_label', '')})

        # الانتقال للخطوة التالية
        next_idx = current_idx + 1
        if next_idx < len(steps):
            state['current_step_idx'] = next_idx
            state['collected_data'] = collected
            self.user_states[user_id] = state
            self._show_custom_step(chat_id, steps[next_idx], next_idx + 1, len(steps), lang)
        else:
            # اكتمال كل الخطوات — تأكيد
            self._complete_custom_flow(message, state, collected, steps)

    def _complete_custom_flow(self, message, state, collected_data, steps):
        """إكمال التدفق المخصص — عرض ملخص + تأكيد"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        company_name = state.get('company_name', '')
        flow_type = state.get('flow_type', 'deposit')
        lang = state.get('lang', 'ar')

        summary = self.tr('a0858_مراجعة_البيانات', lang)
        summary += self.tr('a0859_الشركة', lang, company_name=company_name)
        summary += f"{'💰 إيداع' if flow_type == 'deposit' else '💸 سحب'}\n"
        summary += f"━━━━━━━━━━━━━━━━━━\n\n"

        for i, item in enumerate(collected_data, 1):
            label = item.get('label', self.tr('a0860_خطوة', lang, i=i))
            value = item.get('value', '')
            if item.get('type') == 'screenshot':
                summary += self.tr('a0861_تم_استلام', lang, label=label)
            elif item.get('type') == 'amount':
                summary += self.tr('a0862_اضغط_للنسخ', lang, label=label, value=value)
            else:
                summary += self.tr('a0863_اضغط_للنسخ', lang, label=label, value=value)

        summary += f"\n━━━━━━━━━━━━━━━━━━\n"
        summary += self.tr('a0521_هل_تريد', lang)

        # حفظ البيانات في الحالة للتأكيد
        state['collected_data'] = collected_data
        state['step'] = 'custom_flow_confirm'
        self.user_states[user_id] = state

        inline_btns = [
            [{'text': '✅ تأكيد', 'callback_data': 'custom_flow_confirm'},
             {'text': '❌ إلغاء', 'callback_data': 'custom_flow_cancel'}]
        ]
        self.send_inline_message(chat_id, summary, inline_btns)

    def _finalize_custom_flow(self, chat_id, user_id, state):
        """إنشاء المعاملة بعد التأكيد"""
        user = self.find_user(user_id)
        if not user:
            return

        company_name = state.get('company_name', '')
        flow_type = state.get('flow_type', 'deposit')
        method_id = state.get('method_id', '')
        collected_data = state.get('collected_data', [])
        user_currency = user.get('currency', 'SAR')

        # بناء حقل exchange_address من البيانات المجمعة
        data_parts = []
        amount = 0
        screenshot_file_id = ''
        for item in collected_data:
            if item.get('type') == 'amount':
                amount = float(item.get('value', 0))
            elif item.get('type') == 'screenshot':
                screenshot_file_id = item.get('value', '')
            data_parts.append(f"{item.get('label', '')}: {item.get('value', '')}")

        combined_data = ' | '.join(data_parts)
        trans_id = f"{'DEP' if flow_type == 'deposit' else 'WTH'}{datetime.now().strftime('%Y%m%d%H%M%S')}"

        with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                trans_id, user['customer_id'], user['telegram_id'], user['name'],
                flow_type, company_name,
                collected_data[0].get('value', '') if collected_data else '',  # wallet_number (first text input)
                amount,
                combined_data,  # exchange_address = كل البيانات
                'pending',
                datetime.now().strftime('%Y-%m-%d %H:%M'),
                screenshot_file_id,  # admin_note = screenshot file_id
                '', user_currency
            ])

        # رسالة تأكيد للعميل
        self.send_message(chat_id,
            f"✅ <b>تم تقديم طلبك!</b>\n\n"
            f"🆔 رقم العملية: <code>{trans_id}</code> 👈 اضغط للنسخ\n"
            f"🏢 الشركة: <b>{company_name}</b>\n"
            f"💰 المبلغ: <code>{amount}</code> {user_currency}\n\n"
            f"⏳ بانتظار مراجعة الإدارة",
            self.main_keyboard(user.get('language', 'ar'), user_id))

        # إشعار الأدمن
        for admin_id in self.admin_ids:
            try:
                admin_msg = (
                    f"🔔 <b>طلب جديد</b>\n\n"
                    f"🆔 رقم العملية: <code>{trans_id}</code> 👈 اضغط للنسخ\n"
                    f"👤 {user.get('name', '')} — <code>{user.get('customer_id', '')}</code>\n"
                    f"🏢 {company_name}\n"
                    f"{'💰 إيداع' if flow_type == 'deposit' else '💸 سحب'}\n"
                    f"💰 المبلغ: <code>{amount}</code> {user_currency}\n\n"
                )
                # إضافة تفاصيل كل خطوة
                for item in collected_data:
                    if item.get('type') != 'screenshot':
                        admin_msg += f"📝 {item.get('label', '')}: <code>{item.get('value', '')}</code>\n"

                inline_btns = [
                    [{'text': '✅ موافقة', 'callback_data': f'approve_{trans_id}'},
                     {'text': '❌ رفض', 'callback_data': f'reject_{trans_id}'}]
                ]
                self.send_inline_message(int(admin_id), admin_msg, inline_btns)

                # إرسال لقطة الشاشة إن وجدت
                if screenshot_file_id:
                    self.api_call('sendPhoto', {
                        'chat_id': int(admin_id),
                        'photo': screenshot_file_id,
                        'caption': f"📸 لقطة شاشة — {trans_id}"
                    })
            except:
                pass

        # حلّ سجل pending_transaction بمجرد تقديم الطلب بنجاح
        pending_tx_id = f"FLOW_{user_id}_{flow_type}"
        try:
            self._db.resolve_pending_transaction(pending_tx_id, status='submitted')
        except Exception as _e:
            logger.warning(f"_finalize_custom_flow: فشل تحديث pending_transaction: {_e}")

        if user_id in self.user_states:
            del self.user_states[user_id]

    def show_payment_method_selection(self, message, company_id, transaction_type):
            """عرض وسائل الدفع المتاحة — كأزرار inline"""
            user_id = message['from']['id']
            user = self.find_user(user_id)
            lang = user.get('language', 'ar') if user else 'ar'
            methods = self.get_payment_methods_by_company(company_id, transaction_type)
            
            if not methods:
                self.send_message(message['chat']['id'], 
                                self.tr('no_payment_methods', lang),
                                self.main_keyboard(lang, user_id))
                return

            if lang == 'ar':
                title = self.tr('a0864_اختر_وسيلة', lang)
            else:
                title = "💳 <b>Select Payment Method</b>\n\n"

            inline_btns = []
            for method in methods:
                method_icon = method.get('icon', '💳') or '💳'
                btn_text = f"{method_icon} {method['method_name']}"
                if method.get('method_type'):
                    btn_text += f" — {method['method_type']}"
                if method.get('additional_info'):
                    btn_text += f" ({method['additional_info'][:20]})"
                inline_btns.append([{'text': btn_text, 'callback_data': f'dep_method_{method["id"]}_{company_id}_{transaction_type}'}])

            inline_btns.append([{'text': self.tr('main_menu', lang), 'callback_data': 'dep_cancel'}])
            self.send_inline_message(message['chat']['id'], title, inline_btns)
        
    def add_payment_method(self, company_id, method_name, method_type, account_data, additional_info="", icon="", currency=""):
            """إضافة وسيلة دفع جديدة — بدون تكرار (نفس الاسم + نفس البيانات = نفس الوسيلة)"""
            try:
                # فحص التكرار: لو نفس الاسم + نفس account_data = return existing ID
                existing_methods = self.get_all_payment_methods()
                for m in existing_methods:
                    if (m.get('method_name', '').strip().lower() == method_name.strip().lower() and
                        m.get('account_data', '').strip() == account_data.strip()):
                        logger.info(f"Payment method '{method_name}' with same data already exists: {m['id']}")
                        return m['id']
                
                # إنشاء ID جديد  
                new_id = int(datetime.now().timestamp() * 1000) % 1000000
                # تطبيع الأيقونة
                method_icon = self.normalize_icon(icon or method_type, default='💳')
                # إضافة الوسيلة الجديدة (company_id فارغ = pool عام)
                with open('payment_methods.csv', 'a', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        new_id,
                        '',  # company_id فارغ — الربط يتم عبر company_payment_links.csv
                        method_name,
                        method_type,
                        account_data,
                        additional_info,
                        'active',
                        datetime.now().strftime('%Y-%m-%d'),
                        method_icon,
                        currency.upper() if currency else ''
                    ])
                logger.info(f"Payment method added: {new_id} ({method_name}) currency: {currency}")
                return new_id
            except Exception as e:
                logger.error(f"خطأ في إضافة وسيلة دفع: {e}")
                return False
        
    def edit_payment_method(self, method_id, new_data):
            """تعديل وسيلة دفع موجودة"""
            try:
                methods = []
                found = False
                
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == str(method_id):
                            # تحديث البيانات
                            for key, value in new_data.items():
                                if key in row:
                                    row[key] = value
                            found = True
                        methods.append(row)
                
                if found:
                    # كتابة البيانات المحدثة
                    with open('payment_methods.csv', 'w', encoding='utf-8-sig', newline='') as f:
                        if methods:
                            fieldnames = methods[0].keys()
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            writer.writeheader()
                            writer.writerows(methods)
                    return True
            except:
                pass
            return False
        
    def update_payment_method_status(self, method_id, new_status):
        """تحديث حالة وسيلة دفع"""
        try:
            rows = self.safe_csv_read('payment_methods.csv')
            for row in rows:
                if row.get('id') == str(method_id):
                    row['status'] = new_status
                    break
            fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
            self.safe_csv_write('payment_methods.csv', rows, fieldnames, mode='w')
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث حالة وسيلة الدفع: {e}")
            return False

    def update_payment_method_field(self, method_id, field, value):
        """تحديث حقل واحد في وسيلة دفع"""
        try:
            rows = self.safe_csv_read('payment_methods.csv')
            for row in rows:
                if row.get('id') == str(method_id):
                    row[field] = value
                    break
            fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
            self.safe_csv_write('payment_methods.csv', rows, fieldnames, mode='w')
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث وسيلة الدفع: {e}")
            return False

    def delete_payment_method(self, method_id):
            """حذف وسيلة دفع مع إرجاع البيانات المحذوفة"""
            try:
                methods = []
                deleted_method = None
                
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] != str(method_id):
                            methods.append(row)
                        else:
                            deleted_method = row.copy()
                
                if deleted_method:
                    # كتابة الملف حتى لو كان فارغ
                    with open('payment_methods.csv', 'w', encoding='utf-8-sig', newline='') as f:
                        fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        if methods:  # فقط اكتب الصفوف إذا كانت موجودة
                            writer.writerows(methods)
                    
                    logger.info(f"تم حذف وسيلة الدفع {method_id}: {deleted_method.get('method_name', 'غير محدد')}")
                    return True, deleted_method
                
                return False, None
            except Exception as e:
                logger.error(f"خطأ في حذف وسيلة الدفع {method_id}: {e}")
                return False, None
        
    def start_add_company_wizard(self, message):
            """بدء معالج إضافة شركة تفاعلي"""
            wizard_text = self.tr('a0865_معالج_إضافة', 'ar')
            
            self.send_message(message['chat']['id'], wizard_text)
            self.user_states[message['from']['id']] = 'adding_company_name'
        
    def handle_add_company_wizard(self, message, text):
            """معالجة معالج إضافة الشركة"""
            user_id = message['from']['id']
            state = self.user_states.get(user_id, '')
            
            if state == 'adding_company_name':
                company_name = text.strip()
                if len(company_name) < 2:
                    self.send_message(message['chat']['id'], self.tr('a0866_اسم_قصير', 'ar'))
                    return
                
                # عرض أنواع الخدمة
                service_keyboard = {
                    'keyboard': [
                        [{'text': '💰 إيداع فقط'}, {'text': '💸 سحب فقط'}],
                        [{'text': '🔄 إيداع وسحب معاً'}],
                        [{'text': '❌ إلغاء'}, {'text': '🔄 إعادة تعيين النظام'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': True
                }
                
                self.send_message(message['chat']['id'], self.tr('a0867_اسم_الشركة', 'ar', company_name=company_name), service_keyboard)
                self.user_states[user_id] = f'adding_company_type_{company_name}'
                
            elif state.startswith('adding_company_type_'):
                company_name = state.replace('adding_company_type_', '')
                
                if text == self.tr('a0009_إلغاء', 'ar'):
                    self.send_message(message['chat']['id'], self.tr('a0868_تم_إلغاء', 'ar'), self.admin_keyboard())
                    del self.user_states[user_id]
                    return
                
                # تحديد نوع الخدمة
                if text == self.tr('a0869_إيداع_فقط', 'ar'):
                    service_type = 'deposit'
                    service_ar = self.tr('a0751_إيداع_فقط', 'ar')
                elif text == self.tr('a0870_سحب_فقط', 'ar'):
                    service_type = 'withdraw'
                    service_ar = self.tr('a0753_سحب_فقط', 'ar')
                elif text == self.tr('a0754_إيداع_وسحب', 'ar'):
                    service_type = 'both'
                    service_ar = self.tr('a0755_إيداع_وسحب', 'ar')
                else:
                    self.send_message(message['chat']['id'], self.tr('a0871_اختر_من', 'ar'))
                    return
                
                self.send_message(message['chat']['id'], self.tr('a0872_تم_اختيار', 'ar', service_ar=service_ar))
                
                self.user_states[user_id] = f'adding_company_details_{company_name}_{service_type}'
                
            elif state.startswith('adding_company_details_'):
                parts = state.replace('adding_company_details_', '').rsplit('_', 1)
                company_name = parts[0]
                service_type = parts[1]
                details = text.strip()
                
                if len(details) < 3:
                    self.send_message(message['chat']['id'], self.tr('a0873_تفاصيل_قصيرة', 'ar'))
                    return
                
                # إنشاء الشركة
                company_id = str(int(datetime.now().timestamp()))
                
                try:
                    with open('companies.csv', 'a', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow([company_id, company_name, service_type, details, 'active', '🏢', ''])
                    
                    service_ar = self.tr('a0751_إيداع_فقط', 'ar') if service_type == 'deposit' else self.tr('a0753_سحب_فقط', 'ar') if service_type == 'withdraw' else self.tr('a0755_إيداع_وسحب', 'ar')
                    
                    success_msg = f"""✅ تم إضافة الشركة بنجاح!
    
    🆔 المعرف: {company_id}
    🏢 الاسم: {company_name}
    ⚡ النوع: {service_ar}
    📋 التفاصيل: {details}
    📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    
    الشركة أصبحت متاحة الآن للعملاء."""
                    
                    self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    del self.user_states[user_id]
                    
                except Exception as e:
                    self.send_message(message['chat']['id'], f"❌ فشل في إضافة الشركة: {str(e)}", self.admin_keyboard())
                    del self.user_states[user_id]
        
    def show_companies_management(self, message):
            """عرض إدارة الشركات"""
            companies_text = self.tr('a0874_إدارة_الشركات', 'ar')
            
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        status = "✅" if row.get('is_active') == 'active' else "❌"
                        companies_text += f"{status} {row['id']} - {row['name']}\n"
                        companies_text += f"   📋 {row['type']} - {row['details']}\n\n"
            except:
                pass
            
            companies_text += self.tr('a0875_الأوامر', 'ar')
            companies_text += self.tr('a0876_اضافة_شركة', 'ar')
            companies_text += self.tr('a0877_حذف_شركة', 'ar')
            
            self.send_message(message['chat']['id'], companies_text, self.admin_keyboard())
        
    def show_addresses_management(self, message):
            """عرض إدارة العناوين"""
            current_address = self.get_exchange_address()
            
            address_text = self.tr('a0878_إدارة_عناوين', 'ar', current_address=current_address)
            
            self.send_message(message['chat']['id'], address_text, self.admin_keyboard())
        
    def show_system_settings(self, message):
            """عرض إعدادات النظام بأزرار inline"""
            settings = {}
            try:
                with open('system_settings.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        settings[row['setting_key']] = row.get('setting_value', '')
            except:
                pass

            # تجميع الإعدادات في مجموعات
            text = self.tr('a0879_إعدادات_النظام', 'ar')
            text += "━━━━━━━━━━━━━━━━━━\n\n"

            # المجموعات
            groups = {
                self.tr('a0880_المعاملات', 'ar'): ['min_deposit', 'max_daily_withdrawal', 'default_currency'],
                self.tr('a0881_الأمان', 'ar'): ['rate_limit_per_minute', 'session_timeout'],
                self.tr('a0882_المظهر', 'ar'): ['active_theme'],
            }

            inline_btns = []
            for group_name, keys in groups.items():
                text += f"<b>{group_name}</b>\n"
                row = []
                for key in keys:
                    val = settings.get(key, self.tr('a0122_غير_محدد', 'ar'))
                    label = key.replace('_', ' ')
                    text += f"  • {label}: <code>{val}</code>\n"
                    row.append({'text': f'✏️ {label}', 'callback_data': f'setting_edit_{key}'})
                text += "\n"
                if row:
                    inline_btns.append(row)

            # إعدادات أخرى
            other_settings = {k: v for k, v in settings.items()
                             if k not in sum(groups.values(), [])}
            if other_settings:
                text += self.tr('a0883_أخرى', 'ar')
                row = []
                for key, val in list(other_settings.items())[:6]:
                    text += f"  • {key}: <code>{val}</code>\n"
                    row.append({'text': f'✏️ {key[:20]}', 'callback_data': f'setting_edit_{key}'})
                if row:
                    inline_btns.append(row)

            inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'settings_back'}])

            self.send_inline_message(message['chat']['id'], text, inline_btns)

    def show_multi_bot_panel(self, message):
        """لوحة إدارة البوتات المتعددة — عرض شامل بأزرار inline"""
        manager = MultiBotManager()
        stats = manager.get_stats()

        text = (
            f"🤖 <b>إدارة البوتات</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>إجمالي:</b> {stats['total_bots']} | "
            f"🟢 <b>تعمل:</b> {stats['running_bots']} | "
            f"🧊 <b>مجمدة:</b> {stats['frozen_bots']}\n"
            f"👥 <b>المستخدمين:</b> {stats['total_users']} | "
            f"📋 <b>المعاملات:</b> {stats['total_transactions']}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
        )

        inline_btns = []
        if stats['bots']:
            for b in stats['bots']:
                icon = manager.get_bot_status_icon(b)
                name = b.get('name', '')
                bid = b.get('id', '')
                admins = b.get('admin_ids', '')
                admin_count = len([a for a in admins.split(',') if a.strip()]) if admins else 0
                freeze = b.get('freeze_until', '')

                text += f"{icon} <b>{name}</b>\n"
                text += f"   🆔 <code>{bid}</code> | 👥 {b.get('total_users', '0')} | 📋 {b.get('total_transactions', '0')} | 🔑 {admin_count} أدمن\n"
                if freeze:
                    text += self.tr('a0884_تجميد_في', 'ar', freeze=freeze)
                text += "\n"

                # أزرار تحكم لكل بوت
                is_running = manager.is_running(bid)
                row_buttons = []
                if is_running:
                    row_buttons.append({'text': f'⏹️ إيقاف', 'callback_data': f'mbot_stop_{bid}'})
                elif b.get('status') == 'frozen':
                    row_buttons.append({'text': f'🔓 إلغاء التجميد', 'callback_data': f'mbot_unfreeze_{bid}'})
                else:
                    row_buttons.append({'text': f'▶️ تشغيل', 'callback_data': f'mbot_start_{bid}'})

                row_buttons.append({'text': f'🧊 تجميد', 'callback_data': f'mbot_freeze_{bid}'})
                row_buttons.append({'text': f'🔑 أدمن', 'callback_data': f'mbot_admins_{bid}'})
                row_buttons.append({'text': f'🗑️', 'callback_data': f'mbot_delete_{bid}'})
                inline_btns.append(row_buttons)

            text += "━━━━━━━━━━━━━━━━━━\n"

        inline_btns.append([{'text': '➕ إضافة بوت جديد', 'callback_data': 'mbot_add_wizard'}])
        inline_btns.append([{'text': '🔄 تحديث القائمة', 'callback_data': 'mbot_refresh'}])
        inline_btns.append([{'text': '🔙 العودة للوحة الأدمن', 'callback_data': 'mbot_back_admin'}])

        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def mbot_start_wizard(self, message):
        """معالج إضافة بوت جديد — خطوة بخطوة"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']

        if not hasattr(self, 'temp_mbot_data'):
            self.temp_mbot_data = {}
        self.temp_mbot_data[user_id] = {'step': 'mbot_name'}

        text = (
            "🤖 <b>إضافة بوت جديد</b>\n\n"
            "📝 <b>الخطوة 1 من 4</b>\n\n"
            "✍️ اكتب اسم البوت:\n\n"
            "مثال: بوت السعودية"
        )
        kb = {
            'keyboard': [[{'text': '❌ إلغاء'}], [{'text': '🔙 لوحة الأدمن'}]],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        self.send_message(chat_id, text, kb)
        self.user_states[user_id] = 'mbot_wizard_name'

    def mbot_handle_wizard(self, message):
        """معالجة خطوات معالج إضافة بوت"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()

        if text in [self.tr('a0009_إلغاء', 'ar'), self.tr('a0021_لوحة_الأدمن', 'ar'), self.tr('a0010_إلغاء', 'ar'), self.tr('a0011_الغاء', 'ar')]:
            if user_id in self.user_states:
                del self.user_states[user_id]
            if hasattr(self, 'temp_mbot_data') and user_id in self.temp_mbot_data:
                del self.temp_mbot_data[user_id]
            fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
            self.show_multi_bot_panel(fake_msg)
            return

        data = getattr(self, 'temp_mbot_data', {}).get(user_id, {})
        step = data.get('step', '')

        if step == 'mbot_name':
            if len(text) < 2:
                self.send_message(chat_id, self.tr('a0022_الاسم_قصير', 'ar'))
                return
            data['name'] = text
            data['step'] = 'mbot_token'
            self.temp_mbot_data[user_id] = data
            self.send_message(chat_id,
                "✅ تم حفظ الاسم!\n\n"
                "📝 <b>الخطوة 2 من 4</b>\n\n"
                "🔑 الصق توكن البوت من @BotFather:\n\n"
                "مثال: <code>123456789:AAHxxxxx...</code>")

        elif step == 'mbot_token':
            if len(text) < 20 or ':' not in text:
                self.send_message(chat_id, self.tr('a0885_توكن_غير', 'ar'))
                return
            data['token'] = text
            data['step'] = 'mbot_admins'
            self.temp_mbot_data[user_id] = data
            current_admin = str(message['from']['id'])
            self.send_message(chat_id,
                "✅ تم حفظ التوكن!\n\n"
                "📝 <b>الخطوة 3 من 4</b>\n\n"
                "🔑 اكتب معرفات الأدمن (مفصولة بفاصلة):\n\n"
                f"أو اكتب 'أنا' لتستخدم معرفك: <code>{current_admin}</code>\n\n"
                f"أو اكتب عدة معرفات: <code>{current_admin}, 123456789</code>")

        elif step == 'mbot_admins':
            if text.lower() in [self.tr('a0886_أنا', 'ar'), 'ana', 'me', self.tr('a0887_انا', 'ar')]:
                admin_ids = str(message['from']['id'])
            else:
                admin_ids = text.replace(' ', '')
            data['admin_ids'] = admin_ids
            data['step'] = 'mbot_freeze'
            self.temp_mbot_data[user_id] = data
            self.send_message(chat_id,
                "✅ تم حفظ الأدمن!\n\n"
                "📝 <b>الخطوة 4 من 4 (الأخيرة)</b>\n\n"
                "🧊 تاريخ تجميد البوت (اختياري):\n\n"
                "اكتب تاريخاً بصيغة: <code>YYYY-MM-DD</code>\n"
                "مثال: <code>2026-12-31</code>\n\n"
                "أو اكتب 'تخطي' لبدونه")

        elif step == 'mbot_freeze':
            if text.lower() in [self.tr('a0024_تخطي', 'ar'), 'skip', self.tr('a0025_بدون', 'ar')]:
                freeze_date = ''
            else:
                # التحقق من صحة التاريخ
                try:
                    from datetime import datetime as dt
                    dt.strptime(text, '%Y-%m-%d')
                    freeze_date = text
                except ValueError:
                    self.send_message(chat_id,
                        "❌ صيغة التاريخ غير صحيحة.\n"
                        "استخدم: <code>YYYY-MM-DD</code>\n"
                        "مثال: <code>2026-12-31</code>\n\n"
                        "أو اكتب 'تخطي'")
                    return

            data['freeze_date'] = freeze_date
            data['step'] = 'mbot_manage'
            self.temp_mbot_data[user_id] = data
            self.send_message(chat_id,
                "✅ تم حفظ تاريخ التجميد!\n\n"
                "📝 <b>الخطوة 5 من 5 (الأخيرة)</b>\n\n"
                "🤖 هل تريد أن يتمكن هذا البوت من إدارة البوتات الأخرى؟\n\n"
                "✅ اكتب <code>نعم</code> لمنح صلاحية إدارة البوتات\n"
                "❌ اكتب <code>لا</code> أو <code>تخطي</code> لبدون")

        elif step == 'mbot_manage':
            can_manage = 'yes' if text.lower() in [self.tr('a0198_نعم', 'ar'), 'yes', 'اى', 'اي'] else 'no'

            # حفظ البوت
            manager = MultiBotManager()
            bot_id = manager.add_bot(
                data['name'],
                data['token'],
                data['admin_ids'],
                description='',
                freeze_until=data.get('freeze_date', ''),
                can_manage_bots=can_manage
            )

            if bot_id:
                summary = (
                    "✅ <b>تم إضافة البوت بنجاح!</b>\n\n"
                    f"📱 الاسم: <b>{data['name']}</b>\n"
                    f"🆔 <code>{bot_id}</code>\n"
                    f"🔑 التوكن: <code>{data['token'][:20]}...</code>\n"
                    f"👥 الأدمن: <code>{data['admin_ids']}</code>\n"
                )
                if data.get('freeze_date'):
                    summary += self.tr('a0888_تجميد_في', 'ar', data_freeze_date=data['freeze_date'])
                summary += f"🤖 إدارة البوتات: <b>{'✅ مفعّل' if can_manage == 'yes' else '❌ غير مفعّل'}</b>\n"

                inline_btns = [
                    [{'text': f'▶️ تفعيل وتشغيل', 'callback_data': f'mbot_start_{bot_id}'}],
                    [{'text': '📋 عرض كل البوتات', 'callback_data': 'mbot_refresh'}],
                    [{'text': '➕ إضافة بوت آخر', 'callback_data': 'mbot_add_wizard'}],
                    [{'text': '🔙 لوحة الأدمن', 'callback_data': 'mbot_back_admin'}]
                ]
                self.send_inline_message(chat_id, summary, inline_btns)
            else:
                self.send_message(chat_id, self.tr('a0889_فشل_في', 'ar'), self.admin_keyboard())

            if user_id in self.user_states:
                del self.user_states[user_id]
            if hasattr(self, 'temp_mbot_data') and user_id in self.temp_mbot_data:
                del self.temp_mbot_data[user_id]

    def mbot_show_admins(self, chat_id, bot_id):
        """عرض أدمن البوت وإدارة الأدمن"""
        manager = MultiBotManager()
        bot = manager.get_bot_by_id(bot_id)
        if not bot:
            self.send_message(chat_id, self.tr('a0636_البوت_غير', 'ar'))
            return

        admins = bot.get('admin_ids', '')
        admin_list = [a.strip() for a in admins.split(',') if a.strip()]

        text = (
            f"🔑 <b>أدمن البوت: {bot['name']}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        for i, admin_id in enumerate(admin_list, 1):
            text += f"  {i}. <code>{admin_id}</code>\n"

        text += f"\n👥 العدد: <b>{len(admin_list)}</b>\n"
        text += "━━━━━━━━━━━━━━━━━━\n"
        text += self.tr('a0890_للإضافة_اضافة', 'ar')
        text += self.tr('a0891_للحذف_حذف', 'ar')

        inline_btns = [
            [{'text': '🔙 العودة', 'callback_data': 'mbot_refresh'}]
        ]
        self.send_inline_message(chat_id, text, inline_btns)

    def show_theme_panel(self, message):
        """عرض لوحة الثيمات للأدمن"""
        if not THEME_AVAILABLE:
            self.send_message(message['chat']['id'], self.tr('a0892_نظام_الثيمات', 'ar'), self.admin_keyboard())
            return

        current_theme = self.get_setting('active_theme') or 'gold'
        theme = get_theme(current_theme)

        text = (
            f"╔════════════════════╗\n"
            f"║  🎨 الثيمات  ║\n"
            f"╚════════════════════╝\n\n"
            f"الثيم الحالي: {theme.get('icon', '')} {theme.get('name_ar', current_theme)}\n\n"
            f"اختر ثيماً جديداً:\n"
        )

        themes = get_theme_list()
        keyboard = []
        for key, name_ar, icon in themes:
            marker = self.tr('a0893_نشط', 'ar') if key == current_theme else ''
            keyboard.append([{'text': f"{icon} ثيم_{key}{marker}"}])
        keyboard.append([{'text': '🔙 العودة'}])

        reply_kb = {'keyboard': keyboard, 'resize_keyboard': True, 'one_time_keyboard': True}
        self.send_message(message['chat']['id'], text, reply_kb)
    
    def show_complaints_admin(self, message):
            """عرض الشكاوى مع أزرار inline للرد السريع"""
            try:
                with open('complaints.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    pending_complaints = [row for row in reader if row['status'] == 'pending']
                
                if not pending_complaints:
                    self.send_message(message['chat']['id'], self.tr('a0894_لا_توجد', 'ar'), self.admin_keyboard())
                    return
                
                for complaint in pending_complaints:
                    complaint_text = (
                        f"📨 شكوى\n\n"
                        f"🆔 {complaint['id']}\n"
                        f"👤 {complaint['customer_id']}\n"
                        f"📝 {complaint['message']}\n"
                        f"📅 {complaint['date']}"
                    )
                    # أزرار inline للرد السريع
                    inline_btns = [
                        [{'text': '✅ تم الحل', 'callback_data': f"complaint_resolve_{complaint['id']}"},
                         {'text': '🔍 قيد المراجعة', 'callback_data': f"complaint_review_{complaint['id']}"}],
                        [{'text': '📞 سنتواصل', 'callback_data': f"complaint_contact_{complaint['id']}"},
                         {'text': '💡 رد مخصص', 'callback_data': f"complaint_custom_{complaint['id']}"}]
                    ]
                    self.send_inline_message(message['chat']['id'], complaint_text, inline_btns)
                
            except Exception as e:
                self.send_message(message['chat']['id'], self.tr('a0895_خطأ_في', 'ar', e=e), self.admin_keyboard())
        
    def start_complaint_reply_wizard(self, message, complaint_id):
            """بدء معالج الرد على الشكوى"""
            # البحث عن الشكوى
            complaint_found = False
            complaint_data = None
            
            try:
                with open('complaints.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == complaint_id:
                            complaint_found = True
                            complaint_data = row
                            break
            except:
                pass
            
            if not complaint_found:
                self.send_message(message['chat']['id'], self.tr('a0896_لم_يتم', 'ar', complaint_id=complaint_id), self.admin_keyboard())
                return
            
            # عرض تفاصيل الشكوى مع أزرار ردود سريعة
            # تم تحديث الرسالة لشرح استخدام الأزرار بدلاً من النسخ
            reply_text = (
                f"📞 الرد على الشكوى:\n\n"
                f"🆔 رقم الشكوى: {complaint_id}\n"
                f"👤 العميل: {complaint_data['customer_id']}\n"
                f"📝 الشكوى: {complaint_data['message']}\n"
                f"📅 التاريخ: {complaint_data['date']}\n\n"
                f"اختر رد سريع من الأزرار أدناه أو اكتب ردك المخصص:"
            )
            
            keyboard = [
                [{'text': f"✅ تم الحل - {complaint_id}"}],
                [{'text': f"🔍 قيد المراجعة - {complaint_id}"}],
                [{'text': f"📞 سنتواصل معك - {complaint_id}"}],
                [{'text': f"💡 رد مخصص - {complaint_id}"}],
                [{'text': '🔙 العودة للشكاوى'}]
            ]
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], reply_text, reply_keyboard)
            self.user_states[message['from']['id']] = f'replying_to_complaint_{complaint_id}'
        
    def show_payment_methods_admin(self, message):
            """عرض وسائل الدفع للأدمن"""
            payment_text = self.tr('a0897_وسائل_الدفع', 'ar')
            
            companies = self.get_companies()
            for company in companies:
                service_type = self.tr('a0755_إيداع_وسحب', 'ar') if company['type'] == 'both' else self.tr('a0390_إيداع', 'ar') if company['type'] == 'deposit' else self.tr('a0391_سحب', 'ar')
                payment_text += f"\n🏢 {company['name']}\n"
                payment_text += f"   📋 {service_type} - {company['details']}\n"
            
            self.send_message(message['chat']['id'], payment_text, self.admin_keyboard())
        
    def ban_user_admin(self, message, customer_id, reason):
            """حظر مستخدم من قبل الأدمن"""
            users = []
            success = False
            
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['customer_id'] == customer_id:
                            row['is_banned'] = 'yes'
                            row['ban_reason'] = reason
                            success = True
                        users.append(row)
                
                if success:
                    with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['telegram_id', 'name', 'phone', 'customer_id', 'language', 'date', 'is_banned', 'ban_reason', 'currency']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        for row in users:
                            if 'currency' not in row or not row['currency']:
                                row['currency'] = self.get_setting('default_currency') or 'SAR'
                            writer.writerow({k: row.get(k, '') for k in fieldnames})
                    
                    self.send_message(message['chat']['id'], self.tr('a0898_تم_حظر', 'ar', customer_id=customer_id, reason=reason), self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0899_لم_يتم', 'ar', customer_id=customer_id), self.admin_keyboard())
            except:
                self.send_message(message['chat']['id'], self.tr('a0900_فشل_في', 'ar'), self.admin_keyboard())
        
    def unban_user_admin(self, message, customer_id):
            """إلغاء حظر مستخدم من قبل الأدمن"""
            users = []
            success = False
            
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['customer_id'] == customer_id:
                            row['is_banned'] = 'no'
                            row['ban_reason'] = ''
                            success = True
                        users.append(row)
                
                if success:
                    with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['telegram_id', 'name', 'phone', 'customer_id', 'language', 'date', 'is_banned', 'ban_reason', 'currency']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        for row in users:
                            if 'currency' not in row or not row['currency']:
                                row['currency'] = self.get_setting('default_currency') or 'SAR'
                            writer.writerow({k: row.get(k, '') for k in fieldnames})
                    
                    self.send_message(message['chat']['id'], self.tr('a0901_تم_إلغاء', 'ar', customer_id=customer_id), self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0899_لم_يتم', 'ar', customer_id=customer_id), self.admin_keyboard())
            except:
                self.send_message(message['chat']['id'], self.tr('a0902_فشل_في', 'ar'), self.admin_keyboard())
        
    def delete_company_simple(self, message, company_id):
            """حذف شركة بسيط"""
            companies = []
            deleted = False
            
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] != company_id:
                            companies.append(row)
                        else:
                            deleted = True
                            deleted_name = row.get('name', 'Unknown')
                
                if deleted:
                    with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['id', 'name', 'type', 'details', 'is_active']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(companies)
                    
                    self.send_message(message['chat']['id'], self.tr('a0903_تم_حذف', 'ar', deleted_name=deleted_name, company_id=company_id), self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0804_لم_يتم', 'ar', company_id=company_id), self.admin_keyboard())
            except:
                self.send_message(message['chat']['id'], self.tr('a0904_فشل_في', 'ar'), self.admin_keyboard())
        
    def update_setting_simple(self, message, text):
            """تحديث إعداد النظام"""
            # تنسيق: تعديل_اعداد مفتاح_الإعداد القيمة_الجديدة
            parts = text.replace(self.tr('a0345_تعديل_اعداد', 'ar'), '').split(' ', 1)
            if len(parts) < 2:
                help_text = self.tr('a0905_تنسيق_خاطئ', 'ar')
                self.send_message(message['chat']['id'], help_text, self.admin_keyboard())
                return
            
            setting_key = parts[0]
            setting_value = parts[1]
            
            settings = []
            updated = False
            
            try:
                with open('system_settings.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['setting_key'] == setting_key:
                            row['setting_value'] = setting_value
                            updated = True
                        settings.append(row)
                
                if updated:
                    with open('system_settings.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['setting_key', 'setting_value', 'description']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(settings)
                    
                    self.send_message(message['chat']['id'], self.tr('a0906_تم_تحديث', 'ar', setting_key=setting_key, setting_value=setting_value), self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0907_لم_يتم', 'ar', setting_key=setting_key), self.admin_keyboard())
            except:
                self.send_message(message['chat']['id'], self.tr('a0908_فشل_في', 'ar'), self.admin_keyboard())
        
    def save_complaint(self, message, complaint_text):
            """حفظ شكوى المستخدم"""
            complaint_text = self.sanitize_input(complaint_text)
            user = self.find_user(message['from']['id'])
            if not user:
                return
            
            complaint_id = f"COMP{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            try:
                # إنشاء ملف الشكاوى مع الهيكل الصحيح إذا لم يكن موجوداً
                if not os.path.exists('complaints.csv'):
                    with open('complaints.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow(['id', 'customer_id', 'subject', 'message', 'status', 'date', 'admin_response'])
                
                # إضافة الشكوى الجديدة
                with open('complaints.csv', 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([complaint_id, user['customer_id'], 'شكوى جديدة', complaint_text, 'pending', 
                                   datetime.now().strftime('%Y-%m-%d %H:%M'), ''])
                
                confirmation = f"""✅ تم إرسال شكواك بنجاح
    
    🆔 رقم الشكوى: {complaint_id}
    📝 المحتوى: {complaint_text}
    📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    
    سيتم الرد عليك في أقرب وقت ممكن."""
                
                self.send_message(message['chat']['id'], confirmation, self.main_keyboard(user.get('language', 'ar')))
                if message['from']['id'] in self.user_states:
                    del self.user_states[message['from']['id']]
                
                # إشعار الأدمن بالشكوى الجديدة
                admin_msg = f"""📨 شكوى جديدة
    
    🆔 {complaint_id}
    👤 {user['name']} ({user['customer_id']})
    📝 الشكوى: {complaint_text}
    📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
                
                self.notify_admins(admin_msg, notification_type='new_user')
                
            except Exception as e:
                logger.error(f"خطأ في حفظ الشكوى: {e}")
                self.send_message(message['chat']['id'], self.tr('a0909_فشل_في', 'ar'), self.main_keyboard(user.get('language', 'ar')))
                if message['from']['id'] in self.user_states:
                    del self.user_states[message['from']['id']]
        
    def send_broadcast_message(self, message, broadcast_text=None):
            """إرسال رسالة جماعية — تدعم جميع أنواع الوسائط"""
            sent_count = 0
            failed_count = 0
            
            # تحديد نوع الرسالة
            media_type = None
            media_data = {}
            
            if 'photo' in message:
                media_type = 'photo'
                photo = message['photo'][-1]  # أكبر حجم
                media_data['photo'] = photo['file_id']
                media_data['caption'] = broadcast_text or message.get('caption', '')
            elif 'video' in message:
                media_type = 'video'
                media_data['video'] = message['video']['file_id']
                media_data['caption'] = broadcast_text or message.get('caption', '')
            elif 'sticker' in message:
                media_type = 'sticker'
                media_data['sticker'] = message['sticker']['file_id']
            elif 'document' in message:
                media_type = 'document'
                media_data['document'] = message['document']['file_id']
                media_data['caption'] = broadcast_text or message.get('caption', '')
            elif broadcast_text:
                media_type = 'text'
                media_data['text'] = broadcast_text
            else:
                self.send_message(message['chat']['id'], self.tr('a0910_لا_يوجد', 'ar'), self.admin_keyboard())
                if message['from']['id'] in self.user_states:
                    del self.user_states[message['from']['id']]
                return
            
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    users = list(reader)
                
                for user in users:
                    if user.get('is_banned') == 'yes':
                        continue
                    try:
                        tid = user['telegram_id']
                        
                        if media_type == 'photo':
                            result = self.api_call('sendPhoto', {
                                'chat_id': tid,
                                'photo': media_data['photo'],
                                'caption': f"📢 {media_data['caption']}" if media_data['caption'] else None,
                                'parse_mode': 'HTML'
                            })
                        elif media_type == 'video':
                            result = self.api_call('sendVideo', {
                                'chat_id': tid,
                                'video': media_data['video'],
                                'caption': f"📢 {media_data['caption']}" if media_data['caption'] else None,
                                'parse_mode': 'HTML'
                            })
                        elif media_type == 'sticker':
                            result = self.api_call('sendSticker', {
                                'chat_id': tid,
                                'sticker': media_data['sticker']
                            })
                        elif media_type == 'document':
                            result = self.api_call('sendDocument', {
                                'chat_id': tid,
                                'document': media_data['document'],
                                'caption': f"📢 {media_data['caption']}" if media_data['caption'] else None,
                                'parse_mode': 'HTML'
                            })
                        else:
                            msg = f"📢 رسالة من الإدارة\n\n{media_data['text']}\n\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                            result = self.send_message(tid, msg, None)
                        
                        if result and result.get('ok'):
                            sent_count += 1
                        else:
                            failed_count += 1
                    except:
                        failed_count += 1
                
                media_label = {'photo': '🖼️ صورة', 'video': '🎥 فيديو', 'sticker': '🃏 ملصق', 'document': '📄 ملف', 'text': '📝 نص'}.get(media_type, self.tr('a0911_محتوى', 'ar'))
                summary = f"""✅ تم الإرسال الجماعي

📊 الإحصائيات:
• النوع: {media_label}
• تم الإرسال: <code>{sent_count}</code>
• فشل: <code>{failed_count}</code>
• الإجمالي: <code>{sent_count + failed_count}</code>"""
                
                self.send_message(message['chat']['id'], summary, self.admin_keyboard())
                if message['from']['id'] in self.user_states:
                    del self.user_states[message['from']['id']]
            except:
                self.send_message(message['chat']['id'], self.tr('a0912_فشل_في', 'ar'), self.admin_keyboard())
                if message['from']['id'] in self.user_states:
                    del self.user_states[message['from']['id']]
    
    def show_approved_transactions(self, message):
            """عرض المعاملات المُوافق عليها"""
            approved_text = self.tr('a0913_المعاملات_المُوافق', 'ar')
            found_approved = False
            count = 0
            
            try:
                with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    transactions = list(reader)
                    
                    # عكس الترتيب للحصول على أحدث المعاملات
                    for row in reversed(transactions):
                        if row['status'] == 'approved' and count < 20:
                            found_approved = True
                            count += 1
                            type_emoji = "💰" if row['type'] == 'deposit' else "💸"
                            
                            approved_text += f"{type_emoji} {row['id']}\n"
                            approved_text += f"👤 {row['name']}\n"
                            approved_text += self.tr('a0914_ريال', 'ar', row_amount=row['amount'])
                            approved_text += f"📅 {row['date']}\n\n"
            except:
                pass
            
            if not found_approved:
                approved_text += self.tr('a0915_لا_توجد', 'ar')
            
            self.send_message(message['chat']['id'], approved_text, self.admin_keyboard())
        
    def show_users_management(self, message):
            """عرض إدارة المستخدمين"""
            users_text = self.tr('a0916_إدارة_المستخدمين', 'ar')
            active_count = 0
            banned_count = 0
            
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('is_banned') == 'yes':
                            banned_count += 1
                        else:
                            active_count += 1
            except:
                pass
            
            users_text += self.tr('a0917_مستخدمون_نشطون', 'ar', active_count=active_count)
            users_text += self.tr('a0918_مستخدمون_محظورون', 'ar', banned_count=banned_count)
            
            users_text += self.tr('a0919_الأوامر_المتاحة', 'ar')
            users_text += self.tr('a0920_بحث_اسم', 'ar')
            users_text += self.tr('a0921_حظر_رقم', 'ar')
            users_text += self.tr('a0922_الغاء_حظر', 'ar')
            
            users_text += self.tr('a0923_مثال_بحث', 'ar')
            
            self.send_message(message['chat']['id'], users_text, self.admin_keyboard())
        
    def search_users_admin(self, message, query):
            """البحث في المستخدمين للأدمن"""
            results = []
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if (query.lower() in row['name'].lower() or 
                            query in row['customer_id'] or 
                            query in row['phone']):
                            results.append(row)
            except:
                pass
            
            if not results:
                self.send_message(message['chat']['id'], self.tr('a0650_لم_يتم', 'ar', query=query), self.admin_keyboard())
                return
            
            search_text = self.tr('a0651_نتائج_البحث', 'ar', query=query)
            for user in results[:10]:  # أول 10 نتائج فقط
                status = self.tr('a0652_محظور', 'ar') if user.get('is_banned') == 'yes' else self.tr('a0653_نشط', 'ar')
                search_text += f"👤 {user['name']}\n"
                search_text += f"🆔 {user['customer_id']}\n"
                search_text += f"📱 {user['phone']}\n"
                search_text += f"🔸 {status}\n"
                if user.get('is_banned') == 'yes' and user.get('ban_reason'):
                    search_text += self.tr('a0924_سبب_الحظر', 'ar', user_ban_reason=user['ban_reason'])
                search_text += "\n"
            
            self.send_message(message['chat']['id'], search_text, self.admin_keyboard())
        
    def start_simple_payment_method_wizard(self, message):
            """معالج مبسط لإضافة وسيلة دفع"""
            user_id = message['from']['id']
            
            # عرض الشركات المتاحة
            companies = self.get_companies()
            if not companies:
                self.send_message(message['chat']['id'], 
                                self.tr('a0925_لا_توجد', 'ar'), 
                                self.admin_keyboard())
                return
            
            companies_text = self.tr('a0926_اختر_الشركة', 'ar')
            keyboard = []
            
            for company in companies:
                companies_text += f"🔹 {company['name']}\n"
                keyboard.append([{'text': f"🏢 {company['name']}"}])
            
            keyboard.append([{'text': '🔙 العودة'}])
            
            self.user_states[user_id] = 'adding_payment_simple'
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], companies_text, reply_keyboard)
        
    def start_edit_payment_method_wizard(self, message):
            """معالج مبسط لتعديل وسيلة دفع"""
            methods = self.get_all_payment_methods()
            if not methods:
                self.send_message(message['chat']['id'], self.tr('a0197_لا_توجد', 'ar'), self.admin_keyboard())
                return
            
            methods_text = self.tr('a0927_اختر_وسيلة', 'ar')
            keyboard = []
            
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                
                methods_text += f"🆔 {method['id']} - {method['method_name']}\n"
                methods_text += f"   🏢 {company_name}\n"
                methods_text += f"   💳 {method['method_type']}\n\n"
                
                keyboard.append([{'text': f"تعديل {method['id']}"}])
            
            keyboard.append([{'text': '🔙 العودة'}])
            
            self.user_states[message['from']['id']] = 'selecting_method_to_edit_simple'
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], methods_text, reply_keyboard)
        
    def start_delete_payment_method_wizard(self, message):
            """معالج مبسط لحذف وسيلة دفع"""
            methods = self.get_all_payment_methods()
            if not methods:
                self.send_message(message['chat']['id'], self.tr('a0197_لا_توجد', 'ar'), self.admin_keyboard())
                return
            
            methods_text = self.tr('a0928_اختر_وسيلة', 'ar')
            keyboard = []
            
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                
                methods_text += f"🆔 {method['id']} - {method['method_name']}\n"
                methods_text += f"   🏢 {company_name}\n\n"
                
                keyboard.append([{'text': f"حذف {method['id']}"}])
            
            keyboard.append([{'text': '🔙 العودة'}])
            
            self.user_states[message['from']['id']] = 'selecting_method_to_delete_simple'
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], methods_text, reply_keyboard)
        
    def show_all_payment_methods_simplified(self, message):
            """عرض مبسط لجميع وسائل الدفع"""
            methods = self.get_all_payment_methods()
            
            if not methods:
                self.send_message(message['chat']['id'], self.tr('a0929_لا_توجد', 'ar'), self.admin_keyboard())
                return
            
            methods_text = self.tr('a0930_وسائل_الدفع', 'ar')
            
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                status = self.tr('a0653_نشط', 'ar') if method['status'] == 'active' else self.tr('a0931_متوقف', 'ar')
                
                methods_text += f"🆔 {method['id']} - {method['method_name']}\n"
                methods_text += self.tr('a0932_الشركة', 'ar', company_name=company_name)
                methods_text += self.tr('a0933_النوع', 'ar', method_method_type=method['method_type'])
                methods_text += self.tr('a0934_البيانات', 'ar', method_account_data=method['account_data'])
                methods_text += self.tr('a0935_الحالة', 'ar', status=status)
                if method['additional_info']:
                    methods_text += self.tr('a0936_معلومات', 'ar', method_additional_info=method['additional_info'])
                methods_text += "─────────────\n\n"
            
            methods_text += f"📈 إجمالي وسائل الدفع: {len(methods)}"
            
            self.send_message(message['chat']['id'], methods_text, self.admin_keyboard())
        
    def handle_simple_payment_company_selection(self, message):
            """معالجة اختيار الشركة في المعالج المبسط"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in [self.tr('a0142_العودة', 'ar'), self.tr('a0254_العودة', 'ar')]:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            # البحث عن الشركة
            company_name = text.replace('🏢 ', '')
            companies = self.get_companies()
            selected_company = None
            
            for company in companies:
                if company['name'] == company_name:
                    selected_company = company
                    break
            
            if not selected_company:
                self.send_message(message['chat']['id'], self.tr('a0937_شركة_غير', 'ar'))
                return
            
            # طلب بيانات وسيلة الدفع
            input_text = self.tr('a0938_إضافة_وسيلة', 'ar', selected_company_name=selected_company['name'])
            
            self.send_message(message['chat']['id'], input_text)
            self.user_states[user_id] = f'adding_payment_method_{selected_company["id"]}'
        
    def handle_simple_payment_method_data(self, message):
            """معالجة بيانات وسيلة الدفع المبسطة"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            state = self.user_states.get(user_id, '')
            
            if text == '/cancel':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            # استخراج معرف الشركة
            company_id = state.replace('adding_payment_method_', '')
            
            # تحليل البيانات المدخلة
            if '|' in text:
                parts = [part.strip() for part in text.split('|')]
                if len(parts) >= 3:
                    method_name = parts[0]
                    method_type = parts[1]
                    account_data = parts[2]
                    additional_info = parts[3] if len(parts) > 3 else ""
                    
                    # إضافة وسيلة الدفع
                    success = self.add_payment_method(company_id, method_name, method_type, account_data, additional_info)
                    
                    if success:
                        company = self.get_company_by_id(company_id)
                        company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                        
                        success_msg = f"""✅ تم إضافة وسيلة الدفع بنجاح!
    
    🏢 الشركة: {company_name}
    📋 الاسم: {method_name}
    💳 النوع: {method_type}
    💰 البيانات: {account_data}
    💡 معلومات: {additional_info if additional_info else 'لا توجد'}"""
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], self.tr('a0939_فشل_في', 'ar'), self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0940_تنسيق_غير', 'ar'))
                    return
            else:
                self.send_message(message['chat']['id'], self.tr('a0941_تنسيق_غير', 'ar'))
                return
            
            # تنظيف الحالة
            if user_id in self.user_states:
                del self.user_states[user_id]
        
    def handle_simple_method_edit_selection(self, message):
            """معالجة اختيار وسيلة الدفع للتعديل المبسط"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in [self.tr('a0142_العودة', 'ar'), self.tr('a0254_العودة', 'ar')]:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            if text.startswith(self.tr('a0942_تعديل', 'ar')):
                method_id = text.replace(self.tr('a0942_تعديل', 'ar'), '').strip()
                method = self.get_payment_method_by_id(method_id)
                
                if not method:
                    self.send_message(message['chat']['id'], self.tr('a0943_وسيلة_دفع', 'ar'))
                    return
                
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                
                edit_text = self.tr('a0944_تعديل_وسيلة', 'ar', method_id=method['id'], company_name=company_name, method_method_name=method['method_name'], method_method_type=method['method_type'], method_account_data=method['account_data'], method_additional_info=method['additional_info'])
                
                self.send_message(message['chat']['id'], edit_text)
                self.user_states[user_id] = f'editing_method_simple_{method_id}'
        
    def handle_simple_method_delete_selection(self, message):
            """معالجة اختيار وسيلة الدفع للحذف المبسط"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in [self.tr('a0142_العودة', 'ar'), self.tr('a0254_العودة', 'ar')]:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            if text.startswith(self.tr('a0945_حذف', 'ar')):
                method_id = text.replace(self.tr('a0945_حذف', 'ar'), '').strip()
                
                # الحصول على بيانات الوسيلة قبل الحذف
                method_to_delete = self.get_payment_method_by_id(method_id)
                if not method_to_delete:
                    self.send_message(message['chat']['id'], self.tr('a0946_لم_يتم', 'ar', method_id=method_id), self.admin_keyboard())
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                    return
                
                # حذف وسيلة الدفع
                success, deleted_method = self.delete_payment_method(method_id)
                
                if success and deleted_method:
                    company = self.get_company_by_id(deleted_method['company_id'])
                    company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                    
                    success_msg = self.tr('a0947_تم_حذف', 'ar', deleted_method_id=deleted_method['id'], company_name=company_name, deleted_method_method_name=deleted_method['method_name'], deleted_method_method_type=deleted_method['method_type'])
                    
                    self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0948_فشل_في', 'ar', method_id=method_id), self.admin_keyboard())
                
                # تنظيف الحالة
                if user_id in self.user_states:
                    del self.user_states[user_id]
        
    def handle_simple_method_edit_data(self, message, method_id):
            """معالجة بيانات التعديل المبسط"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text == '/cancel':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            # تحليل البيانات الجديدة - تنسيق مبسط
            if '|' in text:
                parts = [part.strip() for part in text.split('|')]
                if len(parts) >= 3:
                    new_name = parts[0]
                    new_type = parts[1]
                    new_account = parts[2]
                    new_info = parts[3] if len(parts) > 3 else ""
                    
                    # التحقق من وجود الوسيلة قبل التحديث
                    existing_method = self.get_payment_method_by_id(method_id)
                    if not existing_method:
                        self.send_message(message['chat']['id'], self.tr('a0949_لم_يتم', 'ar', method_id=method_id), self.admin_keyboard())
                        if user_id in self.user_states:
                            del self.user_states[user_id]
                        return
                    
                    # تحديث وسيلة الدفع
                    logger.info(f"محاولة تحديث وسيلة الدفع - المعرف: {method_id}, الاسم: {new_name}, البيانات: {new_account}")
                    
                    # تسجيل البيانات للتشخيص
                    logger.info(f"البيانات المدخلة: الاسم={new_name}, النوع={new_type}, الحساب={new_account}, المعلومات={new_info}")
                    
                    success = self.update_payment_method_safe(method_id, new_name, new_type, new_account, new_info)
                    
                    if success:
                        # الحصول على بيانات الشركة
                        company = self.get_company_by_id(existing_method['company_id'])
                        company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                        
                        success_msg = f"""✅ تم تعديل وسيلة الدفع بنجاح!
    
    🆔 المعرف: {method_id}
    🏢 الشركة: {company_name}
    📋 الاسم: {new_name}
    💳 النوع: {new_type}
    💰 البيانات: {new_account}
    💡 معلومات إضافية: {new_info if new_info else 'لا توجد'}"""
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], self.tr('a0950_فشل_في', 'ar', method_id=method_id), self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0951_تنسيق_غير', 'ar'))
                    return
            else:
                self.send_message(message['chat']['id'], self.tr('a0952_يجب_استخدام', 'ar'))
                return
            
            # تنظيف الحالة
            if user_id in self.user_states:
                del self.user_states[user_id]
        
    def update_payment_method_safe(self, method_id, new_name, new_type, new_account, new_info=""):
            """تحديث آمن لوسيلة الدفع مع تحقق شامل"""
            try:
                methods = []
                updated = False
                original_method = None
                
                # قراءة الملف والبحث عن الوسيلة
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == str(method_id):
                            original_method = row.copy()
                            # تحديث البيانات
                            row['method_name'] = new_name
                            row['method_type'] = new_type
                            row['account_data'] = new_account
                            row['additional_info'] = new_info
                            updated = True
                            logger.info(f"تم العثور على وسيلة الدفع {method_id} وتحديثها")
                        methods.append(row)
                
                if not updated:
                    logger.error(f"لم يتم العثور على وسيلة الدفع {method_id}")
                    return False
                
                # كتابة الملف المحدث
                with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(methods)
                
                logger.info(f"✅ تم حفظ التحديث بنجاح - الوسيلة {method_id}: {new_name}")
                return True
                
            except Exception as e:
                logger.error(f"❌ خطأ في تحديث وسيلة الدفع {method_id}: {e}")
                return False
        
    def show_payment_methods_management(self, message):
            """عرض لوحة إدارة وسائل الدفع — أزرار inline"""
            methods = self.get_all_payment_methods()
            
            text = (
                "💳 <b>إدارة وسائل الدفع</b>\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"📊 إجمالي الوسائل: <b>{len(methods)}</b>\n"
                f"✅ نشطة: <b>{sum(1 for m in methods if m.get('status') == 'active')}</b>\n"
                f"⏸️ متوقفة: <b>{sum(1 for m in methods if m.get('status') != 'active')}</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
            )

            inline_btns = []

            # عرض الوسائل كأزرار
            if methods:
                text += self.tr('a0953_قائمة_الوسائل', 'ar')
                for m in methods[:15]:
                    company = self.get_company_by_id(m.get('company_id', ''))
                    company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                    icon = m.get('icon', '💳') or '💳'
                    status_icon = '✅' if m.get('status') == 'active' else '⏸️'
                    text += f"{status_icon} {icon} <b>{m['method_name']}</b>\n"
                    text += f"   🏢 {company_name} | 🆔 <code>{m['id']}</code>\n"
                    text += f"   🔢 <code>{m.get('account_data', '')}</code>\n\n"
                    inline_btns.append([{
                        'text': f"{status_icon} {icon} {m['method_name']} — {company_name}",
                        'callback_data': f'pm_edit_{m["id"]}'
                    }])
            
            # أزرار الإجراءات
            inline_btns.append([
                {'text': '➕ إضافة وسيلة دفع', 'callback_data': 'pm_add'},
                {'text': '📊 عرض الكل', 'callback_data': 'pm_list'}
            ])
            inline_btns.append([{'text': '🔙 العودة', 'callback_data': 'pm_back'}])

            self.send_inline_message(message['chat']['id'], text, inline_btns)
        
    def start_disable_payment_method_wizard(self, message):
            """معالج إيقاف وسيلة دفع"""
            methods = self.get_all_payment_methods()
            active_methods = [m for m in methods if m['status'] == 'active']
            
            if not active_methods:
                self.send_message(message['chat']['id'], self.tr('a0954_لا_توجد', 'ar'), self.admin_keyboard())
                return
            
            methods_text = self.tr('a0955_اختر_وسيلة', 'ar')
            keyboard = []
            
            for method in active_methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                
                methods_text += f"🆔 {method['id']} - {method['method_name']}\n"
                methods_text += f"   🏢 {company_name}\n"
                methods_text += f"   💳 {method['method_type']}\n\n"
                
                keyboard.append([{'text': f"إيقاف {method['id']}"}])
            
            keyboard.append([{'text': '🔙 العودة'}])
            
            self.user_states[message['from']['id']] = 'selecting_method_to_disable'
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], methods_text, reply_keyboard)
        
    def start_enable_payment_method_wizard(self, message):
            """معالج تشغيل وسيلة دفع"""
            methods = self.get_all_payment_methods()
            inactive_methods = [m for m in methods if m['status'] != 'active']
            
            if not inactive_methods:
                self.send_message(message['chat']['id'], self.tr('a0956_جميع_وسائل', 'ar'), self.admin_keyboard())
                return
            
            methods_text = self.tr('a0957_اختر_وسيلة', 'ar')
            keyboard = []
            
            for method in inactive_methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                
                methods_text += f"🆔 {method['id']} - {method['method_name']}\n"
                methods_text += f"   🏢 {company_name}\n"
                methods_text += f"   💳 {method['method_type']}\n\n"
                
                keyboard.append([{'text': f"تشغيل {method['id']}"}])
            
            keyboard.append([{'text': '🔙 العودة'}])
            
            self.user_states[message['from']['id']] = 'selecting_method_to_enable'
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], methods_text, reply_keyboard)
        
    def handle_method_disable_selection(self, message):
            """معالجة اختيار وسيلة الدفع للإيقاف"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in [self.tr('a0142_العودة', 'ar'), self.tr('a0254_العودة', 'ar')]:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            if text.startswith(self.tr('a0958_إيقاف', 'ar')):
                method_id = text.replace(self.tr('a0958_إيقاف', 'ar'), '').strip()
                success = self.toggle_payment_method_status(method_id, 'inactive')
                
                if success:
                    method = self.get_payment_method_by_id(method_id)
                    if method:
                        company = self.get_company_by_id(method['company_id'])
                        company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                        
                        success_msg = self.tr('a0959_تم_إيقاف', 'ar', method_id=method_id, company_name=company_name, method_method_name=method['method_name'], method_method_type=method['method_type'])
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], self.tr('a0946_لم_يتم', 'ar', method_id=method_id), self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0960_فشل_في', 'ar', method_id=method_id), self.admin_keyboard())
                
                if user_id in self.user_states:
                    del self.user_states[user_id]
        
    def handle_method_enable_selection(self, message):
            """معالجة اختيار وسيلة الدفع للتشغيل"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in [self.tr('a0142_العودة', 'ar'), self.tr('a0254_العودة', 'ar')]:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            if text.startswith(self.tr('a0961_تشغيل', 'ar')):
                method_id = text.replace(self.tr('a0961_تشغيل', 'ar'), '').strip()
                success = self.toggle_payment_method_status(method_id, 'active')
                
                if success:
                    method = self.get_payment_method_by_id(method_id)
                    if method:
                        company = self.get_company_by_id(method['company_id'])
                        company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                        
                        success_msg = self.tr('a0962_تم_تشغيل', 'ar', method_id=method_id, company_name=company_name, method_method_name=method['method_name'], method_method_type=method['method_type'])
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], self.tr('a0946_لم_يتم', 'ar', method_id=method_id), self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0963_فشل_في', 'ar', method_id=method_id), self.admin_keyboard())
                
                if user_id in self.user_states:
                    del self.user_states[user_id]
        
    def toggle_payment_method_status(self, method_id, new_status):
            """تغيير حالة وسيلة الدفع (تشغيل/إيقاف)"""
            try:
                methods = []
                updated = False
                
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == str(method_id):
                            row['status'] = new_status
                            updated = True
                            logger.info(f"تم تغيير حالة وسيلة الدفع {method_id} إلى {new_status}")
                        methods.append(row)
                
                if updated:
                    with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(methods)
                    
                    return True
                
                return False
            except Exception as e:
                logger.error(f"خطأ في تغيير حالة وسيلة الدفع {method_id}: {e}")
                return False
        
    def get_all_payment_methods(self):
            """الحصول على جميع وسائل الدفع"""
            methods = []
            try:
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        methods.append(row)
            except:
                pass
            return methods

    def get_payment_methods_by_currency(self, currency):
            """الحصول على وسائل الدفع لعملة محددة — بدون تكرار"""
            methods = []
            seen_names = set()
            try:
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('status') != 'active':
                            continue
                        # فلترة بالعملة: لو الوسيلة لها عملة محددة، طابقها. لو فارغة = تعمل بكل العملات
                        method_currency = row.get('currency', '').strip().upper()
                        if method_currency and method_currency != currency.strip().upper():
                            continue
                        # إزالة التكرار
                        name = row.get('method_name', '').strip().lower()
                        if name not in seen_names:
                            seen_names.add(name)
                            methods.append(row)
            except:
                pass
            return methods
        
    def get_payment_method_by_id(self, method_id):
            """الحصول على وسيلة دفع بالمعرف"""
            try:
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == str(method_id):
                            return row
            except Exception as e:
                logger.error(f"خطأ في البحث عن وسيلة الدفع {method_id}: {e}")
            return None
        
    def show_all_payment_methods(self, message):
            """عرض جميع وسائل الدفع المتاحة"""
            methods_text = self.tr('a0964_جميع_وسائل', 'ar')
            
            try:
                companies = self.get_companies()
                company_names = {c['id']: c['name'] for c in companies}
                
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    methods_by_company = {}
                    
                    for row in reader:
                        company_id = row['company_id']
                        if company_id not in methods_by_company:
                            methods_by_company[company_id] = []
                        methods_by_company[company_id].append(row)
                    
                    for company_id, methods in methods_by_company.items():
                        company_name = company_names.get(company_id, self.tr('a0965_شركة', 'ar', company_id=company_id))
                        methods_text += f"🏢 **{company_name}**:\n"
                        
                        for method in methods:
                            status_emoji = "✅" if method['status'] == 'active' else "⏹️"
                            status_text = self.tr('a0966_نشطة', 'ar') if method['status'] == 'active' else self.tr('a0967_متوقفة', 'ar')
                            methods_text += f"  {status_emoji} {method['method_name']} (#{method['id']}) - {status_text}\n"
                            methods_text += self.tr('a0968_النوع', 'ar', method_method_type=method['method_type'])
                            methods_text += self.tr('a0969_البيانات', 'ar', method_account_data=method['account_data'])
                            if method['additional_info']:
                                methods_text += self.tr('a0970_ملاحظات', 'ar', method_additional_info=method['additional_info'])
                            methods_text += "\n"
                        methods_text += "▫️▫️▫️▫️▫️▫️▫️▫️\n\n"
            except:
                methods_text += self.tr('a0971_خطأ_في', 'ar')
            
            # إضافة أوامر النسخ السريع
            methods_text += self.tr('a0972_أوامر_إدارة', 'ar')
            methods_text += self.tr('a0973_اضافة_وسيلة', 'ar')
            methods_text += self.tr('a0974_تعديل_وسيلة', 'ar')
            methods_text += self.tr('a0975_حذف_وسيلة', 'ar')
            
            methods_text += self.tr('a0976_مثال', 'ar')
            methods_text += self.tr('a0977_اضافة_وسيلة', 'ar')
            
            keyboard = [
                [{'text': '➕ إضافة وسيلة دفع'}, {'text': '✏️ تعديل وسيلة دفع'}],
                [{'text': '🔄 تحديث القائمة'}, {'text': '↩️ العودة'}]
            ]
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': False
            }
            
            self.send_message(message['chat']['id'], methods_text, reply_keyboard)
        
    def start_add_payment_method(self, message):
            """بدء إضافة وسيلة دفع جديدة"""
            user_id = message['from']['id']
            
            # عرض الشركات المتاحة
            companies = self.get_companies()
            if not companies:
                self.send_message(message['chat']['id'], 
                                self.tr('a0925_لا_توجد', 'ar'), 
                                self.admin_keyboard())
                return
            
            companies_text = self.tr('a0978_اختر_الشركة', 'ar')
            keyboard = []
            
            for company in companies:
                companies_text += f"🔹 {company['name']} (#{company['id']})\n"
                keyboard.append([{'text': f"{company['name']} (#{company['id']})"}])
            
            keyboard.append([{'text': '🔙 العودة'}])
            
            self.user_states[user_id] = {
                'step': 'adding_payment_method_select_company',
                'companies': companies
            }
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], companies_text, reply_keyboard)
        
    def handle_payment_method_selection(self, message, text):
            """معالجة اختيار وسيلة الدفع"""
            user_id = message['from']['id']
            state = self.user_states.get(user_id, {})
            
            back_texts = {self.tr('main_menu', l) for l in self.get_supported_languages()}
            if text in back_texts or text in [self.tr('a0142_العودة', 'ar'), self.tr('a0254_العودة', 'ar'), self.tr('a0979_العودة_لاختيار', 'ar')]:
                # العودة لاختيار الشركة
                transaction_type = state.get('transaction_type')
                if transaction_type == 'deposit':
                    self.create_deposit_request(message)
                else:
                    self.create_withdrawal_request(message)
                return
            
            # البحث عن وسيلة الدفع المختارة (إزالة الأيقونة من النص)
            clean_text = text
            for emoji in ['💳', '🏦', '📱', '👛', '💵', '📡', '🏷️']:
                if clean_text.startswith(emoji):
                    clean_text = clean_text[len(emoji):].strip()
                    break
            selected_method = None
            methods = state.get('methods', [])
            for method in methods:
                if method['method_name'] == clean_text or method['method_name'] == text:
                    selected_method = method
                    break
            
            if not selected_method:
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                self.send_message(message['chat']['id'], self.tr('no_payment_methods', lang))
                return
            
            # حفظ الوسيلة المختارة والانتقال للمرحلة التالية
            transaction_type = state['transaction_type']
            company_id = state['company_id']
            company = self.get_company_by_id(company_id)
            
            # عرض تفاصيل الوسيلة وطلب رقم المحفظة — رقم الحساب في code block للنسخ السهل
            user = self.find_user(user_id)
            lang = user.get('language', 'ar') if user else 'ar'
            method_icon = selected_method.get('icon', '💳') or '💳'
            company_name = company['name'] if company else 'N/A'
            account_data = selected_method.get('account_data', '')
            additional_info = selected_method.get('additional_info', '')
            user_currency = user.get('currency', 'SAR') if user else 'SAR'
            
            wallet_text = (
                f"✅ {method_icon} {selected_method['method_name']}\n\n"
                f"📋 {selected_method['method_type']}\n"
                f"🏢 {company_name}\n"
            )
            if additional_info:
                wallet_text += f"💡 {additional_info}\n"
            # طلب رقم محفظة العميل بوضوح
            wallet_text += f"\n📝 {self.tr('enter_wallet', lang, min_amount='0', currency='')}"
            
            cancel_kb = {
                'keyboard': [[{'text': '❌ إلغاء'}, {'text': '🏠 القائمة الرئيسية'}]],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            self.send_message(message['chat']['id'], wallet_text, cancel_kb)
            
            # تحديث الحالة — استبدال _ في اسم الشركة بمسافة لمنع تلف الحالة
            safe_company_name = (company["name"] if company else "unknown").replace('_', ' ')
            if transaction_type == 'deposit':
                self.user_states[user_id] = f'deposit_wallet_{company_id}_{safe_company_name}_{selected_method["id"]}'
            else:
                self.user_states[user_id] = f'withdraw_wallet_{company_id}_{safe_company_name}_{selected_method["id"]}'
        
    def get_company_by_id(self, company_id):
            """الحصول على شركة بواسطة ID"""
            companies = self.get_companies()
            for company in companies:
                if company['id'] == str(company_id):
                    return company
            return None
        
    def start_send_user_message(self, message):
            """بدء إرسال رسالة لعميل محدد"""
            user_id = message['from']['id']
            
            instruction_text = self.tr('a0980_إرسال_رسالة', lang)
            
            self.send_message(message['chat']['id'], instruction_text)
            self.user_states[user_id] = 'sending_user_message_id'
        
    def handle_user_message_id(self, message):
            """معالجة رقم العميل لإرسال الرسالة"""
            user_id = message['from']['id']
            customer_id = message.get('text', '').strip()
            
            if customer_id == '/cancel' or customer_id.lower() == 'cancel':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(message['chat']['id'], self.tr('a0981_تم_إلغاء', lang), self.admin_keyboard())
                return
            
            # البحث عن العميل
            user_found = None
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['customer_id'] == customer_id:
                            user_found = row
                            break
            except:
                pass
            
            if not user_found:
                self.send_message(message['chat']['id'], 
                                self.tr('a0982_لم_يتم', 'ar', customer_id=customer_id))
                return
            
            # عرض معلومات العميل وطلب الرسالة
            customer_info = f"""✅ تم العثور على العميل:
    
    👤 الاسم: {user_found['name']}
    📱 الهاتف: {user_found['phone']}
    🆔 رقم العميل: {user_found['customer_id']}
    📅 تاريخ التسجيل: {user_found.get('registration_date', 'غير محدد')}
    🚫 الحالة: {'محظور' if user_found.get('is_banned') == 'yes' else 'نشط'}
    
    📝 أرسل المحتوى الآن:
    • نص / صورة / فيديو / ملصق / ملف
    
    ⬅️ /cancel للإلغاء"""
            
            self.send_message(message['chat']['id'], customer_info)
            self.user_states[user_id] = f'sending_user_message_{customer_id}'
        
    def handle_user_message_content(self, message, customer_id):
            """معالجة محتوى الرسالة وإرسالها — يدعم جميع أنواع الوسائط"""
            user_id = message['from']['id']
            message_content = message.get('text', '').strip()
            
            if message_content == '/cancel' or message_content.lower() == 'cancel':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(message['chat']['id'], self.tr('a0983_تم_الإلغاء', 'ar'), self.admin_keyboard())
                return
            
            # البحث عن معرف التليجرام للعميل
            target_telegram_id = None
            customer_name = ""
            
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['customer_id'] == customer_id:
                            target_telegram_id = row['telegram_id']
                            customer_name = row['name']
                            break
            except:
                pass
            
            if not target_telegram_id:
                self.send_message(message['chat']['id'], 
                    self.tr('a0984_لم_يتم', 'ar', customer_id=customer_id), 
                    self.admin_keyboard())
                if user_id in self.user_states:
                    del self.user_states[user_id]
                return
            
            admin_info = self.find_user(user_id)
            admin_name = admin_info.get('name', self.tr('a0985_الإدارة', 'ar')) if admin_info else self.tr('a0985_الإدارة', 'ar')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            header = self.tr('a0986_رسالة_من', 'ar', admin_name=admin_name, timestamp=timestamp)
            
            sent = False
            
            try:
                if 'photo' in message:
                    photo = message['photo'][-1]
                    caption = message.get('caption', '')
                    result = self.api_call('sendPhoto', {
                        'chat_id': int(target_telegram_id),
                        'photo': photo['file_id'],
                        'caption': header + caption if caption else header.rstrip(),
                        'parse_mode': 'HTML'
                    })
                    sent = result and result.get('ok')
                elif 'video' in message:
                    caption = message.get('caption', '')
                    result = self.api_call('sendVideo', {
                        'chat_id': int(target_telegram_id),
                        'video': message['video']['file_id'],
                        'caption': header + caption if caption else header.rstrip(),
                        'parse_mode': 'HTML'
                    })
                    sent = result and result.get('ok')
                elif 'sticker' in message:
                    result = self.api_call('sendSticker', {
                        'chat_id': int(target_telegram_id),
                        'sticker': message['sticker']['file_id']
                    })
                    sent = result and result.get('ok')
                    if sent:
                        self.send_message(int(target_telegram_id), header.rstrip(), None)
                elif 'document' in message:
                    caption = message.get('caption', '')
                    result = self.api_call('sendDocument', {
                        'chat_id': int(target_telegram_id),
                        'document': message['document']['file_id'],
                        'caption': header + caption if caption else header.rstrip(),
                        'parse_mode': 'HTML'
                    })
                    sent = result and result.get('ok')
                elif message_content:
                    msg = header + message_content + self.tr('a0987_للرد_استخدم', 'ar')
                    result = self.send_message(int(target_telegram_id), msg, None)
                    sent = result and result.get('ok')
                else:
                    self.send_message(message['chat']['id'], self.tr('a0988_لا_يوجد', 'ar'))
                    return
            except Exception as e:
                logger.error(f"خطأ في إرسال رسالة لعميل: {e}")
                sent = False
            
            if sent:
                self.send_message(message['chat']['id'],
                    self.tr('a0989_تم_الإرسال', 'ar', customer_name=customer_name, customer_id=customer_id, timestamp=timestamp),
                    self.admin_keyboard())
            else:
                self.send_message(message['chat']['id'], self.tr('a0990_فشل_في', 'ar'), self.admin_keyboard())
            
            if user_id in self.user_states:
                del self.user_states[user_id]
        
    def start_edit_payment_method(self, message):
            """بدء تعديل وسيلة دفع"""
            user_id = message['from']['id']
            
            # عرض جميع وسائل الدفع للاختيار
            methods = self.get_all_payment_methods()
            
            if not methods:
                self.send_message(message['chat']['id'], 
                                self.tr('a0991_لا_توجد', 'ar'), 
                                self.admin_keyboard())
                return
            
            methods_text = self.tr('a0927_اختر_وسيلة', 'ar')
            
            keyboard_buttons = []
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                
                method_info = f"🆔 {method['id']} | {method['method_name']} | {company_name}"
                methods_text += f"{method_info}\n"
                keyboard_buttons.append([{'text': f"تعديل {method['id']}"}])
            
            keyboard_buttons.append([{'text': '🔙 العودة'}])
            
            keyboard = {
                'keyboard': keyboard_buttons,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], methods_text, keyboard)
            self.user_states[user_id] = 'selecting_method_to_edit'
        
    def start_delete_payment_method(self, message):
            """بدء حذف وسيلة دفع"""
            user_id = message['from']['id']
            
            # عرض جميع وسائل الدفع للاختيار
            methods = self.get_all_payment_methods()
            
            if not methods:
                self.send_message(message['chat']['id'], 
                                self.tr('a0991_لا_توجد', 'ar'), 
                                self.admin_keyboard())
                return
            
            methods_text = self.tr('a0928_اختر_وسيلة', 'ar')
            
            keyboard_buttons = []
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                
                method_info = f"🆔 {method['id']} | {method['method_name']} | {company_name}"
                methods_text += f"{method_info}\n"
                keyboard_buttons.append([{'text': f"حذف {method['id']}"}])
            
            keyboard_buttons.append([{'text': '🔙 العودة'}])
            
            keyboard = {
                'keyboard': keyboard_buttons,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.send_message(message['chat']['id'], methods_text, keyboard)
            self.user_states[user_id] = 'selecting_method_to_delete'
        
    def get_active_payment_methods(self):
            """الحصول على وسائل الدفع النشطة فقط"""
            methods = []
            try:
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('status') == 'active':
                            methods.append(row)
            except:
                pass
            return methods
        
    def update_payment_method_status(self, method_id, new_status):
        """تحديث حالة وسيلة دفع"""
        try:
            rows = self.safe_csv_read('payment_methods.csv')
            for row in rows:
                if row.get('id') == str(method_id):
                    row['status'] = new_status
                    break
            fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
            self.safe_csv_write('payment_methods.csv', rows, fieldnames, mode='w')
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث حالة وسيلة الدفع: {e}")
            return False

    def update_payment_method_field(self, method_id, field, value):
        """تحديث حقل واحد في وسيلة دفع"""
        try:
            rows = self.safe_csv_read('payment_methods.csv')
            for row in rows:
                if row.get('id') == str(method_id):
                    row[field] = value
                    break
            fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
            self.safe_csv_write('payment_methods.csv', rows, fieldnames, mode='w')
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث وسيلة الدفع: {e}")
            return False

    def delete_payment_method(self, method_id):
            """حذف وسيلة دفع"""
            try:
                methods = []
                deleted = False
                deleted_method = None
                
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] != str(method_id):
                            methods.append(row)
                        else:
                            deleted = True
                            deleted_method = row
                
                if deleted:
                    # إعادة كتابة الملف بدون الوسيلة المحذوفة
                    with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(methods)
                    
                    return True, deleted_method
                else:
                    return False, None
            except Exception as e:
                return False, None
        
    def handle_method_edit_selection(self, message):
            """معالجة اختيار وسيلة الدفع للتعديل"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in [self.tr('a0142_العودة', 'ar'), self.tr('a0254_العودة', 'ar'), self.tr('a0287_العودة', 'ar')]:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(message['chat']['id'], self.tr('a0992_تم_الإلغاء', 'ar'), self.admin_keyboard())
                return
            
            if text.startswith(self.tr('a0942_تعديل', 'ar')):
                method_id = text.replace(self.tr('a0942_تعديل', 'ar'), '').strip()
                
                # البحث عن وسيلة الدفع
                method = self.get_payment_method_by_id(method_id)
                if not method:
                    self.send_message(message['chat']['id'], self.tr('a0946_لم_يتم', 'ar', method_id=method_id))
                    return
                
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                
                # عرض تفاصيل الوسيلة وطلب البيانات الجديدة
                edit_text = self.tr('a0993_تعديل_وسيلة', 'ar', method_id=method['id'], company_name=company_name, method_method_name=method['method_name'], method_method_type=method['method_type'], method_account_data=method['account_data'], method_additional_info=method['additional_info'])
                
                self.send_message(message['chat']['id'], edit_text)
                self.user_states[user_id] = f'editing_method_{method_id}'
        
    def handle_method_delete_selection(self, message):
            """معالجة اختيار وسيلة الدفع للحذف"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in [self.tr('a0142_العودة', 'ar'), self.tr('a0254_العودة', 'ar'), self.tr('a0287_العودة', 'ar')]:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(message['chat']['id'], self.tr('a0992_تم_الإلغاء', 'ar'), self.admin_keyboard())
                return
            
            if text.startswith(self.tr('a0945_حذف', 'ar')):
                method_id = text.replace(self.tr('a0945_حذف', 'ar'), '').strip()
                
                # حذف وسيلة الدفع
                success, deleted_method = self.delete_payment_method(method_id)
                
                if success:
                    company = self.get_company_by_id(deleted_method['company_id'])
                    company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                    
                    success_msg = self.tr('a0994_تم_حذف', 'ar', deleted_method_id=deleted_method['id'], company_name=company_name, deleted_method_method_name=deleted_method['method_name'], deleted_method_method_type=deleted_method['method_type'])
                    
                    self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], self.tr('a0948_فشل_في', 'ar', method_id=method_id), self.admin_keyboard())
                
                del self.user_states[user_id]
        
    def handle_method_edit_data(self, message, method_id):
            """معالجة تعديل بيانات وسيلة الدفع"""
            user_id = message['from']['id']
            new_data = message.get('text', '').strip()
            
            if new_data == '/cancel':
                del self.user_states[user_id]
                self.send_message(message['chat']['id'], self.tr('a0995_تم_إلغاء', 'ar'), self.admin_keyboard())
                return
            
            if not new_data:
                self.send_message(message['chat']['id'], self.tr('a0996_البيانات_فارغة', 'ar'))
                return
            
            # تحديث وسيلة الدفع
            success = self.update_payment_method(method_id, new_data)
            
            if success:
                method = self.get_payment_method_by_id(method_id)
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else self.tr('a0122_غير_محدد', 'ar')
                
                success_msg = self.tr('a0997_تم_تحديث', 'ar', method_id=method['id'], company_name=company_name, method_method_name=method['method_name'], method_method_type=method['method_type'], new_data=new_data)
                
                self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
            else:
                self.send_message(message['chat']['id'], self.tr('a0998_فشل_في', 'ar'), self.admin_keyboard())
            
            del self.user_states[user_id]
        
    def get_payment_method_by_id(self, method_id):
            """الحصول على وسيلة دفع بواسطة المعرف"""
            try:
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == str(method_id):
                            return row
            except:
                pass
            return None
        
    def update_payment_method(self, method_id, new_account_data):
            """تحديث بيانات وسيلة الدفع - تحديث قديم"""
            try:
                methods = []
                updated = False
                
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == str(method_id):
                            row['account_data'] = new_account_data
                            updated = True
                        methods.append(row)
                
                if updated:
                    with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(methods)
                    
                    return True
                return False
            except Exception as e:
                return False
    
    def update_payment_method_complete(self, method_id, new_data):
            """تحديث شامل لوسيلة الدفع - جميع الحقول"""
            try:
                methods = []
                updated = False
                
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == str(method_id):
                            # تحديث جميع الحقول المطلوبة
                            if 'method_name' in new_data:
                                row['method_name'] = new_data['method_name']
                            if 'method_type' in new_data:
                                row['method_type'] = new_data['method_type']
                            if 'account_data' in new_data:
                                row['account_data'] = new_data['account_data']
                            if 'additional_info' in new_data:
                                row['additional_info'] = new_data['additional_info']
                            updated = True
                        methods.append(row)
                
                if updated:
                    with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(methods)
                    
                    return True
                return False
            except Exception as e:
                logger.error(f"خطأ في تحديث وسيلة الدفع {method_id}: {e}")
                return False
        
    def start_backup_scheduler(self):
            """بدء نظام النسخ الاحتياطي التلقائي كل 6 ساعات"""
            def backup_worker():
                while True:
                    try:
                        # انتظار 6 ساعات (21600 ثانية)
                        time.sleep(21600)  # 6 ساعات
                        self.send_backup_to_admins()
                    except Exception as e:
                        logger.error(f"خطأ في نظام النسخ الاحتياطي: {e}")
                        
            # تشغيل النظام في خيط منفصل
            backup_thread = threading.Thread(target=backup_worker, daemon=True)
            backup_thread.start()
            logger.info("تم بدء نظام النسخ الاحتياطي التلقائي (كل 6 ساعات)")
        
    def _recover_pending_states(self):
        """فحص المعاملات المعلّقة والجلسات المتوقفة عند إعادة التشغيل.

        تعمل في خيط خلفي بعد 15 ثانية من بدء البوت.
        ثلاثة سيناريوهات:
          • جلسة FSM متوقفة (5-30 دقيقة): إشعار باستئناف
          • جلسة FSM قديمة (> 30 دقيقة): إلغاء تلقائي + إشعار
          • معاملة pending في transactions.csv بلا جلسة مقابلة: تذكير
        """
        try:
            logger.info("🔄 بدء استرداد المعاملات المعلّقة...")
            now = datetime.now(timezone.utc)
            FIVE_MIN   = 5   * 60
            THIRTY_MIN = 30  * 60
            TWENTY4_H  = 24  * 60 * 60

            # ── 1. فحص جلسات FSM المعلّقة ─────────────────────────────────
            flow_prefixes = ('deposit_', 'withdraw_')
            all_states = self._db.get_all_user_states_with_timestamps()  # [(uid, state, ts)]
            for uid, state, updated_at_iso in all_states:
                if not any(state.startswith(p) for p in flow_prefixes):
                    continue
                try:
                    updated_at = datetime.fromisoformat(updated_at_iso)
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    age = (now - updated_at).total_seconds()
                except Exception:
                    age = 0

                if age < FIVE_MIN:
                    continue  # جلسة نشطة، لا تتدخل

                flow_type = 'إيداع' if state.startswith('deposit_') else 'سحب'

                if age >= TWENTY4_H:
                    # إلغاء تلقائي بعد 24 ساعة
                    try:
                        del self.user_states[uid]
                    except Exception:
                        pass
                    try:
                        self.send_message(
                            uid,
                            f"⚠️ <b>جلسة {flow_type} منتهية</b>\n\n"
                            f"انتهت صلاحية جلسة {flow_type} المفتوحة (أكثر من 24 ساعة).\n"
                            f"يرجى بدء طلب جديد عبر /start"
                        )
                    except Exception as e:
                        logger.warning(f"recovery: فشل إشعار إلغاء جلسة {uid}: {e}")

                elif age >= THIRTY_MIN:
                    # تنبيه: جلسة متوقفة أكثر من 30 دقيقة
                    try:
                        self.send_message(
                            uid,
                            f"⏸️ <b>جلسة {flow_type} متوقفة</b>\n\n"
                            f"يبدو أن جلسة {flow_type} الخاصة بك توقفت منذ {int(age//60)} دقيقة.\n"
                            f"أرسل أي رسالة لمتابعة الطلب، أو /start لبدء جلسة جديدة."
                        )
                    except Exception as e:
                        logger.warning(f"recovery: فشل إشعار جلسة متوقفة {uid}: {e}")

                else:
                    # 5-30 دقيقة: إشعار خفيف فقط
                    try:
                        self.send_message(
                            uid,
                            f"🔔 <b>متابعة طلب {flow_type}</b>\n\n"
                            f"لديك طلب {flow_type} لم يكتمل — أرسل أي رسالة للمتابعة."
                        )
                    except Exception as e:
                        logger.warning(f"recovery: فشل إشعار متابعة {uid}: {e}")

            # ── 2. فحص معاملات pending بلا جلسة FSM مقابلة ──────────────
            try:
                transactions = self.safe_csv_read('transactions.csv')
            except Exception:
                transactions = []

            pending_statuses = {'pending', 'pending_code_verification'}
            notified_uids_pending = set()

            for tx in transactions:
                status = tx.get('status', '').strip().lower()
                if status not in pending_statuses:
                    continue
                tx_uid = str(tx.get('telegram_id', '')).strip()
                if not tx_uid or tx_uid in notified_uids_pending:
                    continue

                # تحقق من أن المعاملة قديمة بما يكفي (> 5 دقائق)
                tx_date_str = tx.get('date', '')
                tx_age = TWENTY4_H  # افتراضي: قديمة
                try:
                    tx_date = datetime.fromisoformat(tx_date_str)
                    if tx_date.tzinfo is None:
                        tx_date = tx_date.replace(tzinfo=timezone.utc)
                    tx_age = (now - tx_date).total_seconds()
                except Exception:
                    pass

                if tx_age < FIVE_MIN:
                    continue  # معاملة حديثة جداً

                # تحقق أن المستخدم ليس في جلسة FSM نشطة الآن (تجنب الازدواجية)
                current_state = self.user_states.get(tx_uid)
                if current_state and any(current_state.startswith(p) for p in flow_prefixes):
                    continue  # الإشعار تمّ في الخطوة 1

                tx_type = 'إيداع' if tx.get('type', '').lower() == 'deposit' else 'سحب'
                tx_id = tx.get('id', '؟')
                tx_amount = tx.get('amount', '؟')

                try:
                    self.send_message(
                        tx_uid,
                        f"📋 <b>تذكير: طلب {tx_type} قيد المراجعة</b>\n\n"
                        f"🆔 رقم المعاملة: <code>{tx_id}</code>\n"
                        f"💰 المبلغ: {tx_amount}\n"
                        f"⏳ الحالة: في انتظار مراجعة الأدمن\n\n"
                        f"سيتم إشعارك فور الموافقة أو الرفض."
                    )
                    notified_uids_pending.add(tx_uid)
                except Exception as e:
                    logger.warning(f"recovery: فشل تذكير معاملة {tx_id} للمستخدم {tx_uid}: {e}")

            logger.info(
                f"✅ اكتمل استرداد المعاملات: {len(all_states)} جلسة فُحصت، "
                f"{len(notified_uids_pending)} معاملة pending أُشعر بها."
            )

            # ── 3. معالجة سجلات pending_transactions (جلسات في منتصف الإدخال) ──
            try:
                stale_flows = self._db.get_pending_transactions_older_than(FIVE_MIN)
                cancelled_count = 0
                reminded_count = 0
                for rec in stale_flows:
                    uid        = rec['user_id']
                    tx_id      = rec['tx_id']
                    tx_type    = rec['tx_type']
                    age        = rec['age_seconds']
                    company    = rec.get('company', '')
                    flow_label = 'إيداع' if tx_type == 'deposit' else 'سحب'

                    # تجاهل إذا كان المستخدم لا يزال في جلسة FSM نشطة
                    cur_state = self.user_states.get(uid)
                    if cur_state and any(cur_state.startswith(p) for p in flow_prefixes):
                        continue

                    if age >= THIRTY_MIN:
                        # إلغاء تلقائي بعد 30 دقيقة + إشعار المستخدم
                        try:
                            self._db.resolve_pending_transaction(tx_id, status='cancelled')
                        except Exception as _e:
                            logger.warning(f"recovery: فشل إلغاء {tx_id}: {_e}")
                        try:
                            self.send_message(
                                uid,
                                f"❌ <b>تم إلغاء طلب {flow_label}</b>\n\n"
                                f"انتهت مهلة إدخال بيانات طلب {flow_label}"
                                f"{' عبر ' + company if company else ''} "
                                f"({int(age // 60)} دقيقة).\n"
                                f"يرجى بدء طلب جديد عبر /start"
                            )
                        except Exception as _e:
                            logger.warning(f"recovery: فشل إشعار الإلغاء {uid}: {_e}")
                        cancelled_count += 1
                    else:
                        # 5-30 دقيقة: تذكير للاستئناف
                        try:
                            self.send_message(
                                uid,
                                f"🔔 <b>طلب {flow_label} غير مكتمل</b>\n\n"
                                f"توقف طلب {flow_label}"
                                f"{' عبر ' + company if company else ''} "
                                f"قبل {int(age // 60)} دقيقة.\n"
                                f"أرسل أي رسالة لمتابعة الإدخال، أو /start لبدء طلب جديد."
                            )
                        except Exception as _e:
                            logger.warning(f"recovery: فشل تذكير {uid}: {_e}")
                        reminded_count += 1

                logger.info(
                    f"✅ pending_transactions: {reminded_count} تذكير، {cancelled_count} إلغاء تلقائي."
                )
            except Exception as _e:
                logger.error(f"recovery: خطأ في معالجة pending_transactions: {_e}", exc_info=True)

        except Exception as e:
            logger.error(f"_recover_pending_states خطأ عام: {e}", exc_info=True)

    def create_backup_zip(self):
            """إنشاء ملف مضغوط يحتوي على جميع بيانات النظام"""
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_filename = f"DUX_Backup_{timestamp}.zip"
            
            try:
                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # إضافة ملفات البيانات الأساسية
                    files_to_backup = [
                        'users.csv',
                        'transactions.csv', 
                        'companies.csv',
                        'complaints.csv',
                        'payment_methods.csv',
                        'exchange_addresses.csv',
                        'system_settings.csv'
                    ]
                    
                    for file in files_to_backup:
                        if os.path.exists(file):
                            zipf.write(file)
                            
                    # إنشاء تقرير ملخص
                    self.create_summary_report(zipf, timestamp)
                    
                logger.info(f"تم إنشاء النسخة الاحتياطية: {zip_filename}")
                return zip_filename
                
            except Exception as e:
                logger.error(f"فشل في إنشاء النسخة الاحتياطية: {e}")
                return None
        
    def create_summary_report(self, zipf, timestamp):
            """إنشاء تقرير ملخص للنسخة الاحتياطية"""
            report_content = f"""تقرير النسخة الاحتياطية - {timestamp}
    {'=' * 50}
    
    📊 إحصائيات النظام:
    """
            
            try:
                # إحصائيات المستخدمين
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    users_count = len(list(csv.DictReader(f)))
                    report_content += self.tr('a0999_عدد_المستخدمين', 'ar', users_count=users_count)
                    
                # إحصائيات المعاملات
                with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    transactions = list(reader)
                    total_transactions = len(transactions)
                    pending = sum(1 for t in transactions if t['status'] == 'pending')
                    approved = sum(1 for t in transactions if t['status'] == 'approved')
                    rejected = sum(1 for t in transactions if t['status'] == 'rejected')
                    
                    report_content += self.tr('a1000_إجمالي_المعاملات', 'ar', total_transactions=total_transactions)
                    report_content += self.tr('a1001_معلقة', 'ar', pending=pending)
                    report_content += self.tr('a1002_موافقة', 'ar', approved=approved)
                    report_content += self.tr('a1003_مرفوضة', 'ar', rejected=rejected)
                    
                # إحصائيات الشركات
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    companies_count = len(list(csv.DictReader(f)))
                    report_content += self.tr('a1004_عدد_الشركات', 'ar', companies_count=companies_count)
                    
            except Exception as e:
                report_content += self.tr('a1005_خطأ_في', 'ar', e=e)
                
            report_content += f"\n📅 تاريخ النسخة: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            report_content += self.tr('a1006_البوت', 'ar')
            
            # حفظ التقرير كملف نصي داخل الـ ZIP
            zipf.writestr('backup_report.txt', report_content.encode('utf-8'))
        
    def send_document(self, chat_id, file_path, caption=""):
            """إرسال ملف لمحادثة معينة"""
            try:
                # قراءة الملف
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                
                # إعداد البيانات للإرسال
                url = f"{self.api_url}/sendDocument"
                
                # إنشاء multipart/form-data
                boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
                
                # بناء البيانات
                data = []
                data.append(f'--{boundary}')
                data.append('Content-Disposition: form-data; name="chat_id"')
                data.append('')
                data.append(str(chat_id))
                
                if caption:
                    data.append(f'--{boundary}')
                    data.append('Content-Disposition: form-data; name="caption"')
                    data.append('')
                    data.append(caption)
                
                data.append(f'--{boundary}')
                data.append(f'Content-Disposition: form-data; name="document"; filename="{os.path.basename(file_path)}"')
                data.append('Content-Type: application/zip')
                data.append('')
                
                # تحويل إلى bytes
                body = '\r\n'.join(data).encode('utf-8')
                body += b'\r\n' + file_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')
                
                # إنشاء الطلب
                req = urllib.request.Request(url, data=body)
                req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                
                # إرسال الطلب
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    return result
                    
            except Exception as e:
                logger.error(f"فشل في إرسال الملف: {e}")
                return None
        
    def get_chat_id_by_username(self, username):
            """الحصول على معرف المحادثة من اسم المستخدم"""
            try:
                # إزالة علامة @ إذا كانت موجودة
                if username.startswith('@'):
                    username = username[1:]
                
                # استخدام getChat API للحصول على معلومات المحادثة
                url = f"{self.api_url}/getChat"
                data = {'chat_id': f'@{username}'}
                
                req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'))
                req.add_header('Content-Type', 'application/json')
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    
                    if result.get('ok') and 'result' in result:
                        return result['result']['id']
                        
            except Exception as e:
                logger.error(f"فشل في الحصول على معرف {username}: {e}")
                
            return None
    
    def send_backup_to_admins(self):
            """إرسال النسخة الاحتياطية لجميع الإدارة"""
            logger.info("بدء إرسال النسخة الاحتياطية للإدارة...")
            
            # إنشاء النسخة الاحتياطية
            backup_file = self.create_backup_zip()
            
            if not backup_file:
                logger.error("فشل في إنشاء النسخة الاحتياطية")
                return
                
            try:
                # رسالة مرافقة للنسخة الاحتياطية
                caption = f"""📦 نسخة احتياطية تلقائية
    
    🤖 البوت: @depositbettingbot
    📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    ⏰ النسخ التلقائي: كل 6 ساعات
    
    📋 المحتويات:
    • بيانات المستخدمين
    • المعاملات المالية
    • الشركات ووسائل الدفع
    • الشكاوى والإعدادات
    • تقرير إحصائي شامل
    
    🔒 البيانات آمنة ومشفرة"""
    
                # إرسال لحساب @Aba10o0 المحدد (إذا تم تفعيله)
                backup_recipients = [
                    # إضافة المعرف الرقمي هنا عندما يصبح متاحاً
                    # مثال: 123456789  # @Aba10o0
                ]
                
                for recipient_id in backup_recipients:
                    try:
                        result = self.send_document(recipient_id, backup_file, caption)
                        if result and result.get('ok'):
                            logger.info(f"تم إرسال النسخة الاحتياطية بنجاح للمستلم: {recipient_id}")
                        else:
                            logger.error(f"فشل في إرسال النسخة للمستلم: {recipient_id}")
                    except Exception as e:
                        logger.error(f"خطأ في إرسال النسخة للمستلم {recipient_id}: {e}")
                    
                # إرسال للإدارة العادية أيضاً كنسخة احتياطية
                sent_count = 0
                for admin_id in self.admin_ids:
                    try:
                        if str(admin_id).isdigit():  # إرسال فقط للمعرفات الرقمية
                            result = self.send_document(admin_id, backup_file, caption)
                            if result and result.get('ok'):
                                sent_count += 1
                                logger.info(f"تم إرسال النسخة الاحتياطية للإدارة: {admin_id}")
                            else:
                                logger.error(f"فشل في إرسال النسخة للإدارة: {admin_id}")
                    except Exception as e:
                        logger.error(f"خطأ في إرسال النسخة للإدارة {admin_id}: {e}")
                        
                # حذف الملف المؤقت
                try:
                    os.remove(backup_file)
                    logger.info(f"تم حذف الملف المؤقت: {backup_file}")
                except:
                    pass
                    
                logger.info(f"تم إرسال النسخة الاحتياطية لـ {sent_count} مدير")
                
            except Exception as e:
                logger.error(f"خطأ في إرسال النسخة الاحتياطية: {e}")
        
    def show_notifications_panel(self, message):
            """عرض لوحة الإشعارات الذكية"""
            notifs = self.get_recent_notifications(15)
            
            if not notifs:
                self.send_message(message['chat']['id'], self.tr('a1007_لا_توجد', 'ar'), self.admin_keyboard())
                return
            
            # تصنيف الإشعارات حسب النوع
            by_type = {}
            for n in notifs:
                ntype = n.get('type', 'general')
                if ntype not in by_type:
                    by_type[ntype] = 0
                by_type[ntype] += 1
            
            summary = self.tr('a1008_لوحة_الإشعارات', 'ar')
            type_icons = {
                'new_deposit': '💰', 'new_withdraw': '💸', 'new_complaint': '📨',
                'new_user': '🆕', 'new_match': '🔄', 'dispute': '⚖️',
                'code_verification': '🔐', 'transaction_approved': '✅',
                'transaction_rejected': '❌', 'admin_action': '🛠️', 'general': '📋'
            }
            for ntype, count in by_type.items():
                icon = type_icons.get(ntype, '📋')
                summary += f"{icon} {ntype}: {count}\n"
            
            summary += f"\n📋 آخر {len(notifs)} إشعار:\n\n"
            
            for n in reversed(notifs):
                icon = type_icons.get(n.get('type', ''), '📋')
                summary += f"{icon} {n.get('timestamp', '')} → {n.get('message_preview', '')}\n"
            
            self.send_message(message['chat']['id'], summary, self.admin_keyboard())

    def manual_backup_command(self, message):
            """أمر يدوي لإنشاء وإرسال نسخة احتياطية فورية"""
            if not self.is_admin(message['from']['id']):
                return
                
            self.send_message(message['chat']['id'], self.tr('a1009_جاري_إنشاء', 'ar'))
            
            # إنشاء وإرسال النسخة
            backup_file = self.create_backup_zip()
            
            if backup_file:
                caption = f"""📦 نسخة احتياطية يدوية
    
    🤖 البوت: @depositbettingbot  
    📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    👨‍💼 طلب من: الإدارة
    
    📋 جميع بيانات النظام محفوظة في هذا الملف"""
    
                result = self.send_document(message['chat']['id'], backup_file, caption)
                
                if result and result.get('ok'):
                    self.send_message(message['chat']['id'], self.tr('a1010_تم_إرسال', 'ar'))
                else:
                    self.send_message(message['chat']['id'], self.tr('a1011_فشل_في', 'ar'))
                    
                # حذف الملف المؤقت
                try:
                    os.remove(backup_file)
                except:
                    pass
            else:
                self.send_message(message['chat']['id'], self.tr('a1012_فشل_في', 'ar'))
        
    def handle_complaint_reply_buttons(self, message, complaint_id):
            """معالجة أزرار الرد على الشكاوى"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text == self.tr('a1013_العودة_للشكاوى', 'ar'):
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_complaints_admin(message)
                return
            
            # تحديد نوع الرد
            reply_message = ""
            if text.startswith(self.tr('a1014_تم_الحل', 'ar')):
                reply_message = self.tr('a0430_شكراً_لتواصلك', 'ar')
            elif text.startswith(self.tr('a1015_قيد_المراجعة', 'ar')):
                reply_message = self.tr('a0432_نحن_نراجع', 'ar')
            elif text.startswith(self.tr('a1016_سنتواصل_معك', 'ar')):
                reply_message = self.tr('a0434_سنتواصل_معك', 'ar')
            elif text.startswith(self.tr('a1017_رد_مخصص', 'ar')):
                # طلب رد مخصص
                custom_text = self.tr('a1018_اكتب_ردك', 'ar')
                
                self.send_message(message['chat']['id'], custom_text)
                self.user_states[user_id] = f'writing_custom_reply_{complaint_id}'
                return
            
            # حفظ الرد وإرساله للعميل
            if reply_message:
                success = self.save_complaint_reply(complaint_id, reply_message)
                if success:
                    self.send_message(message['chat']['id'], self.tr('a1019_تم_إرسال', 'ar', reply_message=reply_message), self.admin_keyboard())
                    # إرسال الرد للعميل
                    self.send_complaint_reply_to_customer(complaint_id, reply_message)
                else:
                    self.send_message(message['chat']['id'], self.tr('a0226_فشل_في', 'ar'), self.admin_keyboard())
            
            # تنظيف الحالة
            if user_id in self.user_states:
                del self.user_states[user_id]
        
    def save_complaint_reply(self, complaint_id, reply_message):
            """حفظ رد الشكوى"""
            try:
                complaints = []
                updated = False
                
                with open('complaints.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == complaint_id:
                            row['status'] = 'resolved'
                            row['admin_response'] = reply_message
                            updated = True
                            logger.info(f"تم العثور على الشكوى {complaint_id} وتحديثها")
                        complaints.append(row)
                
                if updated:
                    with open('complaints.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        fieldnames = ['id', 'customer_id', 'subject', 'message', 'status', 'date', 'admin_response']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        
                        # تنظيف البيانات قبل الكتابة
                        clean_complaints = []
                        for complaint in complaints:
                            clean_complaint = {}
                            for field in fieldnames:
                                clean_complaint[field] = complaint.get(field, '')
                            clean_complaints.append(clean_complaint)
                        
                        writer.writerows(clean_complaints)
                    
                    return True
                
                return False
            except Exception as e:
                logger.error(f"خطأ في حفظ رد الشكوى {complaint_id}: {e}")
                return False
        
    def send_complaint_reply_to_customer(self, complaint_id, reply_message):
            """إرسال رد الشكوى للعميل"""
            try:
                # البحث عن بيانات العميل
                customer_telegram_id = None
                
                with open('complaints.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['id'] == complaint_id:
                            customer_id = row['customer_id']
                            
                            # البحث عن التليجرام ID من ملف المستخدمين
                            with open('users.csv', 'r', encoding='utf-8-sig') as users_file:
                                users_reader = csv.DictReader(users_file)
                                for user_row in users_reader:
                                    if user_row['customer_id'] == customer_id:
                                        customer_telegram_id = user_row['telegram_id']
                                        break
                            break
                
                if customer_telegram_id:
                    customer_message = self.tr('a1020_رد_على', 'ar', complaint_id=complaint_id, reply_message=reply_message)
                    
                    # إرسال الرد للعميل بدون كيبورد لعدم التداخل
                    result = self.send_message_without_keyboard(customer_telegram_id, customer_message)
                    if result and result.get('ok'):
                        logger.info(f"✅ تم إرسال رد الشكوى {complaint_id} للعميل {customer_telegram_id} بنجاح")
                    else:
                        logger.error(f"❌ فشل في إرسال رد الشكوى {complaint_id} للعميل {customer_telegram_id}")
                        # محاولة أخرى بالطريقة العادية
                        self.send_message(customer_telegram_id, customer_message)
                    
            except Exception as e:
                logger.error(f"خطأ في إرسال رد الشكوى للعميل: {e}")
        
    def send_message_without_keyboard(self, chat_id, text):
            """إرسال رسالة بدون كيبورد"""
            try:
                url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                data = {
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': 'Markdown'
                }
                
                # تحويل البيانات إلى JSON
                json_data = json.dumps(data).encode('utf-8')
                
                # إنشاء الطلب
                req = urllib.request.Request(url, data=json_data, headers={
                    'Content-Type': 'application/json',
                    'Content-Length': len(json_data)
                })
                
                # إرسال الطلب
                with urllib.request.urlopen(req) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    return result
                    
            except Exception as e:
                logger.error(f"خطأ في إرسال رسالة بدون لوحة مفاتيح: {e}")
                # محاولة بديلة بالطريقة العادية
                try:
                    return self.send_message(chat_id, text)
                except:
                    return None
        
    def show_support_data_editor(self, message):
        """عرض محرر بيانات الدعم — بأزرار inline"""
        phone = self.get_support_setting('support_phone', '+966501234567')
        telegram = self.get_support_setting('support_telegram', '@DUX_support')
        email = self.get_support_setting('support_email', 'support@dux.com')
        hours = self.get_support_setting('support_hours', '24/7')

        text = (
            f"🛠️ <b>بيانات الدعم</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📞 الهاتف: <code>{phone}</code>\n"
            f"💬 تليجرام: <code>{telegram}</code>\n"
            f"📧 البريد: <code>{email}</code>\n"
            f"🕒 ساعات العمل: <b>{hours}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"اختر ما تريد تعديله:"
        )

        inline_btns = [
            [{'text': f'📞 تعديل الهاتف', 'callback_data': 'support_edit_phone'},
             {'text': f'💬 تعديل تليجرام', 'callback_data': 'support_edit_telegram'}],
            [{'text': f'📧 تعديل البريد', 'callback_data': 'support_edit_email'},
             {'text': f'🕒 تعديل الساعات', 'callback_data': 'support_edit_hours'}],
            [{'text': '🔙 العودة للوحة الأدمن', 'callback_data': 'support_back_admin'}]
        ]
        self.send_inline_message(message['chat']['id'], text, inline_btns)
        
    def start_phone_edit_wizard(self, message):
        """بدء تعديل رقم الهاتف"""
        current = self.get_support_setting('support_phone', '+966501234567')
        self.send_message(message['chat']['id'],
            f"📞 <b>تعديل رقم الهاتف</b>\n\n"
            f"الرقم الحالي: <code>{current}</code>\n\n"
            f"✍️ اكتب الرقم الجديد:\n"
            f"مثال: <code>+966987654321</code>\n\n"
            f"أو اكتب <code>إلغاء</code> للرجوع")
        self.user_states[message['from']['id']] = 'editing_support_phone'

    def start_telegram_edit_wizard(self, message):
        """بدء تعديل حساب التليجرام"""
        current = self.get_support_setting('support_telegram', '@DUX_support')
        self.send_message(message['chat']['id'],
            f"💬 <b>تعديل حساب التليجرام</b>\n\n"
            f"الحساب الحالي: <code>{current}</code>\n\n"
            f"✍️ اكتب الحساب الجديد:\n"
            f"مثال: <code>@DUX_support</code>\n\n"
            f"أو اكتب <code>إلغاء</code> للرجوع")
        self.user_states[message['from']['id']] = 'editing_support_telegram'

    def start_email_edit_wizard(self, message):
        """بدء تعديل البريد الإلكتروني"""
        current = self.get_support_setting('support_email', 'support@dux.com')
        self.send_message(message['chat']['id'],
            f"📧 <b>تعديل البريد الإلكتروني</b>\n\n"
            f"البريد الحالي: <code>{current}</code>\n\n"
            f"✍️ اكتب البريد الجديد:\n"
            f"مثال: <code>support@dux.com</code>\n\n"
            f"أو اكتب <code>إلغاء</code> للرجوع")
        self.user_states[message['from']['id']] = 'editing_support_email'

    def start_hours_edit_wizard(self, message):
        """بدء تعديل ساعات العمل"""
        current = self.get_support_setting('support_hours', '24/7')
        self.send_message(message['chat']['id'],
            f"🕒 <b>تعديل ساعات العمل</b>\n\n"
            f"الساعات الحالية: <b>{current}</b>\n\n"
            f"✍️ اكتب ساعات العمل الجديدة:\n"
            f"مثال: <code>8 صباحاً - 10 مساءً</code>\n\n"
            f"أو اكتب <code>إلغاء</code> للرجوع")
        self.user_states[message['from']['id']] = 'editing_support_hours'
        
    def handle_support_data_edit(self, message, state):
        """معالجة تعديل بيانات الدعم"""
        text = message.get('text', '').strip()
        user_id = message['from']['id']

        if text in ['/cancel', self.tr('a0010_إلغاء', 'ar'), self.tr('a0011_الغاء', 'ar')]:
            if user_id in self.user_states:
                del self.user_states[user_id]
            self.show_support_data_editor(message)
            return

        # تحديد نوع التعديل
        if state == 'editing_support_phone':
            success_msg = self.tr('a1021_تم_تحديث', 'ar', text=text)
            self.save_setting('support_phone', text)
        elif state == 'editing_support_telegram':
            success_msg = self.tr('a1022_تم_تحديث', 'ar', text=text)
            self.save_setting('support_telegram', text)
        elif state == 'editing_support_email':
            success_msg = self.tr('a1023_تم_تحديث', 'ar', text=text)
            self.save_setting('support_email', text)
        elif state == 'editing_support_hours':
            success_msg = self.tr('a1024_تم_تحديث', 'ar', text=text)
            self.save_setting('support_hours', text)
        else:
            success_msg = self.tr('a1025_خطأ_في', 'ar')

        # إرسال رسالة التأكيد والعودة لمحرر البيانات
        self.send_message(message['chat']['id'], success_msg)
        # تنظيف الحالة
        if user_id in self.user_states:
            del self.user_states[user_id]
        # إعادة عرض لوحة الدعم
        self.show_support_data_editor(message)
        
    def save_support_setting(self, key, value):
        """حفظ إعداد الدعم — يستخدم save_setting الموحدة"""
        self.save_setting(key, value)
        
    def get_support_setting(self, key, default=None):
        """قراءة إعداد الدعم — يستخدم get_setting الموحدة"""
        if default is None:
            default = self.tr('a0122_غير_محدد', 'ar')
        val = self.get_setting(key)
        return val if val else default
        
    def show_currency_selection(self, message):
            """عرض قائمة العملات للاختيار"""
            user = self.find_user(message['from']['id'])
            lang = user.get('language', 'ar') if user else 'ar'
            currency_text = (
                f"{self.tr('currency_select_title', lang)}\n\n"
                f"    {self.tr('currency_select_prompt', lang)}\n"
                f"    {self.tr('currency_select_note', lang)}\n\n"
                f"    {self.tr('currency_available', lang)}"
            )
            
            keyboard = []
            
            # تجميع العملات في مجموعات
            arab_currencies = ['SAR', 'AED', 'EGP', 'KWD', 'QAR', 'BHD', 'OMR', 'JOD', 'LBP', 'IQD', 'SYP', 'MAD', 'TND', 'DZD', 'LYD']
            international_currencies = ['USD', 'EUR', 'TRY']
            
            # العملات العربية
            for currency in arab_currencies:
                if currency in self.currencies:
                    curr_info = self.currencies[currency]
                    keyboard.append([{'text': f"{curr_info['flag']} {curr_info['name']} ({curr_info['symbol']})"}])
            
            # العملات الدولية
            for currency in international_currencies:
                if currency in self.currencies:
                    curr_info = self.currencies[currency]
                    keyboard.append([{'text': f"{curr_info['flag']} {curr_info['name']} ({curr_info['symbol']})"}])
            
            keyboard.append([{'text': self.tr('back_to_main', lang)}])
            
            reply_keyboard = {
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            self.user_states[message['from']['id']] = 'selecting_currency'
            self.send_message(message['chat']['id'], currency_text, reply_keyboard)
        
    def handle_currency_selection(self, message, currency_text):
            """معالجة اختيار العملة"""
            try:
                user_id = message['from']['id']
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                
                # البحث عن العملة المحددة
                selected_currency = None
                for code, info in self.currencies.items():
                    if currency_text.startswith(info['flag']):
                        selected_currency = code
                        break
                
                if not selected_currency:
                    self.send_message(message['chat']['id'], self.tr('currency_invalid', lang), self.main_keyboard(lang, user_id))
                    return
                
                # تحديث عملة المستخدم
                users = []
                updated = False
                
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['telegram_id'] == str(user_id):
                            row['currency'] = selected_currency
                            updated = True
                        if 'currency' not in row or not row['currency']:
                            row['currency'] = selected_currency if row['telegram_id'] == str(user_id) else 'SAR'
                        users.append(row)
                
                if updated:
                    fieldnames = ['telegram_id', 'name', 'phone', 'customer_id', 'language', 'date', 'is_banned', 'ban_reason', 'currency']
                    
                    with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(users)
                    
                    curr_info = self.currencies[selected_currency]
                    success_msg = (
                        f"{self.tr('currency_changed_success', lang)}\n\n"
                        f"    {self.tr('currency_new', lang)}: {curr_info['name']}\n"
                        f"    {self.tr('currency_symbol', lang)}: {curr_info['symbol']}\n"
                        f"    {curr_info['flag']}\n\n"
                        f"    {self.tr('currency_hint', lang)}"
                    )
                    self.send_message(message['chat']['id'], success_msg, self.main_keyboard(lang, user_id))
                    logger.info(f"تم تغيير عملة المستخدم {user_id} إلى {selected_currency}")
                else:
                    self.send_message(message['chat']['id'], self.tr('currency_update_error', lang), self.main_keyboard(lang, user_id))
                
                if user_id in self.user_states:
                    del self.user_states[user_id]
                    
            except Exception as e:
                logger.error(f"خطأ في تغيير العملة: {e}")
                u = self.find_user(message['from']['id'])
                ul = u.get('language', 'ar') if u else 'ar'
                self.send_message(message['chat']['id'], self.tr('currency_change_error', ul), self.main_keyboard(ul, message['from']['id']))
        
    def get_currency_symbol(self, user_currency='SAR'):
            """جلب رمز العملة"""
            return self.currencies.get(user_currency, self.currencies['SAR'])['symbol']
        
    def format_amount_with_currency(self, amount, user_currency='SAR'):
            """تنسيق المبلغ مع العملة"""
            symbol = self.get_currency_symbol(user_currency)
            return f"{amount} {symbol}"
        
    def generate_professional_excel_report(self, message):
            """إنشاء تقرير Excel احترافي"""
            chat_id = message['chat']['id']
            
            try:
                self.send_message(chat_id, self.tr('a1026_جاري_إنشاء', lang))
                
                # إنشاء ملف تقرير احترافي
                filename = self.create_professional_excel_report()
                
                if filename and os.path.exists(filename):
                    # إرسال الملف
                    self.send_document(chat_id, filename, self.tr('a1027_تقرير_احترافي', lang))
                    
                    success_text = self.tr('a1028_تم_إنشاء', 'ar')
                    
                    self.send_message(chat_id, success_text, self.admin_keyboard())
                else:
                    self.send_message(chat_id, self.tr('a1029_فشل_في', 'ar'), self.admin_keyboard())
                    
            except Exception as e:
                logger.error(f"خطأ في إنشاء تقرير Excel: {e}")
                self.send_message(chat_id, f"❌ خطأ في إنشاء التقرير: {str(e)}", self.admin_keyboard())
        
    def create_professional_excel_report(self):
            """إنشاء ملف تقرير احترافي منسق"""
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"DUX_Professional_Report_{timestamp}.csv"
                
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    
                    # عنوان التقرير الرئيسي
                    writer.writerow(['📊 تقرير نظام DUX المالي الشامل 📊'])
                    writer.writerow([f'📅 تاريخ التقرير: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
                    writer.writerow(['═══════════════════════════════════════════════════════════'])
                    writer.writerow([''])
                    
                    # قسم 1: الإحصائيات الشاملة أولاً
                    writer.writerow(['📊═══ الإحصائيات الشاملة ═══'])
                    stats = self.calculate_comprehensive_statistics()
                    for category, data in stats.items():
                        writer.writerow([f'📋 {category}'])
                        writer.writerow(['───────────────────────────'])
                        for key, value in data.items():
                            writer.writerow([f'• {key}', value])
                        writer.writerow([''])
                    
                    writer.writerow(['═══════════════════════════════════════════════════════════'])
                    writer.writerow([''])
                    
                    # قسم 2: بيانات المستخدمين
                    writer.writerow(['👥═══ بيانات المستخدمين ═══'])
                    if os.path.exists('users.csv'):
                        with open('users.csv', 'r', encoding='utf-8-sig') as uf:
                            user_reader = csv.reader(uf)
                            for row in user_reader:
                                writer.writerow(row)
                    else:
                        writer.writerow(['لا توجد بيانات مستخدمين'])
                    writer.writerow([''])
                    
                    # قسم 3: بيانات المعاملات
                    writer.writerow(['💳═══ بيانات المعاملات ═══'])
                    if os.path.exists('transactions.csv'):
                        with open('transactions.csv', 'r', encoding='utf-8-sig') as tf:
                            trans_reader = csv.reader(tf)
                            for row in trans_reader:
                                writer.writerow(row)
                    else:
                        writer.writerow(['لا توجد بيانات معاملات'])
                    writer.writerow([''])
                    
                    # قسم 4: بيانات الشكاوى
                    writer.writerow(['📨═══ بيانات الشكاوى ═══'])
                    if os.path.exists('complaints.csv'):
                        with open('complaints.csv', 'r', encoding='utf-8-sig') as cf:
                            comp_reader = csv.reader(cf)
                            for row in comp_reader:
                                writer.writerow(row)
                    else:
                        writer.writerow(['لا توجد بيانات شكاوى'])
                    writer.writerow([''])
                    
                    # قسم 5: بيانات الشركات
                    writer.writerow(['🏢═══ بيانات الشركات ═══'])
                    if os.path.exists('companies.csv'):
                        with open('companies.csv', 'r', encoding='utf-8-sig') as compf:
                            comp_reader = csv.reader(compf)
                            for row in comp_reader:
                                writer.writerow(row)
                    else:
                        writer.writerow(['لا توجد بيانات شركات'])
                    writer.writerow([''])
                    
                    # قسم 6: وسائل الدفع
                    writer.writerow(['💳═══ وسائل الدفع ═══'])
                    if os.path.exists('payment_methods.csv'):
                        with open('payment_methods.csv', 'r', encoding='utf-8-sig') as pmf:
                            pm_reader = csv.reader(pmf)
                            for row in pm_reader:
                                writer.writerow(row)
                    else:
                        writer.writerow(['لا توجد وسائل دفع'])
                    writer.writerow([''])
                    
                    # خاتمة التقرير
                    writer.writerow(['═══════════════════════════════════════════════════════════'])
                    writer.writerow([f'📈 تم إنشاء التقرير بواسطة نظام DUX - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
                    writer.writerow(['🔒 هذا التقرير سري ومخصص للإدارة فقط'])
                
                return filename
                
            except Exception as e:
                logger.error(f"خطأ في إنشاء التقرير: {e}")
                return None
        
    def calculate_comprehensive_statistics(self):
            """حساب إحصائيات شاملة للنظام"""
            stats = {}
            
            try:
                # إحصائيات المستخدمين
                if os.path.exists('users.csv'):
                    with open('users.csv', 'r', encoding='utf-8-sig') as f:
                        users = list(csv.DictReader(f))
                        
                        # تحليل العملات واللغات
                        currency_stats = {}
                        language_stats = {}
                        for user in users:
                            currency = user.get('currency', 'SAR')
                            language = user.get('language', 'ar')
                            currency_stats[currency] = currency_stats.get(currency, 0) + 1
                            language_stats[language] = language_stats.get(language, 0) + 1
                        
                        user_stats = {
                            self.tr('a1030_إجمالي_المستخدمين', 'ar'): len(users),
                            self.tr('a1031_المستخدمين_النشطين', 'ar'): len([u for u in users if u.get('is_banned', 'no').lower() != 'yes']),
                            self.tr('a1032_المستخدمين_المحظورين', 'ar'): len([u for u in users if u.get('is_banned', 'no').lower() == 'yes']),
                            self.tr('a1033_نسبة_المستخدمين', 'ar'): f"{(len([u for u in users if u.get('is_banned', 'no').lower() != 'yes'])/len(users)*100):.1f}%" if users else "0%"
                        }
                        
                        # إضافة إحصائيات العملات
                        for currency, count in currency_stats.items():
                            currency_name = self.currencies.get(currency, {}).get('name', currency)
                            user_stats[self.tr('a1034_مستخدمي', 'ar', currency_name=currency_name)] = f"{count} ({(count/len(users)*100):.1f}%)"
                        
                        stats[self.tr('a1035_إحصائيات_المستخدمين', 'ar')] = user_stats
                
                # إحصائيات المعاملات
                if os.path.exists('transactions.csv'):
                    with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                        transactions = list(csv.DictReader(f))
                        
                        approved = [t for t in transactions if t.get('status') == 'approved']
                        rejected = [t for t in transactions if t.get('status') == 'rejected']
                        pending = [t for t in transactions if t.get('status') == 'pending']
                        deposits = [t for t in transactions if t.get('type') == 'deposit']
                        withdrawals = [t for t in transactions if t.get('type') == 'withdraw']
                        
                        def safe_float(value):
                            try:
                                return float(str(value).replace(',', '')) if value else 0.0
                            except:
                                return 0.0
                        
                        total_approved_amount = sum(safe_float(t.get('amount', 0)) for t in approved)
                        total_deposit_amount = sum(safe_float(t.get('amount', 0)) for t in deposits if t.get('status') == 'approved')
                        total_withdrawal_amount = sum(safe_float(t.get('amount', 0)) for t in withdrawals if t.get('status') == 'approved')
                        
                        transaction_stats = {
                            self.tr('a1036_إجمالي_المعاملات', 'ar'): len(transactions),
                            self.tr('a1037_المعاملات_المُوافقة', 'ar'): f"{len(approved)} ({(len(approved)/len(transactions)*100):.1f}%)" if transactions else "0",
                            self.tr('a1038_المعاملات_المرفوضة', 'ar'): f"{len(rejected)} ({(len(rejected)/len(transactions)*100):.1f}%)" if transactions else "0",
                            self.tr('a1039_المعاملات_المعلقة', 'ar'): f"{len(pending)} ({(len(pending)/len(transactions)*100):.1f}%)" if transactions else "0",
                            self.tr('a1040_طلبات_الإيداع', 'ar'): f"{len(deposits)} ({(len(deposits)/len(transactions)*100):.1f}%)" if transactions else "0",
                            self.tr('a1041_طلبات_السحب', 'ar'): f"{len(withdrawals)} ({(len(withdrawals)/len(transactions)*100):.1f}%)" if transactions else "0",
                            self.tr('a1042_معدل_الموافقة', 'ar'): f"{(len(approved)/len(transactions)*100):.1f}%" if transactions else "0%",
                            self.tr('a1043_إجمالي_المبالغ', 'ar'): f"{total_approved_amount:,.2f}",
                            self.tr('a1044_إجمالي_الإيداعات', 'ar'): f"{total_deposit_amount:,.2f}",
                            self.tr('a1045_إجمالي_السحوبات', 'ar'): f"{total_withdrawal_amount:,.2f}",
                            self.tr('a1046_صافي_الحركة', 'ar'): f"{total_deposit_amount - total_withdrawal_amount:,.2f}",
                            self.tr('a1047_متوسط_قيمة', 'ar'): f"{(total_approved_amount/len(approved)):,.2f}" if approved else "0"
                        }
                        
                        stats[self.tr('a1048_إحصائيات_المعاملات', 'ar')] = transaction_stats
                
                # إحصائيات الشكاوى والشركات
                if os.path.exists('complaints.csv'):
                    with open('complaints.csv', 'r', encoding='utf-8-sig') as f:
                        complaints = list(csv.DictReader(f))
                        resolved = [c for c in complaints if c.get('status') == 'resolved']
                        pending_complaints = [c for c in complaints if c.get('status') == 'pending']
                        
                        stats[self.tr('a1049_إحصائيات_الشكاوى', 'ar')] = {
                            self.tr('a1050_إجمالي_الشكاوى', 'ar'): len(complaints),
                            self.tr('a1051_الشكاوى_المحلولة', 'ar'): f"{len(resolved)} ({(len(resolved)/len(complaints)*100):.1f}%)" if complaints else "0",
                            self.tr('a1052_الشكاوى_المعلقة', 'ar'): f"{len(pending_complaints)} ({(len(pending_complaints)/len(complaints)*100):.1f}%)" if complaints else "0",
                            self.tr('a1053_معدل_الحل', 'ar'): f"{(len(resolved)/len(complaints)*100):.1f}%" if complaints else "0%"
                        }
                
                if os.path.exists('companies.csv'):
                    with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                        companies = list(csv.DictReader(f))
                        active = [c for c in companies if c.get('is_active', '').lower() == 'active']
                        
                        stats[self.tr('a1054_إحصائيات_الشركات', 'ar')] = {
                            self.tr('a1055_إجمالي_الشركات', 'ar'): len(companies),
                            self.tr('a1056_الشركات_النشطة', 'ar'): f"{len(active)} ({(len(active)/len(companies)*100):.1f}%)" if companies else "0",
                            self.tr('a1057_الشركات_غير', 'ar'): f"{len(companies) - len(active)}"
                        }
            
            except Exception as e:
                logger.error(f"خطأ في حساب الإحصائيات: {e}")
            
            return stats



    # ==============================
    #   نظام صلاحيات المديرين والأفعال
    # ==============================
    def load_admin_permissions(self):
        """تحميل صلاحيات المديرين من ملف JSON مستقل."""
        try:
            with open('admin_permissions.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except FileNotFoundError:
            # أول تشغيل: لا يوجد ملف بعد
            return {}
        except Exception as e:
            logger.error(f"خطأ في قراءة admin_permissions.json: {e}")
        return {}

    def save_admin_permissions(self):
        """حفظ صلاحيات المديرين في ملف JSON."""
        try:
            with open('admin_permissions.json', 'w', encoding='utf-8') as f:
                json.dump(self.admin_permissions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"خطأ في حفظ admin_permissions.json: {e}")

    def get_admin_permissions_for(self, admin_id):
        """إرجاع قاموس صلاحيات مدير معيّن، يُنشئ إدخال افتراضي عند الحاجة."""
        admin_key = str(admin_id)
        info = self.admin_permissions.get(admin_key)
        if not info or not isinstance(info, dict):
            info = {"buttons": {}}
            self.admin_permissions[admin_key] = info
        buttons = info.get("buttons")
        if not isinstance(buttons, dict):
            buttons = {}
            info["buttons"] = buttons
        return buttons

    def set_admin_button_permission(self, admin_id, button_label, allowed: bool, actor_id=None):
        """تعيين صلاحية زر معيّن لمدير معيّن مع تسجيل العملية في سجل المدراء."""
        admin_key = str(admin_id)
        buttons = self.get_admin_permissions_for(admin_id)
        buttons[button_label] = bool(allowed)
        self.save_admin_permissions()
        # تسجيل العملية
        self.log_admin_action(
            actor_id or admin_id,
            "set_button_permission",
            f"target_admin={admin_key}, button='{button_label}', allowed={bool(allowed)}"
        )

    def admin_has_button_permission(self, admin_id, button_label) -> bool:
        """التحقق هل يحق للمدير رؤية / استخدام زر معيّن في لوحة الأدمن.

        - المدراء الأساسيون في self.admin_ids لديهم صلاحية كاملة دائماً.
        - المدراء الذين لا يملكون إدخالاً في ملف JSON يحصلون افتراضياً على كل الأزرار.
        - لو هناك إدخال، يتم استخدام القيمة المخزّنة، والافتراضي True عند عدم وجود المفتاح.
        """
        # أصحاب الصلاحية الكاملة (من ملف admins.csv مثلاً) لا يتم تقييدهم
        try:
            if str(admin_id) in self.admin_ids:
                return True
        except Exception:
            pass

        buttons = self.get_admin_permissions_for(admin_id)
        if not buttons:
            # لا توجد صلاحيات مخصّصة -> اعتبر كل الأزرار متاحة
            return True
        return bool(buttons.get(button_label, True))

    def cleanup_expired_temp_admins(self):
        """إزالة أي مدير مؤقت انتهت صلاحيته (إن وُجدت بيانات انتهاء في temp_admin_expiry)."""
        try:
            now = time.time()
            to_remove = []
            for admin_id, ts in list(self.temp_admin_expiry.items()):
                if ts <= now:
                    to_remove.append(admin_id)

            for admin_id in to_remove:
                if admin_id in self.temp_admin_user_ids:
                    try:
                        self.temp_admin_user_ids.remove(admin_id)
                    except ValueError:
                        pass
                self.temp_admin_expiry.pop(admin_id, None)
                logger.info(f"تم إنهاء صلاحيات الأدمن المؤقت: {admin_id}")
        except Exception as e:
            logger.error(f"خطأ في تنظيف المدراء المؤقتين المنتهين: {e}")

    def log_admin_action(self, admin_id, action_type: str, details: str = ""):
        """تسجيل أي تعديل يقوم به الأدمن في ملف CSV مستقل.

        الأعمدة: timestamp, admin_id, action_type, details
        """
        try:
            file_exists = os.path.exists('admin_actions_log.csv')
            with open('admin_actions_log.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'admin_id', 'action_type', 'details'])
                writer.writerow([
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    str(admin_id),
                    action_type,
                    details
                ])
        except Exception as e:
            logger.error(f"تعذر تسجيل عملية الأدمن: {e}")


if __name__ == "__main__":
    # جلب التوكن
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        logger.error("BOT_TOKEN غير موجود في متغيرات البيئة")
        exit(1)
    
    # تشغيل HTTP server بسيط على بورت Render (لكي يكتشف Render الخدمة)
    port = int(os.getenv('PORT', '10000'))
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(self.tr('a1058_البوت_يعمل', 'ar').encode('utf-8'))
        def log_message(self, format, *args):
            pass  # إسكات logs الـ HTTP
    
    http_server = HTTPServer(('0.0.0.0', port), HealthHandler)
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()
    logger.info(f"Health check server started on port {port}")
    
    # فحص وضع متعدد البوتات
    use_multi_bot = os.getenv('MULTI_BOT', 'no').lower() in ('yes', '1', 'true')
    
    if use_multi_bot:
        # وضع متعدد البوتات — تشغيل جميع البوتات النشطة
        try:
            from multi_bot import MultiBotManager
            manager = MultiBotManager()
            
            # إضافة البوت الرئيسي إن لم يكن موجوداً
            all_bots = manager.get_all_bots()
            if not all_bots:
                manager.add_bot(self.tr('a1059_البوت_الرئيسي', 'ar'), bot_token, os.getenv('ADMIN_USER_IDS', '7146701713'))
                manager.toggle_bot('BOT' + bot_token[-6:], activate=True)
            
            # تشغيل جميع البوتات النشطة
            started = manager.start_all_active()
            logger.info(f"Multi-bot mode: started {started} bots")
            
            # إبقاء العملية حية
            while True:
                time.sleep(60)
        except Exception as e:
            logger.error(f"خطأ في وضع متعدد البوتات: {e}")
            bot = ComprehensiveDUXBot(bot_token)
            bot.run()
    else:
        # وضع البوت الواحد (الافتراضي)
        bot = ComprehensiveDUXBot(bot_token)
        bot.run()