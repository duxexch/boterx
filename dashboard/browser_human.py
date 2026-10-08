"""
VEX Browser Human Behavior Simulator
Makes browser interactions indistinguishable from real human usage.
"""
import random, time, math, hashlib
from datetime import datetime


class HumanBehavior:
    """Simulates real human browsing patterns."""

    def __init__(self):
        self._session_start = time.time()
        self._pages_visited = 0
        self._actions_count = 0
        self._last_action_time = 0
        self._break_interval = random.randint(600, 1200)  # 10-20 min
        self._break_duration = random.randint(30, 120)     # 30s-2min
        self._in_break = False
        self._break_until = 0

    def _ms(self, min_ms, max_ms):
        return random.uniform(min_ms, max_ms)

    # ── Mouse Movement ────────────────────────────────────────

    def mouse_path(self, from_x, from_y, to_x, to_y):
        """Generate Bezier curve points for natural mouse movement."""
        points = []
        dist = math.hypot(to_x - from_x, to_y - from_y)
        steps = max(5, int(dist / 30))

        # Control points for bezier curve
        cx1 = from_x + (to_x - from_x) * 0.3 + random.uniform(-50, 50)
        cy1 = from_y + (to_y - from_y) * 0.1 + random.uniform(-30, 30)
        cx2 = from_x + (to_x - from_x) * 0.7 + random.uniform(-50, 50)
        cy2 = from_y + (to_y - from_y) * 0.9 + random.uniform(-30, 30)

        for i in range(steps + 1):
            t = i / steps
            # Cubic bezier
            x = (1-t)**3*from_x + 3*(1-t)**2*t*cx1 + 3*(1-t)*t**2*cx2 + t**3*to_x
            y = (1-t)**3*from_y + 3*(1-t)**2*t*cy1 + 3*(1-t)*t**2*cy2 + t**3*to_y
            # Add micro-jitter
            x += random.uniform(-1.5, 1.5)
            y += random.uniform(-1.5, 1.5)
            points.append((round(x, 1), round(y, 1)))

        # Occasionally overshoot and correct
        if random.random() < 0.15:
            overshoot_x = to_x + random.uniform(-10, 10)
            overshoot_y = to_y + random.uniform(-10, 10)
            points.append((round(overshoot_x, 1), round(overshoot_y, 1)))
            points.append((round(to_x + random.uniform(-2, 2), 1),
                          round(to_y + random.uniform(-2, 2), 1)))
            points.append((round(to_x, 1), round(to_y, 1)))

        return points

    def mouse_move_delay(self, distance):
        """Return delay between mouse moves based on distance."""
        base = 8 + distance * 0.05
        return self._ms(base, base * 2.5) / 1000.0

    def click_position_offset(self, box):
        """Generate human-like click position within element bounds."""
        if not box:
            return 0, 0
        # Don't click exactly center — humans rarely do
        cx = box.get('x', 0) + box.get('width', 0) * random.uniform(0.25, 0.75)
        cy = box.get('y', 0) + box.get('height', 0) * random.uniform(0.2, 0.8)
        return cx, cy

    def click_delay(self):
        """Delay before and after click."""
        pre = self._ms(80, 300) / 1000.0
        post = self._ms(100, 500) / 1000.0
        return pre, post

    # ── Typing ────────────────────────────────────────────────

    def type_char_delay(self, char):
        """Per-character typing delay."""
        if char == ' ':
            return self._ms(80, 250) / 1000.0
        if char in '.,!?;:':
            return self._ms(150, 400) / 1000.0
        # Occasional longer pause (thinking)
        if random.random() < 0.03:
            return self._ms(500, 1500) / 1000.0
        return self._ms(40, 180) / 1000.0

    def should_make_typo(self, char):
        """Whether to simulate a typo (5% chance)."""
        if not char.isalpha():
            return False
        return random.random() < 0.05

    def get_typo_char(self, char):
        """Get a nearby key on keyboard for typo simulation."""
        keyboard_map = {
            'a': 'sqwz', 'b': 'vngh', 'c': 'xdfv', 'd': 'sfcer',
            'e': 'wsdr', 'f': 'dgcv', 'g': 'fhbv', 'h': 'gjbn',
            'i': 'uokj', 'j': 'hknm', 'k': 'jlmi', 'l': 'kop',
            'm': 'njk', 'n': 'bmhj', 'o': 'iplk', 'p': 'ol',
            'q': 'wa', 'r': 'edtf', 's': 'awedx', 't': 'rfgy',
            'u': 'yhji', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc',
            'y': 'tghu', 'z': 'asx',
        }
        neighbors = keyboard_map.get(char.lower(), '')
        if neighbors:
            return random.choice(neighbors)
        return char

    def word_pause(self):
        """Pause between words."""
        return self._ms(100, 400) / 1000.0

    def think_pause(self):
        """Longer pause simulating thinking."""
        return self._ms(800, 3000) / 1000.0

    # ── Scrolling ─────────────────────────────────────────────

    def scroll_amount(self):
        """Random scroll distance."""
        weights = [1, 2, 3, 5, 8, 13]
        weights = weights[:len(weights)-1]
        return random.choices([200, 350, 500, 700, 900], weights=[5, 10, 8, 4, 1])[0]

    def scroll_delay(self):
        """Delay between scroll actions."""
        return self._ms(200, 800) / 1000.0

    def should_scroll_back(self):
        """Sometimes scroll back up (reading pattern)."""
        return random.random() < 0.12

    def scroll_pause_duration(self):
        """Simulate reading pause while scrolling."""
        return self._ms(1000, 4000) / 1000.0

    # ── Session Behavior ──────────────────────────────────────

    def should_take_break(self):
        """Check if it's time for a break."""
        elapsed = time.time() - self._session_start
        if elapsed > self._break_interval and not self._in_break:
            self._in_break = True
            self._break_until = time.time() + self._break_duration
            return True
        return False

    def is_in_break(self):
        """Currently on break?"""
        if self._in_break and time.time() >= self._break_until:
            self._in_break = False
            self._break_interval = time.time() + random.randint(600, 1200)
            return False
        return self._in_break

    def should_visit_random_site(self):
        """Occasionally visit a random popular site (looks human)."""
        return random.random() < 0.02  # 2% chance per action

    def random_site(self):
        """Random popular website."""
        sites = [
            'https://www.google.com', 'https://www.wikipedia.org',
            'https://news.ycombinator.com', 'https://www.bbc.com',
            'https://www.reddit.com', 'https://www.stackoverflow.com',
            'https://www.medium.com', 'https://github.com',
            'https://www.youtube.com', 'https://www.amazon.com',
        ]
        return random.choice(sites)

    def session_duration_target(self):
        """How long a realistic session should last (minutes)."""
        return random.randint(15, 45)

    def record_action(self):
        """Record an action for session tracking."""
        self._actions_count += 1
        self._last_action_time = time.time()

    def idle_time(self):
        """Time since last action."""
        return time.time() - self._last_action_time if self._last_action_time else 0

    # ── Content Interaction ───────────────────────────────────

    def reading_time(self, text_length):
        """Simulate reading time based on content length."""
        words = text_length / 5  # ~5 chars per word
        wpm = random.randint(200, 300)  # words per minute
        return (words / wpm) * 60

    def hover_before_click(self):
        """Time to hover over element before clicking."""
        return self._ms(200, 800) / 1000.0

    def double_check_delay(self):
        """Pause to 'verify' before submitting."""
        return self._ms(500, 2000) / 1000.0

    def page_load_wait(self):
        """Wait after page load before interacting."""
        return self._ms(800, 2500) / 1000.0

    # ── Fingerprint ───────────────────────────────────────────

    def get_fingerprint(self):
        """Generate a consistent human fingerprint for this session."""
        seed = int(self._session_start * 1000) % 1000000
        rng = random.Random(seed)
        return {
            'typing_speed': round(rng.uniform(0.04, 0.15), 3),
            'click_timing': round(rng.uniform(0.1, 0.4), 3),
            'scroll_style': rng.choice(['fast', 'moderate', 'careful']),
            'reading_speed': rng.randint(180, 320),
            'mouse_smoothness': round(rng.uniform(0.7, 1.0), 2),
            'error_rate': round(rng.uniform(0.02, 0.08), 3),
            'break_frequency': rng.randint(600, 1200),
        }
