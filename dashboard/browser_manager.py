"""
VEX Browser Manager — Embedded headless Chrome with persistent profiles
"""
import os, json, time, threading, base64, uuid, random, string
from datetime import datetime
from pathlib import Path

BROWSER_DIR = Path(__file__).parent / 'browser_profiles'
BROWSER_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR = BROWSER_DIR / 'screenshots'
SCREENSHOTS_DIR.mkdir(exist_ok=True)

_lock = threading.Lock()
_instances = {}

UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
]

VIEWPORTS = [
    {'width': 1366, 'height': 768},
    {'width': 1920, 'height': 1080},
    {'width': 1536, 'height': 864},
    {'width': 1440, 'height': 900},
    {'width': 1280, 'height': 720},
]

LOCALES = ['en-US', 'en-GB', 'ar-SA', 'fr-FR', 'de-DE', 'es-ES']
TIMEZONES = ['America/New_York', 'Europe/London', 'Asia/Riyadh', 'Europe/Paris', 'America/Los_Angeles']


def _random_str(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _human_delay(min_s=0.3, max_s=1.5):
    time.sleep(random.uniform(min_s, max_s))


def _human_type_delay():
    return random.uniform(0.03, 0.12)


class BrowserProfile:
    def __init__(self, profile_id, name='', proxy=None):
        self.id = profile_id
        self.name = name or f'Profile-{profile_id[:8]}'
        self.proxy = proxy
        self.dir = BROWSER_DIR / profile_id
        self.dir.mkdir(exist_ok=True)
        self.meta_file = self.dir / 'meta.json'
        self._load_meta()

    def _load_meta(self):
        if self.meta_file.exists():
            with open(self.meta_file) as f:
                self.meta = json.load(f)
        else:
            self.meta = {
                'id': self.id,
                'name': self.name,
                'ua': random.choice(UA_LIST),
                'viewport': random.choice(VIEWPORTS),
                'locale': random.choice(LOCALES),
                'timezone': random.choice(TIMEZONES),
                'created': datetime.now().isoformat(),
                'last_used': None,
                'proxy': self.proxy,
                'cookies_count': 0,
                'pages_visited': 0,
            }
            self._save_meta()

    def _save_meta(self):
        with open(self.meta_file, 'w') as f:
            json.dump(self.meta, f, indent=2, ensure_ascii=False)


class BrowserInstance:
    def __init__(self, instance_id, profile_id, name=''):
        self.id = instance_id
        self.profile_id = profile_id
        self.name = name
        self.profile = BrowserProfile(profile_id)
        self.browser = None
        self.context = None
        self.page = None
        self.status = 'stopped'
        self.screenshot_interval = 2
        self._screenshot_thread = None
        self._stop_screenshots = threading.Event()
        self._last_screenshot = None
        self._actions_log = []
        self._current_url = ''
        self._viewport = self.profile.meta.get('viewport', VIEWPORTS[0])
        self.human = None  # Initialized on start

    def start(self, headless=True):
        from playwright.sync_api import sync_playwright
        from browser_human import HumanBehavior
        self.human = HumanBehavior()
        pw = sync_playwright().start()
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
            '--disable-dev-shm-usage',
            f'--window-size={self._viewport["width"]},{self._viewport["height"]}',
        ]
        if self.profile.proxy:
            launch_args.append(f'--proxy-server={self.profile.proxy}')

        self.browser = pw.chromium.launch(
            headless=headless,
            args=launch_args,
        )
        storage_path = self.profile.dir / 'storage.json'
        storage = None
        if storage_path.exists():
            try:
                with open(storage_path) as f:
                    storage = json.load(f)
            except Exception:
                storage = None

        ctx_args = {
            'user_agent': self.profile.meta['ua'],
            'viewport': self._viewport,
            'locale': self.profile.meta['locale'],
            'timezone_id': self.profile.meta['timezone'],
            'color_scheme': 'light',
            'device_scale_factor': random.choice([1, 1.25, 1.5]),
        }
        if storage:
            ctx_args['storage_state'] = str(storage_path)

        self.context = self.browser.new_context(**ctx_args)
        self._stealth_inject()
        self.page = self.context.new_page()
        self._setup_network_monitor()
        self.status = 'running'
        self.profile.meta['last_used'] = datetime.now().isoformat()
        self.profile._save_meta()
        self._log_action('start', f'Browser started with profile {self.profile.name}')
        return True

    def _setup_network_monitor(self):
        """Monitor network requests for logging."""
        self._network_log = []
        def on_response(response):
            try:
                req = response.request
                entry = {
                    'url': req.url[:500],
                    'method': req.method,
                    'status': response.status,
                    'content_type': response.headers.get('content-type', ''),
                    'timestamp': datetime.now().isoformat(),
                }
                self._network_log.append(entry)
                if len(self._network_log) > 500:
                    self._network_log = self._network_log[-500:]
                # Log to DB
                try:
                    from browser_permissions import log_network_request
                    log_network_request(
                        self.id, req.url[:500], req.method, response.status,
                        response.headers.get('content-type', ''), 0, 0
                    )
                except Exception:
                    pass
            except Exception:
                pass
        self.page.on('response', on_response)

    def _stealth_inject(self):
        stealth_js = """
        () => {
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            window.chrome = {runtime: {}};
            Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        }
        """
        self.context.add_init_script(stealth_js)

    def stop(self):
        self._stop_screenshots.set()
        if self._screenshot_thread and self._screenshot_thread.is_alive():
            self._screenshot_thread.join(timeout=5)
        try:
            if self.context:
                storage_path = self.profile.dir / 'storage.json'
                self.context.storage_state(path=str(storage_path))
                self.profile.meta['cookies_count'] = len(self.context.cookies())
                self.profile._save_meta()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        self.browser = None
        self.context = None
        self.page = None
        self.status = 'stopped'
        self._log_action('stop', 'Browser stopped')

    def navigate(self, url):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            t0 = time.time()
            self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            _human_delay(0.5, 1.5)
            self._current_url = self.page.url
            self.profile.meta['pages_visited'] = self.profile.meta.get('pages_visited', 0) + 1
            self.profile._save_meta()
            duration = int((time.time() - t0) * 1000)
            self._log_action('navigate', url)
            self._learn('navigate', url=url, success=True, duration_ms=duration)
            return {'success': True, 'url': self.page.url, 'title': self.page.title()}
        except Exception as e:
            self._learn('navigate', url=url, success=False, error=str(e))
            return {'success': False, 'error': str(e)}

    def click(self, selector):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            t0 = time.time()
            self.page.wait_for_selector(selector, timeout=10000)
            # Human: hover before click
            if self.human:
                time.sleep(self.human.hover_before_click())
            box = self.page.locator(selector).bounding_box()
            if box and self.human:
                # Human: natural click position with offset
                cx, cy = self.human.click_position_offset(box)
                # Human: move mouse along bezier path
                vp = self._viewport
                start_x = random.uniform(0, vp['width'])
                start_y = random.uniform(0, vp['height'])
                path = self.human.mouse_path(start_x, start_y, cx, cy)
                for px, py in path[:15]:  # Sample path points
                    self.page.mouse.move(px, py)
                    time.sleep(self.human.mouse_move_delay(20))
                # Human: pre-click delay
                time.sleep(self.human.click_delay()[0])
                self.page.mouse.click(cx, cy)
                # Human: post-click delay
                time.sleep(self.human.click_delay()[1])
            elif box:
                self.page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            else:
                self.page.locator(selector).click()
            duration = int((time.time() - t0) * 1000)
            self._log_action('click', selector)
            self._learn('click', selector=selector, success=True, duration_ms=duration)
            return {'success': True}
        except Exception as e:
            self._learn('click', selector=selector, success=False, error=str(e))
            return {'success': False, 'error': str(e)}

    def type_text(self, selector, text, clear=True):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            t0 = time.time()
            self.page.wait_for_selector(selector, timeout=10000)
            self.page.locator(selector).click()
            time.sleep(0.2 + random.uniform(0.1, 0.4))
            if clear:
                self.page.locator(selector).fill('')
                time.sleep(0.1 + random.uniform(0.05, 0.2))
            # Human: type with variable speed and occasional typos
            if self.human:
                for char in text:
                    # Check for typo
                    if self.human.should_make_typo(char):
                        typo_char = self.human.get_typo_char(char)
                        self.page.keyboard.type(typo_char, delay=self.human.type_char_delay(typo_char) * 1000)
                        time.sleep(self.human.type_char_delay(typo_char))
                        # Backspace to fix typo
                        self.page.keyboard.press('Backspace')
                        time.sleep(0.1 + random.uniform(0.05, 0.15))
                    self.page.keyboard.type(char, delay=self.human.type_char_delay(char) * 1000)
                    # Occasional word pause
                    if char == ' ':
                        time.sleep(self.human.word_pause())
                    # Occasional think pause
                    if random.random() < 0.03:
                        time.sleep(self.human.think_pause())
            else:
                for char in text:
                    self.page.keyboard.type(char, delay=random.uniform(30, 100))
            time.sleep(0.2 + random.uniform(0.1, 0.4))
            duration = int((time.time() - t0) * 1000)
            self._log_action('type', f'{selector}: {text[:30]}...')
            self._learn('type', selector=selector, value=text[:50], success=True, duration_ms=duration)
            return {'success': True}
        except Exception as e:
            self._learn('type', selector=selector, success=False, error=str(e))
            return {'success': False, 'error': str(e)}

    def scroll(self, direction='down', amount=3):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            # Human: variable scroll distance
            if self.human:
                delta = self.human.scroll_amount() * (1 if direction == 'down' else -1)
                time.sleep(self.human.scroll_delay())
                self.page.mouse.wheel(0, delta)
                # Human: reading pause
                time.sleep(self.human.scroll_pause_duration())
                # Sometimes scroll back up
                if self.human.should_scroll_back():
                    time.sleep(self.human.scroll_pause_duration())
                    self.page.mouse.wheel(0, -delta * 0.4)
            else:
                delta = 300 * amount * (1 if direction == 'down' else -1)
                self.page.mouse.wheel(0, delta)
            time.sleep(0.3 + random.uniform(0.1, 0.5))
            self._log_action('scroll', f'{direction} {amount}')
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def screenshot(self, full_page=False):
        if not self.page:
            return None
        try:
            fname = f'{self.id}_{int(time.time())}.png'
            fpath = SCREENSHOTS_DIR / fname
            self.page.screenshot(path=str(fpath), full_page=full_page)
            self._last_screenshot = str(fpath)
            return str(fpath)
        except Exception:
            return None

    def get_screenshot_base64(self):
        if not self.page:
            return None
        try:
            buf = self.page.screenshot()
            return base64.b64encode(buf).decode('utf-8')
        except Exception:
            return None

    def get_page_content(self):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            return {
                'success': True,
                'url': self.page.url,
                'title': self.page.title(),
                'content': self.page.content()[:50000],
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_cookies(self):
        if not self.context:
            return []
        try:
            return self.context.cookies()
        except Exception:
            return []

    def evaluate(self, expression):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            result = self.page.evaluate(expression)
            return {'success': True, 'result': str(result)[:5000]}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def press_key(self, key):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            self.page.keyboard.press(key)
            _human_delay(0.2, 0.5)
            self._log_action('keypress', key)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def go_back(self):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            self.page.go_back()
            _human_delay(0.5, 1.0)
            self._log_action('back', '')
            return {'success': True, 'url': self.page.url}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def wait_for(self, selector, timeout=10000):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def hover(self, selector):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        try:
            self.page.locator(selector).hover()
            _human_delay(0.2, 0.5)
            self._log_action('hover', selector)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def fill_form(self, fields):
        if not self.page:
            return {'success': False, 'error': 'Browser not running'}
        results = []
        for f in fields:
            sel = f.get('selector', '')
            val = f.get('value', '')
            action = f.get('action', 'fill')
            if action == 'fill':
                r = self.type_text(sel, val)
            elif action == 'click':
                r = self.click(sel)
            elif action == 'select':
                try:
                    self.page.select_option(sel, val)
                    r = {'success': True}
                except Exception as e:
                    r = {'success': False, 'error': str(e)}
            else:
                r = {'success': False, 'error': f'Unknown action: {action}'}
            results.append({'selector': sel, 'action': action, **r})
            _human_delay(0.3, 0.8)
        return {'success': True, 'results': results}

    def _log_action(self, action, detail=''):
        self._actions_log.append({
            'action': action,
            'detail': detail,
            'time': datetime.now().isoformat(),
        })
        if len(self._actions_log) > 200:
            self._actions_log = self._actions_log[-200:]

    def _learn(self, action_type, selector='', value='', url='', success=True, error='', duration_ms=0):
        """Feed action to learning engine."""
        try:
            from browser_learning import learning_engine
            page_url = url or (self.page.url if self.page else '')
            learning_engine.record_action(
                self.id, page_url, action_type, selector, value,
                success, error, duration_ms
            )
        except Exception:
            pass

    def analyze_current_page(self):
        """Analyze current page and learn from it."""
        try:
            from browser_learning import learning_engine
            from urllib.parse import urlparse
            domain = urlparse(self.page.url).netloc.replace('www.', '') if self.page else ''
            if domain:
                return learning_engine.analyze_page(self.page, domain)
        except Exception:
            pass
        return {}

    def get_site_knowledge(self):
        """Get what's been learned about the current site."""
        try:
            from browser_learning import learning_engine
            from urllib.parse import urlparse
            domain = urlparse(self.page.url).netloc.replace('www.', '') if self.page else ''
            if domain:
                return learning_engine.get_site_summary(domain)
        except Exception:
            pass
        return {}

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'profile_id': self.profile_id,
            'profile_name': self.profile.name,
            'status': self.status,
            'current_url': self._current_url or self.page.url if self.page else '',
            'viewport': self._viewport,
            'ua': self.profile.meta.get('ua', ''),
            'pages_visited': self.profile.meta.get('pages_visited', 0),
            'cookies_count': self.profile.meta.get('cookies_count', 0),
            'last_used': self.profile.meta.get('last_used'),
            'recent_actions': self._actions_log[-10:],
        }


def create_instance(name='', profile_id=None, proxy=None):
    with _lock:
        instance_id = str(uuid.uuid4())
        if not profile_id:
            profile_id = str(uuid.uuid4())
        inst = BrowserInstance(instance_id, profile_id, name)
        _instances[instance_id] = inst
        # Register with daemon
        try:
            from browser_daemon import browser_daemon
            browser_daemon.register_instance(instance_id, inst)
        except Exception:
            pass
        return inst


def get_instance(instance_id):
    inst = _instances.get(instance_id)
    if inst:
        return inst
    # Fall back to daemon's instance registry
    try:
        from browser_daemon import browser_daemon
        if browser_daemon._initialized:
            inst = browser_daemon.get_instance(instance_id)
            if inst:
                _instances[instance_id] = inst
                return inst
    except Exception:
        pass
    return None


def list_instances():
    # Prefer daemon list (includes sleep/health info)
    try:
        from browser_daemon import browser_daemon
        if browser_daemon._initialized:
            return browser_daemon.list_instances()
    except Exception:
        pass
    return [inst.to_dict() for inst in _instances.values()]


def remove_instance(instance_id):
    with _lock:
        inst = _instances.pop(instance_id, None)
        if inst:
            try:
                inst.stop()
            except Exception:
                pass
            try:
                from browser_daemon import browser_daemon
                browser_daemon.unregister_instance(instance_id)
            except Exception:
                pass
            return True
        return False


def list_profiles():
    profiles = []
    for d in BROWSER_DIR.iterdir():
        meta_file = d / 'meta.json'
        if meta_file.exists():
            with open(meta_file) as f:
                profiles.append(json.load(f))
    return profiles


def get_profile(profile_id):
    meta_file = BROWSER_DIR / profile_id / 'meta.json'
    if meta_file.exists():
        with open(meta_file) as f:
            return json.load(f)
    return None


def delete_profile(profile_id):
    import shutil
    profile_dir = BROWSER_DIR / profile_id
    if profile_dir.exists():
        shutil.rmtree(profile_dir, ignore_errors=True)
        return True
    return False
