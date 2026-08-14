#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام المطابقة P2P — Matching System
يطابق عميل إيداع مع عميل سحب بنفس المبلغ والعملة والشركة
يدير الدردشة الوهمية، تأكيد الكود، التقييم، والنزاعات
"""

import os
import csv
import json
import random
import string
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class MatchManager:
    """مدير نظام المطابقة"""

    MATCH_REQUEST_FIELDS = ['id', 'user_id', 'customer_id', 'type', 'amount', 'currency',
                            'company_id', 'company_name', 'payment_method_id', 'status',
                            'created_at', 'matched_at', 'match_id', 'alias', 'bot_id']

    MATCH_FIELDS = ['id', 'deposit_request_id', 'withdraw_request_id', 'depositor_id',
                    'withdrawer_id', 'depositor_alias', 'withdrawer_alias', 'amount',
                    'currency', 'company_id', 'company_name', 'status', 'confirmation_code',
                    'created_at', 'completed_at', 'depositor_rated', 'withdrawer_rated',
                    'dispute_status', 'bot_id']

    CHAT_FIELDS = ['id', 'match_id', 'sender_id', 'sender_alias', 'message', 'timestamp']

    RATING_FIELDS = ['id', 'match_id', 'rater_id', 'rated_id', 'rating', 'comment', 'timestamp']

    DISPUTE_FIELDS = ['id', 'match_id', 'raised_by', 'reason', 'status', 'admin_response',
                      'created_at', 'resolved_at']

    MATCH_BOT_CONFIG_FIELDS = ['bot_id', 'bot_name', 'token', 'is_active', 'match_count',
                               'created_at']

    def __init__(self):
        self.init_matching_files()

    def init_matching_files(self):
        """إنشاء ملفات نظام المطابقة"""
        files = {
            'match_requests.csv': self.MATCH_REQUEST_FIELDS,
            'matches.csv': self.MATCH_FIELDS,
            'chat_messages.csv': self.CHAT_FIELDS,
            'ratings.csv': self.RATING_FIELDS,
            'disputes.csv': self.DISPUTE_FIELDS,
            'match_bot_config.csv': self.MATCH_BOT_CONFIG_FIELDS,
        }
        for filename, fields in files.items():
            if not os.path.exists(filename):
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(fields)
                logger.info(f"Created matching file: {filename}")
            else:
                self._migrate_file(filename, fields)

    def generate_alias(self):
        """توليد اسم وهمي مؤقت"""
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"عميل-{random_part}"

    def _migrate_file(self, filename, expected_fields):
        """ترحيل ملف CSV لإضافة الأعمدة الجديدة"""
        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                old_fields = reader.fieldnames or []
                rows = list(reader)

            missing = [f for f in expected_fields if f not in old_fields]
            if not missing:
                return

            for row in rows:
                for field in missing:
                    row[field] = ''

            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=expected_fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in expected_fields})

            logger.info(f"Migrated {filename}: added {len(missing)} columns: {missing}")
        except Exception as e:
            logger.error(f"خطأ في ترحيل {filename}: {e}")

    def get_match_bot_config(self):
        """قراءة إعدادات بوتات المطابقة"""
        rows = []
        try:
            with open('match_bot_config.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
        except:
            pass
        return rows

    def get_active_match_bots(self):
        """الحصول على بوتات المطابقة النشطة"""
        return [b for b in self.get_match_bot_config() if b.get('is_active') == 'yes']

    def assign_bot(self):
        """توزيع بوت للمطابقة (round-robin)"""
        bots = self.get_active_match_bots()
        if not bots:
            return ''
        # اختيار البوت بأقل عدد مطابقات
        bots.sort(key=lambda b: int(b.get('match_count', 0) or 0))
        selected = bots[0]
        # زيادة العداد
        self._increment_bot_match_count(selected['bot_id'])
        return selected['bot_id']

    def _increment_bot_match_count(self, bot_id):
        """زيادة عداد مطابقات البوت"""
        rows = self.get_match_bot_config()
        for row in rows:
            if row.get('bot_id') == bot_id:
                row['match_count'] = str(int(row.get('match_count', 0) or 0) + 1)
                break
        try:
            with open('match_bot_config.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.MATCH_BOT_CONFIG_FIELDS)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in self.MATCH_BOT_CONFIG_FIELDS})
        except Exception as e:
            logger.error(f"خطأ في تحديث عداد البوت: {e}")

    def add_match_bot(self, bot_id, bot_name, token):
        """إضافة بوت مطابقة"""
        rows = self.get_match_bot_config()
        for row in rows:
            if row.get('bot_id') == bot_id:
                return False, "البوت موجود بالفعل"
        rows.append({
            'bot_id': bot_id,
            'bot_name': bot_name,
            'token': token,
            'is_active': 'yes',
            'match_count': '0',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        try:
            with open('match_bot_config.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.MATCH_BOT_CONFIG_FIELDS)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in self.MATCH_BOT_CONFIG_FIELDS})
            return True, None
        except Exception as e:
            return False, str(e)

    def toggle_match_bot(self, bot_id):
        """تفعيل/إيقاف بوت مطابقة"""
        rows = self.get_match_bot_config()
        for row in rows:
            if row.get('bot_id') == bot_id:
                row['is_active'] = 'no' if row.get('is_active') == 'yes' else 'yes'
                try:
                    with open('match_bot_config.csv', 'w', newline='', encoding='utf-8-sig') as f:
                        writer = csv.DictWriter(f, fieldnames=self.MATCH_BOT_CONFIG_FIELDS)
                        writer.writeheader()
                        for r in rows:
                            writer.writerow({k: r.get(k, '') for k in self.MATCH_BOT_CONFIG_FIELDS})
                    return True
                except:
                    return False
        return False

    def remove_match_bot(self, bot_id):
        """حذف بوت مطابقة"""
        rows = self.get_match_bot_config()
        new_rows = [r for r in rows if r.get('bot_id') != bot_id]
        if len(new_rows) == len(rows):
            return False
        try:
            with open('match_bot_config.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.MATCH_BOT_CONFIG_FIELDS)
                writer.writeheader()
                for row in new_rows:
                    writer.writerow({k: row.get(k, '') for k in self.MATCH_BOT_CONFIG_FIELDS})
            return True
        except:
            return False

    def generate_id(self, prefix):
        """توليد ID فريد"""
        return f"{prefix}{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(10,99)}"

    def create_match_request(self, user_id, customer_id, req_type, amount, currency,
                               company_id, company_name, payment_method_id, bot_id=''):
        """إنشاء طلب مطابقة جديد"""
        # فحص عدم وجود طلب نشط لنفس المستخدم
        existing = self.get_active_request_by_user(user_id)
        if existing:
            return None, "لديك طلب مطابقة نشط بالفعل"

        req_id = self.generate_id('REQ')
        alias = self.generate_alias()

        # توزيع بوت تلقائياً إذا لم يُحدد
        if not bot_id:
            bot_id = self.assign_bot()

        with open('match_requests.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([req_id, user_id, customer_id, req_type, amount, currency,
                           company_id, company_name, payment_method_id, 'waiting',
                           datetime.now().strftime('%Y-%m-%d %H:%M'), '', '', alias, bot_id])

        logger.info(f"Match request created: {req_id} by user {user_id} (bot: {bot_id or 'none'})")
        return req_id, None

    def get_active_request_by_user(self, user_id):
        """الحصول على طلب نشط لمستخدم"""
        try:
            with open('match_requests.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['user_id'] == str(user_id) and row['status'] == 'waiting':
                        return row
        except:
            pass
        return None

    def find_match(self, request):
        """البحث عن مطابقة للطلب"""
        opposite_type = 'withdraw' if request['type'] == 'deposit' else 'deposit'

        try:
            with open('match_requests.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if (row['status'] == 'waiting' and
                        row['type'] == opposite_type and
                        float(row['amount']) == float(request['amount']) and
                        row['currency'] == request['currency'] and
                        row['company_id'] == request['company_id'] and
                        row['user_id'] != request['user_id']):
                        return row
        except:
            pass
        return None

    def create_match(self, deposit_req, withdraw_req):
        """إنشاء مطابقة بين طلبين"""
        match_id = self.generate_id('MTCH')
        depositor_alias = self.generate_alias()
        withdrawer_alias = self.generate_alias()
        bot_id = deposit_req.get('bot_id', '') or withdraw_req.get('bot_id', '')

        with open('matches.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                match_id,
                deposit_req['id'], withdraw_req['id'],
                deposit_req['user_id'], withdraw_req['user_id'],
                depositor_alias, withdrawer_alias,
                deposit_req['amount'], deposit_req['currency'],
                deposit_req['company_id'], deposit_req['company_name'],
                'active', '',  # confirmation_code empty, status=active
                datetime.now().strftime('%Y-%m-%d %H:%M'), '',  # completed_at
                'no', 'no',  # rated flags
                'none',  # dispute_status
                bot_id  # bot_id
            ])

        # تحديث حالة الطلبين إلى matched
        self._update_request_status(deposit_req['id'], 'matched', match_id)
        self._update_request_status(withdraw_req['id'], 'matched', match_id)

        logger.info(f"Match created: {match_id}")
        return match_id

    def _update_request_status(self, req_id, status, match_id=''):
        """تحديث حالة طلب المطابقة"""
        rows = []
        try:
            with open('match_requests.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == req_id:
                        row['status'] = status
                        if match_id:
                            row['match_id'] = match_id
                        if status == 'matched':
                            row['matched_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                    rows.append(row)

            with open('match_requests.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.MATCH_REQUEST_FIELDS)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in self.MATCH_REQUEST_FIELDS})
        except Exception as e:
            logger.error(f"Error updating request status: {e}")

    def get_match_by_id(self, match_id):
        """الحصول على مطابقة بالـ ID"""
        try:
            with open('matches.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == match_id:
                        return row
        except:
            pass
        return None

    def get_match_by_user(self, user_id):
        """الحصول على مطابقة نشطة لمستخدم"""
        try:
            with open('matches.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if (row['status'] not in ('completed', 'cancelled') and
                        (row['depositor_id'] == str(user_id) or
                         row['withdrawer_id'] == str(user_id))):
                        return row
        except:
            pass
        return None

    def update_match_status(self, match_id, status, extra_fields=None):
        """تحديث حالة المطابقة"""
        rows = []
        try:
            with open('matches.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == match_id:
                        row['status'] = status
                        if status == 'completed':
                            row['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                        if extra_fields:
                            for k, v in extra_fields.items():
                                if k in row:
                                    row[k] = v
                    rows.append(row)

            with open('matches.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.MATCH_FIELDS)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in self.MATCH_FIELDS})
            return True
        except Exception as e:
            logger.error(f"Error updating match status: {e}")
            return False

    def set_confirmation_code(self, match_id, code):
        """حفظ كود التأكيد (سرّي)"""
        return self.update_match_status(match_id, 'awaiting_code',
                                         extra_fields={'confirmation_code': code})

    def send_chat_message(self, match_id, sender_id, message):
        """حفظ رسالة دردشة وإرجاع بياناتها للتوجيه"""
        match = self.get_match_by_id(match_id)
        if not match:
            return None

        sender_alias = (match['depositor_alias'] if sender_id == int(match['depositor_id'])
                       else match['withdrawer_alias'])
        receiver_id = (match['withdrawer_id'] if sender_id == int(match['depositor_id'])
                      else match['depositor_id'])

        msg_id = self.generate_id('MSG')
        with open('chat_messages.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([msg_id, match_id, sender_id, sender_alias,
                           message, datetime.now().strftime('%Y-%m-%d %H:%M')])

        return {
            'msg_id': msg_id,
            'sender_alias': sender_alias,
            'receiver_id': receiver_id,
            'message': message
        }

    def get_chat_history(self, match_id):
        """الحصول على سجل الدردشة الكامل (للإدمن)"""
        messages = []
        try:
            with open('chat_messages.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['match_id'] == match_id:
                        messages.append(row)
        except:
            pass
        return messages

    def rate_user(self, match_id, rater_id, rating, comment=''):
        """تقييم مستخدم"""
        match = self.get_match_by_id(match_id)
        if not match:
            return False

        rated_id = (match['withdrawer_id'] if rater_id == int(match['depositor_id'])
                   else match['depositor_id'])

        rating_id = self.generate_id('RTNG')
        with open('ratings.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([rating_id, match_id, rater_id, rated_id, rating, comment,
                           datetime.now().strftime('%Y-%m-%d %H:%M')])

        # تحديث علم التقييم في المطابقة
        if rater_id == int(match['depositor_id']):
            self.update_match_status(match_id, match['status'],
                                      extra_fields={'depositor_rated': 'yes'})
        else:
            self.update_match_status(match_id, match['status'],
                                      extra_fields={'withdrawer_rated': 'yes'})
        return True

    def get_user_rating(self, user_id):
        """الحصول على متوسط تقييم مستخدم"""
        ratings = []
        try:
            with open('ratings.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['rated_id'] == str(user_id):
                        ratings.append(int(row['rating']))
        except:
            pass
        if not ratings:
            return None
        return sum(ratings) / len(ratings)

    def open_dispute(self, match_id, user_id, reason):
        """فتح نزاع"""
        dispute_id = self.generate_id('DSPT')
        with open('disputes.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([dispute_id, match_id, user_id, reason, 'open', '',
                           datetime.now().strftime('%Y-%m-%d %H:%M'), ''])

        self.update_match_status(match_id, 'disputed',
                                 extra_fields={'dispute_status': 'open'})
        logger.info(f"Dispute opened: {dispute_id} for match {match_id}")
        return dispute_id

    def resolve_dispute(self, dispute_id, resolution):
        """حل نزاع بواسطة الإدمن"""
        rows = []
        try:
            with open('disputes.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == dispute_id:
                        row['status'] = 'resolved_by_admin'
                        row['admin_response'] = resolution
                        row['resolved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                    rows.append(row)

            with open('disputes.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.DISPUTE_FIELDS)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in self.DISPUTE_FIELDS})
            return True
        except Exception as e:
            logger.error(f"Error resolving dispute: {e}")
            return False

    def get_active_disputes(self):
        """الحصول على النزاعات المفتوحة"""
        disputes = []
        try:
            with open('disputes.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['status'] == 'open':
                        disputes.append(row)
        except:
            pass
        return disputes

    def cancel_match(self, match_id, cancelled_by):
        """إلغاء مطابقة"""
        self.update_match_status(match_id, 'cancelled',
                                 extra_fields={'dispute_status': 'cancelled'})
        logger.info(f"Match {match_id} cancelled by {cancelled_by}")

    def get_active_matches(self):
        """الحصول على كل المطابقات النشطة"""
        matches = []
        try:
            with open('matches.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['status'] not in ('completed', 'cancelled'):
                        matches.append(row)
        except:
            pass
        return matches

    # ==================== Agent Matching (Phase 6) ====================

    def find_available_agent(self, amount, txn_type='deposit'):
        """Find an available agent bot to act as counterparty."""
        agents = []
        try:
            with open('agent_bots.csv', 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('is_active') != 'yes' or row.get('traffic_enabled') != 'yes':
                        continue
                    bal = float(row.get('balance', 0) or 0)
                    dep = float(row.get('security_deposit', 0) or 0)
                    daily = int(row.get('current_daily_count', 0) or 0)
                    max_daily = int(row.get('max_daily_transactions', 50) or 50)
                    if bal <= dep:
                        continue
                    if daily >= max_daily:
                        continue
                    if txn_type == 'deposit' and bal < amount:
                        continue
                    agents.append({
                        'id': row.get('id', ''), 'name': row.get('bot_name', ''),
                        'balance': bal, 'daily_count': daily,
                        'all_data': row
                    })
        except:
            pass
        if not agents:
            return None
        # Pick lowest daily count (round-robin)
        agents.sort(key=lambda x: x['daily_count'])
        return agents[0]

    def create_agent_match(self, user_request, agent):
        """Create a match between a user request and an agent bot.
        Agent acts as the counterparty (opposite type)."""
        match_id = self.generate_id('MTCH')
        user_alias = self.generate_alias()
        agent_alias = self.generate_alias()
        agent_id = agent['id']

        # Determine roles: if user is deposit → agent is withdrawer (and vice versa)
        if user_request['type'] == 'deposit':
            depositor_id = user_request['user_id']
            withdrawer_id = f"AGENT_{agent_id}"
            depositor_alias = user_alias
            withdrawer_alias = agent_alias
            # Agent pays user → balance goes DOWN
            balance_change = -float(user_request['amount'])
        else:
            depositor_id = f"AGENT_{agent_id}"
            withdrawer_id = user_request['user_id']
            depositor_alias = agent_alias
            withdrawer_alias = user_alias
            # User pays agent → balance goes UP
            balance_change = float(user_request['amount'])

        # Write match
        try:
            with open('matches.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    match_id,
                    user_request['id'], '',  # deposit_req_id, withdraw_req_id (agent has no request)
                    depositor_id, withdrawer_id,
                    depositor_alias, withdrawer_alias,
                    user_request['amount'], user_request['currency'],
                    user_request.get('company_id', ''), user_request.get('company_name', ''),
                    'active', '',  # confirmation_code, status
                    datetime.now().strftime('%Y-%m-%d %H:%M'), '',
                    'no', 'no', 'none',
                    agent_id  # bot_id = agent_id
                ])
        except:
            pass

        # Update user request status
        self._update_request_status(user_request['id'], 'matched', match_id)

        # Update agent balance + daily count + stats
        self._update_agent_balance(agent_id, balance_change, user_request['type'])

        # Log agent transaction
        self._log_agent_transaction(agent_id, match_id, user_request, 'pending')

        logger.info(f"Agent match created: {match_id} (agent={agent_id}, user={user_request['user_id']})")
        return match_id, agent_alias

    def _update_agent_balance(self, agent_id, change, txn_type):
        """Update agent balance, daily count, and stats."""
        try:
            rows = []
            with open('agent_bots.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('id') == agent_id:
                        current_bal = float(row.get('balance', 0) or 0)
                        new_bal = current_bal + change
                        row['balance'] = str(new_bal)
                        row['current_daily_count'] = str(int(row.get('current_daily_count', 0) or 0) + 1)
                        if txn_type == 'deposit':
                            row['total_deposits_processed'] = str(int(row.get('total_deposits_processed', 0) or 0) + 1)
                        else:
                            row['total_withdrawals_processed'] = str(int(row.get('total_withdrawals_processed', 0) or 0) + 1)
                        row['total_volume'] = str(float(row.get('total_volume', 0) or 0) + abs(change))
                        row['last_active'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        # Check traffic stop
                        dep = float(row.get('security_deposit', 0) or 0)
                        if new_bal <= dep:
                            row['traffic_enabled'] = 'no'
                    rows.append(row)
            with open('agent_bots.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
        except Exception as e:
            logger.error(f"Agent balance update error: {e}")

    def _log_agent_transaction(self, agent_id, match_id, user_request, status):
        """Log a transaction for an agent."""
        try:
            import secrets as _sec
            txn_id = f"AGT{_sec.token_hex(3).upper()}"
            with open('agent_transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    txn_id, agent_id, match_id,
                    user_request['type'], user_request['amount'], user_request.get('currency', ''),
                    status, user_request['user_id'], '',  # user_name
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ''
                ])
        except:
            pass

    def get_agent_payment_methods(self, agent_id):
        """Get payment methods for an agent."""
        methods = []
        try:
            with open('agent_payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('agent_id') == agent_id and row.get('is_active') == 'yes':
                        methods.append(row)
        except:
            pass
        return methods
