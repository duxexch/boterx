#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSLATION_DICT = os.path.join(ROOT, 'translation_dict.json')
OUT_FILE = os.path.join(ROOT, 'dashboard', 'static', 'js', 'i18n-admin-lexicon.js')

AR_RE = re.compile(r'[\u0600-\u06FF]')
EN_RE = re.compile(r'[A-Za-z]')


def _norm(text):
    text = str(text or '').replace('\u00a0', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def main():
    with open(TRANSLATION_DICT, 'r', encoding='utf-8') as f:
        src = json.load(f)

    ar_to_en = {}
    for ar, en in src.items():
        ar = _norm(ar)
        en = _norm(en)
        if not ar or not en:
            continue
        if not AR_RE.search(ar):
            continue
        if AR_RE.search(en):
            continue
        if not EN_RE.search(en):
            continue
        ar_to_en[ar] = en

    manual_ar_to_en = {
        'معاملات معلقة': 'Pending transactions',
        'معاملة بانتظار المراجعة': 'transaction pending review',
        'معاملات بانتظار المراجعة': 'transactions pending review',
        'النشاط الأخير': 'Last activity',
        'تعليم كمقروء': 'Mark as read',
        'انقر للذهاب': 'Click to open',
        'لا توجد إشعارات': 'No notifications',
        'الإشعارات': 'Notifications',
        'إشعار': 'Notification',
        'الآن': 'Now',
        'قيد الانتظار': 'Pending',
        'تم الإرسال': 'Sent',
        'فشل': 'Failed',
        'وكيل': 'Agent',
        'وكلاء': 'Agents',
        'مصدر': 'Source',
        'نشر': 'Publish',
        'إضافة وكيل': 'Add Agent',
        'إضافة حساب': 'Add Account',
        'إضافة مصدر': 'Add Source',
        'عنوان المصدر': 'Source title',
        'اسم الحساب': 'Account name',
        'نص فقط': 'Text only',
        'صور فقط': 'Photo only',
        'فيديو فقط': 'Video only',
        'تعليمات مخصصة لهذا الوكيل': 'Custom instructions for this agent',
        'بدون احتياطي': 'No fallback',
        'معرفات الوجهة (|)': 'Target IDs (|)',
        'غير معروف': 'Unknown',
    }
    ar_to_en.update(manual_ar_to_en)

    en_to_ar = {}
    for ar, en in ar_to_en.items():
        if en not in en_to_ar:
            en_to_ar[en] = ar

    manual_en_to_ar = {
        'Open': 'مفتوح',
        'Dispute': 'نزاع',
        'Click to go': 'انقر للذهاب',
        'Click to open': 'انقر للفتح',
        'Muted': 'صامت',
        'No data': 'لا توجد بيانات',
        'No notifications': 'لا توجد إشعارات',
        'Pending': 'معلق',
        'Now': 'الآن',
        'Notification': 'إشعار',
        'Notifications': 'الإشعارات',
        'Agent': 'وكيل',
        'Agents': 'وكلاء',
        'Source': 'مصدر',
        'Publish': 'نشر',
        'Add Agent': 'إضافة وكيل',
        'Add Account': 'إضافة حساب',
        'Add Source': 'إضافة مصدر',
        'Source title': 'عنوان المصدر',
        'Account name': 'اسم الحساب',
        'Text only': 'نص فقط',
        'Photo only': 'صور فقط',
        'Video only': 'فيديو فقط',
        'Custom instructions for this agent': 'تعليمات مخصصة لهذا الوكيل',
        'No fallback': 'بدون احتياطي',
        'Target IDs (|)': 'معرفات الوجهة (|)',
        'Unknown': 'غير معروف',
    }
    en_to_ar.update(manual_en_to_ar)

    payload = {
        'generated_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'arToEn': dict(sorted(ar_to_en.items())),
        'enToAr': dict(sorted(en_to_ar.items())),
    }

    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    js = (
        '/* Auto-generated admin lexicon for runtime bilingual translation. */\n'
        'window.ADMIN_I18N_LEXICON = ' + payload_json + ';\n'
    )

    with open(OUT_FILE, 'w', encoding='utf-8', newline='\n') as f:
        f.write(js)

    print(f'Generated: {OUT_FILE}')
    print(f'ar_to_en={len(ar_to_en)} en_to_ar={len(en_to_ar)}')


if __name__ == '__main__':
    main()
