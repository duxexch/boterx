"""
handlers/registration.py — User registration & language selection handlers
Mixin extracted from comprehensive_bot.py.
"""
import logging

logger = logging.getLogger(__name__)


class RegistrationMixin:
    """Mixin for user registration, start, language selection, phone login."""

    def send_welcome(self, message):
        """رسالة ترحيب"""
        user_id = message['from']['id']
        user = self.find_user(user_id)
        if user:
            lang = user.get('language', 'ar')
            welcome = self.tr('choose_service', lang,
                name=user.get('name', ''),
                customer_id=user.get('customer_id', ''))
            self.send_message(message['chat']['id'], welcome, self.main_keyboard(lang, user_id))
        else:
            # New user — show language selection
            self.show_language_selection(message)

    def show_language_selection(self, message):
        """عرض اختيار اللغة"""
        chat_id = message['chat']['id']
        text = "🌍 اختر لغتك / Select your language"
        langs = self.get_supported_languages()
        from bot_utils.telegram_helpers import make_inline_keyboard
        rows = []
        lang_names = self.get_language_names()
        for code in langs:
            name = lang_names.get(code, code)
            rows.append([(f"{name}", f'start_lang_{code}')])
        inline_btns = make_inline_keyboard(rows)
        self.send_inline_message(chat_id, text, inline_btns)

    def handle_language_change(self, message):
        """تغيير لغة المستخدم"""
        user_id = message['from']['id']
        user = self.find_user(user_id)
        if not user:
            return
        self.show_language_selection(message)
