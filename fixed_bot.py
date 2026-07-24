#!/usr/bin/env python3
"""
LangSense Bot - مُحسن ومُبسط
يحفظ البيانات في ملفات Excel بدون قواعد بيانات
"""

import os
import json
import time
import logging
import csv
from datetime import datetime
import urllib.request
import urllib.parse
import urllib.error

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LangSenseBot:
    def __init__(self, token):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self.init_files()
        
    def init_files(self):
        """إنشاء ملفات Excel"""
        # ملف المستخدمين
        if not os.path.exists('users.csv'):
            with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['telegram_id', 'name', 'phone', 'customer_id', 'language', 'date', 'is_banned', 'ban_reason'])
        
        # ملف المعاملات
        if not os.path.exists('transactions.csv'):
            with open('transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'customer_id', 'telegram_id', 'name', 'type', 'amount', 'status', 'date', 'admin_note', 'payment_method', 'receipt_info'])
        
        # ملف الشكاوى
        if not os.path.exists('complaints.csv'):
            with open('complaints.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'customer_id', 'subject', 'message', 'status', 'date'])
        
        # ملف وسائل الدفع
        if not os.path.exists('payment_methods.csv'):
            with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'type', 'details', 'is_active', 'created_date'])
                # إضافة وسائل افتراضية
                writer.writerow(['1', 'البنك الأهلي', 'deposit', 'رقم الحساب: 1234567890', 'active', datetime.now().strftime('%Y-%m-%d')])
                writer.writerow(['2', 'بنك الراجحي', 'deposit', 'رقم الحساب: 0987654321', 'active', datetime.now().strftime('%Y-%m-%d')])
                writer.writerow(['3', 'STC Pay', 'withdraw', 'رقم الجوال: 0501234567', 'active', datetime.now().strftime('%Y-%m-%d')])
        
        logger.info("تم إنشاء ملفات Excel بنجاح")
        
    def api_call(self, method, data=None):
        """استدعاء Telegram API مُبسط"""
        url = f"{self.api_url}/{method}"
        
        try:
            if data:
                # تحويل البيانات إلى JSON
                json_data = json.dumps(data).encode('utf-8')
                req = urllib.request.Request(url, data=json_data)
                req.add_header('Content-Type', 'application/json')
            else:
                req = urllib.request.Request(url)
            
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            logger.error(f"HTTP Error {e.code}: {error_body}")
            return None
        except Exception as e:
            logger.error(f"خطأ في API: {e}")
            return None
    
    def send_message(self, chat_id, text, keyboard=None):
        """إرسال رسالة"""
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
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
    
    def main_keyboard(self, lang='ar'):
        """لوحة المفاتيح الرئيسية"""
        if lang == 'ar':
            return {
                'keyboard': [
                    [{'text': '💰 إيداع'}, {'text': '💸 سحب'}],
                    [{'text': '📋 طلباتي'}, {'text': '👤 حسابي'}],
                    [{'text': '📨 شكوى'}, {'text': '🇺🇸 English'}]
                ],
                'resize_keyboard': True
            }
        else:
            return {
                'keyboard': [
                    [{'text': '💰 Deposit'}, {'text': '💸 Withdraw'}],
                    [{'text': '📋 My Requests'}, {'text': '👤 Profile'}],
                    [{'text': '📨 Complaint'}, {'text': '🇸🇦 العربية'}]
                ],
                'resize_keyboard': True
            }
    
    def phone_keyboard(self, lang='ar'):
        """لوحة طلب رقم الهاتف"""
        text = '📱 مشاركة رقم الهاتف' if lang == 'ar' else '📱 Share Phone'
        return {
            'keyboard': [[{'text': text, 'request_contact': True}]],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
    
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
    
    def save_user(self, telegram_id, name, phone, customer_id, language='ar'):
        """حفظ مستخدم جديد"""
        with open('users.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                telegram_id, name, phone, customer_id, 
                language, datetime.now().strftime('%Y-%m-%d %H:%M'), 'no', ''
            ])
    
    def generate_customer_id(self):
        """توليد رقم عميل"""
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()
                count = len(lines) - 1  # طرح سطر العناوين
                return f"C{count + 1:06d}"
        except:
            return "C000001"
    
    def save_transaction(self, customer_id, telegram_id, name, trans_type, amount, payment_method='', receipt_info='', status='pending'):
        """حفظ معاملة"""
        trans_id = f"T{datetime.now().strftime('%Y%m%d%H%M%S')}"
        with open('transactions.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                trans_id, customer_id, telegram_id, name, trans_type, amount, 
                status, datetime.now().strftime('%Y-%m-%d %H:%M'), '', payment_method, receipt_info
            ])
        return trans_id
    
    def save_complaint(self, customer_id, subject, message, status='new'):
        """حفظ شكوى"""
        comp_id = f"COMP{datetime.now().strftime('%Y%m%d%H%M%S')}"
        with open('complaints.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                comp_id, customer_id, subject, message, 
                status, datetime.now().strftime('%Y-%m-%d %H:%M')
            ])
        return comp_id
    
    def handle_start(self, message):
        """التعامل مع أمر /start"""
        user_info = message['from']
        user = self.find_user(user_info['id'])
        
        if not user:
            # مستخدم جديد
            text = f"مرحباً {user_info['first_name']}! 🎉\n\nأهلاً بك في LangSense\nيرجى مشاركة رقم هاتفك للتسجيل"
            self.send_message(message['chat']['id'], text, self.phone_keyboard())
        else:
            # مستخدم موجود
            lang = user.get('language', 'ar')
            text = f"مرحباً {user['name']}! 👋\nرقم العميل: {user['customer_id']}" if lang == 'ar' else f"Welcome {user['name']}! 👋\nCustomer ID: {user['customer_id']}"
            self.send_message(message['chat']['id'], text, self.main_keyboard(lang))
    
    def handle_contact(self, message):
        """التعامل مع مشاركة رقم الهاتف"""
        contact = message['contact']
        user_info = message['from']
        
        if contact['user_id'] == user_info['id']:
            customer_id = self.generate_customer_id()
            name = user_info['first_name']
            phone = contact['phone_number']
            
            self.save_user(user_info['id'], name, phone, customer_id)
            
            text = f"✅ تم التسجيل بنجاح!\n📱 الهاتف: {phone}\n🆔 رقم العميل: {customer_id}"
            self.send_message(message['chat']['id'], text, self.main_keyboard())
    
    def is_admin(self, telegram_id):
        """فحص إذا كان المستخدم أدمن"""
        admin_ids = os.getenv('ADMIN_USER_IDS', '').split(',')
        return str(telegram_id) in admin_ids
    
    def is_user_banned(self, telegram_id):
        """فحص إذا كان المستخدم محظور"""
        user = self.find_user(telegram_id)
        return user and user.get('is_banned', 'no') == 'yes'
    
    def get_payment_methods(self, method_type=None):
        """جلب وسائل الدفع"""
        methods = []
        try:
            with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if method_type is None or row['type'] == method_type:
                        if row['is_active'] == 'active':
                            methods.append(row)
        except:
            pass
        return methods
    
    def handle_admin_commands(self, message):
        """أوامر الأدمن"""
        if not self.is_admin(message['from']['id']):
            self.send_message(message['chat']['id'], "🚫 غير مسموح! هذا الأمر للأدمن فقط")
            return
        
        # إحصائيات
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                users_count = len(f.readlines()) - 1
        except:
            users_count = 0
            
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                trans_list = list(reader)
                trans_count = len(trans_list)
                pending_count = len([t for t in trans_list if t['status'] == 'pending'])
        except:
            trans_count = 0
            pending_count = 0
        
        try:
            with open('complaints.csv', 'r', encoding='utf-8-sig') as f:
                comp_count = len(f.readlines()) - 1
        except:
            comp_count = 0
        
        admin_text = f"""🛠️ لوحة الإدارة المتقدمة

📊 الإحصائيات:
👥 المستخدمين: {users_count}
💰 المعاملات: {trans_count} (⏳ معلقة: {pending_count})
📨 الشكاوى: {comp_count}

🔧 أوامر إدارة المستخدمين:
/search اسم_أو_رقم - البحث عن مستخدم
/userinfo رقم_العميل - معلومات مستخدم
/ban رقم_العميل سبب - حظر مستخدم
/unban رقم_العميل - إلغاء حظر

💳 إدارة وسائل الدفع:
/payments - عرض وسائل الدفع
/addpay نوع اسم تفاصيل - إضافة وسيلة دفع

📋 إدارة الطلبات:
/pending - الطلبات المعلقة
/approve رقم_المعاملة - موافقة
/reject رقم_المعاملة سبب - رفض
/note رقم_المعاملة ملاحظة - إضافة تعليق

📢 أوامر أخرى:
/users - قائمة المستخدمين
/broadcast رسالة - إرسال جماعي"""
        
        self.send_message(message['chat']['id'], admin_text)
    
    def handle_broadcast(self, message):
        """إرسال رسالة جماعية"""
        if not self.is_admin(message['from']['id']):
            return
        
        # استخراج الرسالة من النص
        parts = message['text'].split(' ', 1)
        if len(parts) < 2:
            self.send_message(message['chat']['id'], "استخدم: /broadcast رسالتك")
            return
        
        broadcast_msg = parts[1]
        
        # جلب جميع المستخدمين
        users = []
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                users = list(reader)
        except:
            pass
        
        if not users:
            self.send_message(message['chat']['id'], "لا يوجد مستخدمين لإرسال الرسالة إليهم")
            return
        
        # إرسال الرسالة لجميع المستخدمين
        success_count = 0
        for user in users:
            try:
                result = self.send_message(user['telegram_id'], f"📢 رسالة من الإدارة:\n\n{broadcast_msg}")
                if result and result.get('ok'):
                    success_count += 1
                time.sleep(0.1)  # تجنب السبام
            except:
                pass
        
        self.send_message(message['chat']['id'], f"✅ تم إرسال الرسالة إلى {success_count} من {len(users)} مستخدم")
    
    def handle_users_list(self, message):
        """عرض قائمة المستخدمين"""
        if not self.is_admin(message['from']['id']):
            return
        
        try:
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                users = list(reader)
        except:
            users = []
        
        if not users:
            self.send_message(message['chat']['id'], "لا يوجد مستخدمين مسجلين")
            return
        
        users_text = "👥 قائمة المستخدمين:\n\n"
        for user in users[-10:]:  # آخر 10 مستخدمين
            users_text += f"• {user['name']} ({user['customer_id']})\n  📱 {user['phone']}\n  📅 {user['date']}\n\n"
        
        self.send_message(message['chat']['id'], users_text)
    
    def handle_text(self, message):
        """التعامل مع الرسائل النصية"""
        text = message['text']
        chat_id = message['chat']['id']
        
        # أوامر خاصة
        if text == '/admin':
            self.handle_admin_commands(message)
            return
        elif text.startswith('/broadcast '):
            self.handle_broadcast(message)
            return
        elif text == '/users':
            self.handle_users_list(message)
            return
        elif text == '/myid':
            # عرض ID المستخدم
            self.send_message(chat_id, f"🆔 Telegram ID الخاص بك:\n`{message['from']['id']}`\n\nانسخ هذا الرقم وأرسله للمطور لإضافتك كأدمن")
            return
        
        user = self.find_user(message['from']['id'])
        
        if not user:
            self.handle_start(message)
            return
        
        lang = user.get('language', 'ar')
        
        # تغيير اللغة
        if text == '🇺🇸 English':
            # تحديث اللغة في الملف
            self.update_user_language(user['telegram_id'], 'en')
            self.send_message(chat_id, "✅ Language changed to English", self.main_keyboard('en'))
            return
        elif text == '🇸🇦 العربية':
            self.update_user_language(user['telegram_id'], 'ar')
            self.send_message(chat_id, "✅ تم تغيير اللغة إلى العربية", self.main_keyboard('ar'))
            return
        
        # معالجة الطلبات
        if text in ['💰 إيداع', '💰 Deposit']:
            trans_id = self.save_transaction(user['customer_id'], 'deposit', '0')
            response = f"💰 طلب إيداع جديد\n🆔 رقم المعاملة: {trans_id}\n\nيرجى إرسال المبلغ وصورة الإيصال" if lang == 'ar' else f"💰 New deposit request\n🆔 Transaction: {trans_id}\n\nPlease send amount and receipt image"
            self.send_message(chat_id, response)
            
        elif text in ['💸 سحب', '💸 Withdraw']:
            trans_id = self.save_transaction(user['customer_id'], 'withdraw', '0')
            response = f"💸 طلب سحب جديد\n🆔 رقم المعاملة: {trans_id}\n\nيرجى إرسال المبلغ وبيانات الحساب" if lang == 'ar' else f"💸 New withdrawal request\n🆔 Transaction: {trans_id}\n\nPlease send amount and account details"
            self.send_message(chat_id, response)
            
        elif text in ['📋 طلباتي', '📋 My Requests']:
            # عرض آخر 5 طلبات
            transactions = self.get_user_transactions(user['customer_id'])
            if transactions:
                response = "📋 آخر طلباتك:\n\n" if lang == 'ar' else "📋 Your recent requests:\n\n"
                for trans in transactions[-5:]:
                    response += f"• {trans['id']} - {trans['type']} - {trans['status']}\n"
            else:
                response = "لا توجد طلبات سابقة" if lang == 'ar' else "No previous requests"
            self.send_message(chat_id, response)
            
        elif text in ['👤 حسابي', '👤 Profile']:
            response = f"👤 بياناتك:\n🏷️ الاسم: {user['name']}\n📱 الهاتف: {user['phone']}\n🆔 رقم العميل: {user['customer_id']}\n📅 تاريخ التسجيل: {user['date']}" if lang == 'ar' else f"👤 Your Profile:\n🏷️ Name: {user['name']}\n📱 Phone: {user['phone']}\n🆔 Customer ID: {user['customer_id']}\n📅 Registration: {user['date']}"
            self.send_message(chat_id, response)
            
        elif text in ['📨 شكوى', '📨 Complaint']:
            comp_id = self.save_complaint(user['customer_id'], 'عام', 'في انتظار التفاصيل')
            response = f"📨 شكوى جديدة\n🆔 رقم الشكوى: {comp_id}\n\nيرجى إرسال تفاصيل الشكوى" if lang == 'ar' else f"📨 New complaint\n🆔 Complaint ID: {comp_id}\n\nPlease send complaint details"
            self.send_message(chat_id, response)
            
        else:
            response = "اختر من القائمة أدناه:" if lang == 'ar' else "Please select from the menu below:"
            self.send_message(chat_id, response, self.main_keyboard(lang))
    
    def update_user_language(self, telegram_id, new_lang):
        """تحديث لغة المستخدم"""
        try:
            # قراءة جميع المستخدمين
            users = []
            with open('users.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['telegram_id'] == str(telegram_id):
                        row['language'] = new_lang
                    users.append(row)
            
            # إعادة كتابة الملف
            with open('users.csv', 'w', newline='', encoding='utf-8-sig') as f:
                fieldnames = ['telegram_id', 'name', 'phone', 'customer_id', 'language', 'date']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(users)
        except Exception as e:
            logger.error(f"خطأ في تحديث اللغة: {e}")
    
    def get_user_transactions(self, customer_id):
        """جلب معاملات المستخدم"""
        transactions = []
        try:
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['customer_id'] == customer_id:
                        transactions.append(row)
        except:
            pass
        return transactions
    
    def run(self):
        """تشغيل البوت"""
        # اختبار التوكن
        test_result = self.api_call('getMe')
        if not test_result or not test_result.get('ok'):
            logger.error("❌ خطأ في التوكن!")
            print("تأكد من صحة BOT_TOKEN")
            return
        
        bot_info = test_result['result']
        logger.info(f"✅ البوت يعمل: @{bot_info['username']}")
        logger.info("📁 البيانات محفوظة في: users.csv, transactions.csv, complaints.csv")
        
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
                                else:
                                    self.handle_text(message)
                            elif 'contact' in message:
                                self.handle_contact(message)
                
                time.sleep(1)
                
            except KeyboardInterrupt:
                logger.info("تم إيقاف البوت")
                break
            except Exception as e:
                logger.error(f"خطأ: {e}")
                time.sleep(3)

if __name__ == '__main__':
    # قراءة التوكن
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        print("❌ يرجى تعيين BOT_TOKEN في متغيرات البيئة")
        exit(1)
    
    print("🚀 بدء تشغيل LangSense Bot...")
    bot = LangSenseBot(bot_token)
    bot.run()