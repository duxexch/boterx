"""
VEX Browser Schedule Runner + Webhook Triggers
Runs scheduled browser tasks and handles webhook-based wake triggers.
"""
import time, threading, json, logging
from datetime import datetime

logger = logging.getLogger('browser_scheduler')


class ScheduleRunner:
    """Runs scheduled browser tasks in background."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._check_interval = 30  # check every 30s

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name='browser-scheduler')
        self._thread.start()
        logger.info("Schedule runner started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self):
        while self._running:
            try:
                self._check_and_run()
            except Exception as e:
                logger.error(f"Schedule check error: {e}")
            time.sleep(self._check_interval)

    def _check_and_run(self):
        from browser_permissions import get_due_schedules, mark_schedule_run
        from browser_tasks import create_from_template, task_executor
        from browser_manager import list_instances

        due = get_due_schedules()
        if not due:
            return

        instances = list_instances()
        running = [i for i in instances if i.get('status') == 'running']
        if not running:
            return

        for schedule in due:
            try:
                config = schedule.get('config', {})
                task_type = schedule.get('task_type', '')
                instance_id = config.get('instance_id')

                # Find a running instance
                if not instance_id:
                    if running:
                        instance_id = running[0]['id']
                    else:
                        continue

                # Create and execute task
                if task_type == 'scrape':
                    task = create_from_template('scrape_page', {
                        'url': config.get('url', ''),
                        'selector': config.get('selector', 'body'),
                    })
                elif task_type == 'check_status':
                    task = create_from_template('check_site_status', {
                        'url': config.get('url', ''),
                    })
                elif task_type == 'login':
                    task = create_from_template('login', {
                        'url': config.get('url', ''),
                        'username': config.get('username', ''),
                        'password': config.get('password', ''),
                    })
                else:
                    continue

                if task:
                    result = task_executor.execute_task(task.id, instance_id)
                    logger.info(f"Schedule '{schedule['name']}' executed: {result.get('success', False)}")

                # Update next run time
                interval = schedule.get('interval_seconds', 3600)
                mark_schedule_run(schedule['id'], interval)

            except Exception as e:
                logger.error(f"Schedule '{schedule.get('name', '?')}' error: {e}")


class WebhookTrigger:
    """Handles webhook-based wake triggers for browser instances."""

    def __init__(self):
        self._pending_webhooks = {}

    def register_webhook(self, instance_id, webhook_id, config):
        """Register a webhook that can wake a browser instance."""
        self._pending_webhooks[webhook_id] = {
            'instance_id': instance_id,
            'config': config,
            'created': datetime.now().isoformat(),
        }

    def handle_webhook(self, webhook_id, payload=None):
        """Handle incoming webhook — wake the associated browser."""
        info = self._pending_webhooks.get(webhook_id)
        if not info:
            return {'success': False, 'error': 'Webhook not found'}

        instance_id = info['instance_id']
        config = info['config']

        # Check conditions
        conditions = config.get('conditions', {})
        if conditions and payload:
            for key, expected in conditions.items():
                actual = payload.get(key, '')
                if expected and str(actual) != str(expected):
                    return {'success': False, 'error': f'Condition not met: {key}'}

        # Wake the browser
        try:
            from browser_daemon import browser_daemon
            result = browser_daemon.wake_instance(instance_id, trigger='webhook')

            # Navigate to configured URL if specified
            if result.get('success') and config.get('url'):
                from browser_manager import get_instance
                inst = get_instance(instance_id)
                if inst and inst.page:
                    inst.navigate(config['url'])

            return {
                'success': True,
                'instance_id': instance_id,
                'wake_result': result,
                'webhook_id': webhook_id,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def handle_telegram_notification(self, bot_token, chat_id, message_text=''):
        """Handle Telegram notification as wake trigger."""
        # Find webhooks configured for this chat
        for wid, info in self._pending_webhooks.items():
            config = info.get('config', {})
            if config.get('source') == 'telegram' and str(config.get('chat_id')) == str(chat_id):
                return self.handle_webhook(wid, {'text': message_text, 'chat_id': chat_id})
        return {'success': False, 'error': 'No matching webhook'}

    def list_webhooks(self):
        return self._pending_webhooks

    def remove_webhook(self, webhook_id):
        return self._pending_webhooks.pop(webhook_id, None) is not None


# Global singletons
schedule_runner = ScheduleRunner()
webhook_trigger = WebhookTrigger()
