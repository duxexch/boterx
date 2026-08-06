"""
handlers/user_profile.py — User profile & transactions display
Mixin extracted from comprehensive_bot.py.
"""
import logging

logger = logging.getLogger(__name__)

class UserProfileMixin:
    """Mixin for user profile and transaction history display."""

    def show_user_transactions(self, message):
        """عرض معاملات المستخدم"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        lang = user.get('language', 'ar')
        user_currency = user.get('currency', self.get_setting('default_currency') or 'SAR')
        transactions_text = f"{self.tr('transactions_title', lang)}: {user['name']}\n\n"
        found_transactions = False
        try:
            import csv
            with open('transactions.csv', 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('telegram_id') == str(user['telegram_id']):
                        found_transactions = True
                        trans_type = row.get('type', '')
                        status = row.get('status', '')
                        amount = row.get('amount', '0')
                        company = row.get('company', '')
                        date = row.get('date', '')
                        icon = '💰' if trans_type == 'deposit' else '💸'
                        status_icon = '⏳' if 'pending' in status else ('✅' if status == 'approved' else '❌')
                        transactions_text += f"{icon} {trans_type} — {amount} {user_currency} | {company} | {status_icon} {status} | {date}\n"
            if not found_transactions:
                transactions_text += self.tr('no_transactions', lang)
            from bot_utils.telegram_helpers import make_inline_keyboard
            inline_btns = make_inline_keyboard([[('🔙 ' + self.tr('back_btn', lang), 'profile_back_main')]])
            self.send_inline_message(message['chat']['id'], transactions_text, inline_btns)
        except Exception as e:
            logger.error(f"خطأ في عرض المعاملات: {e}")
            self.send_message(message['chat']['id'], self.tr('error_msg', lang), self.main_keyboard(lang))

    def show_user_profile(self, message):
        """عرض ملف المستخدم"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        lang = user.get('language', 'ar')
        lang_names = self.get_language_names()
        from bot_utils.telegram_helpers import make_inline_keyboard
        inline_btns = make_inline_keyboard([
            [('💰 ' + self.tr('transactions_title', lang), 'profile_transactions')],
            [('🔙 ' + self.tr('back_btn', lang), 'profile_back_main')]
        ])
        profile_text = self.tr('profile_info', lang,
            name=user.get('name', ''),
            customer_id=user.get('customer_id', ''),
            phone=user.get('phone', self.tr('a0122_غير_محدد', lang)),
            currency=user.get('currency', 'SAR'),
            language=lang_names.get(lang, lang))
        self.send_inline_message(message['chat']['id'], profile_text, inline_btns)
