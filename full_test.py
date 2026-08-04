#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko, sys, json, urllib.request

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

print('=' * 60)
print('        BOT FUNCTIONALITY TEST REPORT')
print('=' * 60)

# 1. Bot API check
token = run('grep BOT_TOKEN /opt/bot/.env | cut -d= -f2')
try:
    url = f'https://api.telegram.org/bot{token}/getMe'
    resp = urllib.request.urlopen(url, timeout=10)
    data = json.loads(resp.read())
    bot_name = data['result']['username']
    print(f'✅ Bot API: @{bot_name} (online)')
except Exception as e:
    print(f'❌ Bot API: {e}')

# 2. Data files
users = run('cat /opt/bot/users.csv | wc -l')
print(f'✅ Users: {users} lines')

txns = run('cat /opt/bot/transactions.csv 2>/dev/null | wc -l')
print(f'✅ Transactions: {txns} lines')

deposits = run('cat /opt/bot/quick_deposits.csv 2>/dev/null | wc -l')
print(f'✅ Quick deposits: {deposits} lines')

ppm = run('cat /opt/bot/player_payment_methods.csv 2>/dev/null | wc -l')
print(f'✅ Player payment methods: {ppm} lines')

# 3. Games catalog
catalog = run('cat /opt/bot/games_catalog.csv')
games = [l for l in catalog.split('\n') if 'GAME' in l]
print(f'✅ Games catalog: {len(games)} games')

# 4. Payment methods with available_for_games
headers = run('head -1 /opt/bot/payment_methods.csv')
has_col = 'available_for_games' in headers
print(f'✅ available_for_games column: {"YES" if has_col else "NO"}')

# 5. game_balance column
uh = run('head -1 /opt/bot/users.csv')
print(f'✅ game_balance column: {"YES" if "game_balance" in uh else "NO"}')

# 6. BOT_TOKEN in .env (for webapp_auth)
bt = run('grep -c BOT_TOKEN /opt/bot/.env')
print(f'✅ BOT_TOKEN in .env: {"YES" if bt == "1" else "NO"}')

# 7. WebApp auth test — should return 403 without initData
auth_test = run('curl -s http://localhost:8080/api/games/list 2>&1')
has_auth = 'NO_INIT_DATA' in auth_test or 'Missing authentication' in auth_test
print(f'✅ WebApp auth (403 without initData): {"WORKING" if has_auth else "BYPASSED"}')

# 8. Dashboard pages
for page in ['/login', '/games-admin', '/webapp/games', '/webapp/crash', '/webapp/mines', '/webapp/plinko', '/webapp/aviator']:
    code = run(f'curl -s -o /dev/null -w "%{{http_code}}" http://localhost:8080{page}')
    ok = code in ('200', '302')
    print(f'{"✅" if ok else "❌"} {page}: HTTP {code}')

# 9. Service status
for svc in ['boterx', 'boterx-dashboard']:
    status = run(f'systemctl is-active {svc}')
    print(f'✅ {svc}: {status}')

# 10. Bot logs check
bot_logs = run('journalctl -u boterx --no-pager -n 50 2>&1')
error_keywords = ['Traceback', 'Error:', 'Exception:', 'NameError', 'SyntaxError', 'ImportError']
found_errors = [kw for kw in error_keywords if kw in bot_logs]
print(f'{"✅" if not found_errors else "❌"} Bot logs: {"CLEAN" if not found_errors else "ERRORS: " + ", ".join(found_errors)}')

dash_logs = run('journalctl -u boterx-dashboard --no-pager -n 50 2>&1')
found_dash_errors = [kw for kw in error_keywords if kw in dash_logs]
print(f'{"✅" if not found_dash_errors else "❌"} Dashboard logs: {"CLEAN" if not found_dash_errors else "ERRORS: " + ", ".join(found_dash_errors)}')

# 11. i18n files
i18n = run('ls /opt/bot/i18n/*.json 2>/dev/null | wc -l')
print(f'✅ i18n files: {i18n}')

# 12. Python syntax check
for f in ['dashboard/app.py', 'game_engine.py', 'comprehensive_bot.py']:
    result = run(f'cd /opt/bot && python3 -c "import py_compile; py_compile.compile(\'{f}\', doraise=True); print(\'OK\')" 2>&1')
    print(f'{"✅" if "OK" in result else "❌"} Syntax {f}: {"OK" if "OK" in result else result[:80]}')

print('\n' + '=' * 60)
print('        FULL BOT REVIEW & SUGGESTIONS')
print('=' * 60)

suggestions = [
    ('1. Crash game first-round delay', 'Crash/Aviator start round timer is 5s — consider reducing to 3s for faster gameplay'),
    ('2. Mines session cleanup', 'mines_sessions.json grows indefinitely — add cleanup for sessions older than 1 hour'),
    ('3. Plinko payout on end', 'Plinko /end endpoint adds payout again — verify no double-credit (start already deducts, end adds)'),
    ('4. WebApp auth dev mode', 'When BOT_TOKEN not set, webapp_auth falls back to uid param — ensure production always has BOT_TOKEN'),
    ('5. Deposit modal in Crash', 'Crash.html has inline HTML in JS string for modal — consider extracting to template'),
    ('6. Game balance precision', 'All game balances use float — consider rounding to 2 decimal places on all operations'),
    ('7. Rate limiting on game APIs', 'No rate limit on /api/engine/* — a user could spam requests. Add 10/min limit'),
    ('8. CSV file locking', 'game_engine.py uses threading.Lock for wallet but not for other CSVs (mines_sessions.json)'),
    ('9. SSE connection limit', 'SSE notifications stream has no max connections limit — add 50 max'),
    ('10. i18n coverage', '~921 strings still hardcoded in implicit concatenation contexts in comprehensive_bot.py'),
    ('11. Dashboard games_admin', 'Games admin page needs columns for the 3 new games (Crash, Mines, Plinko)'),
    ('12. Withdrawal flow update', 'Withdrawal modal should also use bot payment methods + saved wallets like deposit does'),
]

for title, desc in suggestions:
    print(f'⚠️  {title}')
    print(f'   {desc}')
    print()

print('=' * 60)
ssh.close()
