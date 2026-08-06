"""
handlers/payment_methods_handler.py — Payment methods management
Mixin extracted from comprehensive_bot.py.
"""
import logging

logger = logging.getLogger(__name__)


class PaymentMethodsHandlerMixin:
    """Mixin for payment method CRUD and display."""

    def show_payment_methods_admin(self, message):
        """عرض لوحة وسائل الدفع"""
        user_id = message['from']['id']
        if not self.is_admin(user_id):
            return
        chat_id = message['chat']['id']
        methods = self.get_all_payment_methods()
        text = "💳 <b>وسائل الدفع</b>\n\n"
        if methods:
            for m in methods:
                status = '🟢' if m.get('is_active') == 'yes' else '⏸️'
                icon = m.get('icon', '💳') or '💳'
                text += f"{status} {icon} {m.get('method_name', '')} ({m.get('method_type', '')})\n"
        else:
            text += "⚠️ لا توجد وسائل دفع\n"
        from bot_utils.telegram_helpers import make_inline_keyboard
        inline_btns = make_inline_keyboard([
            [('➕ إضافة وسيلة', 'pm_add')],
            [('📋 عرض الكل', 'pm_list')],
            [('🔙 رجوع', 'admin_back')]
        ])
        self.send_inline_message(chat_id, text, inline_btns)
