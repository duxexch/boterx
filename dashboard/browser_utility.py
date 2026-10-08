"""
VEX Browser History + Backup/Restore + Clipboard + Dashboard
Complete history tracking, profile backup/restore, clipboard management,
and unified dashboard overview.
"""
import json, sqlite3, shutil, time, zipfile, io, base64
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / 'boterx.db'
PROFILES_DIR = Path(__file__).parent / 'browser_profiles'
BACKUPS_DIR = Path(__file__).parent / 'browser_backups'


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS browser_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT DEFAULT '',
                referrer TEXT DEFAULT '',
                load_time_ms INTEGER DEFAULT 0,
                status_code INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_clipboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT DEFAULT '',
                content TEXT NOT NULL,
                content_type TEXT DEFAULT 'text',
                source TEXT DEFAULT '',
                pinned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                backup_file TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                instance_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_bh_instance ON browser_history(instance_id);
            CREATE INDEX IF NOT EXISTS idx_bh_url ON browser_history(url);
            CREATE INDEX IF NOT EXISTS idx_bh_time ON browser_history(created_at);
            CREATE INDEX IF NOT EXISTS idx_bc_time ON browser_clipboard(created_at);
        ''')
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Browser History
# ═══════════════════════════════════════════════════════════════

def add_history(instance_id, url, title='', referrer='', load_time_ms=0, status_code=200):
    """Record a page visit in history."""
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO browser_history
            (instance_id, url, title, referrer, load_time_ms, status_code)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (instance_id, url[:2000], title[:500], referrer[:2000], load_time_ms, status_code))
        conn.commit()
    finally:
        conn.close()


def get_history(instance_id=None, limit=100, search=''):
    """Get browsing history with optional search."""
    conn = _get_conn()
    try:
        where = []
        params = []
        if instance_id:
            where.append('instance_id=?')
            params.append(instance_id)
        if search:
            where.append('(url LIKE ? OR title LIKE ?)')
            params.extend([f'%{search}%', f'%{search}%'])
        where_clause = 'WHERE ' + ' AND '.join(where) if where else ''
        rows = conn.execute(f'''
            SELECT * FROM browser_history {where_clause}
            ORDER BY created_at DESC LIMIT ?
        ''', params + [limit]).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_history(query, limit=50):
    """Search all history across instances."""
    return get_history(limit=limit, search=query)


def get_frequent_sites(instance_id=None, limit=20):
    """Get most frequently visited sites."""
    conn = _get_conn()
    try:
        where = ''
        params = []
        if instance_id:
            where = 'WHERE instance_id=?'
            params.append(instance_id)
        rows = conn.execute(f'''
            SELECT url, title, COUNT(*) as visits, MAX(created_at) as last_visit
            FROM browser_history {where}
            GROUP BY url
            ORDER BY visits DESC
            LIMIT ?
        ''', params + [limit]).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recent_history(instance_id=None, hours=24, limit=50):
    """Get recent history within N hours."""
    conn = _get_conn()
    try:
        where = ['created_at >= datetime("now", ?)']
        params = [f'-{hours} hours']
        if instance_id:
            where.append('instance_id=?')
            params.append(instance_id)
        where_clause = 'WHERE ' + ' AND '.join(where)
        rows = conn.execute(f'''
            SELECT * FROM browser_history {where_clause}
            ORDER BY created_at DESC LIMIT ?
        ''', params + [limit]).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def clear_history(instance_id=None, older_than_days=None):
    """Clear history optionally for specific instance or older than N days."""
    conn = _get_conn()
    try:
        where = []
        params = []
        if instance_id:
            where.append('instance_id=?')
            params.append(instance_id)
        if older_than_days:
            where.append('created_at < datetime("now", ?)')
            params.append(f'-{older_than_days} days')
        where_clause = 'WHERE ' + ' AND '.join(where) if where else ''
        conn.execute(f'DELETE FROM browser_history {where_clause}', params)
        conn.commit()
    finally:
        conn.close()


def get_history_stats(instance_id=None):
    """Get history statistics."""
    conn = _get_conn()
    try:
        where = ''
        params = []
        if instance_id:
            where = 'WHERE instance_id=?'
            params.append(instance_id)
        row = conn.execute(f'''
            SELECT COUNT(*) as total_pages,
                COUNT(DISTINCT url) as unique_urls,
                COUNT(DISTINCT instance_id) as instances,
                ROUND(AVG(load_time_ms), 0) as avg_load_time,
                MIN(created_at) as first_visit,
                MAX(created_at) as last_visit
            FROM browser_history {where}
        ''', params).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Clipboard Manager
# ═══════════════════════════════════════════════════════════════

def clipboard_add(content, instance_id='', content_type='text', source=''):
    """Add text to clipboard history."""
    conn = _get_conn()
    try:
        cursor = conn.execute('''
            INSERT INTO browser_clipboard (instance_id, content, content_type, source)
            VALUES (?, ?, ?, ?)
        ''', (instance_id, content[:10000], content_type, source))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def clipboard_get(limit=50, search=''):
    """Get clipboard history."""
    conn = _get_conn()
    try:
        where = ''
        params = []
        if search:
            where = 'WHERE content LIKE ?'
            params.append(f'%{search}%')
        rows = conn.execute(f'''
            SELECT * FROM browser_clipboard {where}
            ORDER BY pinned DESC, created_at DESC LIMIT ?
        ''', params + [limit]).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def clipboard_pin(clip_id):
    """Pin/unpin a clipboard entry."""
    conn = _get_conn()
    try:
        row = conn.execute('SELECT pinned FROM browser_clipboard WHERE id=?', (clip_id,)).fetchone()
        if row:
            conn.execute('UPDATE browser_clipboard SET pinned=? WHERE id=?', (0 if row['pinned'] else 1, clip_id))
            conn.commit()
    finally:
        conn.close()


def clipboard_delete(clip_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_clipboard WHERE id=?', (clip_id,))
        conn.commit()
    finally:
        conn.close()


def clipboard_clear():
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_clipboard WHERE pinned=0')
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Backup/Restore
# ═══════════════════════════════════════════════════════════════

def create_backup(name='backup', description='', instance_ids=None):
    """Create a backup of browser profiles and data."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'{name}_{timestamp}'
    backup_path = BACKUPS_DIR / f'{backup_name}.zip'

    try:
        with zipfile.ZipFile(str(backup_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            # Backup DB data
            conn = _get_conn()
            try:
                # Export profiles
                profiles_file = PROFILES_DIR
                if profiles_file.exists():
                    for f in profiles_file.rglob('*'):
                        if f.is_file():
                            zf.write(str(f), f'profiles/{f.relative_to(profiles_file)}')

                # Export DB tables as JSON
                for table in ['browser_cookies', 'browser_sessions', 'browser_history',
                              'browser_clipboard', 'browser_knowledge', 'browser_fingerprints',
                              'browser_groups', 'browser_tags', 'browser_templates']:
                    try:
                        rows = conn.execute(f'SELECT * FROM {table}').fetchall()
                        data = [dict(r) for r in rows]
                        zf.writestr(f'db/{table}.json', json.dumps(data, ensure_ascii=False, indent=2))
                    except Exception:
                        pass

                # Export DB file
                import os
                db_path = str(DB_PATH)
                if os.path.exists(db_path):
                    zf.write(db_path, 'boterx.db')
            finally:
                conn.close()

        file_size = backup_path.stat().st_size

        # Record backup
        conn = _get_conn()
        try:
            cursor = conn.execute('''
                INSERT INTO browser_backups (name, description, backup_file, file_size, instance_count)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, description, str(backup_path), file_size,
                  len(instance_ids) if instance_ids else 0))
            conn.commit()
            return {'id': cursor.lastrowid, 'name': backup_name, 'path': str(backup_path), 'size': file_size}
        finally:
            conn.close()

    except Exception as e:
        return {'error': str(e)}


def list_backups():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_backups ORDER BY created_at DESC').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def restore_backup(backup_id):
    """Restore from a backup."""
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM browser_backups WHERE id=?', (backup_id,)).fetchone()
        if not row:
            return {'error': 'Backup not found'}
        backup_path = Path(row['backup_file'])
        if not backup_path.exists():
            return {'error': 'Backup file not found'}

        with zipfile.ZipFile(str(backup_path), 'r') as zf:
            # Restore DB
            if 'boterx.db' in zf.namelist():
                zf.extract('boterx.db', str(DB_PATH.parent))

            # Restore profiles
            for name in zf.namelist():
                if name.startswith('profiles/'):
                    target = PROFILES_DIR / name[9:]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(str(target), 'wb') as dst:
                        dst.write(src.read())

        return {'success': True, 'restored': row['name']}
    finally:
        conn.close()


def delete_backup(backup_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT backup_file FROM browser_backups WHERE id=?', (backup_id,)).fetchone()
        if row and Path(row['backup_file']).exists():
            Path(row['backup_file']).unlink()
        conn.execute('DELETE FROM browser_backups WHERE id=?', (backup_id,))
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Dashboard Overview
# ═══════════════════════════════════════════════════════════════

def get_dashboard_overview():
    """Get unified dashboard overview of entire browser system."""
    conn = _get_conn()
    try:
        # Instance counts
        instances = conn.execute('SELECT COUNT(*) as c FROM sqlite_master WHERE type="table" AND name LIKE "browser_%"').fetchone()['c']

        # History stats
        hist = get_history_stats()

        # Recent activity
        recent = get_recent_history(hours=24, limit=10)

        # Frequent sites
        frequent = get_frequent_sites(limit=5)

        # Backup count
        backups = conn.execute('SELECT COUNT(*) as c FROM browser_backups').fetchone()['c']

        # Clipboard count
        clips = conn.execute('SELECT COUNT(*) as c FROM browser_clipboard').fetchone()['c']

        # Knowledge entries
        knowledge = conn.execute('SELECT COUNT(*) as c FROM browser_knowledge').fetchone()['c']

        return {
            'history': hist,
            'recent_visits': recent,
            'frequent_sites': frequent,
            'backups_count': backups,
            'clipboard_count': clips,
            'knowledge_entries': knowledge,
            'db_tables': instances,
        }
    finally:
        conn.close()


init_db()
