#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import csv
import urllib.request
import urllib.parse
import logging
import threading
import time
import zipfile
from datetime import datetime
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

class ComprehensiveDUXBot:
    def __init__(self, token):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self.user_states = {}
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
        
        # تهيئة البيانات المؤقتة للأدمن
        self.edit_company_data = {}
        self.temp_button_label_edit = {}
        
        # نظام الإحالات
        self.init_referral_files()
        # نظام التطبيقات
        self.init_app_links_file()
        
        # تنظيف المعاملات القديمة عند الإقلاع
        self.cleanup_old_transactions()
        
        # تنظيف أرصدة تعويض 100% المنتهية عند الإقلاع
        if self.svrp:
            self.svrp.expire_old_credits()
        
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


        # تخزين الأسباب المؤقتة لرفض المعاملات قبل التأكيد
        # المفتاح هو معرف الأدمن والقيمة عبارة عن قاموس يحتوي trans_id والسبب
        self.pending_reject_reasons = {}

        # نظام العملات: تعريف أسماء العملات ورموزها وأعلامها
        self.currencies = {
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
            'TRY': {'name': 'الليرة التركية', 'symbol': '₺', 'flag': '🇹🇷'}
        }

        # تسجيل عدد المدراء الدائمين
        logger.info(f"تم تحميل {len(self.admin_user_ids)} مدير دائم: {self.admin_user_ids}")

        # بدء نظام النسخ الاحتياطي التلقائي
        self.start_backup_scheduler()

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
                writer.writerow(['telegram_id', 'name', 'phone', 'customer_id', 'language', 'date', 'is_banned', 'ban_reason', 'currency'])
        
        # ملف المعاملات المتقدم
        if not os.path.exists('transactions.csv'):
            with open('transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'customer_id', 'telegram_id', 'name', 'type', 'company', 'wallet_number', 'amount', 'exchange_address', 'status', 'date', 'admin_note', 'processed_by'])
        
        # ملف الشركات
        if not os.path.exists('companies.csv'):
            with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'type', 'details', 'is_active', 'icon', 'address'])
                # شركات افتراضية
                companies = [
                    ['1', 'STC Pay', 'both', 'محفظة إلكترونية', 'active', '📡', ''],
                    ['2', 'البنك الأهلي', 'deposit', 'حساب بنكي رقم: 1234567890', 'active', '🏦', ''],
                    ['3', 'فودافون كاش', 'both', 'محفظة إلكترونية', 'active', '📱', ''],
                    ['4', 'بنك الراجحي', 'deposit', 'حساب بنكي رقم: 0987654321', 'active', '🏦', ''],
                    ['5', 'مدى البنك الأهلي', 'withdraw', 'رقم الحساب للسحب', 'active', '💳', '']
                ]
                for company in companies:
                    writer.writerow(company)
        
        # ترحيل ملف الشركات الموجود (إضافة أعمدة icon و address)
        self.migrate_companies_csv()
        
        # ملف وسائل الدفع
        if not os.path.exists('payment_methods.csv'):
            with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date', 'icon'])
                defaults = [
                    ['1', '1', 'حساب بنكي', 'حساب بنكي', '1234567890', 'البنك الأهلي', 'active', '2024-01-01', '🏦'],
                    ['2', '1', 'محفظة STC', 'محفظة إلكترونية', '0501234567', 'STC Pay', 'active', '2024-01-01', '📱'],
                    ['3', '3', 'فودافون كاش', 'محفظة إلكترونية', '01012345678', 'فودافون', 'active', '2024-01-01', '📱'],
                    ['4', '4', 'حساب جاري', 'حساب بنكي', '0987654321', 'بنك الراجحي', 'active', '2024-01-01', '🏦'],
                ]
                for m in defaults:
                    writer.writerow(m)
        self.migrate_payment_methods_csv()
        
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
        
        logger.info("تم إنشاء جميع ملفات النظام بنجاح")
        
    # خريطة الأيقونات: تحويل نص/إيموجي إلى أيقونة مناسبة
    ICON_MAP = {
        'bank': '🏦', 'banks': '🏦', 'بنك': '🏦', 'مصرف': '🏦', 'البنك': '🏦',
        'wallet': '👛', 'e-wallet': '👛', 'ewallet': '👛', 'محفظة': '👛', 'محفظه': '👛',
        'phone': '📱', 'mobile': '📱', 'هاتف': '📱', 'جوال': '📱',
        'cash': '💵', 'نقدي': '💵', 'كاش': '💵', 'نقد': '💵',
        'card': '💳', 'credit': '💳', 'debit': '💳', 'بطاقة': '💳', 'بطاقه': '💳', 'مدى': '💳',
        'crypto': '₿', 'bitcoin': '₿', 'بيتكوين': '₿',
        'paypal': '🅿️',
        'stc': '📡', 'stc pay': '📡', 'stcpay': '📡',
        'vodafone': '📱', 'فودافون': '📱',
        'company': '🏢', 'شركة': '🏢', 'business': '🏢',
        'exchange': '🔄', 'صرافة': '🔄', 'صرافه': '🔄',
        'money': '💰', 'مال': '💰', 'أموال': '💰',
        'transfer': '📤', 'تحويل': '📤',
        'store': '🏬', 'متجر': '🏬', 'shop': '🏬',
        'online': '🌐', 'أونلاين': '🌐',
        'gift': '🎁', 'هدية': '🎁',
        'gold': '🥇', 'ذهب': '🥇',
        'rocket': '🚀', 'صاروخ': '🚀',
        'star': '⭐', 'نجمة': '⭐',
        'check': '✅', 'صح': '✅',
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
        # إذا لم يوجد، استخدم النص كما هو مع إضافة 🏷️
        if len(icon_input) <= 20:
            return f"🏷️"
        return default

    def migrate_companies_csv(self):
        """ترحيل companies.csv لإضافة أعمدة icon و address"""
        try:
            with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
            # التحقق من وجود الأعمدة الجديدة
            need_migration = 'icon' not in fieldnames or 'address' not in fieldnames
            if not need_migration:
                return
            new_fieldnames = list(fieldnames)
            if 'icon' not in new_fieldnames:
                new_fieldnames.append('icon')
            if 'address' not in new_fieldnames:
                new_fieldnames.append('address')
            # إضافة القيم الافتراضية للصفوف الموجودة
            for row in rows:
                if 'icon' not in row or not row.get('icon'):
                    row['icon'] = '🏢'
                if 'address' not in row:
                    row['address'] = ''
            with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=new_fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in new_fieldnames})
            logger.info("تم ترحيل companies.csv لإضافة أعمدة icon و address")
        except Exception as e:
            logger.error(f"خطأ في ترحيل companies.csv: {e}")

    def migrate_payment_methods_csv(self):
        """ترحيل payment_methods.csv لإضافة عمود icon"""
        try:
            with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
            if 'icon' in fieldnames:
                return
            new_fieldnames = list(fieldnames) + ['icon']
            for row in rows:
                row['icon'] = self.normalize_icon(row.get('method_type', ''), default='💳')
            with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=new_fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in new_fieldnames})
            logger.info("تم ترحيل payment_methods.csv لإضافة عمود icon")
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
        """إرجاع النص المعدل للزر إن وجد، أو النص الأصلي"""
        try:
            mapping = getattr(self, 'button_labels', None) or {}
            return mapping.get(text, text)
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
        """تنظيف مدخلات المستخدم لمنع حقن CSV والهجمات الأخرى"""
        if not text:
            return text
        # Remove dangerous CSV characters
        dangerous_chars = ['=', '+', '-', '@', '\t', '\r', '\n']
        # If text starts with dangerous chars, prefix with space
        if text and text[0] in dangerous_chars:
            text = ' ' + text
        # Limit length to prevent overflow
        if len(text) > 500:
            text = text[:500]
        # Remove null bytes
        text = text.replace('\x00', '')
        return text.strip()

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
        """التحقق من صحة رقم الهاتف"""
        if not phone:
            return False
        # Remove spaces and dashes
        phone = phone.replace(' ', '').replace('-', '')
        # Must start with + and be 7-20 digits
        if phone.startswith('+'):
            digits = phone[1:]
        else:
            digits = phone
        return digits.isdigit() and 7 <= len(digits) <= 20

    def validate_amount(self, amount_str):
        """التحقق من صحة المبلغ المدخل"""
        try:
            amount = float(amount_str)
            if amount <= 0 or amount > 1000000:  # Max 1 million
                return None
            return amount
        except (ValueError, TypeError):
            return None

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
                        # أخطاء غير قابلة لإعادة المحاولة
                        if 'chat not found' in error_desc or 'blocked' in error_desc:
                            return result
                        last_error = f"API error: {error_desc}"
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
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
    
    def send_inline_message(self, chat_id, text, inline_buttons):
        """إرسال رسالة بأزرار Inline (داخل الدردشة)
        
        inline_buttons: قائمة صفوف، كل صف قائمة أزرار
        كل زر: {'text': 'نص الزر', 'callback_data': 'بيانات_الكالباك'}
        
        مثال:
        buttons = [
            [{'text': '✅ موافقة', 'callback_data': 'approve_DEP123'}, {'text': '❌ رفض', 'callback_data': 'reject_DEP123'}],
            [{'text': '🏠 القائمة', 'callback_data': 'main_menu'}]
        ]
        """
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
    
    def edit_message(self, chat_id, message_id, text=None, inline_buttons=None):
        """تعديل رسالة موجودة (لتحديث الأزرار بعد الضغط)"""
        data = {'chat_id': chat_id, 'message_id': message_id}
        if text:
            data['text'] = text
            data['parse_mode'] = 'HTML'
        if inline_buttons:
            data['reply_markup'] = json.dumps({'inline_keyboard': inline_buttons})
        return self.api_call('editMessageText', data)
    
    def make_inline_btn(self, text, callback_data):
        """إنشاء زر inline بسرعة"""
        return {'text': text, 'callback_data': callback_data}
    
    def make_inline_keyboard(self, rows):
        """إنشاء لوحة inline من قائمة صفوف
        كل صف: قائمة من (text, callback_data) tuples"""
        keyboard = []
        for row in rows:
            keyboard.append([self.make_inline_btn(t, c) for t, c in row])
        return keyboard
    
    def get_updates(self):
        """جلب التحديثات"""
        url = f"{self.api_url}/getUpdates?offset={self.offset + 1}&timeout=10"
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
        """كتابة آمنة في CSV مع قفل"""
        lock = self._get_csv_lock(filename)
        with lock:
            try:
                if mode == 'a':
                    with open(filename, 'a', newline='', encoding='utf-8-sig') as f:
                        if fieldnames:
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            for row in rows:
                                writer.writerow({k: row.get(k, '') for k in fieldnames})
                        else:
                            writer = csv.writer(f)
                            for row in rows:
                                writer.writerow(row)
                elif mode == 'w':
                    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                        if fieldnames:
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            writer.writeheader()
                            for row in rows:
                                writer.writerow({k: row.get(k, '') for k in fieldnames})
                        else:
                            writer = csv.writer(f)
                            for row in rows:
                                writer.writerow(row)
                return True
            except Exception as e:
                logger.error(f"خطأ في الكتابة الآمنة لـ {filename}: {e}")
                return False
    
    def safe_csv_read(self, filename):
        """قراءة آمنة من CSV مع قفل"""
        lock = self._get_csv_lock(filename)
        with lock:
            try:
                with open(filename, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    return list(reader)
            except Exception as e:
                logger.error(f"خطأ في القراءة الآمنة من {filename}: {e}")
                return []
    
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

    def init_app_links_file(self):
        """إنشاء ملف التطبيقات"""
        if not os.path.exists('app_links.csv'):
            with open('app_links.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'icon_url', 'download_url', 'description', 'is_active', 'created_at'])

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

    def add_app_link(self, name, icon_url, download_url, description=''):
        """إضافة تطبيق جديد"""
        app_id = f"APP{str(int(datetime.now().timestamp()))[-6:]}"
        try:
            with open('app_links.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([app_id, name, icon_url, download_url, description, 'yes', datetime.now().strftime('%Y-%m-%d %H:%M')])
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
    
    def cleanup_old_transactions(self):
        """تنظيف المعاملات المعلقة القديمة (أكثر من 72 ساعة)"""
        try:
            rows = self.safe_csv_read('transactions.csv')
            if not rows:
                return
            now = datetime.now()
            updated = False
            for row in rows:
                if row.get('status') in ('pending', 'pending_code_verification'):
                    try:
                        trans_date = datetime.strptime(row.get('date', ''), '%Y-%m-%d %H:%M')
                        if (now - trans_date).total_seconds() > 72 * 3600:  # 72 ساعة
                            row['status'] = 'expired'
                            row['admin_note'] = 'انتهت صلاحية الطلب تلقائياً (تجاوز 72 ساعة)'
                            updated = True
                            logger.info(f"Transaction expired: {row.get('id')}")
                    except:
                        pass
            if updated:
                self.safe_csv_write('transactions.csv', rows, 
                    fieldnames=['id','customer_id','telegram_id','name','type','company','wallet_number','amount','exchange_address','status','date','admin_note','processed_by','currency'], mode='w')
                self.notify_admins("⚠️ تم انتهاء صلاحية معاملات معلقة تلقائياً (تجاوزت 72 ساعة)", notification_type='general')
        except Exception as e:
            logger.error(f"خطأ في تنظيف المعاملات القديمة: {e}")

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
        """عرض لوحة الإحالات"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        lang = user.get('language', 'ar')
        ref_code = self.get_user_referral_code(user)
        ref_count = self.get_referral_count(message['from']['id'])

        ref_text = (
            f"{self.tr('referral_panel_title', lang)}\n\n"
            f"{self.tr('referral_your_code', lang)}\n"
            f"`{ref_code}`\n\n"
            f"{self.tr('referral_count', lang)}: {ref_count}\n\n"
            f"{self.tr('referral_hint', lang)}"
        )
        self.send_message(message['chat']['id'], ref_text, self.main_keyboard(lang, message['from']['id']))

    # ==================== 📱 التطبيقات — Panel Methods ====================

    def show_apps_panel(self, message):
        """عرض لوحة التطبيقات للمستخدم"""
        user = self.find_user(message['from']['id'])
        lang = user.get('language', 'ar') if user else 'ar'
        apps = self.get_app_links()

        if not apps:
            self.send_message(message['chat']['id'],
                self.tr('apps_empty', lang),
                self.main_keyboard(lang, message['from']['id']))
            return

        # رأس اللوحة
        text = (
            f"╔════════════════════╗\n"
            f"║  {self.tr('apps_title', lang)}  ║\n"
            f"╚════════════════════╝\n\n"
            f"📱 {self.tr('apps_count', lang)}: {len(apps)}\n\n"
        )

        # عرض كل تطبيق بشكل منسق
        for i, app in enumerate(apps, 1):
            name = app.get('name', '')
            icon_url = app.get('icon_url', '')
            download_url = app.get('download_url', '')
            desc = app.get('description', '')

            text += (
                f"┌─────────────────────┐\n"
                f"│  📱 <b>{name}</b>\n"
            )
            if desc:
                text += f"│  📝 {desc}\n"
            text += (
                f"│  🔗 <a href=\"{download_url}\">{self.tr('apps_download', lang)}</a>\n"
                f"└─────────────────────┘\n\n"
            )

        text += f"💡 {self.tr('apps_hint', lang)}"

        # إرسال الأيقونة الأولى كصورة إن وجدت
        first_icon = apps[0].get('icon_url', '') if apps else ''
        if first_icon and first_icon.startswith('http'):
            try:
                self.send_photo(message['chat']['id'], first_icon, text, self.main_keyboard(lang, message['from']['id']))
                return
            except:
                pass

        self.send_message(message['chat']['id'], text, self.main_keyboard(lang, message['from']['id']))

    def send_photo(self, chat_id, photo_url, caption='', keyboard=None):
        """إرسال صورة مع نص"""
        data = {
            'chat_id': chat_id,
            'photo': photo_url,
            'parse_mode': 'HTML'
        }
        if caption:
            data['caption'] = caption
        if keyboard:
            if isinstance(keyboard, dict):
                data['reply_markup'] = self.transform_keyboard(keyboard)
            else:
                data['reply_markup'] = keyboard
        return self.api_call('sendPhoto', data)

    # ==================== Admin: Apps Management ====================

    def show_apps_admin_panel(self, message):
        """لوحة إدارة التطبيقات — بأزرار inline أنيقة"""
        apps = self.get_all_app_links()

        text = (
            f"╔════════════════════╗\n"
            f"║  📱 إدارة التطبيقات  ║\n"
            f"╚════════════════════╝\n\n"
            f"📊 إجمالي التطبيقات: {len(apps)}\n"
        )

        inline_btns = []

        if apps:
            text += "\n📋 التطبيقات الحالية:\n\n"
            for app in apps:
                status_icon = '✅' if app.get('is_active') == 'yes' else '⏸️'
                text += (
                    f"{status_icon} <b>{app['name']}</b>\n"
                    f"  🆔 <code>{app['id']}</code>\n"
                )
                if app.get('description'):
                    text += f"  📝 {app['description']}\n"
                text += f"  🔗 <a href=\"{app.get('download_url', '')}\">رابط التحميل</a>\n"
                if app.get('icon_url'):
                    text += f"  🖼️ <a href=\"{app.get('icon_url', '')}\">الأيقونة</a>\n"
                text += f"  📅 {app.get('created_at', '')}\n\n"
                # زر حذف لكل تطبيق
                inline_btns.append([{
                    'text': f"🗑️ حذف: {app['name']}",
                    'callback_data': f"app_delete_{app['id']}"
                }])

        # أزرار الإجراءات
        inline_btns.append([{'text': '➕ إضافة تطبيق جديد', 'callback_data': 'app_add_new'}])
        if apps:
            inline_btns.append([{'text': '🔄 تحديث القائمة', 'callback_data': 'app_refresh'}])
        inline_btns.append([{'text': '🔙 العودة للوحة الأدمن', 'callback_data': 'app_back_admin'}])

        if not apps:
            text += "\n📭 لا توجد تطبيقات بعد.\n"

        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def start_app_wizard(self, message):
        """بدء معالج إضافة تطبيق — خطوة بخطوة"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']

        if not hasattr(self, 'temp_app_data'):
            self.temp_app_data = {}
        self.temp_app_data[user_id] = {'step': 'app_name'}

        text = (
            "╔════════════════════╗\n"
            "║  ➕ إضافة تطبيق  ║\n"
            "╚════════════════════╝\n\n"
            "📝 الخطوة 1 من 4\n\n"
            "✍️ اكتب اسم التطبيق:\n\n"
            "مثال: تطبيق المال"
        )
        kb = {
            'keyboard': [[{'text': '❌ إلغاء'}], [{'text': '🔙 لوحة الأدمن'}]],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        self.send_message(chat_id, text, kb)
        self.user_states[user_id] = 'app_wizard_name'

    def handle_app_wizard(self, message):
        """معالجة خطوات معالج إضافة تطبيق"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()

        # إلغاء
        if text in ['❌ إلغاء', '🔙 لوحة الأدمن', 'إلغاء', 'الغاء']:
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
                self.send_message(chat_id, "❌ الاسم قصير جداً. اكتب اسماً صحيحاً:")
                return
            data['name'] = text
            data['step'] = 'app_icon'
            self.temp_app_data[user_id] = data
            self.send_message(chat_id,
                "✅ تم حفظ الاسم!\n\n"
                "📝 الخطوة 2 من 4\n\n"
                "🖼️ اكتب رابط أيقونة التطبيق (صورة PNG/JPG):\n\n"
                "أو اكتب 'تخطي' لاستخدام أيقونة افتراضية 📱\n\n"
                "مثال: https://example.com/icon.png")

        elif step == 'app_icon':
            if text.lower() in ['تخطي', 'skip', 'بدون']:
                data['icon_url'] = ''
            else:
                data['icon_url'] = text
            data['step'] = 'app_url'
            self.temp_app_data[user_id] = data
            self.send_message(chat_id,
                "✅ تم حفظ الأيقونة!\n\n"
                "📝 الخطوة 3 من 4\n\n"
                "🔗 اكتب رابط تحميل التطبيق:\n\n"
                "مثال: https://play.google.com/store/apps/...")

        elif step == 'app_url':
            if len(text) < 5 or not text.startswith('http'):
                self.send_message(chat_id, "❌ رابط غير صحيح. يجب أن يبدأ بـ http:// أو https://\n\nاكتب الرابط مرة أخرى:")
                return
            data['download_url'] = text
            data['step'] = 'app_desc'
            self.temp_app_data[user_id] = data
            self.send_message(chat_id,
                "✅ تم حفظ رابط التحميل!\n\n"
                "📝 الخطوة 4 من 4 (الأخيرة)\n\n"
                "📝 اكتب وصفاً قصيراً للتطبيق:\n\n"
                "أو اكتب 'تخطي' لبدونه")

        elif step == 'app_desc':
            if text.lower() in ['تخطي', 'skip', 'بدون']:
                data['description'] = ''
            else:
                data['description'] = text

            # حفظ التطبيق
            app_id = self.add_app_link(data['name'], data.get('icon_url', ''), data['download_url'], data.get('description', ''))
            if app_id:
                # عرض ملخص + أزرار تأكيد
                summary = (
                    "╔════════════════════╗\n"
                    "║  ✅ تم الحفظ!  ║\n"
                    "╚════════════════════╝\n\n"
                    f"📱 الاسم: <b>{data['name']}</b>\n"
                    f"🆔 <code>{app_id}</code>\n"
                )
                if data.get('icon_url'):
                    summary += f"🖼️ أيقونة: ✅\n"
                if data.get('description'):
                    summary += f"📝 الوصف: {data['description']}\n"
                summary += f"🔗 التحميل: <a href=\"{data['download_url']}\">رابط</a>\n"

                inline_btns = [
                    [{'text': '📋 عرض كل التطبيقات', 'callback_data': 'app_refresh'}],
                    [{'text': '➕ إضافة تطبيق آخر', 'callback_data': 'app_add_new'}],
                    [{'text': '🔙 لوحة الأدمن', 'callback_data': 'app_back_admin'}]
                ]
                self.send_inline_message(chat_id, summary, inline_btns)
            else:
                self.send_message(chat_id, "❌ فشل في حفظ التطبيق", self.admin_keyboard())

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
            panel_text = (
                "💎 <b>تعويض 100%</b>\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"{intro_ar}\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"🧊 <b>الرصيد المجمد:</b> <code>{frozen:.2f}</code>\n"
                f"🟢 <b>الرصيد المتاح:</b> <code>{available:.2f}</code>\n"
                f"⏳ <b>بانتظار الأصدقاء:</b> <code>{pending:.2f}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📈 المكتسب: <b>{total_earned:.2f}</b> | 📉 المستخدم: <b>{total_used:.2f}</b>\n\n"
                f"👇 <b>اختر ما تريد:</b>"
            )
        else:
            panel_text = (
                "💎 <b>Compensation 100%</b>\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"{intro_en}\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"🧊 <b>Frozen:</b> <code>{frozen:.2f}</code>\n"
                f"🟢 <b>Available:</b> <code>{available:.2f}</code>\n"
                f"⏳ <b>Pending friends:</b> <code>{pending:.2f}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📈 Earned: <b>{total_earned:.2f}</b> | 📉 Used: <b>{total_used:.2f}</b>\n\n"
                f"👇 <b>Select an option:</b>"
            )

        # أزرار inline داخل الدردشة
        inline_btns = [
            [{'text': '💰 إيداع', 'callback_data': 'svrp_deposit'},
             {'text': '💸 سحب', 'callback_data': 'svrp_withdraw'}],
            [{'text': '🔄 استرداد', 'callback_data': 'svrp_recovery_request'},
             {'text': '📤 إرسال رصيد', 'callback_data': 'svrp_send_credits'}],
            [{'text': '💎 محفظتي', 'callback_data': 'svrp_wallet'},
             {'text': '👥 دعوة صديق', 'callback_data': 'svrp_invite'}],
            [{'text': '🏢 تسجيل حساب جديد', 'callback_data': 'svrp_companies'}],
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
            title = "💎 <b>محفظتي</b>"
            frozen_lbl = "🧊 مجمد" if is_frozen else "🟢 متاح"
            pending_lbl = "⏳ بانتظار الأصدقاء"
            earned_lbl = "📈 إجمالي المكتسب"
            used_lbl = "📉 إجمالي المستخدم"
            keep_lbl = "📥 أرصدة الاحتفاظ"
            shared_lbl = "📤 أرصدة المشاركة"
            active_lbl = "نشط"
            pending_status_lbl = "معلق"
            used_lbl2 = "مستخدم"
            expired_lbl = "منتهي"
            hint = "💡 يمكنك إنشاء كود ترويجي أو استرداد كود من صديق"
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
            title = "📋 <b>مهام اليوم</b>"
            reward_lbl = "مكافأة"
            claim_hint = "🎉 لديك مهام مكتملة!\nاكتب: <code>استلام [رقم_المهمة]</code>"
            pending_hint = "💡 أكمل معاملاتك لإنجاز المهام!"
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
            title = "🎟️ <b>أكوادي الترويجية</b>"
            balance_lbl = "رصيدك"
            empty = "📭 لا توجد أكواد بعد"
            create_hint = "➕ لإنشاء كود جديد:"
            create_cmd = "<code>انشاء_كود 100</code>"
            redeem_hint = "📥 لاسترداد كود:"
            redeem_cmd = "<code>استرداد_كود RCVABC123</code>"
            frozen_warn = "⚠️ رصيدك مجمد حتى تكمل 3 معاملات" if is_frozen else ""
        else:
            title = "🎟️ <b>My Promo Codes</b>"
            balance_lbl = "Your balance"
            empty = "📭 No codes yet"
            create_hint = "➕ To create a new code:"
            create_cmd = "<code>انشاء_كود 100</code>"
            redeem_hint = "📥 To redeem a code:"
            redeem_cmd = "<code>استرداد_كود RCVABC123</code>"
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
        group_ar = {'bronze': 'برونزي' if lang=='ar' else 'Bronze', 'silver': 'فضي' if lang=='ar' else 'Silver', 'gold': 'ذهبي' if lang=='ar' else 'Gold', 'platinum': 'بلاتيني' if lang=='ar' else 'Platinum'}.get(group_name, 'برونزي')
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
            ('🥉 ' + ('برونزي' if lang=='ar' else 'Bronze'), 'bronze', 0, '1.0x'),
            ('🥈 ' + ('فضي' if lang=='ar' else 'Silver'), 'silver', 500, '1.2x'),
            ('🥇 ' + ('ذهبي' if lang=='ar' else 'Gold'), 'gold', 2000, '1.5x'),
            ('💎 ' + ('بلاتيني' if lang=='ar' else 'Platinum'), 'platinum', 5000, '2.0x'),
        ]
        text += f"📋 {self.tr('svrp_tier_levels', lang)}:\n"
        for label, gname, min_score, mult in thresholds:
            marker = f" {self.tr('svrp_tier_here', lang)}" if group_name == gname else ''
            bar = '▰' * 5 if group_name == gname else '▱' * 5
            text += f"  {label} {bar} {min_score}+ {self.tr('svrp_tier_points', lang)} ({mult}){marker}\n"

        text += f"\n{self.tr('svrp_tier_hint', lang)}"
        self.send_message(message['chat']['id'], text, self.main_keyboard(lang, user_id))

    def handle_svrp_state(self, message, state):
        """معالجة حالات 💎 تعويض 100%"""
        user_id = message['from']['id']
        text = message.get('text', '').strip()
        chat_id = message['chat']['id']
        user = self.find_user(user_id)
        lang = user.get('language', 'ar') if user else 'ar'

        if text in ['🔙', '🏠 القائمة الرئيسية', '❌ إلغاء', 'الغاء', 'إلغاء']:
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
        """لوحة إدارة 💎 تعويض 100% — إدارة كاملة بأزرار inline"""
        admin_user = self.find_user(message['from']['id'])
        admin_lang = admin_user.get('language', 'ar') if admin_user else 'ar'

        if not self.svrp:
            self.send_message(message['chat']['id'], self.tr('svrp_not_available', admin_lang), self.admin_keyboard())
            return

        stats = self.svrp.get_svrp_stats()
        # قراءة الإعدادات عبر _get_config
        config = {}
        for key in ['recovery_multiplier', 'max_recovery_cap', 'credit_expiry_days',
                     'wagering_requirement', 'promo_code_max_uses',
                     'promo_code_expiry_days', 'max_recovery_per_month']:
            config[key] = self.svrp._get_config(key)

        text = (
            f"╔════════════════════╗\n"
            f"║  💎 إدارة تعويض 100%  ║\n"
            f"╚════════════════════╝\n\n"
            f"┌─── 📊 الإحصائيات ───┐\n"
            f"│  💰 أرصدة مصدرة: {stats['total_credits_issued']:.2f}\n"
            f"│  📉 أرصدة مستخدمة: {stats['total_credits_used']:.2f}\n"
            f"│  ✅ أرصدة نشطة: {stats['active_credits']}\n"
            f"│  ⏰ أرصدة منتهية: {stats['expired_credits']}\n"
            f"│  👥 المحافظ: {stats['total_wallets']}\n"
            f"│  💵 إجمالي الأرصدة: {stats['total_balance']:.2f}\n"
            f"│  ⏳ رصيد معلق: {stats['total_pending']:.2f}\n"
            f"│  📋 مهام نشطة: {stats['active_tasks']}\n"
            f"│  ✅ مهام مكتملة: {stats['completed_tasks']}\n"
            f"│  🎟️ أكواد نشطة: {stats['active_promos']}\n"
            f"└─────────────────────┘\n\n"
            f"┌─── ⚙️ الإعدادات الحالية ───┐\n"
            f"│  🔢 مضاعف الاسترداد: {config['recovery_multiplier']}x\n"
            f"│  💎 الحد الأقصى لكل حدث: {config['max_recovery_cap']}\n"
            f"│  📅 انتهاء الرصيد: {config['credit_expiry_days']} يوم\n"
            f"│  🎯 متطلبات الرهان: {config['wagering_requirement']} معاملة\n"
            f"│  🎟️ حد استخدام الكود: {config['promo_code_max_uses']}\n"
            f"│  📅 انتهاء الكود: {config['promo_code_expiry_days']} يوم\n"
            f"│  📈 الحد الشهري: {config['max_recovery_per_month']}\n"
            f"└─────────────────────┘\n"
        )

        if stats.get('top_referrers'):
            text += "\n🏆 أفضل المُحيلين:\n"
            for tid, count in stats['top_referrers']:
                text += f"  • <code>{tid}</code>: {count} إحالة\n"

        # أزرار inline للإدارة
        inline_btns = [
            [{'text': '⚙️ تعديل الإعدادات', 'callback_data': 'svrp_admin_settings'},
             {'text': '👥 عرض المحافظ', 'callback_data': 'svrp_admin_wallets'}],
            [{'text': '🎟️ الأكواد الترويجية', 'callback_data': 'svrp_admin_promos'},
             {'text': '📋 المهام', 'callback_data': 'svrp_admin_tasks'}],
            [{'text': '🧹 تنظيف الأرصدة المنتهية', 'callback_data': 'svrp_admin_cleanup'},
             {'text': '📊 إحصائيات تفصيلية', 'callback_data': 'svrp_admin_detailed'}],
            [{'text': '📝 تعديل النصوص', 'callback_data': 'svrp_edit_texts'}],
            [{'text': '🔙 العودة للوحة الأدمن', 'callback_data': 'svrp_admin_back'}]
        ]

        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def svrp_admin_view_wallets(self, chat_id):
        """عرض جميع محافظ تعويض 100%"""
        wallets = self.svrp._read_csv('svrp_wallets.csv')
        if not wallets:
            self.send_message(chat_id, "📭 لا توجد محافظ بعد.", self.admin_keyboard('ar'))
            return

        text = "╔════════════════════╗\n║  💎 المحافظ  ║\n╚════════════════════╝\n\n"
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
            self.send_inline_message(chat_id, "📭 لا توجد أكواد ترويجية.",
                [[{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]])
            return

        text = "╔════════════════════╗\n║  🎟️ الأكواد الترويجية  ║\n╚════════════════════╝\n\n"
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
            self.send_inline_message(chat_id, "📭 لا توجد مهام.",
                [[{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]])
            return

        text = "╔════════════════════╗\n║  📋 المهام  ║\n╚════════════════════╝\n\n"
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
            f"🧹 تم التنظيف!\n\n⏰ عدد الأرصدة المنتهية: {expired}",
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
        # المدراء الدائمين من متغيرات البيئة
        if str(telegram_id) in self.admin_ids:
            return True
        # المدراء الدائمين من الجلسة
        try:
            tid = int(telegram_id)
            if tid in self.admin_user_ids:
                return True
            # المدراء المؤقتين — فحص انتهاء الصلاحية
            if tid in self.temp_admin_user_ids:
                # فحص وقت الانتهاء
                if tid in self.temp_admin_expiry:
                    if self.temp_admin_expiry[tid] <= time.time():
                        # انتهت الصلاحية — إزالة تلقائية
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
                if inline_buttons:
                    self.send_inline_message(admin_id, message, inline_buttons)
                else:
                    self.send_message(admin_id, message, self.admin_keyboard())
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
    
    def find_user(self, telegram_id):
        """البحث عن مستخدم بـ telegram_id"""
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['telegram_id'] == str(telegram_id):
                        return row
        except:
            pass
        return None
    
    def find_user_by_phone(self, phone):
        """البحث عن مستخدم برقم الهاتف — للحفاظ على البيانات عند إعادة التسجيل"""
        if not phone:
            return None
        # تطبيع رقم الهاتف
        phone_normalized = phone.replace(' ', '').replace('-', '').replace('+', '')
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    stored_phone = row.get('phone', '').replace(' ', '').replace('-', '').replace('+', '')
                    if stored_phone and stored_phone == phone_normalized:
                        return row
        except:
            pass
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
        return COUNTRY_TO_CURRENCY.get(country_code, 'USD')
    
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
        return "العنوان غير متوفر حالياً"
    
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
        ref_btn = self.tr('referral_btn', lang) if self.tr('referral_btn', lang) != 'referral_btn' else f"{t.get('btn_referral', '🎁')} إحالة"
        help_btn = self.tr('help_btn_label', lang) if self.tr('help_btn_label', lang) != 'help_btn_label' else f"{t.get('btn_help', '❓')} مساعدة"
        svrp_btn = self.tr('svrp_title', lang)
        apps_btn = self.tr('apps_btn', lang) if self.tr('apps_btn', lang) != 'apps_btn' else '📱 تطبيقات'

        lang_names = self.get_language_names()
        lang_btn_text = f"{t.get('btn_language', '🌐')} {lang_names.get(lang, {}).get('native', 'Language')}"

        # تصميم احترافي: الأزرار بدون بادئات إضافية — الإيموجي موجود في الترجمات
        keyboard = [
            [{'text': deposit_btn}, {'text': withdraw_btn}],
            [{'text': requests_btn}, {'text': profile_btn}],
            [{'text': match_btn}, {'text': svrp_btn}],
            [{'text': ref_btn}, {'text': apps_btn}],
            [{'text': notif_btn}, {'text': complaint_btn}],
            [{'text': support_btn}, {'text': help_btn}],
            [{'text': currency_btn}, {'text': lang_btn_text}],
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
            # المجموعة 7b: التطبيقات والاسترداد
            [{'text': self.tr('admin_apps', lang)}, {'text': self.tr('admin_recovery', lang)}, {'text': self.tr('admin_quick_commands', lang)}],
            # المجموعة 8: الأدمن والأدوار
            [{'text': self.tr('admin_managers', lang)}, {'text': self.tr('admin_buttons', lang)}],
            # المجموعة 9: الحماية والنسخ
            [{'text': self.tr('admin_notifications', lang)}, {'text': self.tr('admin_backup', lang)}],
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
        """لوحة اختيار الشركات مع أيقونات مخصصة"""
        companies = self.get_companies(service_type)
        keyboard = []
        
        # أزرار الشركات بأيقوناتها — كل شركة في صف منفصل لوضوح أكبر
        for company in companies:
            icon = company.get('icon', '🏢') or '🏢'
            keyboard.append([{'text': f"{icon} {company['name']}"}])
        
        # زر العودة فقط (نظيف وبسيط)
        keyboard.append([{'text': '🔙'}])
        
        return {'keyboard': keyboard, 'resize_keyboard': True, 'one_time_keyboard': True}
    
    def handle_start(self, message, ref_code=None):
        """معالج بداية المحادثة — اختيار اللغة أولاً ثم رقم الهاتف"""
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        
        # فحص إذا كان المستخدم موجود بـ telegram_id
        user = self.find_user(user_id)
        
        if user:
            if user.get('is_banned') == 'yes':
                ban_reason = user.get('ban_reason', 'غير محدد')
                self.send_message(chat_id, f"❌ تم حظر حسابك\nالسبب: {ban_reason}\n\nللاستفسار تواصل مع الإدارة")
                return
            
            lang = user.get('language', 'ar')
            name = user.get('name', '')
            customer_id = user.get('customer_id', '')
            if lang == 'ar':
                welcome_text = (
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👋 <b>أهلاً وسهلاً، {name}!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🆔 رقم العميل: <b><code>{customer_id}</code></b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🟢 <b>إيداع</b> — أودع أموالك بسهولة\n"
                    f"🔴 <b>سحب</b> — اسحب أموالك بسرعة\n"
                    f"📋 <b>طلباتي</b> — تابع حالة معاملاتك\n"
                    f"🔄 <b>مطابقة</b> — طابق مع عميل آخر\n"
                    f"💎 <b>تعويض 100%</b> — رصيد تعويضي\n"
                    f"🎁 <b>إحالة</b> — ادعُ أصدقاءك\n"
                    f"📱 <b>تطبيقات</b> — تحميل التطبيقات\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"👇 <b>اختر ما تريد من الأزرار بالأسفل</b>"
                )
            else:
                welcome_text = self.tr('welcome_back', lang, name=name, customer_id=customer_id)
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
                
                skip_text = """✅ تم تخطي التسجيل!

يمكنك استخدام النظام كزائر. لاحقاً يمكنك التسجيل لحفظ بياناتك.

⚠️ ملاحظة: بدون تسجيل، لن تتمكن من:
• حفظ طلباتك
• تتبع حالة المعاملات
• الوصول للدعم الفني المخصص"""

                self.send_message(message['chat']['id'], skip_text, self.main_keyboard('ar', user_id))
                return
            elif name in {self.tr('cancel_registration', l) for l in self.get_supported_languages()}:
                # إلغاء التسجيل والعودة للقائمة الرئيسية
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                cancel_text = """❌ تم إلغاء التسجيل

يمكنك إعادة المحاولة في أي وقت باستخدام زر "📝 تسجيل حساب" """

                self.send_message(message['chat']['id'], cancel_text, self.main_keyboard('ar', user_id))
                return
            
            if len(name) < 2:
                self.send_message(message['chat']['id'], "❌ اسم قصير جداً. يرجى إدخال اسم صحيح:")
                return
            
            # منع استخدام نصوص الأزرار كأسماء
            button_prefixes = ['📝', '🔐', '⏭️', '❌', '✅', '🔄', '🏠', '💰', '💸', '📋', '👤', '📨', '🆘', '💱', '🌐', '🎁', '❓', '🔔']
            if any(name.startswith(p) for p in button_prefixes):
                self.send_message(message['chat']['id'], 
                    "❌ هذا نص زر وليس اسماً.\nاكتب اسمك الحقيقي:")
                return
            
            # منع الأسماء التي تحتوي على رموز فقط
            import re
            if not re.search(r'[\u0600-\u06FFa-zA-Z]', name):
                self.send_message(message['chat']['id'], 
                    "❌ الاسم يجب أن يحتوي على حروف.\nاكتب اسمك الحقيقي:")
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
                admin_msg = f"🆕 عضو جديد: {name} | {pre_phone} | {customer_id} | {final_lang} | {detected_country}"
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
            
            # التحقق من نوع الرسالة
            if 'contact' in message:
                # مشاركة جهة الاتصال
                phone = message['contact']['phone_number']
                if not phone.startswith('+'):
                    phone = '+' + phone
            elif 'text' in message:
                text = message['text'].strip()
                
                if text in {self.tr('enter_phone_manual', l) for l in self.get_supported_languages()}:
                    manual_text = """✍️ اكتب رقم هاتفك مع رمز البلد:

مثال: +966501234567
مثال: +201234567890"""
                    self.send_message(message['chat']['id'], manual_text)
                    return
                
                phone = text
                # منع استخدام نصوص الأزرار كأرقام هاتف
                if not self.validate_phone_number(phone):
                    self.send_message(message['chat']['id'], 
                        "❌ رقم هاتف غير صحيح.\nيجب أن يحتوي على أرقام فقط مع رمز البلد.\nمثال: +966501234567")
                    return
            else:
                self.send_message(message['chat']['id'], "❌ يرجى مشاركة جهة الاتصال أو كتابة الرقم:")
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
                               datetime.now().strftime('%Y-%m-%d'), 'no', '', detected_currency])
            
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
                            self.send_message(message['chat']['id'],
                                f"🎁 تم ربطك بكود الإحالة!\nمُحيلك: {ref_code}\nأكمل إيداعك لتفعيل الأرصدة المشتركة.")
                    except Exception as e:
                        logger.error(f"خطأ في معالجة كود الإحالة: {e}")

            # إشعار الأدمن بعضو جديد
            admin_msg = f"""🆕 عضو جديد انضم للنظام

👤 الاسم: {name}
📱 الهاتف: {phone}
🆔 رقم العميل: {customer_id}
🌐 اللغة: {detected_lang}
🌍 الدولة: {detected_country}
💱 العملة: {detected_currency}
📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
            self.notify_admins(admin_msg, notification_type='new_user')
    
    def create_deposit_request(self, message):
        """إنشاء طلب إيداع — شركات كأزرار inline"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        
        lang = user.get('language', 'ar')
        deposit_companies = self.get_companies('deposit')
        if not deposit_companies:
            self.send_message(message['chat']['id'], self.tr('no_companies', lang), self.main_keyboard(lang, message['from']['id']))
            return

        if lang == 'ar':
            title = "💰 <b>طلب إيداع</b>\n\nاختر الشركة:"
        else:
            title = "💰 <b>Deposit Request</b>\n\nSelect company:"

        inline_btns = []
        for company in deposit_companies:
            icon = company.get('icon', '🏢') or '🏢'
            btn_text = f"{icon} {company['name']}"
            if company.get('details'):
                btn_text += f" — {company['details'][:30]}"
            inline_btns.append([{'text': btn_text, 'callback_data': f'dep_company_{company["id"]}'}])

        inline_btns.append([{'text': self.tr('main_menu', lang), 'callback_data': 'dep_cancel'}])
        self.send_inline_message(message['chat']['id'], title, inline_btns)
    
    def create_withdrawal_request(self, message):
        """إنشاء طلب سحب — شركات كأزرار inline"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        
        lang = user.get('language', 'ar')
        withdraw_companies = self.get_companies('withdraw')
        if not withdraw_companies:
            self.send_message(message['chat']['id'], self.tr('no_companies', lang), self.main_keyboard(lang, message['from']['id']))
            return

        if lang == 'ar':
            title = "💸 <b>طلب سحب</b>\n\nاختر الشركة:"
        else:
            title = "💸 <b>Withdrawal Request</b>\n\nSelect company:"

        inline_btns = []
        for company in withdraw_companies:
            icon = company.get('icon', '🏢') or '🏢'
            btn_text = f"{icon} {company['name']}"
            if company.get('details'):
                btn_text += f" — {company['details'][:30]}"
            inline_btns.append([{'text': btn_text, 'callback_data': f'wd_company_{company["id"]}'}])

        inline_btns.append([{'text': self.tr('main_menu', lang), 'callback_data': 'wd_cancel'}])
        self.send_inline_message(message['chat']['id'], title, inline_btns)
    
    def process_deposit_flow(self, message):
        """معالجة تدفق الإيداع الكامل"""
        user_id = message['from']['id']
        state = self.user_states.get(user_id, '')
        text = message.get('text', '')

        # فحص أزرار الإلغاء والعودة أولاً — قبل أي معالجة للبيانات
        all_langs = self.get_supported_languages()
        cancel_texts = {self.tr('cancel_btn', l) for l in all_langs} | {self.tr('cancel_registration', l) for l in all_langs} | {'❌ إلغاء', '❌ Cancel', 'الغاء', 'إلغاء'}
        main_menu_texts = {self.tr('main_menu', l) for l in all_langs} | {self.tr('main_menu_btn', l) for l in all_langs} | {'🏠 القائمة الرئيسية', '🏠 الرئيسية', '🏠 Main Menu'}
        back_texts = {self.tr('back_btn', l) for l in all_langs} | {self.tr('back_to_main', l) for l in all_langs} | {'🔙', '🔙 العودة', '🔙 Back'}

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
                    method_name_display = f"\n💳 الوسيلة: {name} ({mtype})"

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
            confirmation = self.tr(
                'deposit_success',
                lang,
                trans_id=trans_id,
                name=user['name'],
                customer_id=user['customer_id'],
                company_name=f"{company_icon} {company_name}",
                wallet_number=wallet_number,
                amount=self.fmt_deposit_amount(amount, user_currency) + method_name_display,
                date=datetime.now().strftime('%Y-%m-%d %H:%M')
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
                        f"🆔 {trans_id}\n"
                        f"👤 {user['name']} ({user['customer_id']})\n"
                        f"🏢 {company_name}\n"
                        f"💳 {wallet_number}\n"
                        f"💰 {self.format_amount_with_currency(amount, user_currency)}{method_name_display}\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                        f"✅ {trans_id}  |  ❌ {trans_id}"
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
        cancel_texts = {self.tr('cancel_btn', l) for l in all_langs} | {self.tr('cancel_registration', l) for l in all_langs} | {'❌ إلغاء', '❌ Cancel', 'الغاء', 'إلغاء'}
        main_menu_texts = {self.tr('main_menu', l) for l in all_langs} | {self.tr('main_menu_btn', l) for l in all_langs} | {'🏠 القائمة الرئيسية', '🏠 الرئيسية', '🏠 Main Menu'}
        back_texts = {self.tr('back_btn', l) for l in all_langs} | {self.tr('back_to_main', l) for l in all_langs} | {'🔙', '🔙 العودة', '🔙 Back'}

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
            
        elif isinstance(state, str) and state.startswith('withdraw_all_data_'):
            # السحب: العميل يرسل كل البيانات في رسالة واحدة
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text_msg = message.get('text', '').strip()

            if text_msg in ['❌ إلغاء', 'إلغاء', 'الغاء', '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                self.handle_start(message)
                return

            lines = [l.strip() for l in text_msg.split('\n') if l.strip()]
            if len(lines) < 4:
                self.send_message(chat_id,
                    "❌ يجب إرسال 4 أسطر:\n\n"
                    "1️⃣ رقم المحفظة للاستلام\n"
                    "2️⃣ معرف حسابك\n"
                    "3️⃣ كود السحب\n"
                    "4️⃣ المبلغ\n\n"
                    "💡 مثال:\n<code>0501234567\nID-789\nABC123\n500</code>")
                return

            wallet_number = lines[0]
            account_id = lines[1]
            confirmation_code = lines[2]
            amount_str = lines[3]

            try:
                amount = float(amount_str)
                if amount <= 0:
                    self.send_message(chat_id, "❌ المبلغ يجب أن يكون أكبر من صفر")
                    return
            except ValueError:
                self.send_message(chat_id, "❌ المبلغ غير صحيح. السطر الرابع يجب أن يكون رقماً")
                return

            if len(wallet_number) < 5:
                self.send_message(chat_id, "❌ رقم المحفظة قصير جداً (السطر الأول)")
                return
            if len(account_id) < 2:
                self.send_message(chat_id, "❌ معرف الحساب قصير جداً (السطر الثاني)")
                return
            if len(confirmation_code) < 3:
                self.send_message(chat_id, "❌ كود السحب قصير جداً (السطر الثالث)")
                return

            # استخراج بيانات الشركة من الحالة
            parts = state.replace('withdraw_all_data_', '').split('_', 1)
            if len(parts) != 2:
                self.send_message(chat_id, "❌ خطأ في البيانات")
                if user_id in self.user_states: del self.user_states[user_id]
                return
            company_id = parts[0]
            company_name = parts[1]

            user = self.find_user(user_id)
            if not user:
                self.send_message(chat_id, "❌ يجب التسجيل أولاً")
                return

            user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
            trans_id = f"WTH{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # حفظ المعاملة
            with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    trans_id, user['customer_id'], user['telegram_id'], user['name'],
                    'withdraw', company_name, wallet_number, amount,
                    account_id, 'pending_code_verification',
                    datetime.now().strftime('%Y-%m-%d %H:%M'),
                    confirmation_code, '', user_currency
                ])

            # رسالة تأكيد للعميل
            lang = user.get('language', 'ar')
            self.send_message(chat_id,
                f"✅ <b>تم تقديم طلب السحب!</b>\n\n"
                f"🆔 <code>{trans_id}</code>\n"
                f"🏢 الشركة: <b>{company_name}</b>\n"
                f"💳 المحفظة: <code>{wallet_number}</code>\n"
                f"🆔 معرف الحساب: <code>{account_id}</code>\n"
                f"🔑 الكود: <code>{confirmation_code}</code>\n"
                f"💰 المبلغ: <b>{amount}</b> {user_currency}\n\n"
                f"⏳ {self.tr('code_pending_verification', lang)}",
                self.main_keyboard(lang, user_id))

            # إشعار الأدمن
            for admin_id in self.admin_ids:
                try:
                    admin_msg = (
                        f"💸 <b>طلب سحب جديد</b>\n\n"
                        f"🆔 <code>{trans_id}</code>\n"
                        f"👤 {user.get('name', '')} ({user.get('customer_id', '')})\n"
                        f"🏢 {company_name}\n"
                        f"💳 المحفظة: <code>{wallet_number}</code>\n"
                        f"🆔 معرف الحساب: <code>{account_id}</code>\n"
                        f"💰 المبلغ: {amount} {user_currency}\n"
                        f"🔑 الكود: <code>{confirmation_code}</code>\n"
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
                    name=user.get('name', 'غير محدد') if user else 'غير محدد',
                    customer_id=user.get('customer_id', 'غير محدد') if user else 'غير محدد'
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
        """عرض ملف المستخدم"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        
        lang = user.get('language', 'ar')
        lang_names = self.get_language_names()
        lang_display = lang_names.get(lang, {}).get('native', lang)
        
        profile_text = f"👤 {user['customer_id']}\n\n"
        profile_text += f"📛 {user['name']}\n"
        profile_text += f"📱 {user['phone']}\n"
        profile_text += f"📅 {user['date']}\n"
        profile_text += f"🌐 {lang_display}\n"
        profile_text += f"💱 {user.get('currency', 'SAR')}\n"
        profile_text += f"{'🚫' if user.get('is_banned') == 'yes' else '✅'}"
        
        if user.get('is_banned') == 'yes' and user.get('ban_reason'):
            profile_text += f"\n📝 {user['ban_reason']}"
        
        self.send_message(message['chat']['id'], profile_text, self.main_keyboard(lang))
    

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
    
    def process_message(self, message):
        """معالج الرسائل الرئيسي"""
        if 'text' not in message and 'contact' not in message and 'photo' not in message:
            return

        text = message.get('text', '')
        # تطبيع نص الأزرار المعدلة إلى النص الأصلي حتى يستمر النظام في العمل كما هو
        text = self.normalize_button_text(text)
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        
        # معالجة جميع الحالات أولاً (قبل الـ rate limiter)
        # لأن المستخدم في حالة نشطة يجب ألا يُحظر
        current_state = self.user_states.get(user_id, '')
        if current_state == 'phone_login_waiting':
            self.handle_phone_login(message)
            return
        if current_state == 'choosing_start_language':
            self.handle_start_language_choice(message)
            return
        if current_state == 'start_phone_input':
            self.handle_start_phone(message)
            return
        if isinstance(current_state, str) and current_state.startswith('registering_phone_'):
            self.handle_registration(message)
            return
        if isinstance(current_state, str) and current_state.startswith('registering'):
            self.handle_registration(message)
            return
        if isinstance(current_state, str) and current_state.startswith('svrp_'):
            self.handle_svrp_state(message, current_state)
            return
        if isinstance(current_state, str) and current_state.startswith('app_wizard'):
            self.handle_app_wizard(message)
            return
        if isinstance(current_state, str) and current_state.startswith('mbot_wizard'):
            self.mbot_handle_wizard(message)
            return
        if current_state == 'svrp_waiting_screenshot':
            # استقبال لقطة الشاشة للاسترداد
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            user = self.find_user(user_id)

            if 'photo' not in message:
                self.send_message(chat_id, "❌ يرجى إرسال صورة (لقطة شاشة). أعد المحاولة:")
                return

            # الحصول على أكبر حجم صورة
            photo = message['photo'][-1]
            photo_file_id = photo['file_id']

            if not user:
                self.send_message(chat_id, "❌ يجب التسجيل أولاً")
                if user_id in self.user_states: del self.user_states[user_id]
                return

            # إنشاء طلب استرداد
            req_id = self.svrp.create_recovery_request(
                user_id, user.get('customer_id', ''), photo_file_id
            )

            # إشعار المستخدم
            self.send_message(chat_id,
                f"✅ <b>تم إرسال طلب الاسترداد</b>\n\n"
                f"🆔 <code>{req_id}</code>\n"
                f"⏳ بانتظار مراجعة الإدارة",
                self.main_keyboard(user.get('language', 'ar'), user_id))

            # إرسال الصورة للأدمن + أزرار موافقة/رفض
            for admin_id in self.admin_ids:
                try:
                    admin_msg = (
                        f"🔄 <b>طلب استرداد جديد</b>\n\n"
                        f"🆔 <code>{req_id}</code>\n"
                        f"👤 العميل: <code>{user.get('customer_id', '')}</code>\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                        f"📸 لقطة الشاشة:"
                    )
                    inline_btns = [
                        [{'text': '✅ موافقة', 'callback_data': f'svrp_recovery_approve_{req_id}'},
                         {'text': '❌ رفض', 'callback_data': f'svrp_recovery_reject_{req_id}'}]
                    ]
                    # إرسال الصورة + الأزرار
                    self.api_call('sendPhoto', {
                        'chat_id': admin_id,
                        'photo': photo_file_id,
                        'caption': admin_msg,
                        'parse_mode': 'HTML',
                        'reply_markup': json.dumps({'inline_keyboard': [
                            [{'text': '✅ موافقة', 'callback_data': f'svrp_recovery_approve_{req_id}'},
                             {'text': '❌ رفض', 'callback_data': f'svrp_recovery_reject_{req_id}'}]
                        ]})
                    })
                except Exception as e:
                    logger.error(f"خطأ في إشعار الأدمن بطلب الاسترداد: {e}")

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        if isinstance(current_state, str) and current_state.startswith('svrp_recovery_amount_'):
            # الأدمن يكتب مبلغ الاسترداد بعد الموافقة
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            req_id = current_state.replace('svrp_recovery_amount_', '')
            text = message.get('text', '').strip()

            try:
                amount = float(text)
                if amount <= 0:
                    self.send_message(chat_id, "❌ المبلغ يجب أن يكون أكبر من صفر")
                    return
            except ValueError:
                self.send_message(chat_id, "❌ اكتب مبلغاً رقمياً صحيحاً:")
                return

            success, msg = self.svrp.approve_recovery_request(req_id, user_id, amount)
            icon = "✅" if success else "❌"
            self.send_message(chat_id, f"{icon} {msg}", self.admin_keyboard())

            # إشعار المستخدم
            req = self.svrp.get_recovery_request(req_id)
            if req and success:
                self.notify_user(int(req['user_id']),
                    f"✅ <b>تمت الموافقة على استردادك!</b>\n\n"
                    f"💎 الرصيد المضاف: <code>{amount:.2f}</code>\n"
                    f"🧊 حالة الرصيد: <b>مجمد</b>\n\n"
                    f"💡 أرسل رصيداً لأصدقائك لفك التجميد",
                    'recovery_approved')

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        if isinstance(current_state, str) and current_state.startswith('svrp_enter_account_'):
            # إدخال رقم حساب في شركة استرداد
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text = message.get('text', '').strip()

            if text in ['إلغاء', 'الغاء', '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_svrp_panel(fake_msg)
                return

            parts = current_state.replace('svrp_enter_account_', '').split('_', 1)
            if len(parts) != 2:
                return
            company_id = parts[0]
            company_name = parts[1]

            if len(text) < 3:
                self.send_message(chat_id, "❌ رقم الحساب قصير جداً. اكتب رقم حسابك:")
                return

            success, msg = self.svrp.add_user_company_account(user_id, company_id, company_name, text)
            if success:
                self.send_message(chat_id,
                    f"✅ {msg}\n\n"
                    f"🏆 يمكنك الآن طلب المكافأة من الأدمن.\n"
                    f"اضغط الزر بالأسفل:")
                inline_btns = [
                    [{'text': '🏆 طلب مكافأة', 'callback_data': f'svrp_bonus_{company_id}_{company_name}'}],
                    [{'text': '🔙 رجوع', 'callback_data': 'svrp_companies'}]
                ]
                self.send_inline_message(chat_id, "طلب المكافأة:", inline_btns)
            else:
                self.send_message(chat_id, f"❌ {msg}")

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        if isinstance(current_state, str) and current_state.startswith('svrp_bonus_amount_'):
            # الأدمن يكتب مبلغ المكافأة
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            req_id = current_state.replace('svrp_bonus_amount_', '')
            text = message.get('text', '').strip()

            try:
                amount = float(text)
                if amount <= 0:
                    self.send_message(chat_id, "❌ المبلغ يجب أن يكون أكبر من صفر")
                    return
            except ValueError:
                self.send_message(chat_id, "❌ اكتب مبلغاً رقمياً:")
                return

            success, msg = self.svrp.approve_bonus_request(req_id, amount, user_id)
            icon = "✅" if success else "❌"
            self.send_message(chat_id, f"{icon} {msg}", self.admin_keyboard())

            # إشعار المستخدم
            if success:
                rows = self.svrp._read_csv('bonus_requests.csv')
                for r in rows:
                    if r['id'] == req_id:
                        self.notify_user(int(r['user_id']),
                            f"🏆 <b>تمت الموافقة على مكافأتك!</b>\n\n"
                            f"💰 تم إضافة <b>{amount:.2f}</b> لرصيدك المجمد 🧊\n\n"
                            f"💡 أرسل رصيداً لأصدقائك لفك التجميد")
                        break

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        if isinstance(current_state, str) and current_state.startswith('svrp_dep_balance_'):
            # إيداع من الرصيد المتاح
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text = message.get('text', '').strip()

            if text in ['إلغاء', 'الغاء', '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_svrp_panel(fake_msg)
                return

            parts = current_state.replace('svrp_dep_balance_', '').split('_', 1)
            if len(parts) != 2:
                return
            company_id = parts[0]
            company_name = parts[1]

            try:
                amount = float(text)
                if amount <= 0:
                    self.send_message(chat_id, "❌ المبلغ يجب أن يكون أكبر من صفر")
                    return
            except ValueError:
                self.send_message(chat_id, "❌ اكتب مبلغاً رقمياً صحيحاً")
                return

            # الحصول على رقم حساب المستخدم في الشركة
            account = self.svrp.get_user_company_account(user_id, company_id)
            if not account:
                self.send_message(chat_id, "❌ لا يوجد حساب مسجل في هذه الشركة")
                if user_id in self.user_states: del self.user_states[user_id]
                return

            # تنفيذ الإيداع من المتاح
            success, msg = self.svrp.deposit_from_balance(user_id, company_id, company_name, amount)
            if success:
                user = self.find_user(user_id)
                user_currency = user.get('currency', 'SAR') if user else 'SAR'

                self.send_message(chat_id,
                    f"✅ <b>تم طلب الإيداع!</b>\n\n"
                    f"🆔 <code>{msg}</code>\n"
                    f"🏢 الشركة: {company_name}\n"
                    f"📋 رقم حسابك: <code>{account.get('account_number', '')}</code>\n"
                    f"💰 المبلغ: <b>{amount:.2f}</b> {user_currency}\n\n"
                    f"⏳ سيتم مراجعة طلبك من الإدارة")

                # إشعار الأدمن
                for admin_id in self.admin_ids:
                    try:
                        admin_msg = (
                            f"💰 <b>طلب إيداع من رصيد متاح</b>\n\n"
                            f"🆔 <code>{msg}</code>\n"
                            f"👤 العميل: {user.get('name', '')} ({user.get('customer_id', '')})\n"
                            f"🏢 الشركة: {company_name}\n"
                            f"📋 رقم الحساب: <code>{account.get('account_number', '')}</code>\n"
                            f"💰 المبلغ: <b>{amount:.2f}</b> {user_currency}\n\n"
                        )
                        inline_btns = [
                            [{'text': '✅ تأكيد', 'callback_data': f'svrp_dep_approve_{msg}'},
                             {'text': '❌ رفض', 'callback_data': f'svrp_dep_reject_{msg}'}]
                        ]
                        self.send_inline_message(admin_id, admin_msg, inline_btns)
                    except Exception as e:
                        logger.error(f"خطأ في إشعار الأدمن بالإيداع: {e}")
            else:
                self.send_message(chat_id, f"❌ {msg}")

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        if isinstance(current_state, str) and current_state.startswith('setting_input_'):
            # تعديل إعداد النظام
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text = message.get('text', '').strip()

            if text in ['إلغاء', 'الغاء', 'cancel', '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_system_settings(fake_msg)
                return

            key = current_state.replace('setting_input_', '')
            self.save_setting(key, text)

            self.send_message(chat_id,
                f"✅ <b>تم تحديث الإعداد!</b>\n\n"
                f"📋 {key}: <code>{text}</code>",
                self.admin_keyboard())

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        # معالجة إضافة وسيلة دفع جديدة (pm_add_wizard_)
        if isinstance(current_state, str) and current_state.startswith('pm_add_wizard_'):
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text_msg = message.get('text', '').strip()

            if text_msg in ['إلغاء', 'الغاء', 'cancel', '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_payment_methods_management(fake_msg)
                return

            parts = current_state.replace('pm_add_wizard_', '').split('_', 1)
            if len(parts) != 2:
                return
            company_id = parts[0]
            company_name = parts[1]

            lines = [l.strip() for l in text_msg.split('\n') if l.strip()]
            if len(lines) < 5:
                self.send_message(chat_id,
                    "❌ يجب إرسال 5 أسطر:\n\n"
                    "1️⃣ اسم الوسيلة\n"
                    "2️⃣ النوع\n"
                    "3️⃣ رقم الحساب\n"
                    "4️⃣ معلومات إضافية (أو 'بدون')\n"
                    "5️⃣ الأيقونة (أو 'بدون')")
                return

            method_name = lines[0]
            method_type = lines[1]
            account_data = lines[2]
            additional_info = lines[3] if lines[3].lower() not in ['بدون', 'skip', ''] else ''
            icon = lines[4] if lines[4].lower() not in ['بدون', 'skip', ''] else '💳'

            self.add_payment_method(company_id, method_name, method_type, account_data, additional_info, icon)
            self.send_message(chat_id,
                f"✅ <b>تم إضافة وسيلة الدفع!</b>\n\n"
                f"💳 {method_name}\n"
                f"🏢 {company_name}\n"
                f"🔢 <code>{account_data}</code>",
                self.admin_keyboard())

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        # معالجة تعديل اسم وسيلة دفع (pm_input_name_)
        if isinstance(current_state, str) and current_state.startswith('pm_input_name_'):
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            method_id = current_state.replace('pm_input_name_', '')
            text_msg = message.get('text', '').strip()

            if text_msg in ['إلغاء', 'الغاء', 'cancel', '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                return

            if len(text_msg) < 2:
                self.send_message(chat_id, "❌ الاسم قصير جداً")
                return

            self.update_payment_method_field(method_id, 'method_name', text_msg)
            if user_id in self.user_states: del self.user_states[user_id]
            # العودة لتفاصيل الوسيلة المحدّثة بدلاً من لوحة الأدمن
            self.send_message(chat_id, f"✅ تم تحديث الاسم إلى: <b>{text_msg}</b>")
            fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
            # إعادة عرض تفاصيل الوسيلة
            method = self.get_payment_method_by_id(method_id)
            if method:
                company = self.get_company_by_id(method.get('company_id', ''))
                company_name = company['name'] if company else 'غير محدد'
                status = method.get('status', 'active')
                status_icon = '✅' if status == 'active' else '⏸️'
                icon = method.get('icon', '💳') or '💳'
                detail_text = (
                    f"💳 <b>{method['method_name']}</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🏢 الشركة: {company_name}\n"
                    f"📋 النوع: {method.get('method_type', '')}\n"
                    f"🔢 رقم الحساب: <code>{method.get('account_data', '')}</code>\n"
                    f"📊 الحالة: {status_icon} {status}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                )
                inline_btns = [
                    [{'text': '✏️ تعديل الاسم', 'callback_data': f'pm_name_{method_id}'},
                     {'text': '🔢 تعديل الحساب', 'callback_data': f'pm_account_{method_id}'}],
                    [{'text': '⏹️ إيقاف' if status == 'active' else '▶️ تشغيل', 'callback_data': f'pm_toggle_{method_id}'}],
                    [{'text': '🗑️ حذف', 'callback_data': f'pm_delete_{method_id}'}],
                    [{'text': '🔙 رجوع للقائمة', 'callback_data': 'pm_list'}]
                ]
                self.send_inline_message(chat_id, detail_text, inline_btns)
            return

        # معالجة تعديل رقم حساب وسيلة دفع (pm_input_account_)
        if isinstance(current_state, str) and current_state.startswith('pm_input_account_'):
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            method_id = current_state.replace('pm_input_account_', '')
            text_msg = message.get('text', '').strip()

            if text_msg in ['إلغاء', 'الغاء', 'cancel', '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                return

            if len(text_msg) < 3:
                self.send_message(chat_id, "❌ رقم الحساب قصير جداً")
                return

            self.update_payment_method_field(method_id, 'account_data', text_msg)
            if user_id in self.user_states: del self.user_states[user_id]
            self.send_message(chat_id, f"✅ تم تحديث رقم الحساب إلى: <code>{text_msg}</code>")
            # العودة لتفاصيل الوسيلة المحدّثة
            method = self.get_payment_method_by_id(method_id)
            if method:
                company = self.get_company_by_id(method.get('company_id', ''))
                company_name = company['name'] if company else 'غير محدد'
                status = method.get('status', 'active')
                status_icon = '✅' if status == 'active' else '⏸️'
                icon = method.get('icon', '💳') or '💳'
                detail_text = (
                    f"💳 <b>{method['method_name']}</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🏢 الشركة: {company_name}\n"
                    f"📋 النوع: {method.get('method_type', '')}\n"
                    f"🔢 رقم الحساب: <code>{method.get('account_data', '')}</code>\n"
                    f"📊 الحالة: {status_icon} {status}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                )
                inline_btns = [
                    [{'text': '✏️ تعديل الاسم', 'callback_data': f'pm_name_{method_id}'},
                     {'text': '🔢 تعديل الحساب', 'callback_data': f'pm_account_{method_id}'}],
                    [{'text': '⏹️ إيقاف' if status == 'active' else '▶️ تشغيل', 'callback_data': f'pm_toggle_{method_id}'}],
                    [{'text': '🗑️ حذف', 'callback_data': f'pm_delete_{method_id}'}],
                    [{'text': '🔙 رجوع للقائمة', 'callback_data': 'pm_list'}]
                ]
                self.send_inline_message(chat_id, detail_text, inline_btns)
            return

        if isinstance(current_state, str) and current_state.startswith('svrp_edit_intro_'):
            # تعديل نص شرح نظام التعويض — يدعم كل اللغات
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text = message.get('text', '').strip()

            if text in ['إلغاء', 'الغاء', 'cancel', '🔙']:
                if user_id in self.user_states: del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_svrp_admin_panel(fake_msg)
                return

            if len(text) < 10:
                self.send_message(chat_id, "❌ النص قصير جداً. اكتب شرحاً كاملاً:")
                return

            # استخراج كود اللغة من الحالة: svrp_edit_intro_{lang}_input
            parts = current_state.replace('svrp_edit_intro_', '').rsplit('_input', 1)
            lang_code = parts[0] if len(parts) == 2 else 'ar'

            lang_key = f'svrp_intro_{lang_code}'
            self.save_setting(lang_key, text)

            lang_names = self.get_language_names()
            lang_native = lang_names.get(lang_code, {}).get('native', lang_code)

            self.send_message(chat_id,
                f"✅ <b>تم حفظ النص الجديد ({lang_native})!</b>\n\n"
                f"📝 سيظهر النص الجديد للعملاء الذين اختاروا هذه اللغة.",
                self.admin_keyboard())

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        if current_state == 'svrp_send_credits_input':
            # إرسال رصيد مجمد — معرف العميل + المبلغ
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text = message.get('text', '').strip()

            if text in ['إلغاء', 'الغاء', '🔙', '❌ إلغاء']:
                if user_id in self.user_states: del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_svrp_panel(fake_msg)
                return

            # تنسيق: C123456 100
            parts = text.split()
            if len(parts) != 2:
                self.send_message(chat_id,
                    "❌ الصيغة: <code>[معرف_العميل] [المبلغ]</code>\n\n"
                    "مثال: <code>C123456 100</code>")
                return

            receiver_customer_id = parts[0].strip()
            try:
                amount = float(parts[1].strip())
            except ValueError:
                self.send_message(chat_id, "❌ المبلغ يجب أن يكون رقماً")
                return

            success, msg = self.svrp.send_frozen_credits(user_id, receiver_customer_id, amount)
            icon = "✅" if success else "❌"
            self.send_message(chat_id, f"{icon} {msg}")

            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        if isinstance(current_state, str) and current_state.startswith('mbot_freeze_input_'):
            # معالجة إدخال تاريخ التجميد
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text = message.get('text', '').strip()
            bot_id = current_state.replace('mbot_freeze_input_', '')

            if text in ['إلغاء', 'الغاء', 'cancel']:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_multi_bot_panel(fake_msg)
                return

            if text.lower() in ['الآن', 'now', 'الان']:
                freeze_date = datetime.now().strftime('%Y-%m-%d')
            else:
                try:
                    datetime.strptime(text, '%Y-%m-%d')
                    freeze_date = text
                except ValueError:
                    self.send_message(chat_id,
                        "❌ صيغة التاريخ غير صحيحة.\n"
                        "استخدم: <code>YYYY-MM-DD</code>\n"
                        "أو اكتب <code>الآن</code> للتجميد الفوري\n"
                        "أو <code>إلغاء</code>")
                    return

            manager = MultiBotManager()
            manager.freeze_bot(bot_id, freeze_date)
            if user_id in self.user_states:
                del self.user_states[user_id]
            self.send_message(chat_id,
                f"✅ تم تحديد تجميد البوت في: <b>{freeze_date}</b>")
            fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
            self.show_multi_bot_panel(fake_msg)
            return
        if isinstance(current_state, str) and current_state == 'svrp_awaiting_screenshot':
            # معالجة استقبال لقطة الشاشة — يجب أن تكون صورة
            if 'photo' not in message:
                self.send_message(chat_id,
                    "❌ يرجى إرسال <b>صورة</b> (لقطة شاشة).\n\n"
                    "أو اكتب 'إلغاء' للعودة")
                return

            # استخراج أكبر صورة
            photos = message['photo']
            largest = photos[-1]  # آخر عنصر هو الأكبر
            file_id = largest['file_id']

            user = self.find_user(user_id)
            customer_id = user.get('customer_id', '') if user else ''

            req_id = self.svrp.create_recovery_request(user_id, customer_id, file_id)
            if user_id in self.user_states:
                del self.user_states[user_id]

            self.send_message(chat_id,
                f"✅ تم استلام لقطة الشاشة!\n\n"
                f"🆔 <code>{req_id}</code>\n"
                f"⏳ سيتم مراجعتها من قبل الإدارة")

            # إشعار جميع الأدمن
            for admin_id in self.admin_ids:
                try:
                    # إرسال الصورة للأدمن
                    data = {
                        'chat_id': admin_id,
                        'photo': file_id,
                        'caption': (
                            f"🔄 <b>طلب استرداد جديد</b>\n\n"
                            f"🆔 <code>{req_id}</code>\n"
                            f"👤 العميل: {user.get('name', '')}\n"
                            f"🆔 رقم العميل: {customer_id}\n\n"
                            f"للموافقة: اضغط الزر وأدخل المبلغ"
                        ),
                        'parse_mode': 'HTML'
                    }
                    self.api_call('sendPhoto', data)

                    # إرسال أزرار الموافقة/الرفض
                    inline_btns = [
                        [{'text': '✅ موافقة', 'callback_data': f'rec_approve_{req_id}'},
                         {'text': '❌ رفض', 'callback_data': f'rec_reject_{req_id}'}]
                    ]
                    self.send_inline_message(admin_id, "🔄 مراجعة الطلب:", inline_btns)
                except Exception as e:
                    logger.error(f"خطأ في إشعار الأدمن بطلب الاسترداد: {e}")
            return

        if isinstance(current_state, str) and current_state == 'svrp_awaiting_send':
            # معالجة إرسال رصيد مجمد — سيتم في المرحلة 3
            self.send_message(chat_id, "📤 سيتم تفعيل هذه الميزة في المرحلة القادمة")
            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        if isinstance(current_state, str) and current_state.startswith('svrp_approve_amount_'):
            # الأدمن يكتب مبلغ الاسترداد للموافقة
            req_id = current_state.replace('svrp_approve_amount_', '')
            try:
                amount = float(text.strip())
                if amount <= 0:
                    self.send_message(chat_id, "❌ المبلغ يجب أن يكون أكبر من صفر")
                    return
                success, msg = self.svrp.approve_recovery_request(req_id, amount, user_id)
                if success:
                    self.send_message(chat_id, f"✅ {msg}", self.admin_keyboard())
                    # إشعار العميل
                    req = self.svrp.get_recovery_request(req_id)
                    if req:
                        self.notify_user(int(req['user_id']),
                            f"✅ <b>تمت الموافقة على طلب استردادك!</b>\n\n"
                            f"💰 تم إضافة <b>{amount:.2f}</b> لرصيدك المجمد 🧊\n\n"
                            f"💡 أرسل رصيداً لأصدقائك لفك التجميد")
                else:
                    self.send_message(chat_id, f"❌ {msg}", self.admin_keyboard())
            except ValueError:
                self.send_message(chat_id, "❌ اكتب مبلغاً رقمياً صحيحاً")
                return
            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        if isinstance(current_state, str) and current_state == 'selecting_language':
            self.handle_language_change(message, text)
            return
        if isinstance(current_state, str) and current_state == 'selecting_language_admin':
            self.handle_language_change(message, text, return_to_admin=True)
            return
        if isinstance(current_state, str) and current_state == 'selecting_currency':
            self.handle_currency_selection(message, text)
            return
        if isinstance(current_state, str) and current_state == 'writing_complaint':
            self.save_complaint(message, text)
            return
        if isinstance(current_state, str) and current_state.startswith('awaiting_reject_reason_'):
            pass  # يُعالج لاحقاً في handle_admin_actions
        elif isinstance(current_state, dict) and 'step' in current_state:
            self.handle_matching_flow(message)
            return
        elif isinstance(current_state, dict) and current_state.get('step') in ('chatting', 'rating'):
            self.handle_matching_flow(message)
            return
        
        # فحص حد المعدل للمستخدمين العاديين (5 طلبات/دقيقة)
        if not self.is_admin(user_id):
            if not self.check_rate_limit(user_id, 'message'):
                u = self.find_user(user_id)
                ul = u.get('language', 'ar') if u else 'ar'
                self.send_message(chat_id, self.tr('rate_limit_msg', ul))
                return
        
        # بداية المحادثة
        if text == '/start' or text.startswith('/start '):
            ref_code = None
            if text.startswith('/start '):
                parts = text.split(' ', 1)
                ref_code = parts[1].strip() if len(parts) > 1 else None
            self.handle_start(message, ref_code)
            return
            
        # معالجة زر إعادة التعيين أولاً (أولوية عالية)
        if text in ['🔄 إعادة تعيين النظام', '🔄 Reset System', '🔄 إعادة تعيين', '🆘 إصلاح شامل']:
            user = self.find_user(user_id)
            if user:
                self.super_reset_user_system(user_id, chat_id, user)
            else:
                self.handle_start(message)
            return
        
        # معالجة الحالات المختلفة
        # معالجة الحالات المتبقية (deposit/withdraw/payment_method — لم تُعالج قبل الـ rate limiter)
        if user_id in self.user_states:
            state = self.user_states[user_id]
            
            # معالجة الإيداع والسحب
            if isinstance(state, str) and ('deposit' in state or 'withdraw' in state):
                if 'deposit' in state:
                    self.process_deposit_flow(message)
                else:
                    self.process_withdrawal_flow(message)
                return
            
            # معالجة اختيار وسيلة الدفع
            elif isinstance(state, dict) and state.get('step') == 'selecting_payment_method':
                self.handle_payment_method_selection(message, text)
                return
        
        # فحص المستخدم المسجل
        user = self.find_user(user_id)
        
        # تعريف جميع مجموعات النصوص مسبقاً (لمنع NameError)
        all_langs = self.get_supported_languages()
        skip_texts = {self.tr('skip_registration', l) for l in all_langs}
        register_texts_new = {self.tr('register_account', l) for l in all_langs}
        register_texts_new.add('📝 تسجيل حساب جديد')
        reset_texts = {self.tr('reset_system', l) for l in all_langs}
        back_texts = {'🔙', '🔙 العودة', '🔙 العودة للقائمة الرئيسية', '🏠 القائمة الرئيسية', '🏠 الرئيسية'}
        back_texts.add(self.tr('main_menu', 'ar'))
        
        if not user:
            # فحص أزرار التسجيل أولاً قبل إعادة عرض handle_start
            skip_texts = {self.tr('skip_registration', l) for l in self.get_supported_languages()}
            register_texts_new = {self.tr('register_account', l) for l in self.get_supported_languages()}
            register_texts_new.add('📝 تسجيل حساب جديد')
            
            if text in register_texts_new:
                self.start_registration(message)
                return
            elif text == '🔐 تسجيل الدخول برقم الهاتف':
                self.start_phone_login(message)
                return
            elif text in skip_texts:
                # المستخدم تخطى التسجيل — عرض القائمة الرئيسية كزائر
                self.send_message(chat_id, 
                    "✅ تم تخطي التسجيل!\n\n⚠️ بدون تسجيل، لن تتمكن من حفظ طلباتك.\nيمكنك التسجيل لاحقاً.",
                    self.main_keyboard('ar', user_id))
                return
            elif text in reset_texts or text in back_texts or text == self.tr('main_menu', 'ar'):
                # زر العودة للقائمة
                self.handle_start(message)
                return
            else:
                self.handle_start(message)
                return
        
        # فحص الحظر
        if user.get('is_banned') == 'yes':
            ban_reason = user.get('ban_reason', 'غير محدد')
            self.send_message(chat_id, f"❌ تم حظر حسابك\nالسبب: {ban_reason}")
            return
        
        # معالجة أوامر الأدمن
        if self.is_admin(user_id):
            admin_texts = {self.tr('admin_panel_btn', l) for l in all_langs} | {'🔧 Admin', '🔧 لوحة الإدارة'}
            if text == '/admin' or text in admin_texts:
                self.handle_admin_panel(message)
                return
            
            # معالجة حالات الأدمن الخاصة
            if user_id in self.user_states:
                admin_state = self.user_states[user_id]
                if isinstance(admin_state, str):
                    if admin_state == 'admin_broadcasting':
                        self.send_broadcast_message(message, text)
                        return
                    elif admin_state.startswith('adding_company_'):
                        self.handle_company_wizard(message)
                        return
                    elif admin_state.startswith('editing_company_') or admin_state == 'selecting_company_edit':
                        self.handle_company_edit_wizard(message)
                        return
                    elif admin_state == 'confirming_company_delete':
                        self.handle_company_delete_confirmation(message)
                        return
                    elif admin_state.startswith('deleting_company_'):
                        company_id = admin_state.replace('deleting_company_', '')
                        self.finalize_company_delete(message, company_id)
                        return
                    elif admin_state == 'sending_user_message_id':
                        self.handle_user_message_id(message)
                        return
                    elif admin_state.startswith('sending_user_message_'):
                        customer_id = admin_state.replace('sending_user_message_', '')
                        self.handle_user_message_content(message, customer_id)
                        return
                    elif admin_state == 'selecting_method_to_edit':
                        self.handle_method_edit_selection(message)
                        return
                    elif admin_state == 'selecting_method_to_delete':
                        self.handle_method_delete_selection(message)
                        return
                    elif admin_state.startswith('editing_method_'):
                        method_id = admin_state.replace('editing_method_', '')
                        self.handle_method_edit_data(message, method_id)
                        return
                    elif admin_state == 'adding_payment_simple':
                        self.handle_simple_payment_company_selection(message)
                        return
                    elif admin_state.startswith('adding_payment_method_'):
                        self.handle_simple_payment_method_data(message)
                        return
                    elif admin_state == 'selecting_method_to_edit_simple':
                        self.handle_simple_method_edit_selection(message)
                        return
                    elif admin_state == 'selecting_method_to_delete_simple':
                        self.handle_simple_method_delete_selection(message)
                        return
                    elif admin_state.startswith('editing_method_simple_'):
                        method_id = admin_state.replace('editing_method_simple_', '')
                        self.handle_simple_method_edit_data(message, method_id)
                        return
                    elif admin_state == 'selecting_method_to_disable':
                        self.handle_method_disable_selection(message)
                        return
                    elif admin_state == 'selecting_method_to_enable':
                        self.handle_method_enable_selection(message)
                        return
                    elif admin_state.startswith('replying_to_complaint_'):
                        complaint_id = admin_state.replace('replying_to_complaint_', '')
                        self.handle_complaint_reply_buttons(message, complaint_id)
                        return
                    elif admin_state.startswith('writing_custom_reply_'):
                        complaint_id = admin_state.replace('writing_custom_reply_', '')
                        reply_text = text.strip()
                        if reply_text.lower() in ['/cancel', 'الغاء', 'إلغاء']:
                            if user_id in self.user_states: del self.user_states[user_id]
                            self.send_message(chat_id, "❌ تم الإلغاء", self.admin_keyboard())
                            return
                        if reply_text:
                            success = self.save_complaint_reply(complaint_id, reply_text)
                            if success:
                                self.send_message(chat_id, f"✅ تم إرسال الرد!\n\n📝 {reply_text}", self.admin_keyboard())
                                self.send_complaint_reply_to_customer(complaint_id, reply_text)
                            else:
                                self.send_message(chat_id, "❌ فشل في حفظ الرد", self.admin_keyboard())
                        if user_id in self.user_states: del self.user_states[user_id]
                        return
                    elif admin_state.startswith('editing_support_'):
                        self.handle_support_data_edit(message, admin_state)
                        return
                    elif admin_state in ['editing_button_label_old', 'editing_button_label_new', 'choose_button_to_edit', 'enter_new_button_label']:
                        self.handle_button_label_edit(message)
                        return

            
            # معالجة النصوص والأزرار للأدمن
            self.handle_admin_actions(message)
            return
        
        # جلب عملة المستخدم أو العملة الافتراضية
        user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
        
        # معالجة القوائم الرئيسية للمستخدمين — مطابقة ديناميكية لكل اللغات
        user_lang = user.get('language', 'ar')
        
        # Build button text set for matching across all languages
        deposit_texts = {self.tr('deposit', l) for l in self.get_supported_languages()}
        withdraw_texts = {self.tr('withdraw', l) for l in self.get_supported_languages()}
        requests_texts = {self.tr('my_requests', l) for l in self.get_supported_languages()}
        profile_texts = {self.tr('profile', l) for l in self.get_supported_languages()}
        complaint_texts = {self.tr('complaint', l) for l in self.get_supported_languages()}
        support_texts = {self.tr('support', l) for l in self.get_supported_languages()}
        currency_texts = {self.tr('change_currency', l) for l in self.get_supported_languages()}
        match_texts = {self.tr('match_btn', l) for l in all_langs} | {'🔄 مطابقة', '🔄 Match'}
        notif_texts = {self.tr('notif_btn', l) for l in all_langs} | {'🔔 إشعاراتي', '🔔 Notifications'}
        ref_texts = {self.tr('referral_btn', l) for l in all_langs} | {'🎁 إحالة', '🎁 Referral'}
        help_texts = {self.tr('help_btn_label', l) for l in all_langs} | {'❓ مساعدة', '❓ Help'}
        svrp_texts = {self.tr('svrp_title', l) for l in all_langs} | {'💎 تعويض 100%', '💎 تعويض'}
        apps_texts = {self.tr('apps_btn', l) for l in all_langs} | {'📱 تطبيقات', '📱 Apps'}
        register_texts = {self.tr('register_account', l) for l in self.get_supported_languages()}
        register_texts.add('📝 تسجيل حساب جديد')
        reset_texts = {self.tr('reset_system', l) for l in self.get_supported_languages()}
        skip_texts = {self.tr('skip_registration', l) for l in self.get_supported_languages()}
        
        if text in deposit_texts:
            logger.info(f"معالجة طلب إيداع من {user_id}")
            self.create_deposit_request(message)
        elif text in withdraw_texts:
            logger.info(f"معالجة طلب سحب من {user_id}")
            self.create_withdrawal_request(message)
        elif text in requests_texts:
            self.show_user_transactions(message)
        elif text in profile_texts:
            self.show_user_profile(message)
        elif text in complaint_texts:
            self.handle_complaint_start(message)
        elif text in support_texts:
            support_text = self.tr('support_info', user_lang, 
                                   phone_num=self.get_setting('support_phone') or '+966501234567',
                                   hours='24/7',
                                   company=self.get_setting('company_name') or 'DUX')
            self.send_message(chat_id, support_text, self.main_keyboard(user_lang, user_id))
        elif text.startswith('🌐 '):
            self.show_language_selection(message)
        elif text in ref_texts:
            self.show_referral_panel(message)
        elif text in svrp_texts:
            self.show_svrp_panel(message)
        elif text in apps_texts:
            self.show_apps_panel(message)
        elif self.svrp:
            all_langs = self.get_supported_languages()
            svrp_wallet_texts = {self.tr('svrp_my_wallet', l) for l in all_langs}
            svrp_tasks_texts = {self.tr('svrp_my_tasks', l) for l in all_langs}
            svrp_codes_texts = {self.tr('svrp_my_codes', l) for l in all_langs}
            svrp_create_texts = {self.tr('svrp_create_code_btn', l) for l in all_langs}
            svrp_redeem_texts = {self.tr('svrp_redeem_code_btn', l) for l in all_langs}
            svrp_tree_texts = {self.tr('svrp_referral_tree_btn', l) for l in all_langs}
            svrp_tier_texts = {self.tr('svrp_my_tier_btn', l) for l in all_langs}

            if text in svrp_wallet_texts:
                self.show_svrp_wallet(message)
            elif text in svrp_tasks_texts:
                self.show_svrp_tasks(message)
            elif text in svrp_codes_texts:
                self.show_svrp_promo_codes(message)
            elif text in svrp_create_texts:
                self.user_states[user_id] = 'svrp_create_promo_'
                self.send_message(chat_id, self.tr('svrp_enter_amount_prompt', user_lang))
            elif text in svrp_redeem_texts:
                self.user_states[user_id] = 'svrp_redeem_promo_'
                self.send_message(chat_id, self.tr('svrp_enter_code_prompt', user_lang))
            elif text in svrp_tree_texts:
                self.show_svrp_referral_tree(message)
            elif text in svrp_tier_texts:
                self.show_svrp_group(message)
            elif text in help_texts:
                self.show_help_guide(message)
            elif text in notif_texts:
                self.show_user_notifications_panel(message)
            elif text in match_texts:
                self.start_matching_flow(message)
            elif text in currency_texts:
                self.show_currency_selection(message)
        elif text in register_texts or text == '📝 تسجيل حساب جديد':
            self.start_registration(message)
        elif text == '🔐 تسجيل الدخول برقم الهاتف':
            self.start_phone_login(message)
        elif text == '/myid':
            self.send_message(chat_id, f"🆔 معرف المستخدم الخاص بك: {user_id}")
        # 💎 تعويض 100% — أوامر نصية
        elif text.startswith('انشاء_كود ') and self.svrp:
            amount_str = text.replace('انشاء_كود ', '').strip()
            try:
                amount = float(amount_str)
                if amount <= 0:
                    self.send_message(chat_id, self.tr('svrp_invalid_amount_err', user_lang))
                else:
                    code, err = self.svrp.create_promo_code(user_id, amount)
                    if err:
                        self.send_message(chat_id, f"❌ {err}")
                    else:
                        self.send_message(chat_id,
                            f"{self.tr('svrp_code_created_msg', user_lang)}\n🎟️ `{code}`\n"
                            f"💰 {self.tr('svrp_code_amount', user_lang)}: {amount}\n"
                            f"📊 {self.tr('svrp_max_uses', user_lang)}: {self.svrp._get_config('promo_code_max_uses')}\n"
                            f"⏰ {self.tr('svrp_expires_in', user_lang)}: {self.svrp._get_config('promo_code_expiry_days')} {self.tr('svrp_days', user_lang)}")
            except ValueError:
                self.send_message(chat_id, self.tr('svrp_invalid_number_err', user_lang))
        elif text.startswith('استرداد_كود ') and self.svrp:
            code = text.replace('استرداد_كود ', '').strip()
            success, msg = self.svrp.redeem_promo_code(user_id, code)
            icon = "✅" if success else "❌"
            self.send_message(chat_id, f"{icon} {msg}")
        elif text.startswith('استلام ') and self.svrp:
            task_id = text.replace('استلام ', '').strip()
            success, msg = self.svrp.claim_task_reward(user_id, task_id)
            icon = "✅" if success else "❌"
            self.send_message(chat_id, f"{icon} {msg}")
        # أزرار نظام المطابقة
        elif text == '✅ تأكيد البدء' and self.match_manager:
            active_match = self.match_manager.get_match_by_user(user_id)
            if active_match:
                # تحديد من هو الساحب لطلب الكود + بياناته الكاملة
                if user_id == int(active_match['withdrawer_id']):
                    self.user_states[user_id] = {'step': 'match_enter_code', 'match_id': active_match['id']}
                    # عرض وسائل الدفع المتاحة للشركة أولاً
                    methods = self.get_payment_methods_by_company(active_match['company_id'])
                    methods_text = (
                        f"🔐 أنشئ كود السحب بالمبلغ: {active_match['amount']} {active_match['currency']}\n\n"
                        f"📝 يجب إرسال البيانات التالية في رسالة واحدة:\n\n"
                        f"1️⃣ كود السحب\n"
                        f"2️⃣ معرف حسابك (ID)\n"
                        f"3️⃣ رقم محفظتك\n"
                        f"4️⃣ وسيلة الدفع (اكتب اسمها من القائمة)\n\n"
                    )
                    if methods:
                        methods_text += "💳 وسائل الدفع المتاحة:\n"
                        for m in methods:
                            icon = m.get('icon', '💳') or '💳'
                            methods_text += f"  {icon} {m['method_name']}\n"
                    else:
                        methods_text += "⚠️ لا توجد وسائل دفع محددة لهذه الشركة — اكتب الوسيلة يدوياً"
                    methods_text += f"\n💡 مثال:\nABC123\nID-789\n0501234567\nحساب بنكي"
                    self.send_message(chat_id, methods_text)
                else:
                    self.send_message(chat_id, "⏳ بانتظار إنشاء الكود من الطرف الآخر...")
            return
        elif text == '✅ تم الإرسال' and self.match_manager:
            active_match = self.match_manager.get_match_by_user(user_id)
            if active_match:
                self.match_manager.update_match_status(active_match['id'], 'completed')
                # إشعار الطرفين
                dep_id = int(active_match['depositor_id'])
                wit_id = int(active_match['withdrawer_id'])
                self.send_message(dep_id, "✅ اكتملت العملية!\n\n⭐ قيّم الطرف الآخر (1-5):")
                self.send_message(wit_id, "✅ اكتملت العملية!\n\n⭐ قيّم الطرف الآخر (1-5):")
                self.user_states[dep_id] = {'step': 'rating', 'match_id': active_match['id']}
                self.user_states[wit_id] = {'step': 'rating', 'match_id': active_match['id']}
            return
        elif text == '🆘 دعم' and self.match_manager:
            active_match = self.match_manager.get_match_by_user(user_id)
            if active_match:
                dispute_id = self.match_manager.open_dispute(active_match['id'], user_id, 'طلب دعم')
                # إشعار الإدمن
                for admin_id in self.admin_ids:
                    try:
                        dispute_msg = (
                            f"⚖️ نزاع جديد\n\n"
                            f"🆔 النزاع: {dispute_id}\n"
                            f"🔗 المطابقة: {active_match['id']}\n"
                            f"💰 المبلغ: {active_match['amount']} {active_match['currency']}\n"
                            f"👤 المودع: {active_match['depositor_alias']}\n"
                            f"👤 الساحب: {active_match['withdrawer_alias']}\n\n"
                            f"📜 سجل الدردشة:"
                        )
                        history = self.match_manager.get_chat_history(active_match['id'])
                        for msg in history[-10:]:
                            dispute_msg += f"\n{msg['sender_alias']}: {msg['message']}"
                        inline_btns = [
                            [{'text': '✅ لصالح المودع', 'callback_data': f'dispute_resolve_dep_{dispute_id}'},
                             {'text': '✅ لصالح الساحب', 'callback_data': f'dispute_resolve_wit_{dispute_id}'}],
                            [{'text': '❌ إلغاء العملية', 'callback_data': f'dispute_cancel_{dispute_id}'}]
                        ]
                        self.send_inline_message(admin_id, dispute_msg, inline_btns)
                    except:
                        pass
                self.send_message(chat_id, "🆘 تم فتح طلب دعم. سيقوم الإدمن بالتدخل.")
            return
        elif text == '❌ إلغاء' and self.match_manager:
            active_match = self.match_manager.get_match_by_user(user_id)
            if active_match:
                self.match_manager.cancel_match(active_match['id'], user_id)
                dep_id = int(active_match['depositor_id'])
                wit_id = int(active_match['withdrawer_id'])
                self.send_message(dep_id, "❌ تم إلغاء المطابقة", self.main_keyboard(user.get('language','ar'), dep_id))
                self.send_message(wit_id, "❌ تم إلغاء المطابقة", self.main_keyboard(user.get('language','ar'), wit_id))
                if dep_id in self.user_states: del self.user_states[dep_id]
                if wit_id in self.user_states: del self.user_states[wit_id]
            return
        elif text in reset_texts or text in ['🔙 العودة للقائمة الرئيسية', '🔙 العودة', '⬅️ العودة', '🏠 الرئيسية', '🏠 القائمة الرئيسية', '🔄 إعادة تعيين النظام', '🆘 إصلاح', 'reset', 'fix', '🆘 إصلاح شامل'] or text == self.tr('main_menu', user_lang):
            # إجراء إعادة تعيين شاملة وقوية
            self.super_reset_user_system(user_id, chat_id, user)
        else:

            # معالجة حالات نظام المطابقة
            if isinstance(state, dict) and 'step' in state:
                self.handle_matching_flow(message)
                return

            # معالجة حالة المطابقة (نص عادي)
            if state == 'match_select_type':
                self.handle_matching_flow(message)
                return

            # معالجة حالات المطابقة
            if isinstance(state, dict) and 'step' in state:
                if state['step'] in ('match_amount', 'match_company', 'match_enter_code', 'chatting', 'rating'):
                    self.handle_matching_flow(message)
                    return

            # رسالة خطأ محسنة مع زر إصلاح قوي
            reset_btn = self.tr('reset_system', user_lang)
            deposit_btn = self.tr('deposit', user_lang)
            withdraw_btn = self.tr('withdraw', user_lang)
            requests_btn = self.tr('my_requests', user_lang)
            profile_btn = self.tr('profile', user_lang)
            menu_btn = self.tr('main_menu', user_lang)
            error_keyboard = {
                'keyboard': [
                    [{'text': reset_btn}],
                    [{'text': deposit_btn}, {'text': withdraw_btn}],
                    [{'text': requests_btn}, {'text': profile_btn}],
                    [{'text': menu_btn}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            error_msg = self.tr('unknown_command', user_lang)
            
            self.send_message(chat_id, error_msg, error_keyboard)

    def handle_start_language_choice(self, message):
        """معالجة اختيار اللغة في بداية التسجيل"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        text = message.get('text', '')

        lang_names = self.get_language_names()
        selected_lang = None
        for code, info in lang_names.items():
            if text.startswith(info['flag']):
                selected_lang = code
                break

        if not selected_lang:
            selected_lang = 'ar'

        # تخزين اللغة المختارة مؤقتاً
        self._start_lang = getattr(self, '_start_lang', {})
        self._start_lang[user_id] = selected_lang

        # طلب رقم الهاتف
        prompt = (
            f"✅ {self.tr('change_success', selected_lang)}\n\n"
            f"📱 {self.tr('enter_phone_prompt', selected_lang)}"
        )
        keyboard = {
            'keyboard': [
                [{'text': self.tr('share_phone_btn', selected_lang), 'request_contact': True}],
                [{'text': self.tr('enter_phone_manual', selected_lang)}],
                [{'text': self.tr('main_menu_btn', selected_lang)}]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        self.user_states[user_id] = 'start_phone_input'
        self.send_message(chat_id, prompt, keyboard)

    def handle_start_phone(self, message):
        """معالجة رقم الهاتف في بداية التسجيل — تسجيل دخول أو تسجيل جديد"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        selected_lang = getattr(self, '_start_lang', {}).get(user_id, 'ar')

        # استخراج رقم الهاتف
        if 'contact' in message:
            phone = message['contact']['phone_number']
            if not phone.startswith('+'):
                phone = '+' + phone
        elif 'text' in message:
            phone = message['text'].strip()

            # إذا ضغط زر "إدخال يدوي" — اطلب الرقم ولا تغير الحالة
            if phone in {self.tr('enter_phone_manual', l) for l in self.get_supported_languages()}:
                self.send_message(chat_id,
                    f"✍️ {self.tr('enter_phone_prompt', selected_lang)}")
                return

            # إذا ضغط زر القائمة الرئيسية
            if phone in ['🏠 القائمة الرئيسية', '🏠'] or phone in {self.tr('main_menu_btn', l) for l in self.get_supported_languages()}:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.handle_start(message)
                return

            # التحقق من صحة رقم الهاتف
            if len(phone) < 10 or not any(c.isdigit() for c in phone):
                self.send_message(chat_id, self.tr('phone_login_invalid', selected_lang))
                return
        else:
            self.send_message(chat_id, self.tr('phone_login_send_prompt', selected_lang))
            return

        # البحث عن المستخدم برقم الهاتف
        existing_user = self.find_user_by_phone(phone)
        if existing_user:
            # مستخدم قديم — تسجيل دخول تلقائي
            self.link_telegram_to_user(phone, user_id)
            user = self.find_user(user_id)
            if not user:
                self.send_message(chat_id, self.tr('phone_login_error', selected_lang))
                if user_id in self.user_states:
                    del self.user_states[user_id]
                return

            if user.get('is_banned') == 'yes':
                self.send_message(chat_id, self.tr('phone_login_banned', selected_lang, reason=user.get('ban_reason', self.tr('unknown_reason', selected_lang))))
                if user_id in self.user_states:
                    del self.user_states[user_id]
                return

            lang = user.get('language', selected_lang)
            welcome_text = (
                f"✅ {self.tr('welcome_back', lang, name=user.get('name', ''), customer_id=user.get('customer_id', ''))}\n\n"
                f"💡 {self.tr('registration_success', lang, name=user.get('name', ''), phone=user.get('phone', ''), customer_id=user.get('customer_id', ''), date=user.get('date', ''))}"
            )
            self.send_message(chat_id, welcome_text, self.main_keyboard(lang, user_id))
            if user_id in self.user_states:
                del self.user_states[user_id]
        else:
            # مستخدم جديد — بدء التسجيل باللغة المختارة
            if user_id in self.user_states:
                del self.user_states[user_id]

            # كشف اللغة/الدولة/العملة من رقم الهاتف
            detected_lang, detected_country = self.detect_language_from_phone(phone)
            detected_currency = self.detect_currency_from_country(detected_country)
            # استخدام اللغة المختارة يدوياً إن اختلفت
            final_lang = selected_lang if selected_lang else detected_lang

            name_prompt = self.tr('enter_name_prompt', final_lang)
            reg_keyboard = {
                'keyboard': [
                    [{'text': self.tr('cancel_registration', final_lang)}],
                    [{'text': '🏠 القائمة الرئيسية'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }

            self.send_message(chat_id, f"📝 {name_prompt}", reg_keyboard)
            self.user_states[user_id] = f'registering_name_{final_lang}_{phone}'

    def start_phone_login(self, message):
        """تسجيل الدخول برقم الهاتف — للمستخدمين الذين لديهم حساب سابق"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        user = self.find_user(user_id)
        lang = user.get('language', 'ar') if user else 'ar'
        
        login_text = (
            f"{self.tr('phone_login_title', lang)}\n\n"
            f"{self.tr('phone_login_share_prompt', lang)}\n"
            f"{self.tr('phone_login_example', lang)}"
        )
        
        keyboard = {
            'keyboard': [
                [{'text': self.tr('share_phone_btn', lang), 'request_contact': True}],
                [{'text': self.tr('main_menu_btn', lang)}]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        
        self.send_message(chat_id, login_text, keyboard)
        self.user_states[user_id] = 'phone_login_waiting'

    def handle_phone_login(self, message):
        """معالجة تسجيل الدخول برقم الهاتف"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']

        # فحص أزرار الإلغاء والعودة أولاً
        text = message.get('text', '').strip()
        all_langs = self.get_supported_languages()
        main_menu_texts = {self.tr('main_menu', l) for l in all_langs} | {self.tr('main_menu_btn', l) for l in all_langs} | {'🏠 القائمة الرئيسية', '🏠 الرئيسية', '🏠 Main Menu'}
        cancel_texts = {'❌ إلغاء', '❌ Cancel', 'الغاء', 'إلغاء'}

        if text in main_menu_texts or text in cancel_texts:
            if user_id in self.user_states:
                del self.user_states[user_id]
            self.handle_start(message)
            return

        # استخراج رقم الهاتف
        if 'contact' in message:
            phone = message['contact']['phone_number']
            if not phone.startswith('+'):
                phone = '+' + phone
        elif 'text' in message:
            phone = message['text'].strip()
            if len(phone) < 10:
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                self.send_message(chat_id, self.tr('phone_login_invalid', lang))
                return
        else:
            self.send_message(chat_id, self.tr('phone_login_send_prompt', lang))
            return
        
        # البحث عن المستخدم برقم الهاتف
        existing_user = self.find_user_by_phone(phone)
        if not existing_user:
            u = self.find_user(user_id)
            ul = u.get('language', 'ar') if u else 'ar'
            self.send_message(chat_id,
                self.tr('phone_login_not_found', ul),
                self.main_keyboard(ul, user_id))
            if user_id in self.user_states:
                del self.user_states[user_id]
            return
        
        # ربط telegram_id الجديد بالحساب القديم
        self.link_telegram_to_user(phone, user_id)
        user = self.find_user(user_id)
        
        if not user:
            self.send_message(chat_id, self.tr('phone_login_error', 'ar'))
            if user_id in self.user_states:
                del self.user_states[user_id]
            return
        
        lang = user.get('language', 'ar')
        
        # التحقق من الحظر
        if user.get('is_banned') == 'yes':
            ban_reason = user.get('ban_reason', self.tr('unknown_reason', lang))
            self.send_message(chat_id, self.tr('phone_login_banned', lang, reason=ban_reason))
            if user_id in self.user_states:
                del self.user_states[user_id]
            return
        
        welcome_text = (
            f"{self.tr('phone_login_success', lang)}\n\n"
            f"{self.tr('phone_login_name', lang)}: {user['name']}\n"
            f"{self.tr('phone_login_phone', lang)}: {user['phone']}\n"
            f"{self.tr('phone_login_customer_id', lang)}: {user['customer_id']}\n"
            f"{self.tr('phone_login_date', lang)}: {user.get('date', '')}\n\n"
            f"{self.tr('phone_login_restored', lang)}"
        )
        self.send_message(chat_id, welcome_text, self.main_keyboard(lang, user_id))
        if user_id in self.user_states:
            del self.user_states[user_id]

    def start_registration(self, message):
        """بدء عملية التسجيل للمستخدمين غير المسجلين"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        
        # التحقق إذا كان المستخدم مسجل بالفعل
        user = self.find_user(user_id)
        if user:
            self.send_message(chat_id, f"✅ أنت مسجل بالفعل!\n🆔 رقم العميل: {user['customer_id']}", 
                            self.main_keyboard(user.get('language', 'ar'), user_id))
            return
        
        # بدء عملية التسجيل — مسح أي حالة سابقة أولاً
        if user_id in self.user_states:
            del self.user_states[user_id]
        
        welcome_text = (
            "📝 بدء التسجيل\n\n"
            "✍️ اكتب اسمك الكامل:\n"
            "(مثال: أحمد محمد)\n\n"
            "⚠️ أرسل اسماً حقيقياً، وليس نص زر"
        )
        
        registration_keyboard = {
            'keyboard': [
                [{'text': '❌ إلغاء التسجيل'}],
                [{'text': '🏠 القائمة الرئيسية'}]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        
        self.send_message(chat_id, welcome_text, registration_keyboard)
        self.user_states[user_id] = 'registering_name'
    
    def super_reset_user_system(self, user_id, chat_id, user):
        """إعادة تعيين شاملة وقوية للنظام"""
        try:
            logger.info(f"بدء إعادة تعيين شاملة للمستخدم: {user_id}")
            
            # 1. تنظيف جميع حالات المستخدم
            if user_id in self.user_states:
                del self.user_states[user_id]
                logger.info(f"تم حذف حالة المستخدم: {user_id}")
            
            # 2. تنظيف البيانات المؤقتة
            temp_data_attrs = [
                'temp_company_data',
                'edit_company_data', 
                'temp_deposit_data',
                'temp_withdrawal_data',
                'temp_complaint_data',
                'temp_payment_data',
                'admin_temp_data'
            ]
            
            for attr in temp_data_attrs:
                if hasattr(self, attr) and user_id in getattr(self, attr, {}):
                    del getattr(self, attr)[user_id]
                    logger.info(f"تم حذف {attr} للمستخدم: {user_id}")
            
            # 3. إعادة تحميل بيانات المستخدم من الملف
            fresh_user = self.find_user(user_id)
            if fresh_user:
                user.update(fresh_user)
                logger.info(f"تم إعادة تحميل بيانات المستخدم: {user_id}")
            
            # 4. التحقق من سلامة الملفات الأساسية وإصلاحها
            self.verify_and_fix_system_files()
            
            # 5. إرسال رسالة نجاح مع معلومات محدثة
            welcome_text = f"""✅ تم إعادة تعيين النظام بنجاح!

🔧 تم إجراء التالي:
• تنظيف جميع الحالات المؤقتة
• إعادة تحميل البيانات الشخصية
• فحص سلامة النظام
• إصلاح أي أخطاء محتملة

👤 بياناتك المحدثة:
🏷️ الاسم: {user.get('name', 'غير محدد')}
🆔 رقم العميل: {user.get('customer_id', 'غير محدد')}
📱 الهاتف: {user.get('phone', 'غير محدد')}
🌐 اللغة: {'العربية' if user.get('language', 'ar') == 'ar' else 'English'}

🏠 النظام جاهز للاستخدام - اختر الخدمة المطلوبة:"""
            
            # إرسال الرسالة مع الكيبورد المناسب
            if self.is_admin(user_id):
                keyboard = self.admin_keyboard(user.get('language', 'ar'))
            else:
                keyboard = self.main_keyboard(user.get('language', 'ar'))
                
            self.send_message(chat_id, welcome_text, keyboard)
            logger.info(f"تمت إعادة التعيين الشاملة بنجاح للمستخدم: {user_id}")
            
        except Exception as e:
            logger.error(f"خطأ في إعادة التعيين الشاملة للمستخدم {user_id}: {e}")
            
            # في حالة فشل إعادة التعيين، إرسال رسالة طوارئ
            emergency_text = """🚨 حدث خطأ في إعادة التعيين

🔧 يرجى المحاولة مرة أخرى أو التواصل مع الدعم الفني

⚡ رقم الدعم: +966501234567"""
            
            emergency_keyboard = {
                'keyboard': [
                    [{'text': '🆘 إصلاح شامل'}, {'text': '🔄 إعادة تعيين النظام'}],
                    [{'text': '💰 طلب إيداع'}, {'text': '💸 طلب سحب'}]
                ],
                'resize_keyboard': True
            }
            
            self.send_message(chat_id, emergency_text, emergency_keyboard)
    
    def verify_and_fix_system_files(self):
        """فحص وإصلاح ملفات النظام الأساسية"""
        try:
            # التحقق من وجود الملفات الأساسية وإنشاؤها إذا لزم الأمر
            required_files = [
                'users.csv',
                'transactions.csv', 
                'companies.csv',
                'complaints.csv',
                'payment_methods.csv',
                'exchange_addresses.csv'
            ]
            
            for file_name in required_files:
                if not os.path.exists(file_name):
                    logger.warning(f"ملف مفقود يتم إنشاؤه: {file_name}")
                    self.init_files()  # إعادة إنشاء جميع الملفات
                    break
                    
            logger.info("تم فحص سلامة ملفات النظام بنجاح")
            
        except Exception as e:
            logger.error(f"خطأ في فحص ملفات النظام: {e}")

    def handle_admin_actions(self, message):
        """معالجة إجراءات الأدمن"""
        text = message['text']
        chat_id = message['chat']['id']
        user_id = message['from']['id']

        admin_user = self.find_user(user_id)
        admin_lang = admin_user.get('language', 'ar') if admin_user else 'ar'
        all_langs = self.get_supported_languages()

        # أولاً: التحقق مما إذا كان الأدمن في مرحلة إدخال سبب الرفض
        # إذا كان user_state يبدأ بـ 'awaiting_reject_reason_', فهذا يعني أننا بانتظار السبب
        user_state = self.user_states.get(user_id, '')
        # معالجة مرحلة إدخال سبب الرفض
        if isinstance(user_state, str) and user_state.startswith('awaiting_reject_reason_'):
            trans_id = user_state.replace('awaiting_reject_reason_', '')
            reason_text = text.strip()
            # إذا كتب الأدمن كلمة إلغاء أو لا يريد المتابعة
            if reason_text.lower() in ['الغاء', 'إلغاء', 'الغاء العملية', 'cancel', 'الغاء الرفض']:
                # إلغاء العملية
                del self.user_states[user_id]
                # إزالة السبب المؤقت إن وجد
                if user_id in self.pending_reject_reasons:
                    del self.pending_reject_reasons[user_id]
                self.send_message(chat_id, f"❌ تم إلغاء عملية الرفض للمعاملة {trans_id}.", self.admin_keyboard())
                return
            # إذا كتب السبب
            if reason_text:
                # حفظ السبب مؤقتاً
                self.pending_reject_reasons[user_id] = {'trans_id': trans_id, 'reason': reason_text}
                # تغيير الحالة إلى تأكيد الرفض
                self.user_states[user_id] = f'confirming_reject_{trans_id}'
                # إرسال رسالة للتأكيد مع زر
                # أزرار inline لتأكيد الرفض
                inline_btns = [
                    [{'text': f'📤 تأكيد رفض', 'callback_data': f'confirm_reject_{trans_id}'},
                     {'text': '❌ إلغاء', 'callback_data': 'cancel_reject'}]
                ]
                self.send_inline_message(chat_id,
                                  f"📝 تم حفظ سبب الرفض: {reason_text}\n\nاضغط على زر تأكيد الرفض أدناه لإرسال الرفض للعميل، أو اختر إلغاء.",
                                  inline_btns)
                return
            # إذا لم يكتب شيئاً، نعيد الطلب
            self.send_message(chat_id, f"❌ يرجى كتابة سبب الرفض للمعاملة {trans_id} أو اكتب 'إلغاء' لإلغاء العملية.", self.admin_keyboard())
            return
        # معالجة مرحلة تأكيد الرفض
        if isinstance(user_state, str) and user_state.startswith('confirming_reject_'):
            trans_id = user_state.replace('confirming_reject_', '')
            # تأكيد الرفض
            if text.strip().startswith('📤') or 'تأكيد' in text or 'تاكيد' in text:
                pending = self.pending_reject_reasons.get(user_id)
                reason = pending['reason'] if pending else ''
                # إزالة السجلات المؤقتة
                if user_id in self.pending_reject_reasons:
                    del self.pending_reject_reasons[user_id]
                del self.user_states[user_id]
                self.reject_transaction(message, trans_id, reason)
                return
            # إلغاء الرفض خلال مرحلة التأكيد
            if text.strip().lower() in ['الغاء', 'إلغاء', 'إلغاء الرفض', 'cancel', '❌ إلغاء']:
                # إزالة السجلات المؤقتة
                if user_id in self.pending_reject_reasons:
                    del self.pending_reject_reasons[user_id]
                del self.user_states[user_id]
                self.send_message(chat_id, f"❌ تم إلغاء عملية الرفض للمعاملة {trans_id}.", self.admin_keyboard())
                return
            # أي نص آخر لا يقبل في هذه المرحلة
            self.send_message(chat_id, f"❌ يرجى الضغط على زر تأكيد الرفض أو اختيار إلغاء.", self.admin_keyboard())
            return
        
        # الأزرار الرئيسية
        if text in {self.tr('admin_pending_requests', l) for l in all_langs}:
            self.show_pending_requests(message)
        elif text == '✅ طلبات مُوافقة':
            self.show_approved_transactions(message)
        elif text in {self.tr('admin_users', l) for l in all_langs}:
            self.show_users_management(message)
        elif text in {self.tr('admin_search', l) for l in all_langs}:
            self.prompt_admin_search(message)
        elif text in {self.tr('admin_managers', l) for l in all_langs}:
            self.show_admin_management(message)
        elif text in {self.tr('admin_buttons', l) for l in all_langs}:
            self.start_button_label_editor(message)
        elif text == '📋 عرض قائمة المديرين':
            self.show_detailed_admin_list(message)
        elif text == '➕ إضافة مدير دائم':
            self.prompt_add_permanent_admin(message)
        elif text == '🕐 إضافة مدير مؤقت':
            self.prompt_add_temp_admin(message)
        elif text == '➖ إزالة مدير':
            self.prompt_remove_admin(message)
        elif text == '🎭 تخصيص صلاحيات':
            self.start_permission_editor(message)
        elif text == '📊 إحصائيات المديرين':
            self.show_admin_statistics(message)
        elif text == '🆔 معرف المستخدم':
            self.send_message(message['chat']['id'], f"🆔 معرف المستخدم الخاص بك: {message['from']['id']}", self.admin_keyboard())
        elif text in {self.tr('admin_payment_methods', l) for l in all_langs}:
            self.show_payment_methods_management(message)
        elif text == '📊 الإحصائيات':
            self.show_detailed_stats(message)
        elif text in {self.tr('admin_excel_report', l) for l in all_langs}:
            self.generate_professional_excel_report(message)
        elif text in {self.tr('admin_broadcast', l) for l in all_langs}:
            self.prompt_broadcast(message)
        elif text in {self.tr('admin_ban_user', l) for l in all_langs}:
            self.prompt_ban_user(message)
        elif text in {self.tr('admin_unban_user', l) for l in all_langs}:
            self.prompt_unban_user(message)
        
        # معالجة أوامر النص المباشرة
        elif text.startswith('الغاء_حظر ') or text.startswith('الغاء حظر '):
            customer_id = text.replace('الغاء_حظر ', '').replace('الغاء حظر ', '').strip()
            if customer_id:
                self.unban_user_admin(message, customer_id)
            else:
                self.send_message(chat_id, "❌ الصيغة الصحيحة:\nالغاء_حظر [رقم_العميل]\nمثال: الغاء_حظر C810563", self.admin_keyboard())
        elif text == '📝 إضافة شركة':
            self.start_add_company_wizard(message)
        elif text == '🏢 الشركات':
            self.show_companies_management_enhanced(message)
        elif text == '🔄 تحديث القائمة':
            self.show_companies_management_enhanced(message)
        elif text == '➕ إضافة شركة جديدة':
            self.prompt_add_company(message)
        elif text == '✏️ تعديل شركة':
            self.prompt_edit_company(message)
        elif text == '🗑️ حذف شركة':
            self.prompt_delete_company(message)
        elif text in ['↩️ العودة للوحة الأدمن', '🏠 لوحة الأدمن']:
            self.handle_admin_panel(message)
        elif text in ['↩️ العودة', '🔙 العودة', '⬅️ العودة']:
            # تحديد السياق المناسب للعودة حسب الحالة
            user_state = self.user_states.get(message['from']['id'])
            if user_state:
                if 'payment' in str(user_state) or 'method' in str(user_state):
                    self.show_payment_methods_management(message)
                elif 'company' in str(user_state):
                    self.show_companies_management_enhanced(message)
                else:
                    self.handle_admin_panel(message)
            else:
                self.handle_admin_panel(message)
        elif text in {self.tr('admin_addresses', l) for l in all_langs}:
            self.show_addresses_management(message)
        elif text in {self.tr('admin_change_language', l) for l in all_langs}:
            self.show_language_selection(message, return_to_admin=True)
        elif text == '🤖 البوتات' and MULTI_BOT_AVAILABLE and getattr(self, 'can_manage_bots', False):
            self.show_multi_bot_panel(message)
        elif text.startswith('اضافة_ادمن_بوت ') and MULTI_BOT_AVAILABLE and getattr(self, 'can_manage_bots', False):
            # اضافة_ادمن_بوت BOT123 99999999
            parts = text.replace('اضافة_ادمن_بوت ', '').split()
            if len(parts) == 2:
                bot_id = parts[0].strip()
                admin_id = parts[1].strip()
                manager = MultiBotManager()
                if manager.add_admin(bot_id, admin_id):
                    self.send_message(message['chat']['id'],
                        f"✅ تم إضافة الأدمن {admin_id} للبوت {bot_id}",
                        self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ فشل في إضافة الأدمن", self.admin_keyboard())
            else:
                self.send_message(message['chat']['id'],
                    "❌ الصيغة: اضافة_ادمن_بوت [BOT_ID] [ADMIN_ID]\nمثال: اضافة_ادمن_بوت BOT123456 99999999",
                    self.admin_keyboard())
        elif text.startswith('حذف_ادمن_بوت ') and MULTI_BOT_AVAILABLE and getattr(self, 'can_manage_bots', False):
            # حذف_ادمن_بوت BOT123 99999999
            parts = text.replace('حذف_ادمن_بوت ', '').split()
            if len(parts) == 2:
                bot_id = parts[0].strip()
                admin_id = parts[1].strip()
                manager = MultiBotManager()
                if manager.remove_admin(bot_id, admin_id):
                    self.send_message(message['chat']['id'],
                        f"✅ تم حذف الأدمن {admin_id} من البوت {bot_id}",
                        self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ فشل في حذف الأدمن (لا يمكن حذف آخر أدمن)", self.admin_keyboard())
            else:
                self.send_message(message['chat']['id'],
                    "❌ الصيغة: حذف_ادمن_بوت [BOT_ID] [ADMIN_ID]",
                    self.admin_keyboard())
        elif text in {self.tr('admin_themes', l) for l in all_langs} and THEME_AVAILABLE:
            self.show_theme_panel(message)
        elif text.startswith('ثيم_') and THEME_AVAILABLE:
            theme_key = text.replace('ثيم_', '').strip()
            self.save_setting('active_theme', theme_key)
            theme = get_theme(theme_key)
            self.send_message(message['chat']['id'],
                f"✅ تم تفعيل ثيم: {theme.get('icon', '')} {theme.get('name_ar', theme_key)}\n\n"
                f"سيتم تطبيق الثيم على جميع الرسائل والأزرار.",
                self.admin_keyboard())
            return
        elif text in {self.tr('admin_support_data', l) for l in all_langs}:
            self.show_support_data_editor(message)
        elif text in {self.tr('admin_settings', l) for l in all_langs}:
            self.show_system_settings(message)
        elif text in {self.tr('admin_complaints', l) for l in all_langs}:
            self.show_complaints_admin(message)
        elif text in ['🔄 تحديث الشكاوى', '🔄 تحديث']:
            self.show_complaints_admin(message)
        elif text.startswith('📞 رد على '):
            complaint_id = text.replace('📞 رد على ', '').strip()
            self.start_complaint_reply_wizard(message, complaint_id)
        elif text in {self.tr('admin_quick_commands', l) for l in all_langs}:
            self.show_quick_copy_commands(message)
        elif text in {self.tr('admin_recovery', l) for l in all_langs} and self.svrp:
            self.show_svrp_admin_panel(message)
        elif text in {self.tr('admin_apps', l) for l in all_langs}:
            self.show_apps_admin_panel(message)
        elif text in {self.tr('admin_message_user', l) for l in all_langs}:
            self.start_send_user_message(message)
        elif text in {self.tr('admin_notifications', l) for l in all_langs}:
            self.show_notifications_panel(message)
        elif text in {self.tr('admin_backup', l) for l in all_langs}:
            self.manual_backup_command(message)
        elif text == '➕ إضافة وسيلة دفع':
            self.start_simple_payment_method_wizard(message)
        elif text == '✏️ تعديل وسيلة دفع':
            self.start_edit_payment_method_wizard(message)
        elif text == '🗑️ حذف وسيلة دفع':
            self.start_delete_payment_method_wizard(message)
        elif text == '📊 عرض وسائل الدفع':
            self.show_all_payment_methods_simplified(message)
        elif text == '⏹️ إيقاف وسيلة دفع':
            self.start_disable_payment_method_wizard(message)
        elif text == '▶️ تشغيل وسيلة دفع':
            self.start_enable_payment_method_wizard(message)
        elif text in {self.tr('admin_main_menu', l) for l in all_langs}:
            # إنهاء جلسة الأدمن والعودة للقائمة الرئيسية
            if message['from']['id'] in self.user_states:
                del self.user_states[message['from']['id']]
            user = self.find_user(message['from']['id'])
            if user:
                # استخدام الترجمة لعرض شاشة اختيار الخدمة كاملة بلغته
                lang = user.get('language', 'ar')
                welcome_text = self.tr(
                    'choose_service',
                    lang,
                    name=user.get('name', 'غير محدد'),
                    customer_id=user.get('customer_id', 'غير محدد')
                )
                self.send_message(chat_id, welcome_text, self.main_keyboard(lang))
        
        # أوامر نصية للأدمن (مبسطة مع احتمالات متعددة)
        elif any(word in text.lower() for word in ['موافقة', 'موافق', 'اوافق', 'أوافق', 'قبول', 'مقبول', 'تأكيد', 'تاكيد', 'نعم']):
            # استخراج رقم المعاملة
            words = text.split()
            trans_id = None
            for word in words:
                if any(word.startswith(prefix) for prefix in ['DEP', 'WTH']):
                    trans_id = word
                    break
            
            if trans_id:
                self.approve_transaction(message, trans_id)
            else:
                self.send_message(message['chat']['id'], "❌ لم يتم العثور على رقم المعاملة. مثال: موافقة DEP123456", self.admin_keyboard())
                
        elif any(word in text.lower() for word in ['رفض', 'رافض', 'لا', 'مرفوض', 'إلغاء', 'الغاء', 'منع']):
            # استخراج رقم المعاملة والسبب
            words = text.split()
            trans_id = None
            reason_start = -1
            for i, word in enumerate(words):
                if any(word.startswith(prefix) for prefix in ['DEP', 'WTH']):
                    trans_id = word
                    reason_start = i + 1
                    break
            if trans_id:
                # تجميع بقية الكلمات كسبب
                reason = ' '.join(words[reason_start:]) if reason_start != -1 and reason_start < len(words) else ''
                # إذا لم يتم تقديم سبب، نطلب من الأدمن كتابته
                if not reason.strip():
                    # تعيين حالة انتظار السبب لهذا الأدمن
                    self.user_states[user_id] = f'awaiting_reject_reason_{trans_id}'
                    self.send_message(chat_id, f"📝 يرجى كتابة سبب الرفض للمعاملة {trans_id} ثم إرساله، أو اكتب 'إلغاء' لإلغاء العملية.", self.admin_keyboard())
                    return
                # إذا تم تقديم السبب، نقوم برفض المعاملة مباشرة
                self.reject_transaction(message, trans_id, reason)
            else:
                self.send_message(message['chat']['id'], "❌ لم يتم العثور على رقم المعاملة. مثال: رفض DEP123456 سبب الرفض", self.admin_keyboard())
        elif text.startswith('بحث '):
            query = text.replace('بحث ', '')
            self.search_users_admin(message, query)
        elif text.startswith('اضافة_ادمن '):
            user_id_to_add = text.replace('اضافة_ادمن ', '')
            self.add_admin_user(message, user_id_to_add)
        elif text.startswith('اضافة ادمن '):
            user_id_to_add = text.replace('اضافة ادمن ', '')
            self.add_admin_user(message, user_id_to_add)
        elif text.startswith('ادمن_مؤقت '):
            parts = text.replace('ادمن_مؤقت ', '').split()
            if len(parts) < 1:
                self.send_message(chat_id, "❌ الصيغة: ادمن_مؤقت ID الدور المدة\nمثال: ادمن_مؤقت 123456789 full 24", self.admin_keyboard())
                return
            user_id_to_add = parts[0]
            role = parts[1] if len(parts) > 1 else 'full'
            try:
                duration = int(parts[2]) if len(parts) > 2 else 0
            except ValueError:
                duration = 0
            self.add_temp_admin(message, user_id_to_add, role=role, duration_hours=duration)
        elif text.startswith('صلاحيات '):
            parts = text.replace('صلاحيات ', '').split()
            if len(parts) >= 2:
                admin_id_str = parts[0]
                role = parts[1]
                self.set_admin_role(message, admin_id_str, role)
            else:
                self.send_message(chat_id, "❌ الصيغة: صلاحيات ID_المستخدم الدور\nمثال: صلاحيات 123456789 transactions", self.admin_keyboard())
        elif text.startswith('ازالة_ادمن '):
            user_id_to_remove = text.replace('ازالة_ادمن ', '')
            self.remove_admin_user(message, user_id_to_remove)
        elif text.startswith('حظر '):
            parts = text.replace('حظر ', '').split(' ', 1)
            customer_id = parts[0]
            reason = parts[1] if len(parts) > 1 else 'مخالفة الشروط'
            self.ban_user_admin(message, customer_id, reason)
        elif text.startswith('الغاء_حظر '):
            customer_id = text.replace('الغاء_حظر ', '')
            self.unban_user_admin(message, customer_id)
        elif text.startswith('اضافة_شركة '):
            self.add_company_simple_with_display(message, text)
        elif text.startswith('حذف_شركة '):
            company_id = text.replace('حذف_شركة ', '')
            self.delete_company_simple(message, company_id)
        elif text.startswith('عنوان_جديد '):
            new_address = text.replace('عنوان_جديد ', '')
            self.update_address_simple(message, new_address)
        elif any(word in text.lower() for word in ['عنوان', 'العنوان', 'تحديث_عنوان']):
            # استخراج العنوان الجديد
            new_address = text
            for word in ['عنوان', 'العنوان', 'تحديث_عنوان']:
                new_address = new_address.replace(word, '').strip()
            if new_address:
                self.update_address_simple(message, new_address)
            else:
                self.send_message(message['chat']['id'], "يرجى كتابة العنوان الجديد. مثال: عنوان شارع الملك فهد", self.admin_keyboard())
        elif text.startswith('تعديل_اعداد '):
            self.update_setting_simple(message, text)
        elif text.startswith('تعديل_استرداد ') and self.svrp:
            # تعديل إعدادات تعويض 100%
            parts = text.replace('تعديل_استرداد ', '').split()
            if len(parts) == 2:
                key = parts[0].strip()
                try:
                    val = parts[1].strip()
                    old_val = self.svrp._get_config(key)
                    if old_val != 0 or key in ['recovery_multiplier', 'max_recovery_cap', 'credit_expiry_days',
                                               'wagering_requirement', 'promo_code_max_uses',
                                               'promo_code_expiry_days', 'max_recovery_per_month']:
                        # تحديث القيمة في SVRP_CONFIG
                        from svrp import SVRP_CONFIG
                        if isinstance(SVRP_CONFIG.get(key), float):
                            SVRP_CONFIG[key] = float(val)
                        elif isinstance(SVRP_CONFIG.get(key), int):
                            SVRP_CONFIG[key] = int(val)
                        else:
                            SVRP_CONFIG[key] = val
                        self.send_message(message['chat']['id'],
                            f"✅ تم تحديث الإعداد!\n\n{key}: {old_val} → {val}",
                            self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'],
                            f"❌ مفتاح غير صالح: {key}", self.admin_keyboard())
                except ValueError:
                    self.send_message(message['chat']['id'],
                        "❌ قيمة غير صحيحة", self.admin_keyboard())
            else:
                self.send_message(message['chat']['id'],
                    "❌ الصيغة: تعديل_استرداد [المفتاح] [القيمة]\nمثال: تعديل_استرداد recovery_multiplier 3.0",
                    self.admin_keyboard())
        elif text == '✅ حفظ الشركة':
            # التعامل مع حفظ الشركة - تنفيذ مباشر
            if user_id in self.user_states and self.user_states[user_id] == 'confirming_company':
                if user_id in self.temp_company_data:
                    company_data = self.temp_company_data[user_id]
                    company_id = str(int(datetime.now().timestamp()))
                    
                    try:
                        # حفظ الشركة في الملف مع الأيقونة والعنوان
                        icon = company_data.get('icon', '🏢')
                        address = company_data.get('address', '')
                        with open('companies.csv', 'a', newline='', encoding='utf-8-sig') as f:
                            writer = csv.writer(f)
                            writer.writerow([company_id, company_data['name'], company_data['type'], company_data['details'], 'active', icon, address])
                        
                        success_msg = f"""🎉 تم إضافة الشركة بنجاح!

🆔 المعرف: {company_id}
🏢 الاسم: {company_data['name']}
⚡ النوع: {company_data['type_display']}
📋 التفاصيل: {company_data['details']}

الشركة متاحة الآن للعملاء ✅"""
                        
                        self.send_message(chat_id, success_msg, self.admin_keyboard())
                        
                        # تنظيف البيانات المؤقتة
                        del self.user_states[user_id]
                        del self.temp_company_data[user_id]
                        
                    except Exception as e:
                        self.send_message(chat_id, f"❌ فشل في حفظ الشركة: {str(e)}", self.admin_keyboard())
                else:
                    self.send_message(chat_id, "❌ لا توجد بيانات شركة محفوظة", self.admin_keyboard())
            else:
                self.send_message(chat_id, "❌ لا توجد شركة للحفظ. ابدأ بإضافة شركة جديدة أولاً.", self.admin_keyboard())
        elif text == '✅ حفظ التغييرات':
            # التعامل مع حفظ تغييرات الشركة
            if user_id in self.user_states and self.user_states[user_id] == 'editing_company_menu':
                self.save_company_changes(message)
            else:
                self.send_message(chat_id, "❌ لا توجد تغييرات للحفظ. ابدأ بتعديل شركة أولاً.", self.admin_keyboard())
        elif text in ['❌ إلغاء', 'إلغاء', 'الغاء']:
            # إلغاء العملية الحالية
            if user_id in self.user_states:
                del self.user_states[user_id]
            if user_id in self.edit_company_data:
                del self.edit_company_data[user_id]
            self.send_message(chat_id, "❌ تم إلغاء العملية", self.admin_keyboard())
        else:
            self.send_message(message['chat']['id'], "أمر غير مفهوم. استخدم الأزرار أو الأوامر الصحيحة.", self.main_keyboard('ar', user_id))
    
    def show_pending_requests(self, message):
        """عرض الطلبات المعلقة للأدمن — تشمل pending و pending_code_verification"""
        pending_text = "📋 الطلبات المعلقة:\n\n"
        found_pending = False
        copy_commands = []
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['status'] in ('pending', 'pending_code_verification'):
                        found_pending = True
                        type_emoji = "💰" if row['type'] == 'deposit' else "💸"
                        status_tag = "⏳" if row['status'] == 'pending' else "🔐"
                        
                        pending_text += f"{type_emoji} {status_tag} {row['id']}\n"
                        pending_text += f"👤 {row['name']} ({row['customer_id']})\n"
                        pending_text += f"🏢 {row['company']}\n"
                        pending_text += f"💳 {row['wallet_number']}\n"
                        pending_text += f"{self.fmt_amount(row['amount'], row.get('type', 'deposit'))}\n"
                        
                        if row.get('exchange_address'):
                            pending_text += f"📍 {row['exchange_address']}\n"
                        
                        if row.get('admin_note') and row['status'] == 'pending_code_verification':
                            pending_text += f"🔐 الكود: {row['admin_note']}\n"
                        
                        pending_text += f"📅 {row['date']}\n"
                        
                        # إضافة أوامر النسخ السريع
                        pending_text += f"\n📋 أوامر سريعة:\n"
                        pending_text += f"✅ `موافقة {row['id']}`\n"
                        pending_text += f"❌ `رفض {row['id']} السبب_هنا`\n"
                        pending_text += f"▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n\n"
                        
                        copy_commands.append({
                            'id': row['id'],
                            'approve': f"موافقة {row['id']}",
                            'reject': f"رفض {row['id']} السبب_هنا"
                        })
        except:
            pass
        
        if not found_pending:
            pending_text += "✅ لا توجد طلبات معلقة"
        else:
            # إضافة قسم الأوامر الجاهزة للنسخ
            pending_text += "\n🔥 **أوامر جاهزة للنسخ المباشر:**\n\n"
            
            for cmd in copy_commands:
                pending_text += f"**{cmd['id']}:**\n"
                pending_text += f"✅ `{cmd['approve']}`\n"
                pending_text += f"❌ `{cmd['reject']}`\n\n"
            
            pending_text += "💡 **طرق سهلة للاستخدام:**\n"
            pending_text += "• انقر على الأمر واختر 'نسخ'\n"
            pending_text += "• أو اكتب مباشرة: موافقة + رقم المعاملة\n"
            pending_text += "• للرفض: رفض + رقم المعاملة + السبب\n\n"
            
            pending_text += "📝 **أمثلة أوامر الموافقة:**\n"
            pending_text += "`موافقة` أو `موافق` أو `تأكيد` أو `نعم`\n\n"
            
            pending_text += "📝 **أمثلة أوامر الرفض:**\n"
            pending_text += "`رفض` أو `لا` أو `مرفوض` أو `إلغاء`"
        
        self.send_message(message['chat']['id'], pending_text, self.admin_keyboard())
    
    def approve_transaction(self, message, trans_id):
        """الموافقة على معاملة"""
        success = self.update_transaction_status(trans_id, 'approved', '', str(message['from']['id']))
        
        if success:
            # إشعار العميل الذكي
            transaction = self.get_transaction(trans_id)
            if transaction:
                customer_telegram_id = transaction.get('telegram_id')
                if customer_telegram_id:
                    user = self.find_user(customer_telegram_id)
                    lang = user.get('language', 'ar') if user else 'ar'
                    customer_msg = self.tr('transaction_approved', lang, trans_id=trans_id)
                    self.notify_user(int(customer_telegram_id), customer_msg, 'transaction_approved')
                    
                    # 💎 تعويض 100%: تحديث المهام + تفعيل أرصدة الأصدقاء + زيادة الرهان
                    if self.svrp:
                        try:
                            amount = float(transaction.get('amount', 0) or 0)
                            trans_type = transaction.get('type', '')
                            if trans_type == 'deposit':
                                self.svrp.update_task_progress(customer_telegram_id, 'deposit_count', 1)
                                self.svrp.update_task_progress(customer_telegram_id, 'deposit_amount', amount)
                                # تفعيل أرصدة الأصدقاء (إذا كان هذا المستخدم مُحالاً)
                                self.svrp.activate_friend_credits(customer_telegram_id)
                            # زيادة عداد الرهان
                            self.svrp.increment_wagering(customer_telegram_id)
                            # تحديث مجموعة المستخدم
                            self.svrp.update_user_group(customer_telegram_id)
                        except Exception as e:
                            logger.error(f"خطأ في تحديث تعويض 100%: {e}")
            
            self.send_message(message['chat']['id'], self.tr('transaction_approved', 'ar', trans_id=trans_id), self.admin_keyboard())
        else:
            self.send_message(message['chat']['id'], f"❌ {trans_id}", self.admin_keyboard())
    
    def reject_transaction(self, message, trans_id, reason):
        """رفض معاملة"""
        success = self.update_transaction_status(trans_id, 'rejected', reason, str(message['from']['id']))
        
        if success:
            # إشعار العميل
            transaction = self.get_transaction(trans_id)
            if transaction:
                customer_telegram_id = transaction.get('telegram_id')
                if customer_telegram_id:
                    user = self.find_user(customer_telegram_id)
                    lang = user.get('language', 'ar') if user else 'ar'
                    customer_msg = self.tr('transaction_rejected', lang, trans_id=trans_id, reason=reason)
                    self.notify_user(int(customer_telegram_id), customer_msg, 'transaction_rejected')
                    
                    # 💎 تعويض 100%: تشغيل الاسترداد عند رفض السحب
                    if self.svrp and transaction.get('type') == 'withdraw':
                        try:
                            amount = float(transaction.get('amount', 0) or 0)
                            if amount > 0:
                                result, err = self.svrp.trigger_recovery(
                                    customer_telegram_id, trans_id, amount,
                                    transaction.get('currency', 'SAR')
                                )
                                if result:
                                    credit_str = f"{result['total_credit']:.2f} {result['currency']}"
                                    svrp_msg = (
                                        f"{self.tr('svrp_recovery_activated', lang)}\n\n"
                                        f"{self.fmt_success(self.tr('svrp_recovery_credit', lang) + ': ' + credit_str)}\n"
                                        f"📥 {self.tr('svrp_recovery_keep', lang)}: {result['keep_amount']:.2f}\n"
                                        f"📤 {self.tr('svrp_recovery_share', lang)}: {result['share_amount']:.2f}\n\n"
                                        f"📋 {self.tr('svrp_recovery_requirements', lang)}:\n"
                                        f"• {self.tr('svrp_recovery_complete_tx', lang, n=result['wagering_required'])}\n"
                                        f"• {self.tr('svrp_recovery_expires', lang)}: {result['expires_at']}\n\n"
                                        f"{self.tr('svrp_recovery_share_hint', lang)}"
                                    )
                                    self.notify_user(int(customer_telegram_id), svrp_msg, 'svrp_recovery')
                        except Exception as e:
                            logger.error(f"خطأ في تشغيل تعويض 100%: {e}")
            
            self.send_message(message['chat']['id'], self.tr('transaction_rejected', 'ar', trans_id=trans_id, reason=reason), self.admin_keyboard())
        else:
            self.send_message(message['chat']['id'], f"❌ {trans_id}", self.admin_keyboard())
    
    def update_transaction_status(self, trans_id, new_status, note='', admin_id=''):
        """تحديث حالة المعاملة"""
        transactions = []
        success = False
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == trans_id:
                        row['status'] = new_status
                        if note:
                            row['admin_note'] = note
                        if admin_id:
                            row['processed_by'] = admin_id
                        success = True
                    transactions.append(row)
            
            if success:
                with open('transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    fieldnames = [
                        'id',
                        'customer_id',
                        'telegram_id',
                        'name',
                        'type',
                        'company',
                        'wallet_number',
                        'amount',
                        'exchange_address',
                        'status',
                        'date',
                        'admin_note',
                        'processed_by',
                        'currency'
                    ]
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(transactions)

        except:
            pass
        
        return success
    
    def get_transaction(self, trans_id):
        """جلب معاملة محددة"""
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == trans_id:
                        return row
        except:
            pass
        return None
    
    def show_detailed_stats(self, message):
        """عرض إحصائيات مفصلة"""
        stats_text = "📊 إحصائيات النظام الشاملة\n\n"
        
        # إحصائيات المستخدمين
        total_users = 0
        banned_users = 0
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_users += 1
                    if row.get('is_banned') == 'yes':
                        banned_users += 1
        except:
            pass
        
        # إحصائيات المعاملات
        total_transactions = 0
        pending_count = 0
        code_verification_count = 0
        approved_count = 0
        rejected_count = 0
        total_deposit_amount = 0
        total_withdraw_amount = 0
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_transactions += 1
                    amount = float(row.get('amount', 0) or 0)
                    
                    if row['status'] == 'pending':
                        pending_count += 1
                    elif row['status'] == 'pending_code_verification':
                        code_verification_count += 1
                    elif row['status'] == 'approved':
                        approved_count += 1
                        if row['type'] == 'deposit':
                            total_deposit_amount += amount
                        else:
                            total_withdraw_amount += amount
                    elif row['status'] == 'rejected':
                        rejected_count += 1
        except:
            pass
        
        # إحصائيات الشكاوى
        total_complaints = 0
        try:
            with open('complaints.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                total_complaints = sum(1 for row in reader)
        except:
            pass
        
        stats_text += f"👥 المستخدمون:\n"
        stats_text += f"├ الإجمالي: {total_users}\n"
        stats_text += f"├ النشطون: {total_users - banned_users}\n"
        stats_text += f"└ المحظورون: {banned_users}\n\n"
        
        stats_text += f"💰 المعاملات:\n"
        stats_text += f"├ الإجمالي: {total_transactions}\n"
        stats_text += f"├ معلقة: {pending_count}\n"
        stats_text += f"├ بانتظار تأكيد الكود: {code_verification_count}\n"
        stats_text += f"├ مُوافق عليها: {approved_count}\n"
        stats_text += f"└ مرفوضة: {rejected_count}\n\n"
        
        stats_text += f"💵 المبالغ المُوافق عليها:\n"
        stats_text += f"├ الإيداعات: {total_deposit_amount:,.0f}\n"
        stats_text += f"├ السحوبات: {total_withdraw_amount:,.0f}\n"
        stats_text += f"└ الفرق: {total_deposit_amount - total_withdraw_amount:,.0f}\n\n"
        
        stats_text += f"📨 الشكاوى: {total_complaints}\n\n"
        stats_text += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        self.send_message(message['chat']['id'], stats_text, self.admin_keyboard())
    
    def add_company_simple_with_display(self, message, text):
        """إضافة شركة مع عرض القائمة المحدثة"""
        result = self.add_company_simple(message, text)
        if result:
            # عرض قائمة الشركات المحدثة فوراً
            self.show_companies_management_enhanced(message)
    
    def add_company_simple(self, message, text):
        """إضافة شركة بصيغة مبسطة"""
        # تنسيق: اضافة_شركة اسم نوع تفاصيل
        parts = text.replace('اضافة_شركة ', '').split(' ', 2)
        if len(parts) < 3:
            help_text = """❌ طريقة إضافة الشركة:

📝 اكتب بالضبط:
اضافة_شركة اسم_الشركة نوع_الخدمة التفاصيل

🔹 أنواع الخدمة (بالإنجليزي):
• ايداع → deposit
• سحب → withdraw  
• ايداع وسحب → both

📋 أمثلة صحيحة:
▫️ اضافة_شركة مدى both محفظة_رقمية
▫️ اضافة_شركة البنك_الأهلي deposit حساب_بنكي
▫️ اضافة_شركة فودافون_كاش withdraw محفظة_الكترونية
▫️ اضافة_شركة STC_Pay both خدمات_دفع"""
            
            self.send_message(message['chat']['id'], help_text, self.admin_keyboard())
            return
        
        company_name = parts[0].replace('_', ' ')
        service_type = parts[1].lower()
        details = parts[2].replace('_', ' ')
        
        # قبول الكلمات العربية وتحويلها
        if service_type in ['ايداع', 'إيداع']:
            service_type = 'deposit'
        elif service_type in ['سحب']:
            service_type = 'withdraw'
        elif service_type in ['كلاهما', 'الكل', 'ايداع_وسحب']:
            service_type = 'both'
        
        if service_type not in ['deposit', 'withdraw', 'both']:
            error_text = """❌ نوع الخدمة خطأ!

✅ الأنواع المقبولة:
• deposit (للإيداع فقط)
• withdraw (للسحب فقط)
• both (للإيداع والسحب)

أو بالعربي:
• ايداع → deposit
• سحب → withdraw
• كلاهما → both

مثال صحيح:
اضافة_شركة مدى both محفظة_رقمية"""
            
            self.send_message(message['chat']['id'], error_text, self.admin_keyboard())
            return
        
        # إنشاء معرف جديد
        company_id = str(int(datetime.now().timestamp()))
        
        try:
            # التأكد من وجود الملف وإنشاؤه إذا لم يكن موجوداً
            file_exists = True
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    pass
            except FileNotFoundError:
                file_exists = False
            
            # إنشاء الملف مع الرؤوس إذا لم يكن موجوداً
            if not file_exists:
                with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['id', 'name', 'type', 'details', 'is_active'])
            
            # إضافة الشركة الجديدة
            with open('companies.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                company_icon = self.normalize_icon(service_type, default='🏢')
                writer.writerow([company_id, company_name, service_type, details, 'active', company_icon, ''])
            
            # رسالة النجاح مع عرض قائمة الشركات المحدثة
            success_msg = f"""✅ تم إضافة الشركة بنجاح!

🆔 {company_id}
{company_icon} {company_name}
⚡ {service_type}
📋 {details}"""
            
            # عرض جميع الشركات
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    company_count = 0
                    for row in reader:
                        company_count += 1
                        status = "✅" if row.get('is_active') == 'active' else "❌"
                        type_display = {'deposit': 'إيداع', 'withdraw': 'سحب', 'both': 'الكل'}.get(row['type'], row['type'])
                        success_msg += f"\n{status} {row['name']} (ID: {row['id']}) - {type_display}"
                    
                    success_msg += f"\n\n📊 إجمالي الشركات: {company_count}"
            except:
                pass
            
            self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
            return True
            
        except Exception as e:
            self.send_message(message['chat']['id'], f"❌ فشل في إضافة الشركة: {str(e)}", self.admin_keyboard())
            return False
    
    def update_address_simple(self, message, new_address):
        """تحديث عنوان الصرافة"""
        try:
            with open('exchange_addresses.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'address', 'is_active'])
                writer.writerow(['1', new_address, 'yes'])
            
            self.send_message(message['chat']['id'], f"✅ تم تحديث عنوان الصرافة:\n{new_address}", self.admin_keyboard())
        except Exception as e:
            self.send_message(message['chat']['id'], f"❌ فشل في تحديث العنوان: {str(e)}", self.admin_keyboard())
    
    # ==================== نظام المطابقة ====================

    def show_user_notifications_panel(self, message):
        """عرض إشعارات المستخدم"""
        user_id = message['from']['id']
        user = self.find_user(user_id)
        if not user:
            return
        lang = user.get('language', 'ar')
        
        notifs = self.get_user_notifications(user_id, 10)
        
        if not notifs:
            self.send_message(message['chat']['id'], self.tr('notif_empty', lang), self.main_keyboard(lang, user_id))
            return
        
        type_icons = {
            'new_deposit': '💰', 'new_withdraw': '💸', 'new_complaint': '📨',
            'new_match': '🔄', 'dispute': '⚖️', 'code_verification': '🔐',
            'transaction_approved': '✅', 'transaction_rejected': '❌',
            'code_verified': '✅', 'code_rejected': '❌', 'general': '📋'
        }
        
        notif_text = f"{self.tr('notif_recent', lang)}\n\n"
        for n in reversed(notifs):
            icon = type_icons.get(n.get('type', ''), '📋')
            notif_text += f"{icon} {n.get('timestamp', '')}\n{n.get('message_preview', '')}\n\n"
        
        self.send_message(message['chat']['id'], notif_text, self.main_keyboard(lang, user_id))

    def start_matching_flow(self, message):
        """بدء تدفق المطابقة — شرح + قواعد + موافقة"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        lang = user.get('language', 'ar')

        # فحص وجود مطابقة نشطة
        if self.match_manager:
            active_match = self.match_manager.get_match_by_user(message['from']['id'])
            if active_match:
                self.send_message(message['chat']['id'],
                    f"⚠️ لديك مطابقة نشطة: {active_match['id']}\n\nاكمل العملية الحالية أولاً.",
                    self.main_keyboard(lang, message['from']['id']))
                return

        if lang == 'ar':
            text = (
                "🔄 <b>نظام المطابقة P2P</b>\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📌 <b>كيف يعمل النظام؟</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "1️⃣ اختر نوع العملية (إيداع أو سحب)\n"
                "2️⃣ حدد الشركة ووسيلة الدفع\n"
                "3️⃣ أرسل بياناتك (رقم محفظتك + معرف حسابك)\n"
                "4️⃣ انتظر المطابقة — سيصلك إشعار\n"
                "5️⃣ الأدمن يرسل لك رقم المحفظة للتحويل\n"
                "6️⃣ حوّل المال ← اضغط <b>تم الإرسال</b>\n"
                "7️⃣ الأدمن يراجع ويوافق/يرفض\n\n"
                "⚠️ <b>تحذيرات:</b>\n"
                "• لا تُرسل المال قبل استلام بيانات المحفظة من الأدمن\n"
                "• التقييم إلزامي بعد كل عملية\n"
                "• في حالة نزاع → اضغط <b>🆘 دعم</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "هل توافق على القواعد؟"
            )
        else:
            text = (
                "🔄 <b>P2P Matching System</b>\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📌 <b>How it works:</b>\n"
                "1️⃣ Choose operation type (deposit or withdraw)\n"
                "2️⃣ Select company and payment method\n"
                "3️⃣ Send your data (wallet number + account ID)\n"
                "4️⃣ Wait for match — you'll be notified\n"
                "5️⃣ Admin sends wallet number for transfer\n"
                "6️⃣ Send money ← press <b>Sent</b>\n"
                "7️⃣ Admin reviews and approves/rejects\n\n"
                "⚠️ <b>Warnings:</b>\n"
                "• Do NOT send money before receiving wallet details\n"
                "• Rating is mandatory after each operation\n"
                "• In case of dispute → press <b>🆘 Support</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Do you agree to the rules?"
            )

        inline_btns = [
            [{'text': '✅ موافقة', 'callback_data': 'match_agree'},
             {'text': '🔙 العودة', 'callback_data': 'match_cancel'}]
        ]
        self.send_inline_message(message['chat']['id'], text, inline_btns)

    def handle_matching_flow(self, message):
        """معالجة تدفق المطابقة"""
        user_id = message['from']['id']
        state = self.user_states.get(user_id, '')
        text = message.get('text', '').strip()
        user = self.find_user(user_id)
        if not user:
            return
        lang = user.get('language', 'ar')

        # معالجة إدخال بيانات المطابقة (مبلغ + محفظة + معرف)
        if isinstance(state, dict) and state.get('step') == 'match_enter_data':
            text_msg = message.get('text', '').strip()

            if text_msg in ['❌ إلغاء', 'إلغاء', 'الغاء', '🔙', '🏠 القائمة الرئيسية']:
                if user_id in self.user_states: del self.user_states[user_id]
                self.handle_start(message)
                return

            lines = [l.strip() for l in text_msg.split('\n') if l.strip()]
            if len(lines) < 3:
                self.send_message(chat_id,
                    "❌ يجب إرسال 3 أسطر:\n\n"
                    "1️⃣ المبلغ\n"
                    "2️⃣ رقم محفظتك\n"
                    "3️⃣ معرف حسابك\n\n"
                    "💡 مثال:\n<code>500\n0501234567\nID-789</code>")
                return

            try:
                amount = float(lines[0])
                if amount <= 0:
                    self.send_message(chat_id, "❌ المبلغ يجب أن يكون أكبر من صفر")
                    return
            except ValueError:
                self.send_message(chat_id, "❌ المبلغ غير صحيح (السطر الأول)")
                return

            wallet_number = lines[1]
            account_id = lines[2]

            if len(wallet_number) < 5:
                self.send_message(chat_id, "❌ رقم المحفظة قصير (السطر الثاني)")
                return
            if len(account_id) < 2:
                self.send_message(chat_id, "❌ معرف الحساب قصير (السطر الثالث)")
                return

            # إنشاء طلب المطابقة
            req_id, error = self.match_manager.create_match_request(
                user_id, user.get('customer_id', ''), state['type'],
                amount, user.get('currency', 'SAR'),
                state['company_id'], state['company_name'], ''
            )

            if error:
                self.send_message(chat_id, f"❌ {error}", self.main_keyboard(lang, user_id))
                del self.user_states[user_id]
                return

            # البحث عن مطابقة
            request = self.match_manager.get_active_request_by_user(user_id)
            if request:
                match = self.match_manager.find_match(request)
                if match:
                    match_id = self.match_manager.create_match(request, match)
                    self._notify_match_created(match_id)
                    del self.user_states[user_id]
                    return

            # لا توجد مطابقة — إشعار العميل + الأدمن
            type_ar = 'إيداع' if state['type'] == 'deposit' else 'سحب'
            self.send_message(chat_id,
                f"⏳ <b>تم إنشاء طلبك</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{'💵' if state['type'] == 'deposit' else '💸'} النوع: <b>{type_ar}</b>\n"
                f"💰 المبلغ: <b>{amount}</b>\n"
                f"🏢 الشركة: <b>{state['company_name']}</b>\n"
                f"💳 المحفظة: <code>{wallet_number}</code>\n"
                f"🆔 معرف الحساب: <code>{account_id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"⏳ جارٍ البحث عن مطابقة...\n"
                f"سيتم إشعارك فور العثور على طرف آخر.",
                self.main_keyboard(lang, user_id))

            # إشعار الأدمن
            for admin_id in self.admin_ids:
                try:
                    opposite_type = 'سحب' if state['type'] == 'deposit' else 'إيداع'
                    admin_msg = (
                        f"🔔 <b>طلب مطابقة معلق</b>\n\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"👤 العميل: <code>{user_id}</code> ({user.get('name', '')})\n"
                        f"{'💵' if state['type'] == 'deposit' else '💸'} النوع: <b>{type_ar}</b>\n"
                        f"🔄 يبحث عن: <b>{opposite_type}</b>\n"
                        f"💰 المبلغ: <b>{amount}</b>\n"
                        f"🏢 الشركة: <b>{state['company_name']}</b>\n"
                        f"💳 المحفظة: <code>{wallet_number}</code>\n"
                        f"🆔 معرف الحساب: <code>{account_id}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━\n\n"
                        f"يمكنك أن تكون الطرف الآخر:"
                    )
                    inline_btns = [
                        [{'text': f'✅ أنا الطرف الآخر ({opposite_type})', 'callback_data': f'match_admin_join_{request["id"]}'},
                         {'text': '⏳ انتظار', 'callback_data': f'match_admin_wait_{request["id"]}'}]
                    ]
                    self.send_inline_message(admin_id, admin_msg, inline_btns)
                except Exception as e:
                    logger.error(f"خطأ في إشعار الأدمن بطلب المطابقة: {e}")

            del self.user_states[user_id]
            return

        # معالجة قديمة — اختيار النوع (يُترك للتوافق الخلفي)
        if state == 'match_select_type':
            if text == '💰 مطابقة إيداع':
                match_type = 'deposit'
            elif text == '💸 مطابقة سحب':
                match_type = 'withdraw'
            else:
                return

            # حفظ النوع وطلب المبلغ
            self.user_states[user_id] = {'step': 'match_amount', 'type': match_type}
            self.send_message(message['chat']['id'], "💰 أدخل المبلغ:")
            return

        # إدخال المبلغ
        if isinstance(state, dict) and state.get('step') == 'match_amount':
            amount = self.validate_amount(text)
            if amount is None:
                self.send_message(message['chat']['id'], "❌ مبلغ غير صحيح. أدخل رقماً:")
                return

            state['amount'] = amount
            state['step'] = 'match_company'

            # عرض الشركات
            companies = self.get_companies('both')
            if not companies:
                self.send_message(message['chat']['id'], "❌ لا توجد شركات متاحة")
                return

            keyboard = []
            for c in companies:
                icon = c.get('icon', '🏢') or '🏢'
                keyboard.append([{'text': f"{icon} {c['name']}"}])
            keyboard.append([{'text': self.tr('main_menu', lang)}])

            self.send_message(message['chat']['id'], "🏢 اختر الشركة:",
                {'keyboard': keyboard, 'resize_keyboard': True, 'one_time_keyboard': True})
            self.user_states[user_id] = state
            return

        # اختيار الشركة
        if isinstance(state, dict) and state.get('step') == 'match_company':
            company_name = text
            for emoji in ['🏢', '🏦', '📡', '📱', '💳', '👛', '💵', '🔄', '🏷️', '⭐', '🚀', '🏬', '🌐', '🥇', '🎁']:
                if company_name.startswith(emoji):
                    company_name = company_name[len(emoji):].strip()
                    break

            companies = self.get_companies('both')
            selected = None
            for c in companies:
                if c['name'] == company_name:
                    selected = c
                    break

            if not selected:
                self.send_message(message['chat']['id'], "❌ شركة غير صحيحة")
                return

            state['company_id'] = selected['id']
            state['company_name'] = selected['name']
            state['payment_method_id'] = ''

            # إنشاء طلب المطابقة
            req_id, error = self.match_manager.create_match_request(
                user_id, user['customer_id'], state['type'],
                state['amount'], user.get('currency', 'SAR'),
                selected['id'], selected['name'], '')

            if error:
                self.send_message(message['chat']['id'], f"❌ {error}", self.main_keyboard(lang, user_id))
                del self.user_states[user_id]
                return

            # البحث عن مطابقة
            request = self.match_manager.get_active_request_by_user(user_id)
            if request:
                match = self.match_manager.find_match(request)
                if match:
                    # مطابقة موجودة!
                    match_id = self.match_manager.create_match(request, match)
                    self._notify_match_created(match_id)
                    del self.user_states[user_id]
                    return

            # لا توجد مطابقة — إشعار الأدمن + إبلاغ العميل
            req_type_ar = 'إيداع' if state['type'] == 'deposit' else 'سحب'
            self.send_message(message['chat']['id'],
                f"⏳ <b>تم إنشاء طلبك</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{'💵' if state['type'] == 'deposit' else '💸'} النوع: <b>{req_type_ar}</b>\n"
                f"💰 المبلغ: <b>{state['amount']}</b>\n"
                f"🏢 الشركة: <b>{selected['name']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"⏳ جارٍ البحث عن مطابقة...\n"
                f"سيتم إشعارك فور العثور على طرف آخر.",
                self.main_keyboard(lang, user_id))

            # إشعار جميع الأدمن بطلب المطابقة المعلق
            for admin_id in self.admin_ids:
                try:
                    opposite_type = 'سحب' if state['type'] == 'deposit' else 'إيداع'
                    admin_msg = (
                        f"🔔 <b>طلب مطابقة معلق</b>\n\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"👤 العميل: <code>{user_id}</code> ({user.get('name', '')})\n"
                        f"{'💵' if state['type'] == 'deposit' else '💸'} النوع: <b>{req_type_ar}</b>\n"
                        f"🔄 يبحث عن: <b>{opposite_type}</b>\n"
                        f"💰 المبلغ: <b>{state['amount']}</b>\n"
                        f"🏢 الشركة: <b>{selected['name']}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n\n"
                        f"يمكنك أن تكون الطرف الآخر في هذه المطابقة:"
                    )
                    inline_btns = [
                        [{'text': f'✅ أنا الطرف الآخر ({opposite_type})', 'callback_data': f'match_admin_join_{request["id"]}'},
                         {'text': '⏳ انتظار', 'callback_data': f'match_admin_wait_{request["id"]}'}]
                    ]
                    self.send_inline_message(admin_id, admin_msg, inline_btns)
                except Exception as e:
                    logger.error(f"خطأ في إشعار الأدمن بطلب المطابقة: {e}")

            del self.user_states[user_id]
            return

        # إدخال كود السحب + معرف الحساب + رقم المحفظة + وسيلة الدفع
        if isinstance(state, dict) and state.get('step') == 'match_enter_code':
            # تقسيم الرسالة إلى أسطر
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            if len(lines) < 4:
                self.send_message(message['chat']['id'],
                    "❌ يجب إرسال 4 أسطر:\n\n1️⃣ كود السحب\n2️⃣ معرف حسابك (ID)\n3️⃣ رقم محفظتك\n4️⃣ وسيلة الدفع\n\n💡 مثال:\nABC123\nID-789\n0501234567\nحساب بنكي")
                return

            code = self.sanitize_input(lines[0])
            account_id = self.sanitize_input(lines[1])
            wallet_number = self.sanitize_input(lines[2])
            payment_method_name = self.sanitize_input(lines[3])

            if len(code) < 3:
                self.send_message(message['chat']['id'], "❌ الكود قصير جداً. السطر الأول غير صحيح:")
                return
            if len(account_id) < 2:
                self.send_message(message['chat']['id'], "❌ معرف الحساب قصير جداً. السطر الثاني غير صحيح:")
                return
            if len(wallet_number) < 5:
                self.send_message(message['chat']['id'], "❌ رقم المحفظة قصير جداً. السطر الثالث غير صحيح:")
                return
            if len(payment_method_name) < 2:
                self.send_message(message['chat']['id'], "❌ وسيلة الدفع غير واضحة. السطر الرابع غير صحيح:")
                return

            # إزالة أيقونة وسيلة الدفع إن وجدت
            for emoji in ['💳', '🏦', '📱', '👛', '💵', '📡', '🏷️']:
                if payment_method_name.startswith(emoji):
                    payment_method_name = payment_method_name[len(emoji):].strip()
                    break

            match_id = state['match_id']

            # حفظ الكود + البيانات في المطابقة
            combined_code = f"{code} | ID:{account_id} | Wallet:{wallet_number} | Method:{payment_method_name}"
            self.match_manager.set_confirmation_code(match_id, combined_code)

            # إشعار الإدمن فقط (لا يصل للطرف الآخر)
            match = self.match_manager.get_match_by_id(match_id)
            for admin_id in self.admin_ids:
                try:
                    admin_msg = (
                        f"🔐 طلب سحب جديد — مطابقة\n\n"
                        f"🆔 المطابقة: {match_id}\n"
                        f"💰 المبلغ: {match['amount']} {match['currency']}\n"
                        f"🏢 الشركة: {match['company_name']}\n\n"
                        f"🔑 كود السحب: {code}\n"
                        f"🆔 معرف الحساب: {account_id}\n"
                        f"💳 رقم المحفظة: {wallet_number}\n"
                        f"📋 وسيلة الدفع: {payment_method_name}\n\n"
                        f"بانتظار تأكيدك"
                    )
                    inline_btns = [
                        [{'text': '✅ تأكيد الكود', 'callback_data': f'match_verify_{match_id}'},
                         {'text': '❌ رفض الكود', 'callback_data': f'match_reject_code_{match_id}'}]
                    ]
                    self.send_inline_message(admin_id, admin_msg, inline_btns)
                except:
                    pass

            # إشعار الساحب أن البيانات تم إرسالها
            self.send_message(message['chat']['id'],
                "✅ تم إرسال بياناتك للتحقق. سيتم إشعارك فور التأكيد.\n\n🔑 الكود: " + code + "\n🆔 ID: " + account_id + "\n💳 المحفظة: " + wallet_number + "\n📋 الوسيلة: " + payment_method_name,
                self.main_keyboard(lang, user_id))
            del self.user_states[user_id]
            return

        # دردشة
        if isinstance(state, dict) and state.get('step') == 'chatting':
            match_id = state['match_id']
            result = self.match_manager.send_chat_message(match_id, user_id, text)
            if result:
                # توجيه الرسالة للطرف الآخر
                other_lang = 'ar'  # افتراضي
                other_user = self.find_user(result['receiver_id'])
                if other_user:
                    other_lang = other_user.get('language', 'ar')

                chat_keyboard = {
                    'keyboard': [
                        [{'text': '🆘 دعم'}, {'text': '✅ تأكيد'}],
                        [{'text': self.tr('main_menu', other_lang)}]
                    ],
                    'resize_keyboard': True
                }
                self.send_message(result['receiver_id'],
                    f"💬 {result['sender_alias']}:\n{text}", chat_keyboard)
            return

        # تقييم
        if isinstance(state, dict) and state.get('step') == 'rating':
            try:
                rating = int(text)
                if rating < 1 or rating > 5:
                    raise ValueError()
            except (ValueError, TypeError):
                self.send_message(message['chat']['id'], "❌ أدخل رقم من 1 إلى 5:")
                return

            self.match_manager.rate_user(state['match_id'], user_id, rating)
            self.send_message(message['chat']['id'], "✅ شكراً لتقييمك!", self.main_keyboard(lang, user_id))
            del self.user_states[user_id]
            return

    def _notify_match_created(self, match_id):
        """إشعار الطرفين بإنشاء مطابقة"""
        match = self.match_manager.get_match_by_id(match_id)
        if not match:
            return

        depositor_id = int(match['depositor_id'])
        withdrawer_id = int(match['withdrawer_id'])

        # إشعار المودع
        dep_user = self.find_user(depositor_id)
        dep_lang = dep_user.get('language', 'ar') if dep_user else 'ar'
        dep_msg = (
            f"✅ تم العثور على مطابقة!\n\n"
            f"🆔 {match_id}\n"
            f"💰 المبلغ: {match['amount']} {match['currency']}\n"
            f"🏢 الشركة: {match['company_name']}\n"
            f"👤 الطرف الآخر: {match['withdrawer_alias']}\n\n"
            f"💡 اكتب رسالة للتواصل مع الطرف الآخر.\n"
            f"أو اضغط ✅ تأكيد للبدء."
        )
        chat_kb = {
            'keyboard': [
                [{'text': '✅ تأكيد البدء'}, {'text': '❌ إلغاء'}],
                [{'text': '🆘 دعم'}]
            ],
            'resize_keyboard': True
        }
        self.send_message(depositor_id, dep_msg, chat_kb)
        self.user_states[depositor_id] = {'step': 'chatting', 'match_id': match_id}

        # إشعار الساحب
        wit_user = self.find_user(withdrawer_id)
        wit_lang = wit_user.get('language', 'ar') if wit_user else 'ar'
        wit_msg = (
            f"✅ تم العثور على مطابقة!\n\n"
            f"🆔 {match_id}\n"
            f"💰 المبلغ: {match['amount']} {match['currency']}\n"
            f"🏢 الشركة: {match['company_name']}\n"
            f"👤 الطرف الآخر: {match['depositor_alias']}\n\n"
            f"💡 اكتب رسالة للتواصل مع الطرف الآخر.\n"
            f"أو اضغط ✅ تأكيد للبدء."
        )
        self.send_message(withdrawer_id, wit_msg, chat_kb)
        self.user_states[withdrawer_id] = {'step': 'chatting', 'match_id': match_id}

        # إشعار الإدمن
        for admin_id in self.admin_ids:
            try:
                admin_msg = (
                    f"🔗 مطابقة جديدة\n\n"
                    f"🆔 {match_id}\n"
                    f"💰 {match['amount']} {match['currency']}\n"
                    f"🏢 {match['company_name']}\n"
                    f"👤 المودع: {match['depositor_alias']}\n"
                    f"👤 الساحب: {match['withdrawer_alias']}"
                )
                self.send_message(admin_id, admin_msg, self.admin_keyboard())
            except:
                pass

    def handle_callback_query(self, callback):
        """معالجة أزرار Inline (داخل الدردشة)"""
        try:
            callback_id = callback.get('id')
            data = callback.get('data', '')
            message = callback.get('message', {})
            chat_id = message.get('chat', {}).get('id')
            user_id = callback.get('from', {}).get('id')
            
            # الرد على الـ callback لإزالة loading
            self.answer_callback(callback_id)
            
            # معالجة الموافقة على معاملة
            if data.startswith('approve_'):
                trans_id = data.replace('approve_', '')
                # محاكاة رسالة الموافقة
                fake_msg = {
                    'chat': {'id': chat_id},
                    'from': {'id': user_id},
                    'text': f'موافقة {trans_id}'
                }
                self.approve_transaction(fake_msg, trans_id)
                # تحديث الرسالة لإزالة الأزرار
                self.edit_message(chat_id, message.get('message_id'), 
                    f"✅ تمت الموافقة على {trans_id}")
                return
            
            # معالجة الرفض
            elif data.startswith('reject_'):
                trans_id = data.replace('reject_', '')
                # طلب سبب الرفض
                self.send_message(chat_id, f"📝 اكتب سبب الرفض لـ {trans_id}:\nأو اكتب 'بدون سبب'")
                self.user_states[user_id] = f'awaiting_reject_reason_{trans_id}'
                return
            
            # تأكيد الكود (للسحب) — يحول المعاملة من pending_code_verification إلى pending
            elif data.startswith('verify_code_'):
                trans_id = data.replace('verify_code_', '')
                # تحديث حالة المعاملة إلى pending (بانتظار المعالجة)
                self.update_transaction_status(trans_id, 'pending', '', str(user_id))
                # إشعار العميل أن الكود تم تأكيده
                trans = self.get_transaction(trans_id)
                if trans:
                    customer_tid = trans.get('telegram_id')
                    if customer_tid:
                        customer_user = self.find_user(customer_tid)
                        lang = customer_user.get('language', 'ar') if customer_user else 'ar'
                        msg = (
                            f"✅ {self.tr('code_verified', lang)}\n\n"
                            f"🆔 {trans_id}\n"
                            f"⏳ {self.tr('processing', lang)}"
                        )
                        self.send_message(customer_tid, msg, self.main_keyboard(lang))
                # تحديث رسالة الأدمن
                self.edit_message(chat_id, message.get('message_id'),
                    f"✅ تم تأكيد الكود لـ {trans_id}\n\nالمعاملة الآن بانتظار المعالجة.\n✅ موافقة | ❌ رفض")
                # إرسال أزرار الموافقة/الرفض الجديدة
                inline_btns = [
                    [{'text': '✅ موافقة', 'callback_data': f'approve_{trans_id}'},
                     {'text': '❌ رفض', 'callback_data': f'reject_{trans_id}'}]
                ]
                self.send_inline_message(chat_id, f"📋 {trans_id} — جاهزة للموافقة", inline_btns)
                return
            
            # رفض الكود (للسحب) — يطلب من العميل إرسال كود جديد
            elif data.startswith('reject_code_'):
                trans_id = data.replace('reject_code_', '')
                trans = self.get_transaction(trans_id)
                if trans:
                    customer_tid = trans.get('telegram_id')
                    if customer_tid:
                        customer_user = self.find_user(customer_tid)
                        lang = customer_user.get('language', 'ar') if customer_user else 'ar'
                        msg = (
                            f"❌ {self.tr('code_rejected', lang)}\n\n"
                            f"🆔 {trans_id}\n"
                            f"📝 {self.tr('enter_confirmation_code', lang)}"
                        )
                        self.send_message(customer_tid, msg, self.main_keyboard(lang))
                    # تحديث حالة المعاملة إلى code_rejected
                    self.update_transaction_status(trans_id, 'code_rejected', 'الكود غير صحيح', str(user_id))
                # تحديث رسالة الأدمن
                self.edit_message(chat_id, message.get('message_id'),
                    f"🔁 تم طلب كود جديد لـ {trans_id}\n\nتم إشعار العميل.")
                return
            
            # عرض تفاصيل المعاملة
            elif data.startswith('details_'):
                trans_id = data.replace('details_', '')
                trans = self.get_transaction(trans_id)
                if trans:
                    details = (
                        f"📋 تفاصيل {trans_id}\n\n"
                        f"👤 {trans.get('name', 'N/A')}\n"
                        f"🏢 {trans.get('company', 'N/A')}\n"
                        f"💰 {trans.get('amount', 'N/A')} {trans.get('currency', '')}\n"
                        f"💳 {trans.get('wallet_number', 'N/A')}\n"
                        f"📊 {trans.get('status', 'N/A')}\n"
                        f"📅 {trans.get('date', 'N/A')}"
                    )
                    self.send_message(chat_id, details)
                return
            
            # تأكيد حفظ الشركة
            elif data == 'confirm_company_save':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': '✅ حفظ الشركة'}
                # استدعاء منطق الحفظ
                if user_id in self.user_states and self.user_states[user_id] == 'confirming_company':
                    if hasattr(self, 'temp_company_data') and user_id in self.temp_company_data:
                        company_data = self.temp_company_data[user_id]
                        company_id = str(int(datetime.now().timestamp()))
                        icon = company_data.get('icon', '🏢')
                        address = company_data.get('address', '')
                        with open('companies.csv', 'a', newline='', encoding='utf-8-sig') as f:
                            writer = csv.writer(f)
                            writer.writerow([company_id, company_data['name'], company_data['type'], 
                                           company_data['details'], 'active', icon, address])
                        self.edit_message(chat_id, message.get('message_id'),
                            f"✅ تم حفظ الشركة: {company_data['name']}")
                        del self.user_states[user_id]
                        del self.temp_company_data[user_id]
                return
            
            # إلغاء حفظ الشركة
            elif data == 'confirm_company_cancel':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                if hasattr(self, 'temp_company_data') and user_id in self.temp_company_data:
                    del self.temp_company_data[user_id]
                self.edit_message(chat_id, message.get('message_id'), "❌ تم الإلغاء")
                return
            
            # تأكيد حذف شركة
            elif data.startswith('confirm_delete_company_'):
                company_id = data.replace('confirm_delete_company_', '')
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': '🗑️ نعم، احذف'}
                self.finalize_company_delete(fake_msg, company_id)
                self.edit_message(chat_id, message.get('message_id'), "✅ تم الحذف")
                return
            
            # إلغاء حذف شركة
            elif data == 'cancel_delete_company':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.edit_message(chat_id, message.get('message_id'), "❌ تم الإلغاء")
                return
            
            # تأكيد طلب السحب (inline button)
            elif data == 'withdraw_confirm':
                # محاكاة ضغط زر التأكيد
                fake_msg = {
                    'chat': {'id': chat_id},
                    'from': {'id': user_id},
                    'text': self.tr('confirm_request', 'ar')
                }
                # استدعاء منطق تأكيد السحب
                state = self.user_states.get(user_id, '')
                if state.startswith('withdraw_final_confirm_'):
                    # استخراج البيانات من الحالة
                    data_part = state.replace('withdraw_final_confirm_', '', 1)
                    parts = data_part.split('_')
                    company_id = parts[0] if len(parts) > 0 else ''
                    confirmation_code = parts[-1] if len(parts) > 4 else ''
                    withdrawal_address = parts[-2] if len(parts) > 4 else ''
                    amount = parts[-3] if len(parts) > 4 else ''
                    wallet_number = parts[-4] if len(parts) > 4 else ''
                    if len(parts) > 5:
                        company_name = '_'.join(parts[1:-4])
                    else:
                        company_name = parts[1] if len(parts) > 1 else ''
                    
                    user = self.find_user(user_id)
                    if user:
                        trans_id = f"WTH{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
                        
                        with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
                            writer = csv.writer(f)
                            writer.writerow([
                                trans_id, user['customer_id'], user['telegram_id'], user['name'],
                                'withdraw', company_name, wallet_number, amount,
                                withdrawal_address, 'pending', datetime.now().strftime('%Y-%m-%d %H:%M'),
                                confirmation_code, '', user_currency
                            ])
                        
                        lang = user.get('language', 'ar')
                        confirmation_text = self.tr('withdraw_success', lang,
                            trans_id=trans_id, name=user['name'], customer_id=user['customer_id'],
                            company_name=company_name, wallet_number=wallet_number,
                            amount=self.fmt_withdraw_amount(amount, user_currency),
                            withdrawal_address=withdrawal_address,
                            confirmation_code=confirmation_code,
                            date=datetime.now().strftime('%Y-%m-%d %H:%M'))
                        
                        self.edit_message(chat_id, message.get('message_id'), confirmation_text)
                        self.send_message(chat_id, self.tr('main_menu', lang), self.main_keyboard(lang, user_id))
                        
                        # إشعار الأدمن
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
                                    f"🔐 {confirmation_code}\n"
                                    f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                                    f"✅ {trans_id}  |  ❌ {trans_id}"
                                )
                                inline_btns = [
                                    [{'text': '✅ موافقة', 'callback_data': f'approve_{trans_id}'},
                                     {'text': '❌ رفض', 'callback_data': f'reject_{trans_id}'}]
                                ]
                                self.send_inline_message(admin_id, admin_notification, inline_btns)
                            except:
                                pass
                        
                        if user_id in self.user_states:
                            del self.user_states[user_id]
                return
            
            # إلغاء طلب السحب (inline button)
            elif data == 'withdraw_cancel':
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                cancel_text = self.tr('withdraw_cancelled', lang)
                self.edit_message(chat_id, message.get('message_id'), cancel_text)
                self.send_message(chat_id, self.tr('choose_service', lang, 
                    name=user.get('name','') if user else '', 
                    customer_id=user.get('customer_id','') if user else ''), 
                    self.main_keyboard(lang, user_id))
                if user_id in self.user_states:
                    del self.user_states[user_id]
                return
            
            # الرد على الشكاوى (inline buttons)
            elif data.startswith('complaint_resolve_'):
                complaint_id = data.replace('complaint_resolve_', '')
                reply_msg = "شكراً لتواصلك معنا. تم حل مشكلتك بنجاح ونعتذر عن أي إزعاج."
                self.save_complaint_reply(complaint_id, reply_msg)
                self.send_complaint_reply_to_customer(complaint_id, reply_msg)
                self.edit_message(chat_id, message.get('message_id'), f"✅ تم حل الشكوى {complaint_id}")
                return
            
            elif data.startswith('complaint_review_'):
                complaint_id = data.replace('complaint_review_', '')
                reply_msg = "نحن نراجع طلبك بعناية وسنرد عليك خلال 24 ساعة. شكراً لصبرك."
                self.save_complaint_reply(complaint_id, reply_msg)
                self.send_complaint_reply_to_customer(complaint_id, reply_msg)
                self.edit_message(chat_id, message.get('message_id'), f"🔍 قيد المراجعة {complaint_id}")
                return
            
            elif data.startswith('complaint_contact_'):
                complaint_id = data.replace('complaint_contact_', '')
                reply_msg = "سنتواصل معك قريباً عبر الهاتف أو الرسائل. شكراً لتواصلك معنا."
                self.save_complaint_reply(complaint_id, reply_msg)
                self.send_complaint_reply_to_customer(complaint_id, reply_msg)
                self.edit_message(chat_id, message.get('message_id'), f"📞 سنتواصل {complaint_id}")
                return
            
            elif data.startswith('complaint_custom_'):
                complaint_id = data.replace('complaint_custom_', '')
                self.send_message(chat_id, f"💡 اكتب ردك المخصص للشكوى {complaint_id}:\n\n⬅️ /cancel للإلغاء")
                self.user_states[user_id] = f'replying_to_complaint_{complaint_id}'
                return
            
            # تأكيد رفض المعاملة (inline)
            elif data.startswith('confirm_reject_'):
                trans_id = data.replace('confirm_reject_', '')
                pending = self.pending_reject_reasons.get(user_id, {})
                reason = pending.get('reason', '') if pending else ''
                if user_id in self.pending_reject_reasons:
                    del self.pending_reject_reasons[user_id]
                if user_id in self.user_states:
                    del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': f'رفض {trans_id} {reason}'}
                self.reject_transaction(fake_msg, trans_id, reason)
                self.edit_message(chat_id, message.get('message_id'), f"❌ تم رفض {trans_id}")
                return
            
            # إلغاء رفض المعاملة
            elif data == 'cancel_reject':
                if user_id in self.pending_reject_reasons:
                    del self.pending_reject_reasons[user_id]
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.edit_message(chat_id, message.get('message_id'), "❌ تم إلغاء الرفض")
                return

            # ==================== 📱 التطبيقات ====================
            elif data == 'app_add_new':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.start_app_wizard(fake_msg)
                return

            elif data == 'app_refresh':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_apps_admin_panel(fake_msg)
                return

            elif data == 'app_back_admin':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.handle_admin_panel(fake_msg)
                return

            # ==================== ✏️ تعديل مسميات الأزرار ====================
            elif data == 'btn_edit_cancel':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.handle_admin_panel(fake_msg)
                return

            # ==================== 💳 وسائل الدفع ====================
            elif data == 'pm_back':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.handle_admin_panel(fake_msg)
                return

            elif data == 'pm_list':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_payment_methods_management(fake_msg)
                return

            elif data == 'pm_add':
                # عرض الشركات لاختيار أي شركة تضاف لها وسيلة
                companies = self.get_companies()
                if not companies:
                    self.send_message(chat_id, "❌ لا توجد شركات. أضف شركة أولاً")
                    return
                inline_btns = []
                for c in companies:
                    icon = c.get('icon', '🏢') or '🏢'
                    inline_btns.append([{'text': f"{icon} {c['name']}", 'callback_data': f'pm_add_company_{c["id"]}'}])
                inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'pm_back'}])
                self.edit_message(chat_id, message.get('message_id'), "➕ <b>إضافة وسيلة دفع</b>\n\nاختر الشركة:")
                self.send_inline_message(chat_id, "اختر الشركة:", inline_btns)
                return

            elif data.startswith('pm_add_company_'):
                company_id = data.replace('pm_add_company_', '')
                company = self.get_company_by_id(company_id)
                company_name = company['name'] if company else 'غير محدد'
                self.edit_message(chat_id, message.get('message_id'),
                    f"➕ <b>إضافة وسيلة دفع — {company_name}</b>\n\n"
                    "📝 أرسل البيانات في رسالة واحدة:\n\n"
                    "1️⃣ اسم الوسيلة\n"
                    "2️⃣ النوع (محفظة/بنك)\n"
                    "3️⃣ رقم الحساب\n"
                    "4️⃣ معلومات إضافية (أو 'بدون')\n"
                    "5️⃣ الأيقونة (أو 'بدون')\n\n"
                    "💡 مثال:\n<code>محفظة STC\nمحفظة إلكترونية\n0501234567\nالبنك الأهلي\n📱</code>")
                self.user_states[user_id] = f'pm_add_wizard_{company_id}_{company_name}'
                return

            elif data.startswith('pm_edit_'):
                method_id = data.replace('pm_edit_', '')
                method = self.get_payment_method_by_id(method_id) if method_id else None
                if not method:
                    self.send_message(chat_id, "❌ الوسيلة غير موجودة")
                    return

                company = self.get_company_by_id(method.get('company_id', ''))
                company_name = company['name'] if company else 'غير محدد'
                status = method.get('status', 'active')
                status_icon = '✅' if status == 'active' else '⏸️'

                text = (
                    f"💳 <b>{method['method_name']}</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🏢 الشركة: {company_name}\n"
                    f"📋 النوع: {method.get('method_type', '')}\n"
                    f"🔢 رقم الحساب: <code>{method.get('account_data', '')}</code>\n"
                    f"💡 معلومات: {method.get('additional_info', '')}\n"
                    f"🖼️ الأيقونة: {method.get('icon', '💳')}\n"
                    f"📊 الحالة: {status_icon} {status}\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    "اختر الإجراء:"
                )
                inline_btns = [
                    [{'text': '✏️ تعديل الاسم', 'callback_data': f'pm_name_{method_id}'},
                     {'text': '🔢 تعديل الحساب', 'callback_data': f'pm_account_{method_id}'}],
                    [{'text': '⏹️ إيقاف' if status == 'active' else '▶️ تشغيل', 'callback_data': f'pm_toggle_{method_id}'}],
                    [{'text': '🗑️ حذف', 'callback_data': f'pm_delete_{method_id}'}],
                    [{'text': '🔙 رجوع', 'callback_data': 'pm_list'}]
                ]
                self.edit_message(chat_id, message.get('message_id'), text)
                self.send_inline_message(chat_id, "اختر:", inline_btns)
                return

            elif data.startswith('pm_toggle_'):
                method_id = data.replace('pm_toggle_', '')
                method = self.get_payment_method_by_id(method_id)
                if method:
                    new_status = 'inactive' if method.get('status') == 'active' else 'active'
                    self.update_payment_method_status(method_id, new_status)
                    action = 'إيقاف' if new_status == 'inactive' else 'تشغيل'
                    self.edit_message(chat_id, message.get('message_id'), f"✅ تم {action} الوسيلة")
                # إعادة عرض القائمة
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_payment_methods_management(fake_msg)
                return

            elif data.startswith('pm_delete_'):
                method_id = data.replace('pm_delete_', '')
                inline_btns = [
                    [{'text': '✅ نعم احذف', 'callback_data': f'pm_confirm_delete_{method_id}'},
                     {'text': '❌ إلغاء', 'callback_data': f'pm_edit_{method_id}'}]
                ]
                self.edit_message(chat_id, message.get('message_id'),
                    "⚠️ <b>تأكيد الحذف</b>\n\nهل أنت متأكد؟")
                self.send_inline_message(chat_id, "حذف وسيلة الدفع:", inline_btns)
                return

            elif data.startswith('pm_confirm_delete_'):
                method_id = data.replace('pm_confirm_delete_', '')
                self.delete_payment_method(method_id)
                self.edit_message(chat_id, message.get('message_id'), "✅ تم حذف الوسيلة")
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_payment_methods_management(fake_msg)
                return

            elif data.startswith('pm_name_'):
                method_id = data.replace('pm_name_', '')
                self.edit_message(chat_id, message.get('message_id'), "✏️ اكتب الاسم الجديد:")
                self.user_states[user_id] = f'pm_input_name_{method_id}'
                return

            elif data.startswith('pm_account_'):
                method_id = data.replace('pm_account_', '')
                self.edit_message(chat_id, message.get('message_id'), "🔢 اكتب رقم الحساب الجديد:")
                self.user_states[user_id] = f'pm_input_account_{method_id}'
                return

            # ==================== ⚙️ الإعدادات ====================
            elif data == 'settings_back':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.handle_admin_panel(fake_msg)
                return

            elif data.startswith('setting_edit_'):
                key = data.replace('setting_edit_', '')
                current = self.get_setting(key) or 'غير محدد'
                self.edit_message(chat_id, message.get('message_id'),
                    f"⚙️ <b>تعديل إعداد</b>\n\n"
                    f"📋 المفتاح: <code>{key}</code>\n"
                    f"📊 القيمة الحالية: <code>{current}</code>\n\n"
                    f"✍️ اكتب القيمة الجديدة:")
                self.user_states[user_id] = f'setting_input_{key}'
                return

            elif data.startswith('btn_edit_') and data != 'btn_edit_cancel':
                idx = int(data.replace('btn_edit_', ''))
                buttons = getattr(self, '_editable_buttons', {}).get(user_id, [])
                if idx >= len(buttons):
                    self.send_message(chat_id, "❌ خطأ في الاختيار")
                    return

                old_label = buttons[idx]
                if not hasattr(self, 'temp_button_label_edit'):
                    self.temp_button_label_edit = {}
                self.temp_button_label_edit[user_id] = {'old': old_label}

                self.edit_message(chat_id, message.get('message_id'),
                    f"✅ <b>تم اختيار الزر:</b>\n<code>{old_label}</code>\n\n"
                    f"📝 اكتب الاسم <b>الجديد</b> (يمكنك تغيير النص والرمز):")
                self.user_states[user_id] = 'enter_new_button_label'
                return

            elif data.startswith('app_delete_'):
                app_id = data.replace('app_delete_', '')
                # تأكيد الحذف
                inline_btns = [
                    [{'text': '✅ نعم، احذف', 'callback_data': f'app_confirm_delete_{app_id}'},
                     {'text': '❌ إلغاء', 'callback_data': 'app_refresh'}]
                ]
                self.edit_message(chat_id, message.get('message_id'),
                    f"⚠️ هل أنت متأكد من حذف التطبيق <code>{app_id}</code>؟")
                self.send_inline_message(chat_id, "🗑️ تأكيد الحذف:", inline_btns)
                return

            elif data.startswith('app_confirm_delete_'):
                app_id = data.replace('app_confirm_delete_', '')
                if self.delete_app_link(app_id):
                    self.edit_message(chat_id, message.get('message_id'),
                        f"✅ تم حذف التطبيق {app_id}")
                else:
                    self.edit_message(chat_id, message.get('message_id'),
                        f"❌ لم يتم العثور على التطبيق {app_id}")
                # إعادة عرض القائمة
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_apps_admin_panel(fake_msg)
                return

            # ==================== 💎 تعويض 100% — أزرار inline ====================

            elif data == 'svrp_main_menu':
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                self.edit_message(chat_id, message.get('message_id'), "🏠 العودة للقائمة الرئيسية")
                welcome = self.tr('choose_service', lang, name=user.get('name', ''), customer_id=user.get('customer_id', '')) if user else ''
                self.send_message(chat_id, welcome, self.main_keyboard(lang, user_id))
                return

            elif data == 'svrp_deposit':
                # إيداع من الرصيد المتاح — يختار شركة مسجل فيها
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                accounts = self.svrp.get_user_company_accounts(user_id)

                if not accounts:
                    self.edit_message(chat_id, message.get('message_id'),
                        "❌ ليس لديك حسابات مسجلة.\n\n"
                        "اضغط <b>🏢 تسجيل حساب جديد</b> أولاً")
                    return

                wallet = self.svrp.get_wallet(user_id)
                available = float(wallet.get('total_used', 0) or 0)

                text = (
                    f"💰 <b>إيداع من الرصيد المتاح</b>\n\n"
                    f"🟢 الرصيد المتاح: <b><code>{available:.2f}</code></b>\n\n"
                    f"اختر الشركة التي تريد الإيداع لحسابك فيها:"
                )
                inline_btns = []
                for acc in accounts:
                    inline_btns.append([{
                        'text': f"🏢 {acc.get('company_name', '')} — {acc.get('account_number', '')}",
                        'callback_data': f'svrp_dep_amt_{acc["company_id"]}_{acc["company_name"]}'
                    }])
                inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'svrp_back_panel'}])

                self.edit_message(chat_id, message.get('message_id'), text)
                self.send_inline_message(chat_id, "اختر الشركة:", inline_btns)
                return

            elif data.startswith('svrp_dep_amt_'):
                # طلب المبلغ للإيداع من المتاح
                parts = data.replace('svrp_dep_amt_', '').split('_', 1)
                if len(parts) != 2:
                    return
                company_id = parts[0]
                company_name = parts[1]

                wallet = self.svrp.get_wallet(user_id)
                available = float(wallet.get('total_used', 0) or 0)

                self.edit_message(chat_id, message.get('message_id'),
                    f"💰 <b>إيداع من الرصيد المتاح</b>\n\n"
                    f"🏢 الشركة: {company_name}\n"
                    f"🟢 الرصيد المتاح: <b><code>{available:.2f}</code></b>\n\n"
                    f"اكتب المبلغ الذي تريد إيداعه:")
                self.user_states[user_id] = f'svrp_dep_balance_{company_id}_{company_name}'
                return

            elif data == 'svrp_withdraw':
                self.edit_message(chat_id, message.get('message_id'), "💸 سحب")
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.create_withdrawal_request(fake_msg)
                return

            elif data == 'svrp_wallet':
                self.edit_message(chat_id, message.get('message_id'), "💎 محفظتي")
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_svrp_wallet(fake_msg)
                return

            elif data == 'svrp_invite':
                self.edit_message(chat_id, message.get('message_id'), "👥 دعوة صديق")
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_referral_panel(fake_msg)
                return

            elif data == 'svrp_companies':
                # عرض شركات الاسترداد للتسجيل
                companies = self.svrp.get_recovery_companies()
                if not companies:
                    self.edit_message(chat_id, message.get('message_id'), "📭 لا توجد شركات متاحة حالياً")
                    return

                text = "🏢 <b>شركات الاسترداد</b>\n\n"
                text += "اختر شركة للتسجيل:\n\n"
                inline_btns = []
                for c in companies:
                    text += f"• <b>{c['name']}</b>\n  🔗 <a href=\"{c.get('registration_url', '')}\">رابط التسجيل</a>\n  💰 نسبة المكافأة: {c.get('bonus_percentage', '10')}%\n\n"
                    inline_btns.append([{'text': f"📝 تسجيل حساب — {c['name']}", 'callback_data': f'svrp_reg_{c["id"]}'}])

                inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'svrp_back_panel'}])
                self.edit_message(chat_id, message.get('message_id'), text)
                self.send_inline_message(chat_id, "اختر شركة:", inline_btns)
                return

            elif data.startswith('svrp_reg_'):
                # تسجيل رقم حساب في شركة
                company_id = data.replace('svrp_reg_', '')
                companies = self.svrp.get_recovery_companies()
                company = None
                for c in companies:
                    if c['id'] == company_id:
                        company = c
                        break
                if not company:
                    self.send_message(chat_id, "❌ الشركة غير موجودة")
                    return

                self.edit_message(chat_id, message.get('message_id'),
                    f"📝 <b>تسجيل حساب في {company['name']}</b>\n\n"
                    f"🔗 رابط التسجيل: <a href=\"{company.get('registration_url', '')}\">اضغط هنا</a>\n\n"
                    f"بعد التسجيل، اكتب رقم حسابك:")
                self.user_states[user_id] = f'svrp_enter_account_{company_id}_{company["name"]}'
                return

            elif data == 'svrp_back_panel':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_svrp_panel(fake_msg)
                return

            elif data.startswith('svrp_bonus_'):
                # طلب مكافأة
                parts = data.replace('svrp_bonus_', '').split('_', 1)
                if len(parts) != 2:
                    return
                company_id = parts[0]
                company_name = parts[1]

                user = self.find_user(user_id)
                account = self.svrp.get_user_company_account(user_id, company_id)

                if not account:
                    self.send_message(chat_id, "❌ يجب تسجيل رقم حسابك أولاً")
                    return

                req_id, err = self.svrp.create_bonus_request(
                    user_id, company_id, company_name, account.get('account_number', '')
                )
                if err:
                    self.edit_message(chat_id, message.get('message_id'), f"❌ {err}")
                else:
                    self.edit_message(chat_id, message.get('message_id'),
                        f"✅ <b>تم إرسال طلب المكافأة!</b>\n\n"
                        f"🆔 <code>{req_id}</code>\n"
                        f"🏢 الشركة: {company_name}\n"
                        f"📋 رقم الحساب: <code>{account.get('account_number', '')}</code>\n\n"
                        f"⏳ بانتظار موافقة الإدارة")

                    # إشعار الأدمن
                    for admin_id in self.admin_ids:
                        try:
                            admin_msg = (
                                f"🏆 <b>طلب مكافأة جديد</b>\n\n"
                                f"🆔 <code>{req_id}</code>\n"
                                f"👤 العميل: {user.get('name', '')} ({user.get('customer_id', '')})\n"
                                f"🏢 الشركة: {company_name}\n"
                                f"📋 رقم الحساب: <code>{account.get('account_number', '')}</code>\n\n"
                                f"للموافقة: اكتب المبلغ"
                            )
                            inline_btns = [
                                [{'text': '✅ موافقة', 'callback_data': f'svrp_bonus_approve_{req_id}'},
                                 {'text': '❌ رفض', 'callback_data': f'svrp_bonus_reject_{req_id}'}]
                            ]
                            self.send_inline_message(admin_id, admin_msg, inline_btns)
                        except Exception as e:
                            logger.error(f"خطأ في إشعار الأدمن بطلب المكافأة: {e}")
                return

            elif data.startswith('svrp_bonus_approve_'):
                # الأدمن يكتب مبلغ المكافأة
                req_id = data.replace('svrp_bonus_approve_', '')
                self.edit_message(chat_id, message.get('message_id'),
                    f"✅ اكتب مبلغ المكافأة لطلب <code>{req_id}</code>:")
                self.user_states[user_id] = f'svrp_bonus_amount_{req_id}'
                return

            elif data.startswith('svrp_bonus_reject_'):
                req_id = data.replace('svrp_bonus_reject_', '')
                success, msg = self.svrp.reject_bonus_request(req_id, user_id)
                icon = "✅" if success else "❌"
                self.edit_message(chat_id, message.get('message_id'), f"{icon} {msg}")
                return

            elif data == 'svrp_recovery_request':
                # طلب استرداد — طلب لقطة شاشة
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                self.edit_message(chat_id, message.get('message_id'),
                    "🔄 <b>طلب استرداد</b>\n\n"
                    "📸 أرسل <b>لقطة شاشة</b> تظهر:\n"
                    "• رصيدك في حساب الشركة\n"
                    "• رقم حسابك\n\n"
                    "سيتم مراجعة طلبك من الإدارة")
                self.user_states[user_id] = 'svrp_waiting_screenshot'
                return

            elif data == 'svrp_send_credits':
                # إرسال رصيد مجمد — المرحلة 3
                self.edit_message(chat_id, message.get('message_id'),
                    "📤 <b>إرسال رصيد مجمد</b>\n\n"
                    "اكتب معرف العميل + المبلغ:\n\n"
                    "مثال:\n<code>C123456 250</code>\n\n"
                    "⚠️ الحد الأقصى لكل صديق: 25% من رصيدك المجمد\n"
                    "👥 الحد الأدنى: 4 أصدقاء لفك التجميد الكامل\n"
                    "💡 عند الإرسال ← يُفك تجميد نفس المبلغ")
                self.user_states[user_id] = 'svrp_send_credits_input'
                return

            elif data == 'svrp_recovery_approve':
                # موافقة الأدمن على طلب استرداد
                req_id = data.replace('svrp_recovery_approve_', '') if data.startswith('svrp_recovery_approve_') else ''
                if not req_id:
                    req_id = ''
                self.send_message(chat_id,
                    "✅ اكتب مبلغ الاسترداد الذي تريد إضافته للمستخدم:")
                self.user_states[user_id] = f'svrp_recovery_amount_{req_id}'
                return

            elif data == 'svrp_recovery_reject':
                req_id = data.replace('svrp_recovery_reject_', '') if data.startswith('svrp_recovery_reject_') else ''
                if self.svrp:
                    self.svrp.reject_recovery_request(req_id, user_id)
                self.edit_message(chat_id, message.get('message_id'), "❌ تم رفض طلب الاسترداد")
                # إشعار المستخدم
                req = self.svrp.get_recovery_request(req_id) if self.svrp else None
                if req:
                    self.notify_user(int(req['user_id']), "❌ تم رفض طلب الاسترداد الخاص بك", 'recovery_rejected')
                return

            # ==================== 💰 إيداع/سحب: أزرار inline ====================

            # إلغاء الإيداع/السحب
            elif data == 'dep_cancel' or data == 'wd_cancel':
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                self.edit_message(chat_id, message.get('message_id'), "❌ تم الإلغاء")
                welcome = self.tr('choose_service', lang, name=user.get('name', ''), customer_id=user.get('customer_id', '')) if user else ''
                self.send_message(chat_id, welcome, self.main_keyboard(lang, user_id))
                return

            # اختيار شركة للإيداع
            elif data.startswith('dep_company_'):
                company_id = data.replace('dep_company_', '')
                company = None
                for c in self.get_companies('deposit'):
                    if c['id'] == company_id:
                        company = c
                        break
                if not company:
                    self.edit_message(chat_id, message.get('message_id'), "❌ الشركة غير موجودة")
                    return

                icon = company.get('icon', '🏢') or '🏢'
                self.edit_message(chat_id, message.get('message_id'),
                    f"{icon} <b>{company['name']}</b>\n📋 {company.get('details', '')}\n\n💳 اختر وسيلة الدفع:")

                # عرض وسائل الدفع كأزرار inline
                methods = self.get_payment_methods_by_company(company_id, 'deposit')
                if not methods:
                    self.send_message(chat_id, "❌ لا توجد وسائل دفع لهذه الشركة")
                    return

                inline_btns = []
                for m in methods:
                    m_icon = m.get('icon', '💳') or '💳'
                    btn = f"{m_icon} {m['method_name']}"
                    if m.get('method_type'):
                        btn += f" — {m['method_type']}"
                    inline_btns.append([{'text': btn, 'callback_data': f'dep_method_{m["id"]}_{company_id}_{company["name"]}'}])
                inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'dep_back_companies'}])
                self.send_inline_message(chat_id, "💳 <b>وسائل الدفع المتاحة</b>", inline_btns)
                return

            # الرجوع لقائمة الشركات (إيداع)
            elif data == 'dep_back_companies':
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                self.edit_message(chat_id, message.get('message_id'), "💰 <b>طلب إيداع</b>\n\nاختر الشركة:")
                companies = self.get_companies('deposit')
                inline_btns = []
                for c in companies:
                    icon = c.get('icon', '🏢') or '🏢'
                    inline_btns.append([{'text': f"{icon} {c['name']}", 'callback_data': f'dep_company_{c["id"]}'}])
                inline_btns.append([{'text': self.tr('main_menu', lang), 'callback_data': 'dep_cancel'}])
                self.send_inline_message(chat_id, "💰 <b>طلب إيداع</b>", inline_btns)
                return

            # اختيار وسيلة دفع للإيداع
            elif data.startswith('dep_method_'):
                parts = data.replace('dep_method_', '').split('_', 2)
                if len(parts) < 3:
                    return
                method_id = parts[0]
                company_id = parts[1]
                company_name = parts[2]

                method = self.get_payment_method_by_id(method_id) if method_id else None
                method_name = method['method_name'] if method else ''
                method_type = method.get('method_type', '') if method else ''
                account_data = method.get('account_data', '') if method else ''
                additional_info = method.get('additional_info', '') if method else ''
                method_icon = method.get('icon', '💳') if method else '💳'

                # عرض بيانات وسيلة الدفع للعميل — قابلة للنسخ
                method_text = (
                    f"✅ <b>تم اختيار وسيلة الدفع</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🏢 الشركة: <b>{company_name}</b>\n"
                    f"{method_icon} الوسيلة: <b>{method_name}</b>\n"
                )
                if method_type:
                    method_text += f"📋 النوع: {method_type}\n"
                if account_data:
                    method_text += f"🔢 <b>رقم الحساب / المحفظة للتحويل:</b>\n<code>{account_data}</code>\n\n"
                if additional_info:
                    method_text += f"💡 {additional_info}\n"
                method_text += f"━━━━━━━━━━━━━━━━━━\n\n"
                method_text += f"📤 <b>حوّل المال إلى الرقم أعلاه</b>\n"
                method_text += f"ثم أرسل بياناتك في رسالة واحدة:\n\n"
                method_text += f"1️⃣ رقم محفظتك التي أرسلت منها\n"
                method_text += f"2️⃣ معرف حسابك في التطبيق\n\n"
                method_text += f"💡 مثال:\n<code>0501234567\nID-789</code>"

                self.edit_message(chat_id, message.get('message_id'), method_text)

                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                kb = {'keyboard': [[{'text': '❌ إلغاء'}, {'text': self.tr('main_menu', lang)}]], 'resize_keyboard': True, 'one_time_keyboard': True}
                self.send_message(chat_id, "📝 أرسل رقم محفظتك + معرف حسابك:", kb)
                self.user_states[user_id] = f'deposit_wallet_{company_id}_{company_name}_{method_id}'
                return

            # اختيار شركة للسحب
            elif data.startswith('wd_company_'):
                company_id = data.replace('wd_company_', '')
                company = None
                for c in self.get_companies('withdraw'):
                    if c['id'] == company_id:
                        company = c
                        break
                if not company:
                    self.edit_message(chat_id, message.get('message_id'), "❌ الشركة غير موجودة")
                    return

                icon = company.get('icon', '🏢') or '🏢'
                address = company.get('address', '')

                text = f"{icon} <b>{company['name']}</b>\n📋 {company.get('details', '')}\n"
                if address:
                    text += f"📍 <b>عنوان السحب:</b>\n<code>{address}</code>\n\n"
                text += f"━━━━━━━━━━━━━━━━━━\n\n"
                text += f"📝 أرسل بياناتك في رسالة واحدة:\n\n"
                text += f"1️⃣ رقم المحفظة التي تريد الاستلام عليها\n"
                text += f"2️⃣ معرف حسابك في التطبيق\n"
                text += f"3️⃣ كود السحب\n"
                text += f"4️⃣ المبلغ الذي تريد سحبه\n\n"
                text += f"💡 مثال:\n<code>0501234567\nID-789\nABC123\n500</code>"

                self.edit_message(chat_id, message.get('message_id'), text)

                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                kb = {'keyboard': [[{'text': '❌ إلغاء'}, {'text': self.tr('main_menu', lang)}]], 'resize_keyboard': True, 'one_time_keyboard': True}
                self.send_message(chat_id, "📝 أرسل بياناتك الأربعة:", kb)
                self.user_states[user_id] = f'withdraw_all_data_{company_id}_{company["name"]}'
                return

            # ==================== 🤖 إدارة البوتات المتعددة ====================
            elif data == 'mbot_back_admin' or data == 'mbot_back':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.handle_admin_panel(fake_msg)
                return

            elif data == 'mbot_refresh':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_multi_bot_panel(fake_msg)
                return

            elif data == 'mbot_add_wizard':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.mbot_start_wizard(fake_msg)
                return

            elif data == 'mbot_add_new':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.mbot_start_wizard(fake_msg)
                return

            elif data.startswith('mbot_start_'):
                bot_id = data.replace('mbot_start_', '')
                manager = MultiBotManager()
                success, msg = manager.start_bot(bot_id)
                icon = "✅" if success else "❌"
                self.edit_message(chat_id, message.get('message_id'), f"{icon} {msg}")
                # تحديث اللوحة
                import time as _time; _time.sleep(1)
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_multi_bot_panel(fake_msg)
                return

            elif data.startswith('mbot_stop_'):
                bot_id = data.replace('mbot_stop_', '')
                manager = MultiBotManager()
                success, msg = manager.stop_bot(bot_id)
                icon = "✅" if success else "❌"
                self.edit_message(chat_id, message.get('message_id'), f"{icon} {msg}")
                import time as _time; _time.sleep(1)
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_multi_bot_panel(fake_msg)
                return

            elif data.startswith('mbot_activate_'):
                bot_id = data.replace('mbot_activate_', '')
                manager = MultiBotManager()
                manager.toggle_bot(bot_id, activate=True)
                success, msg = manager.start_bot(bot_id)
                icon = "✅" if success else "❌"
                self.edit_message(chat_id, message.get('message_id'), f"{icon} {msg}")
                import time as _time; _time.sleep(1)
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_multi_bot_panel(fake_msg)
                return

            elif data.startswith('mbot_delete_'):
                bot_id = data.replace('mbot_delete_', '')
                # تأكيد الحذف
                inline_btns = [
                    [{'text': '✅ نعم، احذف', 'callback_data': f'mbot_confirm_delete_{bot_id}'},
                     {'text': '❌ إلغاء', 'callback_data': 'mbot_refresh'}]
                ]
                self.edit_message(chat_id, message.get('message_id'),
                    f"⚠️ هل أنت متأكد من حذف البوت <code>{bot_id}</code>؟")
                self.send_inline_message(chat_id, "🗑️ تأكيد حذف البوت:", inline_btns)
                return

            elif data.startswith('mbot_confirm_delete_'):
                bot_id = data.replace('mbot_confirm_delete_', '')
                manager = MultiBotManager()
                if manager.delete_bot(bot_id):
                    self.edit_message(chat_id, message.get('message_id'), f"✅ تم حذف البوت {bot_id}")
                else:
                    self.edit_message(chat_id, message.get('message_id'), f"❌ لم يتم العثور على البوت {bot_id}")
                import time as _time; _time.sleep(1)
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_multi_bot_panel(fake_msg)
                return

            elif data.startswith('mbot_freeze_'):
                bot_id = data.replace('mbot_freeze_', '')
                # طلب تاريخ التجميد
                self.send_message(chat_id,
                    f"🧊 <b>تجميد البوت</b>\n\n"
                    f"اكتب تاريخ التجميد بصيغة <code>YYYY-MM-DD</code>:\n\n"
                    f"مثال: <code>2026-12-31</code>\n\n"
                    f"أو اكتب <code>الآن</code> للتجميد الفوري\n"
                    f"أو اكتب <code>إلغاء</code> للرجوع")
                self.user_states[user_id] = f'mbot_freeze_input_{bot_id}'
                return

            elif data.startswith('mbot_unfreeze_'):
                bot_id = data.replace('mbot_unfreeze_', '')
                manager = MultiBotManager()
                manager.unfreeze_bot(bot_id)
                self.edit_message(chat_id, message.get('message_id'), f"✅ تم إلغاء تجميد البوت {bot_id}")
                import time as _time; _time.sleep(1)
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_multi_bot_panel(fake_msg)
                return

            elif data.startswith('mbot_admins_'):
                bot_id = data.replace('mbot_admins_', '')
                self.mbot_show_admins(chat_id, bot_id)
                return

            # ==================== 💎 إدارة تعويض 100% ====================
            # ==================== 🛠️ بيانات الدعم (inline) ====================
            elif data == 'support_back_admin':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.handle_admin_panel(fake_msg)
                return

            elif data == 'support_edit_phone':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.start_phone_edit_wizard(fake_msg)
                return

            elif data == 'support_edit_telegram':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.start_telegram_edit_wizard(fake_msg)
                return

            elif data == 'support_edit_email':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.start_email_edit_wizard(fake_msg)
                return

            elif data == 'support_edit_hours':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.start_hours_edit_wizard(fake_msg)
                return

            # ==================== 💎 إدارة تعويض 100% ====================
            elif data == 'svrp_admin_back':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_svrp_admin_panel(fake_msg)
                return

            elif data == 'svrp_admin_wallets':
                self.svrp_admin_view_wallets(chat_id)
                return

            elif data == 'svrp_admin_promos':
                self.svrp_admin_view_promos(chat_id)
                return

            elif data == 'svrp_admin_tasks':
                self.svrp_admin_view_tasks(chat_id)
                return

            elif data == 'svrp_admin_settings':
                self.svrp_admin_edit_settings(chat_id)
                return

            elif data == 'svrp_admin_cleanup':
                self.svrp_admin_cleanup(chat_id)
                return

            elif data.startswith('svrp_edit_'):
                key = data.replace('svrp_edit_', '')
                self.svrp_admin_edit_one_setting(chat_id, message.get('message_id'), key)
                return

            elif data.startswith('svrp_inc_'):
                # زيادة قيمة إعداد
                parts = data.replace('svrp_inc_', '').rsplit('_', 1)
                if len(parts) == 2:
                    key, step_str = parts
                    step = float(step_str)
                    old_val = self.svrp._get_config(key)
                    new_val = old_val + step
                    self._update_svrp_config(key, new_val)
                    self.svrp_admin_edit_one_setting(chat_id, message.get('message_id'), key)
                return

            elif data.startswith('svrp_dec_'):
                # نقصان قيمة إعداد
                parts = data.replace('svrp_dec_', '').rsplit('_', 1)
                if len(parts) == 2:
                    key, step_str = parts
                    step = float(step_str)
                    old_val = self.svrp._get_config(key)
                    new_val = max(0, old_val - step)  # لا ينزل تحت صفر
                    self._update_svrp_config(key, new_val)
                    self.svrp_admin_edit_one_setting(chat_id, message.get('message_id'), key)
                return

            elif data == 'svrp_edit_texts':
                lang_names = self.get_language_names()
                text = "📝 <b>تعديل نصوص شرح النظام</b>\n\nاختر اللغة:\n\n"
                inline_btns = []
                row = []
                for code, info in lang_names.items():
                    row.append({'text': f"{info['flag']} {info['native']}", 'callback_data': f'svrp_edit_intro_{code}'})
                    if len(row) == 3:
                        inline_btns.append(row)
                        row = []
                if row:
                    inline_btns.append(row)
                inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'svrp_admin_back'}])
                self.edit_message(chat_id, message.get('message_id'), text)
                self.send_inline_message(chat_id, "اختر اللغة:", inline_btns)
                return

            elif data.startswith('svrp_edit_intro_') and data != 'svrp_edit_texts':
                lang_code = data.replace('svrp_edit_intro_', '')
                current = self.get_setting(f'svrp_intro_{lang_code}') or '(النص الافتراضي)'
                lang_names = self.get_language_names()
                lang_native = lang_names.get(lang_code, {}).get('native', lang_code)
                self.edit_message(chat_id, message.get('message_id'),
                    f"📝 <b>تعديل نص الشرح ({lang_native})</b>\n\n"
                    f"📋 النص الحالي:\n<code>{current[:200]}...</code>\n\n"
                    f"✍️ اكتب النص الجديد كاملاً:")
                self.user_states[user_id] = f'svrp_edit_intro_{lang_code}_input'
                return

            elif data == 'svrp_admin_detailed':
                # إحصائيات تفصيلية
                stats = self.svrp.get_svrp_stats()
                text = (
                    "╔════════════════════╗\n"
                    "║  📊 إحصائيات تفصيلية  ║\n"
                    "╚════════════════════╝\n\n"
                    f"💰 أرصدة مصدرة: {stats['total_credits_issued']:.2f}\n"
                    f"📉 أرصدة مستخدمة: {stats['total_credits_used']:.2f}\n"
                    f"✅ أرصدة نشطة: {stats['active_credits']}\n"
                    f"⏰ أرصدة منتهية: {stats['expired_credits']}\n"
                    f"👥 المحافظ: {stats['total_wallets']}\n"
                    f"💵 إجمالي الأرصدة: {stats['total_balance']:.2f}\n"
                    f"⏳ رصيد معلق: {stats['total_pending']:.2f}\n"
                    f"📋 مهام نشطة: {stats['active_tasks']}\n"
                    f"✅ مهام مكتملة: {stats['completed_tasks']}\n"
                    f"🎉 مهام مستلمة: {stats['claimed_tasks']}\n"
                    f"🎟️ أكواد نشطة: {stats['active_promos']}\n"
                )
                if stats.get('top_referrers'):
                    text += "\n🏆 أفضل المُحيلين:\n"
                    for tid, count in stats['top_referrers']:
                        text += f"  • <code>{tid}</code>: {count} إحالة\n"
                self.send_inline_message(chat_id, text,
                    [[{'text': '🔙 العودة', 'callback_data': 'svrp_admin_back'}]])
                return

            # ==================== 💎 تعويض 100% — أزرار العميل ====================

            elif data == 'svrp_main_menu':
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                self.edit_message(chat_id, message.get('message_id'), "🏠 تم العودة للقائمة الرئيسية")
                welcome = self.tr('choose_service', lang, name=user.get('name',''), customer_id=user.get('customer_id','')) if user else ''
                self.send_message(chat_id, welcome, self.main_keyboard(lang, user_id))
                return

            elif data == 'svrp_recovery_request':
                self.edit_message(chat_id, message.get('message_id'),
                    "🔄 <b>طلب استرداد</b>\n\n"
                    "📸 أرسل <b>لقطة شاشة</b> تظهر:\n"
                    "• رصيدك في حساب الشركة\n"
                    "• رقم حسابك\n\n"
                    "سيتم مراجعتها من قبل الإدارة")
                self.user_states[user_id] = 'svrp_awaiting_screenshot'
                return

            elif data == 'svrp_deposit':
                self.edit_message(chat_id, message.get('message_id'), "💰 جارٍ تحويلك للإيداع...")
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.create_deposit_request(fake_msg)
                return

            elif data == 'svrp_withdraw':
                self.edit_message(chat_id, message.get('message_id'), "💸 جارٍ تحويلك للسحب...")
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.create_withdrawal_request(fake_msg)
                return

            elif data == 'svrp_wallet':
                fake_msg = {'chat': {'id': chat_id}, 'from': {'id': user_id}, 'text': ''}
                self.show_svrp_wallet(fake_msg)
                return

            elif data == 'svrp_send_credits':
                self.edit_message(chat_id, message.get('message_id'),
                    "📤 <b>إرسال رصيد مجمد</b>\n\n"
                    "اكتب معرف العميل + المبلغ:\n\n"
                    "<code>مثال: C123456 100</code>\n\n"
                    "💡 سيتم خصم المبلغ من رصيدك المجمد\n"
                    "وإضافته للرصيد المجمد للعميل الآخر\n"
                    "ونقل نفس المبلغ من مجمده إلى متاحك")
                self.user_states[user_id] = 'svrp_awaiting_send'
                return

            elif data == 'svrp_invite':
                user = self.find_user(user_id)
                ref_code = self.get_user_referral_code(user) if user else ''
                ref_count = self.get_referral_count(user_id)
                self.edit_message(chat_id, message.get('message_id'),
                    f"👥 <b>دعوة صديق</b>\n\n"
                    f"📋 كود الإحالة: <code>{ref_code}</code>\n"
                    f"👥 الإحالات: <b>{ref_count}</b>\n\n"
                    f"شارك الكود مع أصدقائك!")
                return

            # ==================== 💎 تعويض 100% — موافقة الأدمن ====================

            elif data.startswith('rec_approve_'):
                req_id = data.replace('rec_approve_', '')
                self.edit_message(chat_id, message.get('message_id'),
                    f"✅ <b>موافقة على طلب استرداد</b>\n\n"
                    f"🆔 <code>{req_id}</code>\n\n"
                    f"اكتب مبلغ الاسترداد (الرصيد المجمد):")
                self.user_states[user_id] = f'svrp_approve_amount_{req_id}'
                return

            elif data.startswith('rec_reject_'):
                req_id = data.replace('rec_reject_', '')
                self.svrp.reject_recovery_request(req_id, 'مرفوض من الإدارة')
                self.edit_message(chat_id, message.get('message_id'),
                    f"❌ تم رفض طلب الاسترداد {req_id}")
                # إشعار العميل
                req = self.svrp.get_recovery_request(req_id)
                if req:
                    self.notify_user(int(req['user_id']), "❌ تم رفض طلب الاسترداد الخاص بك")
                return

            # ==================== مطابقة: موافقة + اختيار نوع ====================
            elif data == 'match_agree':
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                self.edit_message(chat_id, message.get('message_id'),
                    "✅ <b>تمت الموافقة!</b>\n\nاختر نوع العملية:")
                inline_btns = [
                    [{'text': '💰 مطابقة إيداع', 'callback_data': 'match_type_deposit'},
                     {'text': '💸 مطابقة سحب', 'callback_data': 'match_type_withdraw'}],
                    [{'text': '🔙 العودة', 'callback_data': 'match_cancel'}]
                ]
                self.send_inline_message(chat_id, "اختر نوع العملية:", inline_btns)
                return

            elif data == 'match_cancel':
                user = self.find_user(user_id)
                lang = user.get('language', 'ar') if user else 'ar'
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.edit_message(chat_id, message.get('message_id'), "❌ تم الإلغاء")
                welcome = self.tr('choose_service', lang, name=user.get('name', ''), customer_id=user.get('customer_id', '')) if user else ''
                self.send_message(chat_id, welcome, self.main_keyboard(lang, user_id))
                return

            elif data == 'match_type_deposit' or data == 'match_type_withdraw':
                match_type = 'deposit' if data == 'match_type_deposit' else 'withdraw'
                self.edit_message(chat_id, message.get('message_id'),
                    f"{'💰' if match_type == 'deposit' else '💸'} <b>المطابقة — {match_type}</b>\n\n")

                # عرض الشركات كأزرار inline
                companies = self.get_companies('both')
                if not companies:
                    self.send_message(chat_id, "❌ لا توجد شركات متاحة")
                    return

                inline_btns = []
                for c in companies:
                    icon = c.get('icon', '🏢') or '🏢'
                    inline_btns.append([{'text': f"{icon} {c['name']}", 'callback_data': f'match_company_{c["id"]}_{match_type}'}])
                inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'match_agree'}])

                self.send_inline_message(chat_id, "🏢 اختر الشركة:", inline_btns)
                self.user_states[user_id] = {'step': 'match_company_select', 'type': match_type}
                return

            elif data.startswith('match_company_') and not data.startswith('match_company_select'):
                parts = data.replace('match_company_', '').rsplit('_', 1)
                if len(parts) != 2:
                    return
                company_id = parts[0]
                match_type = parts[1]

                company = None
                for c in self.get_companies('both'):
                    if c['id'] == company_id:
                        company = c
                        break
                if not company:
                    self.send_message(chat_id, "❌ الشركة غير موجودة")
                    return

                icon = company.get('icon', '🏢') or '🏢'
                self.edit_message(chat_id, message.get('message_id'),
                    f"{icon} <b>{company['name']}</b>\n📋 {company.get('details', '')}\n\n"
                    "💳 اختر وسيلة الدفع:")

                methods = self.get_payment_methods_by_company(company_id, match_type)
                if not methods:
                    self.send_message(chat_id, "❌ لا توجد وسائل دفع لهذه الشركة")
                    return

                inline_btns = []
                for m in methods:
                    m_icon = m.get('icon', '💳') or '💳'
                    inline_btns.append([{'text': f"{m_icon} {m['method_name']}", 'callback_data': f'match_method_{m["id"]}_{company_id}_{company["name"]}_{match_type}'}])
                inline_btns.append([{'text': '🔙 رجوع', 'callback_data': 'match_agree'}])

                self.send_inline_message(chat_id, "اختر وسيلة الدفع:", inline_btns)
                return

            elif data.startswith('match_method_'):
                parts = data.replace('match_method_', '').split('_', 3)
                if len(parts) < 4:
                    return
                method_id = parts[0]
                company_id = parts[1]
                company_name = parts[2]
                match_type = parts[3]

                method = self.get_payment_method_by_id(method_id) if method_id else None
                method_name = method['method_name'] if method else ''
                account_data = method.get('account_data', '') if method else ''

                type_ar = 'إيداع' if match_type == 'deposit' else 'سحب'
                text = (
                    f"✅ <b>تم اختيار وسيلة الدفع</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🏢 الشركة: <b>{company_name}</b>\n"
                    f"💳 الوسيلة: <b>{method_name}</b>\n"
                )
                if account_data:
                    text += f"🔢 رقم الحساب: <code>{account_data}</code>\n"
                text += (
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"📝 أرسل بياناتك في رسالة واحدة:\n\n"
                    f"1️⃣ المبلغ\n"
                    f"2️⃣ رقم محفظتك\n"
                    f"3️⃣ معرف حسابك في التطبيق\n\n"
                    f"💡 مثال:\n<code>500\n0501234567\nID-789</code>"
                )

                self.edit_message(chat_id, message.get('message_id'), text)
                self.user_states[user_id] = {
                    'step': 'match_enter_data',
                    'type': match_type,
                    'company_id': company_id,
                    'company_name': company_name,
                    'method_id': method_id,
                    'method_name': method_name
                }
                return

            # ==================== مطابقة: الأدمن ينضم كطرف آخر ====================
            elif data.startswith('match_admin_join_'):
                req_id = data.replace('match_admin_join_', '')
                request = self.match_manager.get_request_by_id(req_id) if hasattr(self.match_manager, 'get_request_by_id') else None

                if not request:
                    # محاولة البحث في الطلبات
                    all_reqs = self.match_manager._read_csv('match_requests.csv') if hasattr(self.match_manager, '_read_csv') else []
                    request = next((r for r in all_reqs if r.get('id') == req_id), None)

                if not request:
                    self.edit_message(chat_id, message.get('message_id'), "❌ الطلب غير موجود أو انتهى")
                    return

                # الأدمن يصبح الطرف الآخر
                admin_user_id = str(user_id)
                opposite_type = 'withdraw' if request.get('type') == 'deposit' else 'deposit'

                # إنشاء طلب مطابقة للأدمن (الطرف المعاكس)
                admin_req_id, err = self.match_manager.create_match_request(
                    admin_user_id, 'ADMIN', opposite_type,
                    request.get('amount', '0'), request.get('currency', 'SAR'),
                    request.get('company_id', ''), request.get('company_name', ''), ''
                )

                if err:
                    self.edit_message(chat_id, message.get('message_id'), f"❌ {err}")
                    return

                # مطابقة فورية بين العميل والأدمن
                admin_request = self.match_manager.get_active_request_by_user(admin_user_id)
                if admin_request:
                    match = self.match_manager.find_match(admin_request)
                    if match:
                        match_id = self.match_manager.create_match(admin_request, match)
                        self._notify_match_created(match_id)

                        self.edit_message(chat_id, message.get('message_id'),
                            f"✅ <b>تم إنشاء المطابقة!</b>\n\n"
                            f"🆔 <code>{match_id}</code>\n"
                            f"👤 العميل: <code>{request.get('user_id', '')}</code>\n"
                            f"👤 الأدمن: <code>{admin_user_id}</code>\n\n"
                            f"تم إشعار الطرفين.")
                        return

                self.edit_message(chat_id, message.get('message_id'),
                    "⏳ تم إنشاء طلبك كطرف آخر. جارٍ البحث عن مطابقة...")

            elif data.startswith('match_admin_wait_'):
                self.edit_message(chat_id, message.get('message_id'),
                    "⏳ تم ترك الطلب معلقاً. سيتم إشعارك عند وجود مطابقة تلقائية.")
                return

            # ==================== مطابقة: تأكيد الكود ====================
            elif data.startswith('match_verify_'):
                match_id = data.replace('match_verify_', '')
                self.match_manager.update_match_status(match_id, 'code_verified')

                match = self.match_manager.get_match_by_id(match_id)
                if match:
                    # إشعار المودع: أرسل المال
                    dep_id = int(match['depositor_id'])
                    dep_user = self.find_user(dep_id)
                    dep_lang = dep_user.get('language', 'ar') if dep_user else 'ar'
                    company = self.get_company_by_id(match['company_id'])
                    company_icon = company.get('icon', '🏢') if company else '🏢'

                    pay_msg = (
                        f"✅ تم تأكيد الكود!\n\n"
                        f"{company_icon} {match['company_name']}\n"
                        f"💰 المبلغ: {match['amount']} {match['currency']}\n\n"
                        f"📤 أرسل المال الآن ثم أكد الإرسال."
                    )
                    pay_kb = {
                        'keyboard': [
                            [{'text': '✅ تم الإرسال'}, {'text': '❌ إلغاء'}],
                            [{'text': '🆘 دعم'}]
                        ],
                        'resize_keyboard': True
                    }
                    self.send_message(dep_id, pay_msg, pay_kb)

                    # إشعار الساحب: الكود مؤكد
                    wit_id = int(match['withdrawer_id'])
                    self.send_message(wit_id, "✅ تم تأكيد الكود! بانتظار استلام المال من الطرف الآخر.")

                self.edit_message(chat_id, message.get('message_id'), f"✅ تم تأكيد الكود لـ {match_id}")
                return

            # ==================== مطابقة: رفض الكود ====================
            elif data.startswith('match_reject_code_'):
                match_id = data.replace('match_reject_code_', '')
                match = self.match_manager.get_match_by_id(match_id)
                if match:
                    wit_id = int(match['withdrawer_id'])
                    wit_user = self.find_user(wit_id)
                    wit_lang = wit_user.get('language', 'ar') if wit_user else 'ar'
                    self.send_message(wit_id,
                        f"❌ الكود أو البيانات غير صحيحة. أرسل البيانات مرة أخرى:\n\n"
                        f"1️⃣ كود السحب\n"
                        f"2️⃣ معرف حسابك (ID)\n"
                        f"3️⃣ رقم محفظتك\n"
                        f"4️⃣ وسيلة الدفع\n\n"
                        f"💡 في 4 أسطر منفصلة")
                    self.user_states[wit_id] = {'step': 'match_enter_code', 'match_id': match_id}

                self.edit_message(chat_id, message.get('message_id'), f"🔁 تم طلب كود جديد لـ {match_id}")
                return

            # ==================== مطابقة: حل نزاع ====================
            elif data.startswith('dispute_resolve_dep_'):
                dispute_id = data.replace('dispute_resolve_dep_', '')
                self.match_manager.resolve_dispute(dispute_id, 'حل لصالح المودع')
                self.edit_message(chat_id, message.get('message_id'), "✅ تم الحل لصالح المودع")
                return

            elif data.startswith('dispute_resolve_wit_'):
                dispute_id = data.replace('dispute_resolve_wit_', '')
                self.match_manager.resolve_dispute(dispute_id, 'حل لصالح الساحب')
                self.edit_message(chat_id, message.get('message_id'), "✅ تم الحل لصالح الساحب")
                return

            elif data.startswith('dispute_cancel_'):
                dispute_id = data.replace('dispute_cancel_', '')
                self.match_manager.resolve_dispute(dispute_id, 'إلغاء العملية')
                self.edit_message(chat_id, message.get('message_id'), "❌ تم إلغاء العملية")
                return

            # القائمة الرئيسية
            elif data == 'main_menu':
                user = self.find_user(user_id)
                if user:
                    lang = user.get('language', 'ar')
                    welcome = self.tr('choose_service', lang, name=user.get('name',''), customer_id=user.get('customer_id',''))
                    self.send_message(chat_id, welcome, self.main_keyboard(lang, user_id))
                return
                
        except Exception as e:
            logger.error(f"خطأ في معالجة callback: {e}")
    
    def run(self):
        """تشغيل البوت — مع نظام حماية شامل"""
        logger.info(f"✅ نظام DUX الشامل يعمل: @{os.getenv('BOT_TOKEN', 'unknown').split(':')[0] if os.getenv('BOT_TOKEN') else 'unknown'}")
        
        # نظام الحماية: تتبع الرسائل المعالجة لمنع التكرار
        processed_updates = set()
        MAX_PROCESSED_CACHE = 1000  # حد أقصى للذاكرة
        
        # نظام الحماية: تتبع آخر نشاط لكل مستخدم
        user_last_activity = {}
        MIN_MESSAGE_INTERVAL = 0.5  # نصف ثانية بين رسائل نفس المستخدم
        
        while True:
            try:
                updates = self.get_updates()
                if not updates or not updates.get('ok'):
                    time.sleep(0.5)
                    continue
                
                for update in updates['result']:
                    update_id = update['update_id']
                    
                    # 1. منع التكرار: تخطي الرسائل المعالجة مسبقاً
                    if update_id in processed_updates:
                        continue
                    
                    # إضافة للذاكرة
                    processed_updates.add(update_id)
                    if len(processed_updates) > MAX_PROCESSED_CACHE:
                        # تنظيف الذاكرة: احتفظ بآخر 500 فقط
                        processed_updates.clear()
                    
                    # تحديث الـ offset فوراً لمنع إعادة استلام نفس الرسالة
                    self.offset = update_id
                    
                    if 'message' in update:
                        message = update['message']
                        user_id = message['from']['id']
                        
                        # 2. منع السبام: فحص الفاصل الزمني بين رسائل نفس المستخدم
                        now = time.time()
                        if user_id in user_last_activity:
                            elapsed = now - user_last_activity[user_id]
                            if elapsed < MIN_MESSAGE_INTERVAL:
                                logger.warning(f"سبام محتمل من {user_id}: {elapsed:.2f}s - تخطي")
                                continue
                        user_last_activity[user_id] = now
                        
                        # 3. تسجيل الرسالة
                        if 'text' in message:
                            logger.info(f"رسالة: {message['text'][:50]} من {user_id}")
                        
                        # 4. معالجة الرسالة مع timeout
                        try:
                            self.process_message(message)
                        except Exception as msg_error:
                            logger.error(f"خطأ في معالجة الرسالة: {msg_error}", exc_info=True)
                            # تنظيف حالة المستخدم عند الخطأ
                            if user_id in self.user_states:
                                try:
                                    del self.user_states[user_id]
                                except:
                                    pass
                            # إرسال رسالة خطأ للمستخدم
                            try:
                                err_user = self.find_user(user_id)
                                err_lang = err_user.get('language', 'ar') if err_user else 'ar'
                                error_kb = {
                                    'keyboard': [
                                        [{'text': self.tr('reset_system', err_lang)}],
                                        [{'text': self.tr('main_menu', err_lang)}]
                                    ],
                                    'resize_keyboard': True
                                }
                                self.send_message(message['chat']['id'],
                                    self.tr('error_occurred', err_lang), error_kb)
                            except:
                                pass
                    
                    elif 'callback_query' in update:
                        try:
                            self.handle_callback_query(update['callback_query'])
                        except Exception as cb_error:
                            logger.error(f"خطأ في معالجة callback: {cb_error}", exc_info=True)
                            try:
                                self.answer_callback(update['callback_query'].get('id'), "❌ خطأ")
                            except:
                                pass
                
                # 5. تنظيف دوري للذاكرة
                if len(user_last_activity) > 500:
                    cutoff = time.time() - 300  # احذف نشاط أقدم من 5 دقائق
                    user_last_activity = {k: v for k, v in user_last_activity.items() if v > cutoff}
                
            except KeyboardInterrupt:
                logger.info("تم إيقاف البوت بواسطة المستخدم")
                break
            except Exception as e:
                logger.error(f"خطأ عام في حلقة التشغيل: {e}", exc_info=True)
                # انتظار قصير قبل المحاولة مرة أخرى
                time.sleep(1)
                continue

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
            self.send_message(message['chat']['id'], "❌ حدث خطأ أثناء تغيير اللغة", self.main_keyboard('ar'))
    
    def prompt_admin_search(self, message):
        """طلب البحث من الأدمن"""
        search_help = """🔍 البحث في النظام

أرسل: بحث متبوعاً بالنص المطلوب

يمكنك البحث بـ:
• اسم العميل
• رقم العميل
• رقم الهاتف

مثال: بحث أحمد"""
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
                self.send_message(message['chat']['id'], f"❌ لم يتم العثور على نتائج للبحث: {query}", self.admin_keyboard())
                return
            
            response = f"🔍 نتائج البحث عن: {query}\n\n"
            for user in results:
                ban_status = "🚫 محظور" if user.get('is_banned') == 'yes' else "✅ نشط"
                response += f"👤 {user.get('name', 'غير محدد')}\n"
                response += f"🆔 {user.get('customer_id', 'غير محدد')}\n"
                response += f"📱 {user.get('phone', 'غير محدد')}\n"
                response += f"🔸 {ban_status}\n\n"
            
            if len(response) > 4000:
                response = response[:4000] + "\n... والمزيد من النتائج"
            
            self.send_message(message['chat']['id'], response, self.admin_keyboard())
            
        except Exception as e:
            logger.error(f"خطأ في البحث: {e}")
            self.send_message(message['chat']['id'], "❌ حدث خطأ أثناء البحث", self.admin_keyboard())

    def add_admin_user(self, message, user_id_to_add):
        """إضافة أدمن جديد — مع فحوصات أمنية"""
        try:
            if not user_id_to_add.isdigit():
                self.send_message(message['chat']['id'], "❌ معرف المستخدم يجب أن يكون رقماً صحيحاً", self.admin_keyboard())
                return

            new_admin_id = int(user_id_to_add)
            requester_id = message['from']['id']

            if new_admin_id == requester_id:
                self.send_message(message['chat']['id'], "⚠️ أنت أدمن بالفعل!", self.admin_keyboard())
                return

            if new_admin_id in self.admin_user_ids:
                self.send_message(message['chat']['id'], f"⚠️ المستخدم {user_id_to_add} أدمن بالفعل", self.admin_keyboard())
                return

            if new_admin_id in self.temp_admin_user_ids:
                self.send_message(message['chat']['id'], f"⚠️ المستخدم {user_id_to_add} مدير مؤقت بالفعل", self.admin_keyboard())
                return

            self.admin_user_ids.append(new_admin_id)
            self.log_admin_action(requester_id, "add_admin", f"added admin: {user_id_to_add}")

            success_msg = f"""✅ تم إضافة أدمن جديد بنجاح!

🆔 {user_id_to_add}
🔐 تم منح صلاحيات الإدارة

💡 ملاحظة: هذا الأدمن نشط في الجلسة الحالية فقط.
للاستمرارية، أضف المعرف إلى متغير البيئة ADMIN_USER_IDS"""

            self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
            logger.info(f"تم إضافة أدمن جديد: {user_id_to_add} بواسطة: {requester_id}")

        except Exception as e:
            logger.error(f"خطأ في إضافة الأدمن: {e}")
            self.send_message(message['chat']['id'], "❌ حدث خطأ أثناء إضافة الأدمن", self.admin_keyboard())
    
    def prompt_add_admin(self, message):
        """طلب إضافة أدمن جديد"""
        add_admin_help = """👥 إضافة أدمن جديد
        
الصيغة: اضافة_ادمن معرف_المستخدم

مثال: اضافة_ادمن 123456789

💡 لمعرفة معرف المستخدم، اطلب منه إرسال /myid"""
        self.send_message(message['chat']['id'], add_admin_help, self.admin_keyboard())
    
    def show_admin_list(self, message):
        """عرض قائمة الأدمن"""
        admin_text = "📋 قائمة المديرين:\n\n"
        
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
            '💰 إيداع', '💸 سحب', '🔄 استرداد', '📤 إرسال رصيد',
            '💎 محفظتي', '👥 دعوة صديق', '🏢 تسجيل حساب جديد', '🏠 القائمة الرئيسية'
        ]
        all_buttons.update(svrp_buttons)

        # 4) أزرار نظام التطبيقات (inline)
        app_buttons = ['➕ إضافة تطبيق جديد', '🔄 تحديث القائمة', '🔙 العودة للوحة الأدمن']
        all_buttons.update(app_buttons)

        # 5) أزرار نظام البوتات (inline)
        bot_buttons = ['➕ إضافة بوت جديد', '🔄 تحديث القائمة', '🔙 العودة للوحة الأدمن']
        all_buttons.update(bot_buttons)

        # 6) أزرار تسجيل الدخول
        login_buttons = ['📝 تسجيل حساب جديد', '🔐 تسجيل الدخول برقم الهاتف', '⏭️ تخطي التسجيل']
        all_buttons.update(login_buttons)

        # 7) أزرار تم تعديلها سابقاً
        try:
            for original in getattr(self, 'button_labels', {}).keys():
                if original:
                    all_buttons.add(original)
        except:
            pass

        if not all_buttons:
            self.send_message(chat_id, "⚠️ لا توجد أزرار متاحة للتعديل حالياً.", self.admin_keyboard())
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
        if text in ['إلغاء', 'الغاء', '❌ إلغاء', '❌ الغاء', 'cancel', 'الغاء العملية']:
            if user_id in self.temp_button_label_edit:
                del self.temp_button_label_edit[user_id]
            if user_id in self.user_states:
                del self.user_states[user_id]
            self.send_message(chat_id, "❌ تم إلغاء عملية تعديل مسمى الزر.", self.admin_keyboard())
            return

        # المرحلة 1: اختيار الزر من القائمة
        if state == 'choose_button_to_edit':
            if not text:
                self.send_message(chat_id, "❗ يرجى اختيار زر من القائمة.", self.admin_keyboard())
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
                self.send_message(chat_id, "❗ يرجى إرسال الاسم الجديد للزر.")
                return

            data = self.temp_button_label_edit.get(user_id, {})
            old_label = data.get('old')
            if not old_label:
                # في حالة فقدان السياق نبدأ من جديد
                self.send_message(chat_id, "⚠️ حدث خطأ بسيط في السياق، لنبدأ من جديد.", self.admin_keyboard())
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
                    "سيتم استخدام الاسم الجديد في جميع القوائم القادمة التي تحتوي على هذا الزر. ✨"
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
            admin_text = """👥 إدارة المديرين
            
🔧 الخيارات:

📋 عرض المديرين الحاليين
➕ إضافة مدير دائم
🕐 إضافة مدير مؤقت (بدور ومدة)
🎭 تخصيص صلاحيات مدير
➖ إزالة مدير
📊 إحصائيات المديرين"""

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
    ADMIN_ROLES = {
        'full': {
            'name': 'مدير كامل',
            'icon': '👑',
            'buttons': None,  # None = كل الأزرار متاحة
        },
        'transactions': {
            'name': 'مشرف معاملات',
            'icon': '💰',
            'buttons': [
                '📋 الطلبات المعلقة', '✅ طلبات مُوافقة',
                '👥 المستخدمين', '🔍 البحث',
                '📊 الإحصائيات', '📑 تقرير Excel',
            ],
        },
        'support': {
            'name': 'مشرف دعم',
            'icon': '🆘',
            'buttons': [
                '📨 الشكاوى', '🛠️ بيانات الدعم',
                '👥 المستخدمين', '🔍 البحث',
            ],
        },
        'companies': {
            'name': 'مشرف شركات',
            'icon': '🏢',
            'buttons': [
                '🏢 الشركات', '💳 وسائل الدفع',
                '📍 العناوين', '⚙️ الإعدادات', '🎨 الثيمات', '🌐 تغيير اللغة',
            ],
        },
    }

    def add_temp_admin(self, message, user_id_to_add, role='full', duration_hours=0):
            """إضافة مدير مؤقت — مع دور ومدة انتهاء"""
            try:
                if not user_id_to_add.isdigit():
                    self.send_message(message['chat']['id'], "❌ معرف المستخدم يجب أن يكون رقماً صحيحاً", self.admin_keyboard())
                    return
                
                user_id = int(user_id_to_add)
                
                if user_id in self.temp_admin_user_ids:
                    self.send_message(message['chat']['id'], f"⚠️ المستخدم {user_id_to_add} مدير مؤقت بالفعل", self.admin_keyboard())
                    return
                
                if user_id in self.admin_user_ids:
                    self.send_message(message['chat']['id'], f"⚠️ المستخدم {user_id_to_add} مدير دائم بالفعل", self.admin_keyboard())
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
                    expiry_display = f"{duration_hours} ساعة"
                else:
                    expiry_display = "حتى إعادة تشغيل النظام"

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

                success_msg = f"""✅ تم إضافة مدير مؤقت بنجاح!
                
🆔 {user_id_to_add}
🎭 الدور: {role_icon} {role_name}
⏰ المدة: {expiry_display}

💡 الصلاحيات حسب الدور المحدد"""

                self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                self.log_admin_action(message['from']['id'], "add_temp_admin",
                    f"user={user_id_to_add}, role={role}, duration={duration_hours}h")
                logger.info(f"تم إضافة مدير مؤقت: {user_id_to_add} (دور: {role}, مدة: {duration_hours}h)")
                
            except Exception as e:
                logger.error(f"خطأ في إضافة المدير المؤقت: {e}")
                self.send_message(message['chat']['id'], "❌ حدث خطأ أثناء إضافة المدير المؤقت", self.admin_keyboard())
        
    def remove_admin_user(self, message, user_id_to_remove):
            """إزالة مدير — مع منع إزالة النفس"""
            try:
                if not user_id_to_remove.isdigit():
                    self.send_message(message['chat']['id'], "❌ معرف المستخدم يجب أن يكون رقماً صحيحاً", self.admin_keyboard())
                    return
                
                user_id = int(user_id_to_remove)
                requester_id = message['from']['id']
                
                # أمان: منع إزالة النفس
                if user_id == requester_id:
                    self.send_message(message['chat']['id'], "⚠️ لا يمكنك إزالة نفسك!", self.admin_keyboard())
                    return
                
                # أمان: منع إزالة آخر أدمن دائم
                if user_id in self.admin_user_ids and len(self.admin_user_ids) <= 1:
                    self.send_message(message['chat']['id'], "⚠️ لا يمكن إزالة آخر مدير دائم!", self.admin_keyboard())
                    return
                
                removed = False
                admin_type = ""
                
                # إزالة من المديرين المؤقتين
                if user_id in self.temp_admin_user_ids:
                    self.temp_admin_user_ids.remove(user_id)
                    removed = True
                    admin_type = "مؤقت"
                
                # إزالة من المديرين الدائمين (للجلسة الحالية فقط)
                elif user_id in self.admin_user_ids:
                    self.admin_user_ids.remove(user_id)
                    removed = True
                    admin_type = "دائم (من الجلسة الحالية)"
                
                if removed:
                    success_msg = f"""✅ تم إزالة المدير بنجاح!
                    
    🆔 معرف المستخدم: {user_id_to_remove}
    🔧 نوع المدير: {admin_type}
    
    ⚠️ ملاحظة: إذا كان مديراً دائماً، سيتم استعادته عند إعادة تشغيل النظام إلا إذا تم إزالته من متغير البيئة ADMIN_USER_IDS"""
                    
                    self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    logger.info(f"تم إزالة مدير {admin_type}: {user_id_to_remove}")
                else:
                    self.send_message(message['chat']['id'], f"❌ المستخدم {user_id_to_remove} ليس مديراً", self.admin_keyboard())
                
            except Exception as e:
                logger.error(f"خطأ في إزالة المدير: {e}")
                self.send_message(message['chat']['id'], "❌ حدث خطأ أثناء إزالة المدير", self.admin_keyboard())
        
    def show_detailed_admin_list(self, message):
            """عرض قائمة المديرين المفصلة"""
            admin_text = "📋 قائمة المديرين المفصلة\n\n"
            
            # المديرين الدائمين
            if self.admin_user_ids:
                admin_text += "🔒 المديرين الدائمين:\n"
                for i, admin_id in enumerate(self.admin_user_ids, 1):
                    admin_text += f"   {i}. 🆔 {admin_id} (دائم)\n"
                admin_text += f"   📊 العدد: {len(self.admin_user_ids)}\n\n"
            
            # المديرين المؤقتين
            if self.temp_admin_user_ids:
                admin_text += "🕐 المديرين المؤقتين:\n"
                for i, admin_id in enumerate(self.temp_admin_user_ids, 1):
                    admin_text += f"   {i}. 🆔 {admin_id} (مؤقت)\n"
                admin_text += f"   📊 العدد: {len(self.temp_admin_user_ids)}\n\n"
            
            # المديرين من متغيرات البيئة
            if self.admin_ids:
                admin_text += "🌐 مديرين البيئة:\n"
                for i, admin_id in enumerate(self.admin_ids, 1):
                    admin_text += f"   {i}. 🆔 {admin_id} (بيئة)\n"
                admin_text += f"   📊 العدد: {len(self.admin_ids)}\n\n"
            
            total_admins = len(self.admin_user_ids) + len(self.temp_admin_user_ids) + len(self.admin_ids)
            admin_text += f"📈 إجمالي المديرين: {total_admins}"
            
            self.send_message(message['chat']['id'], admin_text, self.admin_keyboard())
        
    def prompt_add_permanent_admin(self, message):
            """طلب إضافة مدير دائم"""
            help_text = """➕ إضافة مدير دائم
            
    الصيغة: اضافة_ادمن معرف_المستخدم
    
    مثال: اضافة_ادمن 123456789
    
    💡 المدير الدائم:
    • يحتفظ بصلاحياته في الجلسة الحالية
    • يفقد الصلاحيات عند إعادة التشغيل إلا إذا تم إضافته لمتغير البيئة
    • لمعرفة معرف المستخدم: /myid"""
            
            self.send_message(message['chat']['id'], help_text, self.admin_keyboard())
        
    def prompt_add_temp_admin(self, message):
            """طلب إضافة مدير مؤقت — مع اختيار الدور والمدة"""
            help_text = """🕐 إضافة مدير مؤقت

الصيغة: ادمن_مؤقت معرف_المستخدم الدور المدة_بالساعات

🎭 الأدوار المتاحة:
• full — مدير كامل (كل الصلاحيات)
• transactions — مشرف معاملات (طلبات + موافقة/رفض + إحصائيات)
• support — مشرف دعم (شكاوى + دعم + بحث)
• companies — مشرف شركات (شركات + وسائل دفع + إعدادات)

⏰ المدة بالساعات (0 = حتى إعادة التشغيل):
• 1 = ساعة واحدة
• 24 = يوم كامل
• 168 = أسبوع

📋 أمثلة:
ادمن_مؤقت 123456789 full 24
ادمن_مؤقت 123456789 transactions 8
ادمن_مؤقت 123456789 support 0
ادمن_مؤقت 123456789 companies 48

💡 اكتب الأمر الآن:"""
            
            self.send_message(message['chat']['id'], help_text, self.admin_keyboard())
        
    def start_permission_editor(self, message):
            """بدء تخصيص صلاحيات مدير"""
            # عرض الأدوار الجاهزة
            roles_text = "🎭 تخصيص صلاحيات مدير\n\n"
            roles_text += "اختر دوراً جاهزاً أو خصص يدوياً:\n\n"
            for code, info in self.ADMIN_ROLES.items():
                icon = info['icon']
                name = info['name']
                if info['buttons'] is None:
                    roles_text += f"{icon} {name} ({code}) — كل الأزرار\n"
                else:
                    roles_text += f"{icon} {name} ({code}) — {len(info['buttons'])} أزرار\n"
            roles_text += "\n📋 الصيغة:\n"
            roles_text += "صلاحيات ID_المستخدم الدور\n\n"
            roles_text += "مثال:\n"
            roles_text += "صلاحيات 123456789 transactions"

            self.send_message(message['chat']['id'], roles_text, self.admin_keyboard())

    def set_admin_role(self, message, admin_id_str, role):
            """تعيين دور لمدير"""
            try:
                if role not in self.ADMIN_ROLES:
                    self.send_message(message['chat']['id'], "❌ دور غير صحيح. استخدم: full, transactions, support, companies", self.admin_keyboard())
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
                    f"✅ تم تعيين دور: {role_info['icon']} {role_info['name']}\nللمدير: {admin_id_str}",
                    self.admin_keyboard())
                logger.info(f"Set admin role {role} for {admin_id_str}")
            except Exception as e:
                logger.error(f"خطأ في تعيين دور المدير: {e}")
                self.send_message(message['chat']['id'], "❌ خطأ في تعيين الدور", self.admin_keyboard())

    def prompt_remove_admin(self, message):
            """طلب إزالة مدير"""
            help_text = """➖ إزالة مدير
            
    الصيغة: ازالة_ادمن معرف_المستخدم
    
    مثال: ازالة_ادمن 123456789
    
    ⚠️ ملاحظات مهمة:
    • يمكن إزالة المديرين المؤقتين والدائمين
    • المديرين الدائمين سيتم استعادتهم عند إعادة التشغيل
    • لإزالة دائمة، يجب تعديل متغير البيئة ADMIN_USER_IDS"""
            
            self.send_message(message['chat']['id'], help_text, self.admin_keyboard())
        
    def show_admin_statistics(self, message):
            """عرض إحصائيات المديرين"""
            stats_text = """📊 إحصائيات المديرين
            
    📈 الإحصائيات العامة:
    """
            
            # إحصائيات المديرين
            permanent_count = len(self.admin_user_ids)
            temp_count = len(self.temp_admin_user_ids)
            env_count = len(self.admin_ids)
            total_count = permanent_count + temp_count + env_count
            
            stats_text += f"🔒 مديرين دائمين: {permanent_count}\n"
            stats_text += f"🕐 مديرين مؤقتين: {temp_count}\n"
            stats_text += f"🌐 mديرين البيئة: {env_count}\n"
            stats_text += f"📊 إجمالي المديرين: {total_count}\n\n"
            
            # إحصائيات الأمان
            stats_text += "🔐 مستوى الأمان:\n"
            if total_count >= 3:
                stats_text += "🟢 ممتاز - عدد كافٍ من المديرين\n"
            elif total_count >= 2:
                stats_text += "🟡 جيد - يُنصح بإضافة مدير إضافي\n"
            else:
                stats_text += "🔴 منخفض - يُنصح بإضافة مديرين إضافيين\n"
            
            # توصيات
            stats_text += "\n💡 التوصيات:\n"
            if temp_count > permanent_count:
                stats_text += "• تحويل بعض المديرين المؤقتين إلى دائمين\n"
            if total_count < 2:
                stats_text += "• إضافة مديرين احتياطيين للطوارئ\n"
            if env_count == 0:
                stats_text += "• إضافة مدير في متغير البيئة للاستمرارية\n"
            
            self.send_message(message['chat']['id'], stats_text, self.admin_keyboard())
        
    def prompt_broadcast(self, message):
            """طلب الإرسال الجماعي — مع تأكيد"""
            broadcast_help = """📢 الإرسال الجماعي

⚠️ سيتم إرسال الرسالة لجميع المستخدمين النشطين.
اكتب رسالتك الآن:"""
            self.send_message(message['chat']['id'], broadcast_help)
            self.user_states[message['from']['id']] = 'admin_broadcasting'
        
    def prompt_ban_user(self, message):
            """طلب حظر مستخدم"""
            ban_help = """🚫 حظر مستخدم
    
    الصيغة: حظر رقم_العميل السبب
    
    مثال: حظر C123456 مخالفة الشروط"""
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
                                'ban_reason': row.get('ban_reason', 'غير محدد')
                            })
            except:
                pass
            
            unban_help = """✅ إلغاء حظر مستخدم
    
    📝 الصيغة الصحيحة:
    الغاء_حظر [رقم_العميل]
    أو: الغاء حظر [رقم_العميل]
    
    مثال:
    الغاء_حظر C810563"""
            
            if banned_users:
                unban_help += "\n\n🚫 المستخدمين المحظورين حالياً:\n"
                for user in banned_users:
                    unban_help += f"\n🆔 {user['customer_id']}\n"
                    unban_help += f"👤 {user['name']}\n"
                    unban_help += f"📝 السبب: {user['ban_reason']}\n"
                    unban_help += f"⚡ `الغاء_حظر {user['customer_id']}`\n"
                    unban_help += "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n"
            else:
                unban_help += "\n\n✅ لا يوجد مستخدمين محظورين حالياً"
            
            self.send_message(message['chat']['id'], unban_help, self.admin_keyboard())
        
    def prompt_add_company(self, message):
            """بدء معالج إضافة شركة التفاعلي"""
            help_text = """🏢 معالج إضافة شركة جديدة
            
    سأطلب منك المعلومات خطوة بخطوة:
    
    📝 أولاً، أرسل اسم الشركة:
    مثال: البنك الأهلي، مدى، STC Pay، فودافون كاش"""
            
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
                    f"✅ تم حفظ اسم الشركة: {text}\n\n🔧 الآن اختر نوع الخدمة:", 
                    service_keyboard)
                self.user_states[user_id] = 'adding_company_type'
                
            elif state == 'adding_company_type':
                # حفظ نوع الخدمة
                if text == '💳 إيداع فقط':
                    service_type = 'deposit'
                    service_display = 'إيداع فقط'
                elif text == '💰 سحب فقط':
                    service_type = 'withdraw'
                    service_display = 'سحب فقط'
                elif text == '🔄 إيداع وسحب معاً':
                    service_type = 'both'
                    service_display = 'إيداع وسحب'
                elif text == '❌ إلغاء':
                    del self.user_states[user_id]
                    if hasattr(self, 'temp_company_data') and user_id in self.temp_company_data:
                        del self.temp_company_data[user_id]
                    self.send_message(message['chat']['id'], "❌ تم إلغاء إضافة الشركة", self.admin_keyboard())
                    return
                else:
                    self.send_message(message['chat']['id'], "❌ اختر نوع الخدمة من الأزرار المتاحة")
                    return
                
                self.temp_company_data[user_id]['type'] = service_type
                self.temp_company_data[user_id]['type_display'] = service_display
                
                # طلب التفاصيل
                self.send_message(message['chat']['id'], 
                    f"✅ نوع الخدمة: {service_display}\n\n📋 الآن أرسل تفاصيل الشركة:\nمثال: محفظة إلكترونية، حساب بنكي رقم 1234567890، خدمة دفع رقمية")
                self.user_states[user_id] = 'adding_company_details'
                
            elif state == 'adding_company_details':
                # حفظ التفاصيل وطلب الأيقونة
                self.temp_company_data[user_id]['details'] = text
                self.send_message(message['chat']['id'], 
                    "🏷️ اختر أيقونة للشركة:\n\nاكتب اسم النوع أو الصق إيموجي:\n• bank → 🏦\n• wallet → 👛\n• phone → 📱\n• cash → 💵\n• card → 💳\n• stc → 📡\n• أو اكتب 'skip' للأيقونة الافتراضية")
                self.user_states[user_id] = 'adding_company_icon'
                
            elif state == 'adding_company_icon':
                # حفظ الأيقونة وطلب العنوان
                if text.lower().strip() in ['skip', 'تخطي', '']:
                    icon = '🏢'
                else:
                    icon = self.normalize_icon(text.strip(), default='🏢')
                self.temp_company_data[user_id]['icon'] = icon
                self.send_message(message['chat']['id'], 
                    "📍 أدخل عنوان السحب لهذه الشركة:\n(أو اكتب 'skip' لاستخدام العنوان العام)")
                self.user_states[user_id] = 'adding_company_address'
                
            elif state == 'adding_company_address':
                # حفظ العنوان وعرض الملخص
                if text.lower().strip() in ['skip', 'تخطي', '']:
                    address = ''
                else:
                    address = self.sanitize_input(text.strip())
                self.temp_company_data[user_id]['address'] = address
                
                company_data = self.temp_company_data[user_id]
                icon = company_data.get('icon', '🏢')
                address_display = company_data.get('address', '') or '(عنوان عام)'
                confirm_text = f"""📊 ملخص الشركة الجديدة:
    
    {icon} الاسم: {company_data['name']}
    ⚡ نوع الخدمة: {company_data['type_display']}
    📋 التفاصيل: {company_data['details']}
    📍 العنوان: {address_display}
    
    هل تريد حفظ هذه الشركة؟"""
                
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
                
                if text == '✅ حفظ الشركة':
                    # تجنب تشغيل نفس الكود مرتين - هذا يُعالج الآن في handle_admin_actions
                    pass
                        
                elif text == '❌ إلغاء':
                    del self.user_states[user_id]
                    if user_id in self.temp_company_data:
                        del self.temp_company_data[user_id]
                    self.send_message(message['chat']['id'], "❌ تم إلغاء إضافة الشركة", self.admin_keyboard())
                    
                elif text == '🔄 تعديل الاسم':
                    self.send_message(message['chat']['id'], f"📝 الاسم الحالي: {company_data['name']}\n\nأرسل الاسم الجديد:")
                    self.user_states[user_id] = 'adding_company_name'
                    
                elif text == '🔧 تعديل النوع':
                    service_keyboard = {
                        'keyboard': [
                            [{'text': '💳 إيداع فقط'}, {'text': '💰 سحب فقط'}],
                            [{'text': '🔄 إيداع وسحب معاً'}],
                            [{'text': '❌ إلغاء'}]
                        ],
                        'resize_keyboard': True,
                        'one_time_keyboard': True
                    }
                    self.send_message(message['chat']['id'], f"🔧 النوع الحالي: {company_data['type_display']}\n\nاختر النوع الجديد:", service_keyboard)
                    self.user_states[user_id] = 'adding_company_type'
                    
                elif text == '📝 تعديل التفاصيل':
                    self.send_message(message['chat']['id'], f"📋 التفاصيل الحالية: {company_data['details']}\n\nأرسل التفاصيل الجديدة:")
                    self.user_states[user_id] = 'adding_company_details'
                    
                else:
                    self.send_message(message['chat']['id'], "❌ اختر من الأزرار المتاحة")
        
    def prompt_edit_company(self, message):
            """بدء معالج تعديل الشركة"""
            # عرض الشركات المتاحة للتعديل
            companies_text = "🔧 تعديل الشركات:\n\n"
            
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        status = "✅" if row.get('is_active') == 'active' else "❌"
                        companies_text += f"{status} {row['id']} - {row['name']}\n"
                        companies_text += f"   📋 {row['type']} - {row['details']}\n\n"
            except:
                companies_text += "❌ لا توجد شركات\n\n"
            
            companies_text += "📝 أرسل رقم معرف الشركة التي تريد تعديلها:"
            
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
                    self.send_message(message['chat']['id'], f"❌ لم يتم العثور على شركة بالمعرف: {text}")
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
                if text == '📝 تعديل الاسم':
                    current_name = self.edit_company_data[user_id]['name']
                    self.send_message(message['chat']['id'], f"📝 الاسم الحالي: {current_name}\n\nأرسل الاسم الجديد:")
                    self.user_states[user_id] = 'editing_company_name'
                    
                elif text == '🔧 تعديل النوع':
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
                    self.send_message(message['chat']['id'], f"🔧 النوع الحالي: {current_type}\n\nاختر النوع الجديد:", service_keyboard)
                    self.user_states[user_id] = 'editing_company_type'
                    
                elif text == '📋 تعديل التفاصيل':
                    current_details = self.edit_company_data[user_id]['details']
                    self.send_message(message['chat']['id'], f"📋 التفاصيل الحالية: {current_details}\n\nأرسل التفاصيل الجديدة:")
                    self.user_states[user_id] = 'editing_company_details'
                    
                elif text == '🔘 تغيير الحالة':
                    current_status = self.edit_company_data[user_id].get('is_active', 'active')
                    new_status = 'inactive' if current_status == 'active' else 'active'
                    status_text = 'نشط' if new_status == 'active' else 'غير نشط'
                    
                    self.edit_company_data[user_id]['is_active'] = new_status
                    self.send_message(message['chat']['id'], f"✅ تم تغيير حالة الشركة إلى: {status_text}")
                    self.show_edit_menu(message, user_id)
                    
                elif text == '📍 تعديل العنوان':
                    current_address = self.edit_company_data[user_id].get('address', '') or ''
                    self.send_message(message['chat']['id'],
                        f"📍 العنوان الحالي: {current_address or 'غير محدد'}\n\n"
                        "أرسل العنوان الجديد:\n"
                        "(هذا العنوان يظهر للعميل أثناء عملية السحب)\n\n"
                        "أو اكتب 'حذف' لإزالة العنوان")
                    self.user_states[user_id] = 'editing_company_address'
                    
                elif text == '💳 ربط وسائل الدفع':
                    self.show_company_payment_methods_link(message, user_id)
                    
                elif text == '✅ حفظ التغييرات':
                    self.save_company_changes(message)
                    
                elif text == '❌ إلغاء':
                    del self.user_states[user_id]
                    if user_id in self.edit_company_data:
                        del self.edit_company_data[user_id]
                    self.send_message(message['chat']['id'], "❌ تم إلغاء تعديل الشركة", self.admin_keyboard())
                    
            elif state == 'editing_company_name':
                self.edit_company_data[user_id]['name'] = text
                self.send_message(message['chat']['id'], f"✅ تم تحديث الاسم إلى: {text}")
                self.show_edit_menu(message, user_id)
                
            elif state == 'editing_company_type':
                if text == '💳 إيداع فقط':
                    self.edit_company_data[user_id]['type'] = 'deposit'
                    self.send_message(message['chat']['id'], "✅ تم تحديث النوع إلى: إيداع فقط")
                elif text == '💰 سحب فقط':
                    self.edit_company_data[user_id]['type'] = 'withdraw'
                    self.send_message(message['chat']['id'], "✅ تم تحديث النوع إلى: سحب فقط")
                elif text == '🔄 إيداع وسحب معاً':
                    self.edit_company_data[user_id]['type'] = 'both'
                    self.send_message(message['chat']['id'], "✅ تم تحديث النوع إلى: إيداع وسحب")
                elif text == '↩️ العودة للقائمة':
                    pass
                else:
                    self.send_message(message['chat']['id'], "❌ اختر نوع الخدمة من الأزرار المتاحة")
                    return
                
                self.show_edit_menu(message, user_id)
                
            elif state == 'editing_company_details':
                self.edit_company_data[user_id]['details'] = text
                self.send_message(message['chat']['id'], f"✅ تم تحديث التفاصيل إلى: {text}")
                self.show_edit_menu(message, user_id)
                
            elif state == 'editing_company_address':
                if text.lower() in ['حذف', 'delete', 'مسح']:
                    self.edit_company_data[user_id]['address'] = ''
                    self.send_message(message['chat']['id'], "✅ تم حذف العنوان")
                else:
                    self.edit_company_data[user_id]['address'] = text
                    self.send_message(message['chat']['id'], f"✅ تم تحديث العنوان إلى: {text}")
                self.show_edit_menu(message, user_id)
        
    def show_company_payment_methods_link(self, message, user_id):
        """عرض وسائل الدفع المرتبطة بالشركة وربط/فصل وسائل"""
        company = self.edit_company_data.get(user_id, {})
        company_id = company.get('id', '')
        
        # جلب كل وسائل الدفع
        all_methods = []
        try:
            with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                all_methods = list(reader)
        except:
            pass
        
        # وسائل مرتبطة بهذه الشركة
        linked = [m for m in all_methods if m.get('company_id') == company_id]
        unlinked = [m for m in all_methods if m.get('company_id') != company_id and m.get('status') == 'active']
        
        text = f"💳 وسائل الدفع للشركة: {company.get('name', '')}\n\n"
        
        if linked:
            text += "✅ وسائل مرتبطة:\n"
            for m in linked:
                icon = m.get('icon', '💳') or '💳'
                text += f"  {icon} {m['method_name']} (ID: {m['id']})\n"
        else:
            text += "📭 لا توجد وسائل دفع مرتبطة\n"
        
        if unlinked:
            text += "\n📋 وسائل متاحة للربط:\n"
            for m in unlinked:
                icon = m.get('icon', '💳') or '💳'
                text += f"  {icon} {m['method_name']} (ID: {m['id']})\n"
        
        text += "\n➕ للربط: اكتب <code>ربط_وسيلة [وسيلة_ID]</code>\n"
        text += "➖ للفصل: اكتب <code>فصل_وسيلة [وسيلة_ID]</code>\n"
        text += "أو اكتب 'رجوع' للعودة"
        
        kb = {
            'keyboard': [[{'text': '↩️ رجوع'}]],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        self.send_message(message['chat']['id'], text, kb)
        self.user_states[user_id] = f'editing_company_payment_link_{company_id}'
    
    def show_edit_menu(self, message, user_id):
            """عرض قائمة تعديل الشركة"""
            company_data = self.edit_company_data[user_id]
            type_display = {'deposit': 'إيداع فقط', 'withdraw': 'سحب فقط', 'both': 'إيداع وسحب'}.get(company_data['type'], company_data['type'])
            address = company_data.get('address', '') or 'غير محدد'
            
            edit_options = f"""📊 بيانات الشركة المحدثة:
    
    🆔 المعرف: {company_data['id']}
    🏢 الاسم: {company_data['name']}
    ⚡ النوع: {type_display}
    📋 التفاصيل: {company_data['details']}
    📍 العنوان: {address}
    🔘 الحالة: {'نشط' if company_data.get('is_active') == 'active' else 'غير نشط'}
    
    ماذا تريد تعديل؟"""
            
            edit_keyboard = {
                'keyboard': [
                    [{'text': '📝 تعديل الاسم'}, {'text': '🔧 تعديل النوع'}],
                    [{'text': '📋 تعديل التفاصيل'}, {'text': '📍 تعديل العنوان'}],
                    [{'text': '💳 ربط وسائل الدفع'}, {'text': '🔘 تغيير الحالة'}],
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
                    fieldnames = reader.fieldnames or ['id', 'name', 'type', 'details', 'is_active', 'icon', 'address']
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
            companies_text = "🏢 إدارة الشركات\n\n"
            
            try:
                companies = []
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    companies = list(reader)
                
                if len(companies) == 0:
                    companies_text += "❌ لا توجد شركات مسجلة\n\n"
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
            
            companies_text += """🔧 خيارات الإدارة:
    • ➕ إضافة شركة جديدة - معالج تفاعلي خطوة بخطوة
    • ✏️ تعديل شركة - تعديل البيانات الموجودة
    • 🗑️ حذف شركة - حذف نهائي بأمان
    • 🔄 تحديث القائمة - إعادة تحميل البيانات"""
            
            self.send_message(message['chat']['id'], companies_text, management_keyboard)
        
    def prompt_delete_company(self, message):
            """بدء معالج حذف الشركة بأمان"""
            companies_text = "🗑️ حذف الشركات:\n\n"
            
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        status = "✅" if row.get('is_active') == 'active' else "❌"
                        companies_text += f"{status} {row['id']} - {row['name']}\n"
                        companies_text += f"   📋 {row['type']} - {row['details']}\n\n"
            except:
                companies_text += "❌ لا توجد شركات\n\n"
            
            companies_text += "⚠️ أرسل رقم معرف الشركة للحذف:\n(تحذير: الحذف نهائي ولا يمكن التراجع عنه)"
            
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
                self.send_message(message['chat']['id'], f"❌ لم يتم العثور على شركة بالمعرف: {company_id}")
                del self.user_states[user_id]
                return
            
            # عرض تأكيد الحذف
            confirm_text = f"""⚠️ تأكيد حذف الشركة:
    
    🆔 المعرف: {company_found['id']}
    🏢 الاسم: {company_found['name']}
    📋 النوع: {company_found['type']}
    📝 التفاصيل: {company_found['details']}
    
    ⚠️ هذا الإجراء نهائي ولا يمكن التراجع عنه!
    هل أنت متأكد من الحذف؟"""
            
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
            
            if text == '🗑️ نعم، احذف الشركة':
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
                        success_msg = f"""✅ تم حذف الشركة بنجاح!
    
    🗑️ الشركة المحذوفة:
    🆔 المعرف: {deleted_company['id']}
    🏢 الاسم: {deleted_company['name']}
    📋 النوع: {deleted_company['type']}"""
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], "❌ فشل في العثور على الشركة للحذف", self.admin_keyboard())
                        
                except Exception as e:
                    self.send_message(message['chat']['id'], f"❌ فشل في حذف الشركة: {str(e)}", self.admin_keyboard())
            
            elif text == '❌ إلغاء':
                self.send_message(message['chat']['id'], "❌ تم إلغاء حذف الشركة", self.admin_keyboard())
            
            # تنظيف الحالة
            del self.user_states[user_id]
        
    def show_quick_copy_commands(self, message):
            """عرض أوامر نسخ سريعة للأدمن"""
            commands_text = """📋 أوامر نسخ سريعة:
    
    🔥 **أوامر الموافقة والرفض:**
    • `موافقة DEP123456`
    • `موافق DEP123456`
    • `تأكيد DEP123456`
    • `نعم DEP123456`
    
    • `رفض DEP123456 مبلغ غير صحيح`
    • `لا DEP123456 بيانات ناقصة`
    • `مرفوض WTH789012 رقم محفظة خطأ`
    
    💼 **أوامر إدارة الشركات:**
    • `اضافة_شركة البنك_الأهلي deposit حساب_بنكي_123456789`
    • `اضافة_شركة فودافون_كاش both محفظة_الكترونية`
    • `حذف_شركة 1737570855`
    
    💳 **أوامر وسائل الدفع:**
    • `اضافة_وسيلة_دفع 1 بنك_الأهلي حساب_بنكي SA123456789012345678`
    • `حذف_وسيلة_دفع 123456`
    • `تعديل_وسيلة_دفع 123456 SA987654321098765432`
    
    📧 **أوامر الرسائل:**
    • النقر على "📧 إرسال رسالة لعميل" ثم إدخال رقم العميل
    
    👥 **أوامر إدارة المستخدمين:**
    • `بحث أحمد`
    • `بحث C123456`
    • `حظر C123456 مخالفة الشروط`
    • `الغاء_حظر C123456`
    
    📨 **أوامر الشكاوى:**
    • `رد_شكوى 123 شكراً لتواصلك`
    • `رد_شكوى 456 تم حل مشكلتك`
    • `رد_شكوى 789 نراجع طلبك`
    
    🏢 **أوامر أخرى:**
    • `عنوان_جديد شارع الملك فهد الرياض`
    • `تعديل_اعداد min_deposit 100`
    
    💡 **نصائح للاستخدام:**
    • انقر على أي أمر واختر 'نسخ'
    • غير الأرقام والنصوص حسب الحاجة
    • استخدم _ بدلاً من المسافات في أسماء الشركات"""
            
            self.send_message(message['chat']['id'], commands_text, self.admin_keyboard())
        
    def get_payment_methods_by_company(self, company_id, transaction_type=None):
            """الحصول على وسائل الدفع لشركة معينة"""
            methods = []
            try:
                with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if (row['company_id'] == str(company_id) and 
                            row['status'] == 'active'):
                            methods.append(row)
            except:
                pass
            return methods
        
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
                title = "💳 <b>اختر وسيلة الدفع</b>\n\n"
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
        
    def add_payment_method(self, company_id, method_name, method_type, account_data, additional_info="", icon=""):
            """إضافة وسيلة دفع جديدة"""
            try:
                # إنشاء ID جديد  
                new_id = int(datetime.now().timestamp() * 1000) % 1000000
                # تطبيع الأيقونة
                method_icon = self.normalize_icon(icon or method_type, default='💳')
                # إضافة الوسيلة الجديدة
                with open('payment_methods.csv', 'a', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        new_id,
                        company_id,
                        method_name,
                        method_type,
                        account_data,
                        additional_info,
                        'active',
                        datetime.now().strftime('%Y-%m-%d'),
                        method_icon
                    ])
                return True
            except:
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
            wizard_text = """🧙‍♂️ معالج إضافة الشركة
    
    سأساعدك في إضافة شركة بطريقة سهلة!
    
    📝 أولاً: ما اسم الشركة؟
    (مثال: بنك الراجحي، فودافون كاش، مدى)"""
            
            self.send_message(message['chat']['id'], wizard_text)
            self.user_states[message['from']['id']] = 'adding_company_name'
        
    def handle_add_company_wizard(self, message, text):
            """معالجة معالج إضافة الشركة"""
            user_id = message['from']['id']
            state = self.user_states.get(user_id, '')
            
            if state == 'adding_company_name':
                company_name = text.strip()
                if len(company_name) < 2:
                    self.send_message(message['chat']['id'], "❌ اسم قصير جداً. أدخل اسم الشركة:")
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
                
                self.send_message(message['chat']['id'], f"✅ اسم الشركة: {company_name}\n\n🔹 اختر نوع الخدمة:", service_keyboard)
                self.user_states[user_id] = f'adding_company_type_{company_name}'
                
            elif state.startswith('adding_company_type_'):
                company_name = state.replace('adding_company_type_', '')
                
                if text == '❌ إلغاء':
                    self.send_message(message['chat']['id'], "تم إلغاء إضافة الشركة", self.admin_keyboard())
                    del self.user_states[user_id]
                    return
                
                # تحديد نوع الخدمة
                if text == '💰 إيداع فقط':
                    service_type = 'deposit'
                    service_ar = 'إيداع فقط'
                elif text == '💸 سحب فقط':
                    service_type = 'withdraw'
                    service_ar = 'سحب فقط'
                elif text == '🔄 إيداع وسحب معاً':
                    service_type = 'both'
                    service_ar = 'إيداع وسحب'
                else:
                    self.send_message(message['chat']['id'], "❌ اختر من الأزرار المتاحة:")
                    return
                
                self.send_message(message['chat']['id'], f"""✅ تم اختيار: {service_ar}
    
    📝 الآن أدخل تفاصيل الشركة:
    (مثال: حساب بنكي رقم 1234567890، محفظة إلكترونية، خدمات دفع متعددة)""")
                
                self.user_states[user_id] = f'adding_company_details_{company_name}_{service_type}'
                
            elif state.startswith('adding_company_details_'):
                parts = state.replace('adding_company_details_', '').rsplit('_', 1)
                company_name = parts[0]
                service_type = parts[1]
                details = text.strip()
                
                if len(details) < 3:
                    self.send_message(message['chat']['id'], "❌ تفاصيل قصيرة جداً. أدخل وصف مناسب:")
                    return
                
                # إنشاء الشركة
                company_id = str(int(datetime.now().timestamp()))
                
                try:
                    with open('companies.csv', 'a', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow([company_id, company_name, service_type, details, 'active', '🏢', ''])
                    
                    service_ar = "إيداع فقط" if service_type == 'deposit' else "سحب فقط" if service_type == 'withdraw' else "إيداع وسحب"
                    
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
            companies_text = "🏢 إدارة الشركات:\n\n"
            
            try:
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        status = "✅" if row.get('is_active') == 'active' else "❌"
                        companies_text += f"{status} {row['id']} - {row['name']}\n"
                        companies_text += f"   📋 {row['type']} - {row['details']}\n\n"
            except:
                pass
            
            companies_text += "📝 الأوامر:\n"
            companies_text += "• اضافة_شركة اسم نوع تفاصيل\n"
            companies_text += "• حذف_شركة رقم_المعرف\n"
            
            self.send_message(message['chat']['id'], companies_text, self.admin_keyboard())
        
    def show_addresses_management(self, message):
            """عرض إدارة العناوين"""
            current_address = self.get_exchange_address()
            
            address_text = f"""📍 إدارة عناوين الصرافة
    
    العنوان الحالي:
    {current_address}
    
    لتغيير العنوان:
    عنوان_جديد النص_الجديد_للعنوان
    
    مثال:
    عنوان_جديد شارع الملك فهد، الرياض، مقابل برج المملكة"""
            
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
            text = "⚙️ <b>إعدادات النظام</b>\n\n"
            text += "━━━━━━━━━━━━━━━━━━\n\n"

            # المجموعات
            groups = {
                '💰 المعاملات': ['min_deposit', 'max_daily_withdrawal', 'default_currency'],
                '🔐 الأمان': ['rate_limit_per_minute', 'session_timeout'],
                '🎨 المظهر': ['active_theme'],
            }

            inline_btns = []
            for group_name, keys in groups.items():
                text += f"<b>{group_name}</b>\n"
                row = []
                for key in keys:
                    val = settings.get(key, 'غير محدد')
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
                text += "<b>📋 أخرى</b>\n"
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
                    text += f"   ⏰ تجميد في: <b>{freeze}</b>\n"
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

        if text in ['❌ إلغاء', '🔙 لوحة الأدمن', 'إلغاء', 'الغاء']:
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
                self.send_message(chat_id, "❌ الاسم قصير جداً. اكتب اسماً صحيحاً:")
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
                self.send_message(chat_id, "❌ توكن غير صحيح. يجب أن يحتوي على نقطتين (:) ويكون طويلاً.\n\n الصق التوكن مرة أخرى:")
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
            if text.lower() in ['أنا', 'ana', 'me', 'انا']:
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
            if text.lower() in ['تخطي', 'skip', 'بدون']:
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
            can_manage = 'yes' if text.lower() in ['نعم', 'yes', 'اى', 'اي'] else 'no'

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
                    summary += f"🧊 تجميد في: <b>{data['freeze_date']}</b>\n"
                summary += f"🤖 إدارة البوتات: <b>{'✅ مفعّل' if can_manage == 'yes' else '❌ غير مفعّل'}</b>\n"

                inline_btns = [
                    [{'text': f'▶️ تفعيل وتشغيل', 'callback_data': f'mbot_start_{bot_id}'}],
                    [{'text': '📋 عرض كل البوتات', 'callback_data': 'mbot_refresh'}],
                    [{'text': '➕ إضافة بوت آخر', 'callback_data': 'mbot_add_wizard'}],
                    [{'text': '🔙 لوحة الأدمن', 'callback_data': 'mbot_back_admin'}]
                ]
                self.send_inline_message(chat_id, summary, inline_btns)
            else:
                self.send_message(chat_id, "❌ فشل في إضافة البوت", self.admin_keyboard())

            if user_id in self.user_states:
                del self.user_states[user_id]
            if hasattr(self, 'temp_mbot_data') and user_id in self.temp_mbot_data:
                del self.temp_mbot_data[user_id]

    def mbot_show_admins(self, chat_id, bot_id):
        """عرض أدمن البوت وإدارة الأدمن"""
        manager = MultiBotManager()
        bot = manager.get_bot_by_id(bot_id)
        if not bot:
            self.send_message(chat_id, "❌ البوت غير موجود")
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
        text += "➕ للإضافة: <code>اضافة_ادمن_بوت BOT123 99999999</code>\n"
        text += "➖ للحذف: <code>حذف_ادمن_بوت BOT123 99999999</code>"

        inline_btns = [
            [{'text': '🔙 العودة', 'callback_data': 'mbot_refresh'}]
        ]
        self.send_inline_message(chat_id, text, inline_btns)

    def show_theme_panel(self, message):
        """عرض لوحة الثيمات للأدمن"""
        if not THEME_AVAILABLE:
            self.send_message(message['chat']['id'], "❌ نظام الثيمات غير متاح", self.admin_keyboard())
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
            marker = ' ◀ نشط' if key == current_theme else ''
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
                    self.send_message(message['chat']['id'], "✅ لا توجد شكاوى معلقة", self.admin_keyboard())
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
                self.send_message(message['chat']['id'], f"❌ خطأ في قراءة الشكاوى: {e}", self.admin_keyboard())
        
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
                self.send_message(message['chat']['id'], f"❌ لم يتم العثور على الشكوى {complaint_id}", self.admin_keyboard())
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
            payment_text = """💳 وسائل الدفع المتاحة
    
    هذا القسم يعرض الشركات المتاحة للإيداع والسحب.
    استخدم 'إدارة الشركات' لإضافة أو تعديل وسائل الدفع."""
            
            companies = self.get_companies()
            for company in companies:
                service_type = "إيداع وسحب" if company['type'] == 'both' else "إيداع" if company['type'] == 'deposit' else "سحب"
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
                    
                    self.send_message(message['chat']['id'], f"✅ تم حظر العميل {customer_id}\nالسبب: {reason}", self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ لم يتم العثور على العميل {customer_id}", self.admin_keyboard())
            except:
                self.send_message(message['chat']['id'], "❌ فشل في حظر المستخدم", self.admin_keyboard())
        
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
                    
                    self.send_message(message['chat']['id'], f"✅ تم إلغاء حظر العميل {customer_id}", self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ لم يتم العثور على العميل {customer_id}", self.admin_keyboard())
            except:
                self.send_message(message['chat']['id'], "❌ فشل في إلغاء حظر المستخدم", self.admin_keyboard())
        
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
                    
                    self.send_message(message['chat']['id'], f"✅ تم حذف الشركة: {deleted_name} (ID: {company_id})", self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ لم يتم العثور على شركة بالمعرف: {company_id}", self.admin_keyboard())
            except:
                self.send_message(message['chat']['id'], "❌ فشل في حذف الشركة", self.admin_keyboard())
        
    def update_setting_simple(self, message, text):
            """تحديث إعداد النظام"""
            # تنسيق: تعديل_اعداد مفتاح_الإعداد القيمة_الجديدة
            parts = text.replace('تعديل_اعداد ', '').split(' ', 1)
            if len(parts) < 2:
                help_text = """❌ تنسيق خاطئ
    
    الصيغة الصحيحة:
    تعديل_اعداد مفتاح_الإعداد القيمة_الجديدة
    
    مثال:
    تعديل_اعداد min_deposit 100"""
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
                    
                    self.send_message(message['chat']['id'], f"✅ تم تحديث الإعداد:\n{setting_key} = {setting_value}", self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ لم يتم العثور على الإعداد: {setting_key}", self.admin_keyboard())
            except:
                self.send_message(message['chat']['id'], "❌ فشل في تحديث الإعداد", self.admin_keyboard())
        
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
                self.send_message(message['chat']['id'], "❌ فشل في إرسال الشكوى. حاول مرة أخرى", self.main_keyboard(user.get('language', 'ar')))
                if message['from']['id'] in self.user_states:
                    del self.user_states[message['from']['id']]
        
    def send_broadcast_message(self, message, broadcast_text):
            """إرسال رسالة جماعية"""
            sent_count = 0
            failed_count = 0
            
            try:
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    users = list(reader)
                
                # إرسال للمستخدمين النشطين فقط
                for user in users:
                    if user.get('is_banned') != 'yes':
                        try:
                            broadcast_msg = f"""📢 رسالة من الإدارة
    
    {broadcast_text}
    
    📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
                            
                            # إرسال الرسالة بدون لوحة مفاتيح حتى لا تؤثر على الأزرار الحالية
                            result = self.send_message(user['telegram_id'], broadcast_msg, None)
                            if result and result.get('ok'):
                                sent_count += 1
                            else:
                                failed_count += 1
                        except:
                            failed_count += 1
                
                summary = f"""✅ تم إرسال الرسالة الجماعية
    
    📊 الإحصائيات:
    • تم الإرسال بنجاح: {sent_count}
    • فشل في الإرسال: {failed_count}
    • إجمالي المحاولات: {sent_count + failed_count}
    
    📝 الرسالة: {broadcast_text}"""
                
                self.send_message(message['chat']['id'], summary, self.admin_keyboard())
                del self.user_states[message['from']['id']]
            except:
                self.send_message(message['chat']['id'], "❌ فشل في الإرسال الجماعي", self.admin_keyboard())
                del self.user_states[message['from']['id']]
    
    def show_approved_transactions(self, message):
            """عرض المعاملات المُوافق عليها"""
            approved_text = "✅ المعاملات المُوافق عليها (آخر 20 معاملة):\n\n"
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
                            approved_text += f"💰 {row['amount']} ريال\n"
                            approved_text += f"📅 {row['date']}\n\n"
            except:
                pass
            
            if not found_approved:
                approved_text += "لا توجد معاملات مُوافق عليها"
            
            self.send_message(message['chat']['id'], approved_text, self.admin_keyboard())
        
    def show_users_management(self, message):
            """عرض إدارة المستخدمين"""
            users_text = "👥 إدارة المستخدمين:\n\n"
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
            
            users_text += f"✅ مستخدمون نشطون: {active_count}\n"
            users_text += f"🚫 مستخدمون محظورون: {banned_count}\n\n"
            
            users_text += "📝 الأوامر المتاحة:\n"
            users_text += "• بحث اسم_أو_رقم_العميل\n"
            users_text += "• حظر رقم_العميل السبب\n"
            users_text += "• الغاء_حظر رقم_العميل\n\n"
            
            users_text += "مثال:\nبحث أحمد\nحظر C123456 مخالفة_الشروط"
            
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
                self.send_message(message['chat']['id'], f"❌ لم يتم العثور على نتائج للبحث: {query}", self.admin_keyboard())
                return
            
            search_text = f"🔍 نتائج البحث عن: {query}\n\n"
            for user in results[:10]:  # أول 10 نتائج فقط
                status = "🚫 محظور" if user.get('is_banned') == 'yes' else "✅ نشط"
                search_text += f"👤 {user['name']}\n"
                search_text += f"🆔 {user['customer_id']}\n"
                search_text += f"📱 {user['phone']}\n"
                search_text += f"🔸 {status}\n"
                if user.get('is_banned') == 'yes' and user.get('ban_reason'):
                    search_text += f"📝 سبب الحظر: {user['ban_reason']}\n"
                search_text += "\n"
            
            self.send_message(message['chat']['id'], search_text, self.admin_keyboard())
        
    def start_simple_payment_method_wizard(self, message):
            """معالج مبسط لإضافة وسيلة دفع"""
            user_id = message['from']['id']
            
            # عرض الشركات المتاحة
            companies = self.get_companies()
            if not companies:
                self.send_message(message['chat']['id'], 
                                "❌ لا توجد شركات متاحة. يجب إضافة شركة أولاً", 
                                self.admin_keyboard())
                return
            
            companies_text = "🏢 اختر الشركة لإضافة وسيلة دفع:\n\n"
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
                self.send_message(message['chat']['id'], "❌ لا توجد وسائل دفع متاحة", self.admin_keyboard())
                return
            
            methods_text = "✏️ اختر وسيلة الدفع للتعديل:\n\n"
            keyboard = []
            
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                
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
                self.send_message(message['chat']['id'], "❌ لا توجد وسائل دفع متاحة", self.admin_keyboard())
                return
            
            methods_text = "🗑️ اختر وسيلة الدفع للحذف:\n\n"
            keyboard = []
            
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                
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
                self.send_message(message['chat']['id'], "❌ لا توجد وسائل دفع مضافة بعد", self.admin_keyboard())
                return
            
            methods_text = "📊 وسائل الدفع المتاحة:\n\n"
            
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                status = "✅ نشط" if method['status'] == 'active' else "❌ متوقف"
                
                methods_text += f"🆔 {method['id']} - {method['method_name']}\n"
                methods_text += f"🏢 الشركة: {company_name}\n"
                methods_text += f"💳 النوع: {method['method_type']}\n"
                methods_text += f"💰 البيانات: {method['account_data']}\n"
                methods_text += f"📊 الحالة: {status}\n"
                if method['additional_info']:
                    methods_text += f"💡 معلومات: {method['additional_info']}\n"
                methods_text += "─────────────\n\n"
            
            methods_text += f"📈 إجمالي وسائل الدفع: {len(methods)}"
            
            self.send_message(message['chat']['id'], methods_text, self.admin_keyboard())
        
    def handle_simple_payment_company_selection(self, message):
            """معالجة اختيار الشركة في المعالج المبسط"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in ['🔙 العودة', '⬅️ العودة']:
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
                self.send_message(message['chat']['id'], "❌ شركة غير صحيحة. اختر من القائمة أعلاه")
                return
            
            # طلب بيانات وسيلة الدفع
            input_text = f"""📋 إضافة وسيلة دفع للشركة: {selected_company['name']}
    
    أدخل البيانات بالتنسيق التالي:
    اسم_الوسيلة | نوع_الوسيلة | رقم_الحساب | معلومات_إضافية
    
    مثال:
    بنك الأهلي | حساب بنكي | SA1234567890123456789 | حساب رئيسي
    أو
    فودافون كاش | محفظة إلكترونية | 01012345678 | للدفع السريع
    
    ⬅️ /cancel للإلغاء"""
            
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
                        company_name = company['name'] if company else 'غير محدد'
                        
                        success_msg = f"""✅ تم إضافة وسيلة الدفع بنجاح!
    
    🏢 الشركة: {company_name}
    📋 الاسم: {method_name}
    💳 النوع: {method_type}
    💰 البيانات: {account_data}
    💡 معلومات: {additional_info if additional_info else 'لا توجد'}"""
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], "❌ فشل في إضافة وسيلة الدفع", self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], "❌ تنسيق غير صحيح. يجب أن يحتوي على 3 أجزاء على الأقل مفصولة بـ |")
                    return
            else:
                self.send_message(message['chat']['id'], "❌ تنسيق غير صحيح. استخدم | للفصل بين البيانات")
                return
            
            # تنظيف الحالة
            if user_id in self.user_states:
                del self.user_states[user_id]
        
    def handle_simple_method_edit_selection(self, message):
            """معالجة اختيار وسيلة الدفع للتعديل المبسط"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in ['🔙 العودة', '⬅️ العودة']:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            if text.startswith('تعديل '):
                method_id = text.replace('تعديل ', '').strip()
                method = self.get_payment_method_by_id(method_id)
                
                if not method:
                    self.send_message(message['chat']['id'], "❌ وسيلة دفع غير موجودة")
                    return
                
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                
                edit_text = f"""✏️ تعديل وسيلة الدفع
    
    🆔 المعرف: {method['id']}
    🏢 الشركة: {company_name}
    📋 الاسم الحالي: {method['method_name']}
    💳 النوع الحالي: {method['method_type']}
    💰 البيانات الحالية: {method['account_data']}
    💡 المعلومات الحالية: {method['additional_info']}
    
    أدخل البيانات الجديدة بالتنسيق:
    اسم_جديد | نوع_جديد | رقم_حساب_جديد | معلومات_جديدة
    
    ⬅️ /cancel للإلغاء"""
                
                self.send_message(message['chat']['id'], edit_text)
                self.user_states[user_id] = f'editing_method_simple_{method_id}'
        
    def handle_simple_method_delete_selection(self, message):
            """معالجة اختيار وسيلة الدفع للحذف المبسط"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in ['🔙 العودة', '⬅️ العودة']:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            if text.startswith('حذف '):
                method_id = text.replace('حذف ', '').strip()
                
                # الحصول على بيانات الوسيلة قبل الحذف
                method_to_delete = self.get_payment_method_by_id(method_id)
                if not method_to_delete:
                    self.send_message(message['chat']['id'], f"❌ لم يتم العثور على وسيلة الدفع {method_id}", self.admin_keyboard())
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                    return
                
                # حذف وسيلة الدفع
                success, deleted_method = self.delete_payment_method(method_id)
                
                if success and deleted_method:
                    company = self.get_company_by_id(deleted_method['company_id'])
                    company_name = company['name'] if company else 'غير محدد'
                    
                    success_msg = f"""✅ تم حذف وسيلة الدفع بنجاح!
    
    🆔 المحذوفة: {deleted_method['id']}
    🏢 الشركة: {company_name}
    📋 الاسم: {deleted_method['method_name']}
    💳 النوع: {deleted_method['method_type']}"""
                    
                    self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ فشل في حذف وسيلة الدفع {method_id}", self.admin_keyboard())
                
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
                        self.send_message(message['chat']['id'], f"❌ لم يتم العثور على وسيلة الدفع رقم {method_id}", self.admin_keyboard())
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
                        company_name = company['name'] if company else 'غير محدد'
                        
                        success_msg = f"""✅ تم تعديل وسيلة الدفع بنجاح!
    
    🆔 المعرف: {method_id}
    🏢 الشركة: {company_name}
    📋 الاسم: {new_name}
    💳 النوع: {new_type}
    💰 البيانات: {new_account}
    💡 معلومات إضافية: {new_info if new_info else 'لا توجد'}"""
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], f"❌ فشل في تعديل وسيلة الدفع {method_id}", self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], "❌ تنسيق غير صحيح!\n\nالتنسيق المطلوب:\nاسم_الوسيلة | نوع_الوسيلة | رقم_الحساب | معلومات_إضافية\n\nمثال:\nفودافون كاش | محفظة إلكترونية | 01012345678 | للدفع السريع")
                    return
            else:
                self.send_message(message['chat']['id'], "❌ يجب استخدام | للفصل بين البيانات!\n\nمثال:\nفودافون كاش | محفظة إلكترونية | 01012345678 | للدفع السريع")
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
                text += "<b>قائمة الوسائل:</b>\n\n"
                for m in methods[:15]:
                    company = self.get_company_by_id(m.get('company_id', ''))
                    company_name = company['name'] if company else 'غير محدد'
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
                self.send_message(message['chat']['id'], "❌ لا توجد وسائل دفع نشطة لإيقافها", self.admin_keyboard())
                return
            
            methods_text = "⏹️ اختر وسيلة الدفع لإيقافها:\n\n"
            keyboard = []
            
            for method in active_methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                
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
                self.send_message(message['chat']['id'], "❌ جميع وسائل الدفع نشطة بالفعل", self.admin_keyboard())
                return
            
            methods_text = "▶️ اختر وسيلة الدفع لتشغيلها:\n\n"
            keyboard = []
            
            for method in inactive_methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                
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
            
            if text in ['🔙 العودة', '⬅️ العودة']:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            if text.startswith('إيقاف '):
                method_id = text.replace('إيقاف ', '').strip()
                success = self.toggle_payment_method_status(method_id, 'inactive')
                
                if success:
                    method = self.get_payment_method_by_id(method_id)
                    if method:
                        company = self.get_company_by_id(method['company_id'])
                        company_name = company['name'] if company else 'غير محدد'
                        
                        success_msg = f"""⏹️ تم إيقاف وسيلة الدفع بنجاح!
    
    🆔 المعرف: {method_id}
    🏢 الشركة: {company_name}
    📋 الاسم: {method['method_name']}
    💳 النوع: {method['method_type']}
    📊 الحالة: متوقفة ❌"""
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], f"❌ لم يتم العثور على وسيلة الدفع {method_id}", self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ فشل في إيقاف وسيلة الدفع {method_id}", self.admin_keyboard())
                
                if user_id in self.user_states:
                    del self.user_states[user_id]
        
    def handle_method_enable_selection(self, message):
            """معالجة اختيار وسيلة الدفع للتشغيل"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in ['🔙 العودة', '⬅️ العودة']:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_payment_methods_management(message)
                return
            
            if text.startswith('تشغيل '):
                method_id = text.replace('تشغيل ', '').strip()
                success = self.toggle_payment_method_status(method_id, 'active')
                
                if success:
                    method = self.get_payment_method_by_id(method_id)
                    if method:
                        company = self.get_company_by_id(method['company_id'])
                        company_name = company['name'] if company else 'غير محدد'
                        
                        success_msg = f"""▶️ تم تشغيل وسيلة الدفع بنجاح!
    
    🆔 المعرف: {method_id}
    🏢 الشركة: {company_name}
    📋 الاسم: {method['method_name']}
    💳 النوع: {method['method_type']}
    📊 الحالة: نشطة ✅"""
                        
                        self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                    else:
                        self.send_message(message['chat']['id'], f"❌ لم يتم العثور على وسيلة الدفع {method_id}", self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ فشل في تشغيل وسيلة الدفع {method_id}", self.admin_keyboard())
                
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
            methods_text = "💳 جميع وسائل الدفع:\n\n"
            
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
                        company_name = company_names.get(company_id, f"شركة #{company_id}")
                        methods_text += f"🏢 **{company_name}**:\n"
                        
                        for method in methods:
                            status_emoji = "✅" if method['status'] == 'active' else "⏹️"
                            status_text = "نشطة" if method['status'] == 'active' else "متوقفة"
                            methods_text += f"  {status_emoji} {method['method_name']} (#{method['id']}) - {status_text}\n"
                            methods_text += f"      📋 النوع: {method['method_type']}\n"
                            methods_text += f"      💳 البيانات: {method['account_data']}\n"
                            if method['additional_info']:
                                methods_text += f"      💡 ملاحظات: {method['additional_info']}\n"
                            methods_text += "\n"
                        methods_text += "▫️▫️▫️▫️▫️▫️▫️▫️\n\n"
            except:
                methods_text += "❌ خطأ في قراءة البيانات"
            
            # إضافة أوامر النسخ السريع
            methods_text += "\n📋 **أوامر إدارة سريعة:**\n"
            methods_text += "• `اضافة_وسيلة_دفع ID_الشركة اسم_الوسيلة نوع_الوسيلة البيانات`\n"
            methods_text += "• `تعديل_وسيلة_دفع ID_الوسيلة البيانات_الجديدة`\n"
            methods_text += "• `حذف_وسيلة_دفع ID_الوسيلة`\n\n"
            
            methods_text += "💡 **مثال:**\n"
            methods_text += "`اضافة_وسيلة_دفع 1 حساب_مدى bank_account رقم:1234567890`"
            
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
                                "❌ لا توجد شركات متاحة. يجب إضافة شركة أولاً", 
                                self.admin_keyboard())
                return
            
            companies_text = "🏢 اختر الشركة لإضافة وسيلة دفع لها:\n\n"
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
            if text in back_texts or text in ['🔙 العودة', '⬅️ العودة', '🔙 العودة لاختيار الشركة']:
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
            
            instruction_text = """📧 إرسال رسالة لعميل محدد
            
    📝 أدخل رقم العميل الذي تريد إرسال رسالة إليه:
    
    مثال: C824717
    
    💡 تأكد من كتابة الرقم بشكل صحيح (مع الحرف C)
    
    ⬅️ /cancel للإلغاء"""
            
            self.send_message(message['chat']['id'], instruction_text)
            self.user_states[user_id] = 'sending_user_message_id'
        
    def handle_user_message_id(self, message):
            """معالجة رقم العميل لإرسال الرسالة"""
            user_id = message['from']['id']
            customer_id = message.get('text', '').strip()
            
            if customer_id == '/cancel' or customer_id.lower() == 'cancel':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(message['chat']['id'], "✅ تم إلغاء إرسال الرسالة", self.admin_keyboard())
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
                                f"❌ لم يتم العثور على عميل برقم: {customer_id}\n\nيرجى التحقق من الرقم والمحاولة مرة أخرى:\n\n⬅️ /cancel للإلغاء")
                return
            
            # عرض معلومات العميل وطلب الرسالة
            customer_info = f"""✅ تم العثور على العميل:
    
    👤 الاسم: {user_found['name']}
    📱 الهاتف: {user_found['phone']}
    🆔 رقم العميل: {user_found['customer_id']}
    📅 تاريخ التسجيل: {user_found.get('registration_date', 'غير محدد')}
    🚫 الحالة: {'محظور' if user_found.get('is_banned') == 'yes' else 'نشط'}
    
    📝 الآن أدخل الرسالة التي تريد إرسالها لهذا العميل:
    
    ⬅️ /cancel للإلغاء"""
            
            self.send_message(message['chat']['id'], customer_info)
            self.user_states[user_id] = f'sending_user_message_{customer_id}'
        
    def handle_user_message_content(self, message, customer_id):
            """معالجة محتوى الرسالة وإرسالها"""
            user_id = message['from']['id']
            message_content = message.get('text', '').strip()
            
            if message_content == '/cancel' or message_content.lower() == 'cancel':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(message['chat']['id'], "✅ تم إلغاء إرسال الرسالة", self.admin_keyboard())
                return
            
            if not message_content:
                self.send_message(message['chat']['id'], "❌ الرسالة فارغة. يرجى كتابة الرسالة:")
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
                                f"❌ لم يتم العثور على معرف التليجرام للعميل {customer_id}\n\n💡 تأكد من أن العميل مسجل في النظام", 
                                self.admin_keyboard())
                if user_id in self.user_states:
                    del self.user_states[user_id]
                return
            
            # إرسال الرسالة للعميل بدون لوحة مفاتيح حتى لا تؤثر على الأزرار
            admin_info = self.find_user(user_id)
            admin_name = admin_info.get('name', 'الإدارة') if admin_info else 'الإدارة'
            
            customer_message = f"""📧 رسالة من الإدارة
    
    من: {admin_name}
    التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    
    ━━━━━━━━━━━━━━━━━━━━
    
    {message_content}
    
    ━━━━━━━━━━━━━━━━━━━━
    
    💬 للرد على هذه الرسالة، استخدم قسم الشكاوى في النظام"""
            
            # محاولة إرسال الرسالة بدون لوحة مفاتيح
            try:
                response = self.send_message(int(target_telegram_id), customer_message, None)
                
                # إشعار الأدمن بنجاح الإرسال
                success_msg = f"""✅ تم إرسال الرسالة بنجاح!
    
    📧 إلى العميل: {customer_name} ({customer_id})
    📅 وقت الإرسال: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    
    📝 محتوى الرسالة:
    {message_content}"""
                
                self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                
            except Exception as e:
                # فشل في الإرسال
                error_msg = f"""❌ فشل في إرسال الرسالة!
    
    🎯 العميل: {customer_name} ({customer_id})
    ⚠️ السبب: العميل قد يكون حظر البوت أو حذف المحادثة
    
    💡 يمكنك التواصل معه عبر:
    📱 الهاتف المسجل في النظام
    📧 البريد الإلكتروني (إن وجد)"""
                
                self.send_message(message['chat']['id'], error_msg, self.admin_keyboard())
            
            # حذف الحالة
            if user_id in self.user_states:
                del self.user_states[user_id]
        
    def start_edit_payment_method(self, message):
            """بدء تعديل وسيلة دفع"""
            user_id = message['from']['id']
            
            # عرض جميع وسائل الدفع للاختيار
            methods = self.get_all_payment_methods()
            
            if not methods:
                self.send_message(message['chat']['id'], 
                                "❌ لا توجد وسائل دفع في النظام حالياً", 
                                self.admin_keyboard())
                return
            
            methods_text = "✏️ اختر وسيلة الدفع للتعديل:\n\n"
            
            keyboard_buttons = []
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                
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
                                "❌ لا توجد وسائل دفع في النظام حالياً", 
                                self.admin_keyboard())
                return
            
            methods_text = "🗑️ اختر وسيلة الدفع للحذف:\n\n"
            
            keyboard_buttons = []
            for method in methods:
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                
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
            
            if text in ['🔙 العودة', '⬅️ العودة', '↩️ العودة']:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(message['chat']['id'], "تم الإلغاء", self.admin_keyboard())
                return
            
            if text.startswith('تعديل '):
                method_id = text.replace('تعديل ', '').strip()
                
                # البحث عن وسيلة الدفع
                method = self.get_payment_method_by_id(method_id)
                if not method:
                    self.send_message(message['chat']['id'], f"❌ لم يتم العثور على وسيلة الدفع {method_id}")
                    return
                
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                
                # عرض تفاصيل الوسيلة وطلب البيانات الجديدة
                edit_text = f"""✏️ تعديل وسيلة الدفع:
    
    🆔 المعرف: {method['id']}
    🏢 الشركة: {company_name}
    📋 الاسم: {method['method_name']}
    💳 النوع: {method['method_type']}
    📊 البيانات الحالية: {method['account_data']}
    💡 معلومات إضافية: {method['additional_info']}
    
    📝 أدخل البيانات الجديدة (رقم الحساب/المحفظة):
    
    ⬅️ /cancel للإلغاء"""
                
                self.send_message(message['chat']['id'], edit_text)
                self.user_states[user_id] = f'editing_method_{method_id}'
        
    def handle_method_delete_selection(self, message):
            """معالجة اختيار وسيلة الدفع للحذف"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text in ['🔙 العودة', '⬅️ العودة', '↩️ العودة']:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(message['chat']['id'], "تم الإلغاء", self.admin_keyboard())
                return
            
            if text.startswith('حذف '):
                method_id = text.replace('حذف ', '').strip()
                
                # حذف وسيلة الدفع
                success, deleted_method = self.delete_payment_method(method_id)
                
                if success:
                    company = self.get_company_by_id(deleted_method['company_id'])
                    company_name = company['name'] if company else 'غير محدد'
                    
                    success_msg = f"""✅ تم حذف وسيلة الدفع بنجاح!
    
    🗑️ المحذوفة:
    🆔 المعرف: {deleted_method['id']}
    🏢 الشركة: {company_name}
    📋 الاسم: {deleted_method['method_name']}
    💳 النوع: {deleted_method['method_type']}"""
                    
                    self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
                else:
                    self.send_message(message['chat']['id'], f"❌ فشل في حذف وسيلة الدفع {method_id}", self.admin_keyboard())
                
                del self.user_states[user_id]
        
    def handle_method_edit_data(self, message, method_id):
            """معالجة تعديل بيانات وسيلة الدفع"""
            user_id = message['from']['id']
            new_data = message.get('text', '').strip()
            
            if new_data == '/cancel':
                del self.user_states[user_id]
                self.send_message(message['chat']['id'], "تم إلغاء التعديل", self.admin_keyboard())
                return
            
            if not new_data:
                self.send_message(message['chat']['id'], "❌ البيانات فارغة. يرجى إدخال البيانات الجديدة:")
                return
            
            # تحديث وسيلة الدفع
            success = self.update_payment_method(method_id, new_data)
            
            if success:
                method = self.get_payment_method_by_id(method_id)
                company = self.get_company_by_id(method['company_id'])
                company_name = company['name'] if company else 'غير محدد'
                
                success_msg = f"""✅ تم تحديث وسيلة الدفع بنجاح!
    
    📝 المُحدّثة:
    🆔 المعرف: {method['id']}
    🏢 الشركة: {company_name}
    📋 الاسم: {method['method_name']}
    💳 النوع: {method['method_type']}
    📊 البيانات الجديدة: {new_data}"""
                
                self.send_message(message['chat']['id'], success_msg, self.admin_keyboard())
            else:
                self.send_message(message['chat']['id'], "❌ فشل في تحديث وسيلة الدفع", self.admin_keyboard())
            
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
                    report_content += f"• عدد المستخدمين المسجلين: {users_count}\n"
                    
                # إحصائيات المعاملات
                with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    transactions = list(reader)
                    total_transactions = len(transactions)
                    pending = sum(1 for t in transactions if t['status'] == 'pending')
                    approved = sum(1 for t in transactions if t['status'] == 'approved')
                    rejected = sum(1 for t in transactions if t['status'] == 'rejected')
                    
                    report_content += f"• إجمالي المعاملات: {total_transactions}\n"
                    report_content += f"  - معلقة: {pending}\n"
                    report_content += f"  - موافقة: {approved}\n"
                    report_content += f"  - مرفوضة: {rejected}\n"
                    
                # إحصائيات الشركات
                with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                    companies_count = len(list(csv.DictReader(f)))
                    report_content += f"• عدد الشركات: {companies_count}\n"
                    
            except Exception as e:
                report_content += f"خطأ في جمع الإحصائيات: {e}\n"
                
            report_content += f"\n📅 تاريخ النسخة: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            report_content += f"🤖 البوت: @depositbettingbot\n"
            
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
                self.send_message(message['chat']['id'], "🔔 لا توجد إشعارات حالياً", self.admin_keyboard())
                return
            
            # تصنيف الإشعارات حسب النوع
            by_type = {}
            for n in notifs:
                ntype = n.get('type', 'general')
                if ntype not in by_type:
                    by_type[ntype] = 0
                by_type[ntype] += 1
            
            summary = "🔔 لوحة الإشعارات\n\n📊 ملخص حسب النوع:\n"
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
                
            self.send_message(message['chat']['id'], "🔄 جاري إنشاء النسخة الاحتياطية...")
            
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
                    self.send_message(message['chat']['id'], "✅ تم إرسال النسخة الاحتياطية بنجاح!")
                else:
                    self.send_message(message['chat']['id'], "❌ فشل في إرسال النسخة الاحتياطية")
                    
                # حذف الملف المؤقت
                try:
                    os.remove(backup_file)
                except:
                    pass
            else:
                self.send_message(message['chat']['id'], "❌ فشل في إنشاء النسخة الاحتياطية")
        
    def handle_complaint_reply_buttons(self, message, complaint_id):
            """معالجة أزرار الرد على الشكاوى"""
            user_id = message['from']['id']
            text = message.get('text', '').strip()
            
            if text == '🔙 العودة للشكاوى':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.show_complaints_admin(message)
                return
            
            # تحديد نوع الرد
            reply_message = ""
            if text.startswith('✅ تم الحل'):
                reply_message = "شكراً لتواصلك معنا. تم حل مشكلتك بنجاح ونعتذر عن أي إزعاج."
            elif text.startswith('🔍 قيد المراجعة'):
                reply_message = "نحن نراجع طلبك بعناية وسنرد عليك خلال 24 ساعة. شكراً لصبرك."
            elif text.startswith('📞 سنتواصل معك'):
                reply_message = "سنتواصل معك قريباً عبر الهاتف أو الرسائل. شكراً لتواصلك معنا."
            elif text.startswith('💡 رد مخصص'):
                # طلب رد مخصص
                custom_text = """💡 اكتب ردك المخصص:
                
    مثال: شكراً لتواصلك، تم حل المشكلة...
    
    ⬅️ /cancel للإلغاء"""
                
                self.send_message(message['chat']['id'], custom_text)
                self.user_states[user_id] = f'writing_custom_reply_{complaint_id}'
                return
            
            # حفظ الرد وإرساله للعميل
            if reply_message:
                success = self.save_complaint_reply(complaint_id, reply_message)
                if success:
                    self.send_message(message['chat']['id'], f"✅ تم إرسال الرد للعميل!\n\n📝 الرد: {reply_message}", self.admin_keyboard())
                    # إرسال الرد للعميل
                    self.send_complaint_reply_to_customer(complaint_id, reply_message)
                else:
                    self.send_message(message['chat']['id'], "❌ فشل في حفظ الرد", self.admin_keyboard())
            
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
                    customer_message = f"""📞 رد على شكواك:
    
    🆔 رقم الشكوى: {complaint_id}
    💬 الرد: {reply_message}
    
    شكراً لتواصلك معنا ونتطلع لخدمتك دائماً 🙏"""
                    
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

        if text in ['/cancel', 'إلغاء', 'الغاء']:
            if user_id in self.user_states:
                del self.user_states[user_id]
            self.show_support_data_editor(message)
            return

        # تحديد نوع التعديل
        if state == 'editing_support_phone':
            success_msg = f"✅ تم تحديث رقم الهاتف إلى: <code>{text}</code>"
            self.save_setting('support_phone', text)
        elif state == 'editing_support_telegram':
            success_msg = f"✅ تم تحديث حساب التليجرام إلى: <code>{text}</code>"
            self.save_setting('support_telegram', text)
        elif state == 'editing_support_email':
            success_msg = f"✅ تم تحديث البريد الإلكتروني إلى: <code>{text}</code>"
            self.save_setting('support_email', text)
        elif state == 'editing_support_hours':
            success_msg = f"✅ تم تحديث ساعات العمل إلى: <b>{text}</b>"
            self.save_setting('support_hours', text)
        else:
            success_msg = "❌ خطأ في تحديث البيانات"

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
        
    def get_support_setting(self, key, default='غير محدد'):
        """قراءة إعداد الدعم — يستخدم get_setting الموحدة"""
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
                self.send_message(chat_id, "🔄 جاري إنشاء التقرير الاحترافي...")
                
                # إنشاء ملف تقرير احترافي
                filename = self.create_professional_excel_report()
                
                if filename and os.path.exists(filename):
                    # إرسال الملف
                    self.send_document(chat_id, filename, "📊 تقرير Excel احترافي للنظام")
                    
                    success_text = f"""✅ تم إنشاء التقرير الاحترافي بنجاح!
    
    📊 الملف يحتوي على:
    • بيانات المستخدمين مع تنسيق ملون
    • المعاملات مع تمييز الحالات
    • الشكاوى مع تصنيف الحالة  
    • الشركات وبياناتها
    • وسائل الدفع المتاحة
    • إحصائيات شاملة ومفصلة
    
    🎨 التنسيق الاحترافي:
    • ملف CSV منسق ومرتب
    • عناوين واضحة ومميزة
    • فواصل جميلة بين الأقسام
    • إحصائيات مفصلة ونسب مئوية
    • دعم كامل للنصوص العربية"""
                    
                    self.send_message(chat_id, success_text, self.admin_keyboard())
                else:
                    self.send_message(chat_id, "❌ فشل في إنشاء التقرير. يرجى المحاولة مرة أخرى.", self.admin_keyboard())
                    
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
                            'إجمالي المستخدمين': len(users),
                            'المستخدمين النشطين': len([u for u in users if u.get('is_banned', 'no').lower() != 'yes']),
                            'المستخدمين المحظورين': len([u for u in users if u.get('is_banned', 'no').lower() == 'yes']),
                            'نسبة المستخدمين النشطين': f"{(len([u for u in users if u.get('is_banned', 'no').lower() != 'yes'])/len(users)*100):.1f}%" if users else "0%"
                        }
                        
                        # إضافة إحصائيات العملات
                        for currency, count in currency_stats.items():
                            currency_name = self.currencies.get(currency, {}).get('name', currency)
                            user_stats[f'مستخدمي {currency_name}'] = f"{count} ({(count/len(users)*100):.1f}%)"
                        
                        stats['إحصائيات المستخدمين'] = user_stats
                
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
                            'إجمالي المعاملات': len(transactions),
                            'المعاملات المُوافقة': f"{len(approved)} ({(len(approved)/len(transactions)*100):.1f}%)" if transactions else "0",
                            'المعاملات المرفوضة': f"{len(rejected)} ({(len(rejected)/len(transactions)*100):.1f}%)" if transactions else "0",
                            'المعاملات المعلقة': f"{len(pending)} ({(len(pending)/len(transactions)*100):.1f}%)" if transactions else "0",
                            'طلبات الإيداع': f"{len(deposits)} ({(len(deposits)/len(transactions)*100):.1f}%)" if transactions else "0",
                            'طلبات السحب': f"{len(withdrawals)} ({(len(withdrawals)/len(transactions)*100):.1f}%)" if transactions else "0",
                            'معدل الموافقة': f"{(len(approved)/len(transactions)*100):.1f}%" if transactions else "0%",
                            'إجمالي المبالغ المُوافقة': f"{total_approved_amount:,.2f}",
                            'إجمالي الإيداعات المُوافقة': f"{total_deposit_amount:,.2f}",
                            'إجمالي السحوبات المُوافقة': f"{total_withdrawal_amount:,.2f}",
                            'صافي الحركة': f"{total_deposit_amount - total_withdrawal_amount:,.2f}",
                            'متوسط قيمة المعاملة': f"{(total_approved_amount/len(approved)):,.2f}" if approved else "0"
                        }
                        
                        stats['إحصائيات المعاملات'] = transaction_stats
                
                # إحصائيات الشكاوى والشركات
                if os.path.exists('complaints.csv'):
                    with open('complaints.csv', 'r', encoding='utf-8-sig') as f:
                        complaints = list(csv.DictReader(f))
                        resolved = [c for c in complaints if c.get('status') == 'resolved']
                        pending_complaints = [c for c in complaints if c.get('status') == 'pending']
                        
                        stats['إحصائيات الشكاوى'] = {
                            'إجمالي الشكاوى': len(complaints),
                            'الشكاوى المحلولة': f"{len(resolved)} ({(len(resolved)/len(complaints)*100):.1f}%)" if complaints else "0",
                            'الشكاوى المعلقة': f"{len(pending_complaints)} ({(len(pending_complaints)/len(complaints)*100):.1f}%)" if complaints else "0",
                            'معدل الحل': f"{(len(resolved)/len(complaints)*100):.1f}%" if complaints else "0%"
                        }
                
                if os.path.exists('companies.csv'):
                    with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                        companies = list(csv.DictReader(f))
                        active = [c for c in companies if c.get('is_active', '').lower() == 'active']
                        
                        stats['إحصائيات الشركات'] = {
                            'إجمالي الشركات': len(companies),
                            'الشركات النشطة': f"{len(active)} ({(len(active)/len(companies)*100):.1f}%)" if companies else "0",
                            'الشركات غير النشطة': f"{len(companies) - len(active)}"
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
            self.wfile.write('البوت يعمل بنجاح'.encode('utf-8'))
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
                manager.add_bot('البوت الرئيسي', bot_token, os.getenv('ADMIN_USER_IDS', '7146701713'))
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