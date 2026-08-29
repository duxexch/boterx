"""
VEX Browser File Operations + Mobile Emulation + Task Queue + Enhanced Gallery
File upload/download, responsive testing, sequential task execution, and gallery management.
"""
import json, sqlite3, time, threading, os, shutil
from pathlib import Path
from datetime import datetime
from collections import deque

DB_PATH = Path(__file__).parent.parent / 'boterx.db'
UPLOADS_DIR = Path(__file__).parent / 'browser_uploads'
DOWNLOADS_DIR = Path(__file__).parent / 'browser_downloads'


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS browser_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                url TEXT NOT NULL,
                filename TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                mime_type TEXT DEFAULT '',
                status TEXT DEFAULT 'downloading',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_task_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tasks_json TEXT NOT NULL DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                current_index INTEGER DEFAULT 0,
                result_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now')),
                started_at TEXT,
                completed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_bd_instance ON browser_downloads(instance_id);
        ''')
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  File Upload/Download
# ═══════════════════════════════════════════════════════════════

def upload_file(instance_id, file_path, selector='input[type="file"]'):
    """Upload a file to a file input on the page."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    if not Path(file_path).exists():
        return {'success': False, 'error': 'File not found'}

    try:
        file_input = inst.page.query_selector(selector)
        if not file_input:
            return {'success': False, 'error': 'File input not found'}
        file_input.set_input_files(file_path)
        return {'success': True, 'file': Path(file_path).name, 'size': Path(file_path).stat().st_size}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def upload_files(instance_id, file_paths, selector='input[type="file"]'):
    """Upload multiple files to a file input."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    existing = [p for p in file_paths if Path(p).exists()]
    if not existing:
        return {'success': False, 'error': 'No valid files found'}

    try:
        file_input = inst.page.query_selector(selector)
        if not file_input:
            return {'success': False, 'error': 'File input not found'}
        file_input.set_input_files(existing)
        return {'success': True, 'files': [Path(p).name for p in existing], 'count': len(existing)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def setup_download_handler(instance_id):
    """Set up download event handler for an instance."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    downloads = []

    def on_download(download):
        try:
            filename = download.suggested_filename or f'download_{int(time.time())}'
            save_path = str(DOWNLOADS_DIR / filename)
            download.save_as(save_path)
            file_size = Path(save_path).stat().st_size if Path(save_path).exists() else 0

            # Record in DB
            conn = _get_conn()
            try:
                conn.execute('''
                    INSERT INTO browser_downloads (instance_id, url, filename, file_path, file_size, mime_type, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'completed')
                ''', (instance_id, download.url, filename, save_path, file_size, download.url.split('.')[-1]))
                conn.commit()
            finally:
                conn.close()

            downloads.append({'filename': filename, 'path': save_path, 'size': file_size, 'url': download.url})
        except Exception:
            pass

    inst.page.on('download', on_download)
    return {'success': True, 'message': 'Download handler active'}


def list_downloads(instance_id=None, limit=50):
    """List downloaded files."""
    conn = _get_conn()
    try:
        if instance_id:
            rows = conn.execute(
                'SELECT * FROM browser_downloads WHERE instance_id=? ORDER BY created_at DESC LIMIT ?',
                (instance_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM browser_downloads ORDER BY created_at DESC LIMIT ?', (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_download(download_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT file_path FROM browser_downloads WHERE id=?', (download_id,)).fetchone()
        if row and Path(row['file_path']).exists():
            Path(row['file_path']).unlink()
        conn.execute('DELETE FROM browser_downloads WHERE id=?', (download_id,))
        conn.commit()
    finally:
        conn.close()


def get_upload_dir():
    """Get the uploads directory path for user to place files."""
    return str(UPLOADS_DIR)


def list_upload_files():
    """List files available in uploads directory."""
    files = []
    for f in UPLOADS_DIR.iterdir():
        if f.is_file():
            files.append({
                'name': f.name,
                'path': str(f),
                'size': f.stat().st_size,
                'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return sorted(files, key=lambda x: x['modified'], reverse=True)


# ═══════════════════════════════════════════════════════════════
#  Mobile Emulation + Responsive Testing
# ═══════════════════════════════════════════════════════════════

DEVICE_PRESETS = {
    'iphone_15': {
        'name': 'iPhone 15',
        'viewport': {'width': 393, 'height': 852},
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
        'locale': 'en-US',
        'timezone': 'America/New_York',
        'geolocation': {'latitude': 40.7128, 'longitude': -74.0060},
        'permissions': ['geolocation'],
    },
    'iphone_15_pro': {
        'name': 'iPhone 15 Pro',
        'viewport': {'width': 393, 'height': 852},
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
        'locale': 'en-US',
        'timezone': 'America/New_York',
    },
    'iphone_se': {
        'name': 'iPhone SE',
        'viewport': {'width': 375, 'height': 667},
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
    },
    'ipad_pro': {
        'name': 'iPad Pro 12.9"',
        'viewport': {'width': 1024, 'height': 1366},
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
        'user_agent': 'Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
    },
    'samsung_s24': {
        'name': 'Samsung Galaxy S24',
        'viewport': {'width': 360, 'height': 780},
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
        'user_agent': 'Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36',
    },
    'samsung_tab': {
        'name': 'Samsung Galaxy Tab S9',
        'viewport': {'width': 800, 'height': 1280},
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
        'user_agent': 'Mozilla/5.0 (Linux; Android 14; SM-X810) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    },
    'pixel_8': {
        'name': 'Google Pixel 8',
        'viewport': {'width': 412, 'height': 915},
        'device_scale_factor': 2.625,
        'is_mobile': True,
        'has_touch': True,
        'user_agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36',
    },
    'desktop_1080': {
        'name': 'Desktop 1080p',
        'viewport': {'width': 1920, 'height': 1080},
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },
    'desktop_1440': {
        'name': 'Desktop 1440p',
        'viewport': {'width': 2560, 'height': 1440},
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },
    'laptop_13': {
        'name': 'Laptop 13"',
        'viewport': {'width': 1280, 'height': 800},
        'device_scale_factor': 2,
        'is_mobile': False,
        'has_touch': False,
    },
}


def get_device_presets():
    """Get all available device presets."""
    return {k: {**v, 'id': k} for k, v in DEVICE_PRESETS.items()}


def apply_device_preset(instance_id, device_name):
    """Apply a device preset to an instance."""
    preset = DEVICE_PRESETS.get(device_name)
    if not preset:
        return {'success': False, 'error': f'Device preset "{device_name}" not found'}

    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        vp = preset['viewport']
        inst.page.set_viewport_size({'width': vp['width'], 'height': vp['height']})

        # Apply user agent if mobile
        if preset.get('user_agent'):
            inst.context.route('**/*', lambda route: route.continue_(
                headers={**route.request.headers, 'User-Agent': preset['user_agent']}
            ))

        return {
            'success': True,
            'device': preset['name'],
            'viewport': vp,
            'is_mobile': preset.get('is_mobile', False),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def responsive_test(instance_id, url, devices=None):
    """Run responsive test across multiple devices."""
    if devices is None:
        devices = ['iphone_15', 'samsung_s24', 'ipad_pro', 'desktop_1080']

    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    results = []
    for device_name in devices:
        preset = DEVICE_PRESETS.get(device_name)
        if not preset:
            continue
        try:
            vp = preset['viewport']
            inst.page.set_viewport_size({'width': vp['width'], 'height': vp['height']})
            if url:
                inst.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(1)
            screenshot = inst.page.screenshot(full_page=False)
            results.append({
                'device': preset['name'],
                'viewport': vp,
                'screenshot_size': len(screenshot),
                'url': inst.page.url,
            })
        except Exception:
            results.append({'device': preset['name'], 'viewport': vp, 'error': 'Failed'})

    return {'success': True, 'results': results}


# ═══════════════════════════════════════════════════════════════
#  Task Queue System
# ═══════════════════════════════════════════════════════════════

class TaskQueue:
    """Manages sequential execution of browser tasks."""

    def __init__(self):
        self._running = {}
        self._lock = threading.Lock()

    def create_queue(self, name, tasks):
        """Create a new task queue."""
        conn = _get_conn()
        try:
            cursor = conn.execute('''
                INSERT INTO browser_task_queue (name, tasks_json, status)
                VALUES (?, ?, 'pending')
            ''', (name, json.dumps(tasks, ensure_ascii=False)))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def start_queue(self, queue_id, instance_id):
        """Start executing a task queue."""
        conn = _get_conn()
        try:
            row = conn.execute('SELECT * FROM browser_task_queue WHERE id=?', (queue_id,)).fetchone()
            if not row:
                return {'success': False, 'error': 'Queue not found'}
            tasks = json.loads(row['tasks_json'])
            conn.execute('''
                UPDATE browser_task_queue SET status='running', started_at=datetime('now') WHERE id=?
            ''', (queue_id,))
            conn.commit()
        finally:
            conn.close()

        def _execute():
            from browser_manager import get_instance
            inst = get_instance(instance_id)
            if not inst or not inst.page:
                self._update_status(queue_id, 'failed', 'Browser not running')
                return

            results = []
            for i, task in enumerate(tasks):
                try:
                    action = task.get('action', '')
                    params = task.get('params', {})

                    if action == 'navigate':
                        inst.navigate(params.get('url', ''))
                        result = {'success': True}
                    elif action == 'click':
                        inst.click(params.get('selector', ''))
                        result = {'success': True}
                    elif action == 'type':
                        inst.type_text(params.get('selector', ''), params.get('text', ''))
                        result = {'success': True}
                    elif action == 'scroll':
                        inst.scroll(params.get('direction', 'down'), params.get('distance', 500))
                        result = {'success': True}
                    elif action == 'wait':
                        time.sleep(float(params.get('seconds', 1)))
                        result = {'success': True}
                    elif action == 'screenshot':
                        path = inst.screenshot()
                        result = {'success': True, 'path': path}
                    elif action == 'read_text':
                        text = inst.page.inner_text(params.get('selector', 'body'))
                        result = {'success': True, 'text': text[:2000]}
                    elif action == 'evaluate':
                        value = inst.page.evaluate(params.get('script', ''))
                        result = {'success': True, 'value': str(value)[:2000]}
                    else:
                        result = {'success': False, 'error': f'Unknown action: {action}'}

                    results.append({'index': i, 'action': action, 'result': result})

                    # Update progress
                    self._update_progress(queue_id, i + 1, results)

                    # Delay between tasks
                    delay = task.get('delay', 0.5)
                    time.sleep(float(delay))

                except Exception as e:
                    results.append({'index': i, 'action': action, 'result': {'success': False, 'error': str(e)}})

            self._update_status(queue_id, 'completed', results=results)

        t = threading.Thread(target=_execute, daemon=True, name=f'queue-{queue_id}')
        t.start()
        return {'success': True, 'queue_id': queue_id, 'tasks': len(tasks)}

    def _update_status(self, queue_id, status, error=None, results=None):
        conn = _get_conn()
        try:
            if results:
                conn.execute('''
                    UPDATE browser_task_queue SET status=?, result_json=?, completed_at=datetime('now')
                    WHERE id=?
                ''', (status, json.dumps(results, ensure_ascii=False), queue_id))
            elif error:
                conn.execute('''
                    UPDATE browser_task_queue SET status=?, result_json=?, completed_at=datetime('now')
                    WHERE id=?
                ''', (status, json.dumps({'error': error}), queue_id))
            else:
                conn.execute('UPDATE browser_task_queue SET status=? WHERE id=?', (status, queue_id))
            conn.commit()
        finally:
            conn.close()

    def _update_progress(self, queue_id, index, results):
        conn = _get_conn()
        try:
            conn.execute('''
                UPDATE browser_task_queue SET current_index=?, result_json=? WHERE id=?
            ''', (index, json.dumps(results, ensure_ascii=False), queue_id))
            conn.commit()
        finally:
            conn.close()

    def get_queue(self, queue_id):
        conn = _get_conn()
        try:
            row = conn.execute('SELECT * FROM browser_task_queue WHERE id=?', (queue_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d['tasks'] = json.loads(d.get('tasks_json', '[]'))
            d['results'] = json.loads(d.get('result_json', '[]'))
            return d
        finally:
            conn.close()

    def list_queues(self, limit=20):
        conn = _get_conn()
        try:
            rows = conn.execute(
                'SELECT * FROM browser_task_queue ORDER BY created_at DESC LIMIT ?', (limit,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d['tasks'] = json.loads(d.get('tasks_json', '[]'))
                d['results'] = json.loads(d.get('result_json', '[]'))
                result.append(d)
            return result
        finally:
            conn.close()

    def delete_queue(self, queue_id):
        conn = _get_conn()
        try:
            conn.execute('DELETE FROM browser_task_queue WHERE id=?', (queue_id,))
            conn.commit()
        finally:
            conn.close()


# Global task queue
task_queue = TaskQueue()


init_db()
