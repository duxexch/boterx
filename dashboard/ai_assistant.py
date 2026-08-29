"""
AI Admin Assistant v2 — Self-Learning System
يتعلم من أخطائه ويتطور مع الاستخدام.
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
#  DATABASE INIT — All learning tables
# ═══════════════════════════════════════════════════════════════

def _init_chat_db():
    """Create all AI assistant tables if not exists."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # 1) Chat history
        c.execute('''CREATE TABLE IF NOT EXISTS ai_chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            action_taken TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        # 2) Action outcomes — what happened when we executed an action
        c.execute('''CREATE TABLE IF NOT EXISTS ai_action_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            action_name TEXT NOT NULL,
            params TEXT,
            success INTEGER NOT NULL,
            error_message TEXT,
            result_summary TEXT,
            user_message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        # 3) Learned patterns — phrase → action mapping the AI has learned
        c.execute('''CREATE TABLE IF NOT EXISTS ai_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phrase_hash TEXT NOT NULL,
            phrase_sample TEXT NOT NULL,
            action_name TEXT NOT NULL,
            params_template TEXT,
            confidence REAL DEFAULT 0.5,
            times_used INTEGER DEFAULT 1,
            times_succeeded INTEGER DEFAULT 0,
            last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(phrase_hash, action_name)
        )''')

        # 4) Knowledge base — project-specific facts the AI has learned
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

        # 5) Corrections — admin corrections to AI mistakes
        c.execute('''CREATE TABLE IF NOT EXISTS ai_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            original_action TEXT,
            original_params TEXT,
            corrected_action TEXT,
            corrected_params TEXT,
            correction_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        # 6) Admin preferences — learned defaults per admin
        c.execute('''CREATE TABLE IF NOT EXISTS ai_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            pref_key TEXT NOT NULL,
            pref_value TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(admin_id, pref_key)
        )''')

        # 7) Feedback — thumbs up/down on responses
        c.execute('''CREATE TABLE IF NOT EXISTS ai_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            message_id INTEGER,
            rating INTEGER NOT NULL,
            correction_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        for idx_sql in [
            'CREATE INDEX IF NOT EXISTS idx_chat_admin ON ai_chat_history(admin_id, timestamp)',
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
#  CONVERSATION MEMORY
# ═══════════════════════════════════════════════════════════════

def save_message(admin_id, role, content, action_taken=None):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute(
            'INSERT INTO ai_chat_history (admin_id, role, content, action_taken) VALUES (?, ?, ?, ?)',
            (str(admin_id), role, content, action_taken)
        )
        msg_id = cur.lastrowid
        conn.commit()
        conn.close()
        return msg_id
    except Exception as e:
        logger.error(f"Save message error: {e}")
        return None


def get_conversation_history(admin_id, limit=20):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT role, content, action_taken, timestamp FROM ai_chat_history '
            'WHERE admin_id = ? ORDER BY timestamp DESC LIMIT ?',
            (str(admin_id), limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]
    except Exception as e:
        logger.error(f"Get history error: {e}")
        return []


def clear_history(admin_id):
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM ai_chat_history WHERE admin_id = ?', (str(admin_id),))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Clear history error: {e}")


# ═══════════════════════════════════════════════════════════════
#  LEARNING SYSTEM — Pattern Recognition & Self-Improvement
# ═══════════════════════════════════════════════════════════════

def _phrase_hash(text):
    """Create a normalized hash for phrase matching."""
    normalized = re.sub(r'[^\w\s]', '', text.lower().strip())
    normalized = re.sub(r'\s+', ' ', normalized)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:12]


def record_action_outcome(admin_id, action_name, params, success, error_msg=None,
                         result_summary=None, user_message=None):
    """Log the outcome of an action for learning."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            'INSERT INTO ai_action_outcomes '
            '(admin_id, action_name, params, success, error_message, result_summary, user_message) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (str(admin_id), action_name, json.dumps(params, ensure_ascii=False),
             1 if success else 0, error_msg, result_summary, user_message)
        )
        conn.commit()
        conn.close()

        # Also learn the pattern if successful
        if success and user_message:
            learn_pattern(user_message, action_name, params)
    except Exception as e:
        logger.error(f"Record outcome error: {e}")


def learn_pattern(phrase, action_name, params):
    """Learn a phrase → action pattern from successful interactions."""
    _init_chat_db()
    ph = _phrase_hash(phrase)
    try:
        conn = sqlite3.connect(DB_PATH)
        existing = conn.execute(
            'SELECT id, times_used, times_succeeded, confidence FROM ai_patterns '
            'WHERE phrase_hash = ? AND action_name = ?',
            (ph, action_name)
        ).fetchone()

        if existing:
            new_used = existing[1] + 1
            new_succ = existing[2] + 1
            new_conf = min(0.95, existing[3] + 0.05)
            conn.execute(
                'UPDATE ai_patterns SET times_used=?, times_succeeded=?, confidence=?, '
                'last_used=CURRENT_TIMESTAMP, params_template=? WHERE id=?',
                (new_used, new_succ, new_conf, json.dumps(params, ensure_ascii=False), existing[0])
            )
        else:
            conn.execute(
                'INSERT INTO ai_patterns (phrase_hash, phrase_sample, action_name, params_template, confidence) '
                'VALUES (?, ?, ?, ?, ?)',
                (ph, phrase[:200], action_name, json.dumps(params, ensure_ascii=False), 0.5)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Learn pattern error: {e}")


def record_correction(admin_id, original_action, original_params, corrected_action,
                     corrected_params, correction_text):
    """Record when admin corrects the AI's action."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            'INSERT INTO ai_corrections '
            '(admin_id, original_action, original_params, corrected_action, corrected_params, correction_text) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (str(admin_id), original_action,
             json.dumps(original_params, ensure_ascii=False) if original_params else None,
             corrected_action,
             json.dumps(corrected_params, ensure_ascii=False) if corrected_params else None,
             correction_text)
        )
        conn.commit()
        conn.close()

        # If admin provides a correction, learn from it
        if correction_text:
            store_knowledge('corrections', f'{original_action}_to_{corrected_action}',
                          correction_text, source='admin_correction', confidence=0.9)
    except Exception as e:
        logger.error(f"Record correction error: {e}")


def store_knowledge(category, fact_key, fact_value, source='learned', confidence=0.5):
    """Store a piece of knowledge the AI has learned."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        existing = conn.execute(
            'SELECT id, times_confirmed FROM ai_knowledge WHERE category=? AND fact_key=?',
            (category, fact_key)
        ).fetchone()

        if existing:
            new_conf = min(0.95, confidence + 0.1)
            conn.execute(
                'UPDATE ai_knowledge SET fact_value=?, confidence=?, times_confirmed=times_confirmed+1, '
                'last_updated=CURRENT_TIMESTAMP WHERE id=?',
                (fact_value, new_conf, existing[0])
            )
        else:
            conn.execute(
                'INSERT INTO ai_knowledge (category, fact_key, fact_value, source, confidence) '
                'VALUES (?, ?, ?, ?, ?)',
                (category, fact_key, fact_value, source, confidence)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Store knowledge error: {e}")


def get_knowledge(category=None, limit=50):
    """Retrieve learned knowledge."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        if category:
            rows = conn.execute(
                'SELECT * FROM ai_knowledge WHERE category=? ORDER BY confidence DESC, times_confirmed DESC LIMIT ?',
                (category, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM ai_knowledge ORDER BY confidence DESC, times_confirmed DESC LIMIT ?',
                (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_learned_patterns(action_name=None, min_confidence=0.3, limit=30):
    """Get patterns the AI has learned, sorted by confidence."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        if action_name:
            rows = conn.execute(
                'SELECT * FROM ai_patterns WHERE action_name=? AND confidence>=? '
                'ORDER BY confidence DESC LIMIT ?',
                (action_name, min_confidence, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM ai_patterns WHERE confidence>=? '
                'ORDER BY confidence DESC LIMIT ?',
                (min_confidence, limit)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_repeated_errors(limit=10):
    """Find actions that repeatedly fail — things the AI keeps getting wrong."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT action_name, error_message, COUNT(*) as cnt '
            'FROM ai_action_outcomes WHERE success=0 '
            'GROUP BY action_name, error_message '
            'ORDER BY cnt DESC LIMIT ?',
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_admin_preferences(admin_id):
    """Get learned preferences for an admin."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT pref_key, pref_value, confidence FROM ai_preferences '
            'WHERE admin_id=? ORDER BY confidence DESC',
            (str(admin_id),)
        ).fetchall()
        conn.close()
        return {r['pref_key']: r['pref_value'] for r in rows}
    except Exception:
        return {}


def set_admin_preference(admin_id, key, value, confidence=0.7):
    """Learn/set a preference for an admin."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            'INSERT OR REPLACE INTO ai_preferences (admin_id, pref_key, pref_value, confidence, last_used) '
            'VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)',
            (str(admin_id), key, value, confidence)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Set preference error: {e}")


def record_feedback(admin_id, message_id, rating, correction_text=None):
    """Record admin feedback (1=bad, 2=neutral, 3=good)."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            'INSERT INTO ai_feedback (admin_id, message_id, rating, correction_text) VALUES (?, ?, ?, ?)',
            (str(admin_id), message_id, rating, correction_text)
        )
        conn.commit()
        conn.close()

        # If bad rating, try to find what went wrong and store as correction knowledge
        if rating == 1 and correction_text:
            store_knowledge('negative_feedback', correction_text[:200], correction_text,
                          source='admin_feedback', confidence=0.8)
    except Exception as e:
        logger.error(f"Record feedback error: {e}")


def get_learning_stats():
    """Get stats about what the AI has learned."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        stats = {}

        r = conn.execute('SELECT COUNT(*) FROM ai_action_outcomes').fetchone()
        stats['total_actions'] = r[0] if r else 0

        r = conn.execute('SELECT COUNT(*) FROM ai_action_outcomes WHERE success=1').fetchone()
        stats['successful_actions'] = r[0] if r else 0

        r = conn.execute('SELECT COUNT(*) FROM ai_patterns').fetchone()
        stats['learned_patterns'] = r[0] if r else 0

        r = conn.execute('SELECT COUNT(*) FROM ai_knowledge').fetchone()
        stats['knowledge_facts'] = r[0] if r else 0

        r = conn.execute('SELECT COUNT(*) FROM ai_corrections').fetchone()
        stats['corrections'] = r[0] if r else 0

        r = conn.execute('SELECT COUNT(*) FROM ai_feedback WHERE rating=3').fetchone()
        stats['positive_feedback'] = r[0] if r else 0

        r = conn.execute('SELECT COUNT(*) FROM ai_feedback WHERE rating=1').fetchone()
        stats['negative_feedback'] = r[0] if r else 0

        # Top actions
        rows = conn.execute(
            'SELECT action_name, COUNT(*) as cnt, SUM(success) as succ '
            'FROM ai_action_outcomes GROUP BY action_name ORDER BY cnt DESC LIMIT 5'
        ).fetchall()
        stats['top_actions'] = [{'action': r[0], 'count': r[1], 'success': r[2]} for r in rows]

        conn.close()
        return stats
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
#  ADAPTIVE SYSTEM PROMPT — Evolves with learning
# ═══════════════════════════════════════════════════════════════

ACTIONS_SCHEMA = [
    {"name": "create_post", "description": "إنشاء ونشر بوست في القنوات", "parameters": {
        "message": "نص البوست (HTML)", "platform": "telegram|whatsapp",
        "channel_ids": "معرفات القنوات (اختياري)", "parse_mode": "HTML|Markdown",
        "silent": "true|false", "pin": "true|false", "posting_method": "api|copy|download"}},
    {"name": "broadcast", "description": "بث رسالة جماعية للمستخدمين", "parameters": {
        "message": "نص الرسالة", "target": "all|active|inactive", "platform": "telegram|whatsapp"}},
    {"name": "get_stats", "description": "عرض إحصائيات لوحة التحكم", "parameters": {
        "type": "users|transactions|revenue|matching|channels|all"}},
    {"name": "list_channels", "description": "عرض القنوات المتاحة", "parameters": {}},
    {"name": "list_users", "description": "عرض المستخدمين أو البحث عنهم", "parameters": {
        "search": "بحث (اختياري)", "limit": "عدد (افتراضي: 10)"}},
    {"name": "ban_user", "description": "حظر مستخدم", "parameters": {
        "user_id": "معرف المستخدم", "reason": "سبب الحظر (اختياري)"}},
    {"name": "send_message_to_user", "description": "إرسال رسالة مباشرة لمستخدم", "parameters": {
        "user_id": "المستخدم", "message": "الرسالة"}},
    {"name": "view_transactions", "description": "عرض المعاملات", "parameters": {
        "status": "pending|approved|rejected", "type": "deposit|withdraw", "limit": "عدد"}},
    {"name": "view_matching", "description": "عرض طلبات المطابقة", "parameters": {
        "status": "active|pending|completed|disputed", "limit": "عدد"}},
    {"name": "update_setting", "description": "تعديل إعداد", "parameters": {
        "key": "الإعداد", "value": "القيمة"}},
    {"name": "view_complaints", "description": "عرض الشكاوى", "parameters": {
        "status": "open|closed", "limit": "عدد"}},
    {"name": "generate_post", "description": "توليد بوست بالذكاء الاصطناعي", "parameters": {
        "topic": "الموضوع", "content_type": "info|question|prediction|analysis|live|result"}},
    {"name": "learn_fact", "description": "حفظ معلومة جديدة تعلمها المساعد", "parameters": {
        "category": "الفئة", "key": "المفتاح", "value": "القيمة"}},
    {"name": "get_learning_stats", "description": "عرض إحصائيات تعلم المساعد الذكي", "parameters": {}},
]


def _build_system_prompt(admin_id=None):
    """Build adaptive system prompt that evolves with learning."""
    actions_desc = json.dumps(ACTIONS_SCHEMA, ensure_ascii=False, indent=2)

    # Gather learned knowledge
    learned_parts = []

    # 1) Learned patterns (most confident)
    patterns = get_learned_patterns(min_confidence=0.4, limit=15)
    if patterns:
        pattern_lines = []
        for p in patterns:
            try:
                params_t = json.loads(p['params_template']) if p['params_template'] else {}
                params_str = json.dumps(params_t, ensure_ascii=False)
            except:
                params_str = '{}'
            conf_pct = int(p['confidence'] * 100)
            pattern_lines.append(
                f"  • \"{p['phrase_sample'][:80]}\" → {p['action_name']}({params_str}) "
                f"[ثقة: {conf_pct}%، استُخدم {p['times_used']} مرة]"
            )
        learned_parts.append("## أنماط تعلمها المساعد من تفاعلاتك السابقة:\n" + '\n'.join(pattern_lines))

    # 2) Knowledge base
    knowledge = get_knowledge(limit=20)
    if knowledge:
        k_lines = []
        for k in knowledge:
            k_lines.append(f"  • [{k['category']}] {k['fact_key']}: {k['fact_value'][:100]}")
        learned_parts.append("## معلومات تعلمها المساعد عن المشروع:\n" + '\n'.join(k_lines))

    # 3) Repeated errors — things to avoid
    errors = get_repeated_errors(limit=5)
    if errors:
        e_lines = []
        for e in errors:
            e_lines.append(f"  ⚠️ {e['action_name']}: {e['error_message'][:80]} (حدث {e['cnt']} مرة)")
        learned_parts.append("## أخطاء متكررة — تجنبها:\n" + '\n'.join(e_lines))

    # 4) Admin preferences
    if admin_id:
        prefs = get_admin_preferences(admin_id)
        if prefs:
            p_lines = [f"  • {k}: {v}" for k, v in prefs.items()]
            learned_parts.append("## تفضيلات الأدمن المُتعلمة:\n" + '\n'.join(p_lines))

    # 5) Recent corrections
    if admin_id:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            corrections = conn.execute(
                'SELECT original_action, corrected_action, correction_text FROM ai_corrections '
                'WHERE admin_id=? ORDER BY timestamp DESC LIMIT 5',
                (str(admin_id),)
            ).fetchall()
            conn.close()
            if corrections:
                c_lines = []
                for c in corrections:
                    c_lines.append(f"  • {c['original_action']} → {c['corrected_action']}: {c['correction_text'][:80]}")
                learned_parts.append("## تصحيحات الأدمن الأخيرة:\n" + '\n'.join(c_lines))
        except:
            pass

    # Build the full prompt
    learning_section = '\n\n'.join(learned_parts) if learned_parts else 'لم تتم تعلم أنماط بعد — ابدأ بالتفاعل!'

    return f"""أنت مساعد ذكي متطور لإدارة لوحة تحكم VEX. تتحدث مع الأدمن (المدير).
مهمتك: تنفيذ أوامر الأدمن بذكاء، وتعلم من كل تفاعل لتصبح أذكى مع الوقت.

## أنت تملك هذه الأدوات:

{actions_desc}

## ما تعلمته من تفاعلاتك السابقة:

{learning_section}

## قواعد الذكاء:

1. **التنفيذ**: عند طلب أمر → أرجع JSON:
   {{"action": "اسم", "params": {{...}}, "reply": "رسالة تأكيد"}}

2. **التعلم من الأنماط**: إذا تعرف على نفس طلب الأدمن من أنماط مُتعلمة، استخدم المعاملات المُتعلمة مباشرة بدل طلبها مرة أخرى.

3. **تجنب الأخطاء المتكررة**: راجع قسم "أخطاء متكررة" وتجنب أسبابها.

4. **احترم التفضيلات**: استخدم تفضيلات الأدمن المُتعلمة (اللغة، المنصة، أسلوب الرد).

5. **التعلم من التصحيحات**: إذا صوّب الأدمن خطأك سابقاً، لا تكرره.

6. **حفظ المعرفة**: عندما تتعلم معلومة جديدة عن المشروع، احفظها via learn_fact.

7. **اللغة**: تحدث بنفس لغة الأدمن. إذا تحدث بالعربية → عربية. بالإنجليزية → إنجليزية.

8. **الأمان**: لا تحذف حسابات أو تعدّل إعدادات كبيرة دون تأكيد.

9. **التنسيق**:
   - <b>نص عريض</b> للعناوين
   - <code>نص</code> للأكواد
   - • للقوائم

10. **الإحصائيات**: إذا سأل عن إحصائياتك، استخدم get_learning_stats لعرض تقدمك.

## مثال:
الأدمن: "انشر بوست في القنوات"
المساعد (إذا تعرف على النمط): {{
  "action": "create_post",
  "params": {{"message": "...", "platform": "telegram"}},
  "reply": "✅ جاري النشر..."
}}
"""


# ═══════════════════════════════════════════════════════════════
#  ACTION EXECUTOR
# ═══════════════════════════════════════════════════════════════

def execute_action(action_name, params):
    """Execute an admin action and return result."""
    try:
        dispatch = {
            'create_post': _exec_create_post,
            'broadcast': _exec_broadcast,
            'get_stats': _exec_get_stats,
            'list_channels': _exec_list_channels,
            'list_users': _exec_list_users,
            'ban_user': _exec_ban_user,
            'send_message_to_user': _exec_send_to_user,
            'view_transactions': _exec_view_transactions,
            'view_matching': _exec_view_matching,
            'update_setting': _exec_update_setting,
            'view_complaints': _exec_view_complaints,
            'generate_post': _exec_generate_post,
            'learn_fact': _exec_learn_fact,
            'get_learning_stats': _exec_get_learning_stats,
        }
        handler = dispatch.get(action_name)
        if handler:
            return handler(params)
        return {'success': False, 'error': f'Unknown action: {action_name}'}
    except Exception as e:
        logger.error(f"Execute action error: {e}")
        return {'success': False, 'error': str(e)}


def _exec_create_post(params):
    message = params.get('message', '')
    platform = params.get('platform', 'telegram')
    channel_ids = params.get('channel_ids', [])
    parse_mode = params.get('parse_mode', 'HTML')
    silent = params.get('silent', False)
    pin = params.get('pin', False)
    posting_method = params.get('posting_method', 'api')
    if not message:
        return {'success': False, 'error': 'No message provided'}
    channels_path = os.path.join(BASE_DIR, 'bot_channels.csv')
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    targets = []
    if os.path.exists(channels_path):
        with open(channels_path, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                ch_platform = (row.get('platform') or 'telegram').lower()
                if ch_platform != platform.lower():
                    continue
                ch_id = row.get('chat_id', '')
                if channel_ids and ch_id not in channel_ids:
                    continue
                targets.append(row)
    if not targets:
        return {'success': False, 'error': f'No {platform} channels found'}
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
    return {'success': True, 'queued': queued, 'platform': platform,
            'channels': [ch.get('name', ch.get('chat_id','')) for ch in targets[:5]],
            'message_preview': message[:100] + ('...' if len(message) > 100 else '')}


def _exec_broadcast(params):
    message = params.get('message', '')
    target = params.get('target', 'all')
    if not message:
        return {'success': False, 'error': 'No message provided'}
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['chat_id','message','parse_mode','silent','pin','platform','posting_method','created_at','status'])
        writer.writerow(['BROADCAST_'+target.upper(), message, 'HTML', 'false', 'false', 'telegram', 'api', now, 'pending'])
    return {'success': True, 'target': target, 'message': f'✅ تم وضع الرسالة في قائمة البث ({target})'}


def _exec_get_stats(params):
    stat_type = params.get('type', 'all')
    result = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        if stat_type in ('users', 'all'):
            try:
                r = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()
                result['total_users'] = r[0] if r else 0
            except: result['total_users'] = 'N/A'
            try:
                week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                r = conn.execute('SELECT COUNT(DISTINCT user_id) as c FROM transactions WHERE created_at > ?', (week_ago,)).fetchone()
                result['active_users_7d'] = r[0] if r else 0
            except: pass
        if stat_type in ('transactions', 'revenue', 'all'):
            try:
                r = conn.execute("SELECT COUNT(*) as c, SUM(CASE WHEN status='approved' THEN amount ELSE 0 END) as total FROM transactions WHERE type='deposit'").fetchone()
                result['total_deposits'] = r[0] if r else 0
                result['total_revenue'] = float(r[1] or 0)
            except: result['total_deposits'] = 'N/A'
            try:
                r = conn.execute("SELECT COUNT(*) as c FROM transactions WHERE status='pending'").fetchone()
                result['pending_transactions'] = r[0] if r else 0
            except: pass
        if stat_type in ('matching', 'all'):
            try:
                r = conn.execute("SELECT COUNT(*) as c FROM match_requests WHERE status='pending'").fetchone()
                result['pending_matches'] = r[0] if r else 0
            except: result['pending_matches'] = 'N/A'
            try:
                r = conn.execute("SELECT COUNT(*) as c FROM match_requests WHERE status='completed'").fetchone()
                result['completed_matches'] = r[0] if r else 0
            except: pass
        if stat_type in ('channels', 'all'):
            channels_path = os.path.join(BASE_DIR, 'bot_channels.csv')
            if os.path.exists(channels_path):
                with open(channels_path, 'r', encoding='utf-8-sig') as f:
                    channels = list(csv.DictReader(f))
                result['total_channels'] = len(channels)
                result['active_channels'] = len([c for c in channels if (c.get('is_active','') or '').lower() in ('yes','true','1','')])
        conn.close()
    except Exception as e:
        result['error'] = str(e)
    return {'success': True, 'stats': result}


def _exec_list_channels(params):
    channels_path = os.path.join(BASE_DIR, 'bot_channels.csv')
    if not os.path.exists(channels_path):
        return {'success': True, 'channels': [], 'message': 'No channels file found'}
    with open(channels_path, 'r', encoding='utf-8-sig') as f:
        channels = list(csv.DictReader(f))
    return {'success': True, 'total': len(channels), 'channels': [{
        'name': ch.get('name',''), 'chat_id': ch.get('chat_id',''),
        'platform': ch.get('platform','telegram'), 'is_active': ch.get('is_active',''),
        'type': ch.get('type','')
    } for ch in channels[:20]]}


def _exec_list_users(params):
    search = params.get('search', '')
    limit = int(params.get('limit', 10))
    users_path = os.path.join(BASE_DIR, 'users.csv')
    if not os.path.exists(users_path):
        return {'success': True, 'users': [], 'message': 'No users file found'}
    with open(users_path, 'r', encoding='utf-8-sig') as f:
        users = list(csv.DictReader(f))
    if search:
        sl = search.lower()
        users = [u for u in users if sl in (u.get('name','') or '').lower()
                 or sl in (u.get('telegram_id','') or '').lower()
                 or sl in (u.get('customer_id','') or '').lower()]
    return {'success': True, 'total': len(users), 'shown': min(len(users), limit), 'users': [{
        'telegram_id': u.get('telegram_id',''), 'name': u.get('name',''),
        'customer_id': u.get('customer_id',''), 'currency': u.get('currency',''),
        'balance': u.get('balance','0'), 'is_banned': u.get('is_banned','no')
    } for u in users[:limit]]}


def _exec_ban_user(params):
    user_id = str(params.get('user_id', ''))
    reason = params.get('reason', 'Banned by admin via AI assistant')
    if not user_id:
        return {'success': False, 'error': 'No user_id provided'}
    users_path = os.path.join(BASE_DIR, 'users.csv')
    if not os.path.exists(users_path):
        return {'success': False, 'error': 'Users file not found'}
    rows = []; updated = False
    with open(users_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f); fieldnames = reader.fieldnames
        for row in reader:
            if row.get('telegram_id') == user_id:
                row['is_banned'] = 'yes'; row['ban_reason'] = reason; updated = True
            rows.append(row)
    if not updated:
        return {'success': False, 'error': f'User {user_id} not found'}
    with open(users_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames); writer.writeheader(); writer.writerows(rows)
    return {'success': True, 'user_id': user_id, 'message': f'✅ تم حظر المستخدم {user_id}'}


def _exec_send_to_user(params):
    user_id = str(params.get('user_id', '')); message = params.get('message', '')
    if not user_id or not message:
        return {'success': False, 'error': 'user_id and message required'}
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['chat_id','message','parse_mode','silent','pin','platform','posting_method','created_at','status'])
        writer.writerow([user_id, message, 'HTML', 'false', 'false', 'telegram', 'api', now, 'pending'])
    return {'success': True, 'user_id': user_id, 'message': f'✅ تم وضع الرسالة في قائمة الإرسال للمستخدم {user_id}'}


def _exec_view_transactions(params):
    status = params.get('status', ''); txn_type = params.get('type', ''); limit = int(params.get('limit', 10))
    txns_path = os.path.join(BASE_DIR, 'transactions.csv')
    if not os.path.exists(txns_path):
        return {'success': True, 'transactions': [], 'message': 'No transactions file'}
    with open(txns_path, 'r', encoding='utf-8-sig') as f:
        txns = list(csv.DictReader(f))
    if status: txns = [t for t in txns if (t.get('status') or '').lower() == status.lower()]
    if txn_type: txns = [t for t in txns if (t.get('type') or '').lower() == txn_type.lower()]
    txns = sorted(txns, key=lambda x: x.get('created_at', ''), reverse=True)
    return {'success': True, 'total': len(txns), 'shown': min(len(txns), limit), 'transactions': [{
        'id': t.get('id',''), 'user_id': t.get('user_id',''), 'type': t.get('type',''),
        'amount': t.get('amount',''), 'status': t.get('status',''), 'created_at': t.get('created_at','')
    } for t in txns[:limit]]}


def _exec_view_matching(params):
    status = params.get('status', ''); limit = int(params.get('limit', 10))
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        query = 'SELECT * FROM match_requests'; pl = []
        if status: query += ' WHERE status = ?'; pl.append(status)
        query += ' ORDER BY created_at DESC LIMIT ?'; pl.append(limit)
        rows = conn.execute(query, pl).fetchall(); conn.close()
        return {'success': True, 'total': len(rows), 'requests': [dict(r) for r in rows]}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _exec_update_setting(params):
    key = params.get('key', ''); value = params.get('value', '')
    if not key: return {'success': False, 'error': 'No key provided'}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
                     (key, value, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit(); conn.close()
        return {'success': True, 'key': key, 'value': value, 'message': f'✅ تم تعديل {key} → {value}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _exec_view_complaints(params):
    status = params.get('status', ''); limit = int(params.get('limit', 10))
    complaints_path = os.path.join(BASE_DIR, 'complaints.csv')
    if not os.path.exists(complaints_path):
        return {'success': True, 'complaints': [], 'message': 'No complaints file'}
    with open(complaints_path, 'r', encoding='utf-8-sig') as f:
        complaints = list(csv.DictReader(f))
    if status: complaints = [c for c in complaints if (c.get('status') or '').lower() == status.lower()]
    complaints = sorted(complaints, key=lambda x: x.get('created_at', ''), reverse=True)
    return {'success': True, 'total': len(complaints), 'complaints': [{
        'id': c.get('id',''), 'user_id': c.get('user_id',''), 'subject': c.get('subject',''),
        'status': c.get('status',''), 'created_at': c.get('created_at','')
    } for c in complaints[:limit]]}


def _exec_generate_post(params):
    topic = params.get('topic', ''); content_type = params.get('content_type', 'info')
    if not topic: return {'success': False, 'error': 'No topic provided'}
    try:
        from ai_composer import get_active_keys, generate_post
        keys = get_active_keys(DB_PATH)
        if not keys: return {'success': False, 'error': 'No AI API keys configured'}
        return generate_post(keys[0], content_type, '', {'company_name': ''}, topic, BASE_DIR)
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _exec_learn_fact(params):
    """AI learns a new fact about the project."""
    category = params.get('category', 'general')
    key = params.get('key', '')
    value = params.get('value', '')
    if not key or not value:
        return {'success': False, 'error': 'key and value required'}
    store_knowledge(category, key, value, source='ai_self_learned', confidence=0.6)
    return {'success': True, 'message': f'✅ تم حفظ المعلومة: [{category}] {key} = {value}'}


def _exec_get_learning_stats(params):
    stats = get_learning_stats()
    return {'success': True, 'stats': stats}


# ═══════════════════════════════════════════════════════════════
#  AI CHAT PROCESSOR — Core learning loop
# ═══════════════════════════════════════════════════════════════

def process_chat_message(admin_id, user_message):
    """
    Process a chat message with self-learning loop:
    1. Check for pattern match (fast path)
    2. Build adaptive system prompt with learned knowledge
    3. Call AI
    4. Execute action
    5. Record outcome
    6. Learn from result
    """
    # Save user message
    msg_id = save_message(admin_id, 'user', user_message)

    # Get conversation history
    history = get_conversation_history(admin_id, limit=20)

    # Build adaptive system prompt
    system_prompt = _build_system_prompt(admin_id)
    messages = [{'role': 'system', 'content': system_prompt}]
    for h in history[:-1]:
        messages.append({'role': h['role'], 'content': h['content']})
    messages.append({'role': 'user', 'content': user_message})

    # Call AI
    ai_result = _call_ai(messages)
    if not ai_result['success']:
        save_message(admin_id, 'assistant', f'❌ خطأ: {ai_result["error"]}')
        return {'success': False, 'error': ai_result['error']}

    ai_reply = ai_result['content']

    # Try to parse and execute action
    action_result = None
    action_name = None
    try:
        parsed = _extract_json(ai_reply)
        if parsed and 'action' in parsed:
            action_name = parsed['action']
            params = parsed.get('params', {})
            action_result = execute_action(action_name, params)
            if parsed.get('reply'):
                ai_reply = parsed['reply']
    except Exception as e:
        logger.debug(f"No action parsed: {e}")

    # Format response
    response_text = ai_reply
    if action_result and action_result.get('success'):
        response_text += '\n\n' + _format_action_result(action_name, action_result)
    elif action_result and not action_result.get('success'):
        response_text += f'\n\n❌ خطأ في التنفيذ: {action_result.get("error", "Unknown")}'

    # Save assistant response
    assistant_msg_id = save_message(admin_id, 'assistant', response_text, action_taken=action_name)

    # === LEARNING LOOP ===
    # Record outcome
    success = action_result.get('success', False) if action_result else True
    error_msg = action_result.get('error') if action_result and not action_result.get('success') else None
    record_action_outcome(
        admin_id=admin_id,
        action_name=action_name or 'chat',
        params=parsed.get('params', {}) if parsed else {},
        success=success,
        error_msg=error_msg,
        result_summary=str(action_result)[:500] if action_result else None,
        user_message=user_message
    )

    # Learn user preferences from message patterns
    _detect_preferences(admin_id, user_message)

    return {
        'success': True,
        'reply': response_text,
        'action_taken': action_name,
        'action_result': action_result,
        'message_id': assistant_msg_id
    }


def _detect_preferences(admin_id, message):
    """Detect and learn admin preferences from their messages."""
    msg_lower = message.lower()

    # Detect language preference
    arabic_chars = sum(1 for c in message if '\u0600' <= c <= '\u06FF')
    if arabic_chars > len(message) * 0.3:
        set_admin_preference(admin_id, 'language', 'ar', confidence=0.8)
    elif arabic_chars == 0 and len(message) > 5:
        set_admin_preference(admin_id, 'language', 'en', confidence=0.8)

    # Detect platform preference
    if any(w in msg_lower for w in ['واتساب', 'whatsapp', 'wa']):
        set_admin_preference(admin_id, 'default_platform', 'whatsapp', confidence=0.7)
    elif any(w in msg_lower for w in ['تليجرام', 'telegram', 'tg']):
        set_admin_preference(admin_id, 'default_platform', 'telegram', confidence=0.7)

    # Detect content style preference
    if any(w in msg_lower for w in ['ترحيب', 'welcome', 'افتتاح']):
        set_admin_preference(admin_id, 'preferred_post_type', 'welcome', confidence=0.6)
    elif any(w in msg_lower for w in ['تحليل', 'analysis', 'مباراة']):
        set_admin_preference(admin_id, 'preferred_post_type', 'analysis', confidence=0.6)


# ═══════════════════════════════════════════════════════════════
#  AI API CALL
# ═══════════════════════════════════════════════════════════════

def _call_ai(messages):
    """Call the AI API with messages."""
    try:
        from ai_composer import get_active_keys
        keys = get_active_keys(DB_PATH)
        if not keys:
            return {'success': False, 'error': 'No AI API keys configured'}
        key = keys[0]
        api_key = key.get('api_key', '')
        base_url = (key.get('base_url') or '').rstrip('/')
        model = key.get('default_model', '')
        provider = (key.get('provider') or '').lower()
        timeout = int(key.get('timeout_seconds', 60))
        if not base_url:
            if 'openrouter' in provider: base_url = 'https://openrouter.ai/api/v1'
            elif 'openai' in provider: base_url = 'https://api.openai.com/v1'
            else: base_url = 'https://openrouter.ai/api/v1'
        if not model:
            model = 'openai/gpt-4o-mini' if 'openrouter' in provider else 'gpt-4o-mini'
        url = base_url + '/chat/completions'
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        if 'openrouter' in provider:
            headers['HTTP-Referer'] = 'https://vex.deals'
            headers['X-Title'] = 'VEX Admin Assistant'
        payload = {'model': model, 'messages': messages, 'temperature': 0.4, 'max_tokens': 2048}
        try:
            import httpx
            with httpx.Client(timeout=float(timeout)) as client:
                resp = client.post(url, headers=headers, json=payload)
        except ImportError:
            import urllib.request, ssl
            ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            body = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=body, headers=headers, method='POST')
            resp_raw = urllib.request.urlopen(req, timeout=float(timeout), context=ctx)
            class FakeResp:
                def __init__(self, data, code): self.status_code = code; self._data = data
                def json(self): return json.loads(self._data)
            resp = FakeResp(resp_raw.read().decode(), resp_raw.status)
        if resp.status_code != 200:
            error_detail = ''
            try: error_detail = resp.json().get('error', {}).get('message', str(resp.status_code))
            except: error_detail = str(resp.status_code)
            return {'success': False, 'error': f'AI API error {resp.status_code}: {error_detail}'}
        data = resp.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        if not content:
            return {'success': False, 'error': 'AI returned empty response'}
        return {'success': True, 'content': content}
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return {'success': False, 'error': str(e)}


def _extract_json(text):
    """Extract JSON object from AI response text."""
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
    """Format action result for display."""
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
        if 'pending_transactions' in stats: lines.append(f"• معاملات معلقة: <b>{stats['pending_transactions']}</b>")
        if 'total_channels' in stats: lines.append(f"• القنوات: <b>{stats['total_channels']}</b> (نشطة: {stats.get('active_channels', 0)})")
        if 'pending_matches' in stats: lines.append(f"• مطابقات معلقة: <b>{stats['pending_matches']}</b>")
        return '\n'.join(lines)
    elif action_name == 'list_channels':
        channels = result.get('channels', [])
        lines = [f"📋 <b>القنوات ({result.get('total', 0)}):</b>"]
        for ch in channels[:10]:
            status = '🟢' if ch.get('is_active', '').lower() in ('yes', 'true', '1', '') else '🔴'
            lines.append(f"• {status} {ch.get('name', ch.get('chat_id', ''))} ({ch.get('platform', '')})")
        return '\n'.join(lines)
    elif action_name == 'list_users':
        users = result.get('users', [])
        lines = [f"👥 <b>المستخدمون ({result.get('total', 0)}):</b>"]
        for u in users[:10]:
            ban = '🚫' if u.get('is_banned') == 'yes' else ''
            lines.append(f"• {u.get('name', 'N/A')} (<code>{u.get('telegram_id', '')}</code>) {ban}")
        return '\n'.join(lines)
    elif action_name == 'ban_user':
        return result.get('message', '✅ تم الحظر')
    elif action_name == 'send_message_to_user':
        return result.get('message', '✅ تم الإرسال')
    elif action_name == 'update_setting':
        return result.get('message', '✅ تم التعديل')
    elif action_name == 'generate_post':
        if result.get('success'):
            return f"🤖 <b>البوست المولّد:</b>\n\n{result.get('text', '')}"
        return f"❌ خطأ: {result.get('error', '')}"
    elif action_name == 'learn_fact':
        return result.get('message', '✅ تمت إضافة المعلومة')
    elif action_name == 'get_learning_stats':
        stats = result.get('stats', {})
        lines = ['🧠 <b>إحصائيات التعلم:</b>']
        lines.append(f"• إجراءات مُنفّذة: <b>{stats.get('total_actions', 0)}</b>")
        lines.append(f"• ناجحة: <b>{stats.get('successful_actions', 0)}</b>")
        lines.append(f"• أنماط مُتعلمة: <b>{stats.get('learned_patterns', 0)}</b>")
        lines.append(f"• معلومات محفوظة: <b>{stats.get('knowledge_facts', 0)}</b>")
        lines.append(f"• تصحيحات: <b>{stats.get('corrections', 0)}</b>")
        lines.append(f"• تقييمات إيجابية: <b>{stats.get('positive_feedback', 0)}</b> | سلبية: <b>{stats.get('negative_feedback', 0)}</b>")
        top = stats.get('top_actions', [])
        if top:
            lines.append('\n<b>أكثر الإجراءات استخداماً:</b>')
            for a in top[:5]:
                lines.append(f"  • {a['action']}: {a['count']} مرة (ناجحة: {a['success'] or 0})")
        return '\n'.join(lines)
    return json.dumps(result, ensure_ascii=False, indent=2)
