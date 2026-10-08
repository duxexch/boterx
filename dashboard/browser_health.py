"""
VEX Browser Health Monitor
Continuously monitors browser instances and auto-restarts dead ones.
"""
import time, threading, logging
from datetime import datetime

logger = logging.getLogger('browser_health')


class HealthMonitor:
    """Monitors browser health and auto-recovers dead instances."""

    def __init__(self, check_interval=30):
        self.check_interval = check_interval
        self._running = False
        self._thread = None
        self._instances = {}  # iid -> {'browser': inst, 'sleep_ctrl': ctrl, 'last_check': ...}
        self._lock = threading.Lock()
        self._stats = {
            'checks': 0,
            'restarts': 0,
            'failures': 0,
            'last_check': None,
        }
        self._callbacks = {'on_restart': [], 'on_failure': [], 'on_state_change': []}

    def on(self, event, callback):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _fire(self, event, *args):
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args)
            except Exception:
                pass

    def register(self, instance_id, browser_instance, sleep_controller=None):
        with self._lock:
            self._instances[instance_id] = {
                'browser': browser_instance,
                'sleep_ctrl': sleep_controller,
                'last_check': time.time(),
                'consecutive_failures': 0,
                'last_restart': None,
                'healthy': True,
            }

    def unregister(self, instance_id):
        with self._lock:
            self._instances.pop(instance_id, None)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Health monitor started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Health monitor stopped")

    def _monitor_loop(self):
        while self._running:
            try:
                self._check_all()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            time.sleep(self.check_interval)

    def _check_all(self):
        with self._lock:
            instances = dict(self._instances)

        self._stats['checks'] += 1
        self._stats['last_check'] = datetime.now().isoformat()

        for iid, info in instances.items():
            browser = info['browser']
            sleep_ctrl = info['sleep_ctrl']

            # Skip if sleeping
            if sleep_ctrl and sleep_ctrl.state in ('sleeping', 'deep_sleep'):
                info['healthy'] = True
                info['consecutive_failures'] = 0
                continue

            healthy = self._check_instance(browser)
            info['last_check'] = time.time()

            if healthy:
                info['healthy'] = True
                info['consecutive_failures'] = 0
            else:
                info['consecutive_failures'] += 1
                info['healthy'] = False
                logger.warning(f"Instance {iid} unhealthy (failures: {info['consecutive_failures']})")

                # Auto-restart after 2 consecutive failures
                if info['consecutive_failures'] >= 2:
                    self._restart_instance(iid, info)

    def _check_instance(self, browser):
        """Check if a browser instance is alive and responsive."""
        try:
            if not browser or browser.status == 'stopped':
                return False
            if not browser.browser or not browser.browser.is_connected():
                return False
            if browser.context and browser.page and not browser.page.is_closed():
                # Try a simple JS evaluation
                browser.page.evaluate('1+1', timeout=5000)
                return True
            # No page but browser is running — might need page creation
            if browser.browser and browser.browser.is_connected():
                return True
            return False
        except Exception:
            return False

    def _restart_instance(self, iid, info):
        """Attempt to restart a failed instance."""
        browser = info['browser']
        sleep_ctrl = info['sleep_ctrl']
        logger.info(f"Restarting instance {iid}")

        try:
            # Stop existing
            try:
                browser.stop()
            except Exception:
                pass

            # Wait a moment
            time.sleep(2)

            # Restart
            browser.start(headless=True)
            info['consecutive_failures'] = 0
            info['last_restart'] = datetime.now().isoformat()
            self._stats['restarts'] += 1

            # Restore sleep controller state
            if sleep_ctrl:
                sleep_ctrl.browser = browser
                if sleep_ctrl.state == 'sleeping':
                    # Keep sleeping
                    pass

            self._fire('on_restart', iid, browser)
            logger.info(f"Instance {iid} restarted successfully")

        except Exception as e:
            info['consecutive_failures'] += 3
            self._stats['failures'] += 1
            self._fire('on_failure', iid, str(e))
            logger.error(f"Failed to restart {iid}: {e}")

    def manual_check(self, instance_id):
        """Manually trigger health check for a specific instance."""
        with self._lock:
            info = self._instances.get(instance_id)
        if not info:
            return {'success': False, 'error': 'Instance not registered'}
        healthy = self._check_instance(info['browser'])
        return {'success': True, 'healthy': healthy, 'info': {
            'consecutive_failures': info['consecutive_failures'],
            'last_check': datetime.fromtimestamp(info['last_check']).isoformat() if info['last_check'] else None,
            'last_restart': info['last_restart'],
        }}

    def manual_restart(self, instance_id):
        """Manually trigger restart for a specific instance."""
        with self._lock:
            info = self._instances.get(instance_id)
        if not info:
            return {'success': False, 'error': 'Instance not registered'}
        self._restart_instance(instance_id, info)
        return {'success': True}

    def get_stats(self):
        return {
            **self._stats,
            'total_instances': len(self._instances),
            'healthy': sum(1 for i in self._instances.values() if i['healthy']),
            'unhealthy': sum(1 for i in self._instances.values() if not i['healthy']),
        }

    def get_instance_status(self, instance_id):
        info = self._instances.get(instance_id)
        if not info:
            return None
        return {
            'healthy': info['healthy'],
            'consecutive_failures': info['consecutive_failures'],
            'last_check': datetime.fromtimestamp(info['last_check']).isoformat() if info['last_check'] else None,
            'last_restart': info['last_restart'],
        }


# Global singleton
health_monitor = HealthMonitor()
