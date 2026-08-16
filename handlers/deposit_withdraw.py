"""
handlers/deposit_withdraw.py — Deposit & Withdraw flow handlers
Mixin extracted from comprehensive_bot.py. Preserves self.* access.
"""
import csv
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DepositWithdrawMixin:
    """Mixin for deposit/withdraw flow methods."""

    def create_deposit_request(self, message):
        """إنشاء طلب إيداع — شركات كأزرار inline"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        lang = user.get('language', 'ar')
        deposit_companies = self.get_companies('deposit')
        if not deposit_companies:
            self.send_message(message['chat']['id'], self.tr('no_companies', lang), self.main_keyboard(lang, message['from']['id']))
            return
        if lang == 'ar':
            title = self.tr('a0139_طلب_إيداع', lang)
        else:
            title = "💰 <b>Deposit Request</b>\n\nSelect company:"
        inline_btns = []
        for company in deposit_companies:
            icon = self.display_icon(company.get('icon'), '🏢')
            btn_text = f"{icon} {company['name']}"
            if company.get('details'):
                btn_text += f" — {company['details'][:30]}"
            inline_btns.append([{'text': btn_text, 'callback_data': f'dep_company_{company["id"]}'}])
        inline_btns.append([{'text': self.tr('main_menu', lang), 'callback_data': 'dep_cancel'}])
        self.send_inline_message(message['chat']['id'], title, inline_btns)

    def create_withdrawal_request(self, message):
        """إنشاء طلب سحب — شركات كأزرار inline"""
        user = self.find_user(message['from']['id'])
        if not user:
            return
        lang = user.get('language', 'ar')
        withdraw_companies = self.get_companies('withdraw')
        if not withdraw_companies:
            self.send_message(message['chat']['id'], self.tr('no_companies', lang), self.main_keyboard(lang, message['from']['id']))
            return
        if lang == 'ar':
            title = self.tr('a0140_طلب_سحب', lang)
        else:
            title = "💸 <b>Withdrawal Request</b>\n\nSelect company:"
        inline_btns = []
        for company in withdraw_companies:
            icon = self.display_icon(company.get('icon'), '🏢')
            btn_text = f"{icon} {company['name']}"
            if company.get('details'):
                btn_text += f" — {company['details'][:30]}"
            inline_btns.append([{'text': btn_text, 'callback_data': f'wd_company_{company["id"]}'}])
        inline_btns.append([{'text': self.tr('main_menu', lang), 'callback_data': 'wd_cancel'}])
        self.send_inline_message(message['chat']['id'], title, inline_btns)
