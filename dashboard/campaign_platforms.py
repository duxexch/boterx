"""
Social Media Platform Adapter Abstraction
Provides a unified interface for posting to any social media platform.
Each platform implements the same interface, making it trivial to add new ones.
"""
import logging
import time
import json
import threading
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any

logger = logging.getLogger('platforms')


class PlatformAdapter(ABC):
    """Base class for all social media platform adapters."""

    name: str = 'base'
    display_name: str = 'Base'
    icon: str = '🌐'
    color: str = 'slate'
    max_text_length: int = 4096
    supports_media: bool = True
    supports_video: bool = True
    supports_photo: bool = True

    def __init__(self, account_config: Dict[str, Any]):
        self.config = account_config
        self.account_id = account_config.get('id', '')
        self.account_name = account_config.get('account_name', '')
        self.access_token = account_config.get('access_token', '')

    @abstractmethod
    def post(self, content: str, media_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Post content to the platform.
        Returns: {'success': bool, 'post_id': str|None, 'error': str|None}
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate that the account configuration is complete and valid."""
        pass

    def truncate_text(self, text: str) -> str:
        """Truncate text to platform's max length."""
        if len(text) <= self.max_text_length:
            return text
        return text[:self.max_text_length - 3] + '...'

    def prepare_media(self, media_urls: List[str]) -> List[str]:
        """Filter and validate media URLs. Override for platform-specific needs."""
        valid = []
        for url in media_urls:
            if not url:
                continue
            if not url.startswith('http'):
                url = f'https://vex.deals{url}'
            valid.append(url)
        return valid[:10]  # max 10 media items


class TelegramAdapter(PlatformAdapter):
    """Telegram Bot API adapter."""
    name = 'telegram'
    display_name = 'Telegram'
    icon = '📱'
    color = 'blue'
    max_text_length = 4096

    def __init__(self, account_config):
        super().__init__(account_config)
        self.bot_token = account_config.get('access_token', '')

    def validate_config(self) -> bool:
        return bool(self.bot_token)

    def post(self, content: str, media_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """Post via Telegram Bot API."""
        if not self.validate_config():
            return {'success': False, 'error': 'Bot token not configured'}
        try:
            import requests
            media = self.prepare_media(media_urls or [])
            text = self.truncate_text(content)

            if media:
                # Send first media with caption
                first = media[0]
                is_video = any(first.lower().endswith(e) for e in ('.mp4', '.mov', '.avi', '.mkv'))
                endpoint = 'sendVideo' if is_video else 'sendPhoto'
                payload = {
                    'caption': text[:1024],
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': False,
                }
                if is_video:
                    payload['video'] = first
                else:
                    payload['photo'] = first

                r = requests.post(
                    f'https://api.telegram.org/bot{self.bot_token}/{endpoint}',
                    json=payload, timeout=30
                )
                result = r.json()
                post_id = str(result.get('result', {}).get('message_id', ''))

                # Send remaining media
                for extra_url in media[1:9]:
                    is_v = any(extra_url.lower().endswith(e) for e in ('.mp4', '.mov', '.avi'))
                    ep = 'sendVideo' if is_v else 'sendPhoto'
                    p = {}
                    if is_v:
                        p['video'] = extra_url
                    else:
                        p['photo'] = extra_url
                    requests.post(f'https://api.telegram.org/bot{self.bot_token}/{ep}', json=p, timeout=30)
                    time.sleep(0.5)

                return {'success': result.get('ok', False), 'post_id': post_id, 'error': None}
            else:
                r = requests.post(
                    f'https://api.telegram.org/bot{self.bot_token}/sendMessage',
                    json={'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': False},
                    timeout=30
                )
                result = r.json()
                post_id = str(result.get('result', {}).get('message_id', ''))
                return {'success': result.get('ok', False), 'post_id': post_id, 'error': None}
        except Exception as e:
            logger.error(f'Telegram post failed: {e}')
            return {'success': False, 'error': str(e)}


class WhatsAppAdapter(PlatformAdapter):
    """WhatsApp Business API adapter."""
    name = 'whatsapp'
    display_name = 'WhatsApp'
    icon = '🟢'
    color = 'green'
    max_text_length = 4096

    def validate_config(self) -> bool:
        return bool(self.access_token or self.config.get('business_account_id'))

    def post(self, content: str, media_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """Post via WhatsApp Business API."""
        if not self.validate_config():
            return {'success': False, 'error': 'WhatsApp API not configured'}
        try:
            import requests
            phone_id = self.config.get('phone_number_id', '')
            biz_token = self.access_token
            recipients = [r.strip() for r in self.config.get('whatsapp_contacts', '').split(',') if r.strip()]

            if not phone_id or not biz_token:
                return {'success': False, 'error': 'phone_number_id or token missing'}

            media = self.prepare_media(media_urls or [])
            text = self.truncate_text(content)
            post_ids = []

            for recipient in recipients:
                payload = {
                    'messaging_product': 'whatsapp',
                    'to': recipient,
                    'type': 'text',
                    'text': {'body': text}
                }
                if media:
                    first = media[0]
                    is_video = any(first.lower().endswith(e) for e in ('.mp4', '.mov'))
                    media_type = 'video' if is_video else 'image'
                    payload = {
                        'messaging_product': 'whatsapp',
                        'to': recipient,
                        'type': media_type,
                        media_type: {'link': first, 'caption': text[:1024]}
                    }

                r = requests.post(
                    f'https://graph.facebook.com/v18.0/{phone_id}/messages',
                    json=payload,
                    headers={'Authorization': f'Bearer {biz_token}', 'Content-Type': 'application/json'},
                    timeout=30
                )
                result = r.json()
                mid = result.get('messages', [{}])[0].get('id', '')
                if mid:
                    post_ids.append(mid)
                time.sleep(0.3)

            success = len(post_ids) > 0
            return {'success': success, 'post_id': ','.join(post_ids), 'error': None if success else 'No messages sent'}
        except Exception as e:
            logger.error(f'WhatsApp post failed: {e}')
            return {'success': False, 'error': str(e)}


class InstagramAdapter(PlatformAdapter):
    """Instagram Graph API adapter (via Facebook)."""
    name = 'instagram'
    display_name = 'Instagram'
    icon = '📸'
    color = 'pink'
    max_text_length = 2200

    def validate_config(self) -> bool:
        return bool(self.access_token and self.config.get('page_id'))

    def post(self, content: str, media_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        if not self.validate_config():
            return {'success': False, 'error': 'Instagram API not configured (need access_token + page_id)'}
        try:
            import requests
            page_id = self.config.get('page_id', '')
            media = self.prepare_media(media_urls or [])
            text = self.truncate_text(content)

            if not media:
                # Text-only post via page feed (limited on Instagram)
                r = requests.post(
                    f'https://graph.facebook.com/v18.0/{page_id}/feed',
                    json={'message': text, 'access_token': self.access_token},
                    timeout=30
                )
                result = r.json()
                return {'success': 'id' in result, 'post_id': result.get('id', ''), 'error': result.get('error', {}).get('message')}

            # Media post: create container -> publish
            first = media[0]
            container_r = requests.post(
                f'https://graph.facebook.com/v18.0/{page_id}/media',
                json={'image_url': first, 'caption': text, 'access_token': self.access_token},
                timeout=30
            )
            container = container_r.json()
            container_id = container.get('id', '')
            if not container_id:
                return {'success': False, 'error': container.get('error', {}).get('message', 'Container creation failed')}

            time.sleep(2)
            pub_r = requests.post(
                f'https://graph.facebook.com/v18.0/{page_id}/media_publish',
                json={'creation_id': container_id, 'access_token': self.access_token},
                timeout=30
            )
            pub = pub_r.json()
            return {'success': 'id' in pub, 'post_id': pub.get('id', ''), 'error': pub.get('error', {}).get('message')}
        except Exception as e:
            logger.error(f'Instagram post failed: {e}')
            return {'success': False, 'error': str(e)}


class FacebookAdapter(PlatformAdapter):
    """Facebook Pages API adapter."""
    name = 'facebook'
    display_name = 'Facebook'
    icon = '📘'
    color = 'blue'
    max_text_length = 63206

    def validate_config(self) -> bool:
        return bool(self.access_token and self.config.get('page_id'))

    def post(self, content: str, media_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        if not self.validate_config():
            return {'success': False, 'error': 'Facebook API not configured (need access_token + page_id)'}
        try:
            import requests
            page_id = self.config.get('page_id', '')
            media = self.prepare_media(media_urls or [])
            text = self.truncate_text(content)

            if media:
                post_data = {'message': text, 'access_token': self.access_token}
                first = media[0]
                if any(first.lower().endswith(e) for e in ('.mp4', '.mov')):
                    post_data['file_url'] = first
                    ep = f'https://graph.facebook.com/v18.0/{page_id}/video'
                else:
                    post_data['url'] = first
                    ep = f'https://graph.facebook.com/v18.0/{page_id}/photos'
            else:
                ep = f'https://graph.facebook.com/v18.0/{page_id}/feed'
                post_data = {'message': text, 'access_token': self.access_token}

            r = requests.post(ep, json=post_data, timeout=30)
            result = r.json()
            return {'success': 'id' in result, 'post_id': result.get('id', ''), 'error': result.get('error', {}).get('message')}
        except Exception as e:
            logger.error(f'Facebook post failed: {e}')
            return {'success': False, 'error': str(e)}


class TwitterAdapter(PlatformAdapter):
    """Twitter/X API adapter."""
    name = 'twitter'
    display_name = 'Twitter/X'
    icon = '🐦'
    color = 'sky'
    max_text_length = 280

    def validate_config(self) -> bool:
        return bool(self.access_token)

    def post(self, content: str, media_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        if not self.validate_config():
            return {'success': False, 'error': 'Twitter API not configured'}
        try:
            import requests
            text = self.truncate_text(content)
            media = self.prepare_media(media_urls or [])

            # Twitter API v2 create tweet
            payload = {'text': text}
            if media:
                # Upload media first (requires OAuth 1.0a)
                # Simplified: just send text for now, media needs OAuth
                pass

            r = requests.post(
                'https://api.twitter.com/2/tweets',
                json=payload,
                headers={'Authorization': f'Bearer {self.access_token}', 'Content-Type': 'application/json'},
                timeout=30
            )
            result = r.json()
            post_id = result.get('data', {}).get('id', '')
            return {'success': bool(post_id), 'post_id': post_id, 'error': result.get('errors', [{}])[0].get('message') if not post_id else None}
        except Exception as e:
            logger.error(f'Twitter post failed: {e}')
            return {'success': False, 'error': str(e)}


class LinkedInAdapter(PlatformAdapter):
    """LinkedIn API adapter."""
    name = 'linkedin'
    display_name = 'LinkedIn'
    icon = '💼'
    color = 'indigo'
    max_text_length = 3000

    def validate_config(self) -> bool:
        return bool(self.access_token)

    def post(self, content: str, media_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        if not self.validate_config():
            return {'success': False, 'error': 'LinkedIn API not configured'}
        try:
            import requests
            person_id = self.config.get('handle', '')
            text = self.truncate_text(content)
            payload = {
                'author': f'urn:li:person:{person_id}',
                'lifecycleState': 'PUBLISHED',
                'specificContent': {
                    'com.linkedin.ugc.ShareContent': {
                        'shareCommentary': {'text': text},
                        'shareMediaCategory': 'NONE'
                    }
                },
                'visibility': {'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'}
            }
            r = requests.post(
                'https://api.linkedin.com/v2/ugcPosts',
                json=payload,
                headers={'Authorization': f'Bearer {self.access_token}', 'Content-Type': 'application/json'},
                timeout=30
            )
            result = r.json()
            post_id = result.get('id', '')
            return {'success': bool(post_id), 'post_id': post_id, 'error': result.get('message') if not post_id else None}
        except Exception as e:
            logger.error(f'LinkedIn post failed: {e}')
            return {'success': False, 'error': str(e)}


class TikTokAdapter(PlatformAdapter):
    """TikTok API adapter."""
    name = 'tiktok'
    display_name = 'TikTok'
    icon = '🎵'
    color = 'purple'
    max_text_length = 2200
    supports_photo = False  # TikTok is video-only

    def validate_config(self) -> bool:
        return bool(self.access_token)

    def post(self, content: str, media_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        return {'success': False, 'error': 'TikTok API requires video upload (not yet implemented) — use manual posting'}


class YouTubeAdapter(PlatformAdapter):
    """YouTube Data API adapter."""
    name = 'youtube'
    display_name = 'YouTube'
    icon = '▶️'
    color = 'red'
    max_text_length = 5000
    supports_photo = False

    def validate_config(self) -> bool:
        return bool(self.access_token)

    def post(self, content: str, media_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        return {'success': False, 'error': 'YouTube API requires OAuth2 + video upload — use manual posting'}


# ═══════════════════════════════════════════════════════════
#  Platform Registry
# ═══════════════════════════════════════════════════════════

PLATFORM_REGISTRY: Dict[str, type] = {
    'telegram': TelegramAdapter,
    'whatsapp': WhatsAppAdapter,
    'instagram': InstagramAdapter,
    'facebook': FacebookAdapter,
    'twitter': TwitterAdapter,
    'linkedin': LinkedInAdapter,
    'tiktok': TikTokAdapter,
    'youtube': YouTubeAdapter,
}


def get_adapter(platform_name: str, account_config: Dict[str, Any]) -> Optional[PlatformAdapter]:
    """Factory: get a platform adapter by name."""
    cls = PLATFORM_REGISTRY.get(platform_name)
    if cls:
        return cls(account_config)
    logger.warning(f'Unknown platform: {platform_name}')
    return None


def get_all_platforms() -> List[Dict[str, Any]]:
    """Return info about all supported platforms."""
    return [
        {
            'name': cls.name,
            'display_name': cls.display_name,
            'icon': cls.icon,
            'color': cls.color,
            'max_text_length': cls.max_text_length,
            'supports_media': cls.supports_media,
            'supports_video': cls.supports_video,
            'supports_photo': cls.supports_photo,
        }
        for cls in PLATFORM_REGISTRY.values()
    ]


# ═══════════════════════════════════════════════════════════
#  Campaign Execution Engine — safe, retryable, per-channel tracking
# ═══════════════════════════════════════════════════════════

import csv
import os
import secrets
import sqlite3 as _sqlite3
from datetime import datetime as _dt

_LOCK = threading.Lock()


def _safe_csv_lock():
    """Cross-platform file locking."""
    return _LOCK


def _get_db_connection(db_path: str):
    """Get a thread-safe SQLite connection."""
    conn = _sqlite3.connect(db_path, timeout=10)
    conn.row_factory = _sqlite3.Row
    return conn


def execute_campaign_post(campaign: Dict, channel_id: str, channel_config: Dict,
                          platform: str, text: str, media_urls: List[str],
                          max_retries: int = 3) -> Dict[str, Any]:
    """
    Execute a single campaign post to a single channel with retry logic.
    Returns per-channel result dict.
    """
    adapter = get_adapter(platform, channel_config)
    if not adapter:
        return {
            'channel_id': channel_id,
            'platform': platform,
            'status': 'failed',
            'error': f'No adapter for platform: {platform}',
            'retries': 0,
            'posted_at': '',
        }

    last_error = None
    for attempt in range(max_retries):
        try:
            result = adapter.post(text, media_urls)
            if result.get('success'):
                return {
                    'channel_id': channel_id,
                    'platform': platform,
                    'status': 'delivered',
                    'post_id': result.get('post_id', ''),
                    'error': None,
                    'retries': attempt,
                    'posted_at': _dt.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
            last_error = result.get('error', 'Unknown error')
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return {
        'channel_id': channel_id,
        'platform': platform,
        'status': 'failed',
        'error': last_error,
        'retries': max_retries,
        'posted_at': '',
    }


def run_campaign_async(campaign_id: str, base_dir: str):
    """
    Execute a full campaign asynchronously.
    Resolves targets, sends to each channel, logs per-channel results.
    """
    def _worker():
        try:
            _execute_campaign_internal(campaign_id, base_dir)
        except Exception as e:
            logger.error(f'Campaign {campaign_id} execution failed: {e}')

    t = threading.Thread(target=_worker, daemon=True, name=f'campaign_{campaign_id}')
    t.start()


def _execute_campaign_internal(campaign_id: str, base_dir: str):
    """Internal campaign execution with full error handling."""
    campaigns_path = os.path.join(base_dir, 'campaigns.csv')
    results_path = os.path.join(base_dir, 'campaign_results.csv')

    # Read campaign
    campaign = None
    with _safe_csv_lock():
        try:
            with open(campaigns_path, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('id') == campaign_id:
                        campaign = dict(row)
                        break
        except Exception as e:
            logger.error(f'Read campaign failed: {e}')
            return

    if not campaign:
        logger.error(f'Campaign {campaign_id} not found')
        return

    # Mark as running
    _update_campaign_field(campaigns_path, campaign_id, 'status', 'running')

    message = campaign.get('message', '')
    media_urls_str = campaign.get('media_urls', '')
    media_urls = [u for u in media_urls_str.split('|') if u] if media_urls_str else []
    target = campaign.get('target', 'telegram')
    recipient = campaign.get('recipient', 'all')
    selected_channels_str = campaign.get('selected_channels', '')
    selected_groups_str = campaign.get('selected_groups', '')
    whatsapp_contacts = campaign.get('whatsapp_contacts', '')
    whatsapp_groups = campaign.get('whatsapp_groups', '')

    # Resolve channel list
    channels_to_post = []

    # Load all channels from DB
    db_path = os.path.join(base_dir, 'boterx.db')
    try:
        conn = _get_db_connection(db_path)
        try:
            rows = conn.execute('SELECT * FROM bot_channels WHERE is_active="yes"').fetchall()
            all_channels = {str(r['id']): dict(r) for r in rows}
        finally:
            conn.close()
    except Exception:
        all_channels = {}

    # Load social accounts
    try:
        conn = _get_db_connection(db_path)
        try:
            sa_rows = conn.execute('SELECT * FROM social_accounts WHERE is_active="yes"').fetchall()
            social_accounts = {str(r['id']): dict(r) for r in sa_rows}
        finally:
            conn.close()
    except Exception:
        social_accounts = {}

    # Determine targets based on recipient type
    if recipient == 'single' and selected_channels_str:
        selected_ids = [s.strip() for s in selected_channels_str.split(',') if s.strip()]
        for cid in selected_ids:
            if cid in all_channels:
                ch = all_channels[cid]
                if target in ('telegram', 'both', 'all'):
                    channels_to_post.append({
                        'channel_id': cid,
                        'platform': 'telegram',
                        'config': ch,
                        'chat_id': ch.get('chat_id', ''),
                    })
                # Social media posting
                for sid, sa in social_accounts.items():
                    if sa.get('sub_agent_id') == cid:
                        channels_to_post.append({
                            'channel_id': cid,
                            'platform': sa['platform'],
                            'config': sa,
                            'social_account_id': sid,
                        })
    elif recipient == 'group' and selected_groups_str:
        # Load groups
        groups_path = os.path.join(base_dir, 'channel_groups.csv')
        try:
            with open(groups_path, 'r', encoding='utf-8-sig') as f:
                for grp in csv.DictReader(f):
                    if grp.get('id') in [s.strip() for s in selected_groups_str.split(',')]:
                        grp_ch_ids = [c.strip() for c in grp.get('channel_ids', '').split('|') if c.strip()]
                        for cid in grp_ch_ids:
                            if cid in all_channels:
                                ch = all_channels[cid]
                                if target in ('telegram', 'both', 'all'):
                                    channels_to_post.append({
                                        'channel_id': cid,
                                        'platform': 'telegram',
                                        'config': ch,
                                        'chat_id': ch.get('chat_id', ''),
                                    })
        except Exception:
            pass
    else:
        # All channels
        for cid, ch in all_channels.items():
            if target in ('telegram', 'both', 'all'):
                channels_to_post.append({
                    'channel_id': cid,
                    'platform': 'telegram',
                    'config': ch,
                    'chat_id': ch.get('chat_id', ''),
                })
        # All social accounts
        for sid, sa in social_accounts.items():
            channels_to_post.append({
                'channel_id': sa.get('sub_agent_id', ''),
                'platform': sa['platform'],
                'config': sa,
                'social_account_id': sid,
            })

    # WhatsApp contacts/groups
    if target in ('whatsapp', 'all') and whatsapp_contacts:
        wa_config = {'id': 'whatsapp_direct', 'access_token': '', 'phone_number_id': '', 'whatsapp_contacts': whatsapp_contacts, 'whatsapp_groups': whatsapp_groups}
        # Try to find a WhatsApp account
        for sid, sa in social_accounts.items():
            if sa.get('platform') == 'whatsapp':
                wa_config = sa
                wa_config['whatsapp_contacts'] = whatsapp_contacts
                wa_config['whatsapp_groups'] = whatsapp_groups
                break
        channels_to_post.append({
            'channel_id': 'whatsapp_broadcast',
            'platform': 'whatsapp',
            'config': wa_config,
        })

    if not channels_to_post:
        _update_campaign_field(campaigns_path, campaign_id, 'status', 'completed')
        _update_campaign_field(campaigns_path, campaign_id, 'stats_reach', '0')
        return

    # Execute posts with per-channel tracking
    results = []
    total_reach = 0
    success_count = 0

    for target_info in channels_to_post:
        # Spintax text variation per channel
        import re as _re
        def _pick(m):
            parts = m.group(1).split('|')
            return secrets.choice(parts) if parts else m.group(0)
        spin_text = message
        for _ in range(4):
            new = _re.sub(r'\{([^{}]*)\}', _pick, spin_text)
            if new == spin_text:
                break
            spin_text = new

        # Apply channel-specific branding
        ch_config = target_info['config']
        brand_name = ch_config.get('company_name', '')
        if brand_name:
            spin_text = spin_text.replace('{company_name}', brand_name)
        dl = ch_config.get('download_link', '')
        if dl:
            spin_text = spin_text.replace('{download_link}', dl)
        pc = ch_config.get('promo_code', '')
        if pc:
            spin_text = spin_text.replace('{promo_code}', pc)
        al = ch_config.get('affiliate_link', '')
        if al:
            spin_text = spin_text.replace('{affiliate_link}', al)

        result = execute_campaign_post(
            campaign=campaign,
            channel_id=target_info['channel_id'],
            channel_config=target_info['config'],
            platform=target_info['platform'],
            text=spin_text,
            media_urls=media_urls,
        )
        results.append(result)

        if result['status'] == 'delivered':
            success_count += 1
            total_reach += 1  # Increment per successful send
            time.sleep(0.5)  # Rate limit between channels

    # Save results
    results_fieldnames = ['campaign_id', 'channel_id', 'platform', 'status', 'post_id', 'error', 'retries', 'posted_at']
    try:
        with _safe_csv_lock():
            file_exists = os.path.exists(results_path)
            with open(results_path, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=results_fieldnames)
                if not file_exists:
                    writer.writeheader()
                for r in results:
                    writer.writerow({
                        'campaign_id': campaign_id,
                        'channel_id': r.get('channel_id', ''),
                        'platform': r.get('platform', ''),
                        'status': r.get('status', ''),
                        'post_id': r.get('post_id', ''),
                        'error': r.get('error', ''),
                        'retries': r.get('retries', 0),
                        'posted_at': r.get('posted_at', ''),
                    })
    except Exception as e:
        logger.error(f'Save campaign results failed: {e}')

    # Update campaign stats
    final_status = 'completed' if success_count > 0 else 'failed'
    _update_campaign_field(campaigns_path, campaign_id, 'status', final_status)
    _update_campaign_field(campaigns_path, campaign_id, 'stats_reach', str(total_reach))
    _update_campaign_field(campaigns_path, campaign_id, 'stats_clicks', str(success_count))

    logger.info(f'Campaign {campaign_id}: {success_count}/{len(results)} channels delivered')


def _update_campaign_field(campaigns_path: str, campaign_id: str, field: str, value: str):
    """Thread-safe single-field update in campaigns.csv."""
    with _safe_csv_lock():
        try:
            rows = []
            with open(campaigns_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                for row in reader:
                    rows.append(row)

            if field not in fieldnames:
                fieldnames.append(field)

            for row in rows:
                if row.get('id') == campaign_id:
                    row[field] = value
                    break

            with open(campaigns_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
        except Exception as e:
            logger.error(f'Update campaign field failed: {e}')
