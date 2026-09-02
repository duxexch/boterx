#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEO Agent — تحليل SEO ذكي للشركات
يحلل صفحات الشركات ويولد تقييمات وتوصيات
"""

import os
import json
import re
import hashlib
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEO_DATA_FILE = os.path.join(BASE_DIR, 'seo_data.json')

SITE_DOMAIN = 'https://vex.deals'


class MetaTagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ''
        self.meta_tags = {}
        self.headings = {f'h{i}': [] for i in range(1, 7)}
        self.links = []
        self.images = []
        self.text_length = 0
        self._in_title = False
        self._in_head = False
        self._in_body = False
        self._current_text = []
        self._body_text = []
        self.canonical = ''
        self.structured_data = []
        self.open_graph = {}
        self.twitter_cards = {}

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_lower = tag.lower()

        if tag_lower == 'head':
            self._in_head = True
        elif tag_lower == 'body':
            self._in_body = True
            self._in_head = False
        elif tag_lower == 'title':
            self._in_title = True
        elif tag_lower == 'meta':
            name = attrs_dict.get('name', '').lower()
            prop = attrs_dict.get('property', '').lower()
            content = attrs_dict.get('content', '')
            if name:
                self.meta_tags[name] = content
            if prop.startswith('og:'):
                self.open_graph[prop] = content
            if prop.startswith('twitter:'):
                self.twitter_cards[prop] = content
        elif tag_lower == 'link':
            rel = attrs_dict.get('rel', '').lower()
            href = attrs_dict.get('href', '')
            if rel == 'canonical':
                self.canonical = href
        elif tag_lower in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._current_text = []
        elif tag_lower == 'a':
            href = attrs_dict.get('href', '')
            self.links.append(href)
        elif tag_lower == 'img':
            alt = attrs_dict.get('alt', '')
            src = attrs_dict.get('src', '')
            self.images.append({'src': src, 'alt': alt})
        elif tag_lower == 'script':
            type_attr = attrs_dict.get('type', '')
            if type_attr == 'application/ld+json':
                self._current_text = []
                self._in_title = False

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == 'title':
            self._in_title = False
        elif tag_lower in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            text = ''.join(self._current_text).strip()
            if text:
                self.headings[tag_lower].append(text)
            self._current_text = []
        elif tag_lower == 'script':
            if self._current_text:
                try:
                    sd = json.loads(''.join(self._current_text))
                    if isinstance(sd, dict) and '@context' in sd:
                        self.structured_data.append(sd)
                except (json.JSONDecodeError, ValueError):
                    pass
                self._current_text = []

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_body:
            self._body_text.append(data)
        if self._current_text is not None:
            self._current_text.append(data)

    def get_body_text(self):
        text = ' '.join(self._body_text)
        self.text_length = len(text)
        return text


def _fetch_page(url, timeout=15):
    """Fetch a page and return its HTML content."""
    try:
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; VEX-SEO-Bot/1.0)',
            'Accept': 'text/html,application/xhtml+xml',
        })
        with urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                return None, f'Not HTML: {content_type}'
            return resp.read().decode('utf-8', errors='replace'), None
    except URLError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


def _word_count(text):
    """Count words in text."""
    words = re.findall(r'\w+', text)
    return len(words)


def _analyze_text_quality(text):
    """Analyze text quality metrics."""
    if not text:
        return {'score': 0, 'issues': ['لا يوجد محتوى نصي']}

    word_count = _word_count(text)
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    avg_sentence_length = word_count / max(len(sentences), 1)
    paragraphs = text.count('\n\n') + 1

    issues = []
    score = 100

    if word_count < 100:
        score -= 30
        issues.append(f'المحتوى قصير جداً ({word_count} كلمة — يُنصح بـ 300+)')
    elif word_count < 300:
        score -= 15
        issues.append(f'المحتوى متوسط ({word_count} كلمة — يُنصح بـ 300+)')
    if avg_sentence_length > 25:
        score -= 10
        issues.append('جمل طويلة جداً — يُنصح بتقسيمها')
    if paragraphs < 2:
        score -= 5
        issues.append('نص متواصل بدون فقرات')

    return {'score': max(0, score), 'issues': issues, 'word_count': word_count}


def analyze_company_page(company_name, company_url=None):
    """
    Analyze a company's page for SEO.
    Returns a comprehensive SEO report.
    """
    if not company_url:
        company_url = f'{SITE_DOMAIN}/company/{company_name.lower()}'

    html, error = _fetch_page(company_url)
    if error:
        return {
            'score': 0,
            'url': company_url,
            'error': error,
            'analyzed_at': datetime.now().isoformat(),
            'issues': [f'تعذر تحميل الصفحة: {error}'],
            'recommendations': ['تأكد من أن الرابط صالح ويمكن الوصول إليه'],
        }

    parser = MetaTagParser()
    try:
        parser.feed(html)
    except Exception as e:
        return {
            'score': 0,
            'url': company_url,
            'error': f'Parse error: {e}',
            'analyzed_at': datetime.now().isoformat(),
        }

    body_text = parser.get_body_text()
    issues = []
    recommendations = []
    details = {}
    score = 100

    # === Title Analysis ===
    title = parser.title.strip()
    details['title'] = title
    if not title:
        score -= 20
        issues.append('العنوان (Title) مفقود')
        recommendations.append('أضف عنواناً واضحاً ومميزاً يحتوي على اسم الشركة')
    elif len(title) < 10:
        score -= 10
        issues.append(f'العنوان قصير جداً ({len(title)} حرف — يُنصح بـ 30-60)')
        recommendations.append('اجعل العنوان بين 30-60 حرف')
    elif len(title) > 60:
        score -= 5
        issues.append(f'العنوان طويل ({len(title)} حرف — يُنصح بـ 30-60)')

    # === Meta Description ===
    meta_desc = parser.meta_tags.get('description', '')
    details['meta_description'] = meta_desc
    if not meta_desc:
        score -= 20
        issues.append('الوصف (Meta Description) مفقود')
        recommendations.append('أضف وصفاً تفصيلياً للشركة بين 120-160 حرف')
    elif len(meta_desc) < 50:
        score -= 10
        issues.append(f'الوصف قصير جداً ({len(meta_desc)} حرف)')
        recommendations.append('اجعل الوصف بين 120-160 حرف')
    elif len(meta_desc) > 160:
        score -= 5
        issues.append(f'الوصف طويل ({len(meta_desc)} حرف — يُنصح بـ 120-160)')

    # === Keywords Meta Tag ===
    keywords = parser.meta_tags.get('keywords', '')
    details['keywords'] = keywords
    if not keywords:
        score -= 5
        issues.append('وسم الكلمات المفتاحية مفقود')
        recommendations.append('أضف الكلمات المفتاحية المرتبطة بالشركة')

    # === Open Graph ===
    og_title = parser.open_graph.get('og:title', '')
    og_desc = parser.open_graph.get('og:description', '')
    og_image = parser.open_graph.get('og:image', '')
    og_type = parser.open_graph.get('og:type', '')
    details['og_title'] = og_title
    details['og_description'] = og_desc
    details['og_image'] = og_image
    details['og_type'] = og_type

    if not og_title:
        score -= 5
        issues.append('og:title مفقود — يُحسن ظهور المشاركة على وسائل التواصل')
        recommendations.append('أضف og:title مطابقاً للعنوان')
    if not og_desc:
        score -= 5
        issues.append('og:description مفقود')
        recommendations.append('أضف og:description للتحكم في ظهور المشاركة')
    if not og_image:
        score -= 10
        issues.append('صورة OG مفقودة — المشاركة ستبدو سيئة')
        recommendations.append('أضف صورة OG بأبعاد 1200x633 بكسل')

    # === Twitter Card ===
    twitter_card = parser.twitter_cards.get('twitter:card', '')
    details['twitter_card'] = twitter_card
    if not twitter_card:
        score -= 3
        issues.append('Twitter Card مفقود')
        recommendations.append('أضف twitter:card و twitter:title')

    # === Headings ===
    for level in ['h1', 'h2', 'h3']:
        texts = parser.headings[level]
        details[f'{level}_tags'] = texts

    h1_count = len(parser.headings['h1'])
    if h1_count == 0:
        score -= 10
        issues.append('لا يوجد عنوان H1')
        recommendations.append('أضف عنوان H1 واحد على الأقل')
    elif h1_count > 1:
        score -= 5
        issues.append(f'عدة عناوين H1 ({h1_count}) — يُنصح بواحد فقط')

    # === Images ===
    images_without_alt = [img for img in parser.images if not img.get('alt')]
    details['total_images'] = len(parser.images)
    details['images_without_alt'] = len(images_without_alt)
    if images_without_alt:
        score -= min(len(images_without_alt) * 2, 15)
        issues.append(f'{len(images_without_alt)} صورة بدون نص بديل (alt text)')

    # === Body Text Quality ===
    text_analysis = _analyze_text_quality(body_text)
    details['text_quality'] = text_analysis
    score = int(score * (text_analysis['score'] / 100 + 0.3) / 1.3)

    # === Canonical ===
    details['canonical'] = parser.canonical
    if not parser.canonical:
        score -= 3
        issues.append('Canonical URL مفقود')

    # === Structured Data ===
    details['structured_data_count'] = len(parser.structured_data)
    if not parser.structured_data:
        score -= 5
        issues.append('لا يوجد Structured Data (JSON-LD)')

    # === Internal Links ===
    internal_links = [l for l in parser.links if l.startswith('/') or SITE_DOMAIN in l]
    details['internal_links'] = len(internal_links)
    details['external_links'] = len(parser.links) - len(internal_links)

    # === Final Score ===
    score = max(0, min(100, score))

    return {
        'score': score,
        'url': company_url,
        'analyzed_at': datetime.now().isoformat(),
        'details': details,
        'issues': issues,
        'recommendations': recommendations,
        'text_word_count': text_analysis.get('word_count', 0),
    }


def generate_optimized_meta(company_name, company_description=''):
    """Generate optimized meta tags for a company."""
    title = f'{company_name} — مراجعة وتقييم شامل | VEX'
    if len(title) > 60:
        title = f'{company_name} | VEX'

    desc = company_description[:157] + '...' if len(company_description) > 160 else company_description
    if not desc:
        desc = f'مراجعة شاملة لشركة {company_name} — المميزات والعيوب والخيارات المتاحة. سجّل الآن عبر VEX.'

    keywords_list = [
        company_name,
        f'مراجعة {company_name}',
        f'{company_name} مراجعة',
        f'تقييم {company_name}',
        'رهانات',
        'مراهنة',
        'كازينو',
        'VEX',
        'منصة ألعاب',
    ]

    return {
        'title': title,
        'description': desc,
        'keywords': ', '.join(keywords_list),
        'og_title': title,
        'og_description': desc,
        'og_type': 'website',
        'twitter_card': 'summary_large_image',
    }


def load_seo_data():
    """Load SEO data from file."""
    try:
        with open(SEO_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seo_data(data):
    """Save SEO data to file."""
    tmp = SEO_DATA_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SEO_DATA_FILE)


def analyze_and_store(company_name, company_url=None):
    """Analyze a company and store results."""
    seo_data = load_seo_data()
    result = analyze_company_page(company_name, company_url)

    if company_name not in seo_data:
        seo_data[company_name] = {'history': []}

    current = {
        'score': result['score'],
        'analyzed_at': result['analyzed_at'],
        'issues': result.get('issues', []),
        'recommendations': result.get('recommendations', []),
        'details': result.get('details', {}),
    }

    history = seo_data[company_name].get('history', [])
    if history:
        last_score = history[-1].get('score', 0)
        current['score_change'] = result['score'] - last_score
    else:
        current['score_change'] = 0

    history.append(current)
    if len(history) > 90:
        history = history[-90:]

    seo_data[company_name] = {
        'current': current,
        'history': history,
        'url': result.get('url', ''),
    }

    save_seo_data(seo_data)
    return current


def analyze_all_companies(companies):
    """Analyze all companies and store results."""
    results = {}
    for company in companies:
        name = company.get('name', '')
        if not name:
            continue
        try:
            results[name] = analyze_and_store(name)
        except Exception as e:
            results[name] = {'score': 0, 'error': str(e)}
    return results
