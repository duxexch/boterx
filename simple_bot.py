#!/usr/bin/env python3
"""
Simple Telegram Bot using basic HTTP requests
Works without complex dependencies
"""

import os
import json
import time
import sqlite3
import logging
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError, HTTPError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleTelegramBot:
    def __init__(self, token):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database"""
        self.conn = sqlite3.connect('langsense.db', check_same_thread=False)
        cursor = self.conn.cursor()
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT NOT NULL,
                last_name TEXT,
                phone_number TEXT,
                customer_code TEXT UNIQUE,
                language_code TEXT DEFAULT 'ar',
                country_code TEXT DEFAULT 'SA',
                is_active BOOLEAN DEFAULT 1,
                is_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create languages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS languages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                native_name TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Insert default languages
        cursor.execute("INSERT OR IGNORE INTO languages (code, name, native_name) VALUES ('ar', 'Arabic', 'العربية')")
        cursor.execute("INSERT OR IGNORE INTO languages (code, name, native_name) VALUES ('en', 'English', 'English')")
        
        self.conn.commit()
        logger.info("Database initialized successfully")
        
    def make_request(self, method, params=None):
        """Make HTTP request to Telegram API"""
        url = f"{self.api_url}/{method}"
        
        if params:
            if method == 'sendMessage' or method == 'sendPhoto':
                # POST request for sending messages
                data = urlencode(params).encode('utf-8')
                request = Request(url, data=data)
                request.add_header('Content-Type', 'application/x-www-form-urlencoded')
            else:
                # GET request for other methods
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
                    [{'text': '💰 إيداع'}, {'text': '💸 سحب'}],
                    [{'text': '📨 شكاوى'}, {'text': '🆘 دعم'}],
                    [{'text': '👨‍💼 مدير'}, {'text': '📋 خطط واشتراكات'}],
                    [{'text': '💼 المبيعات'}, {'text': '⚙️ الإعدادات'}],
                    [{'text': '⬅️ رجوع'}, {'text': '➡️ تقدم'}, {'text': '👤 حسابي'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': False
            }
        else:
            return {
                'keyboard': [
                    [{'text': '💰 Deposit'}, {'text': '💸 Withdraw'}],
                    [{'text': '📨 Complaints'}, {'text': '🆘 Support'}],
                    [{'text': '👨‍💼 Manager'}, {'text': '📋 Plans & Subscriptions'}],
                    [{'text': '💼 Sales'}, {'text': '⚙️ Settings'}],
                    [{'text': '⬅️ Back'}, {'text': '➡️ Forward'}, {'text': '👤 My Account'}]
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
        
    def get_or_create_user(self, telegram_user):
        """Get or create user in database"""
        cursor = self.conn.cursor()
        
        # Try to get existing user
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_user['id'],))
        user = cursor.fetchone()
        
        if user:
            # Update existing user
            cursor.execute("""
                UPDATE users 
                SET username = ?, first_name = ?, last_name = ?
                WHERE telegram_id = ?
            """, (
                telegram_user.get('username'),
                telegram_user['first_name'],
                telegram_user.get('last_name'),
                telegram_user['id']
            ))
        else:
            # Create new user
            cursor.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_name, language_code)
                VALUES (?, ?, ?, ?, ?)
            """, (
                telegram_user['id'],
                telegram_user.get('username'),
                telegram_user['first_name'],
                telegram_user.get('last_name'),
                telegram_user.get('language_code', 'ar')
            ))
            
        self.conn.commit()
        
        # Get updated user
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_user['id'],))
        return cursor.fetchone()
        
    def generate_customer_code(self):
        """Generate unique customer code"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE customer_code IS NOT NULL")
        count = cursor.fetchone()[0]
        return f"C-2025-{count + 1:06d}"
        
    def handle_start(self, message):
        """Handle /start command"""
        user = self.get_or_create_user(message['from'])
        lang = user[7] if user else 'ar'  # language_code column
        
        if not user[5]:  # phone_number column
            welcome_text = (
                f"مرحباً بك {user[3]}! 🎉\n\n"
                "أهلاً وسهلاً في نظام LangSense المالي.\n\n"
                "لإكمال التسجيل، يرجى مشاركة رقم هاتفك معنا لإنشاء حساب عميل آمن."
            ) if lang == 'ar' else (
                f"Welcome {user[3]}! 🎉\n\n"
                "Welcome to the LangSense Financial System.\n\n"
                "To complete registration, please share your phone number with us to create a secure customer account."
            )
            
            self.send_message(
                message['chat']['id'],
                welcome_text,
                self.get_phone_request_keyboard(lang)
            )
        else:
            welcome_text = (
                f"أهلاً وسهلاً بك مرة أخرى {user[3]}! 👋\n\n"
                f"رقم العميل: {user[6]}\n\n"
                "اختر الخدمة المطلوبة من القائمة أدناه:"
            ) if lang == 'ar' else (
                f"Welcome back {user[3]}! 👋\n\n"
                f"Customer ID: {user[6]}\n\n"
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
        if contact['user_id'] == message['from']['id']:
            cursor = self.conn.cursor()
            customer_code = self.generate_customer_code()
            
            cursor.execute("""
                UPDATE users 
                SET phone_number = ?, customer_code = ?
                WHERE telegram_id = ?
            """, (contact['phone_number'], customer_code, message['from']['id']))
            self.conn.commit()
            
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (message['from']['id'],))
            user = cursor.fetchone()
            lang = user[7]
            
            success_text = (
                f"✅ تم تسجيل رقم الهاتف بنجاح!\n\n"
                f"📱 الرقم: {contact['phone_number']}\n"
                f"🆔 رقم العميل: {customer_code}\n\n"
                "أهلاً وسهلاً بك في نظام LangSense المالي!"
            ) if lang == 'ar' else (
                f"✅ Phone number registered successfully!\n\n"
                f"📱 Number: {contact['phone_number']}\n"
                f"🆔 Customer ID: {customer_code}\n\n"
                "Welcome to the LangSense Financial System!"
            )
            
            self.send_message(
                message['chat']['id'],
                success_text,
                self.get_main_menu_keyboard(lang)
            )
            
    def handle_text_message(self, message):
        """Handle text messages"""
        text = message['text']
        chat_id = message['chat']['id']
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (message['from']['id'],))
        user = cursor.fetchone()
        
        if not user:
            return
            
        lang = user[7]
        
        # Handle menu options
        if text in ['💰 إيداع', '💰 Deposit']:
            response = (
                "💰 خدمة الإيداع\n\n"
                "لإتمام عملية الإيداع، يرجى:\n"
                "1. تحديد المبلغ المراد إيداعه\n"
                "2. اختيار وسيلة الدفع المناسبة\n"
                "3. إرفاق صورة إيصال التحويل\n\n"
                "سيتم مراجعة طلبك خلال 24 ساعة كحد أقصى."
            ) if lang == 'ar' else (
                "💰 Deposit Service\n\n"
                "To complete the deposit process, please:\n"
                "1. Specify the amount to deposit\n"
                "2. Choose the appropriate payment method\n"
                "3. Attach a transfer receipt image\n\n"
                "Your request will be reviewed within 24 hours maximum."
            )
            
        elif text in ['💸 سحب', '💸 Withdraw']:
            response = (
                "💸 خدمة السحب\n\n"
                "لإتمام عملية السحب، يرجى:\n"
                "1. تحديد المبلغ المراد سحبه\n"
                "2. تقديم بيانات الحساب المصرفي\n"
                "3. تأكيد الهوية حسب المطلوب\n\n"
                "سيتم معالجة طلبك خلال 48 ساعة كحد أقصى."
            ) if lang == 'ar' else (
                "💸 Withdrawal Service\n\n"
                "To complete the withdrawal process, please:\n"
                "1. Specify the amount to withdraw\n"
                "2. Provide bank account details\n"
                "3. Confirm identity as required\n\n"
                "Your request will be processed within 48 hours maximum."
            )
            
        elif text in ['👤 حسابي', '👤 My Account']:
            response = (
                f"👤 معلومات حسابي\n\n"
                f"🏷️ الاسم: {user[3]} {user[4] or ''}\n"
                f"👤 اسم المستخدم: @{user[2] or 'غير محدد'}\n"
                f"📱 رقم الهاتف: {user[5] or 'غير محدد'}\n"
                f"🆔 رقم العميل: {user[6] or 'غير محدد'}\n"
                f"🌐 اللغة: {user[7].upper()}\n"
                f"🌍 الدولة: {user[8].upper()}"
            ) if lang == 'ar' else (
                f"👤 My Account Information\n\n"
                f"🏷️ Name: {user[3]} {user[4] or ''}\n"
                f"👤 Username: @{user[2] or 'Not Set'}\n"
                f"📱 Phone: {user[5] or 'Not Set'}\n"
                f"🆔 Customer ID: {user[6] or 'Not Set'}\n"
                f"🌐 Language: {user[7].upper()}\n"
                f"🌍 Country: {user[8].upper()}"
            )
            
        else:
            response = (
                "❓ عذراً، لم أفهم طلبك. يرجى استخدام القائمة أدناه لاختيار الخدمة المطلوبة."
            ) if lang == 'ar' else (
                "❓ Sorry, I didn't understand your request. Please use the menu below to select the required service."
            )
            
        self.send_message(chat_id, response)
        
    def handle_admin_command(self, message):
        """Handle admin commands"""
        admin_ids = os.getenv('ADMIN_USER_IDS', '').split(',')
        if str(message['from']['id']) not in admin_ids:
            self.send_message(
                message['chat']['id'],
                "🚫 غير مسموح! هذه الخدمة مخصصة للمشرفين فقط."
            )
            return
            
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        active_users = cursor.fetchone()[0]
        
        admin_text = (
            f"🛠️ لوحة إدارة النظام\n\n"
            f"📊 إحصائيات سريعة:\n"
            f"👥 إجمالي المستخدمين: {total_users}\n"
            f"✅ المستخدمون النشطون: {active_users}\n\n"
            f"استخدم /users لعرض المستخدمين"
        )
        
        self.send_message(message['chat']['id'], admin_text)
        
    def run(self):
        """Main bot loop"""
        logger.info("Starting LangSense Bot...")
        
        # Test bot token
        result = self.make_request('getMe')
        if not result or not result.get('ok'):
            logger.error("Invalid bot token!")
            return
            
        logger.info(f"Bot started: @{result['result']['username']}")
        
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
                                    self.handle_admin_command(message)
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
        
    bot = SimpleTelegramBot(bot_token)
    bot.run()

if __name__ == '__main__':
    main()