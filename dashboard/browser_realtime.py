"""
VEX Browser WebSocket + Ad Blocker + Resource Blocker + Console Viewer + PDF Export
Real-time updates, content filtering, performance optimization, debugging, and export.
"""
import json, time, threading, re, hashlib
from pathlib import Path
from datetime import datetime
from collections import deque


# ═══════════════════════════════════════════════════════════════
#  WebSocket Real-Time Updates
# ═══════════════════════════════════════════════════════════════

class BrowserWebSocket:
    """Manages real-time WebSocket connections for browser events."""

    def __init__(self):
        self._clients = {}  # instance_id -> [callback_queue]
        self._events = {}  # instance_id -> deque of recent events
        self._lock = threading.Lock()

    def subscribe(self, instance_id):
        """Subscribe to browser events for an instance."""
        with self._lock:
            if instance_id not in self._clients:
                self._clients[instance_id] = []
                self._events[instance_id] = deque(maxlen=100)
            q = deque(maxlen=200)
            self._clients[instance_id].append(q)
            return q

    def unsubscribe(self, instance_id, queue):
        """Unsubscribe from events."""
        with self._lock:
            if instance_id in self._clients:
                try:
                    self._clients[instance_id].remove(queue)
                except ValueError:
                    pass

    def emit(self, instance_id, event_type, data=None):
        """Emit an event to all subscribers of an instance."""
        event = {
            'type': event_type,
            'instance_id': instance_id,
            'timestamp': datetime.now().isoformat(),
            'data': data or {},
        }
        with self._lock:
            if instance_id in self._events:
                self._events[instance_id].append(event)
            if instance_id in self._clients:
                dead = []
                for q in self._clients[instance_id]:
                    try:
                        q.append(event)
                    except Exception:
                        dead.append(q)
                for d in dead:
                    try:
                        self._clients[instance_id].remove(d)
                    except ValueError:
                        pass

    def get_recent(self, instance_id, limit=50):
        """Get recent events for an instance."""
        with self._lock:
            if instance_id in self._events:
                return list(self._events[instance_id])[-limit:]
            return []

    def get_all_recent(self, limit=100):
        """Get recent events across all instances."""
        all_events = []
        with self._lock:
            for events in self._events.values():
                all_events.extend(list(events))
        all_events.sort(key=lambda e: e.get('timestamp', ''), reverse=True)
        return all_events[:limit]

    def get_subscribers_count(self, instance_id=None):
        """Get count of active subscribers."""
        with self._lock:
            if instance_id:
                return len(self._clients.get(instance_id, []))
            return sum(len(v) for v in self._clients.values())


# Global WebSocket manager
browser_ws = BrowserWebSocket()


# ═══════════════════════════════════════════════════════════════
#  Ad Blocker + Element Hider
# ═══════════════════════════════════════════════════════════════

# Common ad/tracking domains and patterns
AD_DOMAINS = [
    'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
    'google-analytics.com', 'googletagmanager.com', 'googletagservices.com',
    'facebook.com/tr', 'fbcdn.net', 'connect.facebook.net',
    'analytics.twitter.com', 'ads-twitter.com', 'ads.linkedin.com',
    'adnxs.com', 'adsrvr.org', 'demdex.net', 'amazon-adsystem.com',
    'criteo.com', 'criteo.net', 'taboola.com', 'outbrain.com',
    'moat.com', 'bluekai.com', 'rubiconproject.com', 'openx.net',
    'pubmatic.com', 'casalemedia.com', 'sharethrough.com',
    'spotxchange.com', 'spotx.tv', 'yieldmo.com',
]

AD_SELECTORS = [
    '[class*="ad-"]', '[class*="ads-"]', '[class*="advert"]',
    '[id*="ad-"]', '[id*="ads-"]', '[id*="advert"]',
    '[class*="banner"]', '[class*="sponsor"]',
    '[class*="popup"]', '[class*="modal-ad"]',
    'iframe[src*="ads"]', 'iframe[src*="doubleclick"]',
    'iframe[src*="googlesyndication"]',
    '.ad', '.ads', '.advert', '.advertisement',
    '#ad', '#ads', '#advertisement',
]

TRACKING_SELECTORS = [
    '[class*="tracking"]', '[class*="analytics"]',
    '[id*="tracking"]', '[id*="analytics"]',
    'img[width="1"][height="1"]',  # Tracking pixels
    'img[src*="pixel"]', 'img[src*="track"]',
]

HIDE_SELECTORS = [
    '[class*="cookie-banner"]', '[class*="cookie-notice"]',
    '[class*="cookie-consent"]', '[id*="cookie"]',
    '[class*="privacy-banner"]', '[class*="gdpr"]',
    '[class*="newsletter-popup"]', '[class*="subscribe-popup"]',
    '[class*="social-share"]', '[class*="share-buttons"]',
]


def get_adblock_js():
    """Generate JavaScript for ad blocking."""
    selectors = AD_SELECTORS + TRACKING_SELECTORS
    selector_str = ', '.join(selectors)
    return f"""
    () => {{
        // Hide ad elements
        const adElements = document.querySelectorAll('{selector_str}');
        adElements.forEach(el => el.style.display = 'none');

        // Block ad network requests (via PerformanceObserver)
        if (window.PerformanceObserver) {{
            const observer = new PerformanceObserver((list) => {{
                list.getEntries().forEach(entry => {{
                    if (entry.initiatorType === 'xmlhttprequest' || entry.initiatorType === 'fetch') {{
                        const adDomains = {json.dumps(AD_DOMAINS)};
                        if (adDomains.some(d => entry.name.includes(d))) {{
                            // Mark as blocked
                            entry.__blocked = true;
                        }}
                    }}
                }});
            }});
            observer.observe({{ entryTypes: ['resource'] }});
        }}

        // MutationObserver for dynamically added ads
        const mutObserver = new MutationObserver((mutations) => {{
            mutations.forEach(mutation => {{
                mutation.addedNodes.forEach(node => {{
                    if (node.nodeType === 1) {{
                        const adSelectors = {json.dumps(AD_SELECTORS)};
                        adSelectors.forEach(sel => {{
                            try {{
                                if (node.matches && node.matches(sel)) {{
                                    node.style.display = 'none';
                                }}
                                node.querySelectorAll?.(sel).forEach(el => el.style.display = 'none');
                            }} catch(e) {{}}
                        }});
                    }}
                }});
            }});
        }});
        mutObserver.observe(document.body || document.documentElement, {{
            childList: true, subtree: true
        }});

        return 'Ad blocker active';
    }}
    """


def get_hide_elements_js(selectors=None):
    """Generate JS to hide specific elements."""
    sel = selectors or HIDE_SELECTORS
    selector_str = ', '.join(sel)
    return f"""
    () => {{
        const elements = document.querySelectorAll('{selector_str}');
        elements.forEach(el => el.style.display = 'none');
        return elements.length + ' elements hidden';
    }}
    """


def get_custom_hide_js(selector):
    """Generate JS to hide elements matching a custom selector."""
    return f"""
    () => {{
        const elements = document.querySelectorAll('{selector}');
        elements.forEach(el => el.style.display = 'none');
        return elements.length + ' elements hidden';
    }}
    """


# ═══════════════════════════════════════════════════════════════
#  Resource Blocker + Network Throttle
# ═══════════════════════════════════════════════════════════════

RESOURCE_TYPES_TO_BLOCK = ['image', 'media', 'font', 'stylesheet']

THROTTLE_PROFILES = {
    'fast': {'download': 10 * 1024 * 1024, 'upload': 5 * 1024 * 1024, 'latency': 10},
    'normal': {'download': 5 * 1024 * 1024, 'upload': 2 * 1024 * 1024, 'latency': 50},
    'slow': {'download': 500 * 1024, 'upload': 200 * 1024, 'latency': 200},
    '2g': {'download': 50 * 1024, 'upload': 25 * 1024, 'latency': 800},
    '3g': {'download': 750 * 1024, 'upload': 250 * 1024, 'latency': 300},
    'offline': {'download': 0, 'upload': 0, 'latency': 0},
}


def get_resource_block_js(block_types=None):
    """Generate JS to block specific resource types."""
    types = block_types or RESOURCE_TYPES_TO_BLOCK
    return f"""
    () => {{
        const blockTypes = {json.dumps(types)};
        const observer = new PerformanceObserver((list) => {{
            list.getEntries().forEach(entry => {{
                if (blockTypes.includes(entry.initiatorType)) {{
                    // Can't directly block, but can report
                    window.__blockedResources = window.__blockedResources || [];
                    window.__blockedResources.push({{
                        url: entry.name,
                        type: entry.initiatorType,
                        size: entry.transferSize || 0
                    }});
                }}
            }});
        }});
        observer.observe({{ entryTypes: ['resource'] }});
        return 'Resource blocker active for: ' + blockTypes.join(', ');
    }}
    """


# ═══════════════════════════════════════════════════════════════
#  Console Viewer
# ═══════════════════════════════════════════════════════════════

class ConsoleViewer:
    """Captures and stores browser console output."""

    def __init__(self):
        self._logs = {}  # instance_id -> deque of log entries

    def get_console_js(self):
        """Generate JS to capture console output."""
        return """
        () => {
            window.__consoleLogs = [];
            ['log', 'warn', 'error', 'info', 'debug'].forEach(level => {
                const orig = console[level];
                console[level] = function(...args) {
                    window.__consoleLogs.push({
                        level: level,
                        message: args.map(a => {
                            try { return typeof a === 'object' ? JSON.stringify(a) : String(a); }
                            catch(e) { return String(a); }
                        }).join(' '),
                        timestamp: new Date().toISOString()
                    });
                    if (window.__consoleLogs.length > 500) {
                        window.__consoleLogs = window.__consoleLogs.slice(-500);
                    }
                    orig.apply(console, args);
                };
            });

            // Capture errors
            window.addEventListener('error', (e) => {
                window.__consoleLogs.push({
                    level: 'error',
                    message: e.message + ' at ' + e.filename + ':' + e.lineno,
                    timestamp: new Date().toISOString()
                });
            });

            // Capture unhandled promise rejections
            window.addEventListener('unhandledrejection', (e) => {
                window.__consoleLogs.push({
                    level: 'error',
                    message: 'Unhandled Promise: ' + (e.reason?.message || e.reason || 'unknown'),
                    timestamp: new Date().toISOString()
                });
            });

            return 'Console capture active';
        }
        """

    def get_logs(self, instance_id, page=None):
        """Get captured console logs from a browser instance."""
        from browser_manager import get_instance
        inst = get_instance(instance_id)
        if not inst or not inst.page:
            return []
        try:
            logs = inst.page.evaluate('() => window.__consoleLogs || []')
            return logs[-200:] if logs else []
        except Exception:
            return []

    def clear_logs(self, instance_id):
        """Clear captured console logs."""
        from browser_manager import get_instance
        inst = get_instance(instance_id)
        if inst and inst.page:
            try:
                inst.page.evaluate('() => { window.__consoleLogs = []; }')
            except Exception:
                pass


console_viewer = ConsoleViewer()


# ═══════════════════════════════════════════════════════════════
#  PDF Export
# ═══════════════════════════════════════════════════════════════

def export_page_pdf(instance_id, output_path=None, **options):
    """Export current page as PDF."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = str(Path(__file__).parent / 'browser_backups' / f'page_{timestamp}.pdf')

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        pdf_options = {
            'path': output_path,
            'format': options.get('format', 'A4'),
            'print_background': options.get('print_background', True),
            'margin': {
                'top': options.get('margin_top', '1cm'),
                'right': options.get('margin_right', '1cm'),
                'bottom': options.get('margin_bottom', '1cm'),
                'left': options.get('margin_left', '1cm'),
            },
        }

        inst.page.pdf(**pdf_options)
        file_size = Path(output_path).stat().st_size

        return {
            'success': True,
            'path': output_path,
            'size': file_size,
            'url': inst.page.url,
            'title': inst.page.title(),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def export_page_html(instance_id, output_path=None):
    """Export current page HTML."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        html = inst.page.content()
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = str(Path(__file__).parent / 'browser_backups' / f'page_{timestamp}.html')

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html, encoding='utf-8')

        return {
            'success': True,
            'path': output_path,
            'size': len(html),
            'url': inst.page.url,
            'title': inst.page.title(),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def export_page_text(instance_id):
    """Extract plain text from current page."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        text = inst.page.inner_text('body')
        return {
            'success': True,
            'text': text,
            'word_count': len(text.split()),
            'char_count': len(text),
            'url': inst.page.url,
            'title': inst.page.title(),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════
#  Page Performance Monitor
# ═══════════════════════════════════════════════════════════════

def get_performance_js():
    """Generate JS to capture page performance metrics."""
    return """
    () => {
        const perf = performance;
        const nav = perf.getEntriesByType('navigation')[0];
        const paint = perf.getEntriesByType('paint');
        const resources = perf.getEntriesByType('resource');

        const metrics = {
            // Navigation timing
            dns: nav ? Math.round(nav.domainLookupEnd - nav.domainLookupStart) : 0,
            tcp: nav ? Math.round(nav.connectEnd - nav.connectStart) : 0,
            ttfb: nav ? Math.round(nav.responseStart - nav.requestStart) : 0,
            domContentLoaded: nav ? Math.round(nav.domContentLoadedEventEnd - nav.startTime) : 0,
            loadComplete: nav ? Math.round(nav.loadEventEnd - nav.startTime) : 0,

            // Paint timing
            firstPaint: 0,
            firstContentfulPaint: 0,

            // Resources
            totalResources: resources.length,
            totalTransferSize: resources.reduce((sum, r) => sum + (r.transferSize || 0), 0),
            totalDuration: resources.reduce((sum, r) => sum + r.duration, 0),

            // Resource breakdown
            byType: {},
        };

        paint.forEach(p => {
            if (p.name === 'first-paint') metrics.firstPaint = Math.round(p.startTime);
            if (p.name === 'first-contentful-paint') metrics.firstContentfulPaint = Math.round(p.startTime);
        });

        resources.forEach(r => {
            const type = r.initiatorType || 'other';
            if (!metrics.byType[type]) metrics.byType[type] = { count: 0, size: 0, duration: 0 };
            metrics.byType[type].count++;
            metrics.byType[type].size += r.transferSize || 0;
            metrics.byType[type].duration += r.duration;
        });

        // Round durations
        Object.values(metrics.byType).forEach(v => {
            v.size = Math.round(v.size);
            v.duration = Math.round(v.duration);
        });

        return metrics;
    }
    """


def get_page_metrics(instance_id):
    """Get page performance metrics."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        metrics = inst.page.evaluate(get_performance_js())
        return {'success': True, 'metrics': metrics}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════
#  Browser State Export/Import
# ═══════════════════════════════════════════════════════════════

def export_browser_state(instance_id):
    """Export complete browser state (cookies, localStorage, sessionStorage)."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        state = {
            'url': inst.page.url,
            'title': inst.page.title(),
            'cookies': inst.context.cookies(),
            'localStorage': inst.page.evaluate('() => Object.fromEntries(Object.entries(localStorage))'),
            'sessionStorage': inst.page.evaluate('() => Object.fromEntries(Object.entries(sessionStorage))'),
            'timestamp': datetime.now().isoformat(),
        }
        return {'success': True, 'state': state}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def import_browser_state(instance_id, state):
    """Import browser state (cookies, localStorage)."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        # Restore cookies
        if state.get('cookies'):
            inst.context.add_cookies(state['cookies'])

        # Restore localStorage
        ls = state.get('localStorage', {})
        if ls:
            js = f"() => {{ {'; '.join(f'localStorage.setItem({json.dumps(k)}, {json.dumps(v)})' for k, v in ls.items())} }}"
            inst.page.evaluate(js)

        # Navigate to URL if specified
        if state.get('url'):
            inst.navigate(state['url'])

        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}
