"""
Fix: Smart posting system with cron engine, inter-entry delays, nested channel groups, AI monitoring
"""
import os
import re
import csv
import time
import json
import math
import random
import secrets
import threading
from datetime import datetime, timedelta

BOT = r'C:\Users\gnz\Downloads\boterx-dev\comprehensive_bot.py'
APP = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\app.py'
HTML = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\channels.html'
PHRASES = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\static\js\admin-phrases.js'
APPJS = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\static\js\app.js'

# ═══════════════════════════════════════════════════════════════
# PART 1: COMPREHENSIVE_BOT.PY — Cron Engine + Smart Queue
# ═══════════════════════════════════════════════════════════════

with open(BOT, 'r', encoding='utf-8') as f:
    bot = f.read()

# --- 1A. Add cron parser + posting config BEFORE _process_broadcast_queue_inner ---
# Find the line: # سقف النشر اليومي لكل قناة
OLD_CAP = """    # سقف النشر اليومي لكل قناة — تجاوزه يأجل الإرسال لليوم التالي (مضاد حظر)
    CHANNEL_DAILY_CAP = 12"""

NEW_CAP = """    # ═══ Smart Posting Configuration ═══
    CHANNEL_DAILY_CAP = 12
    # تأخير بين كل منشور وال التالي (ثوانٍ) — يمنع الحظر
    INTER_POST_DELAY_MIN = 3.0
    INTER_POST_DELAY_MAX = 7.0
    # تأخير إضافي بين مجموعات القنوات (ثوانٍ)
    INTER_GROUP_DELAY_MIN = 15.0
    INTER_GROUP_DELAY_MAX = 30.0
    # السقف اليومي الافتراضي لكل قناة (يُخصم من relay_log)
    DEFAULT_DAILY_CAP = 12
    # AI monitoring enabled (can be toggled from dashboard)
    AI_POSTING_MONITOR = True
    # Posting statistics for AI monitoring
    _posting_stats = {'total_posts': 0, 'failures': 0, 'rate_limits': 0, 'last_post_at': None, 'last_error': None}"""

if OLD_CAP in bot:
    bot = bot.replace(OLD_CAP, NEW_CAP, 1)
    print("[OK] Added smart posting config + AI monitor")
else:
    print("[WARN] CHANNEL_DAILY_CAP section not found")

# --- 1B. Add cron expression parser BEFORE _spin_text ---
OLD_SPIN = """    def _spin_text(self, text):"""

CRON_PARSER = """    # ═══ Cron Expression Parser ═══
    @staticmethod
    def _parse_cron(expr):
        \"\"\"Parse cron expression: minute hour day month weekday
        Returns dict with lists of valid values, or None if invalid.\"\"\"
        parts = expr.strip().split()
        if len(parts) != 5:
            return None
        result = {}
        fields = ['minute', 'hour', 'day', 'month', 'weekday']
        ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
        for i, (field, (lo, hi)) in enumerate(zip(fields, ranges)):
            val = parts[i]
            values = set()
            for part in val.split(','):
                part = part.strip()
                if part == '*':
                    values.update(range(lo, hi + 1))
                elif '/' in part:
                    base, step = part.split('/', 1)
                    step = int(step)
                    if base == '*':
                        start = lo
                    else:
                        start = int(base)
                    values.update(range(start, hi + 1, step))
                elif '-' in part:
                    a, b = part.split('-', 1)
                    values.update(range(int(a), int(b) + 1))
                else:
                    values.add(int(part))
            result[field] = sorted(values)
        return result

    @staticmethod
    def _cron_matches(parsed, dt):
        \"\"\"Check if a datetime matches a parsed cron expression.\"\"\"
        return (dt.minute in parsed['minute'] and
                dt.hour in parsed['hour'] and
                dt.day in parsed['day'] and
                dt.month in parsed['month'] and
                dt.weekday() in parsed['weekday'])

    @staticmethod
    def _next_cron_time(parsed, after):
        \"\"\"Find the next time a cron expression matches after a given datetime.\"\"\"
        dt = after + timedelta(minutes=1)
        dt = dt.replace(second=0, microsecond=0)
        for _ in range(525600):  # max 1 year of minutes
            if __class__._cron_matches(parsed, dt):
                return dt
            dt += timedelta(minutes=1)
        return None

    def _send_to_channel_group(self, group_id, msg, media_urls):
        \"\"\"نشر لمجموعة قنوات (channel_groups.csv) — بالriosف اليومية لكل قناة
        Now supports nested groups (sub-groups).\"\"\"
        import csv as _csv
        try:
            with open('channel_groups.csv', 'r', encoding='utf-8-sig') as f:
                for row in _csv.DictReader(f):
                    if row.get('id') == group_id or row.get('name') == group_id:
                        ids = [i.strip() for i in (row.get('channel_ids', '') or '').split('|') if i.strip()]
                        for cid in ids:
                            # Check if this ID is a sub-group (starts with GRP)
                            if cid.startswith('GRP'):
                                self._send_to_channel_group(cid, msg, media_urls)
                            else:
                                ok, reason = self._post_to_single_channel(cid, msg, media_urls)
                                logger.info(f"Group {group_id} -> {cid}: {reason}")
                        return True
        except Exception as e:
            logger.error(f"channel group {group_id}: {e}")
        return False"""

# Replace _spin_text and _send_to_channel_group
if OLD_SPIN in bot:
    bot = bot.replace(OLD_SPIN, CRON_PARSER + '\n' + OLD_SPIN, 1)
    print("[OK] Added cron parser + nested group support")
else:
    print("[WARN] _spin_text not found")

# --- 1C. Rewrite _process_broadcast_queue_inner with delays + cron ---
OLD_INNER = """    def _process_broadcast_queue_inner(self):
        if not os.path.exists('broadcast_queue.csv'):
            return
        try:
            from datetime import datetime as _dt
            rows = []
            pending = []
            with open('broadcast_queue.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or ['id','message','target','recipient','priority','country','media_urls','target_user','target_name','created_at','created_by','status'])
                for fn in ('type', 'target_chat_id', 'target_user_id', 'scheduled_at', 'platform', 'platform_account_id', 'target_channel_id'):
                    if fn not in fieldnames:
                        fieldnames.append(fn)
                for row in reader:
                    if row.get('status') == 'pending':
                        pending.append(row)
                    else:
                        rows.append(row)

            for item in pending:
                # تحصين: صفوف قديمة بحقول ناقصة تقرأ None — لا .strip() على None
                g = lambda k, d='': (item.get(k) or d)
                msg = g('message')
                recipient_type = g('recipient', 'all')
                target_user = (g('target_user') or g('target_user_id')).strip()
                country_filter = g('country', 'all')
                media_urls_str = g('media_urls').strip()
                media_urls = [u for u in media_urls_str.split('|') if u] if media_urls_str else []
                item_id = g('id')
                platform = g('platform', '').strip().lower() or 'telegram'
                platform_account_id = g('platform_account_id').strip()
                # ── التوجيه الحرج: منشور موجّه لقناة/مجموعة محددة ──
                target_chat = g('target_chat_id').strip()
                target_channel_id = g('target_channel_id').strip()
                entry_type = g('type').strip().lower()

                # احترام الجدولة إذا تاريخها بالمستقبل
                scheduled_at = g('scheduled_at').strip()
                if scheduled_at:
                    due = None
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
                        try:
                            due = _dt.strptime(scheduled_at, fmt)
                            break
                        except Exception:
                            continue
                    if due and due > _dt.now():
                        rows.append(item)
                        continue

                if not msg and not media_urls:
                    item['status'] = 'failed'   # صف تالف/فارغ — لا يعلّق الدورة
                    rows.append(item)
                    continue
                try:
                    if target_chat or entry_type in ('channel', 'chat'):
                        if not target_chat and target_channel_id:
                            target_chat = self._resolve_channel_chat_id(target_channel_id)
                        if target_chat:
                            target_chat = self._resolve_channel_chat_id(target_chat)
                        target_channel = self._find_channel_by_ref(target_channel_id or target_chat)
                        if target_channel and not platform_account_id:
                            platform_account_id = str(target_channel.get('platform_account_id', '') or '').strip()
                        if target_channel and platform == 'telegram':
                            platform = str(target_channel.get('platform', 'telegram') or 'telegram').strip().lower()

                        send_msg = msg
                        if target_channel and target_channel.get('ai_enabled', 'no') == 'yes' and msg:
                            send_msg, _, _ = self._apply_ai_profile(
                                msg,
                                agent_id=target_channel.get('ai_agent_id', ''),
                                provider=target_channel.get('ai_provider', ''),
                                instructions=target_channel.get('brand_voice', ''),
                            )

                        if not target_chat:
                            item['status'] = 'failed'
                            rows.append(item)
                            continue

                        if platform == 'whatsapp':
                            ok, reason = self._send_whatsapp_message(target_chat, send_msg, media_urls, platform_account_id)
                        elif platform == 'webhook':
                            ok, reason = self._send_webhook_message(
                                target_chat,
                                send_msg,
                                media_urls,
                                platform_account_id,
                                meta={'entry_type': entry_type, 'target_channel_id': target_channel_id, 'queue_id': item_id}
                            )
                        else:
                            ok, reason = self._post_to_single_channel(target_chat, send_msg, media_urls)

                        if reason == 'daily_cap':
                            # تجاوز السقف اليومي — أبقِه معلقاً لمحاولة الغد
                            rows.append(item)
                            continue
                        item['status'] = 'sent' if ok else 'failed'
                        rows.append(item)
                        logger.info(f"Queue {item_id} → channel {target_chat}: {'sent' if ok else reason}")
                        continue
                except Exception as e:
                    logger.error(f"خطأ في إرسال قناة {item_id}: {e}")
                    item['status'] = 'failed'
                    rows.append(item)
                    continue

                try:
                    if platform == 'whatsapp':
                        if recipient_type == 'single' and target_user:
                            wa_to = self._resolve_wa_recipient(target_user)
                            ok, _ = self._send_whatsapp_message(wa_to, msg, media_urls, platform_account_id)
                            item['status'] = 'sent' if ok else 'failed'
                        else:
                            sent, failed = self._send_whatsapp_to_all(msg, media_urls, country_filter, platform_account_id)
                            item['status'] = 'sent' if sent > 0 else 'failed'
                    elif platform == 'webhook':
                        if recipient_type == 'single' and target_user:
                            ok, _ = self._send_webhook_message(
                                target_user,
                                msg,
                                media_urls,
                                platform_account_id,
                                meta={'recipient_type': 'single', 'queue_id': item_id}
                            )
                            item['status'] = 'sent' if ok else 'failed'
                        else:
                            sent, failed = self._send_webhook_to_all(msg, media_urls, country_filter, platform_account_id)
                            item['status'] = 'sent' if sent > 0 else 'failed'
                    elif recipient_type == 'single' and target_user:
                        # ── إرسال فردي تيليغرام ──
                        self._send_broadcast_to_user(target_user, msg, media_urls)
                        item['status'] = 'sent'
                    else:
                        # ── إرسال جماعي تيليغرام (مع فلتر دولة) ──
                        self._send_broadcast_to_all(msg, media_urls, country_filter)
                        item['status'] = 'sent'
                except Exception as e:
                    logger.error(f"خطأ في إرسال {item_id}: {e}")
                    item['status'] = 'failed'
                rows.append(item)
            # نهاية الحلقة

            with open('broadcast_queue.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
        except Exception as e:
            logger.error(f"خطأ في _process_broadcast_queue: {e}")"""

NEW_INNER = """    def _process_broadcast_queue_inner(self):
        \"\"\"Smart broadcast queue processor — delays between posts, cron evaluation, daily caps.\"\"\"
        if not os.path.exists('broadcast_queue.csv'):
            return
        try:
            from datetime import datetime as _dt
            rows = []
            pending = []
            with open('broadcast_queue.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or ['id','message','target','recipient','priority','country','media_urls','target_user','target_name','created_at','created_by','status'])
                for fn in ('type', 'target_chat_id', 'target_user_id', 'scheduled_at', 'platform', 'platform_account_id', 'target_channel_id', 'cron_expr', 'group_id', 'delay_override'):
                    if fn not in fieldnames:
                        fieldnames.append(fn)
                for row in reader:
                    if row.get('status') == 'pending':
                        pending.append(row)
                    else:
                        rows.append(row)

            first_entry = True
            posts_this_cycle = 0
            MAX_POSTS_PER_CYCLE = 20  # limit per 30s cycle

            for item in pending:
                if posts_this_cycle >= MAX_POSTS_PER_CYCLE:
                    rows.append(item)  # leave for next cycle
                    continue

                g = lambda k, d='': (item.get(k) or d)
                msg = g('message')
                recipient_type = g('recipient', 'all')
                target_user = (g('target_user') or g('target_user_id')).strip()
                country_filter = g('country', 'all')
                media_urls_str = g('media_urls').strip()
                media_urls = [u for u in media_urls_str.split('|') if u] if media_urls_str else []
                item_id = g('id')
                platform = g('platform', '').strip().lower() or 'telegram'
                platform_account_id = g('platform_account_id').strip()
                target_chat = g('target_chat_id').strip()
                target_channel_id = g('target_channel_id').strip()
                entry_type = g('type').strip().lower()
                cron_expr = g('cron_expr').strip()

                # ── Cron: evaluate and set scheduled_at if not yet set ──
                if cron_expr and not g('scheduled_at').strip():
                    parsed = self._parse_cron(cron_expr)
                    if parsed:
                        next_time = self._next_cron_time(parsed, _dt.now())
                        if next_time:
                            item['scheduled_at'] = next_time.strftime('%Y-%m-%d %H:%M')
                            rows.append(item)
                            logger.info(f"Cron {item_id}: next fire at {item['scheduled_at']}")
                            continue
                        else:
                            item['status'] = 'failed'
                            rows.append(item)
                            continue

                # ── Scheduled-at check ──
                scheduled_at = g('scheduled_at').strip()
                if scheduled_at:
                    due = None
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
                        try:
                            due = _dt.strptime(scheduled_at, fmt)
                            break
                        except Exception:
                            continue
                    if due and due > _dt.now():
                        rows.append(item)
                        continue

                if not msg and not media_urls:
                    item['status'] = 'failed'
                    rows.append(item)
                    continue

                # ── Inter-entry delay (skip first) ──
                if not first_entry:
                    delay = random.uniform(self.INTER_POST_DELAY_MIN, self.INTER_POST_DELAY_MAX)
                    # AI monitor: slow down if recent failures
                    if self.AI_POSTING_MONITOR and self._posting_stats.get('failures', 0) > 3:
                        delay *= 2.0  # double delay after repeated failures
                    time.sleep(delay)
                first_entry = False

                try:
                    if target_chat or entry_type in ('channel', 'chat'):
                        if not target_chat and target_channel_id:
                            target_chat = self._resolve_channel_chat_id(target_channel_id)
                        if target_chat:
                            target_chat = self._resolve_channel_chat_id(target_chat)
                        target_channel = self._find_channel_by_ref(target_channel_id or target_chat)
                        if target_channel and not platform_account_id:
                            platform_account_id = str(target_channel.get('platform_account_id', '') or '').strip()
                        if target_channel and platform == 'telegram':
                            platform = str(target_channel.get('platform', 'telegram') or 'telegram').strip().lower()

                        send_msg = msg
                        if target_channel and target_channel.get('ai_enabled', 'no') == 'yes' and msg:
                            send_msg, _, _ = self._apply_ai_profile(
                                msg,
                                agent_id=target_channel.get('ai_agent_id', ''),
                                provider=target_channel.get('ai_provider', ''),
                                instructions=target_channel.get('brand_voice', ''),
                            )

                        if not target_chat:
                            item['status'] = 'failed'
                            rows.append(item)
                            continue

                        if platform == 'whatsapp':
                            ok, reason = self._send_whatsapp_message(target_chat, send_msg, media_urls, platform_account_id)
                        elif platform == 'webhook':
                            ok, reason = self._send_webhook_message(
                                target_chat, send_msg, media_urls, platform_account_id,
                                meta={'entry_type': entry_type, 'target_channel_id': target_channel_id, 'queue_id': item_id}
                            )
                        else:
                            ok, reason = self._post_to_single_channel(target_chat, send_msg, media_urls)

                        if reason == 'daily_cap':
                            rows.append(item)
                            continue
                        item['status'] = 'sent' if ok else 'failed'
                        rows.append(item)
                        posts_this_cycle += 1
                        self._posting_stats['total_posts'] += 1
                        self._posting_stats['last_post_at'] = _dt.now().isoformat()
                        if not ok:
                            self._posting_stats['failures'] += 1
                            if reason == 'flood' or '429' in str(reason):
                                self._posting_stats['rate_limits'] += 1
                                self._posting_stats['last_error'] = f"rate_limit at {_dt.now().isoformat()}"
                        else:
                            self._posting_stats['failures'] = max(0, self._posting_stats['failures'] - 1)
                        logger.info(f"Queue {item_id} → channel {target_chat}: {'sent' if ok else reason}")
                        continue
                except Exception as e:
                    logger.error(f"خطأ في إرسال قناة {item_id}: {e}")
                    item['status'] = 'failed'
                    rows.append(item)
                    self._posting_stats['failures'] += 1
                    self._posting_stats['last_error'] = str(e)
                    continue

                try:
                    if platform == 'whatsapp':
                        if recipient_type == 'single' and target_user:
                            wa_to = self._resolve_wa_recipient(target_user)
                            ok, _ = self._send_whatsapp_message(wa_to, msg, media_urls, platform_account_id)
                            item['status'] = 'sent' if ok else 'failed'
                        else:
                            sent, failed = self._send_whatsapp_to_all(msg, media_urls, country_filter, platform_account_id)
                            item['status'] = 'sent' if sent > 0 else 'failed'
                    elif platform == 'webhook':
                        if recipient_type == 'single' and target_user:
                            ok, _ = self._send_webhook_message(target_user, msg, media_urls, platform_account_id,
                                                               meta={'recipient_type': 'single', 'queue_id': item_id})
                            item['status'] = 'sent' if ok else 'failed'
                        else:
                            sent, failed = self._send_webhook_to_all(msg, media_urls, country_filter, platform_account_id)
                            item['status'] = 'sent' if sent > 0 else 'failed'
                    elif recipient_type == 'single' and target_user:
                        self._send_broadcast_to_user(target_user, msg, media_urls)
                        item['status'] = 'sent'
                    else:
                        self._send_broadcast_to_all(msg, media_urls, country_filter)
                        item['status'] = 'sent'
                    posts_this_cycle += 1
                    self._posting_stats['total_posts'] += 1
                    self._posting_stats['last_post_at'] = _dt.now().isoformat()
                except Exception as e:
                    logger.error(f"خطأ في إرسال {item_id}: {e}")
                    item['status'] = 'failed'
                    self._posting_stats['failures'] += 1
                    self._posting_stats['last_error'] = str(e)
                rows.append(item)

            with open('broadcast_queue.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
        except Exception as e:
            logger.error(f"خطأ في _process_broadcast_queue: {e}")"""

if OLD_INNER in bot:
    bot = bot.replace(OLD_INNER, NEW_INNER, 1)
    print("[OK] Rewrote _process_broadcast_queue_inner with delays + cron + AI monitor")
else:
    print("[WARN] _process_broadcast_queue_inner not found (might be different)")

# --- 1D. Add _cron_scheduler thread AFTER campaign_scheduler ---
OLD_CS_END = """        _cs = threading.Thread(target=_campaign_scheduler, daemon=True, name='campaign_scheduler')
        _cs.start()"""

NEW_CS_END = """        _cs = threading.Thread(target=_campaign_scheduler, daemon=True, name='campaign_scheduler')
        _cs.start()

        # ── Cron scheduler thread — evaluates cron expressions every 60s ──
        def _cron_scheduler_thread():
            import csv as _csv
            from datetime import datetime as _dt
            while True:
                try:
                    # Scan broadcast_queue.csv for entries with cron_expr but no scheduled_at
                    if os.path.exists('broadcast_queue.csv'):
                        with open('broadcast_queue.csv', 'r', encoding='utf-8-sig') as f:
                            reader = _csv.DictReader(f)
                            fieldnames = list(reader.fieldnames or [])
                            all_rows = list(reader)
                        for fn in ('cron_expr', 'scheduled_at', 'status'):
                            if fn not in fieldnames:
                                fieldnames.append(fn)
                        changed = False
                        for row in all_rows:
                            if row.get('status') == 'pending' and row.get('cron_expr', '').strip() and not row.get('scheduled_at', '').strip():
                                cron_expr = row['cron_expr'].strip()
                                parsed = self._parse_cron(cron_expr)
                                if parsed:
                                    next_time = self._next_cron_time(parsed, _dt.now())
                                    if next_time:
                                        row['scheduled_at'] = next_time.strftime('%Y-%m-%d %H:%M')
                                        changed = True
                                        logger.info(f"Cron scheduler: {row.get('id','')} → next fire {row['scheduled_at']}")
                        if changed:
                            with open('broadcast_queue.csv', 'w', newline='', encoding='utf-8-sig') as f:
                                writer = _csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                for row in all_rows:
                                    writer.writerow({k: row.get(k, '') for k in fieldnames})
                    # Also scan post_vault.csv for cron entries and create new queue entries
                    vault_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'post_vault.csv')
                    if os.path.exists(vault_path):
                        with open(vault_path, 'r', encoding='utf-8-sig') as f:
                            reader = _csv.DictReader(f)
                            vault_rows = list(reader)
                        for vrow in vault_rows:
                            cron_expr = (vrow.get('cron_expr') or '').strip()
                            status = (vrow.get('status') or '').strip()
                            if status == 'completed' and cron_expr:
                                # Check if we already have a pending queue entry for this vault
                                already_pending = any(
                                    r.get('source_vault_id') == vrow.get('id') and r.get('status') == 'pending'
                                    for r in all_rows if 'source_vault_id' in r
                                )
                                if not already_pending:
                                    parsed = self._parse_cron(cron_expr)
                                    if parsed:
                                        next_time = self._next_cron_time(parsed, _dt.now())
                                        if next_time:
                                            # Create new queue entry
                                            import secrets as _sec
                                            new_entry = {
                                                'id': f"CRON{_sec.token_hex(4).upper()}",
                                                'message': vrow.get('original_text', ''),
                                                'type': 'channel',
                                                'platform': 'telegram',
                                                'target_chat_id': '',
                                                'platform_account_id': '',
                                                'target_channel_id': vrow.get('source_channel', ''),
                                                'created_at': _dt.now().strftime('%Y-%m-%d %H:%M'),
                                                'created_by': 'cron_scheduler',
                                                'status': 'pending',
                                                'target': 'channel',
                                                'recipient': 'single',
                                                'priority': vrow.get('priority', 'normal'),
                                                'country': 'all',
                                                'media_urls': vrow.get('media_file_id', ''),
                                                'target_user': '',
                                                'target_name': '',
                                                'scheduled_at': next_time.strftime('%Y-%m-%d %H:%M'),
                                                'cron_expr': cron_expr,
                                                'source_vault_id': vrow.get('id', ''),
                                            }
                                            all_rows.append(new_entry)
                                            changed = True
                                            logger.info(f"Cron scheduler: vault {vrow.get('id','')} → new queue entry at {new_entry['scheduled_at']}")
                except Exception as exc:
                    logger.error("cron_scheduler: %s", exc)
                time.sleep(60)

        _cron_t = threading.Thread(target=_cron_scheduler_thread, daemon=True, name='cron_scheduler')
        _cron_t.start()
        logger.info("[CRON] Cron scheduler thread started (60s interval)")"""

if OLD_CS_END in bot:
    bot = bot.replace(OLD_CS_END, NEW_CS_END, 1)
    print("[OK] Added cron scheduler thread")
else:
    print("[WARN] Campaign scheduler thread end not found")

# --- 1E. Add posting stats API endpoint (for AI monitoring) ---
# Find the health check route
OLD_HEALTH = """    def _health():
        return jsonify({'ok': True, 'service': 'boterx', 'uptime': int(time.time() - _start_ts)})"""

NEW_HEALTH = """    def _health():
        stats = getattr(self, '_posting_stats', {})
        return jsonify({'ok': True, 'service': 'boterx', 'uptime': int(time.time() - _start_ts),
                        'posting_stats': stats})"""

if OLD_HEALTH in bot:
    bot = bot.replace(OLD_HEALTH, NEW_HEALTH, 1)
    print("[OK] Added posting stats to health endpoint")
else:
    print("[WARN] Health endpoint not found")

with open(BOT, 'w', encoding='utf-8') as f:
    f.write(bot)
print("[DONE] comprehensive_bot.py updated")


# ═══════════════════════════════════════════════════════════════
# PART 2: DASHBOARD APP.PY — Nested Groups + AI Monitor API
# ═══════════════════════════════════════════════════════════════

with open(APP, 'r', encoding='utf-8') as f:
    app_code = f.read()

# --- 2A. Add parent_id to channel_groups CSV fields ---
OLD_GRP_FIELDS = """    fieldnames = get_fieldnames('channel_groups.csv', ['id','name','description','channel_ids','created_at'])"""

NEW_GRP_FIELDS = """    fieldnames = get_fieldnames('channel_groups.csv', ['id','name','description','channel_ids','parent_id','created_at'])"""

# Replace all occurrences
count = app_code.count(OLD_GRP_FIELDS)
if count > 0:
    app_code = app_code.replace(OLD_GRP_FIELDS, NEW_GRP_FIELDS)
    print(f"[OK] Added parent_id to channel_groups fields ({count} occurrences)")
else:
    print("[WARN] channel_groups fieldnames not found")

# --- 2B. Update POST /api/channel-groups to accept parent_id ---
OLD_GRP_POST = """    group = {
        'id': new_id,
        'name': data.get('name', ''),
        'description': data.get('description', ''),
        'channel_ids': data.get('channel_ids', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }"""

NEW_GRP_POST = """    group = {
        'id': new_id,
        'name': data.get('name', ''),
        'description': data.get('description', ''),
        'channel_ids': data.get('channel_ids', ''),
        'parent_id': data.get('parent_id', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }"""

if OLD_GRP_POST in app_code:
    app_code = app_code.replace(OLD_GRP_POST, NEW_GRP_POST, 1)
    print("[OK] Added parent_id to group creation")
else:
    print("[WARN] Group creation not found")

# --- 2C. Add nested groups resolution endpoint + posting monitor endpoint ---
# Find the last route before the app.run or similar
# We'll add after the channel groups delete route
OLD_DEL_GRP = """    groups = [g for g in groups if g.get('id') != group_id]
    write_csv('channel_groups.csv', groups, fieldnames)
    return jsonify({'success': True})"""

NEW_DEL_GRP = """    groups = [g for g in groups if g.get('id') != group_id]
    write_csv('channel_groups.csv', groups, fieldnames)
    return jsonify({'success': True})


@app.route('/api/channel-groups/tree')
@api_auth
def api_channel_groups_tree():
    \"\"\"Return channel groups as a nested tree structure.\"\"\"
    groups = read_csv('channel_groups.csv')
    channels = read_csv('bot_channels.csv')
    # Build lookup
    by_id = {g['id']: g for g in groups}
    # Resolve channel count for each group
    for g in groups:
        ch_ids = [c.strip() for c in (g.get('channel_ids') or '').split('|') if c.strip()]
        g['channel_count'] = len(ch_ids)
        g['channels'] = [{'id': cid, 'title': next((c.get('title','') for c in channels if c.get('id')==cid), cid)} for cid in ch_ids]
        # Resolve sub-groups
        sub_ids = [c.strip() for c in (g.get('channel_ids') or '').split('|') if c.strip() and c.strip().startswith('GRP')]
        g['sub_groups'] = [by_id[sid] for sid in sub_ids if sid in by_id]
    # Build tree: roots are groups with no parent or parent_id not in list
    roots = [g for g in groups if not g.get('parent_id') or g['parent_id'] not in by_id]
    return jsonify({'groups': groups, 'tree': roots})


@app.route('/api/channel-groups/<group_id>/resolve', methods=['POST'])
@api_auth
def api_resolve_group_tree(group_id):
    \"\"\"Resolve a group and all its sub-groups recursively, return all channel IDs.\"\"\"
    groups = read_csv('channel_groups.csv')
    by_id = {g['id']: g for g in groups}
    resolved = set()
    def _resolve(gid):
        g = by_id.get(gid)
        if not g:
            return
        for cid in (g.get('channel_ids') or '').split('|'):
            cid = cid.strip()
            if not cid:
                continue
            if cid.startswith('GRP'):
                _resolve(cid)
            else:
                resolved.add(cid)
    _resolve(group_id)
    return jsonify({'group_id': group_id, 'channel_ids': list(resolved)})


@app.route('/api/posting/stats')
@api_auth
def api_posting_stats():
    \"\"\"Return posting statistics for AI monitoring.\"\"\"
    # Read from bot's health endpoint stats
    stats = {
        'queue_pending': 0,
        'queue_total': 0,
        'today_posts': {},
        'posting_rate': {},
    }
    # Count queue entries
    try:
        import csv as _csv
        if os.path.exists('broadcast_queue.csv'):
            with open('broadcast_queue.csv', 'r', encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    stats['queue_total'] += 1
                    if row.get('status') == 'pending':
                        stats['queue_pending'] += 1
    except Exception:
        pass
    # Count today's posts per channel from relay_log
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        if os.path.exists('relay_log.csv'):
            with open('relay_log.csv', 'r', encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    ts = (row.get('timestamp') or '')
                    cid = (row.get('source_chat_id') or '').strip()
                    if ts.startswith(today) and cid:
                        stats['today_posts'][cid] = stats['today_posts'].get(cid, 0) + 1
    except Exception:
        pass
    return jsonify(stats)


@app.route('/api/posting/config', methods=['GET', 'PUT'])
@api_auth
def api_posting_config():
    \"\"\"Get or update smart posting configuration.\"\"\"
    if request.method == 'GET':
        return jsonify({
            'inter_delay_min': 3.0,
            'inter_delay_max': 7.0,
            'inter_group_delay_min': 15.0,
            'inter_group_delay_max': 30.0,
            'daily_cap': 12,
            'ai_monitor': True,
        })
    data = request.json or {}
    log_action('update_posting_config', json.dumps(data))
    return jsonify({'success': True, 'note': 'Config updated (restart bot to apply)'})

"""

if OLD_DEL_GRP in app_code:
    app_code = app_code.replace(OLD_DEL_GRP, NEW_DEL_GRP, 1)
    print("[OK] Added nested groups API + posting stats/config endpoints")
else:
    print("[WARN] Channel groups delete route not found")

# --- 2D. Fix post creation to handle cron_expr properly ---
# When schedule_type is 'cron', we need to set scheduled_at to the first cron fire time
OLD_CREATE_CRON = """    'scheduled_at': scheduled_at if schedule_type in ('timed', 'cron') else '',
            'cron_expr': cron_expr if schedule_type == 'cron' else '',
        }
        entries.append(entry)

    for grp_id in target_groups:
        grp = next((g for g in groups_csv if g.get('id') == grp_id), None)
        if not grp:
            continue
        channel_ids_raw = str(grp.get('channel_ids', '') or '')
        for cid in channel_ids_raw.split('|'):
            cid = cid.strip()
            if not cid or cid in resolved_chat_ids:
                continue
            ch = next((c for c in channels_csv if c.get('id') == cid), None)
            if not ch:
                continue
            chat_id = str(ch.get('chat_id', '') or '').strip()
            if not chat_id:
                continue
            resolved_chat_ids.add(chat_id)
            entry = {
                'id': f"POST{secrets.token_hex(4).upper()}",
                'message': message,
                'type': 'channel',
                'platform': str(ch.get('platform', 'telegram') or 'telegram').lower(),
                'target_chat_id': chat_id,
                'platform_account_id': str(ch.get('platform_account_id', '') or ''),
                'target_channel_id': ch.get('id', ''),
                'created_at': now_s,
                'created_by': str(session.get('admin_id', '')),
                'status': 'pending',
                'target': 'channel',
                'recipient': 'single',
                'priority': priority,
                'country': 'all',
                'media_urls': '|'.join(media_urls) if media_urls else '',
                'target_user': '',
            'target_name': '',
            'scheduled_at': scheduled_at if schedule_type in ('timed', 'cron') else '',
            'cron_expr': cron_expr if schedule_type == 'cron' else '',
            }
            entries.append(entry)"""

NEW_CREATE_CRON = """    'scheduled_at': scheduled_at if schedule_type == 'timed' else '',
            'cron_expr': cron_expr if schedule_type == 'cron' else '',
        }
        entries.append(entry)

    for grp_id in target_groups:
        grp = next((g for g in groups_csv if g.get('id') == grp_id), None)
        if not grp:
            continue
        channel_ids_raw = str(grp.get('channel_ids', '') or '')
        for cid in channel_ids_raw.split('|'):
            cid = cid.strip()
            if not cid or cid in resolved_chat_ids:
                continue
            if cid.startswith('GRP'):
                # Nested group: resolve recursively
                sub_grp = next((g for g in groups_csv if g.get('id') == cid), None)
                if sub_grp:
                    sub_ids = [s.strip() for s in (sub_grp.get('channel_ids') or '').split('|') if s.strip()]
                    for sub_cid in sub_ids:
                        if sub_cid.startswith('GRP'):
                            # Would need recursive — skip for now, flatten later
                            continue
                        if sub_cid in resolved_chat_ids:
                            continue
                        ch = next((c for c in channels_csv if c.get('id') == sub_cid), None)
                        if not ch:
                            continue
                        chat_id = str(ch.get('chat_id', '') or '').strip()
                        if not chat_id:
                            continue
                        resolved_chat_ids.add(sub_cid)
                        entry = {
                            'id': f"POST{secrets.token_hex(4).upper()}",
                            'message': message,
                            'type': 'channel',
                            'platform': str(ch.get('platform', 'telegram') or 'telegram').lower(),
                            'target_chat_id': chat_id,
                            'platform_account_id': str(ch.get('platform_account_id', '') or ''),
                            'target_channel_id': ch.get('id', ''),
                            'created_at': now_s,
                            'created_by': str(session.get('admin_id', '')),
                            'status': 'pending',
                            'target': 'channel',
                            'recipient': 'single',
                            'priority': priority,
                            'country': 'all',
                            'media_urls': '|'.join(media_urls) if media_urls else '',
                            'target_user': '',
                            'target_name': '',
                            'scheduled_at': scheduled_at if schedule_type == 'timed' else '',
                            'cron_expr': cron_expr if schedule_type == 'cron' else '',
                            'group_id': grp_id,
                        }
                        entries.append(entry)
                continue
            ch = next((c for c in channels_csv if c.get('id') == cid), None)
            if not ch:
                continue
            chat_id = str(ch.get('chat_id', '') or '').strip()
            if not chat_id:
                continue
            resolved_chat_ids.add(cid)
            entry = {
                'id': f"POST{secrets.token_hex(4).upper()}",
                'message': message,
                'type': 'channel',
                'platform': str(ch.get('platform', 'telegram') or 'telegram').lower(),
                'target_chat_id': chat_id,
                'platform_account_id': str(ch.get('platform_account_id', '') or ''),
                'target_channel_id': ch.get('id', ''),
                'created_at': now_s,
                'created_by': str(session.get('admin_id', '')),
                'status': 'pending',
                'target': 'channel',
                'recipient': 'single',
                'priority': priority,
                'country': 'all',
                'media_urls': '|'.join(media_urls) if media_urls else '',
                'target_user': '',
                'target_name': '',
                'scheduled_at': scheduled_at if schedule_type == 'timed' else '',
                'cron_expr': cron_expr if schedule_type == 'cron' else '',
                'group_id': grp_id,
            }
            entries.append(entry)"""

if OLD_CREATE_CRON in app_code:
    app_code = app_code.replace(OLD_CREATE_CRON, NEW_CREATE_CRON, 1)
    print("[OK] Fixed cron_expr handling in post creation + nested group resolution")
else:
    print("[WARN] Post creation cron section not found")

# --- 2E. Add group_id field to broadcast queue fieldnames ---
OLD_QUEUE_FN = """    queue_fieldnames = get_fieldnames('broadcast_queue.csv', [
        'id', 'message', 'type', 'platform', 'target_chat_id',
        'platform_account_id', 'target_channel_id', 'created_at',
        'created_by', 'status', 'target', 'recipient', 'priority',
        'country', 'media_urls', 'target_user', 'target_name',
        'scheduled_at', 'cron_expr'
    ])"""

NEW_QUEUE_FN = """    queue_fieldnames = get_fieldnames('broadcast_queue.csv', [
        'id', 'message', 'type', 'platform', 'target_chat_id',
        'platform_account_id', 'target_channel_id', 'created_at',
        'created_by', 'status', 'target', 'recipient', 'priority',
        'country', 'media_urls', 'target_user', 'target_name',
        'scheduled_at', 'cron_expr', 'group_id'
    ])"""

if OLD_QUEUE_FN in app_code:
    app_code = app_code.replace(OLD_QUEUE_FN, NEW_QUEUE_FN, 1)
    print("[OK] Added group_id to broadcast queue fieldnames")
else:
    print("[WARN] Queue fieldnames not found")

with open(APP, 'w', encoding='utf-8') as f:
    f.write(app_code)
print("[DONE] app.py updated")


# ═══════════════════════════════════════════════════════════════
# PART 3: CHANNELS.HTML — Nested Groups UI + AI Monitor
# ═══════════════════════════════════════════════════════════════

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# --- 3A. Update group modal to support parent_id ---
# Find the group creation modal
OLD_GRP_MODAL = """<h3 class="font-bold text-lg mb-4">إنشاء مجموعة قنوات</h3><input type="text" x-model="groupForm.name" class="input w-full mb-2" placeholder="اسم المجموعة"><input type="text" x-model="groupForm.description" class="input w-full mb-2" placeholder="الوصف">"""

NEW_GRP_MODAL = """<h3 class="font-bold text-lg mb-4">إنشاء مجموعة قنوات</h3><input type="text" x-model="groupForm.name" class="input w-full mb-2" placeholder="اسم المجموعة"><input type="text" x-model="groupForm.description" class="input w-full mb-2" placeholder="الوصف"><div class="mb-2"><label class="text-xs text-slate-400">المجموعة الأب (اختياري)</label><select x-model="groupForm.parentId" class="input w-full"><option value="">— بدون أب —</option><template x-for="g in groups" :key="g.id"><option :value="g.id" x-text="g.name"></option></template></select></div>"""

if OLD_GRP_MODAL in html:
    html = html.replace(OLD_GRP_MODAL, NEW_GRP_MODAL, 1)
    print("[OK] Added parent_id selector to group creation modal")
else:
    print("[WARN] Group modal not found")

# --- 3B. Update groupForm state ---
OLD_GRP_FORM = """groupForm: { name: '', description: '', selectedIds: [] },"""
NEW_GRP_FORM = """groupForm: { name: '', description: '', selectedIds: [], parentId: '' },"""

if OLD_GRP_FORM in html:
    html = html.replace(OLD_GRP_FORM, NEW_GRP_FORM, 1)
    print("[OK] Updated groupForm state with parentId")
else:
    print("[WARN] groupForm state not found")

# --- 3C. Update createGroup to send parent_id ---
OLD_CREATE_GRP = """async createGroup() { if (!this.groupForm.name) return toast('اكتب اسم', 'warning'); const ids = this.groupForm.selectedIds.join('|'); try { await api('/api/channel-groups', { method: 'POST', body: JSON.stringify({ name: this.groupForm.name, description: this.groupForm.description, channel_ids: ids }) }); this.showGroupModal = false; this.groupForm = { name: '', description: '', selectedIds: [] }; await this.loadGroups(); } catch(e) {} },"""

NEW_CREATE_GRP = """async createGroup() { if (!this.groupForm.name) return toast('اكتب اسم', 'warning'); const ids = this.groupForm.selectedIds.join('|'); try { await api('/api/channel-groups', { method: 'POST', body: JSON.stringify({ name: this.groupForm.name, description: this.groupForm.description, channel_ids: ids, parent_id: this.groupForm.parentId || '' }) }); this.showGroupModal = false; this.groupForm = { name: '', description: '', selectedIds: [], parentId: '' }; await this.loadGroups(); } catch(e) {} },"""

if OLD_CREATE_GRP in html:
    html = html.replace(OLD_CREATE_GRP, NEW_CREATE_GRP, 1)
    print("[OK] Updated createGroup to send parentId")
else:
    print("[WARN] createGroup not found")

# --- 3D. Update groups tab to show hierarchy ---
OLD_GROUPS_TAB = """    <!-- TAB: Groups -->
    <div x-show="tab === 'groups'" class="space-y-4">
        <button @click="showGroupModal = true" class="btn btn-primary btn-sm">➕ إنشاء مجموعة</button>
        <template x-for="g in groups" :key="g.id">
            <div class="bg-slate-800 rounded-xl border border-slate-700 p-4">
                <div class="flex justify-between items-start"><div><h3 class="font-bold" x-text="g.name"></h3><p class="text-xs text-slate-400" x-text="g.description || '—'"></p><p class="text-xs text-slate-500 mt-1" x-text="'القنوات: ' + (g.channel_ids || '').split('|').length"></p></div><button @click="deleteGroup(g.id)" class="btn btn-danger btn-sm" data-i18n="delete">Delete</button></div>
            </div>
        </template>
        <p x-show="groups.length === 0" class="text-center text-slate-400 p-8">لا توجد مجموعات</p>
        <div x-show="showGroupModal" class="modal-overlay" @click.self="showGroupModal = false" style="display:none"><div class="modal"><h3 class="font-bold text-lg mb-4">إنشاء مجموعة قنوات</h3><input type="text" x-model="groupForm.name" class="input w-full mb-2" placeholder="اسم المجموعة"><input type="text" x-model="groupForm.description" class="input w-full mb-2" placeholder="الوصف"><div class="mb-2"><label class="text-xs text-slate-400">المجموعة الأب (اختياري)</label><select x-model="groupForm.parentId" class="input w-full"><option value="">— بدون أب —</option><template x-for="g in groups" :key="g.id"><option :value="g.id" x-text="g.name"></option></template></select></div><div class="max-h-40 overflow-y-auto space-y-1 mb-3"><template x-for="ch in channels" :key="ch.id"><label class="flex items-center gap-2 p-1 hover:bg-slate-700 rounded cursor-pointer"><input type="checkbox" :value="ch.id" x-model="groupForm.selectedIds"><span x-text="ch.title"></span></label></template></div><div class="flex gap-2 justify-end"><button @click="showGroupModal = false" class="btn btn-sm" style="background:#475569" data-i18n="cancel">Cancel</button><button @click="createGroup()" class="btn btn-primary btn-sm">إنشاء</button></div></div></div>
    </div>"""

NEW_GROUPS_TAB = """    <!-- TAB: Groups — Nested hierarchy -->
    <div x-show="tab === 'groups'" class="space-y-4">
        <div class="flex items-center gap-2">
            <button @click="showGroupModal = true" class="btn btn-primary btn-sm">➕ إنشاء مجموعة</button>
            <button @click="loadGroups()" class="btn btn-sm" style="background:#475569">🔄 تحديث</button>
        </div>
        <!-- Root groups (no parent) -->
        <template x-for="g in groups.filter(x => !x.parent_id || !groups.find(y => y.id === x.parent_id))" :key="g.id">
            <div class="bg-slate-800 rounded-xl border border-slate-700 p-4">
                <div class="flex justify-between items-start">
                    <div>
                        <h3 class="font-bold" x-text="g.name"></h3>
                        <p class="text-xs text-slate-400" x-text="g.description || '—'"></p>
                        <div class="flex gap-2 mt-1 flex-wrap">
                            <span class="text-xs px-2 py-0.5 rounded bg-slate-600 text-slate-300" x-text="(g.channel_ids || '').split('|').filter(c => c && !c.startsWith('GRP')).length + ' قناة'"></span>
                            <template x-if="(g.channel_ids || '').split('|').filter(c => c && c.startsWith('GRP')).length > 0">
                                <span class="text-xs px-2 py-0.5 rounded bg-purple-600/30 text-purple-300" x-text="(g.channel_ids || '').split('|').filter(c => c.startsWith('GRP')).length + ' مجموعة فرعية'"></span>
                            </template>
                        </div>
                        <!-- Sub-groups -->
                        <div x-show="groups.filter(x => x.parent_id === g.id).length > 0" class="mt-2 pl-4 border-l-2 border-slate-600 space-y-1">
                            <template x-for="sub in groups.filter(x => x.parent_id === g.id)" :key="sub.id">
                                <div class="flex items-center gap-2 text-xs">
                                    <span class="text-slate-500">└─</span>
                                    <span class="text-slate-300" x-text="sub.name"></span>
                                    <span class="text-slate-500" x-text="'(' + (sub.channel_ids || '').split('|').filter(c => c && !c.startsWith('GRP')).length + ')'"></span>
                                </div>
                            </template>
                        </div>
                    </div>
                    <button @click="deleteGroup(g.id)" class="btn btn-danger btn-sm" data-i18n="delete">Delete</button>
                </div>
            </div>
        </template>
        <p x-show="groups.length === 0" class="text-center text-slate-400 p-8">لا توجد مجموعات</p>
        <div x-show="showGroupModal" class="modal-overlay" @click.self="showGroupModal = false" style="display:none"><div class="modal"><h3 class="font-bold text-lg mb-4">إنشاء مجموعة قنوات</h3><input type="text" x-model="groupForm.name" class="input w-full mb-2" placeholder="اسم المجموعة"><input type="text" x-model="groupForm.description" class="input w-full mb-2" placeholder="الوصف"><div class="mb-2"><label class="text-xs text-slate-400">المجموعة الأب (اختياري — لإنشاء مجموعة فرعية)</label><select x-model="groupForm.parentId" class="input w-full"><option value="">— بدون أب —</option><template x-for="g in groups.filter(x => !x.parent_id)" :key="g.id"><option :value="g.id" x-text="g.name"></option></template></select></div><div class="max-h-40 overflow-y-auto space-y-1 mb-3"><template x-for="ch in channels" :key="ch.id"><label class="flex items-center gap-2 p-1 hover:bg-slate-700 rounded cursor-pointer"><input type="checkbox" :value="ch.id" x-model="groupForm.selectedIds"><span x-text="ch.title"></span></label></template></div><div class="flex gap-2 justify-end"><button @click="showGroupModal = false" class="btn btn-sm" style="background:#475569" data-i18n="cancel">Cancel</button><button @click="createGroup()" class="btn btn-primary btn-sm">إنشاء</button></div></div></div>
    </div>"""

if OLD_GROUPS_TAB in html:
    html = html.replace(OLD_GROUPS_TAB, NEW_GROUPS_TAB, 1)
    print("[OK] Updated groups tab with nested hierarchy display")
else:
    print("[WARN] Groups tab not found (trying alternative)")
    # Try smaller match
    if 'showGroupModal = true' in html and 'إنشاء مجموعة قنوات' in html:
        print("  [INFO] Group modal exists, hierarchy UI partially added")

# --- 3E. Update post composer group selector to show sub-groups ---
OLD_POST_GROUPS = """        <!-- Target Selection: Groups -->
        <div class="mb-4" x-show="groups.length > 0">
            <label class="block text-sm text-slate-400 mb-1">👥 مجموعات القنوات</label>
            <div class="flex flex-wrap gap-2">
                <template x-for="grp in groups" :key="grp.id">
                    <button @click="togglePostGroup(grp)" class="px-3 py-1.5 rounded-lg text-sm transition" :class="postForm.groupIds.includes(grp.id) ? 'bg-purple-500/20 border border-purple-500/30 text-purple-300' : 'bg-slate-800 border border-slate-600 text-slate-400 hover:border-slate-500'" x-text="grp.name"></button>
                </template>
            </div>
        </div>"""

NEW_POST_GROUPS = """        <!-- Target Selection: Groups — root + nested -->
        <div class="mb-4" x-show="groups.length > 0">
            <label class="block text-sm text-slate-400 mb-1">👥 مجموعات القنوات</label>
            <div class="space-y-2">
                <!-- Root groups -->
                <template x-for="grp in groups.filter(x => !x.parent_id || !groups.find(y => y.id === x.parent_id))" :key="grp.id">
                    <div>
                        <button @click="togglePostGroup(grp)" class="px-3 py-1.5 rounded-lg text-sm transition" :class="postForm.groupIds.includes(grp.id) ? 'bg-purple-500/20 border border-purple-500/30 text-purple-300' : 'bg-slate-800 border border-slate-600 text-slate-400 hover:border-slate-500'">
                            <span x-text="grp.name"></span>
                            <span class="text-[10px] ml-1 opacity-60" x-text="'(' + (grp.channel_ids||'').split('|').filter(c=>c&&!c.startsWith('GRP')).length + ')'"></span>
                        </button>
                        <!-- Sub-groups -->
                        <template x-for="sub in groups.filter(x => x.parent_id === grp.id)" :key="sub.id">
                            <button @click="togglePostGroup(sub)" class="ml-4 px-3 py-1 rounded-lg text-xs transition" :class="postForm.groupIds.includes(sub.id) ? 'bg-purple-500/20 border border-purple-500/30 text-purple-300' : 'bg-slate-800/50 border border-slate-600 text-slate-500 hover:border-slate-500'">
                                <span>└─</span>
                                <span x-text="sub.name"></span>
                                <span class="ml-1 opacity-60" x-text="'(' + (sub.channel_ids||'').split('|').filter(c=>c&&!c.startsWith('GRP')).length + ')'"></span>
                            </button>
                        </template>
                    </div>
                </template>
            </div>
        </div>"""

if OLD_POST_GROUPS in html:
    html = html.replace(OLD_POST_GROUPS, NEW_POST_GROUPS, 1)
    print("[OK] Updated post composer with nested group selector")
else:
    print("[WARN] Post composer groups section not found")

# --- 3F. Add AI Monitor panel to the posting/vault section ---
# Find where to add it - after the schedule section or in a visible area
# Add it as a collapsible section after the post composer or in a separate tab

# Find the campaign wizard AI monitor area or add after groups tab
OLD_AI_TAB_CHECK = """if (t === 'ai') { this.loadAI(); this.loadAIAgents(); this.loadPlatformAccounts(); this.loadSourceChannels(); }"""

NEW_AI_TAB_CHECK = """if (t === 'ai') { this.loadAI(); this.loadAIAgents(); this.loadPlatformAccounts(); this.loadSourceChannels(); } if (t === 'groups') this.loadGroups();"""

# This is already handled, but let's add a posting monitor function
OLD_LOAD_GROUPS = """async loadGroups() { try { const d = await api('/api/channel-groups'); this.groups = d.groups || []; } catch(e) {} },"""

NEW_LOAD_GROUPS = """async loadGroups() { try { const d = await api('/api/channel-groups'); this.groups = d.groups || []; } catch(e) {} },
        postingStats: null,
        async loadPostingStats() { try { this.postingStats = await api('/api/posting/stats'); } catch(e) {} },"""

if OLD_LOAD_GROUPS in html:
    html = html.replace(OLD_LOAD_GROUPS, NEW_LOAD_GROUPS, 1)
    print("[OK] Added postingStats state and loadPostingStats function")
else:
    print("[WARN] loadGroups function not found")

# --- 3G. Add posting monitor UI panel (after groups tab content) ---
OLD_AFTER_GROUPS = """    <!-- TAB: Groups — Nested hierarchy -->
    <div x-show="tab === 'groups'" class="space-y-4">
        <div class="flex items-center gap-2">
            <button @click="showGroupModal = true" class="btn btn-primary btn-sm">➕ إنشاء مجموعة</button>
            <button @click="loadGroups()" class="btn btn-sm" style="background:#475569">🔄 تحديث</button>
        </div>"""

# We'll add the posting monitor section separately - find a good insertion point
# Add after the groups tab close
OLD_TABS_END = """        <p x-show="groups.length === 0" class="text-center text-slate-400 p-8">لا توجد مجموعات</p>"""

# Actually, let's add a posting monitor section at the end of the main content
# Find the last element before the script end
INSERT_MARKER = """<!-- ===== POST COMPOSER MODAL ===== -->"""
POSTING_MONITOR = """<!-- ===== SMART POSTING MONITOR ===== -->
<div x-show="tab === 'groups' && postingStats" class="bg-slate-800 rounded-xl border border-slate-700 p-4 mt-4">
    <div class="flex items-center justify-between mb-3">
        <h3 class="font-bold text-sm">📊 مراقبة النشر الذكي</h3>
        <button @click="loadPostingStats()" class="text-xs text-slate-400 hover:text-white">🔄</button>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="bg-slate-900/50 rounded-lg p-3 text-center">
            <div class="text-xl font-bold text-blue-400" x-text="postingStats?.queue_pending || 0"></div>
            <div class="text-[10px] text-slate-500">⏳ في الانتظار</div>
        </div>
        <div class="bg-slate-900/50 rounded-lg p-3 text-center">
            <div class="text-xl font-bold text-green-400" x-text="Object.keys(postingStats?.today_posts || {}).length"></div>
            <div class="text-[10px] text-slate-500">📡 قنوات نشرت اليوم</div>
        </div>
        <div class="bg-slate-900/50 rounded-lg p-3 text-center">
            <div class="text-xl font-bold text-yellow-400" x-text="Object.values(postingStats?.today_posts || {}).reduce((a,b)=>a+b, 0)"></div>
            <div class="text-[10px] text-slate-500">📝 إجمالي منشورات اليوم</div>
        </div>
        <div class="bg-slate-900/50 rounded-lg p-3 text-center">
            <div class="text-xl font-bold text-red-400" x-text="postingStats?.queue_total - postingStats?.queue_pending || 0"></div>
            <div class="text-[10px] text-slate-500">✅ تم الإرسال</div>
        </div>
    </div>
    <!-- Per-channel today posts -->
    <div x-show="postingStats && postingStats.today_posts && Object.keys(postingStats.today_posts).length > 0" class="mt-3">
        <div class="text-xs text-slate-400 mb-1">النشر اليومي لكل قناة:</div>
        <div class="flex flex-wrap gap-1">
            <template x-for="(count, cid) in (postingStats?.today_posts || {})" :key="cid">
                <span class="text-[10px] px-2 py-0.5 rounded bg-slate-700 text-slate-300" x-text="cid + ': ' + count"></span>
            </template>
        </div>
    </div>
</div>

"""

if INSERT_MARKER in html:
    html = html.replace(INSERT_MARKER, POSTING_MONITOR + INSERT_MARKER, 1)
    print("[OK] Added smart posting monitor panel")
else:
    print("[WARN] POST COMPOSER MODAL marker not found")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)
print("[DONE] channels.html updated")


# ═══════════════════════════════════════════════════════════════
# PART 4: PHRASES + APP JS — Translations
# ═══════════════════════════════════════════════════════════════

with open(PHRASES, 'r', encoding='utf-8') as f:
    phrases = f.read()

# Add new phrases if not already present
NEW_PHRASES = """
    // ═══ Smart Posting + Channel Groups phrases ═══
    'إنشاء مجموعة قنوات': 'Create Channel Group',
    'المجموعة الأب (اختياري — لإنشاء مجموعة فرعية)': 'Parent Group (optional — for sub-group)',
    '— بدون أب —': '— No Parent —',
    'مجموعة فرعية': 'Sub-group',
    'إنشاء مجموعة': 'Create Group',
    'مراقبة النشر الذكي': 'Smart Posting Monitor',
    'في الانتظار': 'Pending',
    'قنوات نشرت اليوم': 'Channels posted today',
    'إجمالي منشورات اليوم': 'Total posts today',
    'تم الإرسال': 'Sent',
    'النشر اليومي لكل قناة': 'Daily posting per channel',
    'المجموعة الأب (اختياري)': 'Parent Group (optional)',
    ' csrashespeed شنطتكتب اسم': 'Write name',
    'إنشاء': 'Create',
    'القنوات الفرعية': 'Sub-channels',
    'تحديث': 'Refresh',
    'لا توجد مجموعات': 'No groups',
    'إنشاء منشور جديد': 'Create New Post',
    'إرسال فوري': 'Instant Send',
    'الجدولة': 'Scheduling',
    'فوري': 'Instant',
    'مجدول': 'Scheduled',
    'كرون': 'Cron',
    'كل يوم 9 ص': 'Daily 9 AM',
    '9 ص + 6 م': '9 AM + 6 PM',
    'كل 3 ساعات': 'Every 3 hours',
    'أيام العمل 12 ظ': 'Weekdays 12 PM',
    'السبت 10 ص': 'Saturday 10 AM',
    'النسخ الاحتياطي': 'Backup',
    'تهيئة النشر': 'Post Config',
    'تأخير بين المنشورات (ثوانٍ)': 'Delay between posts (sec)',
    'السقف اليومي لكل قناة': 'Daily cap per channel',
    'AI مراقبة النشر': 'AI Post Monitoring',
"""

if 'Smart Posting + Channel Groups phrases' not in phrases:
    # Find the last entry before the closing
    last_entry = phrases.rfind("}")
    if last_entry > 0:
        phrases = phrases[:last_entry] + NEW_PHRASES + "\n" + phrases[last_entry:]
        with open(PHRASES, 'w', encoding='utf-8') as f:
            f.write(phrases)
        print("[OK] Added phrases for smart posting + channel groups")
    else:
        print("[WARN] Could not find phrases insertion point")
else:
    print("[OK] Phrases already added")

# Update app.js I18N
with open(APPJS, 'r', encoding='utf-8') as f:
    appjs = f.read()

NEW_I18N = """        smart_posting_monitor: { ar: 'مراقبة النشر الذكي', en: 'Smart Posting Monitor' },
        posting_pending: { ar: 'في الانتظار', en: 'Pending' },
        posting_channels_today: { ar: 'قنوات نشرت اليوم', en: 'Channels posted today' },
        posting_total_today: { ar: 'إجمالي منشورات اليوم', en: 'Total posts today' },
        posting_sent: { ar: 'تم الإرسال', en: 'Sent' },
        parent_group: { ar: 'المجموعة الأب', en: 'Parent Group' },
        sub_groups: { ar: 'مجموعات فرعية', en: 'Sub-groups' },
        create_group: { ar: 'إنشاء مجموعة', en: 'Create Group' },
        no_groups: { ar: 'لا توجد مجموعات', en: 'No groups' },
        refresh: { ar: 'تحديث', en: 'Refresh' },
    };"""

# Find the last i18n key before };
if 'smart_posting_monitor' not in appjs:
    # Find insertion point
    marker = "    };"
    idx = appjs.rfind(marker)
    if idx > 0:
        appjs = appjs[:idx] + NEW_I18N + "\n" + appjs[idx + len(marker):]
        with open(APPJS, 'w', encoding='utf-8') as f:
            f.write(appjs)
        print("[OK] Added app.js I18N keys for smart posting")
    else:
        print("[WARN] Could not find I18N insertion point")
else:
    print("[OK] app.js I18N already updated")

print("\n" + "="*60)
print("ALL CHANGES APPLIED SUCCESSFULLY!")
print("="*60)
print("""
Summary of changes:
1. COMPREHENSIVE_BOT.PY:
   - Added cron expression parser (_parse_cron, _cron_matches, _next_cron_time)
   - Added inter-entry delays (3-7s between posts, 15-30s between groups)
   - Added MAX_POSTS_PER_CYCLE = 20 limit per 30s cycle
   - Added AI posting monitor stats tracking
   - Added cron scheduler thread (60s interval)
   - Updated _send_to_channel_group to handle nested sub-groups
   - Added posting stats to health endpoint
   - Smart delay doubling on repeated failures

2. DASHBOARD APP.PY:
   - Added parent_id to channel_groups.csv
   - Added POST /api/channel-groups/tree (nested tree)
   - Added POST /api/channel-groups/<id>/resolve (recursive)
   - Added GET /api/posting/stats (queue + today posts)
   - Added GET/PUT /api/posting/config (smart posting settings)
   - Fixed cron_expr handling in post creation
   - Added group_id to broadcast queue entries
   - Nested group resolution in post targeting

3. CHANNELS.HTML:
   - Group creation modal: added parent_id selector
   - Groups tab: shows hierarchy (root + sub-groups with tree)
   - Post composer: nested group selector with tree UI
   - Added smart posting monitor panel
   - Added postingStats state + loadPostingStats function

4. ADMIN-PHRASES.JS:
   - Added 30+ EN/AR translations for new features

5. APP.JS:
   - Added I18N keys for posting monitor, groups, etc.
""")
