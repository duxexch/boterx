"""
handlers/svrp_handler.py — SVRP/Compensation system handlers
Mixin extracted from comprehensive_bot.py.
"""
import logging

logger = logging.getLogger(__name__)


class SVRPHandlerMixin:
    """Mixin for SVRP panel and admin methods."""

    def show_svrp_panel(self, message):
        """عرض لوحة 💎 تعويض 100%"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        lang = user.get('language', 'ar')
        from bot_utils.telegram_helpers import make_inline_keyboard
        # Show wallet, tasks, promo, referral tree, group info
        try:
            wallet = self.svrp.get_wallet(user['telegram_id']) if self.svrp else {'available': 0, 'frozen': 0}
            available = wallet.get('available', 0)
            frozen = wallet.get('frozen', 0)
            tier = wallet.get('tier', 'bronze') if self.svrp else 'bronze'
            text = f"💎 <b>تعويض 100%</b>\n\n"
            text += f"🟢 متاح: <code>{available}</code>\n"
            text += f"🧊 مجمد: <code>{frozen}</code>\n"
            text += f"⭐ المستوى: {tier}\n\n"
            text += "اختر:"
            inline_btns = make_inline_keyboard([
                [('💰 إيداع', 'svrp_deposit')],
                [('💸 سحب', 'svrp_withdraw')],
                [('🔄 استرداد', 'svrp_recover')],
                [('📤 إرسال رصيد', 'svrp_send')],
                [('👥 دعوة', 'svrp_invite')],
                [('💎 محفظتي', 'svrp_wallet')],
                [('🔙 ' + self.tr('back_btn', lang), 'svrp_back_main')]
            ])
            self.send_inline_message(message['chat']['id'], text, inline_btns)
        except Exception as e:
            logger.error(f"خطأ في عرض لوحة SVRP: {e}")
