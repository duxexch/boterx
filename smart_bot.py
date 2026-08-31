#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_bot.py — Smart Bot Engine
Smart Router + Auto-Reply + Analytics + Bot Chains + Smart Notifications + Bot Templates + Webhooks
"""

import os
import csv
import json
import time
import logging
import threading
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ─── Feature Labels (Arabic/English) ───
FEATURE_LABELS = {
    'deposit': {'ar': '💰 إيداع', 'en': '💰 Deposit', 'icon': '💰'},
    'withdraw': {'ar': '💸 سحب', 'en': '💸 Withdraw', 'icon': '💸'},
    'matching': {'ar': '🔄 مطابقة', 'en': '🔄 Matching', 'icon': '🔄'},
    'trading': {'ar': '💱 تداول', 'en': '💱 Trading', 'icon': '💱'},
    'compensation': {'ar': '💎 تعويض', 'en': '💎 Compensation', 'icon': '💎'},
    'games': {'ar': '🎮 ألعاب', 'en': '🎮 Games', 'icon': '🎮'},
    'referral': {'ar': '🎁 إحالات', 'en': '🎁 Referrals', 'icon': '🎁'},
    'complaints': {'ar': '📋 شكاوى', 'en': '📋 Complaints', 'icon': '📋'},
    'apps': {'ar': '📱 تطبيقات', 'en': '📱 Apps', 'icon': '📱'},
    'multi_lang': {'ar': '🌐 لغات', 'en': '🌐 Languages', 'icon': '🌐'},
}

# ─── Bot Templates ───
BOT_TEMPLATES = {
    'games': {
        'name': '🎮 بوت الألعاب',
        'description': 'يانصيب + عجلة حظ + ألعاب متنوعة',
        'features': '["games"]',
        'default_name': 'Games Bot',
    },
    'finance': {
        'name': '💰 بوت مالي',
        'description': 'إيداع + سحب + تعويض',
        'features': '["deposit","withdraw","compensation"]',
        'default_name': 'Finance Bot',
    },
    'matching': {
        'name': '🤝 بوت المطابقة',
        'description': 'نظام المطابقة P2P + الوكالة',
        'features': '["matching"]',
        'default_name': 'Matching Bot',
    },
    'broadcast': {
        'name': '📢 بوت البث',
        'description': 'بث + قنوات + relay',
        'features': '["apps"]',
        'default_name': 'Broadcast Bot',
    },
    'full': {
        'name': '🏢 بوت مؤسسي',
        'description': 'كل الميزات المتاحة',
        'features': '',
        'default_name': 'Full Bot',
    },
}


class SmartBotEngine:
    """المحرك الذكي — يجمع كل الميزات الذكية في مكان واحد"""

    def __init__(self, bot_instance):
        """
        bot_instance: كائن ComprehensiveDUXBot
        """
        self.bot = bot_instance
        self.token = bot_instance.token
        self.bot_id = self._detect_bot_id()

        # ─── Auto-Reply Cache ───
        self._auto_replies_cache = None
        self._auto_replies_cache_time = 0
        self._auto_replies_ttl = 60  # seconds

        # ─── Sister Bots Cache ───
        self._sister_bots_cache = None
        self._sister_bots_cache_time = 0
        self._sister_bots_ttl = 30

        # ─── Smart Notifications Cache ───
        self._smart_notif_cache = None
        self._smart_notif_cache_time = 0
        self._smart_notif_ttl = 300

        # ─── Bot Chains Cache ───
        self._chains_cache = None
        self._chains_cache_time = 0
        self._chains_ttl = 60

        # ─── Webhooks Cache ───
        self._webhooks_cache = None
        self._webhooks_cache_time = 0
        self._webhooks_ttl = 60

        # ─── Analytics Lock ───
        self._analytics_lock = threading.Lock()

        # Ensure CSV files exist
        self._init_files()

    def _detect_bot_id(self):
        """اكتشاف معرف البوت الحالي"""
        try:
            from multi_bot import MultiBotManager
            manager = MultiBotManager()
            for bot in manager.get_all_bots():
                if bot.get('token') == self.token:
                    return bot.get('id', '')
        except Exception:
            pass
        return ''

    def _init_files(self):
        """إنشاء ملفات CSV المطلوبة"""
        files = {
            'bot_analytics.csv': ['bot_id', 'user_id', 'event_type', 'text', 'action', 'timestamp'],
            'auto_replies.csv': ['id', 'bot_id', 'keyword', 'response', 'match_type', 'is_active', 'priority', 'created_at'],
            'bot_chains.csv': ['id', 'trigger_event', 'source_bot', 'target_bot', 'action', 'message_template', 'is_active', 'created_at'],
            'smart_notifications.csv': ['id', 'bot_id', 'trigger', 'delay_hours', 'message_template', 'is_active', 'created_at'],
            'webhook_configs.csv': ['id', 'name', 'url', 'secret', 'events', 'is_active', 'last_triggered', 'created_at'],
        }
        for filename, headers in files.items():
            if not os.path.exists(filename):
                try:
                    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                        csv.writer(f).writerow(headers)
                except Exception as e:
                    logger.error(f"Failed to create {filename}: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # 1. SMART BOT ROUTER — التوجيه الذكي
    # ═══════════════════════════════════════════════════════════════════

    def get_sister_bots(self) -> List[Dict]:
        """الحصول على البوتات الشقيقة (البوتات الأخرى النشطة)"""
        now = time.time()
        if self._sister_bots_cache and (now - self._sister_bots_cache_time) < self._sister_bots_ttl:
            return self._sister_bots_cache

        try:
            from multi_bot import MultiBotManager
            manager = MultiBotManager()
            all_bots = manager.get_all_bots()
            sisters = []
            for b in all_bots:
                if b.get('token') == self.token:
                    continue  # skip self
                if b.get('is_active') != 'yes':
                    continue  # skip inactive
                features_str = b.get('features', '')
                features_list = []
                if features_str:
                    try:
                        features_list = json.loads(features_str)
                    except Exception:
                        pass
                sisters.append({
                    'id': b.get('id', ''),
                    'name': b.get('name', ''),
                    'features': features_list,
                    'description': b.get('description', ''),
                })
            self._sister_bots_cache = sisters
            self._sister_bots_cache_time = now
            return sisters
        except Exception as e:
            logger.error(f"Error getting sister bots: {e}")
            return []

    def _get_feature_for_text(self, text: str) -> Optional[str]:
        """تحويل نص الزر إلى مفتاح الميزة"""
        if not text:
            return None
        text_lower = text.lower().strip()
        # keyword → feature mapping
        keywords = {
            'deposit': ['إيداع', 'ايدع', 'ودع', 'deposit', '💰'],
            'withdraw': ['سحب', 'اسحب', 'withdraw', '💸'],
            'matching': ['مطابقة', 'طابق', 'match', '🔄'],
            'trading': ['تداول', 'بيع', 'شراء', 'trade', '💱'],
            'compensation': ['تعويض', 'استرداد', 'svrp', '💎'],
            'games': ['ألعاب', 'العاب', 'يانصيب', 'عجلة', 'لعبة', 'game', '🎰', '🎡', '🎮'],
            'referral': ['احالة', 'إحالة', 'ادعو', 'اربح', 'referral', '🎁'],
            'complaints': ['شكوى', 'شكاوى', 'complaint', '📋'],
            'apps': ['تطبيق', 'تطبيقات', 'app', '📱'],
        }
        for feature, kws in keywords.items():
            for kw in kws:
                if kw in text_lower:
                    return feature
        return None

    def suggest_bots_for_text(self, text: str, lang: str = 'ar') -> Optional[str]:
        """
        اقتراح بوت مناسب بناءً على النص المرسل.
        يُستخدم عندما المستخدم يبعت أمر غير معروف.
        يُعيد رسالة اقتراح أو None لو مفيش اقتراح مناسب.
        """
        if self.bot.client_features is not None:
            return None  # بوت عادي (مش بوت رئيسي) — لا يقترح بوتات تانية

        feature = self._get_feature_for_text(text)
        if not feature:
            return None

        sisters = self.get_sister_bots()
        matching_bots = []
        for s in sisters:
            if not s['features']:  # بوت بكل الميزات
                matching_bots.append(s)
            elif feature in s['features']:
                matching_bots.append(s)

        if not matching_bots:
            return None

        lines = []
        if lang == 'ar':
            lines.append(f"🔍 يبدو إنك تبحث عن ميزة <b>{FEATURE_LABELS.get(feature, {}).get('ar', feature)}</b>")
            lines.append("")
            lines.append("📌 البوت الحالي لا يدعم هذه الميزة، لكن بوتات أخرى تدعمها:")
        else:
            lines.append(f"🔍 It looks like you're looking for <b>{FEATURE_LABELS.get(feature, {}).get('en', feature)}</b>")
            lines.append("")
            lines.append("📌 This bot doesn't support it, but these bots do:")

        for s in matching_bots[:5]:  # max 5 suggestions
            feat_labels = []
            for f in (s['features'] or []):
                label = FEATURE_LABELS.get(f, {}).get(lang, f)
                feat_labels.append(label)
            feat_text = ' + '.join(feat_labels) if feat_labels else ('كل الميزات' if lang == 'ar' else 'All features')
            lines.append(f"\n🤖 <b>{s['name']}</b>")
            lines.append(f"   └─ {feat_text}")

        if lang == 'ar':
            lines.append("\n💡 ابحث عن البوت المناسب في القائمة أو اضغط /start")
        else:
            lines.append("\n💡 Find the right bot in the list or press /start")

        return '\n'.join(lines)

    def build_start_sister_bots_section(self, lang: str = 'ar') -> str:
        """بناء قسم البوتات الشقيقة لرسالة /start"""
        sisters = self.get_sister_bots()
        if not sisters:
            return ''

        lines = []
        if lang == 'ar':
            lines.append("\n\n🤖 <b>بوتات أخرى متاحة:</b>")
        else:
            lines.append("\n\n🤖 <b>Other available bots:</b>")

        for s in sisters[:8]:  # max 8
            feat_labels = []
            for f in (s['features'] or []):
                label = FEATURE_LABELS.get(f, {}).get(lang, f)
                feat_labels.append(label)
            feat_text = ' · '.join(feat_labels) if feat_labels else ('كل الميزات' if lang == 'ar' else 'All features')
            desc = s.get('description', '')
            bot_name = s['name']
            lines.append(f"\n🔹 <b>{bot_name}</b>")
            lines.append(f"   {feat_text}")
            if desc:
                lines.append(f"   <i>{desc}</i>")

        return '\n'.join(lines)

    # ═══════════════════════════════════════════════════════════════════
    # 2. AUTO-REPLY — الردود الذكية
    # ═══════════════════════════════════════════════════════════════════

    def _load_auto_replies(self) -> List[Dict]:
        """تحميل ردود البوت الذكية مع caching"""
        now = time.time()
        if self._auto_replies_cache and (now - self._auto_replies_cache_time) < self._auto_replies_ttl:
            return self._auto_replies_cache

        replies = []
        try:
            if os.path.exists('auto_replies.csv'):
                with open('auto_replies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('is_active', 'yes') != 'yes':
                            continue
                        bot_id = row.get('bot_id', '')
                        # فلترة: بوت محدد أو بوت عام (bot_id فارغ)
                        if bot_id and bot_id != self.bot_id:
                            continue
                        replies.append(row)
                # ترتيب حسب الأولوية
                replies.sort(key=lambda x: int(x.get('priority', '0') or '0'), reverse=True)
        except Exception as e:
            logger.error(f"Error loading auto replies: {e}")

        self._auto_replies_cache = replies
        self._auto_replies_cache_time = now
        return replies

    def check_auto_reply(self, text: str, lang: str = 'ar') -> Optional[str]:
        """
        فحص لو النص يطابق أي auto-reply.
        يُعيد الرد المناسب أو None.
        """
        if not text or len(text.strip()) < 2:
            return None

        replies = self._load_auto_replies()
        text_lower = text.lower().strip()

        for reply in replies:
            keyword = (reply.get('keyword', '') or '').lower().strip()
            match_type = reply.get('match_type', 'contains')

            if not keyword:
                continue

            matched = False
            if match_type == 'exact':
                matched = text_lower == keyword
            elif match_type == 'starts_with':
                matched = text_lower.startswith(keyword)
            elif match_type == 'contains':
                matched = keyword in text_lower
            elif match_type == 'regex':
                try:
                    import re
                    matched = bool(re.search(keyword, text_lower))
                except Exception:
                    pass

            if matched:
                response = reply.get('response', '')
                if response:
                    return response

        return None

    def add_auto_reply(self, keyword: str, response: str, match_type: str = 'contains',
                       bot_id: str = '', priority: int = 0) -> str:
        """إضافة رد ذكي جديد"""
        reply_id = f"AR{str(int(time.time()))[-6:]}"
        try:
            with open('auto_replies.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([reply_id, bot_id, keyword, response, match_type, 'yes', str(priority),
                                 datetime.now().strftime('%Y-%m-%d %H:%M')])
            self._auto_replies_cache = None  # invalidate cache
            return reply_id
        except Exception as e:
            logger.error(f"Error adding auto reply: {e}")
            return ''

    def delete_auto_reply(self, reply_id: str) -> bool:
        """حذف رد ذكي"""
        try:
            rows = []
            if os.path.exists('auto_replies.csv'):
                with open('auto_replies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames
                    for row in reader:
                        if row.get('id') != reply_id:
                            rows.append(row)
                with open('auto_replies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
            self._auto_replies_cache = None
            return True
        except Exception as e:
            logger.error(f"Error deleting auto reply: {e}")
            return False

    def list_auto_replies(self, bot_id: str = '') -> List[Dict]:
        """قائمة ردود البوت الذكية"""
        replies = []
        try:
            if os.path.exists('auto_replies.csv'):
                with open('auto_replies.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if bot_id and row.get('bot_id', '') and row.get('bot_id') != bot_id:
                            continue
                        replies.append(row)
        except Exception:
            pass
        return replies

    # ═══════════════════════════════════════════════════════════════════
    # 3. BOT ANALYTICS — تحليلات البوتات
    # ═══════════════════════════════════════════════════════════════════

    def log_event(self, user_id, event_type: str, text: str = '', action: str = ''):
        """تسجيل حدث في التحليلات"""
        if not self.bot_id:
            return
        try:
            with self._analytics_lock:
                with open('bot_analytics.csv', 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        self.bot_id,
                        str(user_id),
                        event_type,
                        (text or '')[:200],
                        action,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ])
        except Exception as e:
            logger.error(f"Error logging analytics: {e}")

    def get_analytics(self, bot_id: str = '', days: int = 7) -> Dict:
        """الحصول على تحليلات البوت"""
        bid = bot_id or self.bot_id
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        stats = {
            'total_events': 0,
            'unique_users': set(),
            'message_count': 0,
            'callback_count': 0,
            'command_count': 0,
            'unknown_count': 0,
            'top_actions': {},
            'hourly_distribution': [0] * 24,
            'daily_users': {},
            'auto_reply_hits': 0,
            'sister_bot_suggestions': 0,
        }

        try:
            if os.path.exists('bot_analytics.csv'):
                with open('bot_analytics.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('bot_id') != bid:
                            continue
                        ts = row.get('timestamp', '')
                        if ts < cutoff:
                            continue

                        stats['total_events'] += 1
                        uid = row.get('user_id', '')
                        if uid:
                            stats['unique_users'].add(uid)

                        event_type = row.get('event_type', '')
                        if event_type == 'message':
                            stats['message_count'] += 1
                        elif event_type == 'callback':
                            stats['callback_count'] += 1
                        elif event_type == 'command':
                            stats['command_count'] += 1
                        elif event_type == 'unknown':
                            stats['unknown_count'] += 1
                        elif event_type == 'auto_reply':
                            stats['auto_reply_hits'] += 1
                        elif event_type == 'sister_suggestion':
                            stats['sister_bot_suggestions'] += 1

                        action = row.get('action', '')
                        if action:
                            stats['top_actions'][action] = stats['top_actions'].get(action, 0) + 1

                        # hourly
                        try:
                            hour = int(ts.split(' ')[1].split(':')[0])
                            stats['hourly_distribution'][hour] += 1
                        except Exception:
                            pass

                        # daily
                        day = ts.split(' ')[0] if ' ' in ts else ts
                        stats['daily_users'][day] = stats['daily_users'].get(day, 0) + 1
        except Exception as e:
            logger.error(f"Error reading analytics: {e}")

        # Convert set to count
        stats['unique_users'] = len(stats['unique_users'])
        # Sort top actions
        stats['top_actions'] = dict(sorted(stats['top_actions'].items(), key=lambda x: -x[1])[:10])

        return stats

    def cleanup_analytics(self, days: int = 90):
        """تنظيف البيانات القديمة"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        try:
            if os.path.exists('bot_analytics.csv'):
                rows = []
                with open('bot_analytics.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames
                    for row in reader:
                        if row.get('timestamp', '') >= cutoff:
                            rows.append(row)
                with open('bot_analytics.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
        except Exception as e:
            logger.error(f"Error cleaning analytics: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # 4. BOT CHAINS — سلاسل البوتات
    # ═══════════════════════════════════════════════════════════════════

    def _load_chains(self) -> List[Dict]:
        """تحميل سلاسل البوتات"""
        now = time.time()
        if self._chains_cache and (now - self._chains_cache_time) < self._chains_ttl:
            return self._chains_cache

        chains = []
        try:
            if os.path.exists('bot_chains.csv'):
                with open('bot_chains.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('is_active', 'yes') != 'yes':
                            continue
                        chains.append(row)
        except Exception:
            pass

        self._chains_cache = chains
        self._chains_cache_time = now
        return chains

    def fire_event(self, event_type: str, user_id, extra_data: Dict = None):
        """
        إطلاق حدث — يتحقق من السلاسل ويُنفذ الإجراءات المناسبة.
        event_type: 'new_user', 'deposit', 'withdrawal', 'game_play', 'first_message'
        """
        chains = self._load_chains()
        for chain in chains:
            trigger = chain.get('trigger_event', '')
            source_bot = chain.get('source_bot', '')

            if trigger != event_type:
                continue
            if source_bot and source_bot != self.bot_id:
                continue

            # تنفيذ الإجراء
            action = chain.get('action', '')
            message_template = chain.get('message_template', '')
            target_bot_id = chain.get('target_bot', '')

            if action == 'send_message' and target_bot_id:
                self._chain_send_message(target_bot_id, user_id, message_template, extra_data)
            elif action == 'notify_admin':
                self._chain_notify_admin(message_template, extra_data)

    def _chain_send_message(self, target_bot_id: str, user_id, message: str, extra_data: Dict = None):
        """إرسال رسالة عبر بوت آخر (سلسلة)"""
        try:
            from multi_bot import MultiBotManager
            manager = MultiBotManager()
            if target_bot_id in manager.active_bots:
                target_bot = manager.active_bots[target_bot_id]['bot']
                # تنسيق الرسالة
                if extra_data:
                    try:
                        message = message.format(**extra_data)
                    except Exception:
                        pass
                target_bot.send_message(user_id, message)
        except Exception as e:
            logger.error(f"Chain send message error: {e}")

    def _chain_notify_admin(self, message: str, extra_data: Dict = None):
        """إشعار الأدمن عبر السلسلة"""
        try:
            if extra_data:
                try:
                    message = message.format(**extra_data)
                except Exception:
                    pass
            self.bot.notify_admins(message)
        except Exception as e:
            logger.error(f"Chain notify admin error: {e}")

    def add_chain(self, trigger_event: str, source_bot: str, target_bot: str,
                  action: str, message_template: str) -> str:
        """إضافة سلسلة بوتات جديدة"""
        chain_id = f"CH{str(int(time.time()))[-6:]}"
        try:
            with open('bot_chains.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([chain_id, trigger_event, source_bot, target_bot, action,
                                 message_template, 'yes', datetime.now().strftime('%Y-%m-%d %H:%M')])
            self._chains_cache = None
            return chain_id
        except Exception as e:
            logger.error(f"Error adding chain: {e}")
            return ''

    def list_chains(self) -> List[Dict]:
        """قائمة السلاسل"""
        chains = []
        try:
            if os.path.exists('bot_chains.csv'):
                with open('bot_chains.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    chains = list(reader)
        except Exception:
            pass
        return chains

    # ═══════════════════════════════════════════════════════════════════
    # 5. SMART NOTIFICATIONS — إشعارات ذكية
    # ═══════════════════════════════════════════════════════════════════

    def _load_smart_notifications(self) -> List[Dict]:
        """تحميل قواعد الإشعارات الذكية"""
        now = time.time()
        if self._smart_notif_cache and (now - self._smart_notif_cache_time) < self._smart_notif_ttl:
            return self._smart_notif_cache

        notifs = []
        try:
            if os.path.exists('smart_notifications.csv'):
                with open('smart_notifications.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('is_active', 'yes') != 'yes':
                            continue
                        bot_id = row.get('bot_id', '')
                        if bot_id and bot_id != self.bot_id:
                            continue
                        notifs.append(row)
        except Exception:
            pass

        self._smart_notif_cache = notifs
        self._smart_notif_cache_time = now
        return notifs

    def check_smart_notifications(self, user_id) -> List[str]:
        """
        فحص لو في إشعارات ذكية مفعّلة للمستخدم.
        يُعيد قائمة بالرسائل المطلوب إرسالها.
        """
        notifs = self._load_smart_notifications()
        messages = []
        user = self.bot.find_user(user_id)
        if not user:
            return messages

        for notif in notifs:
            trigger = notif.get('trigger', '')
            template = notif.get('message_template', '')
            delay_hours = int(notif.get('delay_hours', '0') or '0')

            should_send = False

            if trigger == 'inactive_3days':
                # فحص لو المستخدم ما بعتش رسالة من 3 أيام
                last_seen = self._get_user_last_seen(user_id)
                if last_seen and (datetime.now() - last_seen).days >= 3:
                    should_send = True

            elif trigger == 'inactive_7days':
                last_seen = self._get_user_last_seen(user_id)
                if last_seen and (datetime.now() - last_seen).days >= 7:
                    should_send = True

            elif trigger == 'new_user_24h':
                user_date = user.get('date', '')
                if user_date:
                    try:
                        created = datetime.strptime(user_date, '%Y-%m-%d %H:%M')
                        if (datetime.now() - created).total_seconds() >= 86400:
                            should_send = True
                    except Exception:
                        pass

            elif trigger == 'birthday':
                # فحص بسيط — لو تاريخ الميلاد موجود
                pass  # needs birthday field in users.csv

            if should_send:
                try:
                    name = user.get('name', '')
                    msg = template.format(name=name, user_id=user_id)
                    messages.append(msg)
                except Exception:
                    messages.append(template)

        return messages

    def _get_user_last_seen(self, user_id) -> Optional[datetime]:
        """الحصول على آخر ظهور للمستخدم"""
        try:
            if os.path.exists('bot_analytics.csv'):
                with open('bot_analytics.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    last_ts = None
                    for row in reader:
                        if row.get('user_id') == str(user_id) and row.get('bot_id') == self.bot_id:
                            ts = row.get('timestamp', '')
                            if ts:
                                try:
                                    dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                                    if last_ts is None or dt > last_ts:
                                        last_ts = dt
                                except Exception:
                                    pass
                    return last_ts
        except Exception:
            pass
        return None

    def add_smart_notification(self, trigger: str, message_template: str, bot_id: str = '') -> str:
        """إضافة إشعار ذكي"""
        notif_id = f"SN{str(int(time.time()))[-6:]}"
        try:
            with open('smart_notifications.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([notif_id, bot_id, trigger, '0', message_template, 'yes',
                                 datetime.now().strftime('%Y-%m-%d %H:%M')])
            self._smart_notif_cache = None
            return notif_id
        except Exception as e:
            logger.error(f"Error adding smart notification: {e}")
            return ''

    def list_smart_notifications(self) -> List[Dict]:
        """قائمة الإشعارات الذكية"""
        notifs = []
        try:
            if os.path.exists('smart_notifications.csv'):
                with open('smart_notifications.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    notifs = list(reader)
        except Exception:
            pass
        return notifs

    # ═══════════════════════════════════════════════════════════════════
    # 6. WEBHOOKS — نظام الويب هوكس
    # ═══════════════════════════════════════════════════════════════════

    def _load_webhooks(self) -> List[Dict]:
        """تحميل الويب هوكس"""
        now = time.time()
        if self._webhooks_cache and (now - self._webhooks_cache_time) < self._webhooks_ttl:
            return self._webhooks_cache

        hooks = []
        try:
            if os.path.exists('webhook_configs.csv'):
                with open('webhook_configs.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('is_active', 'yes') != 'yes':
                            continue
                        hooks.append(row)
        except Exception:
            pass

        self._webhooks_cache = hooks
        self._webhooks_cache_time = now
        return hooks

    def trigger_webhook(self, event_type: str, data: Dict):
        """إرسال webhook لكل الـ URLs المسجلة لهذا الحدث"""
        hooks = self._load_webhooks()
        for hook in hooks:
            events = [e.strip() for e in hook.get('events', '').split(',') if e.strip()]
            if event_type not in events and '*' not in events:
                continue

            url = hook.get('url', '')
            secret = hook.get('secret', '')
            if not url:
                continue

            payload = {
                'event': event_type,
                'bot_id': self.bot_id,
                'data': data,
                'timestamp': datetime.now().isoformat(),
            }

            # HMAC signature
            if secret:
                sig = hashlib.sha256((secret + json.dumps(payload)).encode()).hexdigest()
                payload['signature'] = sig

            # Send in background thread
            t = threading.Thread(target=self._send_webhook, args=(url, payload), daemon=True)
            t.start()

    def _send_webhook(self, url: str, payload: Dict):
        """إرسال webhook فعلي"""
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=10)
            # Update last_triggered
            self._update_webhook_last_triggered(url)
        except Exception as e:
            logger.error(f"Webhook send error to {url}: {e}")

    def _update_webhook_last_triggered(self, url: str):
        """تحديث آخر مرة شُغل فيها الـ webhook"""
        try:
            if os.path.exists('webhook_configs.csv'):
                rows = []
                with open('webhook_configs.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames
                    for row in reader:
                        if row.get('url') == url:
                            row['last_triggered'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                        rows.append(row)
                with open('webhook_configs.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
        except Exception:
            pass

    def add_webhook(self, name: str, url: str, events: str, secret: str = '') -> str:
        """إضافة webhook"""
        hook_id = f"WH{str(int(time.time()))[-6:]}"
        try:
            with open('webhook_configs.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([hook_id, name, url, secret, events, 'yes', '',
                                 datetime.now().strftime('%Y-%m-%d %H:%M')])
            self._webhooks_cache = None
            return hook_id
        except Exception as e:
            logger.error(f"Error adding webhook: {e}")
            return ''

    def list_webhooks(self) -> List[Dict]:
        """قائمة الويب هوكس"""
        hooks = []
        try:
            if os.path.exists('webhook_configs.csv'):
                with open('webhook_configs.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    hooks = list(reader)
        except Exception:
            pass
        return hooks

    def delete_webhook(self, hook_id: str) -> bool:
        """حذف webhook"""
        try:
            rows = []
            if os.path.exists('webhook_configs.csv'):
                with open('webhook_configs.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames
                    for row in reader:
                        if row.get('id') != hook_id:
                            rows.append(row)
                with open('webhook_configs.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
            self._webhooks_cache = None
            return True
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════════
    # 7. BOT TEMPLATES — قوالب البوتات
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def get_templates() -> Dict:
        """الحصول على جميع القوالب"""
        return BOT_TEMPLATES

    @staticmethod
    def get_template(template_key: str) -> Optional[Dict]:
        """الحصول على قالب محدد"""
        return BOT_TEMPLATES.get(template_key)
