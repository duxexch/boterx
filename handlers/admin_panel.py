"""
handlers/admin_panel.py — Admin panel & actions handler
Mixin extracted from comprehensive_bot.py.
"""
import logging

logger = logging.getLogger(__name__)

class AdminPanelMixin:
    """Mixin for admin panel display and action handling."""

    def handle_admin_panel(self, message):
        """لوحة تحكم الأدمن الرئيسية"""
        user_id = message['from']['id']
        chat_id = message['chat']['id']
        if not self.is_admin(user_id):
            return
        self.current_admin_id = user_id
        admin = self.find_user(user_id)
        admin_lang = admin.get('language', 'ar') if admin else 'ar'
        self.send_message(chat_id, self.tr('admin_welcome', admin_lang), self.admin_keyboard(admin_lang))

    def show_match_admin_panel(self, message):
        """لوحة إدارة المطابقات"""
        user_id = message['from']['id']
        if not self.is_admin(user_id):
            return
        chat_id = message['chat']['id']
        admin = self.find_user(user_id)
        admin_lang = admin.get('language', 'ar') if admin else 'ar'
        # Show active matches, pending requests, logs, bot management
        text = "🔄 <b>إدارة المطابقات</b>\n\n"
        if self.match_manager:
            try:
                stats = self.match_manager.get_stats()
                text += f"📊 النشاطات النشطة: {stats.get('active', 0)}\n"
                text += f"⏳ الطلبات المعلقة: {stats.get('pending', 0)}\n"
            except:
                text += "⚠️ تعذر الحصول على الإحصائيات\n"
        else:
            text += "⚠️ نظام المطابقة غير متاح\n"
        from bot_utils.telegram_helpers import make_inline_keyboard
        inline_btns = make_inline_keyboard([
            [('🔄 الطلبات المعلقة', 'match_pending')],
            [('📜 السجل', 'match_logs')],
            [('🔙 رجوع', 'admin_back')]
        ])
        self.send_inline_message(chat_id, text, inline_btns)
