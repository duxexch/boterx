"""
AI Admin Assistant v4 — Full Control Multi-Agent System
يتحكم في كامل لوحة الإدارة بأوامر ذكية.
"""

import json
import sqlite3
import os
import csv
import re
import time
import hashlib
import logging
import shutil
from datetime import datetime, timedelta
from collections import Counter

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'boterx.db')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════
#  AGENT DEFINITIONS
# ═══════════════════════════════════════════════════════════════

AGENTS = {
    'commander': {
        'id': 'commander', 'name': 'Commander', 'name_ar': 'القائد', 'emoji': '🎯', 'color': '#8b5cf6',
        'role': 'General Manager', 'role_ar': 'المدير العام والمنسق',
        'description_ar': 'المنسق الرئيسي. يتحكم في كل شيء ويوزع المهام.',
        'personality_ar': 'محترف، حاسم، استراتيجي. يفكر بالصورة الكبيرة.',
        'specialties': ['general', 'delegation', 'planning', 'coordination'],
        'actions': ['get_stats', 'get_stats_detailed', 'list_channels', 'list_users', 'user_detail',
                    'ban_user', 'unban_user', 'send_message_to_user', 'view_transactions',
                    'pending_requests', 'approve_txn', 'reject_txn', 'bulk_approve',
                    'view_matching', 'approve_match', 'reject_match', 'resolve_dispute',
                    'view_complaints', 'reply_ticket', 'update_ticket_status',
                    'update_setting', 'get_settings', 'create_backup', 'list_backups',
                    'broadcast', 'broadcast_queue', 'generate_post', 'create_post',
                    'create_multi_post', 'list_multi_posts', 'publish_post', 'preview_post',
                    'import_contacts', 'list_imports', 'contact_stats', 'send_to_contacts',
                    'anti_ban_status', 'anti_ban_log',
                    'list_relays', 'relay_status', 'preview_relay', 'relay_log', 'relay_stats',
                    'browser_list', 'browser_open', 'browser_screenshot', 'browser_status',
                    'daemon_status', 'sleep_all_browsers', 'wake_all_browsers',
                    'analyze_site', 'site_knowledge', 'all_knowledge', 'browser_patterns',
                    'browser_task', 'browser_scrape', 'browser_quick_login',
                    'list_campaigns', 'campaign_stats', 'list_companies', 'company_detail',
                    'list_admins', 'add_admin', 'list_agents', 'agent_stats',
                    'game_stats', 'toggle_game', 'platform_stats',
                    'learn_fact', 'get_learning_stats', 'delegate_task', 'consult_all'],
    },
    'writer': {
        'id': 'writer', 'name': 'Writer', 'name_ar': 'الكاتب', 'emoji': '✍️', 'color': '#06b6d4',
        'role': 'Content Creator', 'role_ar': 'منشئ المحتوى',
        'description_ar': 'متخصص في إنشاء البوستات والمحتوى والنصوص لجميع المنصات.',
        'personality_ar': 'مبدع، تعبيري، دقيق. يستخدم الإيموجي والتنسيق بفعالية.',
        'specialties': ['content', 'posts', 'copywriting', 'creative'],
        'actions': ['create_post', 'generate_post', 'broadcast', 'list_channels',
                    'translate_post', 'post_history', 'post_library',
                    'create_multi_post', 'list_multi_posts', 'publish_post', 'preview_post'],
    },
    'analyst': {
        'id': 'analyst', 'name': 'Analyst', 'name_ar': 'المحلل', 'emoji': '📊', 'color': '#f59e0b',
        'role': 'Data Analyst', 'role_ar': 'محلل البيانات',
        'description_ar': 'متخصص في الإحصائيات وتحليل البيانات وإعداد التقارير.',
        'personality_ar': 'تحليلي، دقيق، مبني على البيانات. يعرض الأرقام بوضوح.',
        'specialties': ['statistics', 'analysis', 'reports', 'data'],
        'actions': ['get_stats', 'get_stats_detailed', 'view_transactions', 'view_matching',
                    'game_stats', 'platform_stats', 'campaign_stats', 'agent_stats',
                    'company_detail', 'pending_requests'],
    },
    'support': {
        'id': 'support', 'name': 'Support', 'name_ar': 'الدعم', 'emoji': '🛡️', 'color': '#10b981',
        'role': 'User Support', 'role_ar': 'دعم المستخدمين',
        'description_ar': 'يتعامل مع إدارة المستخدمين والشكاوى والنزاعات.',
        'personality_ar': 'متعاطف، صبور، يركز على الحلول.',
        'specialties': ['users', 'complaints', 'disputes', 'support'],
        'actions': ['list_users', 'user_detail', 'ban_user', 'unban_user',
                    'send_message_to_user', 'view_complaints', 'reply_ticket',
                    'update_ticket_status', 'view_transactions', 'view_matching',
                    'resolve_dispute', 'approve_match', 'reject_match',
                    'import_contacts', 'list_imports', 'contact_stats', 'send_to_contacts',
                    'anti_ban_status', 'anti_ban_log'],
    },
    'tech': {
        'id': 'tech', 'name': 'Tech', 'name_ar': 'التقني', 'emoji': '⚙️', 'color': '#ef4444',
        'role': 'Technical Manager', 'role_ar': 'المدير التقني',
        'description_ar': 'يتعامل مع إعدادات النظام والتكوين التقني والبنية التحتية.',
        'personality_ar': 'دقيق، تقني، شامل. يركز على صحة النظام.',
        'specialties': ['settings', 'technical', 'configuration', 'system'],
        'actions': ['update_setting', 'get_settings', 'get_stats', 'get_stats_detailed',
                    'create_backup', 'list_backups', 'toggle_game', 'list_channels',
                    'platform_stats'],
    },
}

DEFAULT_AGENT = 'commander'


def get_agent(agent_id):
    return AGENTS.get(agent_id, AGENTS[DEFAULT_AGENT])


def get_all_agents():
    return list(AGENTS.values())


def find_agent_by_mention(text):
    for aid, agent in AGENTS.items():
        for pattern in [f'@{agent["name"].lower()}', f'@{agent["name_ar"]}', f'@{aid}']:
            if pattern.lower() in text.lower():
                clean = re.sub(re.escape(pattern), '', text, flags=re.IGNORECASE).strip()
                return aid, clean
    return None, text


def detect_intent_agent(message):
    msg_lower = message.lower()
    if any(w in msg_lower for w in ['بوست', 'post', 'محتوى', 'content', 'اكتب', 'write', 'نص', 'text', 'تغريدة', 'tweet', 'caption', 'ترجم', 'translate']):
        return 'writer'
    if any(w in msg_lower for w in ['إحصائي', 'stat', 'تقرير', 'report', 'تحليل', 'analysis', 'أرقام', 'numbers', 'كم', 'how many', 'إيرادات', 'revenue', 'iradat']):
        return 'analyst'
    if any(w in msg_lower for w in ['مستخدم', 'user', 'شكوى', 'complaint', 'دعم', 'support', 'حظر', 'ban', 'رسالة', 'message', 'dispute', 'نزاع']):
        return 'support'
    if any(w in msg_lower for w in ['إعداد', 'setting', 'تكوين', 'config', 'نظام', 'system', 'تحديث', 'update', 'backup', 'نسخ']):
        return 'tech'
    return DEFAULT_AGENT


# ═══════════════════════════════════════════════════════════════
#  DATABASE INIT
# ═══════════════════════════════════════════════════════════════

def _init_chat_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for sql in [
            '''CREATE TABLE IF NOT EXISTS ai_chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT NOT NULL, agent_id TEXT NOT NULL DEFAULT 'commander',
                role TEXT NOT NULL, content TEXT NOT NULL,
                action_taken TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS ai_action_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT NOT NULL, agent_id TEXT DEFAULT 'commander',
                action_name TEXT NOT NULL, params TEXT,
                success INTEGER NOT NULL, error_message TEXT,
                result_summary TEXT, user_message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS ai_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phrase_hash TEXT NOT NULL, phrase_sample TEXT NOT NULL,
                action_name TEXT NOT NULL, agent_id TEXT DEFAULT 'commander',
                params_template TEXT, confidence REAL DEFAULT 0.5,
                times_used INTEGER DEFAULT 1, times_succeeded INTEGER DEFAULT 0,
                last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(phrase_hash, action_name))''',
            '''CREATE TABLE IF NOT EXISTS ai_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL, fact_key TEXT NOT NULL,
                fact_value TEXT NOT NULL, source TEXT DEFAULT 'learned',
                confidence REAL DEFAULT 0.5, times_confirmed INTEGER DEFAULT 1,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(category, fact_key))''',
            '''CREATE TABLE IF NOT EXISTS ai_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT NOT NULL, agent_id TEXT DEFAULT 'commander',
                original_action TEXT, original_params TEXT,
                corrected_action TEXT, corrected_params TEXT,
                correction_text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS ai_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT NOT NULL, pref_key TEXT NOT NULL,
                pref_value TEXT NOT NULL, confidence REAL DEFAULT 0.5,
                last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(admin_id, pref_key))''',
            '''CREATE TABLE IF NOT EXISTS ai_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT NOT NULL, agent_id TEXT DEFAULT 'commander',
                message_id INTEGER, rating INTEGER NOT NULL,
                correction_text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS ai_task_delegations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id TEXT NOT NULL, from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL, task_description TEXT NOT NULL,
                task_result TEXT, status TEXT DEFAULT 'pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''',
        ]:
            c.execute(sql)
        for idx in [
            'CREATE INDEX IF NOT EXISTS idx_chat_admin ON ai_chat_history(admin_id, timestamp)',
            'CREATE INDEX IF NOT EXISTS idx_chat_agent ON ai_chat_history(agent_id)',
            'CREATE INDEX IF NOT EXISTS idx_outcomes_admin ON ai_action_outcomes(admin_id, timestamp)',
            'CREATE INDEX IF NOT EXISTS idx_outcomes_action ON ai_action_outcomes(action_name, success)',
            'CREATE INDEX IF NOT EXISTS idx_patterns_hash ON ai_patterns(phrase_hash)',
            'CREATE INDEX IF NOT EXISTS idx_knowledge_cat ON ai_knowledge(category)',
            'CREATE INDEX IF NOT EXISTS idx_feedback_admin ON ai_feedback(admin_id, timestamp)',
        ]:
            c.execute(idx)
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"Chat DB init error: {e}")


# ═══════════════════════════════════════════════════════════════
#  MEMORY & LEARNING (unchanged core)
# ═══════════════════════════════════════════════════════════════

def save_message(admin_id, agent_id, role, content, action_taken=None):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute('INSERT INTO ai_chat_history (admin_id, agent_id, role, content, action_taken) VALUES (?, ?, ?, ?, ?)',
                           (str(admin_id), agent_id, role, content, action_taken))
        msg_id = cur.lastrowid; conn.commit(); conn.close(); return msg_id
    except Exception as e:
        logger.error(f"Save message error: {e}"); return None


def get_conversation_history(admin_id, agent_id=None, limit=20):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        if agent_id:
            rows = conn.execute('SELECT role, content, action_taken, agent_id, timestamp FROM ai_chat_history WHERE admin_id = ? AND agent_id = ? ORDER BY timestamp DESC LIMIT ?', (str(admin_id), agent_id, limit)).fetchall()
        else:
            rows = conn.execute('SELECT role, content, action_taken, agent_id, timestamp FROM ai_chat_history WHERE admin_id = ? ORDER BY timestamp DESC LIMIT ?', (str(admin_id), limit)).fetchall()
        conn.close(); return [dict(r) for r in reversed(rows)]
    except Exception as e:
        logger.error(f"Get history error: {e}"); return []


def clear_history(admin_id, agent_id=None):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        if agent_id:
            conn.execute('DELETE FROM ai_chat_history WHERE admin_id = ? AND agent_id = ?', (str(admin_id), agent_id))
        else:
            conn.execute('DELETE FROM ai_chat_history WHERE admin_id = ?', (str(admin_id),))
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"Clear history error: {e}")


def _phrase_hash(text):
    normalized = re.sub(r'[^\w\s]', '', text.lower().strip())
    normalized = re.sub(r'\s+', ' ', normalized)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:12]


def record_action_outcome(admin_id, agent_id, action_name, params, success, error_msg=None, result_summary=None, user_message=None):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO ai_action_outcomes (admin_id, agent_id, action_name, params, success, error_message, result_summary, user_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                     (str(admin_id), agent_id, action_name, json.dumps(params, ensure_ascii=False), 1 if success else 0, error_msg, result_summary, user_message))
        conn.commit(); conn.close()
        if success and user_message:
            learn_pattern(user_message, action_name, params, agent_id)
    except Exception as e:
        logger.error(f"Record outcome error: {e}")


def learn_pattern(phrase, action_name, params, agent_id='commander'):
    _init_chat_db()
    ph = _phrase_hash(phrase)
    try:
        conn = sqlite3.connect(DB_PATH)
        existing = conn.execute('SELECT id, times_used, times_succeeded, confidence FROM ai_patterns WHERE phrase_hash = ? AND action_name = ?', (ph, action_name)).fetchone()
        if existing:
            conn.execute('UPDATE ai_patterns SET times_used=?, times_succeeded=?, confidence=?, last_used=CURRENT_TIMESTAMP, params_template=? WHERE id=?',
                         (existing[1]+1, existing[2]+1, min(0.95, existing[3]+0.05), json.dumps(params, ensure_ascii=False), existing[0]))
        else:
            conn.execute('INSERT INTO ai_patterns (phrase_hash, phrase_sample, action_name, agent_id, params_template, confidence) VALUES (?, ?, ?, ?, ?, ?)',
                         (ph, phrase[:200], action_name, agent_id, json.dumps(params, ensure_ascii=False), 0.5))
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"Learn pattern error: {e}")


def record_correction(admin_id, agent_id, original_action, original_params, corrected_action, corrected_params, correction_text):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO ai_corrections (admin_id, agent_id, original_action, original_params, corrected_action, corrected_params, correction_text) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (str(admin_id), agent_id, original_action, json.dumps(original_params, ensure_ascii=False) if original_params else None, corrected_action, json.dumps(corrected_params, ensure_ascii=False) if corrected_params else None, correction_text))
        conn.commit(); conn.close()
        if correction_text:
            store_knowledge('corrections', f'{original_action}_to_{corrected_action}', correction_text, source='admin_correction', confidence=0.9)
    except Exception as e:
        logger.error(f"Record correction error: {e}")


def store_knowledge(category, fact_key, fact_value, source='learned', confidence=0.5):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        existing = conn.execute('SELECT id FROM ai_knowledge WHERE category=? AND fact_key=?', (category, fact_key)).fetchone()
        if existing:
            conn.execute('UPDATE ai_knowledge SET fact_value=?, confidence=?, times_confirmed=times_confirmed+1, last_updated=CURRENT_TIMESTAMP WHERE id=?',
                         (fact_value, min(0.95, confidence + 0.1), existing[0]))
        else:
            conn.execute('INSERT INTO ai_knowledge (category, fact_key, fact_value, source, confidence) VALUES (?, ?, ?, ?, ?)',
                         (category, fact_key, fact_value, source, confidence))
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"Store knowledge error: {e}")


def get_knowledge(category=None, limit=50):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        if category:
            rows = conn.execute('SELECT * FROM ai_knowledge WHERE category=? ORDER BY confidence DESC LIMIT ?', (category, limit)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM ai_knowledge ORDER BY confidence DESC LIMIT ?', (limit,)).fetchall()
        conn.close(); return [dict(r) for r in rows]
    except: return []


def get_learned_patterns(action_name=None, min_confidence=0.3, limit=30):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        if action_name:
            rows = conn.execute('SELECT * FROM ai_patterns WHERE action_name=? AND confidence>=? ORDER BY confidence DESC LIMIT ?', (action_name, min_confidence, limit)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM ai_patterns WHERE confidence>=? ORDER BY confidence DESC LIMIT ?', (min_confidence, limit)).fetchall()
        conn.close(); return [dict(r) for r in rows]
    except: return []


def get_repeated_errors(limit=10):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT action_name, error_message, COUNT(*) as cnt FROM ai_action_outcomes WHERE success=0 GROUP BY action_name, error_message ORDER BY cnt DESC LIMIT ?', (limit,)).fetchall()
        conn.close(); return [dict(r) for r in rows]
    except: return []


def get_admin_preferences(admin_id):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT pref_key, pref_value FROM ai_preferences WHERE admin_id=?', (str(admin_id),)).fetchall()
        conn.close(); return {r['pref_key']: r['pref_value'] for r in rows}
    except: return {}


def set_admin_preference(admin_id, key, value, confidence=0.7):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO ai_preferences (admin_id, pref_key, pref_value, confidence, last_used) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)', (str(admin_id), key, value, confidence))
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"Set preference error: {e}")


def record_feedback(admin_id, agent_id, message_id, rating, correction_text=None):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO ai_feedback (admin_id, agent_id, message_id, rating, correction_text) VALUES (?, ?, ?, ?, ?)',
                     (str(admin_id), agent_id, message_id, rating, correction_text))
        conn.commit(); conn.close()
        if rating == 1 and correction_text:
            store_knowledge('negative_feedback', correction_text[:200], correction_text, source='admin_feedback', confidence=0.8)
    except Exception as e:
        logger.error(f"Record feedback error: {e}")


def get_learning_stats():
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH); stats = {}
        for key, sql in [
            ('total_actions', 'SELECT COUNT(*) FROM ai_action_outcomes'),
            ('successful_actions', 'SELECT COUNT(*) FROM ai_action_outcomes WHERE success=1'),
            ('learned_patterns', 'SELECT COUNT(*) FROM ai_patterns'),
            ('knowledge_facts', 'SELECT COUNT(*) FROM ai_knowledge'),
            ('corrections', 'SELECT COUNT(*) FROM ai_corrections'),
            ('positive_feedback', 'SELECT COUNT(*) FROM ai_feedback WHERE rating=3'),
            ('negative_feedback', 'SELECT COUNT(*) FROM ai_feedback WHERE rating=1'),
        ]:
            stats[key] = conn.execute(sql).fetchone()[0]
        rows = conn.execute('SELECT action_name, COUNT(*) as cnt, SUM(success) as succ FROM ai_action_outcomes GROUP BY action_name ORDER BY cnt DESC LIMIT 5').fetchall()
        stats['top_actions'] = [{'action': r[0], 'count': r[1], 'success': r[2]} for r in rows]
        rows = conn.execute('SELECT agent_id, COUNT(*) as cnt, SUM(success) as succ FROM ai_action_outcomes GROUP BY agent_id ORDER BY cnt DESC').fetchall()
        stats['agent_stats'] = [{'agent': r[0], 'count': r[1], 'success': r[2]} for r in rows]
        conn.close(); return stats
    except: return {}


# ═══════════════════════════════════════════════════════════════
#  ACTIONS — FULL ADMIN CONTROL (50+ actions)
# ═══════════════════════════════════════════════════════════════

ACTIONS_SCHEMA = [
    # Stats & Dashboard
    {"name": "get_stats", "description": "إحصائيات عامة", "parameters": {"type": "users|transactions|revenue|matching|channels|all"}},
    {"name": "get_stats_detailed", "description": "إحصائيات مفصلة", "parameters": {"period": "today|week|month"}},
    {"name": "platform_stats", "description": "إحصائيات المنصة", "parameters": {}},
    # Users
    {"name": "list_users", "description": "عرض المستخدمين", "parameters": {"search": "بحث", "limit": "عدد"}},
    {"name": "user_detail", "description": "تفاصيل مستخدم", "parameters": {"user_id": "المستخدم"}},
    {"name": "ban_user", "description": "حظر مستخدم", "parameters": {"user_id": "المستخدم", "reason": "السبب"}},
    {"name": "unban_user", "description": "إلغاء حظر", "parameters": {"user_id": "المستخدم"}},
    {"name": "send_message_to_user", "description": "رسالة مباشرة", "parameters": {"user_id": "المستخدم", "message": "الرسالة"}},
    # Channels
    {"name": "list_channels", "description": "عرض القنوات", "parameters": {}},
    {"name": "add_channel", "description": "إضافة قناة", "parameters": {"chat_id": "المعرف", "name": "الاسم", "platform": "telegram|whatsapp"}},
    {"name": "toggle_channel", "description": "تفعيل/تعطيل قناة", "parameters": {"chat_id": "المعرف"}},
    {"name": "delete_channel", "description": "حذف قناة", "parameters": {"chat_id": "المعرف"}},
    # Transactions
    {"name": "view_transactions", "description": "عرض المعاملات", "parameters": {"status": "الحالة", "type": "النوع", "limit": "عدد"}},
    {"name": "pending_requests", "description": "الطلبات المعلقة", "parameters": {}},
    {"name": "approve_txn", "description": "approval معاملة", "parameters": {"txn_id": "المعرف"}},
    {"name": "reject_txn", "description": "رفض معاملة", "parameters": {"txn_id": "المعرف", "reason": "السبب"}},
    {"name": "bulk_approve", "description": "approval جماعي", "parameters": {"type": "deposits|withdrawals"}},
    # Matching
    {"name": "view_matching", "description": "عرض المطابقة", "parameters": {"status": "الحالة", "limit": "عدد"}},
    {"name": "approve_match", "description": "approval مطابقة", "parameters": {"match_id": "المعرف"}},
    {"name": "reject_match", "description": "رفض مطابقة", "parameters": {"match_id": "المعرف", "reason": "السبب"}},
    {"name": "resolve_dispute", "description": "حل نزاع", "parameters": {"match_id": "المعرف", "resolution": "الحل"}},
    # Complaints & Tickets
    {"name": "view_complaints", "description": "عرض الشكاوى", "parameters": {"status": "الحالة", "limit": "عدد"}},
    {"name": "reply_ticket", "description": "رد على شكوى", "parameters": {"ticket_id": "المعرف", "reply": "الرد"}},
    {"name": "update_ticket_status", "description": "تحديث حالة شكوى", "parameters": {"ticket_id": "المعرف", "status": "الحالة"}},
    # Broadcast & Posts
    {"name": "broadcast", "description": "بث رسالة", "parameters": {"message": "الرسالة", "target": "all|active|inactive"}},
    {"name": "broadcast_queue", "description": "قائمة الانتظار", "parameters": {}},
    {"name": "create_post", "description": "إنشاء بوست", "parameters": {"message": "النص", "platform": "telegram|whatsapp", "channel_ids": "المعرفات"}},
    {"name": "generate_post", "description": "توليد بوست بالذكاء الاصطناعي", "parameters": {"topic": "الموضوع", "content_type": "info|question|prediction"}},
    {"name": "translate_post", "description": "ترجمة نص", "parameters": {"text": "النص", "target_lang": "ar|en|tr"}},
    {"name": "post_history", "description": "سجل البوستات", "parameters": {"limit": "عدد"}},
    {"name": "post_library", "description": "مكتبة المحتوى", "parameters": {}},
    # Settings
    {"name": "update_setting", "description": "تعديل إعداد", "parameters": {"key": "الإعداد", "value": "القيمة"}},
    {"name": "get_settings", "description": "عرض الإعدادات", "parameters": {"filter": "فلتر"}},
    # Games
    {"name": "toggle_game", "description": "تفعيل/تعطيل لعبة", "parameters": {"game_id": "المعرف"}},
    {"name": "game_stats", "description": "إحصائيات الألعاب", "parameters": {}},
    # Agents (Matching)
    {"name": "list_agents", "description": "عرض الوكلاء", "parameters": {}},
    {"name": "agent_stats", "description": "إحصائيات الوكلاء", "parameters": {}},
    # Companies
    {"name": "list_companies", "description": "عرض الشركات", "parameters": {}},
    {"name": "company_detail", "description": "تفاصيل شركة", "parameters": {"company_id": "المعرف"}},
    # Admins
    {"name": "list_admins", "description": "عرض الأدمنز", "parameters": {}},
    {"name": "add_admin", "description": "إضافة أدمن", "parameters": {"user_id": "المستخدم", "role": "الدور"}},
    # Backup
    {"name": "create_backup", "description": "إنشاء نسخة احتياطية", "parameters": {}},
    {"name": "list_backups", "description": "عرض النسخ الاحتياطية", "parameters": {}},
    # Multi-platform Posts
    {"name": "create_multi_post", "description": "إنشاء منشور متعدد المنصات", "parameters": {"title": "العنوان", "content": "المحتوى", "platforms": "المنصات"}},
    {"name": "list_multi_posts", "description": "عرض المنشورات المحفوظة", "parameters": {}},
    {"name": "publish_post", "description": "نشر منشور على منصة", "parameters": {"post_id": "المعرف", "platform": "المنصة"}},
    {"name": "preview_post", "description": "معاينة منشور على منصة", "parameters": {"content": "المحتوى", "platform": "المنصة"}},
    # Contacts
    {"name": "import_contacts", "description": "استيراد جهات اتصال من ملف", "parameters": {"file": "الملف"}},
    {"name": "list_imports", "description": "عرض الاستيرادات", "parameters": {}},
    {"name": "contact_stats", "description": "إحصائيات جهات الاتصال", "parameters": {}},
    {"name": "send_to_contacts", "description": "إرسال رسالة لجهات اتصال", "parameters": {"platform": "المنصة", "template": "القالب", "import_id": "الاستيراد"}},
    {"name": "anti_ban_status", "description": "حالة الحماية من الحظر", "parameters": {"platform": "المنصة"}},
    {"name": "anti_ban_log", "description": "سجل الحماية من الحظر", "parameters": {}},
    # Content Relay
    {"name": "list_relays", "description": "عرض عمليات النقل", "parameters": {}},
    {"name": "relay_status", "description": "حالة عملية نقل", "parameters": {"relay_id": "المعرف"}},
    {"name": "preview_relay", "description": "معاينة محتوى بعد المعالجة", "parameters": {"text": "النص", "relay_id": "المعرف"}},
    {"name": "relay_log", "description": "سجل عمليات النقل", "parameters": {"relay_id": "المعرف"}},
    {"name": "relay_stats", "description": "إحصائيات النقل", "parameters": {}},
    # Browser
    {"name": "browser_list", "description": "عرض نوافذ المتصفح", "parameters": {}},
    {"name": "browser_open", "description": "فتح موقع في المتصفح", "parameters": {"url": "الرابط", "name": "الاسم"}},
    {"name": "browser_screenshot", "description": "لقطة شاشة من المتصفح", "parameters": {"instance_id": "معرف النافذة"}},
    {"name": "browser_status", "description": "حالة المتصفح", "parameters": {"instance_id": "معرف النافذة"}},
    {"name": "daemon_status", "description": "حالة Daemon المتصفح", "parameters": {}},
    {"name": "sleep_all_browsers", "description": "إدخال كل المتصفحات في النوم", "parameters": {}},
    {"name": "wake_all_browsers", "description": "إيقاظ كل المتصفحات", "parameters": {}},
    {"name": "analyze_site", "description": "تحليل الموقع وتعلم من صفحته", "parameters": {"instance_id": "معرف النافذة"}},
    {"name": "site_knowledge", "description": "عرض ما تعلمته عن موقع", "parameters": {"instance_id": "معرف النافذة"}},
    {"name": "all_knowledge", "description": "عرض كل المواقع المعرفة", "parameters": {}},
    {"name": "browser_patterns", "description": "عرض أنماط النجاح المحفوظة", "parameters": {"domain": "الموقع"}},
    {"name": "browser_task", "description": "تنفيذ مهمة في المتصفح (مثل: فتح موقع + تسجيل دخول)", "parameters": {"instance_id": "النافذة", "goal": "الهدف", "steps": "الخطوات"}},
    {"name": "browser_scrape", "description": "استخراج محتوى من صفحة", "parameters": {"instance_id": "النافذة", "url": "الرابط"}},
    {"name": "browser_quick_login", "description": "تسجيل دخول سريع في موقع", "parameters": {"instance_id": "النافذة", "url": "الرابط", "username": "المستخدم", "password": "كلمة المرور"}},
    # Learning
    {"name": "learn_fact", "description": "حفظ معلومة", "parameters": {"category": "الفئة", "key": "المفتاح", "value": "القيمة"}},
    {"name": "get_learning_stats", "description": "إحصائيات التعلم", "parameters": {}},
    {"name": "delegate_task", "description": "تكليف وكيل", "parameters": {"to_agent": "الوكيل", "task": "المهمة"}},
    {"name": "consult_all", "description": "استشارة كل الوكلاء", "parameters": {"question": "السؤال"}},
]


def _db_query(sql, params=(), fetch='one'):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        if fetch == 'one': return rows[0] if rows else None
        return [dict(r) for r in rows]
    except: return None if fetch == 'one' else []


def _db_execute(sql, params=()):
    try:
        conn = sqlite3.connect(DB_PATH); conn.execute(sql, params); conn.commit(); conn.close(); return True
    except: return False


# ── Stats ─────────────────────────────────────────────────────

def _exec_get_stats(params):
    stat_type = params.get('type', 'all'); result = {}
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        if stat_type in ('users', 'all'):
            try: result['total_users'] = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            except: result['total_users'] = 'N/A'
            try:
                week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                result['active_users_7d'] = conn.execute('SELECT COUNT(DISTINCT user_id) FROM transactions WHERE created_at > ?', (week_ago,)).fetchone()[0]
            except: pass
        if stat_type in ('transactions', 'revenue', 'all'):
            try:
                r = conn.execute("SELECT COUNT(*), SUM(CASE WHEN status='approved' THEN amount ELSE 0 END) FROM transactions WHERE type='deposit'").fetchone()
                result['total_deposits'] = r[0]; result['total_revenue'] = float(r[1] or 0)
            except: pass
            try: result['pending_transactions'] = conn.execute("SELECT COUNT(*) FROM transactions WHERE status='pending'").fetchone()[0]
            except: pass
        if stat_type in ('matching', 'all'):
            try: result['pending_matches'] = conn.execute("SELECT COUNT(*) FROM match_requests WHERE status='pending'").fetchone()[0]
            except: pass
        if stat_type in ('channels', 'all'):
            p = os.path.join(BASE_DIR, 'bot_channels.csv')
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8-sig') as f: ch = list(csv.DictReader(f))
                result['total_channels'] = len(ch)
                result['active_channels'] = len([c for c in ch if (c.get('is_active','') or '').lower() in ('yes','true','1','')])
        conn.close()
    except Exception as e: result['error'] = str(e)
    return {'success': True, 'stats': result}


def _exec_get_stats_detailed(params):
    period = params.get('period', 'week'); result = {}
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        if period == 'today':
            start = datetime.now().strftime('%Y-%m-%d')
        elif period == 'week':
            start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        else:
            start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        try:
            r = conn.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE created_at >= ? AND type='deposit'", (start,)).fetchone()
            result['deposits_count'] = r[0]; result['deposits_amount'] = float(r[1] or 0)
        except: pass
        try:
            r = conn.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE created_at >= ? AND type='withdrawal'", (start,)).fetchone()
            result['withdrawals_count'] = r[0]; result['withdrawals_amount'] = float(r[1] or 0)
        except: pass
        try:
            result['new_users'] = conn.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (start,)).fetchone()[0]
        except: pass
        try:
            result['new_matches'] = conn.execute("SELECT COUNT(*) FROM match_requests WHERE created_at >= ?", (start,)).fetchone()[0]
        except: pass
        try:
            result['complaints_count'] = conn.execute("SELECT COUNT(*) FROM tickets WHERE created_at >= ?", (start,)).fetchone()[0]
        except: pass
        result['period'] = period; result['from'] = start
        conn.close()
    except Exception as e: result['error'] = str(e)
    return {'success': True, 'stats': result}


def _exec_platform_stats(params):
    result = {}
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        for key, sql in [
            ('total_users', 'SELECT COUNT(*) FROM users'),
            ('total_transactions', 'SELECT COUNT(*) FROM transactions'),
            ('total_matches', 'SELECT COUNT(*) FROM match_requests'),
            ('total_tickets', 'SELECT COUNT(*) FROM tickets'),
            ('total_settings', 'SELECT COUNT(*) FROM settings'),
        ]:
            try: result[key] = conn.execute(sql).fetchone()[0]
            except: result[key] = 'N/A'
        try:
            r = conn.execute("SELECT SUM(amount) FROM transactions WHERE status='approved' AND type='deposit'").fetchone()
            result['total_revenue'] = float(r[0] or 0)
        except: pass
        try:
            result['banned_users'] = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned=1 OR is_banned='yes'").fetchone()[0]
        except: pass
        conn.close()
    except Exception as e: result['error'] = str(e)
    return {'success': True, 'stats': result}


# ── Users ─────────────────────────────────────────────────────

def _exec_list_users(params):
    search = params.get('search', ''); limit = int(params.get('limit', 10))
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        if search:
            rows = conn.execute("SELECT * FROM users WHERE name LIKE ? OR telegram_id LIKE ? OR phone LIKE ? LIMIT ?",
                                (f'%{search}%', f'%{search}%', f'%{search}%', limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM users ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        users = [dict(r) for r in rows]
        return {'success': True, 'total': len(users), 'users': [{'telegram_id': u.get('telegram_id',''), 'name': u.get('name',''), 'balance': u.get('balance',0), 'is_banned': u.get('is_banned',0)} for u in users]}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _exec_user_detail(params):
    user_id = str(params.get('user_id', ''))
    if not user_id: return {'success': False, 'error': 'user_id مطلوب'}
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,)).fetchone()
        if not user: conn.close(); return {'success': False, 'error': f'المستخدم {user_id} غير موجود'}
        user = dict(user)
        txns = conn.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (user_id,)).fetchall()
        user['recent_transactions'] = [dict(t) for t in txns]
        try:
            matches = conn.execute("SELECT * FROM match_requests WHERE user_id=? OR partner_id=? ORDER BY created_at DESC LIMIT 5", (user_id, user_id)).fetchall()
            user['recent_matches'] = [dict(m) for m in matches]
        except: pass
        conn.close()
        return {'success': True, 'user': user}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _exec_ban_user(params):
    user_id = str(params.get('user_id', '')); reason = params.get('reason', 'Banned via AI')
    if not user_id: return {'success': False, 'error': 'user_id مطلوب'}
    if _db_execute("UPDATE users SET is_banned=1, ban_reason=? WHERE telegram_id=?", (reason, user_id)):
        return {'success': True, 'user_id': user_id}
    return {'success': False, 'error': f'المستخدم {user_id} غير موجود'}


def _exec_unban_user(params):
    user_id = str(params.get('user_id', ''))
    if not user_id: return {'success': False, 'error': 'user_id مطلوب'}
    if _db_execute("UPDATE users SET is_banned=0, ban_reason=NULL WHERE telegram_id=?", (user_id,)):
        return {'success': True, 'user_id': user_id}
    return {'success': False, 'error': f'المستخدم {user_id} غير موجود'}


def _exec_send_to_user(params):
    user_id = str(params.get('user_id', '')); message = params.get('message', '')
    if not user_id or not message: return {'success': False, 'error': 'user_id و message مطلوبان'}
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv'); now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if not file_exists: w.writerow(['chat_id','message','parse_mode','silent','pin','platform','posting_method','created_at','status'])
        w.writerow([user_id, message, 'HTML', 'false', 'false', 'telegram', 'api', now, 'pending'])
    return {'success': True, 'user_id': user_id}


# ── Channels ──────────────────────────────────────────────────

def _exec_list_channels(params):
    p = os.path.join(BASE_DIR, 'bot_channels.csv')
    if not os.path.exists(p): return {'success': True, 'channels': [], 'total': 0}
    with open(p, 'r', encoding='utf-8-sig') as f: channels = list(csv.DictReader(f))
    return {'success': True, 'total': len(channels), 'channels': [{'name': ch.get('name',''), 'chat_id': ch.get('chat_id',''), 'platform': ch.get('platform','telegram'), 'is_active': ch.get('is_active','')} for ch in channels[:30]]}


def _exec_add_channel(params):
    chat_id = str(params.get('chat_id', '')); name = params.get('name', ''); platform = params.get('platform', 'telegram')
    if not chat_id: return {'success': False, 'error': 'chat_id مطلوب'}
    p = os.path.join(BASE_DIR, 'bot_channels.csv')
    file_exists = os.path.exists(p)
    with open(p, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if not file_exists: w.writerow(['chat_id','name','platform','is_active','created_at'])
        w.writerow([chat_id, name or f'Channel {chat_id}', platform, 'yes', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    return {'success': True, 'chat_id': chat_id, 'name': name}


def _exec_toggle_channel(params):
    chat_id = str(params.get('chat_id', ''))
    if not chat_id: return {'success': False, 'error': 'chat_id مطلوب'}
    p = os.path.join(BASE_DIR, 'bot_channels.csv')
    if not os.path.exists(p): return {'success': False, 'error': 'لا يوجد ملف القنوات'}
    rows = []; found = False; new_status = ''
    with open(p, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f); fn = reader.fieldnames
        for row in reader:
            if row.get('chat_id') == chat_id:
                cur = (row.get('is_active','') or '').lower()
                row['is_active'] = 'no' if cur in ('yes','true','1','') else 'yes'
                new_status = row['is_active']; found = True
            rows.append(row)
    if not found: return {'success': False, 'error': f'القناة {chat_id} غير موجودة'}
    with open(p, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fn); w.writeheader(); w.writerows(rows)
    return {'success': True, 'chat_id': chat_id, 'new_status': new_status}


def _exec_delete_channel(params):
    chat_id = str(params.get('chat_id', ''))
    if not chat_id: return {'success': False, 'error': 'chat_id مطلوب'}
    p = os.path.join(BASE_DIR, 'bot_channels.csv')
    if not os.path.exists(p): return {'success': False, 'error': 'لا يوجد ملف القنوات'}
    rows = []; found = False
    with open(p, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f); fn = reader.fieldnames
        for row in reader:
            if row.get('chat_id') == chat_id: found = True; continue
            rows.append(row)
    if not found: return {'success': False, 'error': f'القناة {chat_id} غير موجودة'}
    with open(p, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fn); w.writeheader(); w.writerows(rows)
    return {'success': True, 'chat_id': chat_id}


# ── Transactions ──────────────────────────────────────────────

def _exec_view_transactions(params):
    status = params.get('status', ''); txn_type = params.get('type', ''); limit = int(params.get('limit', 10))
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        q = 'SELECT * FROM transactions WHERE 1=1'; pl = []
        if status: q += ' AND status=?'; pl.append(status)
        if txn_type: q += ' AND type=?'; pl.append(txn_type)
        q += ' ORDER BY created_at DESC LIMIT ?'; pl.append(limit)
        rows = conn.execute(q, pl).fetchall(); conn.close()
        return {'success': True, 'total': len(rows), 'transactions': [dict(r) for r in rows]}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_pending_requests(params):
    result = {}
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        try:
            txns = conn.execute("SELECT * FROM transactions WHERE status='pending' ORDER BY created_at DESC LIMIT 20").fetchall()
            result['pending_transactions'] = [dict(t) for t in txns]
            result['pending_txn_count'] = len(txns)
        except: result['pending_txn_count'] = 0
        try:
            matches = conn.execute("SELECT * FROM match_requests WHERE status='pending' ORDER BY created_at DESC LIMIT 20").fetchall()
            result['pending_matches'] = [dict(m) for m in matches]
            result['pending_match_count'] = len(matches)
        except: result['pending_match_count'] = 0
        try:
            tickets = conn.execute("SELECT * FROM tickets WHERE status IN ('open','pending') ORDER BY created_at DESC LIMIT 20").fetchall()
            result['pending_tickets'] = [dict(t) for t in tickets]
            result['pending_ticket_count'] = len(tickets)
        except: result['pending_ticket_count'] = 0
        conn.close()
    except Exception as e: result['error'] = str(e)
    return {'success': True, 'stats': result}


def _exec_approve_txn(params):
    txn_id = str(params.get('txn_id', ''))
    if not txn_id: return {'success': False, 'error': 'txn_id مطلوب'}
    if _db_execute("UPDATE transactions SET status='approved', approved_at=? WHERE id=?", (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), txn_id)):
        return {'success': True, 'txn_id': txn_id}
    return {'success': False, 'error': f'المعاملة {txn_id} غير موجودة'}


def _exec_reject_txn(params):
    txn_id = str(params.get('txn_id', '')); reason = params.get('reason', 'Rejected via AI')
    if not txn_id: return {'success': False, 'error': 'txn_id مطلوب'}
    if _db_execute("UPDATE transactions SET status='rejected', reject_reason=? WHERE id=?", (reason, txn_id)):
        return {'success': True, 'txn_id': txn_id}
    return {'success': False, 'error': f'المعاملة {txn_id} غير موجودة'}


def _exec_bulk_approve(params):
    txn_type = params.get('type', 'deposits')
    type_filter = 'deposit' if txn_type == 'deposits' else 'withdrawal'
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE transactions SET status='approved', approved_at=? WHERE status='pending' AND type=?",
                     (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), type_filter))
        count = conn.execute("SELECT changes()").fetchone()[0]; conn.commit(); conn.close()
        return {'success': True, 'approved_count': count, 'type': txn_type}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Matching ──────────────────────────────────────────────────

def _exec_view_matching(params):
    status = params.get('status', ''); limit = int(params.get('limit', 10))
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        q = 'SELECT * FROM match_requests'; pl = []
        if status: q += ' WHERE status=?'; pl.append(status)
        q += ' ORDER BY created_at DESC LIMIT ?'; pl.append(limit)
        rows = conn.execute(q, pl).fetchall(); conn.close()
        return {'success': True, 'total': len(rows), 'requests': [dict(r) for r in rows]}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_approve_match(params):
    match_id = str(params.get('match_id', ''))
    if not match_id: return {'success': False, 'error': 'match_id مطلوب'}
    if _db_execute("UPDATE match_requests SET status='approved' WHERE id=?", (match_id,)):
        return {'success': True, 'match_id': match_id}
    return {'success': False, 'error': f'المطابقة {match_id} غير موجودة'}


def _exec_reject_match(params):
    match_id = str(params.get('match_id', '')); reason = params.get('reason', 'Rejected via AI')
    if not match_id: return {'success': False, 'error': 'match_id مطلوب'}
    if _db_execute("UPDATE match_requests SET status='rejected', reject_reason=? WHERE id=?", (reason, match_id)):
        return {'success': True, 'match_id': match_id}
    return {'success': False, 'error': f'المطابقة {match_id} غير موجودة'}


def _exec_resolve_dispute(params):
    match_id = str(params.get('match_id', '')); resolution = params.get('resolution', '')
    if not match_id: return {'success': False, 'error': 'match_id مطلوب'}
    if _db_execute("UPDATE match_requests SET status='resolved', resolution=? WHERE id=?", (resolution, match_id)):
        return {'success': True, 'match_id': match_id}
    return {'success': False, 'error': f'النزاع {match_id} غير موجود'}


# ── Complaints & Tickets ──────────────────────────────────────

def _exec_view_complaints(params):
    status = params.get('status', ''); limit = int(params.get('limit', 10))
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        q = 'SELECT * FROM tickets WHERE 1=1'; pl = []
        if status: q += ' AND status=?'; pl.append(status)
        q += ' ORDER BY created_at DESC LIMIT ?'; pl.append(limit)
        rows = conn.execute(q, pl).fetchall(); conn.close()
        return {'success': True, 'total': len(rows), 'tickets': [dict(r) for r in rows]}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_reply_ticket(params):
    ticket_id = str(params.get('ticket_id', '')); reply = params.get('reply', '')
    if not ticket_id or not reply: return {'success': False, 'error': 'ticket_id و reply مطلوبان'}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO ticket_replies (ticket_id, message, admin_id, created_at) VALUES (?, ?, 'ai_assistant', ?)",
                     (ticket_id, reply, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.execute("UPDATE tickets SET status='replied', updated_at=? WHERE id=?",
                     (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ticket_id))
        conn.commit(); conn.close()
        return {'success': True, 'ticket_id': ticket_id}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_update_ticket_status(params):
    ticket_id = str(params.get('ticket_id', '')); status = params.get('status', '')
    if not ticket_id or not status: return {'success': False, 'error': 'ticket_id و status مطلوبان'}
    if _db_execute("UPDATE tickets SET status=?, updated_at=? WHERE id=?",
                   (status, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ticket_id)):
        return {'success': True, 'ticket_id': ticket_id, 'new_status': status}
    return {'success': False, 'error': f'الشكوى {ticket_id} غير موجودة'}


# ── Broadcast & Posts ─────────────────────────────────────────

def _exec_broadcast(params):
    message = params.get('message', ''); target = params.get('target', 'all')
    if not message: return {'success': False, 'error': 'الرسالة مطلوبة'}
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv'); now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if not file_exists: w.writerow(['chat_id','message','parse_mode','silent','pin','platform','posting_method','created_at','status'])
        w.writerow([f'BROADCAST_{target.upper()}', message, 'HTML', 'false', 'false', 'telegram', 'api', now, 'pending'])
    return {'success': True, 'target': target}


def _exec_broadcast_queue(params):
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    if not os.path.exists(queue_path): return {'success': True, 'queue': [], 'total': 0}
    with open(queue_path, 'r', encoding='utf-8-sig') as f: rows = list(csv.DictReader(f))
    pending = [r for r in rows if r.get('status') == 'pending']
    return {'success': True, 'total': len(pending), 'queue': pending[:20]}


def _exec_create_post(params):
    message = params.get('message', ''); platform = params.get('platform', 'telegram')
    channel_ids = params.get('channel_ids', []); parse_mode = params.get('parse_mode', 'HTML')
    if not message: return {'success': False, 'error': 'الرسالة مطلوبة'}
    p = os.path.join(BASE_DIR, 'bot_channels.csv')
    if not os.path.exists(p): return {'success': False, 'error': 'لا توجد قنوات'}
    with open(p, 'r', encoding='utf-8-sig') as f: channels = list(csv.DictReader(f))
    targets = [ch for ch in channels if (ch.get('platform') or 'telegram').lower() == platform.lower()]
    if channel_ids: targets = [ch for ch in targets if ch.get('chat_id','') in channel_ids]
    if not targets: return {'success': False, 'error': f'لا توجد قنوات {platform}'}
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv'); now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)
    queued = 0
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if not file_exists: w.writerow(['chat_id','message','parse_mode','silent','pin','platform','posting_method','created_at','status'])
        for ch in targets:
            w.writerow([ch.get('chat_id',''), message, parse_mode, 'false', 'false', platform, 'api', now, 'pending'])
            queued += 1
    return {'success': True, 'queued': queued, 'platform': platform, 'channels': [ch.get('name','') for ch in targets[:5]]}


def _exec_generate_post(params):
    topic = params.get('topic', ''); ct = params.get('content_type', 'info')
    if not topic: return {'success': False, 'error': 'الموضوع مطلوب'}
    try:
        from ai_composer import get_active_keys, generate_post
        keys = get_active_keys(DB_PATH)
        if not keys: return {'success': False, 'error': 'لا توجد مفاتيح AI'}
        return generate_post(keys[0], ct, '', {'company_name': ''}, topic, BASE_DIR)
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_translate_post(params):
    text = params.get('text', ''); target_lang = params.get('target_lang', 'en')
    if not text: return {'success': False, 'error': 'النص مطلوب'}
    try:
        from ai_composer import get_active_keys
        keys = get_active_keys(DB_PATH)
        if not keys: return {'success': False, 'error': 'لا توجد مفاتيح AI'}
        # Simple translation via AI
        lang_name = {'ar': 'Arabic', 'en': 'English', 'tr': 'Turkish'}.get(target_lang, target_lang)
        messages = [{'role': 'system', 'content': f'Translate the following text to {lang_name}. Return ONLY the translation, no explanations.'},
                    {'role': 'user', 'content': text}]
        result = _call_ai(messages)
        if result.get('success'): return {'success': True, 'translation': result['content'], 'target_lang': target_lang}
        return result
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_post_history(params):
    limit = int(params.get('limit', 10))
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM posts ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return {'success': True, 'posts': [dict(r) for r in rows]}
    except Exception as e:
        return {'success': True, 'posts': [], 'note': 'سجل البوستات غير متاح'}


def _exec_post_library(params):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM post_library ORDER BY created_at DESC LIMIT 20").fetchall()
        conn.close()
        return {'success': True, 'library': [dict(r) for r in rows]}
    except Exception as e:
        return {'success': True, 'library': [], 'note': 'مكتبة المحتوى غير متاحة'}


# ── Settings ──────────────────────────────────────────────────

def _exec_update_setting(params):
    key = params.get('key', ''); value = params.get('value', '')
    if not key: return {'success': False, 'error': 'الإعداد مطلوب'}
    if _db_execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                   (key, value, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))):
        return {'success': True, 'key': key, 'value': value}
    return {'success': False, 'error': 'فشل التحديث'}


def _exec_get_settings(params):
    flt = params.get('filter', '')
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        if flt:
            rows = conn.execute("SELECT * FROM settings WHERE key LIKE ?", (f'%{flt}%',)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM settings ORDER BY key LIMIT 50").fetchall()
        conn.close()
        return {'success': True, 'settings': [dict(r) for r in rows]}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Games ─────────────────────────────────────────────────────

def _exec_toggle_game(params):
    game_id = str(params.get('game_id', ''))
    if not game_id: return {'success': False, 'error': 'game_id مطلوب'}
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if not game: conn.close(); return {'success': False, 'error': f'اللعبة {game_id} غير موجودة'}
        game = dict(game); new_status = 0 if game.get('is_enabled', 1) else 1
        conn.execute("UPDATE games SET is_enabled=? WHERE id=?", (new_status, game_id))
        conn.commit(); conn.close()
        return {'success': True, 'game_id': game_id, 'new_status': 'enabled' if new_status else 'disabled'}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_game_stats(params):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        games = conn.execute("SELECT * FROM games").fetchall()
        stats = []
        for g in games:
            g = dict(g)
            try:
                r = conn.execute("SELECT COUNT(*), SUM(bet_amount) FROM game_rounds WHERE game_id=?", (g['id'],)).fetchone()
                g['rounds'] = r[0]; g['total_bets'] = float(r[1] or 0)
            except: g['rounds'] = 0; g['total_bets'] = 0
            stats.append(g)
        conn.close()
        return {'success': True, 'games': stats}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Agents ────────────────────────────────────────────────────

def _exec_list_agents(params):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM agents ORDER BY rowid DESC LIMIT 20").fetchall()
        conn.close()
        return {'success': True, 'agents': [dict(r) for r in rows]}
    except Exception as e:
        return {'success': True, 'agents': [], 'note': 'الوكلاء غير متاحين'}


def _exec_agent_stats(params):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute("""SELECT a.id, a.name, a.balance, a.is_active,
            (SELECT COUNT(*) FROM match_requests WHERE agent_id=a.id) as total_matches,
            (SELECT COUNT(*) FROM match_requests WHERE agent_id=a.id AND status='completed') as completed
            FROM agents a ORDER BY total_matches DESC LIMIT 10""").fetchall()
        conn.close()
        return {'success': True, 'agents': [dict(r) for r in rows]}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Companies ─────────────────────────────────────────────────

def _exec_list_companies(params):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM companies ORDER BY rowid DESC LIMIT 20").fetchall()
        conn.close()
        return {'success': True, 'companies': [dict(r) for r in rows]}
    except Exception as e:
        return {'success': True, 'companies': [], 'note': 'الشركات غير متاحة'}


def _exec_company_detail(params):
    company_id = str(params.get('company_id', ''))
    if not company_id: return {'success': False, 'error': 'company_id مطلوب'}
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        company = conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
        if not company: conn.close(); return {'success': False, 'error': f'الشركة {company_id} غير موجودة'}
        company = dict(company)
        try:
            r = conn.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE company_id=? AND status='approved'", (company_id,)).fetchone()
            company['transaction_count'] = r[0]; company['total_volume'] = float(r[1] or 0)
        except: pass
        conn.close()
        return {'success': True, 'company': company}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Admins ────────────────────────────────────────────────────

def _exec_list_admins(params):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT user_id, name, role, is_active FROM admins ORDER BY rowid DESC LIMIT 20").fetchall()
        conn.close()
        return {'success': True, 'admins': [dict(r) for r in rows]}
    except Exception as e:
        return {'success': True, 'admins': [], 'note': 'الأدمنز غير متاحين'}


def _exec_add_admin(params):
    user_id = str(params.get('user_id', '')); role = params.get('role', 'admin')
    if not user_id: return {'success': False, 'error': 'user_id مطلوب'}
    if _db_execute("INSERT OR REPLACE INTO admins (user_id, role, is_active, created_at) VALUES (?, ?, 1, ?)",
                   (user_id, role, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))):
        return {'success': True, 'user_id': user_id, 'role': role}
    return {'success': False, 'error': 'فشل الإضافة'}


# ── Backup ────────────────────────────────────────────────────

def _exec_create_backup(params):
    try:
        backup_dir = os.path.join(BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        db_backup = os.path.join(backup_dir, f'boterx_{ts}.db')
        shutil.copy2(DB_PATH, db_backup)
        # Also backup CSV files
        for csv_name in ['bot_channels.csv', 'users.csv', 'transactions.csv']:
            src = os.path.join(BASE_DIR, csv_name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(backup_dir, f'{csv_name}.{ts}.bak'))
        return {'success': True, 'backup_file': db_backup, 'timestamp': ts}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_list_backups(params):
    backup_dir = os.path.join(BASE_DIR, 'backups')
    if not os.path.exists(backup_dir): return {'success': True, 'backups': []}
    try:
        files = sorted(os.listdir(backup_dir), reverse=True)[:20]
        backups = [{'name': f, 'size': f'{os.path.getsize(os.path.join(backup_dir, f))/1024:.1f} KB'} for f in files]
        return {'success': True, 'backups': backups}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Multi-platform Posts ──────────────────────────────────────

def _exec_create_multi_post(params):
    title = params.get('title', ''); content = params.get('content', ''); platforms = params.get('platforms')
    if not title or not content: return {'success': False, 'error': 'title و content مطلوبان'}
    try:
        from platform_posts import create_post
        result = create_post(title=title, base_content=content, platforms=platforms)
        return result
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_list_multi_posts(params):
    try:
        from platform_posts import list_posts
        posts = list_posts(status=params.get('status'), limit=params.get('limit', 20))
        return {'success': True, 'posts': posts, 'total': len(posts)}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_publish_post(params):
    post_id = params.get('post_id', ''); platform = params.get('platform', 'telegram')
    if not post_id: return {'success': False, 'error': 'post_id مطلوب'}
    try:
        from platform_posts import publish_variant
        return publish_variant(post_id, platform)
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_preview_post(params):
    content = params.get('content', ''); platform = params.get('platform', 'telegram')
    if not content: return {'success': False, 'error': 'content مطلوب'}
    try:
        from platform_posts import format_for_platform
        result = format_for_platform(content, platform, params.get('title', ''))
        return {'success': True, 'variant': result}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Contacts ──────────────────────────────────────────────────

def _exec_import_contacts(params):
    return {'success': False, 'error': 'يرجى رفع الملف من واجهة الدردشة مباشرة (زر 📎)'}


def _exec_list_imports(params):
    try:
        from contact_importer import list_imports
        imports = list_imports()
        return {'success': True, 'imports': imports, 'total': len(imports)}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_contact_stats(params):
    try:
        from contact_importer import get_contact_stats
        stats = get_contact_stats(params.get('import_id'))
        return {'success': True, 'stats': stats}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_send_to_contacts(params):
    platform = params.get('platform', 'telegram'); template = params.get('template', '')
    import_id = params.get('import_id')
    if not template: return {'success': False, 'error': 'template مطلوب'}
    try:
        from anti_ban import queue_messages
        from contact_importer import get_contacts_for_messaging
        contacts = get_contacts_for_messaging(platform, import_id, limit=params.get('limit', 100))
        if not contacts: return {'success': False, 'error': 'لا توجد جهات اتصال لهذه المنصة'}
        result = queue_messages(platform, template, contacts, import_id)
        return result
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_anti_ban_status(params):
    try:
        from anti_ban import get_rate_status, PLATFORM_LIMITS
        platform = params.get('platform', 'telegram')
        status = get_rate_status(platform)
        limits = PLATFORM_LIMITS.get(platform, {})
        return {'success': True, 'status': status, 'limits': limits}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_anti_ban_log(params):
    try:
        from anti_ban import get_ban_log
        log = get_ban_log(params.get('platform'), params.get('limit', 20))
        return {'success': True, 'log': log, 'total': len(log)}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Content Relay ─────────────────────────────────────────────

def _exec_list_relays(params):
    try:
        from content_relay import list_relays
        relays = list_relays(params.get('active_only', False))
        return {'success': True, 'relays': relays, 'total': len(relays)}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_relay_status(params):
    relay_id = params.get('relay_id')
    if not relay_id: return {'success': False, 'error': 'relay_id مطلوب'}
    try:
        from content_relay import get_relay, get_relay_stats
        relay = get_relay(int(relay_id))
        if not relay: return {'success': False, 'error': 'عملية النقل غير موجودة'}
        stats = get_relay_stats(int(relay_id))
        return {'success': True, 'relay': relay, 'stats': stats}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_preview_relay(params):
    text = params.get('text', ''); relay_id = params.get('relay_id')
    if not text: return {'success': False, 'error': 'النص مطلوب'}
    if not relay_id: return {'success': False, 'error': 'relay_id مطلوب'}
    try:
        from content_relay import preview_relay
        return preview_relay(text, int(relay_id))
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_relay_log(params):
    try:
        from content_relay import get_relay_log
        log = get_relay_log(params.get('relay_id'), params.get('limit', 20))
        return {'success': True, 'log': log, 'total': len(log)}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_relay_stats(params):
    try:
        from content_relay import get_relay_stats
        stats = get_relay_stats(params.get('relay_id'))
        return {'success': True, 'stats': stats}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Browser ──────────────────────────────────────────────────

def _exec_browser_list(params):
    try:
        from browser_manager import list_instances
        instances = list_instances()
        return {'success': True, 'instances': instances, 'total': len(instances)}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_browser_open(params):
    url = params.get('url', '')
    if not url: return {'success': False, 'error': 'الرابط مطلوب'}
    try:
        from browser_manager import create_instance, get_instance
        inst = create_instance(name=params.get('name', ''))
        inst.start()
        result = inst.navigate(url)
        return {'success': True, 'instance_id': inst.id, 'navigate': result, 'message': f'تم فتح {url}'}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_browser_screenshot(params):
    iid = params.get('instance_id', '')
    if not iid: return {'success': False, 'error': 'instance_id مطلوب'}
    try:
        from browser_manager import get_instance
        inst = get_instance(iid)
        if not inst: return {'success': False, 'error': 'النافذة غير موجودة'}
        path = inst.screenshot()
        return {'success': True, 'path': path, 'url': inst.page.url if inst.page else ''}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_browser_status(params):
    iid = params.get('instance_id', '')
    try:
        from browser_manager import list_instances
        instances = list_instances()
        if iid:
            inst = next((i for i in instances if i['id'] == iid), None)
            if not inst: return {'success': False, 'error': 'النافذة غير موجودة'}
            return {'success': True, 'instance': inst}
        return {'success': True, 'instances': instances, 'total': len(instances)}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_daemon_status(params):
    try:
        from browser_daemon import browser_daemon
        return {'success': True, 'daemon': browser_daemon.get_daemon_status()}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_sleep_all_browsers(params):
    try:
        from browser_daemon import browser_daemon
        browser_daemon.sleep_all()
        return {'success': True, 'message': 'تم إدخال كل المتصفحات في النوم'}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_wake_all_browsers(params):
    try:
        from browser_daemon import browser_daemon
        results = browser_daemon.wake_all(trigger='ai_command')
        return {'success': True, 'results': results, 'message': 'تم إيقاظ كل المتصفحات'}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Browser Learning ─────────────────────────────────────────

def _exec_analyze_site(params):
    iid = params.get('instance_id', '')
    if not iid: return {'success': False, 'error': 'instance_id مطلوب'}
    try:
        from browser_manager import get_instance
        inst = get_instance(iid)
        if not inst: return {'success': False, 'error': 'النافذة غير موجودة'}
        findings = inst.analyze_current_page()
        return {'success': True, 'findings': findings, 'message': 'تم تحليل الصفحة بنجاح'}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_site_knowledge(params):
    iid = params.get('instance_id', '')
    if not iid: return {'success': False, 'error': 'instance_id مطلوب'}
    try:
        from browser_manager import get_instance
        inst = get_instance(iid)
        if not inst: return {'success': False, 'error': 'النافذة غير موجودة'}
        return {'success': True, 'knowledge': inst.get_site_knowledge()}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_all_knowledge(params):
    try:
        from browser_knowledge import list_sites
        return {'success': True, 'sites': list_sites()}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_browser_patterns(params):
    try:
        from browser_knowledge import list_patterns
        return {'success': True, 'patterns': list_patterns(params.get('domain'))}
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Browser Tasks ────────────────────────────────────────────

def _exec_browser_task(params):
    iid = params.get('instance_id', '')
    goal = params.get('goal', '')
    steps = params.get('steps', [])
    if not iid: return {'success': False, 'error': 'instance_id مطلوب'}
    if not goal: return {'success': False, 'error': 'goal مطلوب'}
    try:
        from browser_tasks import task_executor
        task = task_executor.create_task(goal, steps)
        result = task_executor.execute_task(task.id, iid)
        return result
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_browser_scrape(params):
    iid = params.get('instance_id', '')
    url = params.get('url', '')
    if not iid: return {'success': False, 'error': 'instance_id مطلوب'}
    if not url: return {'success': False, 'error': 'url مطلوب'}
    try:
        from browser_tasks import create_from_template, task_executor
        task = create_from_template('scrape_page', {'url': url, 'selector': params.get('selector', 'body')})
        result = task_executor.execute_task(task.id, iid)
        text = ''
        for r in result.get('task', {}).get('results', []):
            if r.get('action') == 'read_text' and r.get('detail', {}).get('success'):
                text = r['detail'].get('result', '')
        result['scraped_text'] = text[:2000]
        return result
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_browser_quick_login(params):
    iid = params.get('instance_id', '')
    if not iid: return {'success': False, 'error': 'instance_id مطلوب'}
    try:
        from browser_tasks import create_from_template, task_executor
        task = create_from_template('login', {
            'url': params.get('url', ''),
            'username': params.get('username', ''),
            'password': params.get('password', ''),
        })
        result = task_executor.execute_task(task.id, iid)
        return result
    except Exception as e: return {'success': False, 'error': str(e)}


# ── Learning ──────────────────────────────────────────────────

def _exec_learn_fact(params):
    cat = params.get('category', 'general'); k = params.get('key', ''); v = params.get('value', '')
    if not k or not v: return {'success': False, 'error': 'key و value مطلوبان'}
    store_knowledge(cat, k, v, source='ai_self_learned', confidence=0.6)
    return {'success': True}


def _exec_get_learning_stats(params):
    return {'success': True, 'stats': get_learning_stats()}


def _exec_delegate_task(params):
    to_agent = params.get('to_agent', ''); task = params.get('task', '')
    if not to_agent or not task: return {'success': False, 'error': 'to_agent و task مطلوبان'}
    agent = get_agent(to_agent)
    return {'success': True, 'to_agent': to_agent, 'agent_name': agent['name_ar'],
            'task': task, 'message': f'✓ تمت تكليف {agent["emoji"]} {agent["name_ar"]} بالمهمة'}


def _exec_consult_all(params):
    question = params.get('question', '')
    if not question: return {'success': False, 'error': 'السؤال مطلوب'}
    return {'success': True, 'question': question, 'message': '✓ جاري استشارة كل الوكلاء...'}


# ═══════════════════════════════════════════════════════════════
#  ACTION DISPATCHER
# ═══════════════════════════════════════════════════════════════

ACTION_DISPATCH = {
    'get_stats': _exec_get_stats, 'get_stats_detailed': _exec_get_stats_detailed,
    'platform_stats': _exec_platform_stats,
    'list_users': _exec_list_users, 'user_detail': _exec_user_detail,
    'ban_user': _exec_ban_user, 'unban_user': _exec_unban_user,
    'send_message_to_user': _exec_send_to_user,
    'list_channels': _exec_list_channels, 'add_channel': _exec_add_channel,
    'toggle_channel': _exec_toggle_channel, 'delete_channel': _exec_delete_channel,
    'view_transactions': _exec_view_transactions, 'pending_requests': _exec_pending_requests,
    'approve_txn': _exec_approve_txn, 'reject_txn': _exec_reject_txn,
    'bulk_approve': _exec_bulk_approve,
    'view_matching': _exec_view_matching, 'approve_match': _exec_approve_match,
    'reject_match': _exec_reject_match, 'resolve_dispute': _exec_resolve_dispute,
    'view_complaints': _exec_view_complaints, 'reply_ticket': _exec_reply_ticket,
    'update_ticket_status': _exec_update_ticket_status,
    'broadcast': _exec_broadcast, 'broadcast_queue': _exec_broadcast_queue,
    'create_post': _exec_create_post, 'generate_post': _exec_generate_post,
    'translate_post': _exec_translate_post, 'post_history': _exec_post_history,
    'post_library': _exec_post_library,
    'update_setting': _exec_update_setting, 'get_settings': _exec_get_settings,
    'toggle_game': _exec_toggle_game, 'game_stats': _exec_game_stats,
    'list_agents': _exec_list_agents, 'agent_stats': _exec_agent_stats,
    'list_companies': _exec_list_companies, 'company_detail': _exec_company_detail,
    'list_admins': _exec_list_admins, 'add_admin': _exec_add_admin,
    'create_backup': _exec_create_backup, 'list_backups': _exec_list_backups,
    'create_multi_post': _exec_create_multi_post, 'list_multi_posts': _exec_list_multi_posts,
    'publish_post': _exec_publish_post, 'preview_post': _exec_preview_post,
    'import_contacts': _exec_import_contacts, 'list_imports': _exec_list_imports,
    'contact_stats': _exec_contact_stats, 'send_to_contacts': _exec_send_to_contacts,
    'anti_ban_status': _exec_anti_ban_status, 'anti_ban_log': _exec_anti_ban_log,
    'list_relays': _exec_list_relays, 'relay_status': _exec_relay_status,
    'preview_relay': _exec_preview_relay, 'relay_log': _exec_relay_log,
    'relay_stats': _exec_relay_stats,
    'browser_list': _exec_browser_list, 'browser_open': _exec_browser_open,
    'browser_screenshot': _exec_browser_screenshot, 'browser_status': _exec_browser_status,
    'daemon_status': _exec_daemon_status, 'sleep_all_browsers': _exec_sleep_all_browsers,
    'wake_all_browsers': _exec_wake_all_browsers,
    'analyze_site': _exec_analyze_site, 'site_knowledge': _exec_site_knowledge,
    'all_knowledge': _exec_all_knowledge, 'browser_patterns': _exec_browser_patterns,
    'browser_task': _exec_browser_task, 'browser_scrape': _exec_browser_scrape,
    'browser_quick_login': _exec_browser_quick_login,
    'learn_fact': _exec_learn_fact, 'get_learning_stats': _exec_get_learning_stats,
    'delegate_task': _exec_delegate_task, 'consult_all': _exec_consult_all,
}


def execute_action(action_name, params):
    try:
        handler = ACTION_DISPATCH.get(action_name)
        if handler: return handler(params)
        return {'success': False, 'error': f'إجراء غير معروف: {action_name}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

def _build_agent_system_prompt(agent_id, admin_id=None):
    agent = get_agent(agent_id)
    agent_actions = [a for a in ACTIONS_SCHEMA if a['name'] in agent['actions']]
    actions_desc = json.dumps(agent_actions, ensure_ascii=False, indent=2)

    learned_parts = []
    patterns = get_learned_patterns(min_confidence=0.4, limit=10)
    if patterns:
        lines = [f"  • \"{p['phrase_sample'][:60]}\" → {p['action_name']} [ثقة: {int(p['confidence']*100)}%]" for p in patterns]
        learned_parts.append("## أنماط مُتعلمة:\n" + '\n'.join(lines))
    knowledge = get_knowledge(limit=10)
    if knowledge:
        lines = [f"  • [{k['category']}] {k['fact_key']}: {k['fact_value'][:80]}" for k in knowledge]
        learned_parts.append("## معلومات:\n" + '\n'.join(lines))
    errors = get_repeated_errors(limit=3)
    if errors:
        lines = [f"  ⚠️ {e['action_name']}: {e['error_message'][:60]} ({e['cnt']} مرة)" for e in errors]
        learned_parts.append("## تجنب:\n" + '\n'.join(lines))
    if admin_id:
        prefs = get_admin_preferences(admin_id)
        if prefs:
            learned_parts.append("## تفضيلات الأدمن:\n" + '\n'.join([f"  • {k}: {v}" for k, v in prefs.items()]))
    learning_section = '\n\n'.join(learned_parts) if learned_parts else ''

    other_agents = [f"  • @{oa['name']} ({oa['name_ar']}) — {oa['role_ar']}" for oid, oa in AGENTS.items() if oid != agent_id]
    agents_list = '\n'.join(other_agents)

    rules = """1. **التنفيذ**: أرجع JSON عند طلب إجراء:
   {"action": "اسم", "params": {...}, "reply": "رسالة تأكيد"}

2. **التكليف**: {"action": "delegate_task", "params": {"to_agent": "writer", "task": "اكتب بوست"}}

3. **الاستشارة**: {"action": "consult_all", "params": {"question": "ما رأيكم في..."}}"""

    return (
        f"أنت {agent['emoji']} {agent['name']} ({agent['name_ar']}) — {agent['role_ar']}.\n"
        f"{agent['description_ar']}\n\n"
        f"## شخصيتك:\n{agent['personality_ar']}\n\n"
        f"## أنت تملك {len(agent_actions)} أداة لإدارة لوحة التحكم بالكامل:\n{actions_desc}\n\n"
        f"{learning_section}\n\n"
        f"## فريق الوكلاء:\n{agents_list}\n\n"
        f"## قواعد العمل:\n\n{rules}\n\n"
        f"4. **الأمان**: لا تحذف أو تعدّل كبير دون تأكيد.\n"
        f"5. **اللغة**: تحدث بنفس لغة الأدمن.\n"
        f"6. **التنسيق**: <b>عريض</b>، <code>كود</code>، • قوائم\n"
    )


# ═══════════════════════════════════════════════════════════════
#  CHAT PROCESSOR
# ═══════════════════════════════════════════════════════════════

def process_chat_message(admin_id, user_message, target_agent=None):
    mentioned_agent, clean_text = find_agent_by_mention(user_message)
    if mentioned_agent:
        agent_id = mentioned_agent; user_message = clean_text
    elif target_agent:
        agent_id = target_agent
    else:
        agent_id = detect_intent_agent(user_message)

    agent = get_agent(agent_id)
    msg_id = save_message(admin_id, agent_id, 'user', user_message)
    history = get_conversation_history(admin_id, agent_id, limit=15)
    system_prompt = _build_agent_system_prompt(agent_id, admin_id)
    messages = [{'role': 'system', 'content': system_prompt}]
    for h in history[:-1]:
        messages.append({'role': h['role'], 'content': h['content']})
    messages.append({'role': 'user', 'content': user_message})

    ai_result = _call_ai(messages)
    if not ai_result['success']:
        save_message(admin_id, agent_id, 'assistant', f'❌ خطأ: {ai_result["error"]}')
        return {'success': False, 'error': ai_result['error'], 'agent_id': agent_id}

    ai_reply = ai_result['content']
    action_result = None; action_name = None; parsed = None
    try:
        parsed = _extract_json(ai_reply)
        if parsed and 'action' in parsed:
            action_name = parsed['action']; params = parsed.get('params', {})
            if action_name == 'delegate_task':
                _init_chat_db()
                try:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute('INSERT INTO ai_task_delegations (admin_id, from_agent, to_agent, task_description) VALUES (?, ?, ?, ?)',
                                 (str(admin_id), agent_id, params.get('to_agent',''), params.get('task','')))
                    conn.commit(); conn.close()
                except: pass
                action_result = execute_action(action_name, params)
            elif action_name == 'consult_all':
                question = params.get('question', user_message)
                consultations = []
                for oid, oa in AGENTS.items():
                    if oid == agent_id: continue
                    consult_messages = [{'role': 'system', 'content': _build_agent_system_prompt(oid, admin_id)},
                                        {'role': 'user', 'content': f'الأدمن يطلب استشارتك في: {question}\n\nأجب باختصار (3-4 جمل).'}]
                    cr = _call_ai(consult_messages)
                    if cr.get('success'):
                        consultations.append({'agent_id': oid, 'agent_name': oa['name_ar'], 'agent_emoji': oa['emoji'], 'response': cr['content']})
                action_result = {'success': True, 'consultations': consultations, 'question': question}
            else:
                action_result = execute_action(action_name, params)
            if parsed.get('reply'): ai_reply = parsed['reply']
    except: pass

    response_text = ai_reply
    if action_result and action_result.get('success'):
        if action_name == 'consult_all':
            consultations = action_result.get('consultations', [])
            lines = [f'💬 <b>استشارة الفريق — {len(consultations)} وكلاء:</b>\n']
            for c in consultations:
                lines.append(f'{c["agent_emoji"]} <b>{c["agent_name"]}:</b>\n{c["response"]}\n')
            response_text = '\n'.join(lines)
        elif action_name == 'delegate_task':
            response_text += f'\n\n{action_result.get("message", "")}'
        else:
            response_text += '\n\n' + _format_action_result(action_name, action_result)
    elif action_result and not action_result.get('success'):
        response_text += f'\n\n❌ خطأ: {action_result.get("error", "")}'

    assistant_msg_id = save_message(admin_id, agent_id, 'assistant', response_text, action_taken=action_name)
    success = action_result.get('success', False) if action_result else True
    error_msg = action_result.get('error') if action_result and not action_result.get('success') else None
    record_action_outcome(admin_id, agent_id, action_name or 'chat', parsed.get('params', {}) if parsed else {}, success, error_msg, str(action_result)[:500] if action_result else None, user_message)
    _detect_preferences(admin_id, user_message)

    return {'success': True, 'reply': response_text, 'action_taken': action_name,
            'action_result': action_result, 'message_id': assistant_msg_id,
            'agent_id': agent_id, 'agent_name': agent['name_ar'], 'agent_emoji': agent['emoji'],
            'agent_color': agent['color']}


def _detect_preferences(admin_id, message):
    arabic_chars = sum(1 for c in message if '\u0600' <= c <= '\u06FF')
    if arabic_chars > len(message) * 0.3: set_admin_preference(admin_id, 'language', 'ar', confidence=0.8)
    elif arabic_chars == 0 and len(message) > 5: set_admin_preference(admin_id, 'language', 'en', confidence=0.8)
    msg_lower = message.lower()
    if any(w in msg_lower for w in ['واتساب', 'whatsapp']): set_admin_preference(admin_id, 'default_platform', 'whatsapp', confidence=0.7)
    elif any(w in msg_lower for w in ['تليجرام', 'telegram']): set_admin_preference(admin_id, 'default_platform', 'telegram', confidence=0.7)


# ═══════════════════════════════════════════════════════════════
#  AI API CALL
# ═══════════════════════════════════════════════════════════════

def _call_ai(messages):
    try:
        from ai_composer import get_active_keys
        keys = get_active_keys(DB_PATH)
        if not keys: return {'success': False, 'error': 'لا توجد مفاتيح AI'}
        key = keys[0]
        api_key = key.get('api_key', ''); base_url = (key.get('base_url') or '').rstrip('/')
        model = key.get('default_model', ''); provider = (key.get('provider') or '').lower()
        timeout = int(key.get('timeout_seconds', 60))
        if not base_url:
            if 'openrouter' in provider: base_url = 'https://openrouter.ai/api/v1'
            elif 'openai' in provider: base_url = 'https://api.openai.com/v1'
            else: base_url = 'https://openrouter.ai/api/v1'
        if not model: model = 'openai/gpt-4o-mini' if 'openrouter' in provider else 'gpt-4o-mini'
        url = base_url + '/chat/completions'
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        if 'openrouter' in provider: headers['HTTP-Referer'] = 'https://vex.deals'; headers['X-Title'] = 'VEX Admin'
        payload = {'model': model, 'messages': messages, 'temperature': 0.4, 'max_tokens': 2048}
        try:
            import httpx
            with httpx.Client(timeout=float(timeout)) as client: resp = client.post(url, headers=headers, json=payload)
        except ImportError:
            import urllib.request, ssl
            ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            body = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=body, headers=headers, method='POST')
            resp_raw = urllib.request.urlopen(req, timeout=float(timeout), context=ctx)
            class FakeResp:
                def __init__(s, d, c): s.status_code = c; s._d = d
                def json(s): return json.loads(s._d)
            resp = FakeResp(resp_raw.read().decode(), resp_raw.status)
        if resp.status_code != 200:
            try: detail = resp.json().get('error', {}).get('message', str(resp.status_code))
            except: detail = str(resp.status_code)
            return {'success': False, 'error': f'API error {resp.status_code}: {detail}'}
        data = resp.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        if not content: return {'success': False, 'error': 'رد AI فارغ'}
        return {'success': True, 'content': content}
    except Exception as e:
        logger.error(f"AI chat error: {e}"); return {'success': False, 'error': str(e)}


def _extract_json(text):
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try: return json.loads(match.group(1))
        except: pass
    match = re.search(r'\{[^{}]*"action"\s*:\s*"[^"]*"[^{}]*\}', text, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except: pass
    brace_start = text.find('{')
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == '{': depth += 1
            elif text[i] == '}': depth -= 1
            if depth == 0:
                try: return json.loads(text[brace_start:i+1])
                except: break
    return None


def _format_action_result(action_name, result):
    if action_name == 'create_post':
        return f"📤 تم الإرسال إلى {result.get('queued', 0)} قناة"
    elif action_name == 'broadcast':
        return f"📢 تم وضع الرسالة في قائمة البث ({result.get('target', 'all')})"
    elif action_name == 'broadcast_queue':
        return f"📋 قائمة الانتظار: {result.get('total', 0)} رسالة معلقة"
    elif action_name == 'get_stats':
        stats = result.get('stats', {}); lines = ['📊 <b>الإحصائيات:</b>']
        for k, label in [('total_users','المستخدمون'), ('total_revenue','الإيرادات'), ('pending_transactions','المعاملات المعلقة'), ('total_channels','القنوات'), ('pending_matches','المطابقات')]:
            if k in stats: lines.append(f"• {label}: <b>{stats[k]}</b>")
        return '\n'.join(lines)
    elif action_name == 'get_stats_detailed':
        stats = result.get('stats', {}); lines = [f'📊 <b>إحصائيات {stats.get("period","")}:</b>']
        for k, label in [('deposits_count','الإيداعات'), ('deposits_amount','مبلغ الإيداعات'), ('withdrawals_count','السحوبات'), ('withdrawals_amount','مبلغ السحوبات'), ('new_users','مستخدمون جدد'), ('new_matches','مطابقات جديدة'), ('complaints_count','شكاوى')]:
            if k in stats: lines.append(f"• {label}: <b>{stats[k]}</b>")
        return '\n'.join(lines)
    elif action_name == 'platform_stats':
        stats = result.get('stats', {}); lines = ['🖥️ <b>إحصائيات المنصة:</b>']
        for k, label in [('total_users','المستخدمون'), ('total_transactions','المعاملات'), ('total_matches','المطابقات'), ('total_tickets','التذاكر'), ('total_revenue','الإيرادات'), ('banned_users','محظورون')]:
            if k in stats: lines.append(f"• {label}: <b>{stats[k]}</b>")
        return '\n'.join(lines)
    elif action_name == 'list_channels':
        channels = result.get('channels', []); lines = [f"📋 <b>القنوات ({result.get('total', 0)}):</b>"]
        for ch in channels[:15]:
            s = '🟢' if str(ch.get('is_active','')).lower() in ('yes','true','1','') else '🔴'
            lines.append(f"• {s} {ch.get('name', ch.get('chat_id',''))} ({ch.get('platform','')})")
        return '\n'.join(lines)
    elif action_name == 'list_users':
        users = result.get('users', []); lines = [f"👥 <b>المستخدمون ({result.get('total', 0)}):</b>"]
        for u in users[:10]:
            ban = '🚫' if u.get('is_banned') in (1, '1', 'yes') else ''
            lines.append(f"• {u.get('name', 'N/A')} (<code>{u.get('telegram_id', '')}</code>) {ban}")
        return '\n'.join(lines)
    elif action_name == 'user_detail':
        user = result.get('user', {}); lines = [f"👤 <b>تفاصيل المستخدم:</b>",
            f"• الاسم: {user.get('name','N/A')}", f"• المعرف: <code>{user.get('telegram_id','')}</code>",
            f"• الرصيد: {user.get('balance',0)}", f"• محظور: {'نعم' if user.get('is_banned') else 'لا'}"]
        txns = user.get('recent_transactions', [])
        if txns: lines.append(f"• آخر المعاملات: {len(txns)}")
        return '\n'.join(lines)
    elif action_name in ('ban_user', 'unban_user'):
        return f"✅ تم التنفيذ بنجاح"
    elif action_name == 'send_message_to_user':
        return f"✅ تم إرسال الرسالة للمستخدم {result.get('user_id', '')}"
    elif action_name == 'view_transactions':
        txns = result.get('transactions', []); lines = [f"💰 <b>المعاملات ({result.get('total', 0)}):</b>"]
        for t in txns[:10]:
            status_emoji = {'approved': '✅', 'pending': '⏳', 'rejected': '❌'}.get(t.get('status',''), '?')
            lines.append(f"• {status_emoji} #{t.get('id','')} — {t.get('type','')} — {t.get('amount',0)} — {t.get('status','')}")
        return '\n'.join(lines)
    elif action_name == 'pending_requests':
        stats = result.get('stats', {}); lines = ['⏳ <b>الطلبات المعلقة:</b>',
            f"• معاملات: <b>{stats.get('pending_txn_count', 0)}</b>",
            f"• مطابقات: <b>{stats.get('pending_match_count', 0)}</b>",
            f"• تذاكر: <b>{stats.get('pending_ticket_count', 0)}</b>"]
        return '\n'.join(lines)
    elif action_name in ('approve_txn', 'reject_txn'):
        return f"✅ تم تنفيذ الإجراء على المعاملة #{result.get('txn_id', '')}"
    elif action_name == 'bulk_approve':
        return f"✅ تمت approval جماعية: {result.get('approved_count', 0)} معاملة"
    elif action_name == 'view_matching':
        matches = result.get('requests', []); lines = [f"🔗 <b>المطابقات ({result.get('total', 0)}):</b>"]
        for m in matches[:10]:
            lines.append(f"• #{m.get('id','')} — {m.get('status','')} — {m.get('created_at','')}")
        return '\n'.join(lines)
    elif action_name in ('approve_match', 'reject_match', 'resolve_dispute'):
        return f"✅ تم تنفيذ الإجراء على المطابقة"
    elif action_name == 'view_complaints':
        tickets = result.get('tickets', []); lines = [f"🎫 <b>التذاكر ({result.get('total', 0)}):</b>"]
        for t in tickets[:10]:
            lines.append(f"• #{t.get('id','')} — {t.get('subject', t.get('status',''))} — {t.get('status','')}")
        return '\n'.join(lines)
    elif action_name == 'reply_ticket':
        return f"✅ تم الرد على التذكرة #{result.get('ticket_id', '')}"
    elif action_name == 'update_ticket_status':
        return f"✅ تم تحديث حالة التذكرة إلى: {result.get('new_status', '')}"
    elif action_name == 'add_channel':
        return f"✅ تمت إضافة القناة {result.get('name', result.get('chat_id', ''))}"
    elif action_name == 'toggle_channel':
        return f"✅ حالة القناة: {result.get('new_status', '')}"
    elif action_name == 'delete_channel':
        return f"✅ تم حذف القناة"
    elif action_name == 'update_setting':
        return f"✅ تم تحديث الإعداد {result.get('key', '')} إلى {result.get('value', '')}"
    elif action_name == 'get_settings':
        settings = result.get('settings', []); lines = [f"⚙️ <b>الإعدادات ({len(settings)}):</b>"]
        for s in settings[:15]: lines.append(f"• <code>{s.get('key','')}</code> = {s.get('value','')}")
        return '\n'.join(lines)
    elif action_name == 'toggle_game':
        return f"✅ حالة اللعبة: {result.get('new_status', '')}"
    elif action_name == 'game_stats':
        games = result.get('games', []); lines = ['🎮 <b>إحصائيات الألعاب:</b>']
        for g in games[:8]: lines.append(f"• {g.get('name', g.get('id',''))} — جولات: {g.get('rounds',0)} — رهانات: {g.get('total_bets',0)}")
        return '\n'.join(lines)
    elif action_name == 'list_companies':
        companies = result.get('companies', []); lines = [f"🏢 <b>الشركات ({len(companies)}):</b>"]
        for c in companies[:10]: lines.append(f"• {c.get('name', c.get('id',''))}")
        return '\n'.join(lines)
    elif action_name == 'company_detail':
        c = result.get('company', {}); lines = [f"🏢 <b>{c.get('name','')}</b>",
            f"• المعاملات: {c.get('transaction_count',0)}", f"• الحجم: {c.get('total_volume',0)}"]
        return '\n'.join(lines)
    elif action_name == 'list_admins':
        admins = result.get('admins', []); lines = [f"👤 <b>الأدمنز ({len(admins)}):</b>"]
        for a in admins[:10]: lines.append(f"• {a.get('name', a.get('user_id',''))} — {a.get('role','')}")
        return '\n'.join(lines)
    elif action_name == 'add_admin':
        return f"✅ تمت إضافة الأدمن {result.get('user_id', '')} بدور {result.get('role', '')}"
    elif action_name == 'create_backup':
        return f"✅ تمت إنشاء نسخة احتياطية: {result.get('backup_file', '').split('/')[-1]}"
    elif action_name == 'list_backups':
        backups = result.get('backups', []); lines = [f"💾 <b>النسخ الاحتياطية ({len(backups)}):</b>"]
        for b in backups[:10]: lines.append(f"• {b.get('name','')} ({b.get('size','')})")
        return '\n'.join(lines)
    elif action_name == 'create_multi_post':
        return f"📤 تم إنشاء المنشور المتعدد المنصات: <b>{result.get('post_id','')}</b>\nعدد التنسيقات: {result.get('variants',0)}"
    elif action_name == 'list_multi_posts':
        posts = result.get('posts', []); lines = [f"📤 <b>المنشورات ({result.get('total', 0)}):</b>"]
        for p in posts[:10]:
            platforms = ', '.join(p.get('platforms', []))
            lines.append(f"• {p.get('title','')} — [{platforms}] — {p.get('status','')}")
        return '\n'.join(lines)
    elif action_name == 'publish_post':
        return f"✅ تم نشر المنشور على {result.get('platform','')} — {result.get('queued',0)} قناة"
    elif action_name == 'preview_post':
        v = result.get('variant', {})
        return f"👁️ <b>معاينة {v.get('platform','')} ({v.get('char_count',0)}/{v.get('max_length',0)} حرف):</b>\n\n{v.get('content','')[:500]}"
    elif action_name == 'contact_stats':
        s = result.get('stats', {})
        return f"""👥 <b>إحصائيات جهات الاتصال:</b>
• الإجمالي: <b>{s.get('total',0)}</b>
• تليجرام: <b>{s.get('telegram',0)}</b>
• واتساب: <b>{s.get('whatsapp',0)}</b>
• كلاهما: <b>{s.get('both',0)}</b>
• تم الإرسال: <b>{s.get('messaged',0)}</b>
• معلق: <b>{s.get('pending',0)}</b>"""
    elif action_name == 'list_imports':
        imports = result.get('imports', []); lines = [f"📥 <b>الاستيرادات ({len(imports)}):</b>"]
        for i in imports[:10]:
            lines.append(f"• {i.get('filename','')} — {i.get('total_contacts',0)} جهة ({i.get('telegram_contacts',0)} TG, {i.get('whatsapp_contacts',0)} WA)")
        return '\n'.join(lines)
    elif action_name == 'send_to_contacts':
        return f"""📤 <b>تم إرسال الرسائل:</b>
• تم الإرسال: <b>{result.get('queued',0)}</b>
• تم تخطي (معدل): {result.get('skipped_rate_limit',0)}
• تم تخطي (محتوى مكرر): {result.get('skipped_content_duplicate',0)}
• المنصة: {result.get('platform','')}"""
    elif action_name == 'anti_ban_status':
        s = result.get('status', {}); l = result.get('limits', {})
        return f"""🛡️ <b>حالة الحماية من الحظر:</b>
• هذا الساعة: {s.get('hour_used',0)}/{s.get('hour_limit',0)}
• اليوم: {s.get('day_used',0)}/{s.get('day_limit',0)}
• الحد الأدنى للتأخير: {l.get('min_delay_seconds',0)} ثانية
• الحد الأقصى للتأخير: {l.get('max_delay_seconds',0)} ثانية"""
    elif action_name == 'anti_ban_log':
        log = result.get('log', []); lines = [f"🛡️ <b>سجل الحماية ({len(log)}):</b>"]
        for l in log[:10]:
            status_emoji = '✅' if l.get('status') == 'sent' else '❌'
            lines.append(f"• {status_emoji} {l.get('platform','')} — {l.get('delay_used',0)}s delay")
        return '\n'.join(lines)
    elif action_name == 'list_relays':
        relays = result.get('relays', []); lines = [f"🔄 <b>عمليات النقل ({len(relays)}):</b>"]
        for r in relays[:10]:
            active = '🟢' if r.get('is_active') else '🔴'
            stats = r.get('stats', {})
            lines.append(f"• {active} #{r.get('id','')} {r.get('name','')} — {r.get('source_platform','')}→{r.get('dest_platform','')} ({stats.get('total',0)} عملية)")
        return '\n'.join(lines)
    elif action_name == 'relay_status':
        r = result.get('relay', {}); s = result.get('stats', {})
        platforms = f"{r.get('source_platform','')} → {r.get('dest_platform','')}"
        sources = len(r.get('source_ids', [])); dests = len(r.get('dest_ids', []))
        return f"""🔄 <b>عملية النقل #{r.get('id','')} — {r.get('name','')}</b>
• المنصات: {platforms}
• المصادر: {sources} | الوجهات: {dests}
• الوكيل: {r.get('agent_id','')} | AI: {'مفعّل' if r.get('ai_transform') else 'معطّل'}
• الحالة: {'🟢 نشط' if r.get('is_active') else '🔴 معطّل'}
• المعالج: {s.get('total',0)} | ناجح: {s.get('success',0)} | فاشل: {s.get('failed',0)}
• برومت الوكيل: {(r.get('agent_prompt','') or '')[:100]}"""
    elif action_name == 'relay_log':
        log = result.get('log', []); lines = [f"🔄 <b>سجل النقل ({len(log)}):</b>"]
        for l in log[:10]:
            emoji = '✅' if l.get('status') == 'success' else '❌'
            ai = '🤖' if l.get('ai_used') else ''
            lines.append(f"• {emoji} {l.get('source_platform','')}→{l.get('dest_platform','')} {ai} — {l.get('created_at','')[:16]}")
        return '\n'.join(lines)
    elif action_name == 'relay_stats':
        s = result.get('stats', {})
        return f"""🔄 <b>إحصائيات النقل:</b>
• الإجمالي: <b>{s.get('total',0)}</b>
• ناجح: <b>{s.get('success',0)}</b> | فاشل: <b>{s.get('failed',0)}</b>
• معالج بالـ AI: <b>{s.get('ai_processed',0)}</b>"""
    elif action_name == 'browser_list':
        instances = result.get('instances', []); lines = [f"🌐 <b>نوافذ المتصفح ({len(instances)}):</b>"]
        for inst in instances[:10]:
            status = '🟢' if inst.get('status')=='running' else '🔴'
            lines.append(f"• {status} {inst.get('name','')} — {inst.get('current_url','about:blank')[:50]}")
        return '\n'.join(lines)
    elif action_name == 'browser_open':
        return f"""🌐 <b>تم فتح المتصفح</b>
• الرابط: {result.get('navigate',{}).get('url','')}
• العنوان: {result.get('navigate',{}).get('title','')}
• النافذة: {result.get('instance_id','')[:8]}"""
    elif action_name == 'browser_screenshot':
        return f"""📸 <b>تم أخذ لقطة الشاشة</b>
• الرابط: {result.get('url','')}
• الملف: {result.get('path','')}"""
    elif action_name == 'browser_status':
        inst = result.get('instance', {})
        if inst:
            return f"""🌐 <b>حالة النافذة:</b>
• الاسم: {inst.get('name','')}
• الحالة: {'🟢 يعمل' if inst.get('status')=='running' else '🔴 متوقف'}
• الرابط: {inst.get('current_url','about:blank')}
• الكوكيز: {inst.get('cookies_count',0)}
• الصفحات: {inst.get('pages_visited',0)}"""
        return f"🌐 <b>{result.get('total',0)} نوافذ نشطة</b>"
    elif action_name == 'daemon_status':
        d = result.get('daemon', {})
        h = d.get('health', {})
        return f"""🖥️ <b>حالة Daemon:</b>
• الحالة: {'🟢 نشط' if d.get('running') else 'متوقف'}
• النوافذ: {d.get('instances',0)}
• نشطة: {d.get('active',0)} | في النوم: {d.get('sleeping',0)}
• إعادة تشغيل: {h.get('restarts',0)}
• فحوصات: {h.get('checks',0)}"""
    elif action_name == 'sleep_all_browsers':
        return f"😴 <b>{result.get('message','')}</b>"
    elif action_name == 'wake_all_browsers':
        return f"☀️ <b>{result.get('message','')}</b>"
    elif action_name == 'analyze_site':
        f = result.get('findings', {})
        lines = [f"🔍 <b>تحليل الموقع:</b>"]
        if f.get('login_elements'):
            lines.append(f"• عناصر تسجيل الدخول: {len(f['login_elements'])}")
        if f.get('forms'):
            lines.append(f"• نماذج: {len(f['forms'])}")
        if f.get('navigation'):
            lines.append(f"• روابط تنقل: {len(f['navigation'])}")
        if not any(f.get(k) for k in ['login_elements', 'forms', 'navigation']):
            lines.append("• لم يتم العثور على عناصر مميزة")
        return '\n'.join(lines)
    elif action_name == 'site_knowledge':
        k = result.get('knowledge', {})
        return f"""🧠 <b>معرفة الموقع: {k.get('domain','')}</b>
• عناصر معرفة: {k.get('knowledge_count',0)}
• Selectors: {k.get('selectors',0)} | نماذج: {k.get('forms',0)}
• أنماط نجاح: {k.get('patterns',0)}
• نسبة النجاح: {k.get('success_rate',0)}%
• إجراءات: {k.get('total_actions',0)}"""
    elif action_name == 'all_knowledge':
        sites = result.get('sites', [])
        lines = [f"🧠 <b>المواقع المعرفة ({len(sites)}):</b>"]
        for s in sites[:15]:
            lines.append(f"• {s.get('site_domain','')} — {s.get('total',0)} معرفة | ثقة: {round(s.get('avg_confidence',0)*100)}%")
        return '\n'.join(lines)
    elif action_name == 'browser_patterns':
        patterns = result.get('patterns', [])
        lines = [f"📋 <b>أنماط النجاح ({len(patterns)}):</b>"]
        for p in patterns[:10]:
            lines.append(f"• {p.get('site_domain','')}/{p.get('goal','')} — نجاح: {round(p.get('success_rate',0)*100)}% ({p.get('times_used',0)} مرة)")
        return '\n'.join(lines)
    elif action_name == 'browser_task':
        task = result.get('task', {})
        status = '✅' if task.get('status') == 'completed' else '❌'
        lines = [f"{status} <b>مهمة: {task.get('goal','')}</b>"]
        lines.append(f"• الحالة: {task.get('status','')}")
        lines.append(f"• النتائج: {len(task.get('results',[]))} خطوة")
        if task.get('error'):
            lines.append(f"• خطأ: {task.get('error','')}")
        return '\n'.join(lines)
    elif action_name == 'browser_scrape':
        text = result.get('scraped_text', '')
        if text:
            return f"📄 <b>محتوى الصفحة:</b>\n{text[:1500]}"
        return "📄 لم يتم استخراج محتوى"
    elif action_name == 'browser_quick_login':
        task = result.get('task', {})
        if task.get('status') == 'completed':
            return f"✅ <b>تم تسجيل الدخول بنجاح</b>"
        return f"❌ <b>فشل تسجيل الدخول:</b> {task.get('error', 'خطأ غير معروف')}"
    elif action_name == 'generate_post':
        if result.get('success'): return f"🤖 <b>البوست:</b>\n\n{result.get('text', '')}"
        return f"❌ خطأ: {result.get('error', '')}"
    elif action_name == 'translate_post':
        return f"🌐 <b>الترجمة:</b>\n\n{result.get('translation', '')}"
    elif action_name == 'get_learning_stats':
        stats = result.get('stats', {})
        return f"""🧠 <b>إحصائيات التعلم:</b>
• إجراءات: <b>{stats.get('total_actions', 0)}</b> (ناجحة: {stats.get('successful_actions', 0)})
• أنماط: <b>{stats.get('learned_patterns', 0)}</b> | معلومات: <b>{stats.get('knowledge_facts', 0)}</b>
• تصحيحات: <b>{stats.get('corrections', 0)}</b> | 👍{stats.get('positive_feedback', 0)} 👎{stats.get('negative_feedback', 0)}"""
    elif action_name == 'list_agents':
        agents = result.get('agents', []); lines = [f"🤖 <b>وكلاء المطابقة ({len(agents)}):</b>"]
        for a in agents[:10]: lines.append(f"• {a.get('name', a.get('id',''))} — رصيد: {a.get('balance',0)}")
        return '\n'.join(lines)
    elif action_name == 'agent_stats':
        agents = result.get('agents', []); lines = ['📊 <b>إحصائيات الوكلاء:</b>']
        for a in agents[:8]: lines.append(f"• {a.get('name', a.get('id',''))} — مطابقات: {a.get('total_matches',0)} — مكتملة: {a.get('completed',0)}")
        return '\n'.join(lines)
    return json.dumps(result, ensure_ascii=False, indent=2)
