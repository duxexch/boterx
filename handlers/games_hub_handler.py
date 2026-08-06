"""
handlers/games_hub_handler.py — Games hub, wheel, lottery, snatch handlers
Mixin extracted from comprehensive_bot.py.
"""
import logging

logger = logging.getLogger(__name__)


class GamesHubHandlerMixin:
    """Mixin for games hub display, wheel, lottery, snatch webapp data."""

    def show_games_hub(self, user_id, lang, currency):
        """عرض مركز الألعاب"""
        try:
            # Get balance from game engine
            from game_engine import GameManager
            if hasattr(self, '_gm') and self._gm:
                balance = self._gm.get_balance(user_id)
            else:
                balance = 0

            base_url = self.get_setting('dashboard_url') or 'https://vex.deals'
            games_url = f"{base_url}/webapp/games?uid={user_id}&lang={lang}&currency={currency}"

            # Send games hub as URL button (not WebApp — requires BotFather domain verification)
            kb = {'inline_keyboard': [[
                {'text': '🎮 العاب VEX', 'url': games_url}
            ]]}
            self.api_call('sendMessage', {
                'chat_id': user_id,
                'text': f"🎮 <b>VEX Games</b>\n\n💰 رصيدك: <code>{balance}</code> {currency}\n\nاضغط للعب:",
                'parse_mode': 'HTML',
                'reply_markup': json.dumps(kb)
            })
        except Exception as e:
            logger.error(f"خطأ في عرض مركز الألعاب: {e}")
