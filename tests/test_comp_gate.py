# -*- coding: utf-8 -*-
"""اختبارات بوابة تأكيد الإدارة لطلبات التعويض من البوت.

يشغَّل في مجلد مؤقت حتى لا يلمس بيانات المشروع الحقيقية:
    python tests/test_comp_gate.py
"""
import os
import sys
import csv
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# مجلد عمل مؤقت — svrp يقرأ/يكتب CSV بمسارات نسبية من cwd
TMP = tempfile.mkdtemp(prefix='comp_gate_')
os.chdir(TMP)

from svrp import SVRPManager  # noqa: E402
from handlers.callback_handler import CallbackHandlerMixin  # noqa: E402
from handlers.message_dispatcher import MessageDispatcherMixin  # noqa: E402

ACC_FIELDS = SVRPManager.USER_COMPANY_ACCOUNT_FIELDS


class Harness(CallbackHandlerMixin, MessageDispatcherMixin):
    """بوت وهمي: يسجل الرسائل بدلاً من إرسالها لتيليغرام."""

    def __init__(self):
        self.svrp = SVRPManager()
        self.user_states = {}
        self.admin_ids = []
        self.sent = []          # نصوص send_message
        self.edited = []        # نصوص edit_message

    # --- بنية تحتية مزيفة ---
    def send_message(self, chat_id, text, keyboard=None):
        self.sent.append(str(text))

    def edit_message(self, chat_id, message_id, text, *a, **k):
        self.edited.append(str(text))

    def send_inline_message(self, chat_id, text, btns=None):
        self.sent.append(str(text))

    def answer_callback(self, *a, **k):
        pass

    def api_call(self, *a, **k):
        return {}

    def find_user(self, uid):
        return {'customer_id': f'C{uid}', 'language': 'ar'}

    def main_keyboard(self, *a, **k):
        return None

    def tr(self, key, lang='ar', **kw):
        return key

    def is_admin(self, uid):
        return False

    def process_source_channel_post(self, m):
        return False

    def auto_relay_channel_post(self, m):
        return False

    def normalize_button_text(self, text):
        return text

    def get_supported_languages(self):
        return ['ar', 'en']

    def __getattr__(self, name):
        # أي دالة بنية تحتية أخرى غير معرَّفة → stub صامت
        if name.startswith('_'):
            raise AttributeError(name)
        return lambda *a, **k: None


def seed_account(uid, company_id, status):
    row = {'id': f'ACC{company_id}', 'user_id': str(uid), 'company_id': company_id,
           'company_name': f'Co{company_id}', 'account_number': f'AN{company_id}',
           'status': status, 'created_at': '2026-08-16 00:00'}
    with open('user_company_accounts.csv', 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=ACC_FIELDS, extrasaction='ignore')
        w.writerow({k: row.get(k, '') for k in ACC_FIELDS})


def cb(bot, uid, data):
    bot.handle_callback_query({
        'id': 'cb1', 'data': data,
        'from': {'id': uid},
        'message': {'message_id': 1, 'chat': {'id': uid}},
    })


def photo_msg(uid):
    return {'from': {'id': uid}, 'chat': {'id': uid, 'type': 'private'},
            'photo': [{'file_id': 'PHOTO1'}]}


failures = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), '-', name, detail if not cond else '')
    if not cond:
        failures.append(name)


bot = Harness()
UID = 900100

seed_account(UID, 'CP', 'pending')    # معلق
seed_account(UID, 'CA', 'active')     # مؤكد
seed_account(UID, 'CL', '')           # قديم بلا حالة

# 1) اختيار شركة بحساب معلق → يُمنع ولا تُفتح حالة لقطة الشاشة
cb(bot, UID, 'svrp_rec_co_CP')
check('pending blocked at selection',
      any('بانتظار تأكيد الإدارة' in t for t in bot.edited)
      and UID not in bot.user_states)

# 2) حساب مؤكد → تُفتح حالة انتظار لقطة الشاشة
bot.edited.clear()
cb(bot, UID, 'svrp_rec_co_CA')
check('active allowed at selection',
      bot.user_states.get(UID) == 'svrp_waiting_screenshot_CA')

# 3) حساب قديم بلا حالة → لا يُحظر
bot.user_states.pop(UID, None)
cb(bot, UID, 'svrp_rec_co_CL')
check('legacy blank status allowed at selection',
      bot.user_states.get(UID) == 'svrp_waiting_screenshot_CL')

# 4) لقطة شاشة بحالة FSM مزوّرة لحساب معلق → تُمنع وتُمسح الحالة
bot.sent.clear()
bot.user_states[UID] = 'svrp_waiting_screenshot_CP'
bot.process_message(photo_msg(UID))
check('pending blocked at screenshot + FSM cleared',
      any('بانتظار تأكيد الإدارة' in t for t in bot.sent)
      and UID not in bot.user_states)
reqs = bot.svrp._read_csv('recovery_requests.csv')
check('no request created for pending account', len(reqs) == 0)

# 5) حساب مؤكد → الطلب يُنشأ
bot.sent.clear()
bot.user_states[UID] = 'svrp_waiting_screenshot_CA'
bot.process_message(photo_msg(UID))
reqs = bot.svrp._read_csv('recovery_requests.csv')
check('active claim created', len(reqs) == 1
      and any('تم إرسال طلب التعويض' in t for t in bot.sent))

# 6) طلب ثانٍ لنفس الشركة والطلب الأول معلق → يُرفض
bot.sent.clear()
bot.user_states[UID] = 'svrp_waiting_screenshot_CA'
bot.process_message(photo_msg(UID))
reqs = bot.svrp._read_csv('recovery_requests.csv')
check('duplicate pending claim rejected', len(reqs) == 1
      and any('معلق بالفعل' in t for t in bot.sent)
      and UID not in bot.user_states)

# 7) حساب قديم بلا حالة → الطلب يمر (شركة أخرى)
bot.sent.clear()
bot.user_states[UID] = 'svrp_waiting_screenshot_CL'
bot.process_message(photo_msg(UID))
reqs = bot.svrp._read_csv('recovery_requests.csv')
check('legacy blank claim created', len(reqs) == 2)

# 8) بوابة طلب المكافأة (create_bonus_request) — معلق يُمنع، مؤكد يمر
_, err = bot.svrp.create_bonus_request(UID, 'CP', 'CoCP', 'ANCP')
check('bonus request blocked for pending', err and 'بانتظار تأكيد الإدارة' in err)
rid, err = bot.svrp.create_bonus_request(UID, 'CA', 'CoCA', 'ANCA')
check('bonus request allowed for active', rid is not None and err is None)

os.chdir(ROOT)
shutil.rmtree(TMP, ignore_errors=True)

if failures:
    print(f'\n{len(failures)} FAILED:', failures)
    sys.exit(1)
print('\nALL TESTS PASSED')
