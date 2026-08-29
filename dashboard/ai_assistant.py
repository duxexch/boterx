"""
AI Admin Assistant v3 — Multi-Agent System
دردشة احترافية مع فريق وكلاء ذكاء اصطناعي.
"""

import json
import sqlite3
import os
import csv
import re
import time
import hashlib
import logging
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
        'id': 'commander',
        'name': 'Commander',
        'name_ar': 'القائد',
        'emoji': '🎯',
        'color': '#8b5cf6',
        'role': 'General Manager & Coordinator',
        'role_ar': 'المدير العام والمنسق',
        'description': 'The main coordinator. Handles general requests, delegates tasks to specialized agents, and provides overall guidance.',
        'description_ar': 'المنسق الرئيسي. يتعامل مع الطلبات العامة ويوزع المهام على الوكلاء المتخصصين ويقدم التوجيه العام.',
        'personality': 'Professional, decisive, strategic. Thinks big picture. Delegates to specialists when needed.',
        'personality_ar': 'محترف، حاسم، استراتيجي. يفكر بالصورة الكبيرة. يوزع على المتخصصين عند الحاجة.',
        'specialties': ['general', 'delegation', 'planning', 'coordination', 'decisions'],
        'actions': ['get_stats', 'list_channels', 'list_users', 'ban_user', 'send_message_to_user',
                   'view_transactions', 'view_matching', 'view_complaints', 'update_setting',
                   'learn_fact', 'get_learning_stats', 'delegate_task', 'consult_all'],
    },
    'writer': {
        'id': 'writer',
        'name': 'Writer',
        'name_ar': 'الكاتب',
        'emoji': '✍️',
        'color': '#06b6d4',
        'role': 'Content Creator & Copywriter',
        'role_ar': 'منشئ المحتوى وكاتب النصوص',
        'description': 'Specializes in creating posts, writing content, copywriting, and creative text for all platforms.',
        'description_ar': 'متخصص في إنشاء البوستات وكتابة المحتوى والنصوص الإبداعية لجميع المنصات.',
        'personality': 'Creative, expressive, detail-oriented. Uses emojis and formatting effectively.',
        'personality_ar': 'مبدع، تعبيري، دقيق. يستخدم الإيموجي والتنسيق بفعالية.',
        'specialties': ['content', 'posts', 'copywriting', 'creative', 'social_media'],
        'actions': ['create_post', 'generate_post', 'broadcast', 'list_channels'],
    },
    'analyst': {
        'id': 'analyst',
        'name': 'Analyst',
        'name_ar': 'المحلل',
        'emoji': '📊',
        'color': '#f59e0b',
        'role': 'Data Analyst & Reporter',
        'role_ar': 'محلل البيانات ومعد التقارير',
        'description': 'Specializes in statistics, data analysis, generating reports, and providing insights.',
        'description_ar': 'متخصص في الإحصائيات وتحليل البيانات وإعداد التقارير وتقديم الأفكار.',
        'personality': 'Analytical, precise, data-driven. Presents numbers clearly with context.',
        'personality_ar': 'تحليلي، دقيق، مبني على البيانات. يعرض الأرقام بوضوح مع السياق.',
        'specialties': ['statistics', 'analysis', 'reports', 'data', 'insights'],
        'actions': ['get_stats', 'view_transactions', 'view_matching', 'view_complaints'],
    },
    'support': {
        'id': 'support',
        'name': 'Support',
        'name_ar': 'الدعم',
        'emoji': '🛡️',
        'color': '#10b981',
        'role': 'User Support & Relations',
        'role_ar': 'دعم المستخدمين والعلاقات',
        'description': 'Handles user management, complaints, disputes, and support-related tasks.',
        'description_ar': 'يتعامل مع إدارة المستخدمين والشكاوى والنزاعات ومهام الدعم.',
        'personality': 'Empathetic, patient, solution-focused. Prioritizes user satisfaction.',
        'personality_ar': 'متعاطف، صبور، يركز على الحلول. يعطي الأولوية لرضا المستخدم.',
        'specialties': ['users', 'complaints', 'disputes', 'support', 'relations'],
        'actions': ['list_users', 'ban_user', 'send_message_to_user', 'view_complaints',
                   'view_transactions', 'view_matching'],
    },
    'tech': {
        'id': 'tech',
        'name': 'Tech',
        'name_ar': 'التقني',
        'emoji': '⚙️',
        'color': '#ef4444',
        'role': 'Technical Manager',
        'role_ar': 'المدير التقني',
        'description': 'Handles system settings, technical configuration, and infrastructure tasks.',
        'description_ar': 'يتعامل مع إعدادات النظام والتكوين التقني والبنية التحتية.',
        'personality': 'Precise, technical, thorough. Focuses on system health and configuration.',
        'personality_ar': 'دقيق، تقني، شامل. يركز على صحة النظام والتكوين.',
        'specialties': ['settings', 'technical', 'configuration', 'system', 'infrastructure'],
        'actions': ['update_setting', 'get_stats', 'list_channels'],
    },
}

# Default agent
DEFAULT_AGENT = 'commander'


def get_agent(agent_id):
    """Get agent definition by ID."""
    return AGENTS.get(agent_id, AGENTS[DEFAULT_AGENT])


def get_all_agents():
    """Get all agents as a list."""
    return list(AGENTS.values())


def find_agent_by_mention(text):
    """Find agent from @mention in text. Returns (agent_id, clean_text)."""
    for aid, agent in AGENTS.items():
        # Check @name, @name_ar, @id patterns
        patterns = [
            f'@{agent["name"].lower()}',
            f'@{agent["name_ar"]}',
            f'@{aid}',
        ]
        for pattern in patterns:
            if pattern.lower() in text.lower():
                clean_text = re.sub(re.escape(pattern), '', text, flags=re.IGNORECASE).strip()
                return aid, clean_text
    return None, text


def detect_intent_agent(message):
    """Auto-detect which agent should handle this message based on content."""
    msg_lower = message.lower()

    # Content creation keywords
    if any(w in msg_lower for w in ['بوست', 'post', 'محتوى', 'content', 'اكتب', 'write', 'نص', 'text',
                                      'تغريدة', 'tweet', 'caption', 'troijh', '宣传', 'ترجم', 'translate']):
        return 'writer'

    # Statistics/analysis keywords
    if any(w in msg_lower for w in ['إحصائي', 'stat', 'تقرير', 'report', 'تحليل', 'analysis', 'بيانات', 'data',
                                      'أرقام', 'numbers', 'كم', 'how many', 'revenue', 'إيرادات']):
        return 'analyst'

    # User/support keywords
    if any(w in msg_lower for w in ['مستخدم', 'user', 'شكوى', 'complaint', 'دعم', 'support', 'حظر', 'ban',
                                      'رسالة', 'send', 'dispute', 'نزاع']):
        return 'support'

    # Technical keywords
    if any(w in msg_lower for w in ['إعداد', 'setting', 'تكوين', 'config', 'نظام', 'system', 'تقنية', 'tech',
                                      'تحديث', 'update', 'fix', 'إصلاح']):
        return 'tech'

    # Delegation keywords
    if any(w in msg_lower for w in ['نادي', 'call', 'اسأل', 'ask all', 'all agents', 'all', 'الكل',
                                      'ايgent', 'agent', 'وكلاء']):
        return 'commander'

    return DEFAULT_AGENT


# ═══════════════════════════════════════════════════════════════
#  DATABASE INIT
# ═══════════════════════════════════════════════════════════════

def _init_chat_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS ai_chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT 'commander',
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            action_taken TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS ai_action_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            agent_id TEXT DEFAULT 'commander',
            action_name TEXT NOT NULL,
            params TEXT,
            success INTEGER NOT NULL,
            error_message TEXT,
            result_summary TEXT,
            user_message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS ai_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phrase_hash TEXT NOT NULL,
            phrase_sample TEXT NOT NULL,
            action_name TEXT NOT NULL,
            agent_id TEXT DEFAULT 'commander',
            params_template TEXT,
            confidence REAL DEFAULT 0.5,
            times_used INTEGER DEFAULT 1,
            times_succeeded INTEGER DEFAULT 0,
            last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(phrase_hash, action_name)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS ai_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            fact_key TEXT NOT NULL,
            fact_value TEXT NOT NULL,
            source TEXT DEFAULT 'learned',
            confidence REAL DEFAULT 0.5,
            times_confirmed INTEGER DEFAULT 1,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category, fact_key)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS ai_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            agent_id TEXT DEFAULT 'commander',
            original_action TEXT,
            original_params TEXT,
            corrected_action TEXT,
            corrected_params TEXT,
            correction_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS ai_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            pref_key TEXT NOT NULL,
            pref_value TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(admin_id, pref_key)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS ai_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            agent_id TEXT DEFAULT 'commander',
            message_id INTEGER,
            rating INTEGER NOT NULL,
            correction_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS ai_task_delegations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            task_description TEXT NOT NULL,
            task_result TEXT,
            status TEXT DEFAULT 'pending',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        for idx_sql in [
            'CREATE INDEX IF NOT EXISTS idx_chat_admin ON ai_chat_history(admin_id, timestamp)',
            'CREATE INDEX IF NOT EXISTS idx_chat_agent ON ai_chat_history(agent_id)',
            'CREATE INDEX IF NOT EXISTS idx_outcomes_admin ON ai_action_outcomes(admin_id, timestamp)',
            'CREATE INDEX IF NOT EXISTS idx_outcomes_action ON ai_action_outcomes(action_name, success)',
            'CREATE INDEX IF NOT EXISTS idx_patterns_hash ON ai_patterns(phrase_hash)',
            'CREATE INDEX IF NOT EXISTS idx_knowledge_cat ON ai_knowledge(category)',
            'CREATE INDEX IF NOT EXISTS idx_feedback_admin ON ai_feedback(admin_id, timestamp)',
        ]:
            c.execute(idx_sql)

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Chat DB init error: {e}")


# ═══════════════════════════════════════════════════════════════
#  MEMORY
# ═══════════════════════════════════════════════════════════════

def save_message(admin_id, agent_id, role, content, action_taken=None):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute(
            'INSERT INTO ai_chat_history (admin_id, agent_id, role, content, action_taken) VALUES (?, ?, ?, ?, ?)',
            (str(admin_id), agent_id, role, content, action_taken)
        )
        msg_id = cur.lastrowid
        conn.commit(); conn.close()
        return msg_id
    except Exception as e:
        logger.error(f"Save message error: {e}")
        return None


def get_conversation_history(admin_id, agent_id=None, limit=20):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        if agent_id:
            rows = conn.execute(
                'SELECT role, content, action_taken, agent_id, timestamp FROM ai_chat_history '
                'WHERE admin_id = ? AND agent_id = ? ORDER BY timestamp DESC LIMIT ?',
                (str(admin_id), agent_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT role, content, action_taken, agent_id, timestamp FROM ai_chat_history '
                'WHERE admin_id = ? ORDER BY timestamp DESC LIMIT ?',
                (str(admin_id), limit)
            ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]
    except Exception as e:
        logger.error(f"Get history error: {e}")
        return []


def clear_history(admin_id, agent_id=None):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        if agent_id:
            conn.execute('DELETE FROM ai_chat_history WHERE admin_id = ? AND agent_id = ?',
                        (str(admin_id), agent_id))
        else:
            conn.execute('DELETE FROM ai_chat_history WHERE admin_id = ?', (str(admin_id),))
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"Clear history error: {e}")


# ═══════════════════════════════════════════════════════════════
#  LEARNING SYSTEM
# ═══════════════════════════════════════════════════════════════

def _phrase_hash(text):
    normalized = re.sub(r'[^\w\s]', '', text.lower().strip())
    normalized = re.sub(r'\s+', ' ', normalized)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:12]


def record_action_outcome(admin_id, agent_id, action_name, params, success, error_msg=None,
                         result_summary=None, user_message=None):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            'INSERT INTO ai_action_outcomes '
            '(admin_id, agent_id, action_name, params, success, error_message, result_summary, user_message) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (str(admin_id), agent_id, action_name, json.dumps(params, ensure_ascii=False),
             1 if success else 0, error_msg, result_summary, user_message)
        )
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
        existing = conn.execute(
            'SELECT id, times_used, times_succeeded, confidence FROM ai_patterns '
            'WHERE phrase_hash = ? AND action_name = ?', (ph, action_name)
        ).fetchone()
        if existing:
            new_used = existing[1] + 1; new_succ = existing[2] + 1
            new_conf = min(0.95, existing[3] + 0.05)
            conn.execute('UPDATE ai_patterns SET times_used=?, times_succeeded=?, confidence=?, '
                        'last_used=CURRENT_TIMESTAMP, params_template=? WHERE id=?',
                        (new_used, new_succ, new_conf, json.dumps(params, ensure_ascii=False), existing[0]))
        else:
            conn.execute('INSERT INTO ai_patterns (phrase_hash, phrase_sample, action_name, agent_id, params_template, confidence) '
                        'VALUES (?, ?, ?, ?, ?, ?)',
                        (ph, phrase[:200], action_name, agent_id, json.dumps(params, ensure_ascii=False), 0.5))
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"Learn pattern error: {e}")


def record_correction(admin_id, agent_id, original_action, original_params, corrected_action,
                     corrected_params, correction_text):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            'INSERT INTO ai_corrections '
            '(admin_id, agent_id, original_action, original_params, corrected_action, corrected_params, correction_text) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (str(admin_id), agent_id, original_action,
             json.dumps(original_params, ensure_ascii=False) if original_params else None,
             corrected_action,
             json.dumps(corrected_params, ensure_ascii=False) if corrected_params else None,
             correction_text)
        )
        conn.commit(); conn.close()
        if correction_text:
            store_knowledge('corrections', f'{original_action}_to_{corrected_action}',
                          correction_text, source='admin_correction', confidence=0.9)
    except Exception as e:
        logger.error(f"Record correction error: {e}")


def store_knowledge(category, fact_key, fact_value, source='learned', confidence=0.5):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        existing = conn.execute('SELECT id FROM ai_knowledge WHERE category=? AND fact_key=?',
                              (category, fact_key)).fetchone()
        if existing:
            conn.execute('UPDATE ai_knowledge SET fact_value=?, confidence=?, times_confirmed=times_confirmed+1, '
                        'last_updated=CURRENT_TIMESTAMP WHERE id=?',
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
            rows = conn.execute('SELECT * FROM ai_patterns WHERE action_name=? AND confidence>=? ORDER BY confidence DESC LIMIT ?',
                              (action_name, min_confidence, limit)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM ai_patterns WHERE confidence>=? ORDER BY confidence DESC LIMIT ?',
                              (min_confidence, limit)).fetchall()
        conn.close(); return [dict(r) for r in rows]
    except: return []


def get_repeated_errors(limit=10):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT action_name, error_message, COUNT(*) as cnt FROM ai_action_outcomes '
                          'WHERE success=0 GROUP BY action_name, error_message ORDER BY cnt DESC LIMIT ?', (limit,)).fetchall()
        conn.close(); return [dict(r) for r in rows]
    except: return []


def get_admin_preferences(admin_id):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT pref_key, pref_value FROM ai_preferences WHERE admin_id=?',
                          (str(admin_id),)).fetchall()
        conn.close(); return {r['pref_key']: r['pref_value'] for r in rows}
    except: return {}


def set_admin_preference(admin_id, key, value, confidence=0.7):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO ai_preferences (admin_id, pref_key, pref_value, confidence, last_used) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)',
                    (str(admin_id), key, value, confidence))
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
        r = conn.execute('SELECT COUNT(*) FROM ai_action_outcomes').fetchone(); stats['total_actions'] = r[0] if r else 0
        r = conn.execute('SELECT COUNT(*) FROM ai_action_outcomes WHERE success=1').fetchone(); stats['successful_actions'] = r[0] if r else 0
        r = conn.execute('SELECT COUNT(*) FROM ai_patterns').fetchone(); stats['learned_patterns'] = r[0] if r else 0
        r = conn.execute('SELECT COUNT(*) FROM ai_knowledge').fetchone(); stats['knowledge_facts'] = r[0] if r else 0
        r = conn.execute('SELECT COUNT(*) FROM ai_corrections').fetchone(); stats['corrections'] = r[0] if r else 0
        r = conn.execute('SELECT COUNT(*) FROM ai_feedback WHERE rating=3').fetchone(); stats['positive_feedback'] = r[0] if r else 0
        r = conn.execute('SELECT COUNT(*) FROM ai_feedback WHERE rating=1').fetchone(); stats['negative_feedback'] = r[0] if r else 0
        rows = conn.execute('SELECT action_name, COUNT(*) as cnt, SUM(success) as succ FROM ai_action_outcomes GROUP BY action_name ORDER BY cnt DESC LIMIT 5').fetchall()
        stats['top_actions'] = [{'action': r[0], 'count': r[1], 'success': r[2]} for r in rows]
        # Per-agent stats
        rows = conn.execute('SELECT agent_id, COUNT(*) as cnt, SUM(success) as succ FROM ai_action_outcomes GROUP BY agent_id ORDER BY cnt DESC').fetchall()
        stats['agent_stats'] = [{'agent': r[0], 'count': r[1], 'success': r[2]} for r in rows]
        conn.close(); return stats
    except: return {}


# ═══════════════════════════════════════════════════════════════
#  ACTIONS
# ═══════════════════════════════════════════════════════════════

ACTIONS_SCHEMA = [
    {"name": "create_post", "description": "إنشاء ونشر بوست", "parameters": {
        "message": "نص البوست", "platform": "telegram|whatsapp", "channel_ids": "معرفات القنوات"}},
    {"name": "broadcast", "description": "بث رسالة جماعية", "parameters": {
        "message": "الرسالة", "target": "all|active|inactive"}},
    {"name": "get_stats", "description": "عرض إحصائيات", "parameters": {"type": "users|transactions|revenue|matching|channels|all"}},
    {"name": "list_channels", "description": "عرض القنوات", "parameters": {}},
    {"name": "list_users", "description": "عرض المستخدمين", "parameters": {"search": "بحث", "limit": "عدد"}},
    {"name": "ban_user", "description": "حظر مستخدم", "parameters": {"user_id": "المستخدم", "reason": "السبب"}},
    {"name": "send_message_to_user", "description": "رسالة مباشرة", "parameters": {"user_id": "المستخدم", "message": "الرسالة"}},
    {"name": "view_transactions", "description": "عرض المعاملات", "parameters": {"status": "الحالة", "type": "النوع", "limit": "عدد"}},
    {"name": "view_matching", "description": "عرض المطابقة", "parameters": {"status": "الحالة", "limit": "عدد"}},
    {"name": "update_setting", "description": "تعديل إعداد", "parameters": {"key": "الإعداد", "value": "القيمة"}},
    {"name": "view_complaints", "description": "عرض الشكاوى", "parameters": {"status": "الحالة", "limit": "عدد"}},
    {"name": "generate_post", "description": "توليد بوست بالذكاء الاصطناعي", "parameters": {"topic": "الموضوع", "content_type": "info|question|prediction|analysis"}},
    {"name": "learn_fact", "description": "حفظ معلومة", "parameters": {"category": "الفئة", "key": "المفتاح", "value": "القيمة"}},
    {"name": "get_learning_stats", "description": "إحصائيات التعلم", "parameters": {}},
    {"name": "delegate_task", "description": "تكليف وكيل آخر بمهام", "parameters": {"to_agent": "الوكيل", "task": "المهمة"}},
    {"name": "consult_all", "description": "استشارة كل الوكلاء", "parameters": {"question": "السؤال"}},
]


def _build_agent_system_prompt(agent_id, admin_id=None):
    agent = get_agent(agent_id)
    actions_desc = json.dumps([a for a in ACTIONS_SCHEMA if a['name'] in agent['actions']], ensure_ascii=False, indent=2)

    learned_parts = []

    patterns = get_learned_patterns(min_confidence=0.4, limit=10)
    if patterns:
        lines = [f"  • \"{p['phrase_sample'][:60]}\" → {p['action_name']} [ثقة: {int(p['confidence']*100)}%]" for p in patterns]
        learned_parts.append("## أنماط مُتعلمة:\n" + '\n'.join(lines))

    knowledge = get_knowledge(limit=10)
    if knowledge:
        lines = [f"  • [{k['category']}] {k['fact_key']}: {k['fact_value'][:80]}" for k in knowledge]
        learned_parts.append("## معلومات عن المشروع:\n" + '\n'.join(lines))

    errors = get_repeated_errors(limit=3)
    if errors:
        lines = [f"  ⚠️ {e['action_name']}: {e['error_message'][:60]} ({e['cnt']} مرة)" for e in errors]
        learned_parts.append("## تجنب هذه الأخطاء:\n" + '\n'.join(lines))

    if admin_id:
        prefs = get_admin_preferences(admin_id)
        if prefs:
            lines = [f"  • {k}: {v}" for k, v in prefs.items()]
            learned_parts.append("## تفضيلات الأدمن:\n" + '\n'.join(lines))

    if admin_id:
        try:
            conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
            corrections = conn.execute('SELECT original_action, corrected_action, correction_text FROM ai_corrections WHERE admin_id=? ORDER BY timestamp DESC LIMIT 3',
                                      (str(admin_id),)).fetchall()
            conn.close()
            if corrections:
                lines = [f"  • {c['original_action']} → {c['corrected_action']}: {c['correction_text'][:60]}" for c in corrections]
                learned_parts.append("## تصحيحات سابقة:\n" + '\n'.join(lines))
        except: pass

    learning_section = '\n\n'.join(learned_parts) if learned_parts else 'لم تتم تعلم أنماط بعد.'

    # Other agents info
    other_agents_info = []
    for oid, oa in AGENTS.items():
        if oid != agent_id:
            other_agents_info.append(f"  • @{oa['name']} ({oa['name_ar']}) — {oa['role_ar']}")
    agents_list = '\n'.join(other_agents_info)

    return f"""أنت {agent['emoji']} {agent['name']} ({agent['name_ar']}) — {agent['role_ar']}.
{agent['description_ar']}

## شخصيتك:
{agent['personality_ar']}

## أنت تملك هذه الأدوات:
{actions_desc}

## فريق الوكلاء المتاحين (يمكنك تكليفهم أو استشارتهم):
{agents_list}

{learning_section}

## قواعد العمل:

1. **التنفيذ**: أرجع JSON عند طلب إجراء:
   {{"action": "اسم", "params": {{...}}, "reply": "رسالة تأكيد"}}

2. **التكليف**: لإرسال مهمة لوكيلاً آخر:
   {{"action": "delegate_task", "params": {{"to_agent": "writer", "task": "اكتب بوست ترحيبي"}}, "reply": "✓ أكلفت الكاتب بكتابة البوست"}}

3. **الاستشارة**: لسؤال كل الوكلاء:
   {{"action": "consult_all", "params": {{"question": "ما رأيكم في..."}}, "reply": "✓ جاري استشارة الفريق"}}

4. **التعلم**: استخدم أنماطك المُتعلمة مباشرة.

5. **تجنب الأخطاء**: راجع الأخطاء المتكررة.

6. **اللغة**: تحدث بنفس لغة الأدمن.

7. **الأمان**: لا تحذف أو تعدّل كبير دون تأكيد.

8. **التنسيق**:
   - <b>نص عريض</b> للعناوين
   - <code>نص</code> للأكواد
   - • للقوائم
"""


# ═══════════════════════════════════════════════════════════════
#  ACTION EXECUTOR
# ═══════════════════════════════════════════════════════════════

def execute_action(action_name, params):
    try:
        dispatch = {
            'create_post': _exec_create_post, 'broadcast': _exec_broadcast,
            'get_stats': _exec_get_stats, 'list_channels': _exec_list_channels,
            'list_users': _exec_list_users, 'ban_user': _exec_ban_user,
            'send_message_to_user': _exec_send_to_user, 'view_transactions': _exec_view_transactions,
            'view_matching': _exec_view_matching, 'update_setting': _exec_update_setting,
            'view_complaints': _exec_view_complaints, 'generate_post': _exec_generate_post,
            'learn_fact': _exec_learn_fact, 'get_learning_stats': _exec_get_learning_stats,
            'delegate_task': _exec_delegate_task, 'consult_all': _exec_consult_all,
        }
        handler = dispatch.get(action_name)
        if handler: return handler(params)
        return {'success': False, 'error': f'Unknown action: {action_name}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _exec_delegate_task(params):
    to_agent = params.get('to_agent', '')
    task = params.get('task', '')
    if not to_agent or not task:
        return {'success': False, 'error': 'to_agent and task required'}
    agent = get_agent(to_agent)
    return {'success': True, 'to_agent': to_agent, 'agent_name': agent['name_ar'],
            'task': task, 'message': f'✓ تمت تكليف {agent["emoji"]} {agent["name_ar"]} بالمهمة'}


def _exec_consult_all(params):
    question = params.get('question', '')
    if not question:
        return {'success': False, 'error': 'question required'}
    return {'success': True, 'question': question,
            'message': '✓ جاري استشارة كل الوكلاء... سيأتي رد كل وكيل على حدة'}


def _exec_create_post(params):
    message = params.get('message', ''); platform = params.get('platform', 'telegram')
    channel_ids = params.get('channel_ids', []); parse_mode = params.get('parse_mode', 'HTML')
    silent = params.get('silent', False); pin = params.get('pin', False)
    posting_method = params.get('posting_method', 'api')
    if not message: return {'success': False, 'error': 'No message provided'}
    channels_path = os.path.join(BASE_DIR, 'bot_channels.csv')
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    targets = []
    if os.path.exists(channels_path):
        with open(channels_path, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if (row.get('platform') or 'telegram').lower() != platform.lower(): continue
                if channel_ids and row.get('chat_id', '') not in channel_ids: continue
                targets.append(row)
    if not targets: return {'success': False, 'error': f'No {platform} channels found'}
    queued = 0
    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['chat_id','message','parse_mode','silent','pin','platform','posting_method','created_at','status'])
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for ch in targets:
            writer.writerow([ch.get('chat_id',''), message, parse_mode, str(silent).lower(), str(pin).lower(), platform, posting_method, now, 'pending'])
            queued += 1
    return {'success': True, 'queued': queued, 'platform': platform, 'channels': [ch.get('name', ch.get('chat_id','')) for ch in targets[:5]]}


def _exec_broadcast(params):
    message = params.get('message', ''); target = params.get('target', 'all')
    if not message: return {'success': False, 'error': 'No message provided'}
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['chat_id','message','parse_mode','silent','pin','platform','posting_method','created_at','status'])
        writer.writerow(['BROADCAST_'+target.upper(), message, 'HTML', 'false', 'false', 'telegram', 'api', now, 'pending'])
    return {'success': True, 'target': target}


def _exec_get_stats(params):
    stat_type = params.get('type', 'all'); result = {}
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        if stat_type in ('users', 'all'):
            try: r = conn.execute('SELECT COUNT(*) as c FROM users').fetchone(); result['total_users'] = r[0] if r else 0
            except: result['total_users'] = 'N/A'
            try:
                week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                r = conn.execute('SELECT COUNT(DISTINCT user_id) as c FROM transactions WHERE created_at > ?', (week_ago,)).fetchone()
                result['active_users_7d'] = r[0] if r else 0
            except: pass
        if stat_type in ('transactions', 'revenue', 'all'):
            try:
                r = conn.execute("SELECT COUNT(*) as c, SUM(CASE WHEN status='approved' THEN amount ELSE 0 END) as total FROM transactions WHERE type='deposit'").fetchone()
                result['total_deposits'] = r[0] if r else 0; result['total_revenue'] = float(r[1] or 0)
            except: result['total_deposits'] = 'N/A'
            try: r = conn.execute("SELECT COUNT(*) as c FROM transactions WHERE status='pending'").fetchone(); result['pending_transactions'] = r[0] if r else 0
            except: pass
        if stat_type in ('matching', 'all'):
            try: r = conn.execute("SELECT COUNT(*) as c FROM match_requests WHERE status='pending'").fetchone(); result['pending_matches'] = r[0] if r else 0
            except: result['pending_matches'] = 'N/A'
        if stat_type in ('channels', 'all'):
            channels_path = os.path.join(BASE_DIR, 'bot_channels.csv')
            if os.path.exists(channels_path):
                with open(channels_path, 'r', encoding='utf-8-sig') as f: channels = list(csv.DictReader(f))
                result['total_channels'] = len(channels)
                result['active_channels'] = len([c for c in channels if (c.get('is_active','') or '').lower() in ('yes','true','1','')])
        conn.close()
    except Exception as e: result['error'] = str(e)
    return {'success': True, 'stats': result}


def _exec_list_channels(params):
    channels_path = os.path.join(BASE_DIR, 'bot_channels.csv')
    if not os.path.exists(channels_path): return {'success': True, 'channels': []}
    with open(channels_path, 'r', encoding='utf-8-sig') as f: channels = list(csv.DictReader(f))
    return {'success': True, 'total': len(channels), 'channels': [{'name': ch.get('name',''), 'chat_id': ch.get('chat_id',''), 'platform': ch.get('platform','telegram'), 'is_active': ch.get('is_active','')} for ch in channels[:20]]}


def _exec_list_users(params):
    search = params.get('search', ''); limit = int(params.get('limit', 10))
    users_path = os.path.join(BASE_DIR, 'users.csv')
    if not os.path.exists(users_path): return {'success': True, 'users': []}
    with open(users_path, 'r', encoding='utf-8-sig') as f: users = list(csv.DictReader(f))
    if search:
        sl = search.lower()
        users = [u for u in users if sl in (u.get('name','') or '').lower() or sl in (u.get('telegram_id','') or '').lower()]
    return {'success': True, 'total': len(users), 'users': [{'telegram_id': u.get('telegram_id',''), 'name': u.get('name',''), 'balance': u.get('balance','0'), 'is_banned': u.get('is_banned','no')} for u in users[:limit]]}


def _exec_ban_user(params):
    user_id = str(params.get('user_id', '')); reason = params.get('reason', 'Banned via AI')
    if not user_id: return {'success': False, 'error': 'No user_id'}
    users_path = os.path.join(BASE_DIR, 'users.csv')
    if not os.path.exists(users_path): return {'success': False, 'error': 'No users file'}
    rows = []; updated = False
    with open(users_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f); fn = reader.fieldnames
        for row in reader:
            if row.get('telegram_id') == user_id: row['is_banned'] = 'yes'; row['ban_reason'] = reason; updated = True
            rows.append(row)
    if not updated: return {'success': False, 'error': f'User {user_id} not found'}
    with open(users_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fn); w.writeheader(); w.writerows(rows)
    return {'success': True, 'user_id': user_id}


def _exec_send_to_user(params):
    user_id = str(params.get('user_id', '')); message = params.get('message', '')
    if not user_id or not message: return {'success': False, 'error': 'user_id and message required'}
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv'); now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists: writer.writerow(['chat_id','message','parse_mode','silent','pin','platform','posting_method','created_at','status'])
        writer.writerow([user_id, message, 'HTML', 'false', 'false', 'telegram', 'api', now, 'pending'])
    return {'success': True, 'user_id': user_id}


def _exec_view_transactions(params):
    status = params.get('status', ''); txn_type = params.get('type', ''); limit = int(params.get('limit', 10))
    txns_path = os.path.join(BASE_DIR, 'transactions.csv')
    if not os.path.exists(txns_path): return {'success': True, 'transactions': []}
    with open(txns_path, 'r', encoding='utf-8-sig') as f: txns = list(csv.DictReader(f))
    if status: txns = [t for t in txns if (t.get('status') or '').lower() == status.lower()]
    if txn_type: txns = [t for t in txns if (t.get('type') or '').lower() == txn_type.lower()]
    txns = sorted(txns, key=lambda x: x.get('created_at', ''), reverse=True)
    return {'success': True, 'total': len(txns), 'transactions': [{'id': t.get('id',''), 'user_id': t.get('user_id',''), 'type': t.get('type',''), 'amount': t.get('amount',''), 'status': t.get('status',''), 'created_at': t.get('created_at','')} for t in txns[:limit]]}


def _exec_view_matching(params):
    status = params.get('status', ''); limit = int(params.get('limit', 10))
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        q = 'SELECT * FROM match_requests'; pl = []
        if status: q += ' WHERE status = ?'; pl.append(status)
        q += ' ORDER BY created_at DESC LIMIT ?'; pl.append(limit)
        rows = conn.execute(q, pl).fetchall(); conn.close()
        return {'success': True, 'total': len(rows), 'requests': [dict(r) for r in rows]}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_update_setting(params):
    key = params.get('key', ''); value = params.get('value', '')
    if not key: return {'success': False, 'error': 'No key'}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
                    (key, value, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit(); conn.close()
        return {'success': True, 'key': key, 'value': value}
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_view_complaints(params):
    status = params.get('status', ''); limit = int(params.get('limit', 10))
    p = os.path.join(BASE_DIR, 'complaints.csv')
    if not os.path.exists(p): return {'success': True, 'complaints': []}
    with open(p, 'r', encoding='utf-8-sig') as f: complaints = list(csv.DictReader(f))
    if status: complaints = [c for c in complaints if (c.get('status') or '').lower() == status.lower()]
    complaints = sorted(complaints, key=lambda x: x.get('created_at', ''), reverse=True)
    return {'success': True, 'total': len(complaints), 'complaints': [{'id': c.get('id',''), 'user_id': c.get('user_id',''), 'subject': c.get('subject',''), 'status': c.get('status','')} for c in complaints[:limit]]}


def _exec_generate_post(params):
    topic = params.get('topic', ''); ct = params.get('content_type', 'info')
    if not topic: return {'success': False, 'error': 'No topic'}
    try:
        from ai_composer import get_active_keys, generate_post
        keys = get_active_keys(DB_PATH)
        if not keys: return {'success': False, 'error': 'No AI keys'}
        return generate_post(keys[0], ct, '', {'company_name': ''}, topic, BASE_DIR)
    except Exception as e: return {'success': False, 'error': str(e)}


def _exec_learn_fact(params):
    cat = params.get('category', 'general'); k = params.get('key', ''); v = params.get('value', '')
    if not k or not v: return {'success': False, 'error': 'key and value required'}
    store_knowledge(cat, k, v, source='ai_self_learned', confidence=0.6)
    return {'success': True}


def _exec_get_learning_stats(params):
    return {'success': True, 'stats': get_learning_stats()}


# ═══════════════════════════════════════════════════════════════
#  CHAT PROCESSOR
# ═══════════════════════════════════════════════════════════════

def process_chat_message(admin_id, user_message, target_agent=None):
    """
    Process a chat message with multi-agent routing.
    target_agent: explicit agent to use, or None for auto-detect.
    """
    # Detect agent
    mentioned_agent, clean_text = find_agent_by_mention(user_message)
    if mentioned_agent:
        agent_id = mentioned_agent
        user_message = clean_text
    elif target_agent:
        agent_id = target_agent
    else:
        agent_id = detect_intent_agent(user_message)

    agent = get_agent(agent_id)

    # Save user message
    msg_id = save_message(admin_id, agent_id, 'user', user_message)

    # Get conversation history for this agent
    history = get_conversation_history(admin_id, agent_id, limit=15)

    # Build system prompt
    system_prompt = _build_agent_system_prompt(agent_id, admin_id)
    messages = [{'role': 'system', 'content': system_prompt}]
    for h in history[:-1]:
        messages.append({'role': h['role'], 'content': h['content']})
    messages.append({'role': 'user', 'content': user_message})

    # Call AI
    ai_result = _call_ai(messages)
    if not ai_result['success']:
        save_message(admin_id, agent_id, 'assistant', f'❌ خطأ: {ai_result["error"]}')
        return {'success': False, 'error': ai_result['error'], 'agent_id': agent_id}

    ai_reply = ai_result['content']

    # Parse and execute action
    action_result = None; action_name = None; parsed = None
    try:
        parsed = _extract_json(ai_reply)
        if parsed and 'action' in parsed:
            action_name = parsed['action']
            params = parsed.get('params', {})

            # Handle delegation
            if action_name == 'delegate_task':
                to_agent = params.get('to_agent', 'commander')
                task = params.get('task', '')
                # Save delegation record
                _init_chat_db()
                try:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute('INSERT INTO ai_task_delegations (admin_id, from_agent, to_agent, task_description) VALUES (?, ?, ?, ?)',
                               (str(admin_id), agent_id, to_agent, task))
                    conn.commit(); conn.close()
                except: pass
                action_result = execute_action(action_name, params)
            # Handle consultation
            elif action_name == 'consult_all':
                question = params.get('question', user_message)
                # Get responses from each agent
                consultations = []
                for oid, oa in AGENTS.items():
                    if oid == agent_id: continue
                    consult_prompt = _build_agent_system_prompt(oid, admin_id)
                    consult_messages = [
                        {'role': 'system', 'content': consult_prompt},
                        {'role': 'user', 'content': f'الأدمن يطلب استشارتك في: {question}\n\nأجب باختصار (3-4 جمل) بما يخص تخصصك فقط.'}
                    ]
                    consult_result = _call_ai(consult_messages)
                    if consult_result.get('success'):
                        consultations.append({
                            'agent_id': oid,
                            'agent_name': oa['name_ar'],
                            'agent_emoji': oa['emoji'],
                            'response': consult_result['content']
                        })
                action_result = {'success': True, 'consultations': consultations, 'question': question}
            else:
                action_result = execute_action(action_name, params)

            if parsed.get('reply'):
                ai_reply = parsed['reply']
    except Exception as e:
        logger.debug(f"No action parsed: {e}")

    # Format response
    response_text = ai_reply
    if action_result and action_result.get('success'):
        if action_name == 'consult_all':
            # Format multi-agent consultation
            consultations = action_result.get('consultations', [])
            lines = [f'💬 <b>استشارة الفريق — {len(consultations)} وكلاء:</b>\n']
            for c in consultations:
                lines.append(f'{c["agent_emoji"]} <b>{c["agent_name"]}:</b>')
                lines.append(f'{c["response"]}\n')
            response_text = '\n'.join(lines)
        elif action_name == 'delegate_task':
            response_text += f'\n\n{action_result.get("message", "")}'
        else:
            response_text += '\n\n' + _format_action_result(action_name, action_result)
    elif action_result and not action_result.get('success'):
        response_text += f'\n\n❌ خطأ: {action_result.get("error", "")}'

    # Save assistant response
    assistant_msg_id = save_message(admin_id, agent_id, 'assistant', response_text, action_taken=action_name)

    # Learning loop
    success = action_result.get('success', False) if action_result else True
    error_msg = action_result.get('error') if action_result and not action_result.get('success') else None
    record_action_outcome(admin_id, agent_id, action_name or 'chat', parsed.get('params', {}) if parsed else {},
                         success, error_msg, str(action_result)[:500] if action_result else None, user_message)
    _detect_preferences(admin_id, user_message)

    return {
        'success': True, 'reply': response_text, 'action_taken': action_name,
        'action_result': action_result, 'message_id': assistant_msg_id,
        'agent_id': agent_id, 'agent_name': agent['name_ar'], 'agent_emoji': agent['emoji'],
        'agent_color': agent['color']
    }


def _detect_preferences(admin_id, message):
    arabic_chars = sum(1 for c in message if '\u0600' <= c <= '\u06FF')
    if arabic_chars > len(message) * 0.3:
        set_admin_preference(admin_id, 'language', 'ar', confidence=0.8)
    elif arabic_chars == 0 and len(message) > 5:
        set_admin_preference(admin_id, 'language', 'en', confidence=0.8)
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
        if not keys: return {'success': False, 'error': 'No AI API keys configured'}
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
        if 'openrouter' in provider: headers['HTTP-Referer'] = 'https://vex.deals'; headers['X-Title'] = 'VEX Admin Assistant'
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
        if not content: return {'success': False, 'error': 'Empty AI response'}
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
        channels = ', '.join(result.get('channels', [])[:3])
        return f"📤 تم الإرسال إلى {result.get('queued', 0)} قناة: {channels}"
    elif action_name == 'broadcast':
        return f"📢 تم وضع الرسالة في قائمة البث ({result.get('target', 'all')})"
    elif action_name == 'get_stats':
        stats = result.get('stats', {})
        lines = ['📊 <b>الإحصائيات:</b>']
        if 'total_users' in stats: lines.append(f"• المستخدمون: <b>{stats['total_users']}</b>")
        if 'total_revenue' in stats: lines.append(f"• الإيرادات: <b>{stats['total_revenue']:.0f}</b>")
        if 'pending_transactions' in stats: lines.append(f"• معلقة: <b>{stats['pending_transactions']}</b>")
        if 'total_channels' in stats: lines.append(f"• القنوات: <b>{stats['total_channels']}</b>")
        if 'pending_matches' in stats: lines.append(f"• مطابقات: <b>{stats['pending_matches']}</b>")
        return '\n'.join(lines)
    elif action_name == 'list_channels':
        channels = result.get('channels', [])
        lines = [f"📋 <b>القنوات ({result.get('total', 0)}):</b>"]
        for ch in channels[:10]:
            s = '🟢' if ch.get('is_active', '').lower() in ('yes', 'true', '1', '') else '🔴'
            lines.append(f"• {s} {ch.get('name', ch.get('chat_id', ''))} ({ch.get('platform', '')})")
        return '\n'.join(lines)
    elif action_name == 'list_users':
        users = result.get('users', [])
        lines = [f"👥 <b>المستخدمون ({result.get('total', 0)}):</b>"]
        for u in users[:10]:
            ban = '🚫' if u.get('is_banned') == 'yes' else ''
            lines.append(f"• {u.get('name', 'N/A')} (<code>{u.get('telegram_id', '')}</code>) {ban}")
        return '\n'.join(lines)
    elif action_name in ('ban_user', 'send_message_to_user', 'update_setting', 'learn_fact'):
        return f"✅ تم التنفيذ بنجاح"
    elif action_name == 'generate_post':
        if result.get('success'): return f"🤖 <b>البوست:</b>\n\n{result.get('text', '')}"
        return f"❌ خطأ: {result.get('error', '')}"
    elif action_name == 'get_learning_stats':
        stats = result.get('stats', {})
        lines = ['🧠 <b>إحصائيات التعلم:</b>',
                 f"• إجراءات: <b>{stats.get('total_actions', 0)}</b> (ناجحة: {stats.get('successful_actions', 0)})",
                 f"• أنماط: <b>{stats.get('learned_patterns', 0)}</b> | معلومات: <b>{stats.get('knowledge_facts', 0)}</b>",
                 f"• تصحيحات: <b>{stats.get('corrections', 0)}</b> | تقييمات: 👍{stats.get('positive_feedback', 0)} 👎{stats.get('negative_feedback', 0)}"]
        return '\n'.join(lines)
    return json.dumps(result, ensure_ascii=False, indent=2)
