"""
VEX Browser Cookie Manager + Session Recording + Multi-Tab Support
"""
import json, sqlite3, time, threading, base64
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
            CREATE TABLE IF NOT EXISTS browser_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                session_name TEXT NOT NULL,
                started_at TEXT DEFAULT (datetime('now')),
                ended_at TEXT,
                duration_seconds INTEGER DEFAULT 0,
                pages_visited INTEGER DEFAULT 0,
                actions_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'recording',
                recording_json TEXT DEFAULT '[]',
                cookies_snapshot TEXT DEFAULT '[]',
                localStorage_snapshot TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_tabs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                tab_index INTEGER DEFAULT 0,
                tab_id TEXT,
                title TEXT DEFAULT '',
                url TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_cookies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                name TEXT NOT NULL,
                value TEXT DEFAULT '',
                path TEXT DEFAULT '/',
                expires TEXT DEFAULT '',
                http_only INTEGER DEFAULT 0,
                secure INTEGER DEFAULT 0,
                same_site TEXT DEFAULT 'Lax',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_bc_instance ON browser_cookies(instance_id);
            CREATE INDEX IF NOT EXISTS idx_bs_instance ON browser_sessions(instance_id);
            CREATE INDEX IF NOT EXISTS idx_btab_instance ON browser_tabs(instance_id);
        ''')
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Cookie Manager
# ═══════════════════════════════════════════════════════════════

def save_cookies_from_browser(instance_id, cookies):
    """Save cookies from browser to DB."""
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_cookies WHERE instance_id=?', (instance_id,))
        for c in cookies:
            conn.execute('''
                INSERT INTO browser_cookies
                (instance_id, domain, name, value, path, expires, http_only, secure, same_site)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                instance_id, c.get('domain', ''), c.get('name', ''), c.get('value', ''),
                c.get('path', '/'), c.get('expires', ''), 1 if c.get('httpOnly') else 0,
                1 if c.get('secure') else 0, c.get('sameSite', 'Lax'),
            ))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_cookies(instance_id):
    """Get all cookies for an instance from DB."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            'SELECT * FROM browser_cookies WHERE instance_id=? ORDER BY domain, name', (instance_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_cookie(instance_id, cookie_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_cookies WHERE id=? AND instance_id=?', (cookie_id, instance_id))
        conn.commit()
    finally:
        conn.close()


def delete_all_cookies(instance_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_cookies WHERE instance_id=?', (instance_id,))
        conn.commit()
    finally:
        conn.close()


def import_cookies(instance_id, cookies_json):
    """Import cookies from JSON string."""
    try:
        if isinstance(cookies_json, str):
            cookies = json.loads(cookies_json)
        else:
            cookies = cookies_json
        return save_cookies_from_browser(instance_id, cookies)
    except Exception:
        return False


def export_cookies(instance_id, format='json'):
    """Export cookies in various formats."""
    cookies = get_cookies(instance_id)
    if format == 'json':
        return json.dumps([{
            'domain': c['domain'], 'name': c['name'], 'value': c['value'],
            'path': c['path'], 'httpOnly': bool(c['http_only']),
            'secure': bool(c['secure']), 'sameSite': c['same_site'],
        } for c in cookies], ensure_ascii=False, indent=2)
    elif format == 'netscape':
        lines = ['# Netscape HTTP Cookie File']
        for c in cookies:
            secure = 'TRUE' if c['secure'] else 'FALSE'
            http_only = 'TRUE' if c['http_only'] else 'FALSE'
            expires = c.get('expires', '0')
            if not expires or expires == '':
                expires = '0'
            lines.append(f"{c['domain']}\tTRUE\t{c['path']}\t{secure}\t{expires}\t{c['name']}\t{c['value']}")
        return '\n'.join(lines)
    return json.dumps(cookies, ensure_ascii=False)


def search_cookies(instance_id, query):
    """Search cookies by name or domain."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM browser_cookies WHERE instance_id=? AND (name LIKE ? OR domain LIKE ? OR value LIKE ?)",
            (instance_id, f'%{query}%', f'%{query}%', f'%{query}%')
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Session Recording
# ═══════════════════════════════════════════════════════════════

class SessionRecorder:
    """Records browser sessions for playback."""

    def __init__(self):
        self._active = {}

    def start_recording(self, instance_id, name=''):
        """Start recording a session."""
        conn = _get_conn()
        try:
            cursor = conn.execute('''
                INSERT INTO browser_sessions (instance_id, session_name, status, recording_json)
                VALUES (?, ?, 'recording', '[]')
            ''', (instance_id, name or f'session_{int(time.time())}'))
            conn.commit()
            session_id = cursor.lastrowid
            self._active[instance_id] = session_id
            return session_id
        finally:
            conn.close()

    def record_action(self, instance_id, action, params=None, result=None):
        """Record a single action in the session."""
        sid = self._active.get(instance_id)
        if not sid:
            return
        conn = _get_conn()
        try:
            row = conn.execute('SELECT recording_json FROM browser_sessions WHERE id=?', (sid,)).fetchone()
            if not row:
                return
            actions = json.loads(row['recording_json'] or '[]')
            actions.append({
                'action': action,
                'params': params or {},
                'result': result,
                'timestamp': datetime.now().isoformat(),
            })
            conn.execute('UPDATE browser_sessions SET recording_json=?, actions_count=? WHERE id=?',
                         (json.dumps(actions, ensure_ascii=False), len(actions), sid))
            conn.commit()
        finally:
            conn.close()

    def stop_recording(self, instance_id):
        """Stop recording and save final state."""
        sid = self._active.pop(instance_id, None)
        if not sid:
            return
        conn = _get_conn()
        try:
            conn.execute('''
                UPDATE browser_sessions
                SET status='completed', ended_at=datetime('now'),
                    duration_seconds=CAST((julianday('now') - julianday(started_at)) * 86400 AS INTEGER)
                WHERE id=?
            ''', (sid,))
            conn.commit()
            return sid
        finally:
            conn.close()

    def get_session(self, session_id):
        conn = _get_conn()
        try:
            row = conn.execute('SELECT * FROM browser_sessions WHERE id=?', (session_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d['actions'] = json.loads(d.get('recording_json', '[]'))
            d['cookies'] = json.loads(d.get('cookies_snapshot', '[]'))
            d['localStorage'] = json.loads(d.get('localStorage_snapshot', '{}'))
            return d
        finally:
            conn.close()

    def list_sessions(self, instance_id=None, limit=50):
        conn = _get_conn()
        try:
            if instance_id:
                rows = conn.execute(
                    'SELECT * FROM browser_sessions WHERE instance_id=? ORDER BY created_at DESC LIMIT ?',
                    (instance_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM browser_sessions ORDER BY created_at DESC LIMIT ?', (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_session(self, session_id):
        conn = _get_conn()
        try:
            conn.execute('DELETE FROM browser_sessions WHERE id=?', (session_id,))
            conn.commit()
        finally:
            conn.close()


class SessionPlayer:
    """Plays back recorded sessions."""

    def __init__(self):
        self._playing = {}

    def play_session(self, session_id, instance_id, speed=1.0):
        """Play a recorded session on a browser instance."""
        recorder = SessionRecorder()
        session = recorder.get_session(session_id)
        if not session:
            return {'success': False, 'error': 'Session not found'}

        actions = session.get('actions', [])
        if not actions:
            return {'success': False, 'error': 'No actions recorded'}

        from browser_manager import get_instance
        inst = get_instance(instance_id)
        if not inst or not inst.page:
            return {'success': False, 'error': 'Browser not running'}

        self._playing[instance_id] = {
            'session_id': session_id,
            'started': datetime.now().isoformat(),
            'actions': len(actions),
            'current': 0,
        }

        def _play():
            for i, action in enumerate(actions):
                if instance_id not in self._playing:
                    break
                self._playing[instance_id]['current'] = i
                try:
                    act = action.get('action', '')
                    params = action.get('params', {})

                    if act == 'navigate':
                        inst.navigate(params.get('url', ''))
                    elif act == 'click':
                        inst.click(params.get('selector', ''))
                    elif act == 'type':
                        inst.type_text(params.get('selector', ''), params.get('text', ''))
                    elif act == 'scroll':
                        inst.scroll(params.get('direction', 'down'), params.get('distance', 500))
                    elif act == 'wait':
                        time.sleep(float(params.get('seconds', 1)))
                    elif act == 'read_text':
                        inst.page.inner_text(params.get('selector', 'body'))
                    elif act == 'screenshot':
                        inst.screenshot()

                    time.sleep(float(action.get('delay', 1.0)) / speed)
                except Exception:
                    pass
            self._playing.pop(instance_id, None)

        t = threading.Thread(target=_play, daemon=True)
        t.start()
        return {'success': True, 'actions': len(actions), 'session_id': session_id}

    def stop_playback(self, instance_id):
        self._playing.pop(instance_id, None)
        return True

    def get_status(self, instance_id):
        return self._playing.get(instance_id)


# ═══════════════════════════════════════════════════════════════
#  Multi-Tab Manager
# ═══════════════════════════════════════════════════════════════

class TabManager:
    """Manages multiple tabs per browser instance."""

    def __init__(self):
        self._tabs = {}  # instance_id -> [{id, page, title, url, active}]

    def open_tab(self, instance_id, url='', activate=True):
        """Open a new tab in an instance."""
        from browser_manager import get_instance
        inst = get_instance(instance_id)
        if not inst or not inst.page:
            return {'success': False, 'error': 'Browser not running'}

        try:
            page = inst.context.new_page()
            if url:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)

            tab_id = f'tab_{int(time.time()*1000)}'
            if instance_id not in self._tabs:
                self._tabs[instance_id] = []
            self._tabs[instance_id].append({
                'id': tab_id,
                'page': page,
                'title': page.title() if page else '',
                'url': page.url if page else '',
                'active': activate,
            })

            # Save to DB
            conn = _get_conn()
            try:
                conn.execute('''
                    INSERT INTO browser_tabs (instance_id, tab_index, tab_id, title, url, is_active)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (instance_id, len(self._tabs[instance_id]) - 1, tab_id,
                      page.title() if page else '', page.url if page else '', 1 if activate else 0))
                conn.commit()
            finally:
                conn.close()

            return {'success': True, 'tab_id': tab_id, 'url': page.url if page else ''}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def close_tab(self, instance_id, tab_id):
        """Close a specific tab."""
        tabs = self._tabs.get(instance_id, [])
        for t in tabs:
            if t['id'] == tab_id:
                try:
                    t['page'].close()
                except Exception:
                    pass
                tabs.remove(t)
                conn = _get_conn()
                try:
                    conn.execute('DELETE FROM browser_tabs WHERE instance_id=? AND tab_id=?',
                                 (instance_id, tab_id))
                    conn.commit()
                finally:
                    conn.close()
                return {'success': True}
        return {'success': False, 'error': 'Tab not found'}

    def switch_tab(self, instance_id, tab_id):
        """Switch active tab."""
        tabs = self._tabs.get(instance_id, [])
        for t in tabs:
            t['active'] = (t['id'] == tab_id)
        return {'success': True}

    def list_tabs(self, instance_id):
        """List all tabs for an instance."""
        tabs = self._tabs.get(instance_id, [])
        return [{'id': t['id'], 'title': t.get('title', ''), 'url': t.get('url', ''),
                 'active': t.get('active', False)} for t in tabs]

    def get_active_tab(self, instance_id):
        """Get the currently active tab's page object."""
        tabs = self._tabs.get(instance_id, [])
        for t in tabs:
            if t.get('active'):
                return t['page']
        # Return first tab if none active
        if tabs:
            return tabs[0]['page']
        return None


# Global instances
session_recorder = SessionRecorder()
session_player = SessionPlayer()
tab_manager = TabManager()


init_db()
