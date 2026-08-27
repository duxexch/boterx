"""
AI Composer — توليد بوستات تليجرام بالذكاء الاصطناعي
يستخدم مفاتيح AI المخزنة في ai_api_keys لتوليد محتوى عربي HTML.
"""

import json
import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

# ─── Content type prompts ────────────────────────────────────────
CONTENT_TYPE_PROMPTS = {
    'info': (
        "اكتب بوست تليجرام عربي格式 HTML ي爸爸 Facts وإحصائيات "
        "عن الفريق أو الدوري. استخدم <b> للأرقام المهمة. "
        "النبرة: معلوماتية ومشوقة."
    ),
    'question': (
        "اكتب بوست تليجرام عربي HTML يطرح سؤال تفاعلي عن مباراة أو لاعب. "
        "النبرة: حماسية وتشجع التعليقات."
    ),
    'prediction': (
        "اكتب بوست تليجرام عربي HTML فيه توقعات لمباراة قادمة. "
        "استخدم <b> للنتيجة المتوقعة. النبرة: واثقة وتحليلية."
    ),
    'analysis': (
        "اكتب بوست تليجرام عربي HTML تحليلي لمباراة. "
        "استخدم <b> لأسماء اللاعبين والأرقام. النبرة: احترافية وتحليلية."
    ),
    'live': (
        "اكتب بوست تليجرام عربي HTML لبث مباشر أو حدث جاري. "
        "استخدم 🔴 في البداية. النبرة: عاجلة ومتحمسة."
    ),
    'result': (
        "اكتب بوست تليجرام عربي HTML لنتيجة مباراة. "
        "استخدم <b> للنتيجة وأسماء الهدافين. النبرة: م INFORMATION."
    ),
}

# ─── Read active AI keys from DB ────────────────────────────────
def get_active_keys(db_path):
    """Return list of active AI keys ordered by priority."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT * FROM ai_api_keys WHERE is_active=1 ORDER BY priority ASC, id ASC'
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_active_keys: {e}")
        return []


# ─── Read company data for placeholders ──────────────────────────
def get_company_context(base_dir):
    """Read companies.csv and return first active company's promo/affiliate data."""
    try:
        import csv
        csv_path = os.path.join(base_dir, 'companies.csv')
        if not os.path.exists(csv_path):
            return {}
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                active = (row.get('is_active') or '').lower()
                if active in ('yes', 'active', 'true', '1', ''):
                    return {
                        'company_name': row.get('name', ''),
                        'promo_code': row.get('promo_code', ''),
                        'affiliate_link': row.get('affiliate_link', ''),
                    }
        return {}
    except Exception as e:
        logger.error(f"get_company_context: {e}")
        return {}


# ─── Build the generation prompt ─────────────────────────────────
def build_prompt(content_type, channel_identity, company_data, user_note):
    """Build the full system+user prompt for AI generation."""
    type_instruction = CONTENT_TYPE_PROMPTS.get(content_type, CONTENT_TYPE_PROMPTS['info'])

    system = (
        "أنت كاتب محتوى متخصص في بوستات تليجرام الرياضية. "
        "اكتب بوست باللغة العربية فقط. "
        "استخدم تنسيق HTML خاص بتليجرام: <b>للنص العريض</b>, <i> للمائل</i>, "
        "<a href='...'>للروابط</a>, <blockquote>لاقتباس</blockquote>. "
        "لا تستخدم أي تنسيق HTML آخر. "
        "الحد الأقصى 80 كلمة. "
        "أخرج نص البوست فقط بدون أي شرح أو مقدمة."
    )

    parts = [type_instruction]

    if channel_identity:
        parts.append(f"نبرة القناة: {channel_identity}")

    if company_data.get('company_name'):
        parts.append(f"اسم الشركة/المنتج: {company_data['company_name']}")
    if company_data.get('promo_code'):
        parts.append(f"كود الخصم: {company_data['promo_code']}")
    if company_data.get('affiliate_link'):
        parts.append(f"رابط الإحالة: {company_data['affiliate_link']}")
    if company_data.get('download_link'):
        parts.append(f"رابط التحميل: {company_data['download_link']}")

    if user_note:
        parts.append(f"ملاحظة إضافية: {user_note}")

    parts.append(
        "IMPORTANT: استبدل {promo_code} و {affiliate_link} و {download_link} "
        "بالقيم المذكورة أعلاه إذا وُجدت. "
        "إذا كان المحتوى ترويجي (يذكر كود خصم أو رابط إحالة)، "
        "أضف في النهاية: ⚠️ 18+ — راهن بمسؤولية"
    )

    user_msg = '\n'.join(parts)
    return system, user_msg


# ─── Call the AI API ─────────────────────────────────────────────
def generate_post(key_data, content_type, channel_identity, company_data, user_note, base_dir):
    """
    Generate a Telegram post using AI.
    Returns: {'success': True, 'text': '...'} or {'success': False, 'error': '...'}
    """
    api_key = key_data.get('api_key', '')
    base_url = (key_data.get('base_url') or '').rstrip('/')
    model = key_data.get('default_model', '')
    temperature = float(key_data.get('temperature', 0.7))
    max_tokens = int(key_data.get('max_tokens', 1024))
    timeout = int(key_data.get('timeout_seconds', 60))

    if not api_key:
        return {'success': False, 'error': 'No API key available'}

    # Resolve base URL
    provider = (key_data.get('provider') or '').lower()
    if not base_url:
        if 'openrouter' in provider:
            base_url = 'https://openrouter.ai/api/v1'
        elif 'openai' in provider:
            base_url = 'https://api.openai.com/v1'
        elif 'anthropic' in provider or 'claude' in provider:
            base_url = 'https://api.anthropic.com/v1'
        else:
            base_url = 'https://openrouter.ai/api/v1'

    # Resolve model
    if not model:
        if 'openrouter' in provider:
            model = 'openai/gpt-4o-mini'
        elif 'claude' in provider:
            model = 'claude-3-haiku-20240307'
        else:
            model = 'gpt-4o-mini'

    system_prompt, user_prompt = build_prompt(content_type, channel_identity, company_data, user_note)

    url = base_url + '/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    if 'openrouter' in provider:
        headers['HTTP-Referer'] = 'https://vex.deals'
        headers['X-Title'] = 'VEX Admin Composer'

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': temperature,
        'max_tokens': max_tokens,
    }

    # Try httpx first, fall back to urllib
    try:
        import httpx
        return _call_with_httpx(url, headers, payload, timeout, provider, key_data, base_dir)
    except ImportError:
        return _call_with_urllib(url, headers, payload, timeout, provider, key_data, base_dir)


def _call_with_httpx(url, headers, payload, timeout, provider, key_data, base_dir):
    import httpx
    try:
        with httpx.Client(timeout=float(timeout)) as client:
            resp = client.post(url, headers=headers, json=payload)

        if resp.status_code != 200:
            error_detail = ''
            try:
                error_detail = resp.json().get('error', {}).get('message', resp.text[:200])
            except Exception:
                error_detail = resp.text[:200]
            return {'success': False, 'error': f'API error {resp.status_code}: {error_detail}'}

        data = resp.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        if not content or len(content) < 5:
            return {'success': False, 'error': 'AI returned empty response'}
        content = _clean_content(content)
        _update_key_usage(key_data.get('id'), data.get('usage', {}), base_dir)
        return {'success': True, 'text': content}

    except httpx.TimeoutException:
        return {'success': False, 'error': f'API timeout after {timeout}s'}
    except httpx.ConnectError:
        return {'success': False, 'error': f'Cannot connect to {url}'}
    except Exception as e:
        logger.error(f"AI compose error: {e}")
        return {'success': False, 'error': str(e)}


def _call_with_urllib(url, headers, payload, timeout, provider, key_data, base_dir):
    import urllib.request
    import ssl
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        resp = urllib.request.urlopen(req, timeout=float(timeout), context=ctx)
        data = json.loads(resp.read().decode('utf-8'))

        content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        if not content or len(content) < 5:
            return {'success': False, 'error': 'AI returned empty response'}
        content = _clean_content(content)
        _update_key_usage(key_data.get('id'), data.get('usage', {}), base_dir)
        return {'success': True, 'text': content}

    except urllib.error.HTTPError as e:
        error_detail = ''
        try:
            error_detail = json.loads(e.read().decode()).get('error', {}).get('message', str(e))
        except Exception:
            error_detail = str(e)
        return {'success': False, 'error': f'API error {e.code}: {error_detail}'}
    except Exception as e:
        logger.error(f"AI compose error: {e}")
        return {'success': False, 'error': str(e)}


def _clean_content(content):
    """Clean AI output: remove code fences, extra quotes."""
    if content.startswith('```'):
        lines = content.split('\n')
        content = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
    return content.strip('"').strip("'").strip()


def _update_key_usage(key_id, usage, base_dir):
    """Increment request/token counters for the AI key."""
    if not key_id:
        return
    try:
        db_path = os.path.join(base_dir, 'boterx.db')
        conn = sqlite3.connect(db_path)
        conn.execute(
            'UPDATE ai_api_keys SET requests_today = requests_today + 1, '
            'tokens_today = tokens_today + ? WHERE id = ?',
            (usage.get('total_tokens', 0), key_id)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
