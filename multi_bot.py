#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام إدارة البوتات المتعددة — Multi-Bot Manager
يدعم تشغيل عدة بوتات بتوكنز مختلفة في نفس الوقت
مع تجميد مؤقت وإدارة أدمن متعددة
"""

import os
import csv
import threading
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BOT_TOKEN_FIELDS = [
    'id', 'name', 'token', 'is_active', 'created_at',
    'admin_ids', 'last_started', 'total_users', 'total_transactions',
    'freeze_until', 'status', 'description', 'can_manage_bots', 'features'
]


class MultiBotManager:
    """مدير البوتات المتعددة"""

    def __init__(self):
        self.active_bots = {}  # bot_id -> bot_instance + thread
        self.init_tokens_file()

    def init_tokens_file(self):
        """إنشاء ملف التوكنات"""
        if not os.path.exists('bot_tokens.csv'):
            with open('bot_tokens.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(BOT_TOKEN_FIELDS)
            logger.info("Created bot_tokens.csv")
        else:
            # ترحيل الملف القديم — إضافة الأعمدة الجديدة
            self._migrate_tokens_file()

    def _migrate_tokens_file(self):
        """ترحيل ملف التوكنات لإضافة الأعمدة الجديدة"""
        try:
            with open('bot_tokens.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                old_fields = reader.fieldnames or []
                rows = list(reader)

            # فحص الأعمدة المفقودة
            missing = [f for f in BOT_TOKEN_FIELDS if f not in old_fields]
            if not missing:
                return  # لا يحاجة للترحيل

            # إضافة الأعمدة المفقودة بقيم افتراضية
            for row in rows:
                for field in missing:
                    if field == 'freeze_until':
                        row[field] = ''
                    elif field == 'status':
                        row[field] = 'active' if row.get('is_active') == 'yes' else 'inactive'
                    elif field == 'description':
                        row[field] = ''
                    elif field == 'can_manage_bots':
                        row[field] = 'no'
                    elif field == 'features':
                        row[field] = ''
                    else:
                        row[field] = row.get(field, '')

            with open('bot_tokens.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=BOT_TOKEN_FIELDS)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in BOT_TOKEN_FIELDS})

            logger.info(f"Migrated bot_tokens.csv: added {len(missing)} columns")
        except Exception as e:
            logger.error(f"خطأ في ترحيل bot_tokens.csv: {e}")

    def _read_tokens(self):
        """قراءة جميع التوكنات"""
        rows = []
        try:
            with open('bot_tokens.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
        except Exception as e:
            logger.error(f"خطأ في قراءة bot_tokens.csv: {e}")
        return rows

    def _write_tokens(self, rows):
        """كتابة التوكنات"""
        try:
            with open('bot_tokens.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=BOT_TOKEN_FIELDS)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in BOT_TOKEN_FIELDS})
            return True
        except Exception as e:
            logger.error(f"خطأ في كتابة bot_tokens.csv: {e}")
            return False

    def _append_token(self, row):
        """إضافة توكن جديد"""
        try:
            with open('bot_tokens.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=BOT_TOKEN_FIELDS)
                writer.writerow({k: row.get(k, '') for k in BOT_TOKEN_FIELDS})
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة توكن: {e}")
            return False

    def get_all_bots(self):
        """الحصول على جميع البوتات (مع فحص التجميد التلقائي)"""
        self._check_freezes()
        return self._read_tokens()

    def get_active_bots(self):
        """الحصول على البوتات النشطة فقط"""
        self._check_freezes()
        return [b for b in self._read_tokens() if b.get('is_active') == 'yes']

    def get_bot_by_id(self, bot_id):
        """الحصول على بوت بالمعرف"""
        for b in self._read_tokens():
            if b['id'] == bot_id:
                return b
        return None

    def _check_freezes(self):
        """فحص التجميد التلقائي — إيقاف البوتات التي انتهى تاريخها"""
        rows = self._read_tokens()
        changed = False
        now = datetime.now()
        for row in rows:
            freeze_date = row.get('freeze_until', '')
            if freeze_date and row.get('is_active') == 'yes':
                try:
                    freeze_dt = datetime.strptime(freeze_date, '%Y-%m-%d')
                    if now >= freeze_dt:
                        # تجميد تلقائي
                        row['is_active'] = 'no'
                        row['status'] = 'frozen'
                        self.stop_bot(row['id'])
                        changed = True
                        logger.info(f"Bot {row['id']} auto-frozen (date reached: {freeze_date})")
                except:
                    pass
        if changed:
            self._write_tokens(rows)

    def add_bot(self, name, token, admin_ids='7146701713', description='', freeze_until='', can_manage_bots='no', features=''):
        """إضافة بوت جديد"""
        bot_id = f"BOT{str(int(datetime.now().timestamp()))[-6:]}"
        row = {
            'id': bot_id,
            'name': name,
            'token': token,
            'is_active': 'no',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'admin_ids': admin_ids,
            'last_started': '',
            'total_users': '0',
            'total_transactions': '0',
            'freeze_until': freeze_until,
            'status': 'inactive',
            'description': description,
            'can_manage_bots': can_manage_bots,
            'features': features,
        }
        if self._append_token(row):
            logger.info(f"Bot added: {bot_id} ({name})")
            return bot_id
        return None

    def delete_bot(self, bot_id):
        """حذف بوت"""
        rows = self._read_tokens()
        new_rows = [r for r in rows if r['id'] != bot_id]
        if len(new_rows) < len(rows):
            self.stop_bot(bot_id)
            return self._write_tokens(new_rows)
        return False

    def toggle_bot(self, bot_id, activate=True):
        """تفعيل أو إيقاف بوت"""
        rows = self._read_tokens()
        for row in rows:
            if row['id'] == bot_id:
                # فحص التجميد
                if activate and row.get('status') == 'frozen':
                    # إزالة التجميد
                    row['status'] = 'active'
                    row['freeze_until'] = ''

                row['is_active'] = 'yes' if activate else 'no'
                if activate:
                    row['last_started'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                    row['status'] = 'active'
                else:
                    self.stop_bot(bot_id)
                    row['status'] = 'inactive'
                return self._write_tokens(rows)
        return False

    def freeze_bot(self, bot_id, freeze_date_str):
        """تجميد بوت في تاريخ محدد"""
        rows = self._read_tokens()
        for row in rows:
            if row['id'] == bot_id:
                row['freeze_until'] = freeze_date_str
                row['status'] = 'scheduled_freeze'
                return self._write_tokens(rows)
        return False

    def unfreeze_bot(self, bot_id):
        """إلغاء تجميد بوت"""
        rows = self._read_tokens()
        for row in rows:
            if row['id'] == bot_id:
                row['freeze_until'] = ''
                row['status'] = 'active' if row.get('is_active') == 'yes' else 'inactive'
                return self._write_tokens(rows)
        return False

    def add_admin(self, bot_id, admin_id):
        """إضافة أدمن لبوت"""
        bot = self.get_bot_by_id(bot_id)
        if not bot:
            return False
        current_admins = bot.get('admin_ids', '')
        admin_list = [a.strip() for a in current_admins.split(',') if a.strip()]
        if admin_id not in admin_list:
            admin_list.append(admin_id)
            rows = self._read_tokens()
            for row in rows:
                if row['id'] == bot_id:
                    row['admin_ids'] = ','.join(admin_list)
                    return self._write_tokens(rows)
        return True  # موجود بالفعل

    def remove_admin(self, bot_id, admin_id):
        """إزالة أدمن من بوت"""
        bot = self.get_bot_by_id(bot_id)
        if not bot:
            return False
        current_admins = bot.get('admin_ids', '')
        admin_list = [a.strip() for a in current_admins.split(',') if a.strip() and a.strip() != admin_id]
        if len(admin_list) == 0:
            return False  # لا يمكن إزالة آخر أدمن
        rows = self._read_tokens()
        for row in rows:
            if row['id'] == bot_id:
                row['admin_ids'] = ','.join(admin_list)
                return self._write_tokens(rows)
        return False

    def update_bot_stats(self, bot_id, total_users=None, total_transactions=None):
        """تحديث إحصائيات بوت"""
        rows = self._read_tokens()
        for row in rows:
            if row['id'] == bot_id:
                if total_users is not None:
                    row['total_users'] = str(total_users)
                if total_transactions is not None:
                    row['total_transactions'] = str(total_transactions)
                return self._write_tokens(rows)
        return False

    def update_bot_features(self, bot_id, features):
        """تحديث مميزات بوت (features = JSON string)"""
        rows = self._read_tokens()
        for row in rows:
            if row['id'] == bot_id:
                row['features'] = features
                # إعادة تشغيل البوت لو كان شغال عشان التغييرات تسرى
                if row.get('is_active') == 'yes' and bot_id in self.active_bots:
                    self.stop_bot(bot_id)
                return self._write_tokens(rows)
        return False

    def get_stats(self):
        """إحصائيات شاملة"""
        self._check_freezes()
        bots = self._read_tokens()
        total = len(bots)
        active = sum(1 for b in bots if b.get('is_active') == 'yes')
        inactive = total - active
        frozen = sum(1 for b in bots if b.get('status') in ('frozen', 'scheduled_freeze'))
        total_users = sum(int(b.get('total_users', 0) or 0) for b in bots)
        total_transactions = sum(int(b.get('total_transactions', 0) or 0) for b in bots)
        running = len(self.active_bots)
        return {
            'total_bots': total,
            'active_bots': active,
            'inactive_bots': inactive,
            'frozen_bots': frozen,
            'running_bots': running,
            'total_users': total_users,
            'total_transactions': total_transactions,
            'bots': bots
        }

    def start_bot(self, bot_id, bot_factory=None):
        """تشغيل بوت في thread منفصل"""
        if bot_id in self.active_bots:
            return False, "البوت يعمل بالفعل"

        bot_info = self.get_bot_by_id(bot_id)
        if not bot_info:
            return False, "البوت غير موجود"

        # فحص التجميد
        if bot_info.get('status') == 'frozen':
            return False, "البوت مجمد — ألغِ التجميد أولاً"

        token = bot_info['token']
        if not token or len(token) < 20:
            return False, "التوكن غير صالح"

        try:
            from comprehensive_bot import ComprehensiveDUXBot
            features_str = bot_info.get('features', '')
            bot = ComprehensiveDUXBot(token, features=features_str if features_str else None)
            thread = threading.Thread(target=bot.run, daemon=True)
            thread.start()

            self.active_bots[bot_id] = {
                'bot': bot,
                'thread': thread,
                'started_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'token': token,
                'name': bot_info['name']
            }

            logger.info(f"Bot started: {bot_id} ({bot_info['name']})")
            return True, f"تم تشغيل البوت: {bot_info['name']}"

        except Exception as e:
            logger.error(f"خطأ في تشغيل البوت {bot_id}: {e}")
            return False, f"خطأ: {str(e)}"

    def stop_bot(self, bot_id):
        """إيقاف بوت"""
        if bot_id not in self.active_bots:
            return False, "البوت لا يعمل حالياً"

        try:
            bot_info = self.active_bots[bot_id]
            bot = bot_info['bot']
            if hasattr(bot, 'running'):
                bot.running = False
            del self.active_bots[bot_id]
            logger.info(f"Bot stopped: {bot_id}")
            return True, "تم إيقاف البوت"
        except Exception as e:
            logger.error(f"خطأ في إيقاف البوت {bot_id}: {e}")
            return False, f"خطأ: {str(e)}"

    def start_all_active(self):
        """تشغيل جميع البوتات النشطة"""
        self._check_freezes()
        active_bots = self.get_active_bots()
        started = 0
        for bot in active_bots:
            success, msg = self.start_bot(bot['id'])
            if success:
                started += 1
        logger.info(f"Started {started}/{len(active_bots)} active bots")
        return started

    def is_running(self, bot_id):
        """فحص إذا كان البوت يعمل"""
        return bot_id in self.active_bots

    def get_bot_status_icon(self, bot):
        """أيقونة حالة البوت"""
        is_running = bot.get('id') in self.active_bots
        is_active = bot.get('is_active') == 'yes'
        status = bot.get('status', '')

        if is_running:
            return '🟢'
        elif status == 'frozen':
            return '🧊'
        elif status == 'scheduled_freeze':
            return '⏰'
        elif is_active:
            return '⏸️'
        else:
            return '❌'
