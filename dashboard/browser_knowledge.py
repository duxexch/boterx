"""
VEX Browser Knowledge Base
Stores learned patterns, selectors, strategies per site.
"""
import json, sqlite3, os, time
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'boterx.db'


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    """Create browser knowledge tables."""
    conn = _get_conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS browser_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_domain TEXT NOT NULL,
                knowledge_type TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                last_used TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(site_domain, knowledge_type, key)
            );

            CREATE TABLE IF NOT EXISTS browser_action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT,
                site_domain TEXT,
                action_type TEXT NOT NULL,
                selector TEXT,
                value TEXT,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                duration_ms INTEGER,
                screenshot_path TEXT,
                page_url TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_success_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_domain TEXT NOT NULL,
                goal TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                avg_duration_ms INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 1.0,
                times_used INTEGER DEFAULT 0,
                last_used TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(site_domain, goal)
            );

            CREATE TABLE IF NOT EXISTS browser_site_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_domain TEXT NOT NULL UNIQUE,
                config_json TEXT NOT NULL DEFAULT '{}',
                notes TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_bk_domain ON browser_knowledge(site_domain);
            CREATE INDEX IF NOT EXISTS idx_bk_type ON browser_knowledge(knowledge_type);
            CREATE INDEX IF NOT EXISTS idx_bal_domain ON browser_action_log(site_domain);
            CREATE INDEX IF NOT EXISTS idx_bal_action ON browser_action_log(action_type);
            CREATE INDEX IF NOT EXISTS idx_bsp_domain ON browser_success_patterns(site_domain);
        ''')
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Knowledge CRUD
# ═══════════════════════════════════════════════════════════════

def learn(domain, ktype, key, value, confidence=0.5):
    """Store a piece of knowledge about a site."""
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO browser_knowledge (site_domain, knowledge_type, key, value, confidence)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(site_domain, knowledge_type, key) DO UPDATE SET
                value=excluded.value,
                confidence=MAX(browser_knowledge.confidence, excluded.confidence),
                success_count=browser_knowledge.success_count+1,
                last_used=datetime('now')
        ''', (domain, ktype, key, value, confidence))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def recall(domain, ktype, key=None):
    """Recall knowledge about a site."""
    conn = _get_conn()
    try:
        if key:
            row = conn.execute(
                'SELECT * FROM browser_knowledge WHERE site_domain=? AND knowledge_type=? AND key=?',
                (domain, ktype, key)
            ).fetchone()
            return dict(row) if row else None
        rows = conn.execute(
            'SELECT * FROM browser_knowledge WHERE site_domain=? AND knowledge_type=? ORDER BY confidence DESC',
            (domain, ktype)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def reinforce(domain, ktype, key, success=True):
    """Reinforce or penalize a knowledge entry."""
    conn = _get_conn()
    try:
        if success:
            conn.execute('''
                UPDATE browser_knowledge SET success_count=success_count+1,
                    confidence=MIN(1.0, confidence+0.05), last_used=datetime('now')
                WHERE site_domain=? AND knowledge_type=? AND key=?
            ''', (domain, ktype, key))
        else:
            conn.execute('''
                UPDATE browser_knowledge SET fail_count=fail_count+1,
                    confidence=MAX(0.0, confidence-0.1), last_used=datetime('now')
                WHERE site_domain=? AND knowledge_type=? AND key=?
            ''', (domain, ktype, key))
        conn.commit()
    finally:
        conn.close()


def forget(domain, ktype=None, min_confidence=0.1):
    """Remove low-confidence or old knowledge."""
    conn = _get_conn()
    try:
        if ktype:
            conn.execute(
                'DELETE FROM browser_knowledge WHERE site_domain=? AND knowledge_type=? AND confidence<?',
                (domain, ktype, min_confidence)
            )
        else:
            conn.execute(
                'DELETE FROM browser_knowledge WHERE site_domain=? AND confidence<?',
                (domain, min_confidence)
            )
        conn.commit()
    finally:
        conn.close()


def list_sites():
    """List all known sites with knowledge counts."""
    conn = _get_conn()
    try:
        rows = conn.execute('''
            SELECT site_domain,
                COUNT(*) as total,
                SUM(CASE WHEN knowledge_type='selector' THEN 1 ELSE 0 END) as selectors,
                SUM(CASE WHEN knowledge_type='login_flow' THEN 1 ELSE 0 END) as login_flows,
                SUM(CASE WHEN knowledge_type='form_pattern' THEN 1 ELSE 0 END) as forms,
                AVG(confidence) as avg_confidence,
                SUM(success_count) as total_success,
                SUM(fail_count) as total_fails
            FROM browser_knowledge
            GROUP BY site_domain
            ORDER BY total DESC
        ''').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_site_knowledge(domain):
    """Get all knowledge for a site."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            'SELECT * FROM browser_knowledge WHERE site_domain=? ORDER BY knowledge_type, confidence DESC',
            (domain,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_knowledge(query, limit=20):
    """Search knowledge by key or value."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            'SELECT * FROM browser_knowledge WHERE key LIKE ? OR value LIKE ? ORDER BY confidence DESC LIMIT ?',
            (f'%{query}%', f'%{query}%', limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Action Log
# ═══════════════════════════════════════════════════════════════

def log_action(instance_id, domain, action_type, selector='', value='',
               success=True, error='', duration_ms=0, screenshot='', page_url=''):
    """Log a browser action for learning."""
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO browser_action_log
            (instance_id, site_domain, action_type, selector, value, success,
             error_message, duration_ms, screenshot_path, page_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (instance_id, domain, action_type, selector, value,
              1 if success else 0, error, duration_ms, screenshot, page_url))
        conn.commit()
    finally:
        conn.close()


def get_action_stats(domain=None, action_type=None, limit=100):
    """Get action statistics."""
    conn = _get_conn()
    try:
        where = []
        params = []
        if domain:
            where.append('site_domain=?')
            params.append(domain)
        if action_type:
            where.append('action_type=?')
            params.append(action_type)
        where_clause = ' AND '.join(where)
        if where_clause:
            where_clause = 'WHERE ' + where_clause

        # Success rate per selector
        rows = conn.execute(f'''
            SELECT selector, action_type,
                COUNT(*) as total,
                SUM(success) as successes,
                ROUND(AVG(success)*100, 1) as success_rate,
                ROUND(AVG(duration_ms), 0) as avg_duration
            FROM browser_action_log {where_clause}
            GROUP BY selector, action_type
            HAVING total >= 2
            ORDER BY success_rate DESC, total DESC
            LIMIT ?
        ''', params + [limit]).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_best_selector(domain, action_type):
    """Get the selector with highest success rate for an action."""
    conn = _get_conn()
    try:
        row = conn.execute('''
            SELECT selector, success_rate, total
            FROM (
                SELECT selector,
                    ROUND(AVG(success)*100, 1) as success_rate,
                    COUNT(*) as total
                FROM browser_action_log
                WHERE site_domain=? AND action_type=? AND selector != ''
                GROUP BY selector
                HAVING total >= 2
            )
            ORDER BY success_rate DESC, total DESC
            LIMIT 1
        ''', (domain, action_type)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_recent_actions(domain=None, limit=50):
    """Get recent actions."""
    conn = _get_conn()
    try:
        if domain:
            rows = conn.execute(
                'SELECT * FROM browser_action_log WHERE site_domain=? ORDER BY created_at DESC LIMIT ?',
                (domain, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM browser_action_log ORDER BY created_at DESC LIMIT ?',
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def clear_action_log(domain=None, days=30):
    """Clear old action logs."""
    conn = _get_conn()
    try:
        if domain:
            conn.execute(
                "DELETE FROM browser_action_log WHERE site_domain=? AND created_at < datetime('now', ?)",
                (domain, f'-{days} days')
            )
        else:
            conn.execute(
                "DELETE FROM browser_action_log WHERE created_at < datetime('now', ?)",
                (f'-{days} days',)
            )
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Success Patterns
# ═══════════════════════════════════════════════════════════════

def save_pattern(domain, goal, steps, avg_duration_ms=0, success_rate=1.0):
    """Save a successful action pattern."""
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO browser_success_patterns (site_domain, goal, steps_json, avg_duration_ms, success_rate)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(site_domain, goal) DO UPDATE SET
                steps_json=excluded.steps_json,
                avg_duration_ms=excluded.avg_duration_ms,
                success_rate=MAX(browser_success_patterns.success_rate, excluded.success_rate),
                times_used=browser_success_patterns.times_used+1,
                last_used=datetime('now')
        ''', (domain, goal, json.dumps(steps, ensure_ascii=False), avg_duration_ms, success_rate))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_pattern(domain, goal):
    """Get a stored pattern."""
    conn = _get_conn()
    try:
        row = conn.execute(
            'SELECT * FROM browser_success_patterns WHERE site_domain=? AND goal=?',
            (domain, goal)
        ).fetchone()
        if row:
            d = dict(row)
            d['steps'] = json.loads(d['steps_json']) if d.get('steps_json') else []
            return d
        return None
    finally:
        conn.close()


def list_patterns(domain=None):
    """List all patterns."""
    conn = _get_conn()
    try:
        if domain:
            rows = conn.execute(
                'SELECT * FROM browser_success_patterns WHERE site_domain=? ORDER BY success_rate DESC',
                (domain,)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM browser_success_patterns ORDER BY times_used DESC'
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['steps'] = json.loads(d['steps_json']) if d.get('steps_json') else []
            result.append(d)
        return result
    finally:
        conn.close()


def use_pattern(domain, goal, success=True):
    """Mark a pattern as used (success or failure)."""
    conn = _get_conn()
    try:
        if success:
            conn.execute('''
                UPDATE browser_success_patterns
                SET times_used=times_used+1,
                    success_rate=MIN(1.0, success_rate+0.05),
                    last_used=datetime('now')
                WHERE site_domain=? AND goal=?
            ''', (domain, goal))
        else:
            conn.execute('''
                UPDATE browser_success_patterns
                SET success_rate=MAX(0.0, success_rate-0.1)
                WHERE site_domain=? AND goal=?
            ''', (domain, goal))
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Site Config
# ═══════════════════════════════════════════════════════════════

def save_site_config(domain, config, notes=''):
    """Save site-specific configuration."""
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO browser_site_config (site_domain, config_json, notes, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(site_domain) DO UPDATE SET
                config_json=excluded.config_json,
                notes=excluded.notes,
                updated_at=datetime('now')
        ''', (domain, json.dumps(config, ensure_ascii=False), notes))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_site_config(domain):
    """Get site configuration."""
    conn = _get_conn()
    try:
        row = conn.execute(
            'SELECT * FROM browser_site_config WHERE site_domain=?', (domain,)
        ).fetchone()
        if row:
            d = dict(row)
            d['config'] = json.loads(d['config_json']) if d.get('config_json') else {}
            return d
        return None
    finally:
        conn.close()


# Initialize on import
init_db()
