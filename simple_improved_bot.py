#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import csv
import urllib.request
import urllib.parse
import logging
from datetime import datetime

# إعداد التسجيل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleLangSenseBot:
    def __init__(self, token):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self.user_states = {}
        self.init_files()
        self.admin_ids = self.get_admin_ids()
        
    def init_files(self):
        """إنشاء ملفات النظام"""
        # ملف المستخدمين
        if not os.path.exists('users.csv'):
            with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['telegram_id', 'name', 'phone', 'customer_id', 'language', 'date', 'is_banned'])
        
        # ملف المعاملات
        if not os.path.exists('transactions.csv'):
            with open('transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'customer_id', 'name', 'type', 'company', 'wallet_number', 'amount', 'exchange_address', 'status', 'date', 'admin_note'])
        
        # ملف الشركات
        if not os.path.exists('companies.csv'):
            with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'type', 'details'])
                # شركات افتراضية
                companies = [
                    ['1', 'STC Pay', 'both', 'محفظة إلكترونية'],
                    ['2', 'البنك الأهلي', 'both', 'حساب بنكي'],
                    ['3', 'فودافون كاش', 'both', 'محفظة إلكترونية'],
                    ['4', 'بنك الراجحي', 'both', 'حساب بنكي']
                ]
                for company in companies:
                    writer.writerow(company)
        
        # ملف عناوين الصرافة
        if not os.path.exists('exchange_addresses.csv'):
            with open('exchange_addresses.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'address', 'is_active'])
                writer.writerow(['1', 'شارع الملك فهد، الرياض، مقابل مول الرياض', 'yes'])
        
        logger.info("تم إنشاء جميع ملفات النظام")
        
    def api_call(self, method, data=None):
        """استدعاء API"""
        url = f"{self.api_url}/{method}"
        try:
            if data:
                json_data = json.dumps(data).encode('utf-8')
                req = urllib.request.Request(url, data=json_data)
                req.add_header('Content-Type', 'application/json')
            else:
                req = urllib.request.Request(url)
            
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"خطأ في API: {e}")
            return None
    
    def send_message(self, chat_id, text, keyboard=None):
        """إرسال رسالة"""
        data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
        if keyboard:
            data['reply_markup'] = keyboard
        return self.api_call('sendMessage', data)
    
    def get_updates(self):
        """جلب التحديثات"""
        url = f"{self.api_url}/getUpdates?offset={self.offset + 1}&timeout=10"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"خطأ في جلب التحديثات: {e}")
            return None
    
    def get_admin_ids(self):
        """جلب معرفات الأدمن"""
        admin_ids = os.getenv('ADMIN_USER_IDS', '').split(',')
        return [admin_id.strip() for admin_id in admin_ids if admin_id.strip()]
    
    def is_admin(self, telegram_id):
        """فحص صلاحية الأدمن"""
        return str(telegram_id) in self.admin_ids
    
    def notify_admins(self, message):
        """إشعار جميع الأدمن"""
        for admin_id in self.admin_ids:
            self.send_message(admin_id, message, self.admin_keyboard())
    
    def find_user(self, telegram_id):
        """البحث عن مستخدم"""
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['telegram_id'] == str(telegram_id):
                        return row
        except:
            pass
        return None
    
    def get_companies(self, service_type=None):
        """جلب الشركات"""
        companies = []
        try:
            with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if service_type is None or row['type'] in [service_type, 'both']:
                        companies.append(row)
        except:
            pass
        return companies
    
    def get_exchange_address(self):
        """جلب عنوان الصرافة النشط"""
        try:
            with open('exchange_addresses.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['is_active'] == 'yes':
                        return row['address']
        except:
            pass
        return "العنوان غير متوفر"
    
    def main_keyboard(self, lang='ar'):
        """القائمة الرئيسية"""
        return {
            'keyboard': [
                [{'text': '💰 إيداع'}, {'text': '💸 سحب'}],
                [{'text': '📋 طلباتي'}, {'text': '🆘 دعم'}]
            ],
            'resize_keyboard': True
        }
    
    def admin_keyboard(self):
        """لوحة الأدمن"""
        return {
            'keyboard': [
                [{'text': '📋 طلبات معلقة'}, {'text': '✅ موافقة طلب'}],
                [{'text': '❌ رفض طلب'}, {'text': '👥 المستخدمين'}],
                [{'text': '🏢 إدارة الشركات'}, {'text': '📍 تعديل العنوان'}],
                [{'text': '📊 إحصائيات'}, {'text': '🏠 القائمة الرئيسية'}]
            ],
            'resize_keyboard': True
        }
    
    def companies_keyboard(self, service_type):
        """لوحة اختيار الشركات"""
        companies = self.get_companies(service_type)
        keyboard = []
        for company in companies:
            keyboard.append([{'text': company['name']}])
        keyboard.append([{'text': '🔙 رجوع'}])
        return {'keyboard': keyboard, 'resize_keyboard': True}
    
    def handle_start(self, message):
        """معالج بداية المحادثة"""
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        
        # فحص إذا كان المستخدم موجود
        user = self.find_user(user_id)
        if user:
            welcome_text = f"مرحباً بعودتك {user['name']}! 👋"
            self.send_message(chat_id, welcome_text, self.main_keyboard())
        else:
            welcome_text = """مرحباً بك في نظام الخدمات المالية! 👋

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
                self.send_message(message['chat']['id'], "اسم قصير جداً. يرجى إدخال اسم صحيح:")
                return
            
            self.user_states[user_id] = f'registering_phone_{name}'
            self.send_message(message['chat']['id'], "ممتاز! الآن أرسل رقم هاتفك:")
            
        elif state.startswith('registering_phone_'):
            name = state.replace('registering_phone_', '')
            phone = message['text'].strip()
            
            if len(phone) < 10:
                self.send_message(message['chat']['id'], "رقم هاتف غير صحيح. يرجى إدخال رقم صحيح:")
                return
            
            # إنشاء رقم عميل
            customer_id = f"C{str(int(datetime.now().timestamp()))[-6:]}"
            
            # حفظ المستخدم
            with open('users.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([user_id, name, phone, customer_id, 'ar', datetime.now().strftime('%Y-%m-%d'), 'no'])
            
            welcome_text = f"""✅ تم التسجيل بنجاح!

👤 الاسم: {name}
📱 الهاتف: {phone}
🆔 رقم العميل: {customer_id}

يمكنك الآن استخدام الخدمات:"""
            
            self.send_message(message['chat']['id'], welcome_text, self.main_keyboard())
            del self.user_states[user_id]
    
    def start_deposit(self, message):
        """بدء عملية الإيداع"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        
        self.send_message(message['chat']['id'], "اختر الشركة للإيداع:", self.companies_keyboard('deposit'))
        self.user_states[message['from']['id']] = 'selecting_deposit_company'
    
    def start_withdrawal(self, message):
        """بدء عملية السحب"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        
        self.send_message(message['chat']['id'], "اختر الشركة للسحب:", self.companies_keyboard('withdraw'))
        self.user_states[message['from']['id']] = 'selecting_withdraw_company'
    
    def process_deposit_flow(self, message):
        """معالجة تدفق الإيداع"""
        user_id = message['from']['id']
        state = self.user_states.get(user_id, '')
        text = message['text']
        
        if state == 'selecting_deposit_company':
            # حفظ الشركة المختارة
            companies = self.get_companies('deposit')
            selected_company = None
            for company in companies:
                if company['name'] == text:
                    selected_company = company
                    break
            
            if not selected_company:
                self.send_message(message['chat']['id'], "اختيار غير صحيح. اختر من القائمة:")
                return
            
            self.user_states[user_id] = f'deposit_wallet_{selected_company["name"]}'
            self.send_message(message['chat']['id'], f"أدخل رقم محفظتك/حسابك في {selected_company['name']}:")
            
        elif state.startswith('deposit_wallet_'):
            company_name = state.replace('deposit_wallet_', '')
            wallet_number = text.strip()
            
            if len(wallet_number) < 5:
                self.send_message(message['chat']['id'], "رقم المحفظة قصير. أدخل رقم صحيح:")
                return
            
            self.user_states[user_id] = f'deposit_amount_{company_name}_{wallet_number}'
            self.send_message(message['chat']['id'], "أدخل المبلغ المطلوب إيداعه:")
            
        elif state.startswith('deposit_amount_'):
            parts = state.split('_', 2)
            company_name = parts[2].split('_')[0]
            wallet_number = '_'.join(parts[2].split('_')[1:])
            
            try:
                amount = float(text.strip())
                if amount < 50:
                    self.send_message(message['chat']['id'], "أقل مبلغ للإيداع 50 ريال:")
                    return
            except:
                self.send_message(message['chat']['id'], "مبلغ غير صحيح. أدخل رقم:")
                return
            
            # إنشاء المعاملة
            user = self.find_user(user_id)
            trans_id = f"DEP{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([trans_id, user['customer_id'], user['name'], 'deposit', 
                               company_name, wallet_number, amount, '', 'pending', 
                               datetime.now().strftime('%Y-%m-%d %H:%M'), ''])
            
            # رسالة تأكيد للعميل
            confirmation = f"""✅ تم إرسال طلب الإيداع

🆔 رقم المعاملة: {trans_id}
🏢 الشركة: {company_name}
💳 رقم المحفظة: {wallet_number}
💰 المبلغ: {amount} ريال

سيتم مراجعة طلبك وإشعارك بالنتيجة."""
            
            self.send_message(message['chat']['id'], confirmation, self.main_keyboard())
            
            # إشعار الأدمن
            admin_msg = f"""🔔 طلب إيداع جديد

🆔 {trans_id}
👤 {user['name']} ({user['customer_id']})
🏢 {company_name}
💳 {wallet_number}
💰 {amount} ريال

استخدم: موافقة {trans_id} أو رفض {trans_id} سبب"""
            
            self.notify_admins(admin_msg)
            del self.user_states[user_id]
    
    def process_withdrawal_flow(self, message):
        """معالجة تدفق السحب"""
        user_id = message['from']['id']
        state = self.user_states.get(user_id, '')
        text = message['text']
        
        if state == 'selecting_withdraw_company':
            # حفظ الشركة المختارة
            companies = self.get_companies('withdraw')
            selected_company = None
            for company in companies:
                if company['name'] == text:
                    selected_company = company
                    break
            
            if not selected_company:
                self.send_message(message['chat']['id'], "اختيار غير صحيح. اختر من القائمة:")
                return
            
            self.user_states[user_id] = f'withdraw_wallet_{selected_company["name"]}'
            self.send_message(message['chat']['id'], f"أدخل رقم محفظتك/حسابك في {selected_company['name']}:")
            
        elif state.startswith('withdraw_wallet_'):
            company_name = state.replace('withdraw_wallet_', '')
            wallet_number = text.strip()
            
            if len(wallet_number) < 5:
                self.send_message(message['chat']['id'], "رقم المحفظة قصير. أدخل رقم صحيح:")
                return
            
            self.user_states[user_id] = f'withdraw_amount_{company_name}_{wallet_number}'
            self.send_message(message['chat']['id'], "أدخل المبلغ المطلوب سحبه:")
            
        elif state.startswith('withdraw_amount_'):
            parts = state.split('_', 2)
            company_name = parts[2].split('_')[0]
            wallet_number = '_'.join(parts[2].split('_')[1:])
            
            try:
                amount = float(text.strip())
                if amount < 100:
                    self.send_message(message['chat']['id'], "أقل مبلغ للسحب 100 ريال:")
                    return
            except:
                self.send_message(message['chat']['id'], "مبلغ غير صحيح. أدخل رقم:")
                return
            
            # عرض عنوان الصرافة
            exchange_address = self.get_exchange_address()
            self.user_states[user_id] = f'withdraw_confirm_{company_name}_{wallet_number}_{amount}'
            
            confirm_msg = f"""📍 عنوان مكتب الصرافة:
{exchange_address}

تأكيد طلب السحب:
🏢 الشركة: {company_name}
💳 رقم المحفظة: {wallet_number}
💰 المبلغ: {amount} ريال
📍 العنوان: {exchange_address}

أرسل "تأكيد" لإتمام الطلب أو "إلغاء" للعودة"""
            
            self.send_message(message['chat']['id'], confirm_msg)
            
        elif state.startswith('withdraw_confirm_'):
            if text.lower() == 'تأكيد':
                parts = state.split('_', 2)
                company_name = parts[2].split('_')[0]
                wallet_number = parts[2].split('_')[1]
                amount = parts[2].split('_')[2]
                
                # إنشاء المعاملة
                user = self.find_user(user_id)
                trans_id = f"WTH{datetime.now().strftime('%Y%m%d%H%M%S')}"
                exchange_address = self.get_exchange_address()
                
                with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([trans_id, user['customer_id'], user['name'], 'withdraw', 
                                   company_name, wallet_number, amount, exchange_address, 'pending', 
                                   datetime.now().strftime('%Y-%m-%d %H:%M'), ''])
                
                # رسالة تأكيد للعميل
                confirmation = f"""✅ تم إرسال طلب السحب

🆔 رقم المعاملة: {trans_id}
🏢 الشركة: {company_name}
💳 رقم المحفظة: {wallet_number}
💰 المبلغ: {amount} ريال
📍 العنوان: {exchange_address}

سيتم مراجعة طلبك وإشعارك بالنتيجة."""
                
                self.send_message(message['chat']['id'], confirmation, self.main_keyboard())
                
                # إشعار الأدمن
                admin_msg = f"""🔔 طلب سحب جديد

🆔 {trans_id}
👤 {user['name']} ({user['customer_id']})
🏢 {company_name}
💳 {wallet_number}
💰 {amount} ريال
📍 {exchange_address}

استخدم: موافقة {trans_id} أو رفض {trans_id} سبب"""
                
                self.notify_admins(admin_msg)
                del self.user_states[user_id]
            else:
                self.send_message(message['chat']['id'], "تم إلغاء العملية", self.main_keyboard())
                del self.user_states[user_id]
    
    def show_user_requests(self, message):
        """عرض طلبات المستخدم"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        
        requests_text = "📋 طلباتك:\n\n"
        found_requests = False
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['customer_id'] == user['customer_id']:
                        found_requests = True
                        status_emoji = "⏳" if row['status'] == 'pending' else "✅" if row['status'] == 'approved' else "❌"
                        requests_text += f"{status_emoji} {row['id']}\n"
                        requests_text += f"🏢 {row['company']}\n"
                        requests_text += f"💰 {row['amount']} ريال\n"
                        requests_text += f"📅 {row['date']}\n\n"
        except:
            pass
        
        if not found_requests:
            requests_text += "لا توجد طلبات"
        
        self.send_message(message['chat']['id'], requests_text, self.main_keyboard())
    
    def handle_admin_commands(self, message):
        """معالجة أوامر الأدمن"""
        text = message['text'].lower()
        
        if text == 'طلبات معلقة':
            self.show_pending_requests(message)
        elif text.startswith('موافقة '):
            self.approve_request(message, text.replace('موافقة ', ''))
        elif text.startswith('رفض '):
            parts = text.replace('رفض ', '').split(' ', 1)
            trans_id = parts[0]
            reason = parts[1] if len(parts) > 1 else 'غير محدد'
            self.reject_request(message, trans_id, reason)
        elif text == 'المستخدمين':
            self.show_all_users(message)
        elif text == 'إدارة الشركات':
            self.show_companies_admin(message)
        elif text == 'تعديل العنوان':
            self.show_address_admin(message)
        elif text == 'إحصائيات':
            self.show_statistics(message)
        elif text.startswith('اضف_شركة '):
            self.add_company_simple(message, text)
        elif text.startswith('حذف_شركة '):
            self.delete_company_simple(message, text)
        elif text.startswith('عنوان_جديد '):
            self.update_address_simple(message, text)
    
    def show_pending_requests(self, message):
        """عرض الطلبات المعلقة"""
        pending_text = "📋 الطلبات المعلقة:\n\n"
        found_pending = False
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['status'] == 'pending':
                        found_pending = True
                        pending_text += f"🆔 {row['id']}\n"
                        pending_text += f"👤 {row['name']} ({row['customer_id']})\n"
                        pending_text += f"📋 {row['type']} - {row['company']}\n"
                        pending_text += f"💰 {row['amount']} ريال\n"
                        pending_text += f"💳 {row['wallet_number']}\n"
                        if row['exchange_address']:
                            pending_text += f"📍 {row['exchange_address']}\n"
                        pending_text += f"📅 {row['date']}\n\n"
        except:
            pass
        
        if not found_pending:
            pending_text += "لا توجد طلبات معلقة"
        else:
            pending_text += "\nاستخدم: موافقة رقم_المعاملة أو رفض رقم_المعاملة السبب"
        
        self.send_message(message['chat']['id'], pending_text, self.admin_keyboard())
    
    def approve_request(self, message, trans_id):
        """موافقة على طلب"""
        success = self.update_transaction_status(trans_id, 'approved')
        
        if success:
            # إشعار العميل
            transaction = self.get_transaction(trans_id)
            if transaction:
                customer = self.get_customer_by_id(transaction['customer_id'])
                if customer:
                    customer_msg = f"""✅ تمت الموافقة على طلبك

🆔 {trans_id}
💰 {transaction['amount']} ريال
📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
                    
                    self.send_message(customer['telegram_id'], customer_msg, self.main_keyboard())
            
            self.send_message(message['chat']['id'], f"✅ تمت الموافقة على {trans_id}", self.admin_keyboard())
        else:
            self.send_message(message['chat']['id'], f"❌ فشل في الموافقة على {trans_id}", self.admin_keyboard())
    
    def reject_request(self, message, trans_id, reason):
        """رفض طلب"""
        success = self.update_transaction_status(trans_id, 'rejected', reason)
        
        if success:
            # إشعار العميل
            transaction = self.get_transaction(trans_id)
            if transaction:
                customer = self.get_customer_by_id(transaction['customer_id'])
                if customer:
                    customer_msg = f"""❌ تم رفض طلبك

🆔 {trans_id}
💰 {transaction['amount']} ريال
📝 السبب: {reason}
📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
                    
                    self.send_message(customer['telegram_id'], customer_msg, self.main_keyboard())
            
            self.send_message(message['chat']['id'], f"✅ تم رفض {trans_id}", self.admin_keyboard())
        else:
            self.send_message(message['chat']['id'], f"❌ فشل في رفض {trans_id}", self.admin_keyboard())
    
    def update_transaction_status(self, trans_id, new_status, note=''):
        """تحديث حالة المعاملة"""
        transactions = []
        success = False
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == trans_id:
                        row['status'] = new_status
                        if note:
                            row['admin_note'] = note
                        success = True
                    transactions.append(row)
            
            if success:
                with open('transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    fieldnames = ['id', 'customer_id', 'name', 'type', 'company', 'wallet_number', 'amount', 'exchange_address', 'status', 'date', 'admin_note']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(transactions)
        except:
            pass
        
        return success
    
    def get_transaction(self, trans_id):
        """جلب معاملة"""
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] == trans_id:
                        return row
        except:
            pass
        return None
    
    def get_customer_by_id(self, customer_id):
        """جلب عميل بالرقم"""
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['customer_id'] == customer_id:
                        return row
        except:
            pass
        return None
    
    def show_all_users(self, message):
        """عرض جميع المستخدمين"""
        users_text = "👥 جميع المستخدمين:\n\n"
        count = 0
        
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    count += 1
                    status = "🚫" if row.get('is_banned') == 'yes' else "✅"
                    users_text += f"{status} {row['name']} ({row['customer_id']})\n"
                    users_text += f"📱 {row['phone']}\n\n"
        except:
            pass
        
        users_text += f"📊 إجمالي المستخدمين: {count}"
        self.send_message(message['chat']['id'], users_text, self.admin_keyboard())
    
    def show_companies_admin(self, message):
        """عرض إدارة الشركات"""
        companies_text = "🏢 إدارة الشركات:\n\n"
        
        try:
            with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    companies_text += f"🆔 {row['id']} - {row['name']}\n"
                    companies_text += f"⚡ {row['type']} - {row['details']}\n\n"
        except:
            pass
        
        companies_text += "\n📝 الأوامر:\n"
        companies_text += "اضف_شركة اسم نوع تفاصيل\n"
        companies_text += "حذف_شركة رقم\n\n"
        companies_text += "مثال: اضف_شركة مدى both محفظة"
        
        self.send_message(message['chat']['id'], companies_text, self.admin_keyboard())
    
    def show_address_admin(self, message):
        """عرض إدارة العنوان"""
        current_address = self.get_exchange_address()
        
        address_text = f"📍 العنوان الحالي:\n{current_address}\n\n"
        address_text += "لتغيير العنوان استخدم:\n"
        address_text += "عنوان_جديد النص_الجديد\n\n"
        address_text += "مثال: عنوان_جديد شارع التحلية، جدة"
        
        self.send_message(message['chat']['id'], address_text, self.admin_keyboard())
    
    def show_statistics(self, message):
        """عرض الإحصائيات"""
        stats_text = "📊 إحصائيات النظام:\n\n"
        
        # عدد المستخدمين
        user_count = 0
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                user_count = sum(1 for row in reader)
        except:
            pass
        
        # المعاملات
        total_transactions = 0
        pending_count = 0
        approved_count = 0
        rejected_count = 0
        
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_transactions += 1
                    if row['status'] == 'pending':
                        pending_count += 1
                    elif row['status'] == 'approved':
                        approved_count += 1
                    elif row['status'] == 'rejected':
                        rejected_count += 1
        except:
            pass
        
        stats_text += f"👥 المستخدمين: {user_count}\n"
        stats_text += f"📋 إجمالي المعاملات: {total_transactions}\n"
        stats_text += f"⏳ معلقة: {pending_count}\n"
        stats_text += f"✅ مُوافق عليها: {approved_count}\n"
        stats_text += f"❌ مرفوضة: {rejected_count}\n"
        
        self.send_message(message['chat']['id'], stats_text, self.admin_keyboard())
    
    def add_company_simple(self, message, text):
        """إضافة شركة بسيطة"""
        parts = text.replace('اضف_شركة ', '').split(' ')
        if len(parts) < 3:
            self.send_message(message['chat']['id'], "❌ استخدم: اضف_شركة اسم نوع تفاصيل")
            return
        
        name = parts[0]
        company_type = parts[1]
        details = ' '.join(parts[2:])
        
        if company_type not in ['deposit', 'withdraw', 'both']:
            self.send_message(message['chat']['id'], "❌ النوع يجب أن يكون: deposit أو withdraw أو both")
            return
        
        company_id = str(int(datetime.now().timestamp()))
        
        try:
            with open('companies.csv', 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([company_id, name, company_type, details])
            
            self.send_message(message['chat']['id'], f"✅ تم إضافة الشركة: {name}")
        except:
            self.send_message(message['chat']['id'], "❌ فشل في إضافة الشركة")
    
    def delete_company_simple(self, message, text):
        """حذف شركة بسيطة"""
        company_id = text.replace('حذف_شركة ', '').strip()
        
        companies = []
        deleted = False
        
        try:
            with open('companies.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['id'] != company_id:
                        companies.append(row)
                    else:
                        deleted = True
            
            if deleted:
                with open('companies.csv', 'w', newline='', encoding='utf-8-sig') as f:
                    fieldnames = ['id', 'name', 'type', 'details']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(companies)
                
                self.send_message(message['chat']['id'], f"✅ تم حذف الشركة رقم {company_id}")
            else:
                self.send_message(message['chat']['id'], f"❌ لم يتم العثور على شركة رقم {company_id}")
        except:
            self.send_message(message['chat']['id'], "❌ فشل في حذف الشركة")
    
    def update_address_simple(self, message, text):
        """تحديث العنوان بسيط"""
        new_address = text.replace('عنوان_جديد ', '')
        
        try:
            with open('exchange_addresses.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'address', 'is_active'])
                writer.writerow(['1', new_address, 'yes'])
            
            self.send_message(message['chat']['id'], f"✅ تم تحديث العنوان إلى:\n{new_address}")
        except:
            self.send_message(message['chat']['id'], "❌ فشل في تحديث العنوان")
    
    def process_message(self, message):
        """معالج الرسائل الرئيسي"""
        if 'text' not in message:
            return
        
        text = message['text']
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        
        # بداية المحادثة
        if text == '/start':
            self.handle_start(message)
            return
        
        # معالجة التسجيل
        if user_id in self.user_states and self.user_states[user_id].startswith('registering'):
            self.handle_registration(message)
            return
        
        # فحص المستخدم المسجل
        user = self.find_user(user_id)
        if not user:
            self.handle_start(message)
            return
        
        # معالجة أوامر الأدمن
        if self.is_admin(user_id):
            if text == '/admin':
                self.send_message(chat_id, "🔧 لوحة تحكم الأدمن", self.admin_keyboard())
                return
            
            self.handle_admin_commands(message)
            return
        
        # معالجة حالات المستخدم
        if user_id in self.user_states:
            state = self.user_states[user_id]
            if 'deposit' in state:
                self.process_deposit_flow(message)
                return
            elif 'withdraw' in state:
                self.process_withdrawal_flow(message)
                return
        
        # القوائم الرئيسية
        if text == 'إيداع':
            self.start_deposit(message)
        elif text == 'سحب':
            self.start_withdrawal(message)
        elif text == 'طلباتي':
            self.show_user_requests(message)
        elif text == 'دعم':
            support_msg = "📞 للدعم الفني:\n\nيمكنك التواصل معنا عبر الطلبات أو مراسلة الإدارة مباشرة"
            self.send_message(chat_id, support_msg, self.main_keyboard())
        elif text == 'رجوع':
            self.send_message(chat_id, "تم العودة للقائمة الرئيسية", self.main_keyboard())
            if user_id in self.user_states:
                del self.user_states[user_id]
        else:
            self.send_message(chat_id, "اختر من القائمة:", self.main_keyboard())
    
    def run(self):
        """تشغيل البوت"""
        logger.info(f"✅ النظام المبسط يعمل")
        
        while True:
            try:
                updates = self.get_updates()
                if updates and updates.get('ok'):
                    for update in updates['result']:
                        self.offset = update['update_id']
                        
                        if 'message' in update:
                            self.process_message(update['message'])
                        elif 'callback_query' in update:
                            pass  # يمكن إضافة معالجة الأزرار هنا لاحقاً
                            
            except KeyboardInterrupt:
                logger.info("تم إيقاف البوت")
                break
            except Exception as e:
                logger.error(f"خطأ: {e}")

if __name__ == "__main__":
    # جلب التوكن
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        logger.error("BOT_TOKEN غير موجود في متغيرات البيئة")
        exit(1)
    
    # تشغيل البوت
    bot = SimpleLangSenseBot(bot_token)
    bot.run()