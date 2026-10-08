#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI SEO Agent — وكيل SEO بالذكاء الاصطناعي
يستخدم OpenAI/Claude لتوليد محتوى SEO محسّن وتحليل الكلمات المفتاحية
"""

import os
import re
import json
import time
import logging
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEO_CONTENT_FILE = os.path.join(BASE_DIR, 'seo_content.json')
SEO_PERFORMANCE_FILE = os.path.join(BASE_DIR, 'seo_performance.json')
SEO_SETTINGS_FILE = os.path.join(BASE_DIR, 'seo_settings.json')
COMPANY_TRANSLATIONS_FILE = os.path.join(BASE_DIR, 'company_translations.json')

SITE_DOMAIN = 'https://vex.deals'
SITE_NAME = 'VEX'

ALL_LANGUAGES = ['ar', 'en', 'fr', 'es', 'de', 'it', 'pt', 'ru', 'zh', 'tr', 'ur', 'hi', 'fa', 'id', 'ja', 'ko', 'th']

logger = logging.getLogger('ai_seo_agent')

COMPANY_KEYWORDS = {
    '1XBET': {
        'primary': ['1xbet', '1xbet مراجعة', '1xbet review', '1xbet تقييم', '1xbet betting'],
        'secondary': ['1xbet كازينو', '1xbet رهانات', '1xbet تسجيل', '1xbet promo code', '1xbet bonus',
                      '1xbet arabic', '1xbet حساب', '1xbet سحب', '1xbet إيداع'],
        'long_tail': ['مراجعة شاملة لشركة 1xbet 2026', 'هل 1xbet موثوقة', 'أفضل بونص في 1xbet',
                      '1xbet vs melbet مقارنة', 'كيفية التسجيل في 1xbet'],
    },
    'MELBET': {
        'primary': ['melbet', 'melbet مراجعة', 'melbet review', 'melbet تقييم', 'melbet betting'],
        'secondary': ['melbet كازينو', 'melbet رهانات', 'melbet تسجيل', 'melbet promo code', 'melbet bonus',
                      'melbet عربي', 'melbet سحب', 'melbet إيداع'],
        'long_tail': ['مراجعة شاملة لشركة melbet 2026', 'هل melbet موثوقة', 'أفضل بونص في melbet',
                      'melbet vs 1xbet مقارنة', 'elmet[filiate link'],
    },
    'BETJAM': {
        'primary': ['betjam', 'betjam مراجعة', 'betjam review', 'betjam تقييم'],
        'secondary': ['betjam كازينو', 'betjam رهانات', 'betjam تسجيل', 'betjam promo code',
                      'betjam عربي', 'betjam سحب'],
        'long_tail': ['مراجعة شاملة لشركة betjam 2026', 'هل betjam موثوقة', 'betjam vs melbet مقارنة'],
    },
    'MOSTBET': {
        'primary': ['mostbet', 'mostbet مراجعة', 'mostbet review', 'mostbet تقييم'],
        'secondary': ['mostbet كازينو', 'mostbet رهانات', 'mostbet تسجيل', 'mostbet promo code',
                      'mostbet عربي', 'mostbet سحب'],
        'long_tail': ['مراجعة شاملة لشركة mostbet 2026', 'هل mostbet موثوقة', 'mostbet vs 1xbet مقارنة'],
    },
    'BIZBET': {
        'primary': ['bizbet', 'bizbet مراجعة', 'bizbet review', 'bizbet تقييم'],
        'secondary': ['bizbet كازينو', 'bizbet رهانات', 'bizbet تسجيل', 'bizbet promo code',
                      'bizbet عربي', 'bizbet سحب'],
        'long_tail': ['مراجعة شاملة لشركة bizbet 2026', 'هل bizbet موثوقة'],
    },
    'XPARI': {
        'primary': ['xpari', 'xpari مراجعة', 'xpari review', 'xpari تقييم'],
        'secondary': ['xpari كازينو', 'xpari رهانات', 'xpari تسجيل', 'xpari promo code',
                      'xpari عربي', 'xpari سحب'],
        'long_tail': ['مراجعة شاملة لشركة xpari 2026', 'هل xpari موثوقة'],
    },
    'LINEBET': {
        'primary': ['linebet', 'linebet مراجعة', 'linebet review', 'linebet تقييم'],
        'secondary': ['linebet كازينو', 'linebet رهانات', 'linebet تسجيل', 'linebet promo code',
                      'linebet عربي', 'linebet سحب'],
        'long_tail': ['مراجعة شاملة لشركة linebet 2026', 'هل linebet موثوقة'],
    },
    'GOOOBET': {
        'primary': ['gooobet', 'gooobet مراجعة', 'gooobet review', 'gooobet تقييم'],
        'secondary': ['gooobet كازينو', 'gooobet رهانات', 'gooobet تسجيل', 'gooobet promo code',
                      'gooobet عربي', 'gooobet سحب'],
        'long_tail': ['مراجعة شاملة لشركة gooobet 2026', 'هل gooobet موثوقة'],
    },
}

LANG_NAMES = {
    'ar': 'العربية', 'en': 'English', 'fr': 'Français', 'es': 'Español',
    'de': 'Deutsch', 'it': 'Italiano', 'pt': 'Português', 'ru': 'Русский',
    'zh': '中文', 'tr': 'Türkçe', 'ur': 'اردو', 'hi': 'हिन्दी',
    'fa': 'فارسی', 'id': 'Bahasa Indonesia', 'ja': '日本語', 'ko': '한국어', 'th': 'ไทย'
}


class AISEOAgent:
    def __init__(self, api_key=None, provider='openai', model=None):
        self.api_key = api_key
        self.provider = provider
        self.model = model
        if not self.api_key:
            self._load_api_key_from_db()

    def _load_api_key_from_db(self):
        db_path = os.path.join(BASE_DIR, 'boterx.db')
        if not os.path.exists(db_path):
            logger.warning("boterx.db not found — cannot load API key")
            return
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ai_api_keys WHERE is_active=1 ORDER BY priority ASC LIMIT 1"
            ).fetchone()
            if row:
                self.api_key = row['api_key']
                self.provider = row['provider'] or 'openai'
                self.model = row['default_model'] or self._default_model()
                logger.info("Loaded AI key: provider=%s model=%s", self.provider, self.model)
            conn.close()
        except Exception as e:
            logger.error("Failed to load API key from DB: %s", e)

    def _default_model(self):
        defaults = {
            'openai': 'gpt-4o', 'anthropic': 'claude-3-5-sonnet-20241022',
            'google': 'gemini-1.5-pro', 'azure': 'gpt-4o',
            'openrouter': 'openai/gpt-4o', 'custom': 'gpt-4o',
        }
        return defaults.get(self.provider, 'gpt-4o')

    def _call_ai(self, prompt, system_prompt=None, max_tokens=2000, temperature=0.7):
        if not self.api_key:
            raise ValueError("No AI API key configured")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        if self.provider in ('openai', 'azure', 'openrouter'):
            return self._call_openai(messages, max_tokens, temperature)
        elif self.provider == 'anthropic':
            return self._call_anthropic(messages, max_tokens, temperature)
        elif self.provider == 'google':
            return self._call_google(messages, max_tokens, temperature)
        else:
            return self._call_openai(messages, max_tokens, temperature)

    def _call_openai(self, messages, max_tokens, temperature):
        base_url = 'https://api.openai.com/v1'
        if self.provider == 'openrouter':
            base_url = 'https://openrouter.ai/api/v1'
        payload = json.dumps({
            "model": self.model or self._default_model(),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode('utf-8')
        req = urllib.request.Request(
            f'{base_url}/chat/completions',
            data=payload,
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data['choices'][0]['message']['content']

    def _call_anthropic(self, messages, max_tokens, temperature):
        system_msg = ""
        user_msgs = []
        for m in messages:
            if m['role'] == 'system':
                system_msg = m['content']
            else:
                user_msgs.append(m['content'])
        prompt = '\n\n'.join(user_msgs)
        payload = json.dumps({
            "model": self.model or "claude-3-5-sonnet-20241022",
            "max_tokens": max_tokens,
            "system": system_msg,
            "messages": [{"role": "user", "content": prompt}],
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'x-api-key': self.api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data['content'][0]['text']

    def _call_google(self, messages, max_tokens, temperature):
        contents = []
        for m in messages:
            role = 'user' if m['role'] == 'user' else 'user'
            contents.append({"role": role, "parts": [{"text": m['content']}]})
        model_name = (self.model or 'gemini-1.5-pro').replace('models/', '')
        payload = json.dumps({
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }).encode('utf-8')
        req = urllib.request.Request(
            f'https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}',
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data['candidates'][0]['content']['parts'][0]['text']

    def analyze_page(self, company_name, page_url=None):
        if not page_url:
            page_url = f'{SITE_DOMAIN}/company/{company_name.lower()}'
        system = (
            f"You are an expert SEO analyst for {SITE_NAME} ({SITE_DOMAIN}), "
            "a betting affiliate platform. Analyze the page and provide a comprehensive "
            "SEO report in Arabic. Return JSON with: score (0-100), title_analysis, "
            "description_analysis, keyword_analysis, content_quality, technical_seo, "
            "competitor_gaps, recommendations (list of {priority, category, issue, suggestion})"
        )
        prompt = (
            f"Analyze the SEO of this betting affiliate page:\n"
            f"Company: {company_name}\nURL: {page_url}\n"
            f"Site: {SITE_NAME}\n\n"
            f"Provide analysis in Arabic JSON format with score 0-100, and detailed "
            f"recommendations for improvement including meta tags, content, keywords, "
            f"and technical SEO issues."
        )
        try:
            result = self._call_ai(prompt, system, max_tokens=2000, temperature=0.3)
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                return json.loads(json_match.group())
            return {'score': 50, 'raw_analysis': result, 'error': 'Could not parse JSON'}
        except Exception as e:
            logger.error("analyze_page failed: %s", e)
            return {'score': 0, 'error': str(e)}

    def generate_meta_tags(self, company_name, company_description='', target_lang='ar'):
        lang_name = LANG_NAMES.get(target_lang, target_lang)
        system = (
            f"You are an SEO expert creating meta tags in {lang_name} for {SITE_NAME}. "
            "Return ONLY a JSON object with: title, description, keywords, og_title, og_description, "
            "twitter_title, twitter_description, twitter_image. "
            "Meta title: 30-60 chars. Description: 120-160 chars. Keywords: 5-10 relevant keywords."
        )
        prompt = (
            f"Generate SEO-optimized meta tags for {company_name} in {lang_name}.\n"
            f"Company description: {company_description[:500]}\n"
            f"Site: {SITE_NAME} ({SITE_DOMAIN})\n"
            f"Page URL: {SITE_DOMAIN}/company/{company_name.lower()}\n"
            f"Include betting/gambling/casino related keywords.\n"
            f"Return ONLY JSON."
        )
        try:
            result = self._call_ai(prompt, system, max_tokens=800, temperature=0.3)
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                tags = json.loads(json_match.group())
                tags.setdefault('target_lang', target_lang)
                return tags
            return {'title': f'{company_name} — VEX', 'description': company_description[:160],
                    'keywords': company_name, 'error': 'parse_failed'}
        except Exception as e:
            logger.error("generate_meta_tags failed: %s", e)
            return {'error': str(e)}

    def generate_content(self, company_name, target_lang='ar'):
        lang_name = LANG_NAMES.get(target_lang, target_lang)
        keywords = COMPANY_KEYWORDS.get(company_name, {})
        primary_kw = keywords.get('primary', [company_name])
        system = (
            f"You are a professional SEO content writer for {SITE_NAME}, a betting affiliate platform. "
            f"Write compelling, SEO-optimized content in {lang_name}.\n"
            f"Requirements:\n"
            f"- Use primary keywords naturally 3-5 times\n"
            f"- Include secondary keywords 1-2 times each\n"
            f"- Write 800-1200 words minimum\n"
            f"- Use proper heading hierarchy (H1, H2, H3)\n"
            f"- Include FAQ section with 5-8 questions\n"
            f"- Include comparison with other betting sites\n"
            f"- Add call-to-action for registration\n"
            f"- Follow E-E-A-T principles (Experience, Expertise, Authoritativeness, Trust)\n"
            f"Return JSON with: page_title, meta_description, meta_keywords, og_title, og_description, "
            f"sections (array of {heading, content}), faq (array of {question, answer}), "
            f"cta_text, internal_links (array of {text, url})"
        )
        prompt = (
            f"Create full SEO content for {company_name} in {lang_name}.\n"
            f"Target keywords: {', '.join(primary_kw)}\n"
            f"Secondary keywords: {', '.join(keywords.get('secondary', []))}\n"
            f"Long-tail keywords: {', '.join(keywords.get('long_tail', []))}\n"
            f"Page URL: {SITE_DOMAIN}/company/{company_name.lower()}\n"
            f"Include pros, cons, bonus details, payment methods, and why choose this company."
        )
        try:
            result = self._call_ai(prompt, system, max_tokens=4000, temperature=0.7)
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                content = json.loads(json_match.group())
                content['generated_at'] = datetime.now().isoformat()
                content['language'] = target_lang
                content['company'] = company_name
                return content
            return {'raw_content': result, 'error': 'parse_failed'}
        except Exception as e:
            logger.error("generate_content failed: %s", e)
            return {'error': str(e)}

    def generate_all_languages_content(self, company_name, languages=None):
        if languages is None:
            languages = ALL_LANGUAGES
        results = {}
        for lang in languages:
            logger.info("Generating content for %s in %s", company_name, lang)
            results[lang] = self.generate_content(company_name, lang)
            time.sleep(0.5)
        return results

    def keyword_research(self, company_name):
        keywords = COMPANY_KEYWORDS.get(company_name, {})
        system = (
            "You are an SEO keyword research expert for a betting affiliate site. "
            "Analyze the provided keywords and suggest improvements. "
            "Return JSON with: primary_keywords (list with search_volume_estimate, difficulty, relevance), "
            "secondary_keywords, long_tail_suggestions (list with keyword, intent, difficulty), "
            "content_gap_keywords, competitor_keywords, recommended_anchor_texts, "
            "keyword_density_analysis, overall_keyword_score (0-100), recommendations"
        )
        prompt = (
            f"Perform keyword research for {company_name} on {SITE_NAME}.\n"
            f"Existing primary keywords: {json.dumps(keywords.get('primary', []))}\n"
            f"Existing secondary keywords: {json.dumps(keywords.get('secondary', []))}\n"
            f"Existing long-tail keywords: {json.dumps(keywords.get('long_tail', []))}\n"
            f"Suggest 10 new high-value keywords, analyze difficulty and search potential, "
            f"and provide a keyword optimization strategy."
        )
        try:
            result = self._call_ai(prompt, system, max_tokens=2000, temperature=0.5)
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                return json.loads(json_match.group())
            return {'raw': result, 'error': 'parse_failed'}
        except Exception as e:
            logger.error("keyword_research failed: %s", e)
            return {'error': str(e)}

    def competitor_analysis(self, company_name):
        system = (
            "You are a competitive SEO analyst for betting affiliate sites. "
            "Compare the given company with industry best practices and competitors. "
            "Return JSON with: our_advantages, our_weaknesses, competitor_benchmarks, "
            "content_gaps, improvement_areas (list with area, priority, action, expected_impact), "
            "overall_competitive_score (0-100), quick_wins, long_term_strategy"
        )
        prompt = (
            f"Analyze competitive SEO position for {company_name} on {SITE_NAME}.\n"
            f"Compare against: 1xbet, melbet, betwinner, parimatch.\n"
            f"Focus on: meta tags quality, content depth, keyword coverage, "
            f"page structure, internal linking, and user engagement signals."
        )
        try:
            result = self._call_ai(prompt, system, max_tokens=2000, temperature=0.5)
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                return json.loads(json_match.group())
            return {'raw': result, 'error': 'parse_failed'}
        except Exception as e:
            logger.error("competitor_analysis failed: %s", e)
            return {'error': str(e)}

    def generate_internal_links(self, company_name, all_companies):
        system = (
            "You are an internal linking strategist for a betting affiliate site. "
            "Suggest internal links to maximize SEO value. "
            "Return JSON with: recommended_links (list with anchor_text, target_url, reason, priority), "
            "hub_pages, cluster_strategy, link_equity_distribution"
        )
        prompt = (
            f"Suggest internal linking strategy for {company_name} page on {SITE_NAME}.\n"
            f"Available pages: {', '.join(c['name'] for c in all_companies if c['name'] != company_name)}\n"
            f"Homepage: {SITE_DOMAIN}\n"
            f"Suggest 5-10 internal links with descriptive anchor texts."
        )
        try:
            result = self._call_ai(prompt, system, max_tokens=1500, temperature=0.5)
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                return json.loads(json_match.group())
            return {'raw': result, 'error': 'parse_failed'}
        except Exception as e:
            logger.error("generate_internal_links failed: %s", e)
            return {'error': str(e)}

    def daily_optimization(self, companies):
        report = {
            'timestamp': datetime.now().isoformat(),
            'companies_analyzed': 0,
            'companies_optimized': 0,
            'average_score': 0,
            'total_improvements': 0,
            'details': {},
        }
        scores = []
        for company in companies:
            name = company.get('name', '')
            if not name:
                continue
            logger.info("Daily optimization for %s", name)
            try:
                meta = self.generate_meta_tags(name)
                content = self.generate_content(name, 'ar')
                keywords = self.keyword_research(name)
                score = 0
                if isinstance(meta, dict) and not meta.get('error'):
                    score += 30
                if isinstance(content, dict) and not content.get('error'):
                    score += 40
                if isinstance(keywords, dict) and not keywords.get('error'):
                    score += 30
                report['details'][name] = {
                    'meta_generated': not meta.get('error'),
                    'content_generated': not content.get('error'),
                    'keywords_researched': not keywords.get('error'),
                    'score': score,
                    'meta': meta,
                    'content': content,
                    'keywords': keywords,
                }
                scores.append(score)
                report['companies_analyzed'] += 1
                if score > 50:
                    report['companies_optimized'] += 1
                report['total_improvements'] += 1
                time.sleep(1)
            except Exception as e:
                logger.error("Optimization failed for %s: %s", name, e)
                report['details'][name] = {'error': str(e)}
        if scores:
            report['average_score'] = round(sum(scores) / len(scores), 1)
        self._save_performance(report)
        return report

    def get_recommendations(self, company_name):
        system = (
            "You are an SEO consultant for a betting affiliate site. "
            "Provide 5-8 actionable recommendations for improving SEO. "
            "Return JSON with: recommendations (list of {title, description, priority, "
            "category, effort, expected_impact, implementation_steps}), "
            "overall_seo_score (0-100), quick_wins (list)"
        )
        prompt = (
            f"Get SEO recommendations for {company_name} on {SITE_NAME}.\n"
            f"Focus on: meta tags, content quality, keyword optimization, "
            f"technical SEO, internal linking, and mobile optimization."
        )
        try:
            result = self._call_ai(prompt, system, max_tokens=2000, temperature=0.5)
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                return json.loads(json_match.group())
            return {'raw': result, 'error': 'parse_failed'}
        except Exception as e:
            logger.error("get_recommendations failed: %s", e)
            return {'error': str(e)}

    def score_company_page(self, company_name, current_content=None):
        system = (
            "You are an SEO scoring engine. Score a company page 0-100 based on: "
            "meta tags (20), content quality (25), keyword optimization (20), "
            "technical SEO (15), user experience (10), internal linking (10). "
            "Return JSON with: total_score, breakdown ({meta, content, keywords, technical, ux, internal_links}), "
            "grade (A-F), issues (list), suggestions (list)"
        )
        content_info = ""
        if current_content:
            content_info = json.dumps(current_content, ensure_ascii=False)[:2000]
        prompt = (
            f"Score the SEO of {company_name} page on {SITE_NAME}.\n"
            f"Current content info: {content_info}\n"
            f"URL: {SITE_DOMAIN}/company/{company_name.lower()}\n"
        )
        try:
            result = self._call_ai(prompt, system, max_tokens=1500, temperature=0.3)
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                return json.loads(json_match.group())
            return {'total_score': 50, 'error': 'parse_failed'}
        except Exception as e:
            logger.error("score_company_page failed: %s", e)
            return {'total_score': 0, 'error': str(e)}

    def _save_performance(self, report):
        performance = self._load_performance()
        history = performance.get('daily_history', [])
        history.append(report)
        if len(history) > 90:
            history = history[-90:]
        performance['daily_history'] = history
        performance['last_run'] = datetime.now().isoformat()
        if report.get('average_score'):
            performance['latest_score'] = report['average_score']
        if not performance.get('best_score') or report.get('average_score', 0) > performance.get('best_score', 0):
            performance['best_score'] = report.get('average_score', 0)
        if not performance.get('worst_score') or report.get('average_score', 0) < performance.get('worst_score', 0):
            performance['worst_score'] = report.get('average_score', 0)
        self._write_json(SEO_PERFORMANCE_FILE, performance)

    @staticmethod
    def _load_performance():
        return _load_json(SEO_PERFORMANCE_FILE)

    @staticmethod
    def _write_json(filepath, data):
        tmp = filepath + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, filepath)


# ===== Module-level helpers =====

def _load_json(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_json(filepath, data):
    tmp = filepath + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, filepath)


def load_seo_content():
    return _load_json(SEO_CONTENT_FILE)


def save_seo_content(data):
    _save_json(SEO_CONTENT_FILE, data)


def load_seo_performance():
    return _load_json(SEO_PERFORMANCE_FILE)


def load_seo_settings():
    return _load_json(SEO_SETTINGS_FILE)


def save_seo_settings(data):
    _save_json(SEO_SETTINGS_FILE, data)


def get_ai_agent(api_key=None, provider=None):
    agent = AISEOAgent(api_key=api_key, provider=provider or 'openai')
    return agent
