"""
VEX Browser Sleep/Wake Controller
Manages browser sleep states and wake triggers.
"""
import time, json, threading
from datetime import datetime
from pathlib import Path

SLEEP_DIR = Path(__file__).parent / 'browser_profiles' / 'sleep_states'
SLEEP_DIR.mkdir(parents=True, exist_ok=True)

# Sleep states
STATE_ACTIVE = 'active'
STATE_SLEEPING = 'sleeping'
STATE_DEEP_SLEEP = 'deep_sleep'
STATE_WAKING = 'waking'


class SleepController:
    """Controls browser sleep/wake lifecycle."""

    def __init__(self, instance_id, browser_instance):
        self.instance_id = instance_id
        self.browser = browser_instance
        self.state = STATE_ACTIVE
        self.state_file = SLEEP_DIR / f'{instance_id}.json'
        self._wake_triggers = []
        self._sleep_timer = None
        self._idle_timeout = 300  # 5 min idle → sleep
        self._last_activity = time.time()
        self._lock = threading.Lock()
        self._callbacks = {'on_sleep': [], 'on_wake': [], 'on_deep_sleep': []}
        self._load_state()

    def _load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                self.state = data.get('state', STATE_ACTIVE)
                self._idle_timeout = data.get('idle_timeout', 300)
                self._last_activity = data.get('last_activity', time.time())
                self._wake_triggers = data.get('wake_triggers', [])
            except Exception:
                pass

    def _save_state(self):
        data = {
            'instance_id': self.instance_id,
            'state': self.state,
            'idle_timeout': self._idle_timeout,
            'last_activity': self._last_activity,
            'wake_triggers': self._wake_triggers,
            'saved_at': datetime.now().isoformat(),
            'cookies': self._get_cookies(),
            'url': self.browser.page.url if self.browser.page else '',
            'localStorage': self._get_local_storage(),
        }
        with open(self.state_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _get_cookies(self):
        try:
            if self.browser.context:
                return self.browser.context.cookies()
        except Exception:
            pass
        return []

    def _get_local_storage(self):
        try:
            if self.browser.page:
                return self.browser.page.evaluate(
                    '() => { let d={}; for(let i=0;i<localStorage.length;i++) { '
                    'let k=localStorage.key(i); d[k]=localStorage.getItem(k); } return d; }'
                )
        except Exception:
            pass
        return {}

    def on(self, event, callback):
        """Register event callback: 'on_sleep', 'on_wake', 'on_deep_sleep'."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _fire(self, event):
        for cb in self._callbacks.get(event, []):
            try:
                cb(self.instance_id, self.state)
            except Exception:
                pass

    def add_wake_trigger(self, trigger_type, config):
        """Add a wake trigger.
        trigger_type: 'notification', 'schedule', 'webhook', 'api', 'keyword'
        config: depends on type
        """
        trigger = {
            'id': f'trigger_{int(time.time()*1000)}',
            'type': trigger_type,
            'config': config,
            'active': True,
            'created': datetime.now().isoformat(),
        }
        self._wake_triggers.append(trigger)
        self._save_state()
        return trigger

    def remove_wake_trigger(self, trigger_id):
        self._wake_triggers = [t for t in self._wake_triggers if t['id'] != trigger_id]
        self._save_state()

    def list_wake_triggers(self):
        return self._wake_triggers

    def record_activity(self):
        """Record user/admin activity — resets idle timer."""
        self._last_activity = time.time()
        if self.state == STATE_SLEEPING:
            self.wake('activity')
        self._save_state()

    def check_idle(self):
        """Check if browser should go to sleep."""
        if self.state != STATE_ACTIVE:
            return
        idle = time.time() - self._last_activity
        if idle >= self._idle_timeout:
            self.sleep()

    def sleep(self):
        """Put browser to sleep — save state and close page."""
        with self._lock:
            if self.state != STATE_ACTIVE:
                return
            self.state = STATE_SLEEPING
            try:
                # Save cookies + localStorage before sleeping
                self._save_state()
                # Close the page but keep context alive
                if self.browser.page:
                    self.browser.page.close()
                    self.browser.page = None
                self.browser.status = 'sleeping'
            except Exception as e:
                pass
            self._fire('on_sleep')
            self._save_state()

    def wake(self, trigger='manual'):
        """Wake browser from sleep — restore page and state."""
        with self._lock:
            if self.state not in (STATE_SLEEPING, STATE_DEEP_SLEEP):
                return {'success': False, 'error': 'Not sleeping'}
            self.state = STATE_WAKING
            self._save_state()
            try:
                # Restore page
                if not self.browser.page or self.browser.page.is_closed():
                    self.browser.page = self.browser.context.new_page()
                # Navigate to last URL
                saved = self._load_saved_state()
                url = saved.get('url', 'about:blank')
                if url and url != 'about:blank':
                    self.browser.page.goto(url, wait_until='domcontentloaded', timeout=15000)
                # Restore localStorage
                ls = saved.get('localStorage', {})
                if ls:
                    js = '() => {'
                    for k, v in ls.items():
                        v_escaped = str(v).replace("'", "\\'")
                        k_escaped = str(k).replace("'", "\\'")
                        js += f"localStorage.setItem('{k_escaped}','{v_escaped}');"
                    js += '}'
                    try:
                        self.browser.page.evaluate(js)
                    except Exception:
                        pass
                self.browser.status = 'running'
                self.state = STATE_ACTIVE
                self._last_activity = time.time()
                self._fire('on_wake')
            except Exception:
                self.state = STATE_SLEEPING
            self._save_state()
            return {'success': True, 'state': self.state, 'trigger': trigger}

    def deep_sleep(self):
        """Deep sleep — close everything, save all state."""
        with self._lock:
            self.state = STATE_DEEP_SLEEP
            self._save_state()
            try:
                if self.browser.context:
                    storage_path = Path(self.browser.profile.dir) / 'storage.json'
                    self.browser.context.storage_state(path=str(storage_path))
            except Exception:
                pass
            try:
                if self.browser.page:
                    self.browser.page.close()
                    self.browser.page = None
                if self.browser.context:
                    self.browser.context.close()
                    self.browser.context = None
                if self.browser.browser:
                    self.browser.browser.close()
                    self.browser.browser = None
            except Exception:
                pass
            self.browser.status = 'deep_sleep'
            self._fire('on_deep_sleep')
            self._save_state()

    def restore_from_deep_sleep(self):
        """Restore from deep sleep — restart browser with saved state."""
        saved = self._load_saved_state()
        try:
            self.browser.start(headless=True)
            self.state = STATE_ACTIVE
            self._last_activity = time.time()
            url = saved.get('url', 'about:blank')
            if url and url != 'about:blank':
                self.browser.navigate(url)
            self._save_state()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _load_saved_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def get_status(self):
        return {
            'instance_id': self.instance_id,
            'state': self.state,
            'idle_timeout': self._idle_timeout,
            'idle_for': round(time.time() - self._last_activity),
            'wake_triggers': len(self._wake_triggers),
            'last_activity': datetime.fromtimestamp(self._last_activity).isoformat() if self._last_activity else None,
        }

    def set_idle_timeout(self, seconds):
        self._idle_timeout = max(30, seconds)
        self._save_state()


class SleepManager:
    """Manages sleep controllers for all instances."""

    def __init__(self):
        self._controllers = {}
        self._lock = threading.Lock()

    def register(self, instance_id, browser_instance):
        with self._lock:
            ctrl = SleepController(instance_id, browser_instance)
            self._controllers[instance_id] = ctrl
            return ctrl

    def unregister(self, instance_id):
        with self._lock:
            self._controllers.pop(instance_id, None)

    def get(self, instance_id):
        return self._controllers.get(instance_id)

    def check_all_idle(self):
        """Check all instances for idle timeout."""
        for ctrl in self._controllers.values():
            try:
                ctrl.check_idle()
            except Exception:
                pass

    def wake_all(self, trigger='manual'):
        results = {}
        for iid, ctrl in self._controllers.items():
            results[iid] = ctrl.wake(trigger)
        return results

    def sleep_all(self):
        for ctrl in self._controllers.values():
            try:
                ctrl.sleep()
            except Exception:
                pass

    def get_all_status(self):
        return {iid: ctrl.get_status() for iid, ctrl in self._controllers.items()}


# Global singleton
sleep_manager = SleepManager()
