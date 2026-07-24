#!/usr/bin/env python3
"""
LangSense Telegram Bot - Excel Based Storage
No databases, no servers - all data saved in Excel files
"""

import os
import json
import time
import logging
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError, HTTPError
from datetime import datetime
import csv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ExcelTelegramBot:
    def __init__(self, token):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self.users_file = 'users_data.csv'
        self.transactions_file = 'transactions_data.csv'
        self.complaints_file = 'complaints_data.csv'
        self.init_excel_files()
        
    def init_excel_files(self):
        """Initialize CSV files (Excel compatible)"""
        # Initialize users file
        if not os.path.exists(self.users_file):
            with open(self.users_file, 'w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file)
                writer.writerow([
                    'telegram_id', 'username', 'first_name', 'last_name', 
                    'phone_number', 'customer_code', 'language', 'country',
                    'registration_date', 'is_active'
                ])
                
        # Initialize transactions file  
        if not os.path.exists(self.transactions_file):
            with open(self.transactions_file, 'w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file)
                writer.writerow([
                    'transaction_id', 'customer_code', 'telegram_id', 'type', 
                    'amount', 'status', 'request_date', 'approval_date',
                    'notes', 'receipt_info'
                ])
                
        # Initialize complaints file
        if not os.path.exists(self.complaints_file):
            with open(self.complaints_file, 'w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file)
                writer.writerow([
                    'complaint_id', 'customer_code', 'telegram_id', 'subject',
                    'description', 'status', 'submission_date', 'resolution_date',
                    'admin_response'
                ])
                
        logger.info("Excel files initialized successfully")
        
    def make_request(self, method, params=None):
        """Make HTTP request to Telegram API"""
        url = f"{self.api_url}/{method}"
        
        if params:
            if method in ['sendMessage', 'sendPhoto', 'sendDocument']:
                data = urlencode(params).encode('utf-8')
                request = Request(url, data=data)
                request.add_header('Content-Type', 'application/x-www-form-urlencoded')
            else:
                url += '?' + urlencode(params)
                request = Request(url)
        else:
            request = Request(url)
            
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except (URLError, HTTPError, json.JSONDecodeError) as e:
            logger.error(f"API request failed: {e}")
            return None
            
    def send_message(self, chat_id, text, reply_markup=None):
        """Send message to user"""
        params = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        if reply_markup:
            params['reply_markup'] = json.dumps(reply_markup)
            
        return self.make_request('sendMessage', params)
        
    def get_updates(self):
        """Get updates from Telegram"""
        params = {
            'offset': self.offset + 1,
            'timeout': 10
        }
        return self.make_request('getUpdates', params)
        
    def get_main_menu_keyboard(self, lang='ar'):
        """Create main menu keyboard"""
        if lang == 'ar':
            return {
                'keyboard': [
                    [{'text': '💰 طلب إيداع'}, {'text': '💸 طلب سحب'}],
                    [{'text': '📨 تقديم شكوى'}, {'text': '📋 حالة طلباتي'}],
                    [{'text': '👨‍💼 أدوات الإدارة'}, {'text': '👤 بياناتي الشخصية'}],
                    [{'text': '⚙️ تغيير اللغة'}, {'text': '🆘 المساعدة'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': False
            }
        else:
            return {
                'keyboard': [
                    [{'text': '💰 Request Deposit'}, {'text': '💸 Request Withdrawal'}],
                    [{'text': '📨 Submit Complaint'}, {'text': '📋 My Requests Status'}],
                    [{'text': '👨‍💼 Admin Tools'}, {'text': '👤 My Profile'}],
                    [{'text': '⚙️ Change Language'}, {'text': '🆘 Help'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': False
            }
            
    def get_phone_request_keyboard(self, lang='ar'):
        """Create phone number request keyboard"""
        text = '📱 مشاركة رقم الهاتف' if lang == 'ar' else '📱 Share Phone Number'
        return {
            'keyboard': [[{'text': text, 'request_contact': True}]],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        
    def get_language_keyboard(self):
        """Create language selection keyboard"""
        return {
            'keyboard': [
                [{'text': '🇸🇦 العربية'}, {'text': '🇺🇸 English'}]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        
    def find_user_by_telegram_id(self, telegram_id):
        """Find user in CSV file"""
        try:
            with open(self.users_file, 'r', newline='', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row['telegram_id'] == str(telegram_id):
                        return row
            return None
        except FileNotFoundError:
            return None
            
    def save_user(self, user_data):
        """Save or update user in CSV file"""
        users = []
        user_exists = False
        
        # Read existing users
        try:
            with open(self.users_file, 'r', newline='', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row['telegram_id'] == str(user_data['telegram_id']):
                        # Update existing user
                        users.append(user_data)
                        user_exists = True
                    else:
                        users.append(row)
        except FileNotFoundError:
            pass
            
        # Add new user if doesn't exist
        if not user_exists:
            users.append(user_data)
            
        # Write back to file
        with open(self.users_file, 'w', newline='', encoding='utf-8-sig') as file:
            if users:
                fieldnames = users[0].keys()
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(users)
                
    def generate_customer_code(self):
        """Generate unique customer code"""
        try:
            with open(self.users_file, 'r', newline='', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                count = sum(1 for row in reader if row['customer_code'])
                return f"C-2025-{count + 1:06d}"
        except FileNotFoundError:
            return "C-2025-000001"
            
    def save_transaction(self, transaction_data):
        """Save transaction request to CSV file"""
        with open(self.transactions_file, 'a', newline='', encoding='utf-8-sig') as file:
            fieldnames = [
                'transaction_id', 'customer_code', 'telegram_id', 'type', 
                'amount', 'status', 'request_date', 'approval_date',
                'notes', 'receipt_info'
            ]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            
            # Write header if file is empty
            if file.tell() == 0:
                writer.writeheader()
                
            writer.writerow(transaction_data)
            
    def save_complaint(self, complaint_data):
        """Save complaint to CSV file"""
        with open(self.complaints_file, 'a', newline='', encoding='utf-8-sig') as file:
            fieldnames = [
                'complaint_id', 'customer_code', 'telegram_id', 'subject',
                'description', 'status', 'submission_date', 'resolution_date',
                'admin_response'
            ]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            
            # Write header if file is empty  
            if file.tell() == 0:
                writer.writeheader()
                
            writer.writerow(complaint_data)
            
    def get_user_transactions(self, customer_code):
        """Get user transactions from CSV"""
        transactions = []
        try:
            with open(self.transactions_file, 'r', newline='', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row['customer_code'] == customer_code:
                        transactions.append(row)
        except FileNotFoundError:
            pass
        return transactions
        
    def get_user_complaints(self, customer_code):
        """Get user complaints from CSV"""
        complaints = []
        try:
            with open(self.complaints_file, 'r', newline='', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row['customer_code'] == customer_code:
                        complaints.append(row)
        except FileNotFoundError:
            pass
        return complaints
        
    def handle_start(self, message):
        """Handle /start command"""
        telegram_user = message['from']
        user = self.find_user_by_telegram_id(telegram_user['id'])
        
        if not user or not user.get('phone_number'):
            # New user or user without phone
            welcome_text = (
                f"مرحباً بك {telegram_user['first_name']}! 🎉\n\n"
                "أهلاً وسهلاً في نظام LangSense المالي.\n\n"
                "لإكمال التسجيل، يرجى مشاركة رقم هاتفك معنا."
            )
            
            self.send_message(
                message['chat']['id'],
                welcome_text,
                self.get_phone_request_keyboard('ar')
            )
        else:
            lang = user.get('language', 'ar')
            welcome_text = (
                f"أهلاً وسهلاً بك مرة أخرى {user['first_name']}! 👋\n\n"
                f"رقم العميل: {user['customer_code']}\n\n"
                "اختر الخدمة المطلوبة من القائمة أدناه:"
            ) if lang == 'ar' else (
                f"Welcome back {user['first_name']}! 👋\n\n"
                f"Customer ID: {user['customer_code']}\n\n"
                "Select the required service from the menu below:"
            )
            
            self.send_message(
                message['chat']['id'],
                welcome_text,
                self.get_main_menu_keyboard(lang)
            )
            
    def handle_contact(self, message):
        """Handle contact sharing"""
        contact = message['contact']
        telegram_user = message['from']
        
        if contact['user_id'] == telegram_user['id']:
            customer_code = self.generate_customer_code()
            
            user_data = {
                'telegram_id': str(telegram_user['id']),
                'username': telegram_user.get('username', ''),
                'first_name': telegram_user['first_name'],
                'last_name': telegram_user.get('last_name', ''),
                'phone_number': contact['phone_number'],
                'customer_code': customer_code,
                'language': 'ar',
                'country': 'SA',
                'registration_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'is_active': 'Yes'
            }
            
            self.save_user(user_data)
            
            success_text = (
                f"✅ تم تسجيل رقم الهاتف بنجاح!\n\n"
                f"📱 الرقم: {contact['phone_number']}\n"
                f"🆔 رقم العميل: {customer_code}\n\n"
                "أهلاً وسهلاً بك في نظام LangSense المالي!"
            )
            
            self.send_message(
                message['chat']['id'],
                success_text,
                self.get_main_menu_keyboard('ar')
            )
            
    def handle_deposit_request(self, message):
        """Handle deposit request"""
        user = self.find_user_by_telegram_id(message['from']['id'])
        if not user:
            return
            
        lang = user.get('language', 'ar')
        
        transaction_id = f"DEP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        response = (
            f"💰 طلب إيداع جديد\n\n"
            f"🆔 رقم المعاملة: {transaction_id}\n\n"
            "لإتمام طلب الإيداع، يرجى إرسال:\n"
            "1️⃣ المبلغ المراد إيداعه\n"
            "2️⃣ صورة إيصال التحويل\n\n"
            "مثال: 1000 ريال\n\n"
            "سيتم مراجعة طلبك خلال 24 ساعة."
        ) if lang == 'ar' else (
            f"💰 New Deposit Request\n\n"
            f"🆔 Transaction ID: {transaction_id}\n\n"
            "To complete the deposit request, please send:\n"
            "1️⃣ Amount to deposit\n"
            "2️⃣ Transfer receipt image\n\n"
            "Example: 1000 SAR\n\n"
            "Your request will be reviewed within 24 hours."
        )
        
        self.send_message(message['chat']['id'], response)
        
        # Save transaction request
        transaction_data = {
            'transaction_id': transaction_id,
            'customer_code': user['customer_code'],
            'telegram_id': str(message['from']['id']),
            'type': 'Deposit',
            'amount': '0',  # Will be updated when user provides amount
            'status': 'Pending Info',
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'approval_date': '',
            'notes': 'Awaiting amount and receipt',
            'receipt_info': ''
        }
        
        self.save_transaction(transaction_data)
        
    def handle_withdrawal_request(self, message):
        """Handle withdrawal request"""
        user = self.find_user_by_telegram_id(message['from']['id'])
        if not user:
            return
            
        lang = user.get('language', 'ar')
        
        transaction_id = f"WD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        response = (
            f"💸 طلب سحب جديد\n\n"
            f"🆔 رقم المعاملة: {transaction_id}\n\n"
            "لإتمام طلب السحب، يرجى إرسال:\n"
            "1️⃣ المبلغ المراد سحبه\n"
            "2️⃣ بيانات الحساب البنكي\n"
            "3️⃣ صورة الهوية\n\n"
            "مثال: 500 ريال\n"
            "البنك الأهلي - 1234567890\n\n"
            "سيتم معالجة طلبك خلال 48 ساعة."
        ) if lang == 'ar' else (
            f"💸 New Withdrawal Request\n\n"
            f"🆔 Transaction ID: {transaction_id}\n\n"
            "To complete the withdrawal request, please send:\n"
            "1️⃣ Amount to withdraw\n"
            "2️⃣ Bank account details\n"
            "3️⃣ ID photo\n\n"
            "Example: 500 SAR\n"
            "National Bank - 1234567890\n\n"
            "Your request will be processed within 48 hours."
        )
        
        self.send_message(message['chat']['id'], response)
        
        # Save transaction request
        transaction_data = {
            'transaction_id': transaction_id,
            'customer_code': user['customer_code'],
            'telegram_id': str(message['from']['id']),
            'type': 'Withdrawal',
            'amount': '0',  # Will be updated when user provides amount
            'status': 'Pending Info',
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'approval_date': '',
            'notes': 'Awaiting amount and bank details',
            'receipt_info': ''
        }
        
        self.save_transaction(transaction_data)
        
    def handle_complaint_request(self, message):
        """Handle complaint submission"""
        user = self.find_user_by_telegram_id(message['from']['id'])
        if not user:
            return
            
        lang = user.get('language', 'ar')
        
        complaint_id = f"COMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        response = (
            f"📨 تقديم شكوى جديدة\n\n"
            f"🆔 رقم الشكوى: {complaint_id}\n\n"
            "يرجى إرسال تفاصيل الشكوى:\n"
            "• موضوع الشكوى\n"
            "• تفاصيل المشكلة\n"
            "• أي مستندات مطلوبة\n\n"
            "سيتم الرد على شكواك خلال 24 ساعة."
        ) if lang == 'ar' else (
            f"📨 New Complaint Submission\n\n"
            f"🆔 Complaint ID: {complaint_id}\n\n"
            "Please send complaint details:\n"
            "• Subject of complaint\n"
            "• Problem details\n"
            "• Any required documents\n\n"
            "Your complaint will be addressed within 24 hours."
        )
        
        self.send_message(message['chat']['id'], response)
        
        # Save complaint
        complaint_data = {
            'complaint_id': complaint_id,
            'customer_code': user['customer_code'],
            'telegram_id': str(message['from']['id']),
            'subject': 'Pending',
            'description': 'Awaiting details',
            'status': 'Submitted',
            'submission_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'resolution_date': '',
            'admin_response': ''
        }
        
        self.save_complaint(complaint_data)
        
    def handle_status_check(self, message):
        """Handle status check request"""
        user = self.find_user_by_telegram_id(message['from']['id'])
        if not user:
            return
            
        lang = user.get('language', 'ar')
        
        # Get transactions
        transactions = self.get_user_transactions(user['customer_code'])
        complaints = self.get_user_complaints(user['customer_code'])
        
        status_text = "📋 حالة طلباتي\n\n" if lang == 'ar' else "📋 My Requests Status\n\n"
        
        if transactions:
            status_text += "💰 المعاملات المالية:\n" if lang == 'ar' else "💰 Financial Transactions:\n"
            for trans in transactions[-5:]:  # Show last 5 transactions
                status_text += f"• {trans['transaction_id']} - {trans['type']} - {trans['status']}\n"
            status_text += "\n"
            
        if complaints:
            status_text += "📨 الشكاوى:\n" if lang == 'ar' else "📨 Complaints:\n"
            for comp in complaints[-3:]:  # Show last 3 complaints
                status_text += f"• {comp['complaint_id']} - {comp['status']}\n"
            status_text += "\n"
            
        if not transactions and not complaints:
            status_text += "لا توجد طلبات سابقة." if lang == 'ar' else "No previous requests found."
            
        self.send_message(message['chat']['id'], status_text)
        
    def handle_profile(self, message):
        """Handle profile view"""
        user = self.find_user_by_telegram_id(message['from']['id'])
        if not user:
            return
            
        lang = user.get('language', 'ar')
        
        profile_text = (
            f"👤 بياناتي الشخصية\n\n"
            f"🏷️ الاسم: {user['first_name']} {user.get('last_name', '')}\n"
            f"👤 اسم المستخدم: @{user.get('username', 'غير محدد')}\n"
            f"📱 رقم الهاتف: {user.get('phone_number', 'غير محدد')}\n"
            f"🆔 رقم العميل: {user.get('customer_code', 'غير محدد')}\n"
            f"🌐 اللغة: {user.get('language', 'ar').upper()}\n"
            f"🌍 الدولة: {user.get('country', 'SA').upper()}\n"
            f"📅 تاريخ التسجيل: {user.get('registration_date', 'غير محدد')}"
        ) if lang == 'ar' else (
            f"👤 My Profile\n\n"
            f"🏷️ Name: {user['first_name']} {user.get('last_name', '')}\n"
            f"👤 Username: @{user.get('username', 'Not Set')}\n"
            f"📱 Phone: {user.get('phone_number', 'Not Set')}\n"
            f"🆔 Customer ID: {user.get('customer_code', 'Not Set')}\n"
            f"🌐 Language: {user.get('language', 'ar').upper()}\n"
            f"🌍 Country: {user.get('country', 'SA').upper()}\n"
            f"📅 Registration: {user.get('registration_date', 'Not Set')}"
        )
        
        self.send_message(message['chat']['id'], profile_text)
        
    def handle_language_change(self, message):
        """Handle language change request"""
        response = "🌐 اختر اللغة المفضلة:\n🇸🇦 العربية\n🇺🇸 English"
        self.send_message(message['chat']['id'], response, self.get_language_keyboard())
        
    def handle_language_selection(self, message):
        """Handle language selection"""
        text = message['text']
        user = self.find_user_by_telegram_id(message['from']['id'])
        
        if not user:
            return
            
        if '🇸🇦 العربية' in text:
            new_lang = 'ar'
            response = "✅ تم تغيير اللغة إلى العربية بنجاح!"
        elif '🇺🇸 English' in text:
            new_lang = 'en'
            response = "✅ Language changed to English successfully!"
        else:
            return
            
        # Update user language
        user['language'] = new_lang
        self.save_user(user)
        
        self.send_message(message['chat']['id'], response, self.get_main_menu_keyboard(new_lang))
        
    def handle_admin_commands(self, message):
        """Handle admin commands"""
        admin_ids = os.getenv('ADMIN_USER_IDS', '').split(',')
        if str(message['from']['id']) not in admin_ids:
            self.send_message(
                message['chat']['id'],
                "🚫 غير مسموح! هذه الخدمة مخصصة للمشرفين فقط."
            )
            return
            
        # Count statistics from files
        user_count = 0
        transaction_count = 0
        complaint_count = 0
        
        try:
            with open(self.users_file, 'r', encoding='utf-8-sig') as f:
                user_count = len(f.readlines()) - 1  # Subtract header
        except:
            pass
            
        try:
            with open(self.transactions_file, 'r', encoding='utf-8-sig') as f:
                transaction_count = len(f.readlines()) - 1
        except:
            pass
            
        try:
            with open(self.complaints_file, 'r', encoding='utf-8-sig') as f:
                complaint_count = len(f.readlines()) - 1
        except:
            pass
            
        admin_text = (
            f"🛠️ لوحة إدارة النظام\n\n"
            f"📊 إحصائيات سريعة:\n"
            f"👥 المستخدمون: {user_count}\n"
            f"💰 المعاملات: {transaction_count}\n"
            f"📨 الشكاوى: {complaint_count}\n\n"
            f"📁 الملفات:\n"
            f"• {self.users_file}\n"
            f"• {self.transactions_file}\n"
            f"• {self.complaints_file}\n\n"
            f"يمكن فتح الملفات في Excel لإدارة البيانات"
        )
        
        self.send_message(message['chat']['id'], admin_text)
        
    def handle_text_message(self, message):
        """Handle text messages"""
        text = message['text']
        chat_id = message['chat']['id']
        
        user = self.find_user_by_telegram_id(message['from']['id'])
        if not user:
            return
            
        lang = user.get('language', 'ar')
        
        # Handle menu options
        if text in ['💰 طلب إيداع', '💰 Request Deposit']:
            self.handle_deposit_request(message)
        elif text in ['💸 طلب سحب', '💸 Request Withdrawal']:
            self.handle_withdrawal_request(message)
        elif text in ['📨 تقديم شكوى', '📨 Submit Complaint']:
            self.handle_complaint_request(message)
        elif text in ['📋 حالة طلباتي', '📋 My Requests Status']:
            self.handle_status_check(message)
        elif text in ['👤 بياناتي الشخصية', '👤 My Profile']:
            self.handle_profile(message)
        elif text in ['⚙️ تغيير اللغة', '⚙️ Change Language']:
            self.handle_language_change(message)
        elif text in ['🇸🇦 العربية', '🇺🇸 English']:
            self.handle_language_selection(message)
        elif text in ['🆘 المساعدة', '🆘 Help']:
            help_text = (
                "🆘 المساعدة\n\n"
                "الخدمات المتاحة:\n"
                "💰 طلب إيداع - لإيداع الأموال\n"
                "💸 طلب سحب - لسحب الأموال\n"
                "📨 تقديم شكوى - لتقديم شكوى\n"
                "📋 حالة طلباتي - متابعة الطلبات\n"
                "👤 بياناتي - عرض البيانات الشخصية\n"
                "⚙️ تغيير اللغة - تغيير لغة الواجهة\n\n"
                "للدعم الفني، تواصل مع الإدارة."
            ) if lang == 'ar' else (
                "🆘 Help\n\n"
                "Available services:\n"
                "💰 Request Deposit - For depositing funds\n"
                "💸 Request Withdrawal - For withdrawing funds\n"
                "📨 Submit Complaint - For submitting complaints\n"
                "📋 My Requests Status - Track requests\n"
                "👤 My Profile - View personal data\n"
                "⚙️ Change Language - Change interface language\n\n"
                "For technical support, contact administration."
            )
            self.send_message(chat_id, help_text)
        else:
            response = (
                "❓ عذراً، لم أفهم طلبك. يرجى استخدام القائمة أدناه."
            ) if lang == 'ar' else (
                "❓ Sorry, I didn't understand your request. Please use the menu below."
            )
            self.send_message(chat_id, response, self.get_main_menu_keyboard(lang))
            
    def run(self):
        """Main bot loop"""
        logger.info("Starting LangSense Excel Bot...")
        
        # Test bot token
        result = self.make_request('getMe')
        if not result or not result.get('ok'):
            logger.error("Invalid bot token!")
            return
            
        logger.info(f"Bot started: @{result['result']['username']}")
        logger.info("All data will be saved to Excel-compatible CSV files")
        logger.info(f"Files: {self.users_file}, {self.transactions_file}, {self.complaints_file}")
        
        while True:
            try:
                updates = self.get_updates()
                
                if updates and updates.get('ok'):
                    for update in updates['result']:
                        self.offset = update['update_id']
                        
                        if 'message' in update:
                            message = update['message']
                            
                            if 'text' in message:
                                if message['text'] == '/start':
                                    self.handle_start(message)
                                elif message['text'] == '/admin':
                                    self.handle_admin_commands(message)
                                else:
                                    self.handle_text_message(message)
                            elif 'contact' in message:
                                self.handle_contact(message)
                                
                time.sleep(1)
                
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in bot loop: {e}")
                time.sleep(5)

def main():
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        logger.error("BOT_TOKEN environment variable not set!")
        return
        
    bot = ExcelTelegramBot(bot_token)
    bot.run()

if __name__ == '__main__':
    main()