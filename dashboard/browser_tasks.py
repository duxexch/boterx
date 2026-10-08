"""
VEX Browser Agent Task Executor
Allows AI agents to execute browser tasks with full logging.
"""
import time, json, threading
from datetime import datetime


class BrowserTask:
    """A single browser task (action + result)."""

    def __init__(self, task_id, goal, steps=None):
        self.id = task_id
        self.goal = goal
        self.steps = steps or []
        self.results = []
        self.status = 'pending'
        self.started_at = None
        self.finished_at = None
        self.error = None
        self.screenshots = []

    def to_dict(self):
        return {
            'id': self.id,
            'goal': self.goal,
            'steps': self.steps,
            'results': self.results,
            'status': self.status,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'error': self.error,
            'screenshots': len(self.screenshots),
        }


class TaskExecutor:
    """Executes browser tasks with human-like behavior."""

    def __init__(self):
        self._tasks = {}
        self._lock = threading.Lock()

    def create_task(self, goal, steps=None):
        """Create a new task."""
        task_id = f'task_{int(time.time()*1000)}'
        task = BrowserTask(task_id, goal, steps)
        with self._lock:
            self._tasks[task_id] = task
        return task

    def execute_task(self, task_id, instance_id):
        """Execute a task on a browser instance."""
        from browser_manager import get_instance

        task = self._tasks.get(task_id)
        if not task:
            return {'success': False, 'error': 'Task not found'}

        inst = get_instance(instance_id)
        if not inst:
            return {'success': False, 'error': 'Instance not found'}
        if not inst.page:
            return {'success': False, 'error': 'Browser not running'}

        task.status = 'running'
        task.started_at = datetime.now().isoformat()

        try:
            for i, step in enumerate(task.steps):
                action = step.get('action', '')
                result = self._execute_step(inst, step, task)
                task.results.append({
                    'step': i,
                    'action': action,
                    'success': result.get('success', False),
                    'detail': result,
                })

                # Take screenshot after important steps
                if action in ('navigate', 'click', 'fill_form') and inst.page:
                    try:
                        path = inst.screenshot()
                        if path:
                            task.screenshots.append(path)
                    except Exception:
                        pass

                # If step failed and no continue_on_error
                if not result.get('success') and not step.get('continue_on_error'):
                    task.status = 'failed'
                    task.error = result.get('error', 'Step failed')
                    task.finished_at = datetime.now().isoformat()
                    return {
                        'success': False,
                        'task': task.to_dict(),
                        'failed_step': i,
                        'error': result.get('error'),
                    }

            task.status = 'completed'
            task.finished_at = datetime.now().isoformat()
            return {'success': True, 'task': task.to_dict()}

        except Exception as e:
            task.status = 'error'
            task.error = str(e)
            task.finished_at = datetime.now().isoformat()
            return {'success': False, 'task': task.to_dict(), 'error': str(e)}

    def _execute_step(self, inst, step, task):
        """Execute a single step."""
        action = step.get('action', '')

        try:
            if action == 'navigate':
                return inst.navigate(step.get('url', ''))

            elif action == 'click':
                return inst.click(step.get('selector', ''))

            elif action == 'type':
                return inst.type_text(
                    step.get('selector', ''),
                    step.get('text', ''),
                    step.get('clear', True)
                )

            elif action == 'scroll':
                return inst.scroll(
                    step.get('direction', 'down'),
                    step.get('amount', 3)
                )

            elif action == 'wait':
                return inst.wait_for(
                    step.get('selector', ''),
                    step.get('timeout', 10000)
                )

            elif action == 'hover':
                return inst.hover(step.get('selector', ''))

            elif action == 'press':
                return inst.press_key(step.get('key', 'Enter'))

            elif action == 'back':
                return inst.go_back()

            elif action == 'fill_form':
                return inst.fill_form(step.get('fields', []))

            elif action == 'evaluate':
                return inst.evaluate(step.get('expression', ''))

            elif action == 'screenshot':
                path = inst.screenshot(step.get('full_page', False))
                return {'success': bool(path), 'path': path}

            elif action == 'read_text':
                result = inst.evaluate(
                    f'document.querySelector("{step.get("selector","body")}")?.innerText || ""'
                )
                return result

            elif action == 'check_element':
                result = inst.evaluate(
                    f'!!document.querySelector("{step.get("selector","")}")'
                )
                return {'success': True, 'exists': result.get('result', 'false') == 'true'}

            elif action == 'random_delay':
                import random
                min_s = step.get('min', 1)
                max_s = step.get('max', 3)
                time.sleep(random.uniform(min_s, max_s))
                return {'success': True}

            else:
                return {'success': False, 'error': f'Unknown action: {action}'}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_task(self, task_id):
        return self._tasks.get(task_id)

    def list_tasks(self):
        return [t.to_dict() for t in self._tasks.values()]

    def delete_task(self, task_id):
        with self._lock:
            return self._tasks.pop(task_id, None) is not None


# Predefined task templates
TASK_TEMPLATES = {
    'login': {
        'goal': 'Login to website',
        'steps': [
            {'action': 'navigate', 'url': '{{url}}'},
            {'action': 'wait', 'selector': 'input[type="password"], input[name="password"]', 'timeout': 15000},
            {'action': 'type', 'selector': 'input[type="email"], input[name="email"], input[type="text"]', 'text': '{{username}}'},
            {'action': 'random_delay', 'min': 0.5, 'max': 1.5},
            {'action': 'type', 'selector': 'input[type="password"], input[name="password"]', 'text': '{{password}}'},
            {'action': 'random_delay', 'min': 0.3, 'max': 1.0},
            {'action': 'click', 'selector': 'button[type="submit"], input[type="submit"]'},
            {'action': 'wait', 'selector': 'body', 'timeout': 10000},
        ],
    },
    'scrape_page': {
        'goal': 'Scrape page content',
        'steps': [
            {'action': 'navigate', 'url': '{{url}}'},
            {'action': 'wait', 'selector': 'body', 'timeout': 15000},
            {'action': 'random_delay', 'min': 1, 'max': 3},
            {'action': 'read_text', 'selector': '{{selector}}'},
        ],
    },
    'check_site_status': {
        'goal': 'Check if site is accessible',
        'steps': [
            {'action': 'navigate', 'url': '{{url}}'},
            {'action': 'wait', 'selector': 'body', 'timeout': 15000},
            {'action': 'screenshot'},
            {'action': 'evaluate', 'expression': 'document.title'},
        ],
    },
}


def get_task_templates():
    return TASK_TEMPLATES


def create_from_template(template_name, variables=None):
    """Create a task from a template with variable substitution."""
    template = TASK_TEMPLATES.get(template_name)
    if not template:
        return None

    steps = json.loads(json.dumps(template['steps']))

    if variables:
        for step in steps:
            for key, val in step.items():
                if isinstance(val, str):
                    for var_name, var_val in variables.items():
                        step[key] = step[key].replace(f'{{{{{var_name}}}}}', str(var_val))

    executor = TaskExecutor()
    return executor.create_task(template['goal'], steps)


# Global singleton
task_executor = TaskExecutor()
