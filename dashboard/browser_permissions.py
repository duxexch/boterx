"""
VEX Browser Agent Permissions
Controls what each AI agent can do with the browser.
"""
import json, sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / 'boterx.db'


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    conn = _get_conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS browser_agent_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL UNIQUE,
                can_navigate INTEGER DEFAULT 1,
                can_click INTEGER DEFAULT 1,
                can_type INTEGER DEFAULT 0,
                can_scroll INTEGER DEFAULT 1,
                can_screenshot INTEGER DEFAULT 1,
                can_execute_js INTEGER DEFAULT 0,
                can_fill_forms INTEGER DEFAULT 0,
                can_manage_profiles INTEGER DEFAULT 0,
                can_view_cookies INTEGER DEFAULT 1,
                can_delete_cookies INTEGER DEFAULT 0,
                can_export_cookies INTEGER DEFAULT 0,
                can_network_monitor INTEGER DEFAULT 0,
                can_create_tasks INTEGER DEFAULT 0,
                can_execute_tasks INTEGER DEFAULT 0,
                max_pages_per_session INTEGER DEFAULT 50,
                allowed_domains TEXT DEFAULT '*',
                blocked_domains TEXT DEFAULT '',
                max_session_minutes INTEGER DEFAULT 60,
                auto_sleep INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                task_type TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                cron_expr TEXT DEFAULT '',
                interval_seconds INTEGER DEFAULT 0,
                next_run TEXT,
                last_run TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_network_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT,
                request_url TEXT,
                method TEXT DEFAULT 'GET',
                status_code INTEGER,
                content_type TEXT,
                duration_ms INTEGER,
                size_bytes INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_bnl_instance ON browser_network_log(instance_id);
            CREATE INDEX IF NOT EXISTS idx_bnl_url ON browser_network_log(request_url);
        ''')
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Agent Permissions
# ═══════════════════════════════════════════════════════════════

AGENT_DEFAULTS = {
    'commander': {
        'can_navigate': 1, 'can_click': 1, 'can_type': 1, 'can_scroll': 1,
        'can_screenshot': 1, 'can_execute_js': 1, 'can_fill_forms': 1,
        'can_manage_profiles': 1, 'can_view_cookies': 1, 'can_delete_cookies': 1,
        'can_export_cookies': 1, 'can_network_monitor': 1,
        'can_create_tasks': 1, 'can_execute_tasks': 1,
        'max_pages_per_session': 200, 'allowed_domains': '*',
        'blocked_domains': '', 'max_session_minutes': 120, 'auto_sleep': 1,
    },
    'writer': {
        'can_navigate': 1, 'can_click': 1, 'can_type': 1, 'can_scroll': 1,
        'can_screenshot': 1, 'can_execute_js': 0, 'can_fill_forms': 1,
        'can_manage_profiles': 0, 'can_view_cookies': 1, 'can_delete_cookies': 0,
        'can_export_cookies': 0, 'can_network_monitor': 0,
        'can_create_tasks': 0, 'can_execute_tasks': 1,
        'max_pages_per_session': 30, 'allowed_domains': '*',
        'blocked_domains': '', 'max_session_minutes': 45, 'auto_sleep': 1,
    },
    'analyst': {
        'can_navigate': 1, 'can_click': 1, 'can_type': 0, 'can_scroll': 1,
        'can_screenshot': 1, 'can_execute_js': 1, 'can_fill_forms': 0,
        'can_manage_profiles': 0, 'can_view_cookies': 1, 'can_delete_cookies': 0,
        'can_export_cookies': 0, 'can_network_monitor': 1,
        'can_create_tasks': 0, 'can_execute_tasks': 0,
        'max_pages_per_session': 100, 'allowed_domains': '*',
        'blocked_domains': '', 'max_session_minutes': 60, 'auto_sleep': 1,
    },
    'support': {
        'can_navigate': 1, 'can_click': 1, 'can_type': 0, 'can_scroll': 1,
        'can_screenshot': 1, 'can_execute_js': 0, 'can_fill_forms': 0,
        'can_manage_profiles': 0, 'can_view_cookies': 1, 'can_delete_cookies': 0,
        'can_export_cookies': 0, 'can_network_monitor': 0,
        'can_create_tasks': 0, 'can_execute_tasks': 0,
        'max_pages_per_session': 20, 'allowed_domains': '*',
        'blocked_domains': '', 'max_session_minutes': 30, 'auto_sleep': 1,
    },
    'tech': {
        'can_navigate': 1, 'can_click': 1, 'can_type': 1, 'can_scroll': 1,
        'can_screenshot': 1, 'can_execute_js': 1, 'can_fill_forms': 1,
        'can_manage_profiles': 1, 'can_view_cookies': 1, 'can_delete_cookies': 1,
        'can_export_cookies': 1, 'can_network_monitor': 1,
        'can_create_tasks': 1, 'can_execute_tasks': 1,
        'max_pages_per_session': 500, 'allowed_domains': '*',
        'blocked_domains': '', 'max_session_minutes': 180, 'auto_sleep': 0,
    },
}


def get_agent_permissions(agent_id):
    """Get permissions for an agent. Creates defaults if not exists."""
    conn = _get_conn()
    try:
        row = conn.execute(
            'SELECT * FROM browser_agent_permissions WHERE agent_id=?', (agent_id,)
        ).fetchone()
        if row:
            return dict(row)
        # Create defaults
        defaults = AGENT_DEFAULTS.get(agent_id, AGENT_DEFAULTS['support'])
        cols = ', '.join(defaults.keys())
        vals = ', '.join(['?' for _ in defaults])
        conn.execute(
            f'INSERT INTO browser_agent_permissions (agent_id, {cols}) VALUES (?, {vals})',
            [agent_id] + list(defaults.values())
        )
        conn.commit()
        return {'agent_id': agent_id, **defaults}
    finally:
        conn.close()


def set_agent_permissions(agent_id, permissions):
    """Update agent permissions."""
    conn = _get_conn()
    try:
        existing = get_agent_permissions(agent_id)
        updates = {**existing, **permissions, 'agent_id': agent_id, 'updated_at': datetime.now().isoformat()}
        sets = ', '.join(f'{k}=?' for k in updates if k != 'id')
        vals = list(updates.values())
        conn.execute(
            f'UPDATE browser_agent_permissions SET {sets} WHERE agent_id=?',
            vals + [agent_id]
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def check_permission(agent_id, permission):
    """Check if agent has a specific permission."""
    perms = get_agent_permissions(agent_id)
    return bool(perms.get(permission, False))


def list_agent_permissions():
    """List all agents and their permissions."""
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_agent_permissions ORDER BY agent_id').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Schedules
# ═══════════════════════════════════════════════════════════════

def create_schedule(name, task_type, config, cron_expr='', interval_seconds=0):
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO browser_schedules (name, task_type, config_json, cron_expr, interval_seconds, next_run)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        ''', (name, task_type, json.dumps(config, ensure_ascii=False), cron_expr, interval_seconds))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def list_schedules(active_only=True):
    conn = _get_conn()
    try:
        if active_only:
            rows = conn.execute('SELECT * FROM browser_schedules WHERE is_active=1').fetchall()
        else:
            rows = conn.execute('SELECT * FROM browser_schedules').fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['config'] = json.loads(d.get('config_json', '{}'))
            result.append(d)
        return result
    finally:
        conn.close()


def delete_schedule(schedule_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_schedules WHERE id=?', (schedule_id,))
        conn.commit()
    finally:
        conn.close()


def toggle_schedule(schedule_id, active):
    conn = _get_conn()
    try:
        conn.execute('UPDATE browser_schedules SET is_active=? WHERE id=?', (1 if active else 0, schedule_id))
        conn.commit()
    finally:
        conn.close()


def get_due_schedules():
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM browser_schedules WHERE is_active=1 AND (next_run IS NULL OR next_run <= datetime('now'))"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['config'] = json.loads(d.get('config_json', '{}'))
            result.append(d)
        return result
    finally:
        conn.close()


def mark_schedule_run(schedule_id, interval_seconds=0):
    conn = _get_conn()
    try:
        if interval_seconds > 0:
            conn.execute(
                "UPDATE browser_schedules SET last_run=datetime('now'), next_run=datetime('now', ?) WHERE id=?",
                (f'+{interval_seconds} seconds', schedule_id)
            )
        else:
            conn.execute(
                "UPDATE browser_schedules SET last_run=datetime('now') WHERE id=?", (schedule_id,)
            )
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Network Log
# ═══════════════════════════════════════════════════════════════

def log_network_request(instance_id, url, method='GET', status=200,
                        content_type='', duration_ms=0, size=0):
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO browser_network_log
            (instance_id, request_url, method, status_code, content_type, duration_ms, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (instance_id, url, method, status, content_type, duration_ms, size))
        conn.commit()
    finally:
        conn.close()


def get_network_log(instance_id=None, limit=100):
    conn = _get_conn()
    try:
        if instance_id:
            rows = conn.execute(
                'SELECT * FROM browser_network_log WHERE instance_id=? ORDER BY created_at DESC LIMIT ?',
                (instance_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM browser_network_log ORDER BY created_at DESC LIMIT ?', (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_network_stats(instance_id=None):
    conn = _get_conn()
    try:
        where = 'WHERE instance_id=?' if instance_id else ''
        params = [instance_id] if instance_id else []
        row = conn.execute(f'''
            SELECT COUNT(*) as total,
                SUM(CASE WHEN status_code >= 200 AND status_code < 300 THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as errors,
                ROUND(AVG(duration_ms), 0) as avg_duration,
                SUM(size_bytes) as total_size
            FROM browser_network_log {where}
        ''', params).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


init_db()
