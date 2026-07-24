#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت LangSense المبسط مع نظام وسائل الدفع
إصدار مبسط يركز على الوظائف الأساسية
"""

import csv
import os
import time
import logging
import urllib.request
import urllib.parse
import json
from datetime import datetime

# إعداد نظام السجلات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleLangSenseBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.user_states = {}
        self.init_files()
        logger.info("تم إنشاء البوت المبسط بنجاح")
    
    def init_files(self):
        """إنشاء الملفات الأساسية"""
        files_to_create = [
            ('users.csv', ['user_id', 'name', 'phone', 'customer_id', 'language', 'registration_date', 'is_banned', 'ban_reason']),
            ('transactions.csv', ['id', 'user_id', 'customer_id', 'type', 'company_name', 'payment_method', 'wallet_number', 'amount', 'status', 'date', 'withdrawal_address', 'confirmation_code']),
            ('companies.csv', ['id', 'name', 'type', 'details', 'is_active']),
            ('payment_methods.csv', ['id', 'company_id', 'method_name', 'method_type', 'account_data', 'additional_info', 'status', 'created_date'])
        ]
        
        for filename, headers in files_to_create:
            if not os.path.exists(filename):
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                logger.info(f"تم إنشاء الملف: {filename}")
    
    def send_message(self, chat_id, text, keyboard=None):
        """إرسال رسالة"""
        try:
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'Markdown'
            }
            
            if keyboard:
                data['reply_markup'] = json.dumps(keyboard)
            
            encoded_data = urllib.parse.urlencode(data).encode('utf-8')
            request = urllib.request.Request(f"{self.base_url}/sendMessage", data=encoded_data)
            response = urllib.request.urlopen(request)
            return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"خطأ في إرسال الرسالة: {e}")
            return None
    
    def is_admin(self, user_id):
        """فحص الأدمن"""
        admin_ids = os.getenv('ADMIN_USER_IDS', '').split(',')
        return str(user_id) in admin_ids
    
    def main_keyboard(self, language='ar'):
        """الكيبورد الرئيسي"""
        return {
            'keyboard': [
                [{'text': '💰 طلب إيداع'}, {'text': '💸 طلب سحب'}],
                [{'text': '📋 طلباتي'}, {'text': '👤 حسابي'}],
                [{'text': '📨 شكوى'}, {'text': '🆘 دعم'}]
            ],
            'resize_keyboard': True
        }
    
    def admin_keyboard(self):
        """كيبورد الأدمن"""
        return {
            'keyboard': [
                [{'text': '📋 الطلبات المعلقة'}, {'text': '✅ طلبات مُوافقة'}],
                [{'text': '💳 وسائل الدفع'}, {'text': '🏢 الشركات'}],
                [{'text': '👥 المستخدمين'}, {'text': '📊 الإحصائيات'}],
                [{'text': '🏠 القائمة الرئيسية'}]
            ],
            'resize_keyboard': True
        }
    
    def find_user(self, user_id):
        """العثور على مستخدم"""
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['user_id'] == str(user_id):
                        return row
        except:
            pass
        return None
    
    def get_companies(self):
        """الحصول على الشركات"""
        companies = []
        try:
            with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('is_active') == 'yes':
                        companies.append(row)
        except:
            pass
        return companies
    
    def get_payment_methods_by_company(self, company_id):
        """الحصول على وسائل الدفع للشركة"""
        methods = []
        try:
            with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['company_id'] == str(company_id) and row.get('status') == 'active':
                        methods.append(row)
        except:
            pass
        return methods
    
    def handle_start(self, message):
        """معالجة بدء المحادثة"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        
        user = self.find_user(user_id)
        
        if user:
            if user.get('is_banned') == 'yes':
                ban_reason = user.get('ban_reason', 'غير محدد')
                self.send_message(chat_id, f"❌ تم حظر حسابك\nالسبب: {ban_reason}")
                return
            
            welcome_text = f"مرحباً بعودتك {user['name']}! 👋\n🆔 رقم العميل: {user['customer_id']}"
            self.send_message(chat_id, welcome_text, self.main_keyboard())
        else:
            welcome_text = """مرحباً بك في نظام LangSense المالي! 👋

🔹 خدمات الإيداع والسحب
🔹 دعم فني متخصص
🔹 أمان وموثوقية عالية

يرجى إرسال اسمك الكامل للتسجيل:"""
            self.send_message(chat_id, welcome_text)
            self.user_states[user_id] = 'registering_name'
    
    def handle_registration(self, message):
        """معالجة التسجيل"""
        user_id = message['from']['id']
        state = self.user_states.get(user_id)
        
        if state == 'registering_name':
            name = message['text'].strip()
            if len(name) < 2:
                self.send_message(message['chat']['id'], "❌ اسم قصير جداً. يرجى إدخال اسم صحيح:")
                return
            
            self.user_states[user_id] = f'registering_phone_{name}'
            
            # كيبورد مشاركة جهة الاتصال
            contact_keyboard = {
                'keyboard': [
                    [{'text': '📱 مشاركة رقم الهاتف', 'request_contact': True}],
                    [{'text': '✍️ كتابة الرقم يدوياً'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            
            phone_text = """ممتاز! الآن أرسل رقم هاتفك:

📱 يمكنك مشاركة رقمك مباشرة بالضغط على "📱 مشاركة رقم الهاتف"
✍️ أو اكتب الرقم يدوياً مع رمز البلد (مثال: +966501234567)"""
            
            self.send_message(message['chat']['id'], phone_text, contact_keyboard)
            
        elif state.startswith('registering_phone_'):
            name = state.replace('registering_phone_', '')
            
            # التحقق من نوع الرسالة
            if 'contact' in message:
                # مشاركة جهة الاتصال
                phone = message['contact']['phone_number']
                if not phone.startswith('+'):
                    phone = '+' + phone
            elif 'text' in message:
                text = message['text'].strip()
                
                if text == '✍️ كتابة الرقم يدوياً':
                    manual_text = """✍️ اكتب رقم هاتفك مع رمز البلد:

مثال: +966501234567
مثال: +201234567890"""
                    self.send_message(message['chat']['id'], manual_text)
                    return
                
                phone = text
                if len(phone) < 10:
                    self.send_message(message['chat']['id'], "❌ رقم هاتف غير صحيح. يرجى إدخال رقم صحيح مع رمز البلد:")
                    return
            else:
                self.send_message(message['chat']['id'], "❌ يرجى مشاركة جهة الاتصال أو كتابة الرقم:")
                return
            
            # إنشاء رقم عميل تلقائي
            customer_id = f"C{str(int(datetime.now().timestamp()))[-6:]}"
            
            # حفظ المستخدم
            with open('users.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([user_id, name, phone, customer_id, 'ar', 
                               datetime.now().strftime('%Y-%m-%d'), 'no', ''])
            
            welcome_text = f"""✅ تم التسجيل بنجاح!

👤 الاسم: {name}
📱 الهاتف: {phone}
🆔 رقم العميل: {customer_id}
📅 تاريخ التسجيل: {datetime.now().strftime('%Y-%m-%d')}

يمكنك الآن استخدام جميع الخدمات المالية:"""
            
            self.send_message(message['chat']['id'], welcome_text, self.main_keyboard())
            del self.user_states[user_id]
    
    def handle_deposit(self, message):
        """معالجة طلب الإيداع"""
        user_id = message['from']['id']
        companies = self.get_companies()
        
        if not companies:
            self.send_message(message['chat']['id'], "❌ لا توجد شركات متاحة حالياً")
            return
        
        companies_text = "💰 اختر الشركة للإيداع:\n\n"
        keyboard_buttons = []
        
        for company in companies:
            companies_text += f"🏢 {company['name']} - {company['type']}\n"
            keyboard_buttons.append([{'text': company['name']}])
        
        keyboard_buttons.append([{'text': '🔙 العودة'}])
        
        keyboard = {
            'keyboard': keyboard_buttons,
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        
        self.send_message(message['chat']['id'], companies_text, keyboard)
        self.user_states[user_id] = 'deposit_company_selection'
    
    def handle_withdrawal(self, message):
        """معالجة طلب السحب"""
        user_id = message['from']['id']
        companies = self.get_companies()
        
        if not companies:
            self.send_message(message['chat']['id'], "❌ لا توجد شركات متاحة حالياً")
            return
        
        companies_text = "💸 اختر الشركة للسحب:\n\n"
        keyboard_buttons = []
        
        for company in companies:
            companies_text += f"🏢 {company['name']} - {company['type']}\n"
            keyboard_buttons.append([{'text': company['name']}])
        
        keyboard_buttons.append([{'text': '🔙 العودة'}])
        
        keyboard = {
            'keyboard': keyboard_buttons,
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        
        self.send_message(message['chat']['id'], companies_text, keyboard)
        self.user_states[user_id] = 'withdraw_company_selection'
    
    def handle_company_selection(self, message, transaction_type):
        """معالجة اختيار الشركة"""
        user_id = message['from']['id']
        company_name = message['text'].strip()
        
        if company_name == '🔙 العودة':
            del self.user_states[user_id]
            self.send_message(message['chat']['id'], "تم الإلغاء", self.main_keyboard())
            return
        
        # البحث عن الشركة
        companies = self.get_companies()
        selected_company = None
        
        for company in companies:
            if company['name'] == company_name:
                selected_company = company
                break
        
        if not selected_company:
            self.send_message(message['chat']['id'], "❌ شركة غير صحيحة. يرجى الاختيار من القائمة")
            return
        
        # الحصول على وسائل الدفع للشركة
        payment_methods = self.get_payment_methods_by_company(selected_company['id'])
        
        if not payment_methods:
            self.send_message(message['chat']['id'], 
                            f"❌ لا توجد وسائل دفع متاحة لشركة {company_name} حالياً")
            return
        
        # عرض وسائل الدفع
        methods_text = f"💳 وسائل الدفع المتاحة لشركة {company_name}:\n\n"
        keyboard_buttons = []
        
        for method in payment_methods:
            method_info = f"📋 {method['method_name']} ({method['method_type']})\n"
            method_info += f"💰 الحساب: `{method['account_data']}`\n"
            if method.get('additional_info'):
                method_info += f"💡 {method['additional_info']}\n"
            method_info += "━━━━━━━━━━━━━━━━━━━━\n"
            
            methods_text += method_info
            keyboard_buttons.append([{'text': method['method_name']}])
        
        methods_text += "\n📋 انسخ رقم الحساب المطلوب ثم اختر وسيلة الدفع:"
        
        keyboard_buttons.append([{'text': '🔙 العودة لاختيار الشركة'}])
        
        keyboard = {
            'keyboard': keyboard_buttons,
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        
        self.send_message(message['chat']['id'], methods_text, keyboard)
        self.user_states[user_id] = {
            'step': 'method_selection',
            'transaction_type': transaction_type,
            'company': selected_company,
            'methods': payment_methods
        }
    
    def handle_method_selection(self, message):
        """معالجة اختيار وسيلة الدفع"""
        user_id = message['from']['id']
        method_name = message['text'].strip()
        state = self.user_states[user_id]
        
        if method_name == '🔙 العودة لاختيار الشركة':
            transaction_type = state['transaction_type']
            if transaction_type == 'deposit':
                self.handle_deposit(message)
            else:
                self.handle_withdrawal(message)
            return
        
        # البحث عن وسيلة الدفع المختارة
        selected_method = None
        for method in state['methods']:
            if method['method_name'] == method_name:
                selected_method = method
                break
        
        if not selected_method:
            self.send_message(message['chat']['id'], "❌ اختيار غير صحيح. يرجى الاختيار من القائمة")
            return
        
        # طلب رقم المحفظة
        wallet_text = f"""✅ تم اختيار: {selected_method['method_name']}

📝 الآن أدخل رقم محفظتك/حسابك الشخصي:"""
        
        self.send_message(message['chat']['id'], wallet_text)
        
        # تحديث الحالة
        company = state['company']
        transaction_type = state['transaction_type']
        self.user_states[user_id] = f'{transaction_type}_wallet_{company["id"]}_{company["name"]}_{selected_method["id"]}'
    
    def process_transaction_flow(self, message, transaction_type):
        """معالجة تدفق المعاملة"""
        user_id = message['from']['id']
        state = self.user_states[user_id]
        text = message['text'].strip()
        
        if text == '/cancel':
            del self.user_states[user_id]
            self.send_message(message['chat']['id'], "تم إلغاء العملية", self.main_keyboard())
            return
        
        # استخراج معلومات الحالة
        parts = state.split('_')
        if len(parts) >= 4:
            company_id = parts[2]
            company_name = parts[3]
            method_id = parts[4] if len(parts) > 4 else ''
            
            if f'{transaction_type}_wallet_' in state:
                # حفظ رقم المحفظة وطلب المبلغ
                wallet_number = text
                amount_text = f"""💰 تم حفظ رقم المحفظة: {wallet_number}

📝 الآن أدخل المبلغ:

⬅️ /cancel للإلغاء"""
                
                self.send_message(message['chat']['id'], amount_text)
                self.user_states[user_id] = f'{transaction_type}_amount_{company_id}_{company_name}_{method_id}_{wallet_number}'
                
            elif f'{transaction_type}_amount_' in state:
                # حفظ المبلغ وإنهاء المعاملة
                try:
                    amount = float(text)
                    if amount <= 0:
                        raise ValueError()
                except:
                    self.send_message(message['chat']['id'], "❌ مبلغ غير صحيح. يرجى إدخال رقم صحيح:")
                    return
                
                # استخراج رقم المحفظة
                wallet_number = parts[5] if len(parts) > 5 else ''
                
                # إنشاء معاملة جديدة
                transaction_id = f"{transaction_type.upper()}{str(int(datetime.now().timestamp()))[-6:]}"
                user = self.find_user(user_id)
                
                with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        transaction_id, user_id, user.get('customer_id', ''), 
                        transaction_type, company_name, method_id,
                        wallet_number, amount, 'pending', 
                        datetime.now().strftime('%Y-%m-%d %H:%M'), '', ''
                    ])
                
                # رسالة تأكيد للعميل
                confirmation_text = f"""✅ تم إرسال طلب {'الإيداع' if transaction_type == 'deposit' else 'السحب'} بنجاح!

🆔 رقم المعاملة: {transaction_id}
🏢 الشركة: {company_name}
💰 المبلغ: {amount}
📱 رقم المحفظة: {wallet_number}
📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}

⏳ حالة الطلب: قيد المراجعة
سيتم إشعارك عند الموافقة أو الرفض"""
                
                self.send_message(message['chat']['id'], confirmation_text, self.main_keyboard())
                
                # إشعار الأدمن
                admin_ids = os.getenv('ADMIN_USER_IDS', '').split(',')
                admin_msg = f"""🆕 طلب {'إيداع' if transaction_type == 'deposit' else 'سحب'} جديد

🆔 رقم المعاملة: {transaction_id}
👤 العميل: {user.get('name', 'غير محدد')} ({user.get('customer_id', '')})
🏢 الشركة: {company_name}
💰 المبلغ: {amount}
📱 رقم المحفظة: {wallet_number}

للموافقة: موافقة {transaction_id}
للرفض: رفض {transaction_id} السبب"""
                
                for admin_id in admin_ids:
                    if admin_id.strip():
                        self.send_message(int(admin_id), admin_msg)
                
                del self.user_states[user_id]
    
    def handle_admin_commands(self, message):
        """معالجة أوامر الأدمن"""
        text = message['text'].strip()
        chat_id = message['chat']['id']
        
        if text.startswith('موافقة '):
            transaction_id = text.replace('موافقة ', '').strip()
            self.approve_transaction(chat_id, transaction_id)
            
        elif text.startswith('رفض '):
            parts = text.split(' ', 2)
            if len(parts) >= 3:
                transaction_id = parts[1]
                reason = parts[2]
                self.reject_transaction(chat_id, transaction_id, reason)
            else:
                self.send_message(chat_id, "الصيغة: رفض رقم_المعاملة السبب")
    
    def approve_transaction(self, chat_id, transaction_id):
        """الموافقة على معاملة"""
        # تحديث المعاملة
        transactions = []
        updated = False
        approved_transaction = None
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == transaction_id and row['status'] == 'pending':
                        row['status'] = 'approved'
                        updated = True
                        approved_transaction = row
                    transactions.append(row)
            
            if updated:
                with open('transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    fieldnames = ['id', 'user_id', 'customer_id', 'type', 'company_name', 'payment_method', 'wallet_number', 'amount', 'status', 'date', 'withdrawal_address', 'confirmation_code']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(transactions)
                
                # إشعار الأدمن
                self.send_message(chat_id, f"✅ تم الموافقة على المعاملة {transaction_id}")
                
                # إشعار العميل
                customer_msg = f"""✅ تم الموافقة على طلبك!

🆔 رقم المعاملة: {transaction_id}
💰 المبلغ: {approved_transaction['amount']}
📅 تاريخ الموافقة: {datetime.now().strftime('%Y-%m-%d %H:%M')}

شكراً لاستخدامك خدماتنا"""
                
                self.send_message(int(approved_transaction['user_id']), customer_msg)
            else:
                self.send_message(chat_id, f"❌ لم يتم العثور على معاملة معلقة برقم {transaction_id}")
        except Exception as e:
            self.send_message(chat_id, f"❌ خطأ في الموافقة: {e}")
    
    def reject_transaction(self, chat_id, transaction_id, reason):
        """رفض معاملة"""
        # تحديث المعاملة
        transactions = []
        updated = False
        rejected_transaction = None
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == transaction_id and row['status'] == 'pending':
                        row['status'] = 'rejected'
                        updated = True
                        rejected_transaction = row
                    transactions.append(row)
            
            if updated:
                with open('transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    fieldnames = ['id', 'user_id', 'customer_id', 'type', 'company_name', 'payment_method', 'wallet_number', 'amount', 'status', 'date', 'withdrawal_address', 'confirmation_code']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(transactions)
                
                # إشعار الأدمن
                self.send_message(chat_id, f"❌ تم رفض المعاملة {transaction_id}")
                
                # إشعار العميل
                customer_msg = f"""❌ تم رفض طلبك

🆔 رقم المعاملة: {transaction_id}
💰 المبلغ: {rejected_transaction['amount']}
🔍 سبب الرفض: {reason}
📅 تاريخ الرفض: {datetime.now().strftime('%Y-%m-%d %H:%M')}

يمكنك تقديم طلب جديد بعد تصحيح المشكلة"""
                
                self.send_message(int(rejected_transaction['user_id']), customer_msg)
            else:
                self.send_message(chat_id, f"❌ لم يتم العثور على معاملة معلقة برقم {transaction_id}")
        except Exception as e:
            self.send_message(chat_id, f"❌ خطأ في الرفض: {e}")
    
    def handle_message(self, message):
        """معالجة الرسائل الواردة"""
        try:
            # قبول الرسائل النصية أو جهات الاتصال
            if 'text' not in message and 'contact' not in message:
                return
            
            user_id = message['from']['id']
            chat_id = message['chat']['id']
            text = message.get('text', '')
            
            # معالجة /start
            if text == '/start':
                self.handle_start(message)
                return
            
            # معالجة التسجيل
            if user_id in self.user_states:
                state = self.user_states[user_id]
                if isinstance(state, str):
                    if state.startswith('registering'):
                        self.handle_registration(message)
                        return
                    elif 'deposit' in state:
                        self.process_transaction_flow(message, 'deposit')
                        return
                    elif 'withdraw' in state:
                        self.process_transaction_flow(message, 'withdrawal')
                        return
                    elif state == 'deposit_company_selection':
                        self.handle_company_selection(message, 'deposit')
                        return
                    elif state == 'withdraw_company_selection':
                        self.handle_company_selection(message, 'withdrawal')
                        return
                elif isinstance(state, dict):
                    if state.get('step') == 'method_selection':
                        self.handle_method_selection(message)
                        return
            
            # فحص المستخدم المسجل
            user = self.find_user(user_id)
            if not user:
                self.handle_start(message)
                return
            
            # فحص الحظر
            if user.get('is_banned') == 'yes':
                ban_reason = user.get('ban_reason', 'غير محدد')
                self.send_message(chat_id, f"❌ تم حظر حسابك\nالسبب: {ban_reason}")
                return
            
            # معالجة أوامر الأدمن
            if self.is_admin(user_id):
                if text == '/admin':
                    self.send_message(chat_id, "مرحباً بك في لوحة الإدارة", self.admin_keyboard())
                    return
                
                # أوامر الموافقة والرفض
                if text.startswith(('موافقة ', 'رفض ')):
                    self.handle_admin_commands(message)
                    return
            
            # معالجة القوائم الرئيسية
            if text == '💰 طلب إيداع':
                self.handle_deposit(message)
            elif text == '💸 طلب سحب':
                self.handle_withdrawal(message)
            elif text == '🏠 القائمة الرئيسية':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(chat_id, "تم العودة للقائمة الرئيسية", self.main_keyboard())
            else:
                # رسالة افتراضية
                self.send_message(chat_id, "مرحباً! استخدم الأزرار للتنقل في النظام", self.main_keyboard())
        
        except Exception as e:
            logger.error(f"خطأ في معالجة الرسالة: {e}")
    
    def get_updates(self, offset=None):
        """جلب التحديثات من تليجرام"""
        try:
            url = f"{self.base_url}/getUpdates"
            if offset:
                url += f"?offset={offset}"
            
            request = urllib.request.Request(url)
            response = urllib.request.urlopen(request)
            return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"خطأ في جلب التحديثات: {e}")
            return None
    
    def run(self):
        """تشغيل البوت"""
        logger.info("✅ البوت المبسط يعمل الآن")
        offset = None
        
        while True:
            try:
                updates = self.get_updates(offset)
                if updates and updates.get('ok'):
                    for update in updates['result']:
                        if 'message' in update:
                            self.handle_message(update['message'])
                        offset = update['update_id'] + 1
                
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("تم إيقاف البوت")
                break
            except Exception as e:
                logger.error(f"خطأ في التشغيل: {e}")
                time.sleep(5)

if __name__ == "__main__":
    # جلب التوكن
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        logger.error("BOT_TOKEN غير موجود في متغيرات البيئة")
        exit(1)
    
    # تشغيل البوت
    bot = SimpleLangSenseBot(bot_token)
    bot.run()