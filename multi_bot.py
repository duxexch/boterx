#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام إدارة البوتات المتعددة — Multi-Bot Manager
يدعم تشغيل عدة بوتات بتوكنز مختلفة في نفس الوقت
"""

import os
import csv
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

BOT_TOKEN_FIELDS = [
    'id', 'name', 'token', 'is_active', 'created_at',
    'admin_ids', 'last_started', 'total_users', 'total_transactions'
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
        """الحصول على جميع البوتات"""
        return self._read_tokens()

    def get_active_bots(self):
        """الحصول على البوتات النشطة فقط"""
        return [b for b in self._read_tokens() if b.get('is_active') == 'yes']

    def get_bot_by_id(self, bot_id):
        """الحصول على بوت بالمعرف"""
        for b in self._read_tokens():
            if b['id'] == bot_id:
                return b
        return None

    def add_bot(self, name, token, admin_ids='7146701713'):
        """إضافة بوت جديد"""
        bot_id = f"BOT{str(int(datetime.now().timestamp()))[-6:]}"
        row = {
            'id': bot_id,
            'name': name,
            'token': token,
            'is_active': 'no',  # يبدأ متوقفاً حتى التفعيل
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'admin_ids': admin_ids,
            'last_started': '',
            'total_users': '0',
            'total_transactions': '0'
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
            # إيقاف البوت إن كان يعمل
            self.stop_bot(bot_id)
            return self._write_tokens(new_rows)
        return False

    def toggle_bot(self, bot_id, activate=True):
        """تفعيل أو إيقاف بوت"""
        rows = self._read_tokens()
        for row in rows:
            if row['id'] == bot_id:
                row['is_active'] = 'yes' if activate else 'no'
                if activate:
                    row['last_started'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                else:
                    self.stop_bot(bot_id)
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

    def get_stats(self):
        """إحصائيات شاملة"""
        bots = self._read_tokens()
        total = len(bots)
        active = sum(1 for b in bots if b.get('is_active') == 'yes')
        inactive = total - active
        total_users = sum(int(b.get('total_users', 0) or 0) for b in bots)
        total_transactions = sum(int(b.get('total_transactions', 0) or 0) for b in bots)
        running = len(self.active_bots)
        return {
            'total_bots': total,
            'active_bots': active,
            'inactive_bots': inactive,
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

        token = bot_info['token']
        if not token or len(token) < 20:
            return False, "التوكن غير صالح"

        try:
            # استيراد ComprehensiveDUXBot ديناميكياً
            from comprehensive_bot import ComprehensiveDUXBot

            # إنشاء instance جديد
            bot = ComprehensiveDUXBot(token)
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
            # إيقاف الـ polling loop
            if hasattr(bot, 'running'):
                bot.running = False
            # حذف من القائمة النشطة
            del self.active_bots[bot_id]
            logger.info(f"Bot stopped: {bot_id}")
            return True, "تم إيقاف البوت"
        except Exception as e:
            logger.error(f"خطأ في إيقاف البوت {bot_id}: {e}")
            return False, f"خطأ: {str(e)}"

    def start_all_active(self):
        """تشغيل جميع البوتات النشطة"""
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
