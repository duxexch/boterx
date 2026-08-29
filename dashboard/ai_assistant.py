"""
AI Admin Assistant — دردشة ذكية في لوحة الأدمن
يمكنها تنفيذ مهام حقيقية: إنشاء بوستات، بث، إدارة القنوات، إحصائيات، وإدارة المستخدمين.
"""

import json
import sqlite3
import os
import csv
import re
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'boterx.db')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════
#  CONVERSATION MEMORY
# ═══════════════════════════════════════════════════════════════

def _init_chat_db():
    """Create chat_history table if not exists."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''CREATE TABLE IF NOT EXISTS ai_chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            action_taken TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.execute('''CREATE INDEX IF NOT EXISTS idx_chat_admin ON ai_chat_history(admin_id, timestamp)''')
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Chat DB init error: {e}")


def save_message(admin_id, role, content, action_taken=None):
    """Save a chat message to history."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            'INSERT INTO ai_chat_history (admin_id, role, content, action_taken) VALUES (?, ?, ?, ?)',
            (str(admin_id), role, content, action_taken)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Save message error: {e}")


def get_conversation_history(admin_id, limit=20):
    """Get recent conversation history for context."""
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
    """Clear chat history for an admin."""
    _init_chat_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM ai_chat_history WHERE admin_id = ?', (str(admin_id),))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Clear history error: {e}")


# ═══════════════════════════════════════════════════════════════
#  AVAILABLE ACTIONS — What the AI can do
# ═══════════════════════════════════════════════════════════════

ACTIONS_SCHEMA = [
    {
        "name": "create_post",
        "description": "إنشاء ونشر بوست في قنوات تليجرام أو واتساب أو منصات أخرى",
        "parameters": {
            "message": "نص البوست (HTML مدعوم لـ تليجرام)",
            "platform": "telegram|whatsapp|instagram|facebook|twitter (افتراضي: telegram)",
            "channel_ids": "قائمة معرفات القنوات أو أسماؤها (اختياري، إذا فارغ يُنشر في كل القنوات)",
            "parse_mode": "HTML|Markdown|null",
            "silent": "true|false — إرسال بدون تنبيه",
            "pin": "true|false — تثبيت الرسالة",
            "posting_method": "api|copy|download|deeplink"
        }
    },
    {
        "name": "broadcast",
        "description": "بث رسالة جماعية لكل المستخدمين أو فئة محددة",
        "parameters": {
            "message": "نص الرسالة",
            "target": "all|active|inactive|premium — المستخدمون المستهدفون",
            "platform": "telegram|whatsapp (افتراضي: telegram)"
        }
    },
    {
        "name": "get_stats",
        "description": "عرض إحصائيات لوحة التحكم — عدد المستخدمين، المعاملات، الإيرادات",
        "parameters": {
            "type": "users|transactions|revenue|matching|channels|all"
        }
    },
    {
        "name": "list_channels",
        "description": "عرض قائمة القنوات المتاحة وحالتها",
        "parameters": {}
    },
    {
        "name": "list_users",
        "description": "عرض المستخدمين أو البحث عن مستخدم محدد",
        "parameters": {
            "search": "اسم أو معرف المستخدم (اختياري)",
            "limit": "عدد النتائج (افتراضي: 10)"
        }
    },
    {
        "name": "ban_user",
        "description": "حظر مستخدم من البوت",
        "parameters": {
            "user_id": "معرف المستخدم (رقم تليجرام)",
            "reason": "سبب الحظر (اختياري)"
        }
    },
    {
        "name": "send_message_to_user",
        "description": "إرسال رسالة مباشرة لمستخدم محدد عبر البوت",
        "parameters": {
            "user_id": "معرف المستخدم",
            "message": "نص الرسالة"
        }
    },
    {
        "name": "view_transactions",
        "description": "عرض المعاملات الأخيرة أو البحث في سجل المعاملات",
        "parameters": {
            "status": "pending|approved|rejected (اختياري)",
            "type": "deposit|withdraw (اختياري)",
            "limit": "عدد النتائج (افتراضي: 10)"
        }
    },
    {
        "name": "view_matching",
        "description": "عرض طلبات المطابقة النشطة أو المعلقة",
        "parameters": {
            "status": "active|pending|completed|disputed (اختياري)",
            "limit": "عدد النتائج (افتراضي: 10)"
        }
    },
    {
        "name": "update_setting",
        "description": "تعديل إعداد في لوحة التحكم",
        "parameters": {
            "key": "اسم الإعداد",
            "value": "القيمة الجديدة"
        }
    },
    {
        "name": "view_complaints",
        "description": "عرض الشكاوى المفتوحة",
        "parameters": {
            "status": "open|closed (اختياري)",
            "limit": "عدد النتائج (افتراضي: 10)"
        }
    },
    {
        "name": "generate_post",
        "description": "استخدام الذكاء الاصطناعي لتوليد بوست بناءً على وصف أو موضوع",
        "parameters": {
            "topic": "موضوع البوست",
            "content_type": "info|question|prediction|analysis|live|result",
            "platform": "telegram|whatsapp"
        }
    }
]


def _build_system_prompt():
    """Build the system prompt for the AI assistant."""
    actions_desc = json.dumps(ACTIONS_SCHEMA, ensure_ascii=False, indent=2)

    return f"""أنت مساعد ذكي لإدارة لوحة تحكم VEX. أنت تتحدث مع الأدمن (المدير).
بوتبعك أوامر الأدمن ونفّذها داخل لوحة التحكم.

## أنت تملك هذه الأدوات (Actions) لتنفيذ المهام:

{actions_desc}

## قواعد مهمة:

1. **عندما يطلب الأدمن تنفيذ أمر**: استخرج 参数ètres المطلوبة ثم أرجع JSON بالشكل:
   {{"action": "اسم_الإجراء", "params": {{...}}, "reply": "رسالة تأكيد للأدمن"}}

2. **عندما يطلب معلومات**: استخرج الإحصائيات أو البيانات المطلوبة وأعها بشكل واضح ومُنظّم.

3. **عندما يطلب إنشاء بوست**: استخرج النص والمعلومات وتأكد من صحتها قبل التنفيذ.

4. **عندما يسأل سؤال عام أو طلب مساعدة**: أجب بشكل طبيعي ومفيد.

5. **تعلم من المحادثات السابقة**: إذا تكرر طلب الأدمن لنفس الإجراء مع معاملات مختلفة، استخدم هذا المعرف لتسريع التنفيذ.

6. **اللغة**: تحدث بالعربية الفصحى البسيطة. إذا تحدث الأدمن بالإنجليزية، أجب بالإنجليزية.

7. **الأمان**: لا تنفّذ أوامر حذف حسابات أو تعديلات كبيرة دون طلب تأكيد من الأدمن.

8. **التنسيق**: استخدم تنسيق HTML بسيط في الردود:
   - <b>نص عريض</b> للعناوين والأرقام المهمة
   - <code>نص</code> للأكواد والمعرفات
   - • أو - للقوائم

## مثال على التفاعل:

الأدمن: "انشر بوست ترحيبي في كل القنوات"
المساعد:挑明 الاستجابة {{
  "action": "create_post",
  "params": {{"message": "مرحباً بكم في قناتنا! ...", "platform": "telegram"}},
  "reply": "✅ جاري إنشاء البوست الترحيبي ونشره في كل القنوات..."
}}

الأدمن: "كم عدد المستخدمين؟"
المساعد:挑明 الاستجابة {{
  "action": "get_stats",
  "params": {{"type": "users"}},
  "reply": "📊 جاري جلب إحصائيات المستخدمين..."
}}
"""


# ═══════════════════════════════════════════════════════════════
#  ACTION EXECUTOR — Execute real admin tasks
# ═══════════════════════════════════════════════════════════════

def execute_action(action_name, params):
    """Execute an admin action and return result."""
    try:
        if action_name == 'create_post':
            return _exec_create_post(params)
        elif action_name == 'broadcast':
            return _exec_broadcast(params)
        elif action_name == 'get_stats':
            return _exec_get_stats(params)
        elif action_name == 'list_channels':
            return _exec_list_channels(params)
        elif action_name == 'list_users':
            return _exec_list_users(params)
        elif action_name == 'ban_user':
            return _exec_ban_user(params)
        elif action_name == 'send_message_to_user':
            return _exec_send_to_user(params)
        elif action_name == 'view_transactions':
            return _exec_view_transactions(params)
        elif action_name == 'view_matching':
            return _exec_view_matching(params)
        elif action_name == 'update_setting':
            return _exec_update_setting(params)
        elif action_name == 'view_complaints':
            return _exec_view_complaints(params)
        elif action_name == 'generate_post':
            return _exec_generate_post(params)
        else:
            return {'success': False, 'error': f'Unknown action: {action_name}'}
    except Exception as e:
        logger.error(f"Execute action error: {e}")
        return {'success': False, 'error': str(e)}


def _exec_create_post(params):
    """Create and queue a post for broadcasting."""
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

    # Read channels
    targets = []
    if os.path.exists(channels_path):
        with open(channels_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ch_platform = (row.get('platform') or 'telegram').lower()
                if ch_platform != platform.lower():
                    continue
                ch_id = row.get('chat_id', '')
                if channel_ids and ch_id not in channel_ids:
                    continue
                targets.append(row)

    if not targets:
        return {'success': False, 'error': f'No {platform} channels found'}

    # Append to broadcast queue
    queued = 0
    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['chat_id', 'message', 'parse_mode', 'silent', 'pin',
                           'platform', 'posting_method', 'created_at', 'status'])
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for ch in targets:
            writer.writerow([
                ch.get('chat_id', ''),
                message,
                parse_mode,
                str(silent).lower(),
                str(pin).lower(),
                platform,
                posting_method,
                now,
                'pending'
            ])
            queued += 1

    return {
        'success': True,
        'queued': queued,
        'platform': platform,
        'channels': [ch.get('name', ch.get('chat_id', '')) for ch in targets[:5]],
        'message_preview': message[:100] + ('...' if len(message) > 100 else '')
    }


def _exec_broadcast(params):
    """Broadcast message to users via bot."""
    message = params.get('message', '')
    target = params.get('target', 'all')

    if not message:
        return {'success': False, 'error': 'No message provided'}

    # Write to broadcast queue for the bot to pick up
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # For broadcast to users, we create a special broadcast entry
    entry = {
        'type': 'broadcast',
        'message': message,
        'target': target,
        'created_at': now,
        'status': 'pending'
    }

    # Append to broadcast queue
    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['chat_id', 'message', 'parse_mode', 'silent', 'pin',
                           'platform', 'posting_method', 'created_at', 'status'])
        writer.writerow([
            'BROADCAST_' + target.upper(),
            message,
            'HTML',
            'false',
            'false',
            'telegram',
            'api',
            now,
            'pending'
        ])

    return {
        'success': True,
        'target': target,
        'message': f'✅ تم وضع الرسالة في قائمة البث للمستخدمين ({target})'
    }


def _exec_get_stats(params):
    """Get dashboard statistics."""
    stat_type = params.get('type', 'all')
    result = {}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        if stat_type in ('users', 'all'):
            try:
                rows = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()
                result['total_users'] = rows[0] if rows else 0
            except:
                result['total_users'] = 'N/A'

            # Active users (last 7 days)
            try:
                week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                rows = conn.execute(
                    'SELECT COUNT(DISTINCT user_id) as c FROM transactions WHERE created_at > ?',
                    (week_ago,)
                ).fetchone()
                result['active_users_7d'] = rows[0] if rows else 0
            except:
                pass

        if stat_type in ('transactions', 'revenue', 'all'):
            try:
                rows = conn.execute(
                    "SELECT COUNT(*) as c, SUM(CASE WHEN status='approved' THEN amount ELSE 0 END) as total "
                    "FROM transactions WHERE type='deposit'"
                ).fetchone()
                result['total_deposits'] = rows[0] if rows else 0
                result['total_revenue'] = float(rows[1] or 0)
            except:
                result['total_deposits'] = 'N/A'

            try:
                rows = conn.execute(
                    "SELECT COUNT(*) as c FROM transactions WHERE status='pending'"
                ).fetchone()
                result['pending_transactions'] = rows[0] if rows else 0
            except:
                pass

        if stat_type in ('matching', 'all'):
            try:
                rows = conn.execute(
                    "SELECT COUNT(*) as c FROM match_requests WHERE status='pending'"
                ).fetchone()
                result['pending_matches'] = rows[0] if rows else 0
            except:
                result['pending_matches'] = 'N/A'

            try:
                rows = conn.execute(
                    "SELECT COUNT(*) as c FROM match_requests WHERE status='completed'"
                ).fetchone()
                result['completed_matches'] = rows[0] if rows else 0
            except:
                pass

        if stat_type in ('channels', 'all'):
            channels_path = os.path.join(BASE_DIR, 'bot_channels.csv')
            if os.path.exists(channels_path):
                with open(channels_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    channels = list(reader)
                result['total_channels'] = len(channels)
                result['active_channels'] = len([c for c in channels if (c.get('is_active', '') or '').lower() in ('yes', 'true', '1', '')])

        conn.close()
    except Exception as e:
        result['error'] = str(e)

    return {'success': True, 'stats': result}


def _exec_list_channels(params):
    """List available channels."""
    channels_path = os.path.join(BASE_DIR, 'bot_channels.csv')
    if not os.path.exists(channels_path):
        return {'success': True, 'channels': [], 'message': 'No channels file found'}

    with open(channels_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        channels = list(reader)

    return {
        'success': True,
        'total': len(channels),
        'channels': [{
            'name': ch.get('name', ''),
            'chat_id': ch.get('chat_id', ''),
            'platform': ch.get('platform', 'telegram'),
            'is_active': ch.get('is_active', ''),
            'type': ch.get('type', '')
        } for ch in channels[:20]]
    }


def _exec_list_users(params):
    """List users or search for specific users."""
    search = params.get('search', '')
    limit = int(params.get('limit', 10))

    users_path = os.path.join(BASE_DIR, 'users.csv')
    if not os.path.exists(users_path):
        return {'success': True, 'users': [], 'message': 'No users file found'}

    with open(users_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        users = list(reader)

    if search:
        search_lower = search.lower()
        users = [u for u in users if search_lower in (u.get('name', '') or '').lower()
                 or search_lower in (u.get('telegram_id', '') or '').lower()
                 or search_lower in (u.get('customer_id', '') or '').lower()]

    return {
        'success': True,
        'total': len(users),
        'shown': min(len(users), limit),
        'users': [{
            'telegram_id': u.get('telegram_id', ''),
            'name': u.get('name', ''),
            'customer_id': u.get('customer_id', ''),
            'currency': u.get('currency', ''),
            'balance': u.get('balance', '0'),
            'is_banned': u.get('is_banned', 'no')
        } for u in users[:limit]]
    }


def _exec_ban_user(params):
    """Ban a user."""
    user_id = str(params.get('user_id', ''))
    reason = params.get('reason', 'Banned by admin via AI assistant')

    if not user_id:
        return {'success': False, 'error': 'No user_id provided'}

    users_path = os.path.join(BASE_DIR, 'users.csv')
    if not os.path.exists(users_path):
        return {'success': False, 'error': 'Users file not found'}

    rows = []
    updated = False
    with open(users_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row.get('telegram_id') == user_id:
                row['is_banned'] = 'yes'
                row['ban_reason'] = reason
                updated = True
            rows.append(row)

    if not updated:
        return {'success': False, 'error': f'User {user_id} not found'}

    with open(users_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {'success': True, 'user_id': user_id, 'message': f'✅ تم حظر المستخدم {user_id}'}


def _exec_send_to_user(params):
    """Queue a message to send to a user (via broadcast queue)."""
    user_id = str(params.get('user_id', ''))
    message = params.get('message', '')

    if not user_id or not message:
        return {'success': False, 'error': 'user_id and message required'}

    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    file_exists = os.path.exists(queue_path)
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['chat_id', 'message', 'parse_mode', 'silent', 'pin',
                           'platform', 'posting_method', 'created_at', 'status'])
        writer.writerow([
            user_id, message, 'HTML', 'false', 'false',
            'telegram', 'api', now, 'pending'
        ])

    return {'success': True, 'user_id': user_id, 'message': f'✅ تم وضع الرسالة في قائمة الإرسال للمستخدم {user_id}'}


def _exec_view_transactions(params):
    """View recent transactions."""
    status = params.get('status', '')
    txn_type = params.get('type', '')
    limit = int(params.get('limit', 10))

    txns_path = os.path.join(BASE_DIR, 'transactions.csv')
    if not os.path.exists(txns_path):
        return {'success': True, 'transactions': [], 'message': 'No transactions file'}

    with open(txns_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        txns = list(reader)

    if status:
        txns = [t for t in txns if (t.get('status') or '').lower() == status.lower()]
    if txn_type:
        txns = [t for t in txns if (t.get('type') or '').lower() == txn_type.lower()]

    # Most recent first
    txns = sorted(txns, key=lambda x: x.get('created_at', ''), reverse=True)

    return {
        'success': True,
        'total': len(txns),
        'shown': min(len(txns), limit),
        'transactions': [{
            'id': t.get('id', ''),
            'user_id': t.get('user_id', ''),
            'type': t.get('type', ''),
            'amount': t.get('amount', ''),
            'status': t.get('status', ''),
            'created_at': t.get('created_at', '')
        } for t in txns[:limit]]
    }


def _exec_view_matching(params):
    """View matching requests."""
    status = params.get('status', '')
    limit = int(params.get('limit', 10))

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        query = 'SELECT * FROM match_requests'
        params_list = []
        if status:
            query += ' WHERE status = ?'
            params_list.append(status)
        query += ' ORDER BY created_at DESC LIMIT ?'
        params_list.append(limit)

        rows = conn.execute(query, params_list).fetchall()
        conn.close()

        return {
            'success': True,
            'total': len(rows),
            'requests': [dict(r) for r in rows]
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _exec_update_setting(params):
    """Update a setting in the settings table."""
    key = params.get('key', '')
    value = params.get('value', '')

    if not key:
        return {'success': False, 'error': 'No key provided'}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            'INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
            (key, value, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        conn.close()
        return {'success': True, 'key': key, 'value': value, 'message': f'✅ تم تعديل الإعداد {key} → {value}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _exec_view_complaints(params):
    """View complaints."""
    status = params.get('status', '')
    limit = int(params.get('limit', 10))

    complaints_path = os.path.join(BASE_DIR, 'complaints.csv')
    if not os.path.exists(complaints_path):
        return {'success': True, 'complaints': [], 'message': 'No complaints file'}

    with open(complaints_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        complaints = list(reader)

    if status:
        complaints = [c for c in complaints if (c.get('status') or '').lower() == status.lower()]

    complaints = sorted(complaints, key=lambda x: x.get('created_at', ''), reverse=True)

    return {
        'success': True,
        'total': len(complaints),
        'complaints': [{
            'id': c.get('id', ''),
            'user_id': c.get('user_id', ''),
            'subject': c.get('subject', ''),
            'status': c.get('status', ''),
            'created_at': c.get('created_at', '')
        } for c in complaints[:limit]]
    }


def _exec_generate_post(params):
    """Generate a post using AI."""
    topic = params.get('topic', '')
    content_type = params.get('content_type', 'info')
    platform = params.get('platform', 'telegram')

    if not topic:
        return {'success': False, 'error': 'No topic provided'}

    try:
        from ai_composer import get_active_keys, generate_post
        keys = get_active_keys(DB_PATH)
        if not keys:
            return {'success': False, 'error': 'No AI API keys configured'}

        result = generate_post(
            keys[0], content_type, '', {'company_name': ''}, topic, BASE_DIR
        )
        return result
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════
#  AI CHAT PROCESSOR
# ═══════════════════════════════════════════════════════════════

def process_chat_message(admin_id, user_message):
    """
    Process a chat message from the admin.
    1. Get conversation history for context
    2. Call AI with system prompt + history + user message
    3. Parse AI response for actions
    4. Execute any actions
    5. Return response
    """
    # Save user message
    save_message(admin_id, 'user', user_message)

    # Get conversation history
    history = get_conversation_history(admin_id, limit=20)

    # Build messages for AI
    system_prompt = _build_system_prompt()
    messages = [{'role': 'system', 'content': system_prompt}]

    for h in history[:-1]:  # Exclude the just-saved user message
        messages.append({'role': h['role'], 'content': h['content']})

    messages.append({'role': 'user', 'content': user_message})

    # Call AI
    ai_result = _call_ai(messages)
    if not ai_result['success']:
        save_message(admin_id, 'assistant', f'❌ خطأ: {ai_result["error"]}')
        return {'success': False, 'error': ai_result['error']}

    ai_reply = ai_result['content']

    # Try to parse action from AI response
    action_result = None
    action_name = None
    try:
        parsed = _extract_json(ai_reply)
        if parsed and 'action' in parsed:
            action_name = parsed['action']
            params = parsed.get('params', {})
            action_result = execute_action(action_name, params)
            # Use the reply from the parsed JSON if available
            if parsed.get('reply'):
                ai_reply = parsed['reply']
    except Exception as e:
        logger.debug(f"No action parsed: {e}")

    # Format the final response
    response_text = ai_reply
    if action_result and action_result.get('success'):
        response_text += '\n\n' + _format_action_result(action_name, action_result)
    elif action_result and not action_result.get('success'):
        response_text += f'\n\n❌ خطأ في التنفيذ: {action_result.get("error", "Unknown")}'

    # Save assistant response
    save_message(admin_id, 'assistant', response_text, action_taken=action_name)

    return {
        'success': True,
        'reply': response_text,
        'action_taken': action_name,
        'action_result': action_result
    }


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
            if 'openrouter' in provider:
                base_url = 'https://openrouter.ai/api/v1'
            elif 'openai' in provider:
                base_url = 'https://api.openai.com/v1'
            else:
                base_url = 'https://openrouter.ai/api/v1'

        if not model:
            model = 'openai/gpt-4o-mini' if 'openrouter' in provider else 'gpt-4o-mini'

        url = base_url + '/chat/completions'
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        if 'openrouter' in provider:
            headers['HTTP-Referer'] = 'https://vex.deals'
            headers['X-Title'] = 'VEX Admin Assistant'

        payload = {
            'model': model,
            'messages': messages,
            'temperature': 0.4,
            'max_tokens': 2048,
        }

        try:
            import httpx
            with httpx.Client(timeout=float(timeout)) as client:
                resp = client.post(url, headers=headers, json=payload)
        except ImportError:
            import urllib.request, ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            body = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=body, headers=headers, method='POST')
            resp_raw = urllib.request.urlopen(req, timeout=float(timeout), context=ctx)
            # Convert to compatible object
            class FakeResp:
                def __init__(self, data, code):
                    self.status_code = code
                    self._data = data
                def json(self): return json.loads(self._data)
            resp = FakeResp(resp_raw.read().decode(), resp_raw.status)

        if resp.status_code != 200:
            error_detail = ''
            try:
                error_detail = resp.json().get('error', {}).get('message', str(resp.status_code))
            except:
                error_detail = str(resp.status_code)
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
    # Try to find JSON in code blocks
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass

    # Try to find JSON directly
    match = re.search(r'\{[^{}]*"action"\s*:\s*"[^"]*"[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass

    # Try broader JSON extraction
    brace_start = text.find('{')
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == '{': depth += 1
            elif text[i] == '}': depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[brace_start:i+1])
                except:
                    break

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
        if 'total_users' in stats:
            lines.append(f"• المستخدمون: <b>{stats['total_users']}</b>")
        if 'total_revenue' in stats:
            lines.append(f"• الإيرادات: <b>{stats['total_revenue']:.0f}</b>")
        if 'pending_transactions' in stats:
            lines.append(f"• معاملات معلقة: <b>{stats['pending_transactions']}</b>")
        if 'total_channels' in stats:
            lines.append(f"• القنوات: <b>{stats['total_channels']}</b> (نشطة: {stats.get('active_channels', 0)})")
        if 'pending_matches' in stats:
            lines.append(f"• مطابقات معلقة: <b>{stats['pending_matches']}</b>")
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

    return json.dumps(result, ensure_ascii=False, indent=2)
