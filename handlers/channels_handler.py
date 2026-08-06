"""
handlers/channels_handler.py — Channel relay, AI processing, source channels
Mixin extracted from comprehensive_bot.py.
"""
import logging

logger = logging.getLogger(__name__)


class ChannelsHandlerMixin:
    """Mixin for channel management, relay, AI processing, source channels."""

    def show_channels_admin(self, message):
        """لوحة إدارة القنوات"""
        user_id = message['from']['id']
        if not self.is_admin(user_id):
            return
        chat_id = message['chat']['id']
        channels = self.get_bot_channels()
        text = "📢 <b>إدارة القنوات</b>\n\n"
        if channels:
            for ch in channels:
                status = '🟢' if ch.get('is_active') == 'yes' else '⏸️'
                text += f"{status} {ch.get('title', ch.get('chat_id', ''))}\n"
        else:
            text += "⚠️ لا توجد قنوات مسجلة\n"
        from bot_utils.telegram_helpers import make_inline_keyboard
        inline_btns = make_inline_keyboard([
            [('➕ إضافة قناة', 'ch_add')],
            [('🔄 إعدادات AI', 'ch_ai_settings')],
            [('📝 استبدالات النص', 'ch_text_replacements')],
            [('📥 القنوات المصدرية', 'ch_sources')],
            [('🔙 رجوع', 'admin_back')]
        ])
        self.send_inline_message(chat_id, text, inline_btns)
