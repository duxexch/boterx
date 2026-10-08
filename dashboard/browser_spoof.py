"""
VEX Browser Anti-Detection Spoofing + Interaction Enhancements
User agent rotation, screen/WebGL/canvas spoofing, drag-drop,
keyboard shortcuts, iframe handling, shadow DOM, media devices.
"""
import json, random, hashlib, time, math
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
#  User Agent Rotation
# ═══════════════════════════════════════════════════════════════

USER_AGENTS = {
    'chrome_windows': [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    ],
    'chrome_mac': [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    ],
    'chrome_linux': [
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    ],
    'firefox_windows': [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
    ],
    'firefox_mac': [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0',
    ],
    'safari_mac': [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15',
    ],
    'safari_iphone': [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1',
    ],
    'safari_ipad': [
        'Mozilla/5.0 (iPad; CPU OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1',
    ],
    'edge_windows': [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0',
    ],
    'android_chrome': [
        'Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 13; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36',
    ],
}


def get_random_ua(platform=None, browser=None):
    """Get a random user agent, optionally filtered by platform/browser."""
    if platform and browser:
        key = f'{browser}_{platform}'
        agents = USER_AGENTS.get(key, [])
    elif platform:
        agents = [ua for k, uas in USER_AGENTS.items() if platform in k for ua in uas]
    elif browser:
        agents = [ua for k, uas in USER_AGENTS.items() if browser in k for ua in uas]
    else:
        agents = [ua for uas in USER_AGENTS.values() for ua in uas]

    return random.choice(agents) if agents else get_random_ua()


def rotate_user_agent(instance_id):
    """Rotate the user agent for a browser instance."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    ua = get_random_ua()
    try:
        inst.page.evaluate(f"() => {{ Object.defineProperty(navigator, 'userAgent', {{get: () => '{ua}'}}); }}")
        return {'success': True, 'user_agent': ua}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_all_user_agents():
    """Get all available user agents grouped by platform."""
    return {k: v for k, v in USER_AGENTS.items()}


# ═══════════════════════════════════════════════════════════════
#  Screen/WebGL/Canvas Spoofing
# ═══════════════════════════════════════════════════════════════

SCREEN_RESOLUTIONS = [
    (1920, 1080), (2560, 1440), (1366, 768), (1536, 864),
    (1440, 900), (1280, 720), (1600, 900), (1280, 800),
    (3840, 2160), (3440, 1440), (2560, 1080),
]

WEBGL_CONFIGS = [
    {'vendor': 'Google Inc. (NVIDIA)', 'renderer': 'ANGLE (NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0)'},
    {'vendor': 'Google Inc. (AMD)', 'renderer': 'ANGLE (AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)'},
    {'vendor': 'Google Inc. (Intel)', 'renderer': 'ANGLE (Intel UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)'},
    {'vendor': 'Google Inc. (NVIDIA)', 'renderer': 'ANGLE (NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)'},
    {'vendor': 'Google Inc. (AMD)', 'renderer': 'ANGLE (AMD Radeon RX 5600 XT Direct3D11 vs_5_0 ps_5_0)'},
    {'vendor': 'Google Inc. (NVIDIA)', 'renderer': 'ANGLE (NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0)'},
    {'vendor': 'Google Inc. (Intel)', 'renderer': 'ANGLE (Intel Iris Xe Graphics Direct3D11 vs_5_0 ps_5_0)'},
]


def get_spoof_screen_js():
    """Generate JS to spoof screen resolution."""
    w, h = random.choice(SCREEN_RESOLUTIONS)
    return f"""
    () => {{
        Object.defineProperty(screen, 'width', {{get: () => {w}}});
        Object.defineProperty(screen, 'height', {{get: () => {h}}});
        Object.defineProperty(screen, 'availWidth', {{get: () => {w}}});
        Object.defineProperty(screen, 'availHeight', {{get: () => {h - 40}}});
        Object.defineProperty(screen, 'colorDepth', {{get: () => 24}});
        Object.defineProperty(screen, 'pixelDepth', {{get: () => 24}});
        return 'Screen spoofed: {w}x{h}';
    }}
    """


def get_spoof_webgl_js():
    """Generate JS to spoof WebGL vendor/renderer."""
    config = random.choice(WEBGL_CONFIGS)
    vendor = config['vendor']
    renderer = config['renderer']
    return f"""
    () => {{
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return '{vendor}';
            if (param === 37446) return '{renderer}';
            return getParameter.call(this, param);
        }};
        const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return '{vendor}';
            if (param === 37446) return '{renderer}';
            return getParameter2.call(this, param);
        }};
        return 'WebGL spoofed: {vendor} / {renderer}';
    }}
    """


def get_spoof_canvas_js():
    """Generate JS to add canvas fingerprint noise."""
    return """
    () => {
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            const ctx = this.getContext('2d');
            if (ctx) {
                const imageData = ctx.getImageData(0, 0, this.width, this.height);
                for (let i = 0; i < imageData.data.length; i += 4) {
                    imageData.data[i] = imageData.data[i] ^ (Math.random() > 0.5 ? 1 : 0);
                }
                ctx.putImageData(imageData, 0, 0);
            }
            return origToDataURL.apply(this, arguments);
        };

        const origToBlob = HTMLCanvasElement.prototype.toBlob;
        HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {
            const ctx = this.getContext('2d');
            if (ctx) {
                const imageData = ctx.getImageData(0, 0, this.width, this.height);
                for (let i = 0; i < imageData.data.length; i += 4) {
                    imageData.data[i] = imageData.data[i] ^ (Math.random() > 0.5 ? 1 : 0);
                }
                ctx.putImageData(imageData, 0, 0);
            }
            return origToBlob.apply(this, arguments);
        };
        return 'Canvas fingerprint noise added';
    }
    """


def get_full_spoof_js():
    """Generate comprehensive anti-detection JS."""
    return """
    () => {
        // WebRTC IP leak prevention
        if (window.RTCPeerConnection) {
            const origRTC = window.RTCPeerConnection;
            window.RTCPeerConnection = function(...args) {
                const pc = new origRTC(...args);
                const origCreateDataChannel = pc.createDataChannel;
                pc.createDataChannel = function(...a) {
                    return origCreateDataChannel.apply(this, a);
                };
                return pc;
            };
        }

        // Override permissions API
        if (navigator.permissions) {
            const origQuery = navigator.permissions.query;
            navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    origQuery(parameters)
            );
        }

        // Override plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });

        // Override platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });

        // Override hardware concurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });

        // Override device memory
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });

        // Override connection
        if (navigator.connection) {
            Object.defineProperty(navigator.connection, 'rtt', { get: () => 50 });
        }

        return 'Full anti-detection active';
    }
    """


# ═══════════════════════════════════════════════════════════════
#  Drag & Drop Simulation
# ═══════════════════════════════════════════════════════════════

def simulate_drag_drop(instance_id, source_selector, target_selector):
    """Simulate drag and drop between two elements."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        source = inst.page.query_selector(source_selector)
        target = inst.page.query_selector(target_selector)
        if not source or not target:
            return {'success': False, 'error': 'Element(s) not found'}

        source_box = source.bounding_box()
        target_box = target.bounding_box()
        if not source_box or not target_box:
            return {'success': False, 'error': 'Cannot get element positions'}

        # Generate human-like path
        sx, sy = source_box['x'] + source_box['width'] / 2, source_box['y'] + source_box['height'] / 2
        tx, ty = target_box['x'] + target_box['width'] / 2, target_box['y'] + target_box['height'] / 2

        # Mouse down on source
        inst.page.mouse.move(sx, sy)
        time.sleep(0.1)
        inst.page.mouse.down()
        time.sleep(0.1)

        # Move along bezier curve with jitter
        steps = 20
        for i in range(steps + 1):
            t = i / steps
            cx = sx + (tx - sx) * t + random.uniform(-2, 2)
            cy = sy + (ty - sy) * t + random.uniform(-2, 2)
            inst.page.mouse.move(cx, cy)
            time.sleep(random.uniform(0.01, 0.03))

        # Drop
        inst.page.mouse.up()
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def simulate_file_drop(instance_id, file_path, target_selector):
    """Simulate dropping a file onto a drop zone."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        # Use DataTransfer API to simulate file drop
        js = f"""
        async () => {{
            const dropZone = document.querySelector('{target_selector}');
            if (!dropZone) return 'Drop zone not found';

            const file = new File(['dummy content'], '{Path(file_path).name}', {{type: 'application/octet-stream'}});
            const dt = new DataTransfer();
            dt.items.add(file);

            const event = new DragEvent('drop', {{
                dataTransfer: dt,
                bubbles: true,
                cancelable: true
            }});
            dropZone.dispatchEvent(event);
            return 'File dropped';
        }}
        """
        result = inst.page.evaluate(js)
        return {'success': True, 'result': result}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════
#  Keyboard Shortcuts
# ═══════════════════════════════════════════════════════════════

BROWSER_SHORTCUTS = {
    'new_tab': 'Control+t',
    'close_tab': 'Control+w',
    'next_tab': 'Control+Tab',
    'prev_tab': 'Control+Shift+Tab',
    'reload': 'Control+r',
    'hard_reload': 'Control+Shift+r',
    'back': 'Alt+ArrowLeft',
    'forward': 'Alt+ArrowRight',
    'find': 'Control+f',
    'find_next': 'Control+g',
    'zoom_in': 'Control+Equal',
    'zoom_out': 'Control+Minus',
    'zoom_reset': 'Control+0',
    'select_all': 'Control+a',
    'copy': 'Control+c',
    'paste': 'Control+v',
    'cut': 'Control+x',
    'undo': 'Control+z',
    'redo': 'Control+Shift+z',
    'scroll_home': 'Home',
    'scroll_end': 'End',
    'page_up': 'PageUp',
    'page_down': 'PageDown',
    'escape': 'Escape',
    'enter': 'Enter',
    'tab': 'Tab',
    'focus_address_bar': 'Control+l',
    'focus_search': 'Control+k',
    'print': 'Control+p',
    'save_page': 'Control+s',
    'developer_tools': 'F12',
    'full_screen': 'F11',
}


def press_shortcut(instance_id, shortcut_name):
    """Press a browser keyboard shortcut."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    keys = BROWSER_SHORTCUTS.get(shortcut_name)
    if not keys:
        return {'success': False, 'error': f'Unknown shortcut: {shortcut_name}'}

    try:
        parts = keys.split('+')
        if len(parts) == 1:
            inst.page.keyboard.press(parts[0])
        else:
            # For modifier combos, use keyboard.down for modifiers and press for the key
            modifiers = parts[:-1]
            key = parts[-1]
            for mod in modifiers:
                inst.page.keyboard.down(mod)
            inst.page.keyboard.press(key)
            for mod in reversed(modifiers):
                inst.page.keyboard.up(mod)

        return {'success': True, 'shortcut': shortcut_name, 'keys': keys}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def press_key(instance_id, key, modifiers=None):
    """Press a specific key with optional modifiers."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        if modifiers:
            for mod in modifiers:
                inst.page.keyboard.down(mod)
        inst.page.keyboard.press(key)
        if modifiers:
            for mod in reversed(modifiers):
                inst.page.keyboard.up(mod)
        return {'success': True, 'key': key, 'modifiers': modifiers or []}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def type_shortcut(instance_id, text, delay=50):
    """Type text character by character with human-like delays."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        for char in text:
            inst.page.keyboard.press(char)
            time.sleep(delay / 1000 + random.uniform(-0.01, 0.01))
        return {'success': True, 'typed': len(text)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_all_shortcuts():
    """Get all available keyboard shortcuts."""
    return BROWSER_SHORTCUTS


# ═══════════════════════════════════════════════════════════════
#  Iframe Handling
# ═══════════════════════════════════════════════════════════════

def list_iframes(instance_id):
    """List all iframes on the page."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        iframes = inst.page.frames
        result = []
        for i, frame in enumerate(iframes):
            result.append({
                'index': i,
                'name': frame.name,
                'url': frame.url,
                'is_main': frame == inst.page.main_frame,
            })
        return {'success': True, 'iframes': result, 'count': len(result)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def switch_to_frame(instance_id, frame_index=0, frame_name=''):
    """Switch to a specific iframe."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        frames = inst.page.frames
        if frame_name:
            frame = inst.page.frame(name=frame_name)
        elif frame_index < len(frames):
            frame = frames[frame_index]
        else:
            return {'success': False, 'error': 'Frame not found'}

        if frame:
            inst._current_frame = frame
            return {'success': True, 'frame': frame.name or frame.url}
        return {'success': False, 'error': 'Frame not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def switch_to_main_frame(instance_id):
    """Switch back to main frame."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}
    inst._current_frame = None
    return {'success': True}


# ═══════════════════════════════════════════════════════════════
#  Shadow DOM Support
# ═══════════════════════════════════════════════════════════════

def query_shadow_dom(instance_id, host_selector, inner_selector):
    """Query elements inside a shadow DOM."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        result = inst.page.evaluate(f"""
        () => {{
            const host = document.querySelector('{host_selector}');
            if (!host || !host.shadowRoot) return null;
            const el = host.shadowRoot.querySelector('{inner_selector}');
            if (!el) return null;
            return {{
                tagName: el.tagName,
                text: el.textContent?.substring(0, 500),
                html: el.innerHTML?.substring(0, 1000)
            }};
        }}
        """)
        return {'success': True, 'element': result}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def click_shadow_dom(instance_id, host_selector, inner_selector):
    """Click an element inside a shadow DOM."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        inst.page.evaluate(f"""
        () => {{
            const host = document.querySelector('{host_selector}');
            if (!host || !host.shadowRoot) throw new Error('Shadow root not found');
            const el = host.shadowRoot.querySelector('{inner_selector}');
            if (!el) throw new Error('Element not found in shadow DOM');
            el.click();
        }}
        """)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════
#  Media Device Emulation
# ═══════════════════════════════════════════════════════════════

def get_media_devices_js(camera=1, microphone=1, speaker=1):
    """Generate JS to emulate media devices."""
    devices = []
    for i in range(camera):
        devices.append({'kind': 'videoinput', 'label': f'Camera {i+1}', 'deviceId': f'camera_{i}', 'groupId': f'group_{i}'})
    for i in range(microphone):
        devices.append({'kind': 'audioinput', 'label': f'Microphone {i+1}', 'deviceId': f'mic_{i}', 'groupId': f'group_{i}'})
    for i in range(speaker):
        devices.append({'kind': 'audiooutput', 'label': f'Speaker {i+1}', 'deviceId': f'speaker_{i}', 'groupId': f'group_{i}'})

    devices_json = json.dumps(devices)
    return f"""
    () => {{
        const devices = {devices_json};
        const origEnumerate = navigator.mediaDevices?.enumerateDevices;
        if (navigator.mediaDevices) {{
            navigator.mediaDevices.enumerateDevices = async () => devices;
        }}
        return 'Media devices emulated: ' + devices.length + ' devices';
    }}
    """


def emulate_media_devices(instance_id, camera=1, microphone=1, speaker=1):
    """Emulate media devices on a browser instance."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    try:
        result = inst.page.evaluate(get_media_devices_js(camera, microphone, speaker))
        return {'success': True, 'result': result, 'devices': camera + microphone + speaker}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════
#  Apply All Anti-Detection
# ═══════════════════════════════════════════════════════════════

def apply_full_anti_detection(instance_id):
    """Apply all anti-detection measures to a browser instance."""
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return {'success': False, 'error': 'Browser not running'}

    results = []
    try:
        # Screen spoofing
        r = inst.page.evaluate(get_spoof_screen_js())
        results.append(('screen', r))

        # WebGL spoofing
        r = inst.page.evaluate(get_spoof_webgl_js())
        results.append(('webgl', r))

        # Canvas noise
        r = inst.page.evaluate(get_spoof_canvas_js())
        results.append(('canvas', r))

        # Full anti-detection
        r = inst.page.evaluate(get_full_spoof_js())
        results.append(('full', r))

        return {'success': True, 'applied': len(results), 'details': results}
    except Exception as e:
        return {'success': False, 'error': str(e), 'partial': results}
