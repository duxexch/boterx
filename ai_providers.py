#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام الذكاء الاصطناعي متعدد المزودين — Multi-Provider AI System
يدعم: OpenAI + Claude (Anthropic) + Kimi (Moonshot) + أي مزود جديد
"""

import os
import json
import urllib.request
import logging

logger = logging.getLogger(__name__)


class AIProvider:
    """القاعدة الأساسية لمزود AI"""
    name = 'base'
    display_name = 'Base AI'
    api_key_env = ''

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv(self.api_key_env, '')

    def is_available(self):
        return bool(self.api_key)

    def process(self, text, instructions):
        """معالجة نص وإرجاع النتيجة"""
        raise NotImplementedError

    def _make_request(self, url, payload, headers=None):
        """طلب HTTP عام"""
        if not headers:
            headers = {'Content-Type': 'application/json'}
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode('utf-8'))


class OpenAIProvider(AIProvider):
    """مزود OpenAI (GPT-4o, GPT-4o-mini, GPT-3.5-turbo)"""
    name = 'openai'
    display_name = '🤖 OpenAI (GPT)'
    api_key_env = 'OPENAI_API_KEY'

    def process(self, text, instructions):
        if not self.is_available():
            return None
        try:
            url = 'https://api.openai.com/v1/chat/completions'
            model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': instructions},
                    {'role': 'user', 'content': f'أعد صياغة هذا البوست:\n\n{text}'}
                ],
                'max_tokens': 2000,
                'temperature': 0.7
            }
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            result = self._make_request(url, payload, headers)
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            return content if len(content) > 10 else None
        except Exception as e:
            logger.error(f"خطأ OpenAI: {e}")
            return None


class ClaudeProvider(AIProvider):
    """مزود Claude (Anthropic)"""
    name = 'claude'
    display_name = '🧠 Claude (Anthropic)'
    api_key_env = 'CLAUDE_API_KEY'

    def process(self, text, instructions):
        if not self.is_available():
            return None
        try:
            url = 'https://api.anthropic.com/v1/messages'
            model = os.getenv('CLAUDE_MODEL', 'claude-3-5-sonnet-20241022')
            payload = {
                'model': model,
                'max_tokens': 2000,
                'system': instructions,
                'messages': [
                    {'role': 'user', 'content': f'أعد صياغة هذا البوست:\n\n{text}'}
                ]
            }
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key,
                'anthropic-version': '2023-06-01'
            }
            result = self._make_request(url, payload, headers)
            content = result.get('content', [{}])[0].get('text', '').strip()
            return content if len(content) > 10 else None
        except Exception as e:
            logger.error(f"خطأ Claude: {e}")
            return None


class KimiProvider(AIProvider):
    """مزود Kimi (Moonshot AI)"""
    name = 'kimi'
    display_name = '🌙 Kimi (Moonshot)'
    api_key_env = 'KIMI_API_KEY'

    def process(self, text, instructions):
        if not self.is_available():
            return None
        try:
            url = 'https://api.moonshot.cn/v1/chat/completions'
            model = os.getenv('KIMI_MODEL', 'moonshot-v1-8k')
            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': instructions},
                    {'role': 'user', 'content': f'أعد صياغة هذا البوست:\n\n{text}'}
                ],
                'max_tokens': 2000,
                'temperature': 0.7
            }
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            result = self._make_request(url, payload, headers)
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            return content if len(content) > 10 else None
        except Exception as e:
            logger.error(f"خطأ Kimi: {e}")
            return None


class OpenRouterProvider(AIProvider):
    """مزود OpenRouter — يدعم كل النماذج عبر OpenAI-compatible API"""
    name = 'openrouter'
    display_name = '🔀 OpenRouter (كل النماذج)'
    api_key_env = 'OPENROUTER_API_KEY'

    def __init__(self, api_key=None):
        super().__init__(api_key)
        if not self.api_key:
            self.api_key = self._load_key_from_db()

    def _load_key_from_db(self):
        try:
            import sqlite3
            for db_path in [
                os.getenv('BOTERX_DB', ''),
                '/opt/bot/boterx.db',
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard', 'boterx.db'),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'boterx.db'),
            ]:
                if db_path and os.path.exists(db_path):
                    conn = sqlite3.connect(db_path)
                    row = conn.execute("SELECT api_key FROM ai_api_keys WHERE (provider LIKE '%openrouter%' OR key_name LIKE '%openrouter%') AND is_active=1 ORDER BY priority ASC LIMIT 1").fetchone()
                    conn.close()
                    if row and row[0]:
                        return row[0]
        except Exception:
            pass
        return ''

    def process(self, text, instructions):
        if not self.is_available():
            return None
        try:
            url = 'https://openrouter.ai/api/v1/chat/completions'
            model = os.getenv('OPENROUTER_MODEL', 'openai/gpt-4o-mini')
            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': instructions},
                    {'role': 'user', 'content': f'أعد صياغة هذا البوست:\n\n{text}'}
                ],
                'max_tokens': 2000,
                'temperature': 0.7
            }
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
                'HTTP-Referer': 'https://vex.deals',
                'X-Title': 'VEX Games AI'
            }
            result = self._make_request(url, payload, headers)
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            return content if len(content) > 10 else None
        except Exception as e:
            logger.error(f"خطأ OpenRouter: {e}")
            return None


class AIManager:
    """مدير كل مزودي AI — يختار المزود النشط ويعالج النصوص"""

    def __init__(self):
        self.providers = {
            'openai': OpenAIProvider(),
            'claude': ClaudeProvider(),
            'kimi': KimiProvider(),
            'openrouter': OpenRouterProvider(),
        }

    def get_available_providers(self):
        """قائمة المزودين المتاحين (لديهم API key)"""
        available = []
        for key, provider in self.providers.items():
            if provider.is_available():
                available.append({
                    'name': provider.name,
                    'display_name': provider.display_name,
                    'available': True
                })
            else:
                available.append({
                    'name': provider.name,
                    'display_name': provider.display_name,
                    'available': False
                })
        return available

    def get_active_provider_name(self):
        """المزود النشط من الإعدادات"""
        return os.getenv('AI_ACTIVE_PROVIDER', 'openai')

    def get_active_provider(self):
        """المزود النشط ككائن"""
        active_name = self.get_active_provider_name()
        provider = self.providers.get(active_name)
        if provider and provider.is_available():
            return provider
        # fallback: أول مزود متاح
        for provider in self.providers.values():
            if provider.is_available():
                return provider
        return None

    def process(self, text, instructions, provider_name=None):
        """
        معالجة نص باستخدام AI
        - provider_name: لو محدد، يستخدم مزود معين. لو None، يستخدم النشط
        """
        if provider_name:
            provider = self.providers.get(provider_name)
            if not provider or not provider.is_available():
                logger.warning(f"AI provider '{provider_name}' غير متاح")
                return None, provider_name
        else:
            provider = self.get_active_provider()
            provider_name = self.get_active_provider_name()

        if not provider:
            logger.warning("لا يوجد مزود AI متاح")
            return None, None

        result = provider.process(text, instructions)
        return result, provider.name

    def test_provider(self, provider_name=None):
        """اختبار مزود — يرسل نص بسيط"""
        instructions = "أعد كتابة النص التالي باحترافية مع إيموجي:"
        test_text = "مرحبا بكم في منصتنا المالية"
        result, used_provider = self.process(test_text, instructions, provider_name)
        return {
            'success': result is not None,
            'provider': used_provider,
            'result': result or 'فشل الاختبار',
            'test_input': test_text
        }
