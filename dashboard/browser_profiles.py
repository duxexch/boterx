"""
VEX Browser Profiles + Content Injection + Geolocation/Notification/Network
Save/restore browser sessions, inject custom CSS/JS, spoof geolocation,
handle notifications, simulate network conditions.
"""
import json, sqlite3, time, threading, shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / 'boterx.db'
PROFILES_DIR = Path(__file__).parent / 'browser_profiles'


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS browser_saved_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                profile_dir TEXT NOT NULL,
                cookies_json TEXT DEFAULT '[]',
                localStorage_json TEXT DEFAULT '{}',
                sessionStorage_json TEXT DEFAULT '{}',
                viewport_width INTEGER DEFAULT 1280,
                viewport_height INTEGER DEFAULT 720,
                user_agent TEXT DEFAULT '',
                locale TEXT DEFAULT 'en-US',
                timezone TEXT DEFAULT 'America/New_York',
                proxy TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                is_favorite INTEGER DEFAULT 0,
                last_used TEXT,
                use_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_css_injections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                css_text TEXT NOT NULL,
                url_pattern TEXT DEFAULT '*',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_js_injections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                js_text TEXT NOT NULL,
                url_pattern TEXT DEFAULT '*',
                run_at TEXT DEFAULT 'document_idle',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_geolocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                accuracy REAL DEFAULT 100,
                city TEXT DEFAULT '',
                country TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_network_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                download_speed INTEGER DEFAULT 5000000,
                upload_speed INTEGER DEFAULT 2000000,
                latency INTEGER DEFAULT 50,
                packet_loss REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_bsp_name ON browser_saved_profiles(name);
        ''')
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Browser Profiles (Save/Restore Sessions)
# ═══════════════════════════════════════════════════════════════

def save_profile(instance_id, name, description=''):
    """Save current browser state as a named profile."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        # Get current state
        cookies = inst.context.cookies()
        ls = inst.page.evaluate('() => Object.fromEntries(Object.entries(localStorage))')
        ss = inst.page.evaluate('() => Object.fromEntries(Object.entries(sessionStorage))')
        vp = inst.page.viewport_size or {'width': 1280, 'height': 720}
        ua = inst.page.evaluate('() => navigator.userAgent')

        # Save to DB
        conn = _get_conn()
        try:
            cursor = conn.execute('''
                INSERT INTO browser_saved_profiles
                (name, description, profile_dir, cookies_json, localStorage_json, sessionStorage_json,
                 viewport_width, viewport_height, user_agent)
                VALUES (?, ?, '', ?, ?, ?, ?, ?, ?)
            ''', (name, description, json.dumps(cookies, ensure_ascii=False),
                  json.dumps(ls, ensure_ascii=False), json.dumps(ss, ensure_ascii=False),
                  vp.get('width', 1280), vp.get('height', 720), ua))
            conn.commit()
            profile_id = cursor.lastrowid

            # Save profile directory
            profile_dir = PROFILES_DIR / f'profile_{profile_id}'
            profile_dir.mkdir(parents=True, exist_ok=True)
            conn.execute('UPDATE browser_saved_profiles SET profile_dir=? WHERE id=?',
                         (str(profile_dir), profile_id))
            conn.commit()

            return {'success': True, 'profile_id': profile_id, 'name': name}
        finally:
            conn.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}


def restore_profile(profile_id, instance_id=None):
    """Restore a saved profile to a browser instance."""
    from browser_manager import get_instance, create_instance, start_instance

    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM browser_saved_profiles WHERE id=?', (profile_id,)).fetchone()
        if not row:
            return {'success': False, 'error': 'Profile not found'}
        profile = dict(row)
    finally:
        conn.close()

    # Get or create instance
    inst = None
    if instance_id:
        inst = get_instance(instance_id)
    if not inst or not inst.page:
        inst = create_instance(name=profile['name'])
        if inst:
            start_instance(inst.id, proxy=profile.get('proxy', ''))
            inst = get_instance(inst.id)

    if not inst or not inst.page:
        return {'success': False, 'error': 'Failed to create/restore browser'}

    try:
        # Restore cookies
        cookies = json.loads(profile.get('cookies_json', '[]'))
        if cookies:
            inst.context.add_cookies(cookies)

        # Restore localStorage
        ls = json.loads(profile.get('localStorage_json', '{}'))
        if ls:
            js = f"() => {{ {'; '.join(f'localStorage.setItem({json.dumps(k)}, {json.dumps(v)})' for k, v in ls.items())} }}"
            inst.page.evaluate(js)

        # Navigate to last URL if available
        # Update usage stats
        conn = _get_conn()
        try:
            conn.execute('''
                UPDATE browser_saved_profiles
                SET use_count=use_count+1, last_used=datetime('now')
                WHERE id=?
            ''', (profile_id,))
            conn.commit()
        finally:
            conn.close()

        return {'success': True, 'instance_id': inst.id, 'cookies': len(cookies), 'ls_keys': len(ls)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def list_profiles():
    conn = _get_conn()
    try:
        rows = conn.execute(
            'SELECT * FROM browser_saved_profiles ORDER BY is_favorite DESC, last_used DESC'
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_profile(profile_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM browser_saved_profiles WHERE id=?', (profile_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_profile(profile_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT profile_dir FROM browser_saved_profiles WHERE id=?', (profile_id,)).fetchone()
        if row and Path(row['profile_dir']).exists():
            shutil.rmtree(row['profile_dir'], ignore_errors=True)
        conn.execute('DELETE FROM browser_saved_profiles WHERE id=?', (profile_id,))
        conn.commit()
    finally:
        conn.close()


def toggle_favorite(profile_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT is_favorite FROM browser_saved_profiles WHERE id=?', (profile_id,)).fetchone()
        if row:
            conn.execute('UPDATE browser_saved_profiles SET is_favorite=? WHERE id=?',
                         (0 if row['is_favorite'] else 1, profile_id))
            conn.commit()
    finally:
        conn.close()


def search_profiles(query):
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM browser_saved_profiles WHERE name LIKE ? OR description LIKE ? ORDER BY name",
            (f'%{query}%', f'%{query}%')
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def export_profile(profile_id):
    """Export a profile as JSON."""
    profile = get_profile(profile_id)
    if not profile:
        return None
    return {
        'name': profile['name'],
        'description': profile.get('description', ''),
        'cookies': json.loads(profile.get('cookies_json', '[]')),
        'localStorage': json.loads(profile.get('localStorage_json', '{}')),
        'sessionStorage': json.loads(profile.get('sessionStorage_json', '{}')),
        'viewport': {'width': profile.get('viewport_width', 1280), 'height': profile.get('viewport_height', 720)},
        'user_agent': profile.get('user_agent', ''),
        'locale': profile.get('locale', 'en-US'),
        'timezone': profile.get('timezone', 'America/New_York'),
    }


def import_profile(data, name=None):
    """Import a profile from JSON data."""
    conn = _get_conn()
    try:
        cursor = conn.execute('''
            INSERT INTO browser_saved_profiles
            (name, description, cookies_json, localStorage_json, sessionStorage_json,
             viewport_width, viewport_height, user_agent, locale, timezone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name or data.get('name', 'imported'),
            data.get('description', ''),
            json.dumps(data.get('cookies', []), ensure_ascii=False),
            json.dumps(data.get('localStorage', {}), ensure_ascii=False),
            json.dumps(data.get('sessionStorage', {}), ensure_ascii=False),
            data.get('viewport', {}).get('width', 1280),
            data.get('viewport', {}).get('height', 720),
            data.get('user_agent', ''),
            data.get('locale', 'en-US'),
            data.get('timezone', 'America/New_York'),
        ))
        conn.commit()
        return {'success': True, 'profile_id': cursor.lastrowid}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Content Injection (Custom CSS/JS)
# ═══════════════════════════════════════════════════════════════

def inject_css(instance_id, css_text):
    """Inject custom CSS into the page."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        inst.page.evaluate(f"""
        () => {{
            const style = document.createElement('style');
            style.textContent = `{css_text}`;
            style.setAttribute('data-vex-injected', 'true');
            document.head.appendChild(style);
            return 'CSS injected';
        }}
        """)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def inject_js(instance_id, js_text):
    """Inject custom JavaScript into the page."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        result = inst.page.evaluate(f"() => {{ {js_text} }}")
        return {'success': True, 'result': str(result)[:2000]}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def inject_js_file(instance_id, js_url):
    """Inject a JavaScript file via script tag."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        inst.page.evaluate(f"""
        () => {{
            const script = document.createElement('script');
            script.src = '{js_url}';
            script.setAttribute('data-vex-injected', 'true');
            document.head.appendChild(script);
            return 'JS file injected';
        }}
        """)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def remove_injections(instance_id):
    """Remove all VEX-injected CSS/JS."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        count = inst.page.evaluate("""
        () => {
            let removed = 0;
            document.querySelectorAll('[data-vex-injected]').forEach(el => {
                el.remove();
                removed++;
            });
            return removed;
        }
        """)
        return {'success': True, 'removed': count}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def save_css_injection(name, css_text, url_pattern='*'):
    """Save a CSS injection rule."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            'INSERT INTO browser_css_injections (name, css_text, url_pattern) VALUES (?, ?, ?)',
            (name, css_text, url_pattern)
        )
        conn.commit()
        return {'success': True, 'id': cursor.lastrowid}
    finally:
        conn.close()


def save_js_injection(name, js_text, url_pattern='*', run_at='document_idle'):
    """Save a JS injection rule."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            'INSERT INTO browser_js_injections (name, js_text, url_pattern, run_at) VALUES (?, ?, ?, ?)',
            (name, js_text, url_pattern, run_at)
        )
        conn.commit()
        return {'success': True, 'id': cursor.lastrowid}
    finally:
        conn.close()


def list_css_injections():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_css_injections ORDER BY name').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_js_injections():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_js_injections ORDER BY name').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_css_injection(injection_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_css_injections WHERE id=?', (injection_id,))
        conn.commit()
    finally:
        conn.close()


def delete_js_injection(injection_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_js_injections WHERE id=?', (injection_id,))
        conn.commit()
    finally:
        conn.close()


def toggle_css_injection(injection_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT is_active FROM browser_css_injections WHERE id=?', (injection_id,)).fetchone()
        if row:
            conn.execute('UPDATE browser_css_injections SET is_active=? WHERE id=?',
                         (0 if row['is_active'] else 1, injection_id))
            conn.commit()
    finally:
        conn.close()


def toggle_js_injection(injection_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT is_active FROM browser_js_injections WHERE id=?', (injection_id,)).fetchone()
        if row:
            conn.execute('UPDATE browser_js_injections SET is_active=? WHERE id=?',
                         (0 if row['is_active'] else 1, injection_id))
            conn.commit()
    finally:
        conn.close()


def apply_saved_injections(instance_id):
    """Apply all active saved injections to a browser instance."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    applied = 0
    # Apply CSS
    for inj in list_css_injections():
        if inj.get('is_active'):
            try:
                inject_css(instance_id, inj['css_text'])
                applied += 1
            except Exception:
                pass

    # Apply JS
    for inj in list_js_injections():
        if inj.get('is_active'):
            try:
                inject_js(instance_id, inj['js_text'])
                applied += 1
            except Exception:
                pass

    return {'success': True, 'applied': applied}


# ═══════════════════════════════════════════════════════════════
#  Geolocation Spoofing
# ═══════════════════════════════════════════════════════════════

PRESET_LOCATIONS = [
    {'name': 'New York, USA', 'lat': 40.7128, 'lng': -74.0060, 'city': 'New York', 'country': 'USA'},
    {'name': 'London, UK', 'lat': 51.5074, 'lng': -0.1278, 'city': 'London', 'country': 'UK'},
    {'name': 'Tokyo, Japan', 'lat': 35.6762, 'lng': 139.6503, 'city': 'Tokyo', 'country': 'Japan'},
    {'name': 'Dubai, UAE', 'lat': 25.2048, 'lng': 55.2708, 'city': 'Dubai', 'country': 'UAE'},
    {'name': 'Paris, France', 'lat': 48.8566, 'lng': 2.3522, 'city': 'Paris', 'country': 'France'},
    {'name': 'Sydney, Australia', 'lat': -33.8688, 'lng': 151.2093, 'city': 'Sydney', 'country': 'Australia'},
    {'name': 'Berlin, Germany', 'lat': 52.5200, 'lng': 13.4050, 'city': 'Berlin', 'country': 'Germany'},
    {'name': 'Singapore', 'lat': 1.3521, 'lng': 103.8198, 'city': 'Singapore', 'country': 'Singapore'},
    {'name': 'Riyadh, Saudi Arabia', 'lat': 24.7136, 'lng': 46.6753, 'city': 'Riyadh', 'country': 'Saudi Arabia'},
    {'name': 'Cairo, Egypt', 'lat': 30.0444, 'lng': 31.2357, 'city': 'Cairo', 'country': 'Egypt'},
    {'name': 'Istanbul, Turkey', 'lat': 41.0082, 'lng': 28.9784, 'city': 'Istanbul', 'country': 'Turkey'},
    {'name': 'Moscow, Russia', 'lat': 55.7558, 'lng': 37.6173, 'city': 'Moscow', 'country': 'Russia'},
]


def set_geolocation(instance_id, latitude, longitude, accuracy=100):
    """Set geolocation for a browser instance."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        inst.context.set_geolocation({
            'latitude': float(latitude),
            'longitude': float(longitude),
            'accuracy': float(accuracy),
        })
        inst.context.grant_permissions(['geolocation'])
        return {'success': True, 'lat': latitude, 'lng': longitude}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def save_geolocation(name, latitude, longitude, accuracy=100, city='', country=''):
    conn = _get_conn()
    try:
        cursor = conn.execute('''
            INSERT INTO browser_geolocations (name, latitude, longitude, accuracy, city, country)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, float(latitude), float(longitude), float(accuracy), city, country))
        conn.commit()
        return {'success': True, 'id': cursor.lastrowid}
    finally:
        conn.close()


def list_geolocations():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_geolocations ORDER BY name').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_geolocation(geo_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_geolocations WHERE id=?', (geo_id,))
        conn.commit()
    finally:
        conn.close()


def get_preset_locations():
    return PRESET_LOCATIONS


# ═══════════════════════════════════════════════════════════════
#  Notification Handling
# ═══════════════════════════════════════════════════════════════

def setup_notification_handler(instance_id):
    """Set up notification event handler."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        inst.context.grant_permissions(['notifications'])
        return {'success': True, 'message': 'Notifications permitted'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def deny_notifications(instance_id):
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        inst.context.set_geolocation({'latitude': 0, 'longitude': 0, 'accuracy': 0})
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════
#  Network Condition Simulation
# ═══════════════════════════════════════════════════════════════

NETWORK_PRESETS = {
    'fast': {'name': 'Fast (Fiber)', 'download': 50000000, 'upload': 25000000, 'latency': 5},
    'normal': {'name': 'Normal (Broadband)', 'download': 10000000, 'upload': 5000000, 'latency': 30},
    'slow': {'name': 'Slow (DSL)', 'download': 1000000, 'upload': 500000, 'latency': 100},
    'very_slow': {'name': 'Very Slow (2G)', 'download': 50000, 'upload': 25000, 'latency': 800},
    '3g': {'name': '3G Mobile', 'download': 750000, 'upload': 250000, 'latency': 300},
    '4g': {'name': '4G LTE', 'download': 12000000, 'upload': 5000000, 'latency': 50},
    'wifi': {'name': 'WiFi', 'download': 30000000, 'upload': 15000000, 'latency': 10},
    'offline': {'name': 'Offline', 'download': 0, 'upload': 0, 'latency': 0},
}


def simulate_network(instance_id, profile_name):
    """Simulate network conditions."""
    from browser_manager import get_instance
    profile = NETWORK_PRESETS.get(profile_name)
    if not profile:
        return {'success': False, 'error': f'Unknown network profile: {profile_name}'}

    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        cdp = inst.context.new_cdp_session(inst.page)
        if profile_name == 'offline':
            cdp.send('Network.emulateNetworkConditions', {
                'offline': True, 'downloadThroughput': 0, 'uploadThroughput': 0, 'latency': 0,
            })
        else:
            cdp.send('Network.emulateNetworkConditions', {
                'offline': False,
                'downloadThroughput': profile['download'],
                'uploadThroughput': profile['upload'],
                'latency': profile['latency'],
            })
        return {'success': True, 'profile': profile['name'], 'latency': profile['latency']}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_network_presets():
    return NETWORK_PRESETS


def save_network_profile(name, download_speed, upload_speed, latency, packet_loss=0):
    conn = _get_conn()
    try:
        cursor = conn.execute('''
            INSERT INTO browser_network_profiles (name, download_speed, upload_speed, latency, packet_loss)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, int(download_speed), int(upload_speed), int(latency), float(packet_loss)))
        conn.commit()
        return {'success': True, 'id': cursor.lastrowid}
    finally:
        conn.close()


def list_network_profiles():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_network_profiles ORDER BY name').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


init_db()
