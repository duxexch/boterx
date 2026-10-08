"""
VEX News Monitor — مستكشف الأخبار الرياضية بالمتصفح (Playwright/Chromium)

كل10 دقائق (بدون flock مع التكرار):
1. يفتح مواقع الأخبار الرياضية المفعّلة (news_sources.csv).
2. يستخرج العناوين الجديدة ويطبّق فلاتر (طول، مواعيد المباريات، تكرار).
3. يرسل إشعار ويب لكل عنوان جديد (بحد أقصى4 إشعارات/دورة).
4. يجدول بوست ملخّص واحد للقنوات النشطة (منصات post_to_channels=yes،
   مع هامش15 دقيقة بين الملخصات).

المشترك: يُمرَّر push_notification/read_csv/append_csv/get_fieldnames من app.py
(يمنع الاستيراد الدائري بين news_monitor و app).
"""
import os
import csv
import json
import time
import threading
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # /opt/bot
SOURCES_FILE = os.path.join(BASE_DIR, 'news_sources.csv')
SEEN_FILE = os.path.join(BASE_DIR, 'news_seen.csv')
STATE_FILE = os.path.join(BASE_DIR, '.news_monitor_state.json')
LOCK_FILE = os.path.join(BASE_DIR, '.news_monitor.lock')

INTERVAL = 600            # كل10 دقائق
INITIAL_DELAY = 60        # انتظار اكتمال تحميل باقي الخيوط
MAX_ITEMS_PER_SOURCE = 6
MAX_PUSH_PER_CYCLE = 4
MAX_DIGEST_ITEMS = 6
MIN_DIGEST_GAP = 900      #15 دقيقة بين ملخصات القنوات

SOURCE_FIELDS = ['name', 'url', 'enabled', 'post_to_channels', 'last_check', 'last_status']
SEEN_FIELDS = ['hash', 'title', 'source', 'url', 'ts']

DEFAULT_SOURCES = [
    {'name': 'FilGoal', 'url': 'https://www.filgoal.com/', 'enabled': 'yes', 'post_to_channels': 'yes'},
    {'name': 'YallaKora', 'url': 'https://www.yallakora.com/', 'enabled': 'yes', 'post_to_channels': 'yes'},
    {'name': 'SkySports', 'url': 'https://www.skysports.com/', 'enabled': 'yes', 'post_to_channels': 'no'},
    {'name': 'BBC Sport', 'url': 'https://www.bbc.com/sport', 'enabled': 'yes', 'post_to_channels': 'no'},
]

_cb = {}
_log = []


def configure(**kwargs):
    _cb.update({k: v for k, v in kwargs.items() if v is not None})


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _read_csv(path, fields=None):
    fn = _cb.get('read_csv')
    if fn:
        try:
            return fn(os.path.basename(path))
        except Exception:
            pass
    rows = []
    try:
        with open(path, encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        pass
    return rows


def _append(path, entry, fields):
    fn = _cb.get('append_csv')
    if fn:
        try:
            fn(os.path.basename(path), entry, fields)
            return
        except Exception:
            pass
    file_exists = os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', restval='')
        if not file_exists:
            w.writeheader()
        w.writerow(entry)


def _get_fieldnames(path, default):
    fn = _cb.get('get_fieldnames')
    if fn:
        try:
            return fn(os.path.basename(path), default)
        except Exception:
            pass
    return default


def _push(ntype, title, message, data=None):
    fn = _cb.get('push_notification')
    if not fn:
        return
    try:
        fn(ntype, title, message, data or {})
    except Exception:
        pass


# ===== المصادر =====

def _load_sources():
    rows = _read_csv(SOURCES_FILE)
    if not rows:
        for s in DEFAULT_SOURCES:
            entry = dict(s)
            entry.update({'last_check': '', 'last_status': ''})
            _append(SOURCES_FILE, entry, SOURCE_FIELDS)
        rows = _read_csv(SOURCES_FILE)
    return rows


def _save_source_state(name, status):
    rows = _read_csv(SOURCES_FILE)
    changed = False
    for r in rows:
        if r.get('name') == name:
            r['last_check'] = _now()
            r['last_status'] = status[:180]
            changed = True
    if changed:
        tmp = SOURCES_FILE + '.tmp'
        with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=SOURCE_FIELDS, extrasaction='ignore', restval='')
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, '') for k in SOURCE_FIELDS})
        os.replace(tmp, SOURCES_FILE)


# ===== الرؤية (dedupe عبر الدورات) =====

def _load_seen():
    seen = set()
    for r in _read_csv(SEEN_FILE):
        h = r.get('hash')
        if h:
            seen.add(h)
    return seen


def _title_hash(title):
    import hashlib
    norm = re.sub(r'[^\w\u0600-\u06FF]+', '', title.lower())[:120]
    return hashlib.md5(norm.encode('utf-8', 'ignore')).hexdigest()


def _remember(title, source, url):
    entry = {'hash': _title_hash(title), 'title': title[:200], 'source': source,
             'url': url[:400], 'ts': _now()}
    _append(SEEN_FILE, entry, SEEN_FIELDS)


def _trim_seen():
    try:
        with open(SEEN_FILE, encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        if len(rows) > 2500:
            rows = rows[-2000:]
            with open(SEEN_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.DictWriter(f, fieldnames=SEEN_FIELDS)
                w.writeheader()
                w.writerows(rows)
    except Exception:
        pass


# ===== الاستخراج بالمتصفح =====

_EXTRACT_JS = """
() => {
  const out = [];
  const seen = new Set();
  const push = (a) => {
    if (!a) return;
    try {
      const text = (a.innerText || '').trim().replace(/\\s+/g, ' ');
      const href = a.href || '';
      if (!href.startsWith('http')) return;
      if (text.length < 35 || text.length > 260) return;
      if (!text.includes(' ')) return;
      try { if (new URL(href).pathname === '/') return; } catch (e) {}
      const key = text.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      out.push({t: text, u: href});
    } catch (e) {}
  };
  document.querySelectorAll('h1 a, h2 a, h3 a, article a, [class*=title] a, [class*=news] a')
    .forEach(el => push(el.tagName === 'A' ? el : el.querySelector('a')));
  if (out.length < 5) document.querySelectorAll('a').forEach(push);
  return out.slice(0, 12);
}
"""

_FIXTURE_RE = re.compile(r'\b\d{1,2}:\d{2}\b')
_TITLE_CLEAN_RE = re.compile(r'^خبر (?:في الجول|الفول|-)\s*[-–—]\s*')


def _clean_title(t):
    t = _TITLE_CLEAN_RE.sub('', t.strip())
    return t.strip(' -–—|')


def _filter_items(raw_items, seen):
    fresh = []
    for it in raw_items:
        title = _clean_title(str(it.get('t', '')))
        url = str(it.get('u', ''))
        if not title or not url:
            continue
        if _FIXTURE_RE.search(title):      # مواعيد مباريات (يومية كورة)
            continue
        if title.count('-') >= 6:          # قوائم/توصيفات
            continue
        h = _title_hash(title)
        if h in seen:
            continue
        seen.add(h)
        fresh.append({'title': title, 'url': url})
        if len(fresh) >= MAX_ITEMS_PER_SOURCE:
            break
    return fresh


def _scrape_all(sources):
    """متصفح واحد لكل الدورة — يرجع {name: [items]} ويحدّث حالة كل مصدر."""
    from playwright.sync_api import sync_playwright
    results = {}
    ua = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
                  '--disable-extensions', '--no-first-run'])
        ctx = browser.new_context(user_agent=ua, viewport={'width': 1366, 'height': 768},
                                  locale='ar-EG')
        for s in sources:
            name = (s.get('name') or '').strip()
            url = (s.get('url') or '').strip()
            if not name or not url or s.get('enabled') != 'yes':
                continue
            page = ctx.new_page()
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(4000)
                raw = page.evaluate(_EXTRACT_JS)
                results[name] = raw
                _save_source_state(name, f'ok — {len(raw)} items')
            except Exception as e:
                results[name] = []
                _save_source_state(name, f'error: {str(e)[:120]}')
            finally:
                try:
                    page.close()
                except Exception:
                    pass
        try:
            browser.close()
        except Exception:
            pass
    return results


# ===== الملخّص + الإشعارات =====

def _state_load():
    try:
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _state_save(state):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def _digest_message(items_by_source):
    """ملخّص جميل: عناوين مرقّمة + اسم المصدر فقط + روابط دوميناتنا (بدون روابط المصدر)."""
    import random as _rnd
    doms = [d for d in (_cb.get('project_domains') or []) if d.startswith('http')] or \
           ['https://vex.deals']
    nums = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣']
    lines = ['🗞️ <b>عاجل رياضي — أبرز العناوين</b> ⚽', '']
    n = 0
    for src, items in items_by_source.items():
        for it in items:
            if n >= MAX_DIGEST_ITEMS:
                break
            link = doms[n % len(doms)] if len(doms) <= n + 1 else _rnd.choice(doms)
            lines.append(f'{nums[n] if n < len(nums) else "▪️"} <b>{it["title"]}</b>')
            lines.append(f'    🏷️ المصدر: <i>{src}</i>')
            lines.append(f'    🔗 <a href="{link}">تابع التفاصيل كاملة</a>')
            lines.append('')
            n += 1
        if n >= MAX_DIGEST_ITEMS:
            break
    if n == 0:
        return ''
    footer_links = ' · '.join(f'<a href="{d}">{d.replace("https://", "")}</a>' for d in doms)
    lines.append('━━━━━━━━━━━━━━')
    lines.append(f'🌐 مواقعنا: {footer_links}')
    lines.append('⚽ كل جديد الرياضة — معنا يومياً')
    return '\n'.join(lines)


def _random_domain():
    import random as _rnd
    doms = [d for d in (_cb.get('project_domains') or []) if d.startswith('http')] or \
           ['https://vex.deals']
    return _rnd.choice(doms)


def _queue_digest(items_by_source):
    """جدول ملخّص واحد لجميع القنوات النشطة — بصيغة طابور البوت."""
    msg = _digest_message(items_by_source)
    if not msg:
        return 0
    channels = [c for c in _read_csv('bot_channels.csv')
                if c.get('is_active') == 'yes' and c.get('platform', 'telegram') == 'telegram']
    if not channels:
        return 0
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M')
    fieldnames = _get_fieldnames('broadcast_queue.csv', [
        'id', 'message', 'type', 'platform', 'target_chat_id',
        'platform_account_id', 'target_channel_id', 'created_at',
        'created_by', 'status', 'target', 'recipient', 'priority',
        'country', 'media_urls', 'target_user', 'target_name',
        'scheduled_at', 'cron_expr'])
    import secrets as _secrets
    queued = 0
    for ch in channels:
        entry = {
            'id': 'NEWS' + _secrets.token_hex(4).upper(),
            'message': msg,
            'type': 'channel',
            'platform': 'telegram',
            'target_chat_id': str(ch.get('chat_id', '') or ''),
            'platform_account_id': str(ch.get('platform_account_id', '') or ''),
            'target_channel_id': ch.get('id', ''),
            'created_at': now_s,
            'created_by': 'news_monitor',
            'status': 'pending',
            'target': 'channel',
            'recipient': 'single',
            'priority': 'normal',
            'country': 'all',
            'media_urls': '',
            'target_user': '',
            'target_name': '',
            'scheduled_at': '',
            'cron_expr': '',
        }
        _append('broadcast_queue.csv', entry, fieldnames)
        queued += 1
    return queued


def _silent_log(type_label, message, status='ok'):
    try:
        entry = {'timestamp': _now(), 'type': 'news_monitor',
                 'type_label': type_label, 'message_preview': message[:220],
                 'target_type': 'dashboard', 'target_id': '', 'status': status}
        fns = _get_fieldnames('notifications_log.csv',
                              ['timestamp', 'type', 'type_label', 'message_preview',
                               'target_type', 'target_id', 'status'])
        _append('notifications_log.csv', entry, fns)
    except Exception:
        pass


# ===== الدورة الرئيسية =====

def _run_cycle():
    sources = _load_sources()
    active = [s for s in sources if s.get('enabled') == 'yes']
    if not active:
        return
    seen = _load_seen()
    raw_by_source = _scrape_all(active)

    new_by_source = {}
    for name, raw in raw_by_source.items():
        fresh = _filter_items(raw, seen)
        if fresh:
            new_by_source[name] = fresh

    total_new = sum(len(v) for v in new_by_source.values())

    # إشعار ويب لكل عنوان جديد (بحد أقصى MAX_PUSH_PER_CYCLE)
    pushed = 0
    for name, items in new_by_source.items():
        for it in items:
            if pushed >= MAX_PUSH_PER_CYCLE:
                break
            pushed += 1
            _push('news', f'⚽ {it["title"][:70]}',
                  f'{name} — {it["title"]}',
                  {'source': name, 'url': _random_domain()})

    # ملخّص للقنوات (منصات post_to_channels=yes فقط + هامش15 دقيقة)
    postable = {n: its for n, its in new_by_source.items()
                if next((s.get('post_to_channels') for s in active
                         if s.get('name') == n), 'no') == 'yes'}
    digest_queued = 0
    if postable:
        state = _state_load()
        try:
            last = datetime.strptime(state.get('last_digest', ''), '%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError):
            last = datetime(2000, 1, 1)
        if (datetime.now() - last).total_seconds() >= MIN_DIGEST_GAP:
            digest_queued = _queue_digest(postable)
            if digest_queued:
                state['last_digest'] = _now()
                _state_save(state)
                _push('news', '🗞️ ملخّص أخبار رياضية',
                      f'{sum(len(v) for v in postable.values())} خبر جديد — '
                      f'مجدول لـ{digest_queued} قناة',
                      {'sources': list(postable.keys())})

    # سجل الدورة
    n_sites = len(raw_by_source)
    if total_new:
        _silent_log('📰 فحص الأخبار الرياضية',
                    f'{total_new} خبر جديد من {n_sites} مواقع'
                    + (f' — ملخّص مجدول لـ{digest_queued} قناة' if digest_queued else '')
                    + (f' — {pushed} إشعار ويب' if pushed else ''),
                    'ok')
        print(f'[NEWS] cycle: {total_new} new from {n_sites} sites, '
              f'{pushed} pushed, digest queued={digest_queued}', flush=True)
    else:
        _silent_log('📰 فحص الأخبار الرياضية',
                    f'بدون أخبار جديدة — {n_sites} مواقع', 'ok')
        print(f'[NEWS] cycle: no new items ({n_sites} sites)', flush=True)

    for name in raw_by_source:
        for it in new_by_source.get(name, []):
            _remember(it['title'], name, it['url'])
    _trim_seen()


def _loop():
    import fcntl
    time.sleep(INITIAL_DELAY)
    while True:
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                _run_cycle()
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        except BlockingIOError:
            pass  # عامل gunicorn آخر يفحص الآن
        except Exception as exc:
            print(f'[NEWS] error: {exc}', flush=True)
            try:
                _silent_log('📰 فحص الأخبار الرياضية', f'خطأ: {exc}', 'error')
            except Exception:
                pass
        time.sleep(INTERVAL)


def start(**callbacks):
    configure(**callbacks)
    threading.Thread(target=_loop, daemon=True, name='news_monitor').start()


def run_now():
    """تشغيل دورة فوراً (بدون انتظار) — يرجع False إذا كانت دورة تعمل الآن."""
    import fcntl
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        try:
            _run_cycle()
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
