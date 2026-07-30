#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام 💎 الاسترداد الذكي — Smart Recovery
يحوّل خسائر العملاء (الطلبات المرفوضة) إلى أرصدة ترويجية مرتبطة بالإحالات
العميل يحصل على رصيد استرداد، يشارك جزء مع أصدقائه، والأصدقاء يجب أن يودعوا لتفعيل الأرصدة
"""

import os
import csv
import json
import random
import string
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ==================== إعدادات 💎 الاسترداد الذكي ====================
SVRP_CONFIG = {
    'recovery_multiplier': 2.0,       # الرصيد = المبلغ المرفوض × المضاعف
    'max_recovery_cap': 5000,          # أقصى رصيد استرداد لكل حدث
    'credit_expiry_days': 30,          # مدة انتهاء الرصيد بالأيام
    'wagering_requirement': 3,         # عدد المعاملات المطلوبة قبل استخدام الرصيد
    'promo_code_max_uses': 10,         # أقصى استخدام لكود ترويجي
    'promo_code_expiry_days': 14,      # مدة انتهاء الكود الترويجي
    'referral_depth_limit': 3,         # عمق شجرة الإحالات
    'credit_split_keep': 0.5,          # نسبة الرصيد الذي يحتفظ به العميل
    'credit_split_share': 0.5,         # نسبة الرصيد المشترك مع الأصدقاء
    'max_recovery_per_month': 10000,   # أقصى استرداد شهرياً لكل مستخدم
}

# تعريف مجموعات المستخدمين
USER_GROUPS = {
    'bronze':   {'min_score': 0,    'multiplier': 1.0, 'icon': '🥉', 'name_ar': 'برونزي'},
    'silver':   {'min_score': 500,  'multiplier': 1.2, 'icon': '🥈', 'name_ar': 'فضي'},
    'gold':     {'min_score': 2000, 'multiplier': 1.5, 'icon': '🥇', 'name_ar': 'ذهبي'},
    'platinum': {'min_score': 5000, 'multiplier': 2.0, 'icon': '💎', 'name_ar': 'بلاتيني'},
}


class SVRPManager:
    """مدير نظام 💎 الاسترداد الذكي"""

    CREDIT_FIELDS = [
        'id', 'user_id', 'trigger_trans_id', 'trigger_amount', 'credit_amount',
        'credit_type', 'status', 'friend_id', 'created_at', 'expires_at',
        'wagering_required', 'wagering_completed', 'currency'
    ]

    WALLET_FIELDS = [
        'telegram_id', 'customer_id', 'balance', 'pending_balance',
        'total_earned', 'total_used', 'wagering_required', 'wagering_completed',
        'last_recovery_date', 'monthly_recovery_total'
    ]

    TASK_FIELDS = [
        'id', 'user_id', 'task_type', 'target_value', 'current_progress',
        'status', 'reward_amount', 'created_at', 'completed_at'
    ]

    PROMO_CODE_FIELDS = [
        'code', 'creator_id', 'amount', 'currency', 'max_uses',
        'used_count', 'status', 'created_at', 'expires_at'
    ]

    GROUP_FIELDS = [
        'telegram_id', 'group_name', 'tier_score', 'join_date',
        'benefits_active', 'last_updated'
    ]

    RECOVERY_REQUEST_FIELDS = [
        'id', 'user_id', 'customer_id', 'photo_file_id', 'status',
        'recovery_amount', 'admin_note', 'created_at', 'approved_at', 'approved_by'
    ]

    SVRP_COMPANY_FIELDS = [
        'id', 'name', 'registration_url', 'bonus_percentage', 'is_active', 'created_at'
    ]

    USER_COMPANY_ACCOUNT_FIELDS = [
        'id', 'user_id', 'company_id', 'company_name', 'account_number', 'status', 'created_at'
    ]

    BONUS_REQUEST_FIELDS = [
        'id', 'user_id', 'company_id', 'company_name', 'account_number', 'bonus_amount', 'status', 'created_at', 'approved_by'
    ]

    def __init__(self):
        self.init_svrp_files()

    # ==================== تهيئة الملفات ====================

    def init_svrp_files(self):
        """إنشاء جميع ملفات الاسترداد الذكي"""
        files = {
            'svrp_credits.csv': self.CREDIT_FIELDS,
            'svrp_wallets.csv': self.WALLET_FIELDS,
            'svrp_tasks.csv': self.TASK_FIELDS,
            'svrp_promo_codes.csv': self.PROMO_CODE_FIELDS,
            'svrp_user_groups.csv': self.GROUP_FIELDS,
            'recovery_requests.csv': self.RECOVERY_REQUEST_FIELDS,
            'svrp_companies.csv': self.SVRP_COMPANY_FIELDS,
            'user_company_accounts.csv': self.USER_COMPANY_ACCOUNT_FIELDS,
            'bonus_requests.csv': self.BONUS_REQUEST_FIELDS,
        }
        for filename, fields in files.items():
            if not os.path.exists(filename):
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(fields)
                logger.info(f"Created recovery file: {filename}")

    # ==================== أدوات مساعدة ====================

    def _generate_id(self, prefix):
        """توليد ID فريد"""
        return f"{prefix}{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(10,99)}"

    def _read_csv(self, filename):
        """قراءة آمنة من CSV"""
        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception as e:
            logger.error(f"خطأ في قراءة {filename}: {e}")
            return []

    def _write_csv(self, filename, rows, fields):
        """كتابة آمنة في CSV"""
        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fields})
            return True
        except Exception as e:
            logger.error(f"خطأ في كتابة {filename}: {e}")
            return False

    def _append_csv(self, filename, row, fields):
        """إضافة صف جديد إلى CSV"""
        try:
            with open(filename, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writerow({k: row.get(k, '') for k in fields})
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة صف إلى {filename}: {e}")
            return False

    def _get_config(self, key):
        """الحصول على قيمة إعداد"""
        return SVRP_CONFIG.get(key, 0)

    # ==================== المحفظة ====================

    def get_wallet(self, telegram_id):
        """الحصول على محفظة المستخدم أو إنشاؤها"""
        tid = str(telegram_id)
        rows = self._read_csv('svrp_wallets.csv')
        for row in rows:
            if row['telegram_id'] == tid:
                return row
        # إنشاء محفظة جديدة
        wallet = {
            'telegram_id': tid,
            'customer_id': '',
            'balance': '0',
            'pending_balance': '0',
            'total_earned': '0',
            'total_used': '0',
            'wagering_required': str(self._get_config('wagering_requirement')),
            'wagering_completed': '0',
            'last_recovery_date': '',
            'monthly_recovery_total': '0'
        }
        self._append_csv('svrp_wallets.csv', wallet, self.WALLET_FIELDS)
        return wallet

    def _update_wallet(self, telegram_id, updates):
        """تحديث محفظة مستخدم"""
        tid = str(telegram_id)
        rows = self._read_csv('svrp_wallets.csv')
        found = False
        for row in rows:
            if row['telegram_id'] == tid:
                for k, v in updates.items():
                    if k in row:
                        row[k] = str(v)
                found = True
                break
        if not found:
            # إنشاء إذا لم تكن موجودة
            wallet = self.get_wallet(telegram_id)
            rows = self._read_csv('svrp_wallets.csv')
            for row in rows:
                if row['telegram_id'] == tid:
                    for k, v in updates.items():
                        if k in row:
                            row[k] = str(v)
                    break
        return self._write_csv('svrp_wallets.csv', rows, self.WALLET_FIELDS)

    # ==================== تشغيل الاسترداد ====================

    def trigger_recovery(self, user_id, trans_id, amount, currency='SAR'):
        """
        تشغيل نظام الاسترداد عند رفض معاملة سحب
        يقسم الرصيد: 50% للمستخدم + 50% مشترك مع الأصدقاء
        """
        tid = str(user_id)
        multiplier = self._get_config('recovery_multiplier')
        max_cap = self._get_config('max_recovery_cap')
        monthly_cap = self._get_config('max_recovery_per_month')

        # فحص الحد الشهري
        wallet = self.get_wallet(tid)
        monthly_total = float(wallet.get('monthly_recovery_total', 0) or 0)
        if monthly_total >= monthly_cap:
            logger.info(f"Recovery: User {tid} reached monthly cap ({monthly_cap})")
            return None, "تم الوصول للحد الشهري للاسترداد"

        # حساب الرصيد
        credit_amount = min(amount * multiplier, max_cap)
        # التأكد من عدم تجاوز الحد الشهري
        remaining_monthly = monthly_cap - monthly_total
        if credit_amount > remaining_monthly:
            credit_amount = remaining_monthly

        if credit_amount <= 0:
            return None, "لا يوجد رصيد متاح"

        keep_amount = credit_amount * self._get_config('credit_split_keep')
        share_amount = credit_amount * self._get_config('credit_split_share')

        now = datetime.now()
        expiry = now + timedelta(days=self._get_config('credit_expiry_days'))
        wagering_req = self._get_config('wagering_requirement')

        # 1. إضافة رصيد "احتفاظ" للمستخدم
        keep_credit = {
            'id': self._generate_id('CRK'),
            'user_id': tid,
            'trigger_trans_id': trans_id,
            'trigger_amount': str(amount),
            'credit_amount': str(keep_amount),
            'credit_type': 'keep',
            'status': 'pending',
            'friend_id': '',
            'created_at': now.strftime('%Y-%m-%d %H:%M'),
            'expires_at': expiry.strftime('%Y-%m-%d %H:%M'),
            'wagering_required': str(wagering_req),
            'wagering_completed': '0',
            'currency': currency
        }
        self._append_csv('svrp_credits.csv', keep_credit, self.CREDIT_FIELDS)

        # 2. إضافة رصيد "مشاركة" — يُفعّل عندما يُودع صديق
        share_credit = {
            'id': self._generate_id('CRS'),
            'user_id': tid,
            'trigger_trans_id': trans_id,
            'trigger_amount': str(amount),
            'credit_amount': str(share_amount),
            'credit_type': 'shared',
            'status': 'pending',
            'friend_id': '',
            'created_at': now.strftime('%Y-%m-%d %H:%M'),
            'expires_at': expiry.strftime('%Y-%m-%d %H:%M'),
            'wagering_required': str(wagering_req),
            'wagering_completed': '0',
            'currency': currency
        }
        self._append_csv('svrp_credits.csv', share_credit, self.CREDIT_FIELDS)

        # 3. تحديث المحفظة
        current_balance = float(wallet.get('balance', 0) or 0)
        current_pending = float(wallet.get('pending_balance', 0) or 0)
        current_earned = float(wallet.get('total_earned', 0) or 0)

        self._update_wallet(tid, {
            'balance': current_balance + keep_amount,
            'pending_balance': current_pending + share_amount,
            'total_earned': current_earned + credit_amount,
            'wagering_required': wagering_req,
            'last_recovery_date': now.strftime('%Y-%m-%d %H:%M'),
            'monthly_recovery_total': monthly_total + credit_amount
        })

        # 4. إنشاء مهام يومائية تلقائياً
        self.create_daily_tasks(tid)

        # 5. تحديث مجموعة المستخدم
        self.update_user_group(tid)

        logger.info(f"Recovery triggered for user {tid}: {credit_amount} {currency} "
                     f"(keep={keep_amount}, share={share_amount})")

        return {
            'total_credit': credit_amount,
            'keep_amount': keep_amount,
            'share_amount': share_amount,
            'currency': currency,
            'wagering_required': wagering_req,
            'expires_at': expiry.strftime('%Y-%m-%d %H:%M')
        }, None

    # ==================== تفعيل أرصدة الأصدقاء ====================

    def activate_friend_credits(self, friend_telegram_id):
        """
        تفعيل الأرصدة المشتركة عندما يُكمل صديق إيداعاً
        يبحث عن الأرصدة المشتركة المرتبطة بهذا الصديق
        """
        tid = str(friend_telegram_id)

        # البحث في referrals.csv عن من أحال هذا المستخدم
        referrer_id = None
        try:
            if os.path.exists('referrals.csv'):
                with open('referrals.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if (row.get('referred_id') == tid and
                            row.get('status') in ('completed', 'registered')):
                            referrer_id = row.get('referrer_id')
                            break
        except Exception as e:
            logger.error(f"خطأ في البحث عن الإحالة: {e}")

        if not referrer_id:
            return False

        # تفعيل أول رصيد مشترك معلق للمُحيل
        rows = self._read_csv('svrp_credits.csv')
        activated = False
        for row in rows:
            if (row['user_id'] == referrer_id and
                row['credit_type'] == 'shared' and
                row['status'] == 'pending'):
                row['status'] = 'active'
                row['friend_id'] = tid
                activated = True
                break

        if activated:
            self._write_csv('svrp_credits.csv', rows, self.CREDIT_FIELDS)

            # نقل الرصيد من pending إلى balance في المحفظة
            wallet = self.get_wallet(referrer_id)
            share_amount = float(row['credit_amount'])
            current_balance = float(wallet.get('balance', 0) or 0)
            current_pending = float(wallet.get('pending_balance', 0) or 0)

            self._update_wallet(referrer_id, {
                'balance': current_balance + share_amount,
                'pending_balance': max(0, current_pending - share_amount)
            })

            # تحديث حالة الإحالة
            try:
                if os.path.exists('referrals.csv'):
                    ref_rows = self._read_csv('referrals.csv')
                    for ref_row in ref_rows:
                        if (ref_row.get('referred_id') == tid and
                            ref_row.get('status') == 'registered'):
                            ref_row['status'] = 'completed'
                            ref_row['reward_given'] = 'yes'
                    self._write_csv('referrals.csv', ref_rows,
                                    ['id', 'referrer_id', 'referrer_customer_id',
                                     'referred_id', 'referred_phone', 'status',
                                     'created_at', 'reward_given'])
            except Exception as e:
                logger.error(f"خطأ في تحديث الإحالة: {e}")

            logger.info(f"Recovery: Activated shared credits for referrer {referrer_id} "
                         f"(friend {tid} deposited)")
            return True

        return False

    # ==================== متطلبات الرهان ====================

    def check_wagering(self, telegram_id):
        """فحص إذا كان المستخدم أكمل متطلبات الرهان"""
        wallet = self.get_wallet(telegram_id)
        required = int(wallet.get('wagering_required', 0) or 0)
        completed = int(wallet.get('wagering_completed', 0) or 0)
        return completed >= required

    def increment_wagering(self, telegram_id):
        """زيادة عداد الرهان عند إكمال معاملة — وتفعيل الأرصدة المعلقة عند إكمال الرهان"""
        wallet = self.get_wallet(telegram_id)
        current = int(wallet.get('wagering_completed', 0) or 0)
        required = int(wallet.get('wagering_required', 3) or 3)
        new_count = current + 1
        self._update_wallet(telegram_id, {
            'wagering_completed': new_count
        })

        # فك التجميد: تحويل أرصدة 'pending' إلى 'active' عند إكمال الرهان
        if new_count >= required:
            rows = self._read_csv('svrp_credits.csv')
            activated = 0
            for row in rows:
                if (row['user_id'] == str(telegram_id) and
                    row['status'] == 'pending'):
                    row['status'] = 'active'
                    activated += 1
            if activated > 0:
                self._write_csv('svrp_credits.csv', rows, self.CREDIT_FIELDS)
                logger.info(f"Recovery: Activated {activated} pending credits for user {telegram_id} (wagering complete: {new_count}/{required})")

        return new_count

    # ==================== استخدام الأرصدة ====================

    def use_credits(self, telegram_id, amount):
        """
        استخدام الأرصدة كخصم رسوم
        يجب أن يكون المستخدم قد أكمل متطلبات الرهان
        """
        if not self.check_wagering(telegram_id):
            return False, "لم تكمل متطلبات الرهان بعد"

        wallet = self.get_wallet(telegram_id)
        balance = float(wallet.get('balance', 0) or 0)

        if balance < amount:
            return False, f"الرصيد غير كافٍ (المتاح: {balance})"

        # خصم من المحفظة
        new_balance = balance - amount
        total_used = float(wallet.get('total_used', 0) or 0) + amount
        self._update_wallet(telegram_id, {
            'balance': new_balance,
            'total_used': total_used
        })

        # تحديث حالة الأرصدة المستخدمة (pending أو active — تم تفعيلها في increment_wagering)
        rows = self._read_csv('svrp_credits.csv')
        remaining = amount
        for row in rows:
            if (row['user_id'] == str(telegram_id) and
                row['status'] in ('active', 'pending') and
                float(row.get('credit_amount', 0) or 0) > 0):
                credit_val = float(row['credit_amount'])
                if remaining >= credit_val:
                    remaining -= credit_val
                    row['status'] = 'used'
                    row['credit_amount'] = '0'
                else:
                    row['credit_amount'] = str(credit_val - remaining)
                    remaining = 0
                    break
        self._write_csv('svrp_credits.csv', rows, self.CREDIT_FIELDS)

        logger.info(f"Recovery: User {telegram_id} used {amount} credits")
        return True, "تم استخدام الأرصدة بنجاح"

    # ==================== الأكواد الترويجية ====================

    def create_promo_code(self, telegram_id, amount, currency='SAR'):
        """إنشاء كود ترويجي من رصيد المحفظة — يتطلب إكمال الرهان"""
        # فحص الرهان قبل السماح بإنشاء كود
        if not self.check_wagering(telegram_id):
            return None, "لم تكمل متطلبات الرهان بعد — لا يمكنك إنشاء أكواد"

        wallet = self.get_wallet(telegram_id)
        balance = float(wallet.get('balance', 0) or 0)

        if balance < amount:
            return None, "الرصيد غير كافٍ لإنشاء كود ترويجي"

        if amount <= 0:
            return None, "المبلغ يجب أن يكون أكبر من صفر"

        # توليد كود فريد
        code = 'RCV' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        now = datetime.now()
        expiry = now + timedelta(days=self._get_config('promo_code_expiry_days'))

        promo = {
            'code': code,
            'creator_id': str(telegram_id),
            'amount': str(amount),
            'currency': currency,
            'max_uses': str(self._get_config('promo_code_max_uses')),
            'used_count': '0',
            'status': 'active',
            'created_at': now.strftime('%Y-%m-%d %H:%M'),
            'expires_at': expiry.strftime('%Y-%m-%d %H:%M')
        }
        self._append_csv('svrp_promo_codes.csv', promo, self.PROMO_CODE_FIELDS)

        # خصم من محفظة المنشئ
        new_balance = balance - amount
        total_used = float(wallet.get('total_used', 0) or 0) + amount
        self._update_wallet(telegram_id, {
            'balance': new_balance,
            'total_used': total_used
        })

        logger.info(f"Recovery: Promo code {code} created by {telegram_id} for {amount} {currency}")
        return code, None

    def redeem_promo_code(self, telegram_id, code):
        """استرداد كود ترويجي"""
        rows = self._read_csv('svrp_promo_codes.csv')
        found = False
        for row in rows:
            if (row['code'].upper() == code.upper() and
                row['status'] == 'active'):
                used_count = int(row.get('used_count', 0) or 0)
                max_uses = int(row.get('max_uses', 10) or 10)
                if used_count >= max_uses:
                    return False, "تم استخدام هذا الكود الحد الأقصى من المرات"

                # فحص الانتهاء
                try:
                    expiry = datetime.strptime(row.get('expires_at', ''), '%Y-%m-%d %H:%M')
                    if datetime.now() > expiry:
                        row['status'] = 'expired'
                        self._write_csv('svrp_promo_codes.csv', rows, self.PROMO_CODE_FIELDS)
                        return False, "انتهت صلاحية هذا الكود"
                except:
                    pass

                # منع استرداد الكود الخاص بك
                if row['creator_id'] == str(telegram_id):
                    return False, "لا يمكنك استرداد كودك الترويجي الخاص"

                # إضافة الرصيد للمستخدم
                amount = float(row['amount'])
                wallet = self.get_wallet(telegram_id)
                current_balance = float(wallet.get('balance', 0) or 0)
                current_earned = float(wallet.get('total_earned', 0) or 0)

                self._update_wallet(telegram_id, {
                    'balance': current_balance + amount,
                    'total_earned': current_earned + amount
                })

                # تحديث عداد الاستخدام
                row['used_count'] = str(used_count + 1)
                if used_count + 1 >= max_uses:
                    row['status'] = 'fully_used'

                found = True
                break

        if not found:
            return False, "كود ترويجي غير صالح"

        self._write_csv('svrp_promo_codes.csv', rows, self.PROMO_CODE_FIELDS)
        logger.info(f"Recovery: User {telegram_id} redeemed promo code {code}")
        return True, f"تم استرداد الكود بنجاح! حصلت على {amount} رصيد"

    def get_user_promo_codes(self, telegram_id):
        """الحصول على أكواد المستخدم الترويجية"""
        rows = self._read_csv('svrp_promo_codes.csv')
        return [r for r in rows if r['creator_id'] == str(telegram_id)]

    # ==================== المهام ====================

    def create_daily_tasks(self, telegram_id):
        """إنشاء مهام يومية للمستخدم"""
        tid = str(telegram_id)
        today = datetime.now().strftime('%Y-%m-%d')

        # فحص إذا كانت المهام اليومية موجودة
        rows = self._read_csv('svrp_tasks.csv')
        for row in rows:
            if (row['user_id'] == tid and
                row['created_at'].startswith(today)):
                return  # المهام موجودة بالفعل

        # إنشاء 3 مهام يومية
        tasks = [
            ('deposit_count', '1', '50', 'إيداع واحد اليوم'),
            ('deposit_amount', '500', '100', 'إيداع 500 اليوم'),
            ('referral_count', '1', '75', 'دعوة صديق واحد اليوم'),
        ]

        for task_type, target, reward, desc in tasks:
            task = {
                'id': self._generate_id('TSK'),
                'user_id': tid,
                'task_type': task_type,
                'target_value': target,
                'current_progress': '0',
                'status': 'active',
                'reward_amount': reward,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'completed_at': ''
            }
            self._append_csv('svrp_tasks.csv', task, self.TASK_FIELDS)

        logger.info(f"Recovery: Daily tasks created for user {tid}")

    def update_task_progress(self, telegram_id, task_type, progress):
        """تحديث تقدم مهمة"""
        tid = str(telegram_id)
        rows = self._read_csv('svrp_tasks.csv')
        updated = False

        for row in rows:
            if (row['user_id'] == tid and
                row['task_type'] == task_type and
                row['status'] == 'active'):
                current = float(row.get('current_progress', 0) or 0)
                target = float(row.get('target_value', 1) or 1)

                if task_type in ('deposit_count', 'withdraw_count', 'referral_count'):
                    # عدّاد تراكمي
                    new_progress = current + progress
                else:
                    # قيمة تراكمية (مثل deposit_amount)
                    new_progress = current + progress

                row['current_progress'] = str(new_progress)

                if new_progress >= target:
                    row['status'] = 'completed'
                    row['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                    updated = True
                else:
                    updated = True

        if updated:
            self._write_csv('svrp_tasks.csv', rows, self.TASK_FIELDS)

    def claim_task_reward(self, telegram_id, task_id):
        """استلام مكافأة مهمة مكتملة"""
        tid = str(telegram_id)
        rows = self._read_csv('svrp_tasks.csv')
        reward = 0
        found = False

        for row in rows:
            if (row['id'] == task_id and
                row['user_id'] == tid and
                row['status'] == 'completed'):
                reward = float(row.get('reward_amount', 0) or 0)
                row['status'] = 'claimed'
                found = True
                break

        if not found:
            return False, "المهمة غير موجودة أو لم تكتمل"

        self._write_csv('svrp_tasks.csv', rows, self.TASK_FIELDS)

        # إضافة المكافئة للمحفظة
        wallet = self.get_wallet(tid)
        current_balance = float(wallet.get('balance', 0) or 0)
        current_earned = float(wallet.get('total_earned', 0) or 0)

        self._update_wallet(tid, {
            'balance': current_balance + reward,
            'total_earned': current_earned + reward
        })

        logger.info(f"Recovery: User {tid} claimed task {task_id} reward: {reward}")
        return True, f"تم استلام المكافأة: {reward} رصيد!"

    def get_user_tasks(self, telegram_id):
        """الحصول على مهام المستخدم"""
        tid = str(telegram_id)
        rows = self._read_csv('svrp_tasks.csv')
        today = datetime.now().strftime('%Y-%m-%d')
        return [r for r in rows if r['user_id'] == tid and r['created_at'].startswith(today)]

    # ==================== مجموعات المستخدمين ====================

    def get_user_group(self, telegram_id):
        """الحصول على مجموعة المستخدم"""
        tid = str(telegram_id)
        rows = self._read_csv('svrp_user_groups.csv')
        for row in rows:
            if row['telegram_id'] == tid:
                return row
        # إنشاء مجموعة افتراضية (برونزي)
        group = {
            'telegram_id': tid,
            'group_name': 'bronze',
            'tier_score': '0',
            'join_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'benefits_active': 'yes',
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        self._append_csv('svrp_user_groups.csv', group, self.GROUP_FIELDS)
        return group

    def update_user_group(self, telegram_id):
        """إعادة حساب مجموعة المستخدم بناءً على النشاط"""
        tid = str(telegram_id)

        # حساب النقاط: مجموع الأرصدة المكتسبة + المعاملات
        wallet = self.get_wallet(tid)
        total_earned = float(wallet.get('total_earned', 0) or 0)
        total_transactions = int(wallet.get('wagering_completed', 0) or 0)

        # النقاط = الأرصدة + (المعاملات × 100)
        score = total_earned + (total_transactions * 100)

        # تحديد المجموعة
        group_name = 'bronze'
        for gname, ginfo in sorted(USER_GROUPS.items(), key=lambda x: x[1]['min_score'], reverse=True):
            if score >= ginfo['min_score']:
                group_name = gname
                break

        # تحديث الملف
        rows = self._read_csv('svrp_user_groups.csv')
        found = False
        for row in rows:
            if row['telegram_id'] == tid:
                old_group = row.get('group_name', 'bronze')
                row['group_name'] = group_name
                row['tier_score'] = str(score)
                row['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                found = True
                # إرجاع معلومات الترقية
                upgraded = group_name != old_group
                break

        if not found:
            rows.append({
                'telegram_id': tid,
                'group_name': group_name,
                'tier_score': str(score),
                'join_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'benefits_active': 'yes',
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M')
            })
            upgraded = True
        else:
            pass

        self._write_csv('svrp_user_groups.csv', rows, self.GROUP_FIELDS)
        return group_name, upgraded if found else True

    # ==================== شجرة الإحالات ====================

    def get_referral_tree(self, telegram_id, depth=None):
        """الحصول على شجرة الإحالات"""
        if depth is None:
            depth = self._get_config('referral_depth_limit')

        tree = {'user_id': str(telegram_id), 'referrals': []}

        if depth <= 0:
            return tree

        # البحث عن من أحالهم هذا المستخدم
        try:
            if os.path.exists('referrals.csv'):
                with open('referrals.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('referrer_id') == str(telegram_id):
                            referred_id = row.get('referred_id', '')
                            if referred_id:
                                child = self.get_referral_tree(referred_id, depth - 1)
                                child['status'] = row.get('status', 'unknown')
                                tree['referrals'].append(child)
        except Exception as e:
            logger.error(f"خطأ في شجرة الإحالات: {e}")

        return tree

    def count_referrals_recursive(self, telegram_id, depth=None):
        """عدد جميع الإحالات في الشجرة"""
        if depth is None:
            depth = self._get_config('referral_depth_limit')
        if depth <= 0:
            return 0

        count = 0
        try:
            if os.path.exists('referrals.csv'):
                with open('referrals.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('referrer_id') == str(telegram_id):
                            referred_id = row.get('referred_id', '')
                            if referred_id:
                                count += 1
                                count += self.count_referrals_recursive(referred_id, depth - 1)
        except:
            pass
        return count

    # ==================== معالجة كود الإحالة ====================

    def process_referral_code(self, referrer_customer_id, referred_telegram_id):
        """
        ربط كود الإحالة بالمستخدم الجديد
        referrer_customer_id: رقم عميل المُحيل (من كود REFxxxx)
        referred_telegram_id: معرف تلجرام المستخدم الجديد
        """
        try:
            # العثور على المُحيل في users.csv
            referrer = None
            if os.path.exists('users.csv'):
                with open('users.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('customer_id') == referrer_customer_id:
                            referrer = row
                            break

            if not referrer:
                return False, "كود الإحالة غير صالح"

            referrer_tid = referrer.get('telegram_id', '')
            if referrer_tid == str(referred_telegram_id):
                return False, "لا يمكنك استخدام كود الإحالة الخاص بك"

            # فحص عدم وجود إحالة سابقة لهذا المستخدم
            existing_rows = self._read_csv('referrals.csv')
            for row in existing_rows:
                if row.get('referred_id') == str(referred_telegram_id):
                    return False, "تم استخدام كود إحالة بالفعل"

            # إنشاء سجل إحالة
            referral = {
                'id': self._generate_id('REF'),
                'referrer_id': referrer_tid,
                'referrer_customer_id': referrer_customer_id,
                'referred_id': str(referred_telegram_id),
                'referred_phone': '',
                'status': 'registered',
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'reward_given': 'no'
            }
            self._append_csv('referrals.csv', referral,
                             ['id', 'referrer_id', 'referrer_customer_id',
                              'referred_id', 'referred_phone', 'status',
                              'created_at', 'reward_given'])

            logger.info(f"Recovery: Referral processed — referrer {referrer_tid} → {referred_telegram_id}")
            return True, "تم ربط كود الإحالة بنجاح"

        except Exception as e:
            logger.error(f"خطأ في معالجة كود الإحالة: {e}")
            return False, "خطأ في معالجة كود الإحالة"

    # ==================== انتهاء الأرصدة ====================

    def expire_old_credits(self):
        """انتهاء صلاحية الأرصدة القديمة"""
        now = datetime.now()
        rows = self._read_csv('svrp_credits.csv')
        expired_count = 0

        for row in rows:
            if row['status'] in ('pending', 'active'):
                try:
                    expiry = datetime.strptime(row.get('expires_at', ''), '%Y-%m-%d %H:%M')
                    if now > expiry:
                        row['status'] = 'expired'
                        expired_count += 1
                except:
                    pass

        if expired_count > 0:
            self._write_csv('svrp_credits.csv', rows, self.CREDIT_FIELDS)
            logger.info(f"Recovery: Expired {expired_count} old credits")

        # انتهاء صلاحية الأكواد الترويجية
        promo_rows = self._read_csv('svrp_promo_codes.csv')
        expired_promos = 0
        for row in promo_rows:
            if row['status'] == 'active':
                try:
                    expiry = datetime.strptime(row.get('expires_at', ''), '%Y-%m-%d %H:%M')
                    if now > expiry:
                        row['status'] = 'expired'
                        expired_promos += 1
                except:
                    pass

        if expired_promos > 0:
            self._write_csv('svrp_promo_codes.csv', promo_rows, self.PROMO_CODE_FIELDS)
            logger.info(f"Recovery: Expired {expired_promos} promo codes")

        # إعادة تعيين الحد الشهري (بداية شهر جديد)
        wallets = self._read_csv('svrp_wallets.csv')
        now_month = datetime.now().strftime('%Y-%m')
        reset_count = 0
        for row in wallets:
            last_date = row.get('last_recovery_date', '')
            if last_date:
                try:
                    last_month = datetime.strptime(last_date, '%Y-%m-%d %H:%M').strftime('%Y-%m')
                    if last_month != now_month and float(row.get('monthly_recovery_total', 0) or 0) > 0:
                        row['monthly_recovery_total'] = '0'
                        reset_count += 1
                except:
                    pass

        if reset_count > 0:
            self._write_csv('svrp_wallets.csv', wallets, self.WALLET_FIELDS)
            logger.info(f"Recovery: Reset monthly totals for {reset_count} wallets")

        return expired_count

    # ==================== إحصائيات الإدمن ====================

    # ==================== طلبات الاسترداد بلقطة شاشة ====================

    def create_recovery_request(self, user_id, customer_id, photo_file_id):
        """إنشاء طلب استرداد جديد بلقطة شاشة"""
        req_id = self._generate_id('REC')
        row = {
            'id': req_id,
            'user_id': str(user_id),
            'customer_id': customer_id or '',
            'photo_file_id': photo_file_id,
            'status': 'pending',
            'recovery_amount': '',
            'admin_note': '',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'approved_at': '',
            'approved_by': ''
        }
        self._append_csv('recovery_requests.csv', row, self.RECOVERY_REQUEST_FIELDS)
        logger.info(f"Recovery request created: {req_id} by user {user_id}")
        return req_id

    def get_pending_recovery_requests(self):
        """الحصول على طلبات الاسترداد المعلقة"""
        rows = self._read_csv('recovery_requests.csv')
        return [r for r in rows if r.get('status') == 'pending']

    def get_recovery_request(self, req_id):
        """الحصول على طلب استرداد بالمعرف"""
        rows = self._read_csv('recovery_requests.csv')
        for r in rows:
            if r['id'] == req_id:
                return r
        return None

    def approve_recovery_request(self, req_id, amount, admin_id):
        """موافقة الأدمن على طلب استرداد — يُضاف الرصيد للمجمد"""
        rows = self._read_csv('recovery_requests.csv')
        req = None
        for r in rows:
            if r['id'] == req_id:
                r['status'] = 'approved'
                r['recovery_amount'] = str(amount)
                r['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                r['approved_by'] = str(admin_id)
                req = r
                break

        if not req:
            return False, "الطلب غير موجود"

        self._write_csv('recovery_requests.csv', rows, self.RECOVERY_REQUEST_FIELDS)

        # إضافة الرصيد للمحفظة المجمدة
        user_id = req['user_id']
        wallet = self.get_wallet(user_id)
        current_balance = float(wallet.get('balance', 0) or 0)
        current_earned = float(wallet.get('total_earned', 0) or 0)

        self._update_wallet(user_id, {
            'balance': current_balance + amount,
            'total_earned': current_earned + amount,
            'last_recovery_date': datetime.now().strftime('%Y-%m-%d %H:%M')
        })

        logger.info(f"Recovery approved: {req_id} amount={amount} for user {user_id}")
        return True, f"تم إضافة {amount} للرصيد المجمد"

    def reject_recovery_request(self, req_id, admin_note=''):
        """رفض طلب استرداد"""
        rows = self._read_csv('recovery_requests.csv')
        for r in rows:
            if r['id'] == req_id:
                r['status'] = 'rejected'
                r['admin_note'] = admin_note
                self._write_csv('recovery_requests.csv', rows, self.RECOVERY_REQUEST_FIELDS)
                logger.info(f"Recovery rejected: {req_id}")
                return True, "تم رفض الطلب"
        return False, "الطلب غير موجود"

    def send_frozen_credits(self, sender_telegram_id, receiver_customer_id, amount):
        """
        إرسال رصيد مجمد لصديق — يفك التجميد بنفس المبلغ
        
        المنطق:
        1. الرصيد المجمد يُقسم لـ 4 أقسام (25% لكل صديق)
        2. الحد الأدنى: 4 أصدقاء لفك التجميد الكامل
        3. عند إرسال مبلغ لصديق ← يُفك تجميد نفس المبلغ
        4. لا يمكن إرسال أكثر من 25% للصديق الواحد
        
        مثال: مجمد=1000، أرسل 250 لصديق
        - المرسل: مجمد 1000→750، متاح 0→250
        - المستلم: مجمد 0→250
        """
        tid = str(sender_telegram_id)
        
        # البحث عن المستلم بمعرف العميل
        receiver = None
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('customer_id') == receiver_customer_id:
                        receiver = row
                        break
        except:
            pass

        if not receiver:
            return False, "معرف العميل غير موجود"

        receiver_tid = receiver.get('telegram_id', '')
        if receiver_tid == tid:
            return False, "لا يمكنك إرسال رصيد لنفسك"

        # فحص رصيد المرسل
        sender_wallet = self.get_wallet(tid)
        sender_balance = float(sender_wallet.get('balance', 0) or 0)

        if sender_balance <= 0:
            return False, "لا يوجد رصيد مجمد للإرسال"

        # الحد الأقصى للإرسال لصديق واحد = 25% من الرصيد المجمد
        max_per_friend = sender_balance * 0.25
        
        if amount > max_per_friend:
            return False, f"الحد الأقصى لكل صديق: {max_per_friend:.2f} (25% من رصيدك المجمد)"

        if amount <= 0:
            return False, "المبلغ يجب أن يكون أكبر من صفر"

        # فحص عدد الأصدقاء المُرسل لهم (من سجل التحويلات)
        transfers = self._read_csv('svrp_transfers.csv')
        unique_friends = set()
        for t in transfers:
            if t.get('sender_id') == tid:
                unique_friends.add(t.get('receiver_id', ''))
        
        # إذا كان الصديق جديد، أضفه للعدد
        if receiver_tid not in unique_friends:
            friend_count = len(unique_friends) + 1
        else:
            friend_count = len(unique_friends)
        
        # 1. خصم من المرسل + نقل نفس المبلغ للمتاح
        sender_used = float(sender_wallet.get('total_used', 0) or 0)
        
        self._update_wallet(tid, {
            'balance': sender_balance - amount,
            'total_used': sender_used + amount
        })

        # 2. إضافة للمستلم (مجمد)
        receiver_wallet = self.get_wallet(receiver_tid)
        receiver_balance = float(receiver_wallet.get('balance', 0) or 0)
        receiver_earned = float(receiver_wallet.get('total_earned', 0) or 0)

        self._update_wallet(receiver_tid, {
            'balance': receiver_balance + amount,
            'total_earned': receiver_earned + amount
        })

        # 3. تسجيل التحويل
        transfer_id = self._generate_id('TRF')
        transfer = {
            'id': transfer_id,
            'sender_id': tid,
            'receiver_id': receiver_tid,
            'amount': str(amount),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        self._append_csv('svrp_transfers.csv', transfer,
            ['id', 'sender_id', 'receiver_id', 'amount', 'created_at'])

        logger.info(f"SVRP transfer: {tid} → {receiver_tid} amount={amount}")
        remaining = max(0, 4 - friend_count)
        return True, f"✅ تم إرسال {amount:.2f} للعميل {receiver_customer_id}\n💰 تم فك تجميد {amount:.2f} من رصيدك\n👥 عدد أصدقائك: {friend_count}/4\n{'⏳ تحتاج {0} أصدقاء آخرين لفك التجميد الكامل'.format(remaining) if remaining > 0 else '🎉 أكملت 4 أصدقاء!'}"

    # ==================== شركات الاسترداد ====================

    def add_recovery_company(self, name, registration_url, bonus_percentage=10):
        """إضافة شركة استرداد جديدة"""
        company_id = self._generate_id('SVC')
        row = {
            'id': company_id,
            'name': name,
            'registration_url': registration_url,
            'bonus_percentage': str(bonus_percentage),
            'is_active': 'yes',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        if self._append_csv('svrp_companies.csv', row, self.SVRP_COMPANY_FIELDS):
            logger.info(f"Recovery company added: {company_id} ({name})")
            return company_id
        return None

    def get_recovery_companies(self, active_only=True):
        """جلب شركات الاسترداد من ملف الشركات الرئيسي companies.csv"""
        rows = self._read_csv('companies.csv')
        result = []
        for r in rows:
            is_active = r.get('is_active', '').lower() in ['active', 'yes', '1', 'true']
            if active_only and not is_active:
                continue
            result.append({
                'id': r.get('id', ''),
                'name': r.get('name', ''),
                'registration_url': r.get('address', ''),
                'bonus_percentage': '10',
                'is_active': 'yes' if is_active else 'no',
                'icon': r.get('icon', ''),
                'details': r.get('details', '')
            })
        return result

    def delete_recovery_company(self, company_id):
        """حذف شركة استرداد"""
        rows = self._read_csv('svrp_companies.csv')
        new_rows = [r for r in rows if r['id'] != company_id]
        if len(new_rows) < len(rows):
            return self._write_csv('svrp_companies.csv', new_rows, self.SVRP_COMPANY_FIELDS)
        return False

    # ==================== حسابات المستخدمين في الشركات ====================

    def add_user_company_account(self, user_id, company_id, company_name, account_number):
        """إضافة رقم حساب المستخدم في شركة"""
        # فحص إذا كان لديه حساب بالفعل في هذه الشركة
        rows = self._read_csv('user_company_accounts.csv')
        for row in rows:
            if row.get('user_id') == str(user_id) and row.get('company_id') == company_id:
                return False, "لديك حساب مسجل بالفعل في هذه الشركة. لتغييره، أرسل طلباً للإدارة"

        account_id = self._generate_id('UAC')
        row = {
            'id': account_id,
            'user_id': str(user_id),
            'company_id': company_id,
            'company_name': company_name,
            'account_number': account_number,
            'status': 'active',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        if self._append_csv('user_company_accounts.csv', row, self.USER_COMPANY_ACCOUNT_FIELDS):
            return True, f"✅ تم تسجيل حسابك في {company_name}"
        return False, "❌ فشل في التسجيل"

    def get_user_company_accounts(self, user_id):
        """حسابات المستخدم في الشركات"""
        rows = self._read_csv('user_company_accounts.csv')
        return [r for r in rows if r.get('user_id') == str(user_id)]

    def get_user_company_account(self, user_id, company_id):
        """حساب مستخدم في شركة محددة"""
        rows = self._read_csv('user_company_accounts.csv')
        for row in rows:
            if row.get('user_id') == str(user_id) and row.get('company_id') == company_id:
                return row
        return None

    # ==================== طلبات المكافآت ====================

    def create_bonus_request(self, user_id, company_id, company_name, account_number):
        """إنشاء طلب مكافأة"""
        # فحص إذا كان لديه طلب سابق معلق
        rows = self._read_csv('bonus_requests.csv')
        for row in rows:
            if (row.get('user_id') == str(user_id) and
                row.get('company_id') == company_id and
                row.get('status') == 'pending'):
                return None, "لديك طلب مكافأة معلق بالفعل في هذه الشركة"

        # فحص إذا كان لديه حساب مسجل
        account = self.get_user_company_account(user_id, company_id)
        if not account:
            return None, "يجب تسجيل رقم حسابك أولاً"

        # نسبة المكافأة الافتراضية
        bonus_pct = 10

        request_id = self._generate_id('BNR')
        row = {
            'id': request_id,
            'user_id': str(user_id),
            'company_id': company_id,
            'company_name': company_name,
            'account_number': account_number,
            'bonus_amount': '',  # يحددها الأدمن
            'status': 'pending',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'approved_by': ''
        }
        if self._append_csv('bonus_requests.csv', row, self.BONUS_REQUEST_FIELDS):
            logger.info(f"Bonus request created: {request_id} by user {user_id} for {company_name}")
            return request_id, None
        return None, "❌ فشل في إنشاء الطلب"

    def get_pending_bonus_requests(self):
        """طلبات المكافآت المعلقة"""
        rows = self._read_csv('bonus_requests.csv')
        return [r for r in rows if r.get('status') == 'pending']

    def approve_bonus_request(self, request_id, bonus_amount, admin_id):
        """موافقة الأدمن على مكافأة"""
        rows = self._read_csv('bonus_requests.csv')
        req = None
        for r in rows:
            if r['id'] == request_id:
                r['status'] = 'approved'
                r['bonus_amount'] = str(bonus_amount)
                r['approved_by'] = str(admin_id)
                req = r
                break

        if not req:
            return False, "الطلب غير موجود"

        self._write_csv('bonus_requests.csv', rows, self.BONUS_REQUEST_FIELDS)

        # إضافة المكافأة للرصيد المجمد
        user_id = req['user_id']
        wallet = self.get_wallet(user_id)
        current_balance = float(wallet.get('balance', 0) or 0)
        current_earned = float(wallet.get('total_earned', 0) or 0)

        self._update_wallet(user_id, {
            'balance': current_balance + bonus_amount,
            'total_earned': current_earned + bonus_amount
        })

        logger.info(f"Bonus approved: {request_id} amount={bonus_amount} for user {user_id}")
        return True, f"تم إضافة {bonus_amount} للرصيد المجمد"

    def reject_bonus_request(self, request_id, admin_id):
        """رفض طلب مكافأة"""
        rows = self._read_csv('bonus_requests.csv')
        for r in rows:
            if r['id'] == request_id:
                r['status'] = 'rejected'
                r['approved_by'] = str(admin_id)
                self._write_csv('bonus_requests.csv', rows, self.BONUS_REQUEST_FIELDS)
                return True, "تم رفض الطلب"
        return False, "الطلب غير موجود"

    def deposit_from_balance(self, user_id, company_id, company_name, amount):
        """
        إيداع من الرصيد المتاح — العميل يطلب إيداع رصيده المتاح لحسابه في الشركة
        يُخصم من المتاح (total_used) → يُسجل كمعاملة إيداع
        
        ملاحظة: الرصيد المتاح = total_used (المبلغ الذي تم فك تجميده عبر الإرسال)
        """
        tid = str(user_id)
        wallet = self.get_wallet(tid)
        
        # الرصيد المتاح = ما تم فك تجميده (total_used يمثل ما خرج من المجمد)
        available = float(wallet.get('total_used', 0) or 0)
        
        if available < amount:
            return False, f"رصيدك المتاح غير كافٍ (المتاح: {available:.2f})"

        if amount <= 0:
            return False, "المبلغ يجب أن يكون أكبر من صفر"

        # خصم من المتاح
        new_used = available - amount
        self._update_wallet(tid, {
            'total_used': new_used
        })

        # تسجيل معاملة الإيداع
        deposit_id = self._generate_id('DEP')
        transfer = {
            'id': deposit_id,
            'sender_id': tid,
            'receiver_id': tid,  # نفس المستخدم
            'amount': str(amount),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        self._append_csv('svrp_transfers.csv', transfer,
            ['id', 'sender_id', 'receiver_id', 'amount', 'created_at'])

        logger.info(f"SVRP deposit from balance: user {tid} deposited {amount} to {company_name}")
        return True, deposit_id

    def get_svrp_stats(self):
        """إحصائيات شاملة للاسترداد الذكي (للإدمن)"""
        credits = self._read_csv('svrp_credits.csv')
        wallets = self._read_csv('svrp_wallets.csv')
        tasks = self._read_csv('svrp_tasks.csv')
        promos = self._read_csv('svrp_promo_codes.csv')

        total_credits_issued = sum(float(r.get('credit_amount', 0) or 0) for r in credits
                                    if r.get('status') != 'used')
        total_credits_used = sum(float(r.get('credit_amount', 0) or 0) for r in credits
                                  if r.get('status') == 'used')
        active_credits = sum(1 for r in credits if r.get('status') in ('pending', 'active'))
        expired_credits = sum(1 for r in credits if r.get('status') == 'expired')

        total_balance = sum(float(r.get('balance', 0) or 0) for r in wallets)
        total_pending = sum(float(r.get('pending_balance', 0) or 0) for r in wallets)

        active_tasks = sum(1 for r in tasks if r.get('status') == 'active')
        completed_tasks = sum(1 for r in tasks if r.get('status') == 'completed')
        claimed_tasks = sum(1 for r in tasks if r.get('status') == 'claimed')

        active_promos = sum(1 for r in promos if r.get('status') == 'active')

        # أفضل المُحيلين
        ref_stats = {}
        try:
            if os.path.exists('referrals.csv'):
                with open('referrals.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rid = row.get('referrer_id', '')
                        ref_stats[rid] = ref_stats.get(rid, 0) + 1
        except:
            pass

        top_referrers = sorted(ref_stats.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            'total_credits_issued': total_credits_issued,
            'total_credits_used': total_credits_used,
            'active_credits': active_credits,
            'expired_credits': expired_credits,
            'total_wallets': len(wallets),
            'total_balance': total_balance,
            'total_pending': total_pending,
            'active_tasks': active_tasks,
            'completed_tasks': completed_tasks,
            'claimed_tasks': claimed_tasks,
            'active_promos': active_promos,
            'top_referrers': top_referrers
        }

    def get_user_credits_summary(self, telegram_id):
        """ملخص أرصدة المستخدم"""
        tid = str(telegram_id)
        rows = self._read_csv('svrp_credits.csv')
        user_credits = [r for r in rows if r['user_id'] == tid]

        keep_credits = [r for r in user_credits if r['credit_type'] == 'keep']
        shared_credits = [r for r in user_credits if r['credit_type'] == 'shared']

        return {
            'keep': {
                'pending': sum(1 for r in keep_credits if r['status'] == 'pending'),
                'active': sum(1 for r in keep_credits if r['status'] == 'active'),
                'used': sum(1 for r in keep_credits if r['status'] == 'used'),
                'expired': sum(1 for r in keep_credits if r['status'] == 'expired'),
                'total_amount': sum(float(r.get('credit_amount', 0) or 0) for r in keep_credits
                                    if r['status'] in ('pending', 'active'))
            },
            'shared': {
                'pending': sum(1 for r in shared_credits if r['status'] == 'pending'),
                'active': sum(1 for r in shared_credits if r['status'] == 'active'),
                'used': sum(1 for r in shared_credits if r['status'] == 'used'),
                'expired': sum(1 for r in shared_credits if r['status'] == 'expired'),
                'total_amount': sum(float(r.get('credit_amount', 0) or 0) for r in shared_credits
                                    if r['status'] in ('pending', 'active'))
            }
        }

    # ==================== نظام الاسترداد بلقطة شاشة ====================

    RECOVERY_FIELDS = [
        'id', 'user_id', 'customer_id', 'photo_file_id', 'status',
        'recovery_amount', 'admin_note', 'admin_id', 'created_at', 'approved_at'
    ]

    def init_recovery_requests_file(self):
        """إنشاء ملف طلبات الاسترداد"""
        if not os.path.exists('recovery_requests.csv'):
            with open('recovery_requests.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(self.RECOVERY_FIELDS)
            logger.info("Created recovery_requests.csv")

    def create_recovery_request(self, user_id, customer_id, photo_file_id):
        """إنشاء طلب استرداد بلقطة شاشة"""
        self.init_recovery_requests_file()
        req_id = f"REC{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(10,99)}"
        row = {
            'id': req_id,
            'user_id': str(user_id),
            'customer_id': customer_id,
            'photo_file_id': photo_file_id,
            'status': 'pending',
            'recovery_amount': '0',
            'admin_note': '',
            'admin_id': '',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'approved_at': ''
        }
        self._append_csv('recovery_requests.csv', row, self.RECOVERY_FIELDS)
        logger.info(f"Recovery request created: {req_id} for user {user_id}")
        return req_id

    def get_recovery_request(self, req_id):
        """الحصول على طلب استرداد"""
        rows = self._read_csv('recovery_requests.csv')
        for row in rows:
            if row['id'] == req_id:
                return row
        return None

    def get_pending_recovery_requests(self):
        """الحصول على طلبات الاسترداد المعلقة"""
        rows = self._read_csv('recovery_requests.csv')
        return [r for r in rows if r.get('status') == 'pending']

    def approve_recovery_request(self, req_id, admin_id, amount, note=''):
        """الموافقة على طلب استرداد — يُضاف الرصيد المجمد"""
        rows = self._read_csv('recovery_requests.csv')
        request = None
        for row in rows:
            if row['id'] == req_id:
                row['status'] = 'approved'
                row['recovery_amount'] = str(amount)
                row['admin_note'] = note
                row['admin_id'] = str(admin_id)
                row['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                request = row
                break

        if not request:
            return False, "الطلب غير موجود"

        self._write_csv('recovery_requests.csv', rows, self.RECOVERY_FIELDS)

        # إضافة الرصيد المجمد للمستخدم
        user_id = request['user_id']
        wallet = self.get_wallet(user_id)
        current_balance = float(wallet.get('balance', 0) or 0)
        current_earned = float(wallet.get('total_earned', 0) or 0)

        self._update_wallet(user_id, {
            'balance': current_balance + amount,
            'total_earned': current_earned + amount
        })

        # إنشاء سجل رصيد مجمد
        credit = {
            'id': self._generate_id('FRC'),
            'user_id': user_id,
            'trigger_trans_id': req_id,
            'trigger_amount': str(amount),
            'credit_amount': str(amount),
            'credit_type': 'recovery',
            'status': 'frozen',
            'friend_id': '',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'expires_at': (datetime.now() + timedelta(days=self._get_config('credit_expiry_days'))).strftime('%Y-%m-%d %H:%M'),
            'wagering_required': '0',
            'wagering_completed': '0',
            'currency': 'SAR'
        }
        self._append_csv('svrp_credits.csv', credit, self.CREDIT_FIELDS)

        logger.info(f"Recovery approved: {req_id} → {amount} frozen for user {user_id}")
        return True, "تمت الموافقة على الاسترداد"

    def reject_recovery_request(self, req_id, admin_id, note=''):
        """رفض طلب استرداد"""
        rows = self._read_csv('recovery_requests.csv')
        for row in rows:
            if row['id'] == req_id:
                row['status'] = 'rejected'
                row['admin_note'] = note
                row['admin_id'] = str(admin_id)
                row['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                self._write_csv('recovery_requests.csv', rows, self.RECOVERY_FIELDS)
                logger.info(f"Recovery rejected: {req_id}")
                return True, "تم رفض الطلب"
        return False, "الطلب غير موجود"
