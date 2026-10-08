"""
VEX Browser Daemon
Background process that manages all browser instances persistently.
Survives restarts via state snapshots. Integrates health monitor,
sleep controller, and human behavior.
"""
import time, json, threading, logging, signal, sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger('browser_daemon')

PROFILES_DIR = Path(__file__).parent / 'browser_profiles'
SNAPSHOTS_DIR = PROFILES_DIR / 'snapshots'
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

DAEMON_STATE_FILE = PROFILES_DIR / 'daemon_state.json'


class BrowserDaemon:
    """Persistent background daemon for browser management."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._instances = {}  # iid -> BrowserInstance
        self._sleep_controllers = {}  # iid -> SleepController
        self._lock = threading.Lock()
        self._snapshot_interval = 60  # snapshot every 60s
        self._idle_check_interval = 30  # check idle every 30s
        self._last_snapshot = 0
        self._last_idle_check = 0
        self._stats = {
            'started': None,
            'snapshots': 0,
            'restores': 0,
            'total_actions': 0,
        }
        self._initialized = False

    def start(self):
        """Start the daemon."""
        if self._running:
            return
        self._running = True

        # Import here to avoid circular imports
        from browser_health import health_monitor
        from browser_sleep import sleep_manager

        self._health = health_monitor
        self._sleep_mgr = sleep_manager

        # Restore previous sessions
        self._restore_from_snapshot()

        # Start health monitor
        self._health.start()

        # Start daemon thread
        self._thread = threading.Thread(target=self._daemon_loop, daemon=True, name='browser-daemon')
        self._thread.start()

        self._stats['started'] = datetime.now().isoformat()
        self._initialized = True
        logger.info("Browser daemon started")
        self._save_daemon_state()

    def stop(self):
        """Stop the daemon gracefully."""
        self._running = False
        try:
            from browser_health import health_monitor
            health_monitor.stop()
        except Exception:
            pass
        # Save final snapshot
        self._save_snapshot()
        self._save_daemon_state()
        if self._thread:
            self._thread.join(timeout=15)
        logger.info("Browser daemon stopped")

    def _daemon_loop(self):
        """Main daemon loop."""
        while self._running:
            now = time.time()

            # Snapshot
            if now - self._last_snapshot >= self._snapshot_interval:
                try:
                    self._save_snapshot()
                except Exception as e:
                    logger.error(f"Snapshot error: {e}")
                self._last_snapshot = now

            # Idle check
            if now - self._last_idle_check >= self._idle_check_interval:
                try:
                    self._check_idle()
                except Exception as e:
                    logger.error(f"Idle check error: {e}")
                self._last_idle_check = now

            time.sleep(5)

    def register_instance(self, instance_id, browser_instance):
        """Register a browser instance with the daemon."""
        with self._lock:
            self._instances[instance_id] = browser_instance

            # Create sleep controller
            from browser_sleep import SleepController
            ctrl = SleepController(instance_id, browser_instance)
            self._sleep_controllers[instance_id] = ctrl

            # Register with health monitor
            self._health.register(instance_id, browser_instance, ctrl)

            # Register with sleep manager
            self._sleep_mgr.register(instance_id, browser_instance)

            # Setup sleep callbacks
            ctrl.on('on_sleep', self._on_instance_sleep)
            ctrl.on('on_wake', self._on_instance_wake)

    def unregister_instance(self, instance_id):
        """Remove an instance from daemon."""
        with self._lock:
            self._instances.pop(instance_id, None)
            self._sleep_controllers.pop(instance_id, None)
            self._health.unregister(instance_id)
            self._sleep_mgr.unregister(instance_id)

    def get_instance(self, instance_id):
        return self._instances.get(instance_id)

    def get_sleep_controller(self, instance_id):
        return self._sleep_controllers.get(instance_id)

    def list_instances(self):
        result = []
        for iid, inst in self._instances.items():
            ctrl = self._sleep_controllers.get(iid)
            info = inst.to_dict()
            if ctrl:
                info['sleep_state'] = ctrl.state
                info['idle_for'] = round(time.time() - ctrl._last_activity) if ctrl._last_activity else 0
                info['wake_triggers'] = len(ctrl._wake_triggers)
            health = self._health.get_instance_status(iid)
            if health:
                info['health'] = health
            result.append(info)
        return result

    def _check_idle(self):
        """Check all instances for idle timeout."""
        for ctrl in self._sleep_controllers.values():
            try:
                ctrl.check_idle()
            except Exception:
                pass

    def _on_instance_sleep(self, instance_id, state):
        logger.info(f"Instance {instance_id} went to sleep")

    def _on_instance_wake(self, instance_id, state):
        logger.info(f"Instance {instance_id} woke up")

    def wake_instance(self, instance_id, trigger='manual'):
        """Wake a sleeping instance."""
        ctrl = self._sleep_controllers.get(instance_id)
        if not ctrl:
            return {'success': False, 'error': 'No controller'}
        return ctrl.wake(trigger)

    def sleep_instance(self, instance_id):
        """Put an instance to sleep."""
        ctrl = self._sleep_controllers.get(instance_id)
        if not ctrl:
            return {'success': False, 'error': 'No controller'}
        ctrl.sleep()
        return {'success': True}

    def wake_all(self, trigger='manual'):
        results = {}
        for iid, ctrl in self._sleep_controllers.items():
            results[iid] = ctrl.wake(trigger)
        return results

    def sleep_all(self):
        for ctrl in self._sleep_controllers.values():
            try:
                ctrl.sleep()
            except Exception:
                pass

    # ── Snapshot Persistence ───────────────────────────────────

    def _save_snapshot(self):
        """Save state of all instances for recovery."""
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'instances': {},
        }
        for iid, inst in self._instances.items():
            ctrl = self._sleep_controllers.get(iid)
            snap = {
                'profile_id': inst.profile_id,
                'name': inst.name,
                'status': inst.status,
                'current_url': inst.page.url if inst.page else '',
            }
            if ctrl:
                snap['sleep_state'] = ctrl.state
                snap['last_activity'] = ctrl._last_activity
                snap['wake_triggers'] = ctrl._wake_triggers
            snapshot['instances'][iid] = snap

        # Write atomically
        tmp = SNAPSHOTS_DIR / 'latest.json.tmp'
        final = SNAPSHOTS_DIR / 'latest.json'
        with open(tmp, 'w') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        tmp.rename(final)

        # Keep last 10 snapshots
        snapshots = sorted(SNAPSHOTS_DIR.glob('snap_*.json'))
        for old in snapshots[:-10]:
            old.unlink(missing_ok=True)

        # Named snapshot
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        named = SNAPSHOTS_DIR / f'snap_{ts}.json'
        with open(named, 'w') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)

        self._stats['snapshots'] += 1

    def _restore_from_snapshot(self):
        """Restore instances from latest snapshot."""
        snap_file = SNAPSHOTS_DIR / 'latest.json'
        if not snap_file.exists():
            return

        try:
            with open(snap_file) as f:
                snapshot = json.load(f)
        except Exception:
            return

        instances = snapshot.get('instances', {})
        if not instances:
            return

        logger.info(f"Restoring {len(instances)} instances from snapshot")

        for iid, snap in instances.items():
            try:
                # Recreate instance
                from browser_manager import create_instance
                inst = create_instance(
                    name=snap.get('name', ''),
                    profile_id=snap.get('profile_id'),
                )

                # Try to start
                inst.start(headless=True)

                # Navigate to last URL
                url = snap.get('current_url', '')
                if url and url != 'about:blank':
                    inst.navigate(url)

                # Register with daemon
                self.register_instance(inst.id, inst)

                # Restore sleep state
                ctrl = self._sleep_controllers.get(inst.id)
                if ctrl and snap.get('sleep_state') == 'sleeping':
                    ctrl.sleep()

                self._stats['restores'] += 1
                logger.info(f"Restored instance {inst.id} ({snap.get('name', '')})")

            except Exception as e:
                logger.error(f"Failed to restore instance {iid}: {e}")

    def _save_daemon_state(self):
        """Save daemon metadata."""
        state = {
            'running': self._running,
            'stats': self._stats,
            'instance_count': len(self._instances),
            'saved_at': datetime.now().isoformat(),
        }
        with open(DAEMON_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

    def get_daemon_status(self):
        """Get full daemon status."""
        return {
            'running': self._running,
            'stats': self._stats,
            'instances': len(self._instances),
            'sleeping': sum(1 for c in self._sleep_controllers.values() if c.state == 'sleeping'),
            'active': sum(1 for c in self._sleep_controllers.values() if c.state == 'active'),
            'health': self._health.get_stats() if hasattr(self, '_health') else {},
        }


# Global singleton
browser_daemon = BrowserDaemon()
