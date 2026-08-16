#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام المطابقة P2P — Matching System (SQLite-backed)
يطابق عميل إيداع مع عميل سحب بنفس المبلغ والعملة والشركة
يدير الدردشة الوهمية، تأكيد الكود، التقييم، والنزاعات

All data is now stored in SQLite via agent_db.py functions.
This class is a thin wrapper maintaining backward compatibility.
"""

import os
import csv
import json
import random
import string
import logging
from datetime import datetime

import agent_db as adb

logger = logging.getLogger(__name__)


class MatchManager:
    """مدير نظام المطابقة — SQLite-backed via agent_db"""

    MATCH_REQUEST_FIELDS = ['id', 'user_id', 'customer_id', 'type', 'amount', 'currency',
                            'company_id', 'company_name', 'payment_method_id', 'status',
                            'created_at', 'matched_at', 'match_id', 'alias', 'bot_id',
                            'assigned_agent_id']

    MATCH_FIELDS = ['id', 'deposit_request_id', 'withdraw_request_id', 'depositor_id',
                    'withdrawer_id', 'depositor_alias', 'withdrawer_alias', 'amount',
                    'currency', 'company_id', 'company_name', 'status', 'confirmation_code',
                    'created_at', 'completed_at', 'depositor_rated', 'withdrawer_rated',
                    'dispute_status', 'bot_id', 'agent_id', 'escrow_amount', 'escrow_released']

    CHAT_FIELDS = ['id', 'match_id', 'sender_id', 'sender_alias', 'message', 'timestamp']

    RATING_FIELDS = ['id', 'match_id', 'rater_id', 'rated_id', 'rating', 'comment', 'timestamp']

    DISPUTE_FIELDS = ['id', 'match_id', 'raised_by', 'reason', 'status', 'admin_response',
                      'created_at', 'resolved_at']

    MATCH_BOT_CONFIG_FIELDS = ['bot_id', 'bot_name', 'token', 'is_active', 'match_count',
                               'created_at']

    def __init__(self):
        self.init_matching_files()

    def init_matching_files(self):
        """Create CSV stubs if they don't exist (for backward compatibility).
        New data goes to SQLite — CSV files are no longer written to."""
        for filename, fields in [
            ('match_requests.csv', self.MATCH_REQUEST_FIELDS),
            ('matches.csv', self.MATCH_FIELDS),
            ('chat_messages.csv', self.CHAT_FIELDS),
            ('ratings.csv', self.RATING_FIELDS),
            ('disputes.csv', self.DISPUTE_FIELDS),
        ]:
            if not os.path.exists(filename):
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    import csv as _csv
                    _csv.writer(f).writerow(fields)
        # match_bot_config still uses CSV (small config, rarely changes)
        filename = 'match_bot_config.csv'
        if not os.path.exists(filename):
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                import csv as _csv
                _csv.writer(f).writerow(self.MATCH_BOT_CONFIG_FIELDS)

    def generate_alias(self):
        return adb._generate_alias()

    def generate_id(self, prefix):
        return adb._generate_id(prefix)

    # ── Match Bot Config (still CSV — small config) ──────────────────────────

    def get_match_bot_config(self):
        rows = []
        try:
            with open('match_bot_config.csv', 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    rows.append(row)
        except Exception:
            pass
        return rows

    def get_active_match_bots(self):
        return [b for b in self.get_match_bot_config() if b.get('is_active') == 'yes']

    def assign_bot(self):
        bots = self.get_active_match_bots()
        if not bots:
            return ''
        bots.sort(key=lambda b: int(b.get('match_count', 0) or 0))
        selected = bots[0]
        self._increment_bot_match_count(selected['bot_id'])
        return selected['bot_id']

    def _increment_bot_match_count(self, bot_id):
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
            logger.error(f"Error updating bot match count: {e}")

    def add_match_bot(self, bot_id, bot_name, token):
        rows = self.get_match_bot_config()
        for row in rows:
            if row.get('bot_id') == bot_id:
                return False, "البوت موجود بالفعل"
        rows.append({
            'bot_id': bot_id, 'bot_name': bot_name, 'token': token,
            'is_active': 'yes', 'match_count': '0',
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
                except Exception:
                    return False
        return False

    def remove_match_bot(self, bot_id):
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
        except Exception:
            return False

    # ── Match Requests (SQLite) ──────────────────────────────────────────────

    def create_match_request(self, user_id, customer_id, req_type, amount, currency,
                               company_id, company_name, payment_method_id, bot_id=''):
        bot_id = bot_id or self.assign_bot()
        return adb.db_create_match_request(
            user_id, customer_id, req_type, amount, currency,
            company_id, company_name, payment_method_id,
            bot_id=bot_id)

    def get_active_request_by_user(self, user_id):
        return adb.db_get_active_request_by_user(user_id)

    def find_match(self, request):
        return adb.db_find_match(request)

    def _update_request_status(self, req_id, status, match_id=''):
        adb.db_update_request_status(req_id, status, match_id)

    # ── Matches (SQLite) ──────────────────────────────────────────────────────

    def create_match(self, deposit_req, withdraw_req):
        return adb.db_create_match(deposit_req, withdraw_req)

    def get_match_by_id(self, match_id):
        return adb.db_get_match_by_id(match_id)

    def get_match_by_user(self, user_id):
        return adb.db_get_match_by_user(user_id)

    def update_match_status(self, match_id, status, extra_fields=None):
        return adb.db_update_match_status(match_id, status, extra_fields)

    def set_confirmation_code(self, match_id, code):
        return adb.db_set_confirmation_code(match_id, code)

    def cancel_match(self, match_id, cancelled_by=''):
        return adb.db_cancel_match(match_id, cancelled_by)

    def get_active_matches(self):
        return adb.db_get_active_matches()

    # ── Chat (SQLite) ──────────────────────────────────────────────────────────

    def send_chat_message(self, match_id, sender_id, message):
        return adb.db_send_chat_message(match_id, sender_id, message)

    def get_chat_history(self, match_id):
        return adb.db_get_chat_history(match_id)

    # ── Ratings (SQLite) ──────────────────────────────────────────────────────

    def rate_user(self, match_id, rater_id, rating, comment=''):
        return adb.db_rate_user(match_id, rater_id, rating, comment)

    def get_user_rating(self, user_id):
        return adb.db_get_user_rating(user_id)

    # ── Disputes (SQLite) ────────────────────────────────────────────────────

    def open_dispute(self, match_id, user_id, reason):
        return adb.db_open_dispute(match_id, user_id, reason)

    def resolve_dispute(self, dispute_id, resolution):
        return adb.db_resolve_dispute(dispute_id, resolution)

    def get_active_disputes(self):
        return adb.db_get_active_disputes()

    # ── Agent Matching (delegates to agent_db.py) ────────────────────────────

    def find_available_agent(self, amount, txn_type='deposit'):
        """Legacy compat — pick agent via agent_db."""
        result = adb.pick_agent_for_request(txn_type, amount)
        if not result:
            return None
        return {'id': result['id'], 'name': result['name'],
                'balance': result['balance'], 'daily_count': 0}

    def create_agent_match(self, user_request, agent):
        """Create agent match via agent_db (escrow included via pick_and_create_transaction)."""
        agent_id = agent['id']
        # Use agent_db to pick + create transaction + hold escrow
        result = adb.pick_and_create_transaction(
            user_request['type'],
            float(user_request['amount']),
            user_request.get('currency', 'EGP'),
            str(user_request.get('user_id', '')),
            user_request.get('user_name', ''),
            user_request.get('id', ''),
        )
        if not result:
            return None, None

        agent_info = result['agent']
        txn_id = result['txn_id']
        user_alias = self.generate_alias()
        agent_alias = self.generate_alias()

        # Create the match record
        if user_request['type'] == 'deposit':
            deposit_req_id = user_request['id']
            withdraw_req_id = ''
            depositor_id = str(user_request['user_id'])
            withdrawer_id = f"AGENT_{agent_id}"
            dep_alias = user_alias
            with_alias = agent_alias
        else:
            deposit_req_id = ''
            withdraw_req_id = user_request['id']
            depositor_id = f"AGENT_{agent_id}"
            withdrawer_id = str(user_request['user_id'])
            dep_alias = agent_alias
            with_alias = user_alias

        match_id = self.generate_id('MTCH')
        conn = adb._conn()
        try:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('''INSERT INTO matches
                (id, deposit_request_id, withdraw_request_id,
                 depositor_id, withdrawer_id, depositor_alias, withdrawer_alias,
                 amount, currency, company_id, company_name,
                 status, confirmation_code, created_at,
                 depositor_rated, withdrawer_rated, dispute_status,
                 bot_id, agent_id, escrow_amount, escrow_released)
                VALUES (?,?,?,?,?,?,?,?,?,'active','',?, 'no','no','none',?,?,?,0)''', (
                match_id, deposit_req_id, withdraw_req_id,
                depositor_id, withdrawer_id, dep_alias, with_alias,
                float(user_request['amount']), user_request.get('currency', 'EGP'),
                str(user_request.get('company_id', '')),
                str(user_request.get('company_name', '')),
                _now(), agent_id, agent_id, float(user_request['amount'])))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating agent match: {e}")
            return None, None
        finally:
            conn.close()

        # Link txn to match request
        if user_request.get('id'):
            adb.set_txn_match_request(txn_id, user_request['id'])

        # Update user request status
        self._update_request_status(user_request['id'], 'matched', match_id)

        logger.info(f"Agent match created: {match_id} (agent={agent_id})")
        return match_id, agent_alias

    def get_agent_payment_methods(self, agent_id):
        """Get payment methods for an agent via agent_db."""
        return adb.list_payment_methods(agent_id)

    # ── Helper for dashboard ───────────────────────────────────────────────────

    def get_completed_matches(self, limit=50):
        return adb.db_get_completed_matches(limit)

    def get_match_requests(self, status='', limit=100):
        return adb.db_get_match_requests(status, limit)

    def delete_request(self, req_id):
        return adb.db_delete_request(req_id)
