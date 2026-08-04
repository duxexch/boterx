#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko, sys, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

tests = []

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 1. Dashboard login
code = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/login')
tests.append(('Dashboard login page', code == '200', f'HTTP {code}'))

# 2. Games list API
games = run('curl -s http://localhost:8080/api/games/list 2>&1')
tests.append(('Games list API', 'games' in games, games[:200]))

# 3. Games catalog CSV
catalog = run('cat /opt/bot/games_catalog.csv 2>&1')
game_count = catalog.count('GAME')
tests.append(('Games catalog', game_count >= 7, f'{game_count} games'))

# 4. available_for_games column
headers = run('head -1 /opt/bot/payment_methods.csv 2>&1')
tests.append(('available_for_games column', 'available_for_games' in headers, 'OK' if 'available_for_games' in headers else 'MISSING'))

# 5. game_balance column
users_headers = run('head -1 /opt/bot/users.csv 2>&1')
tests.append(('game_balance column', 'game_balance' in users_headers, 'OK' if 'game_balance' in users_headers else 'MISSING'))

# 6. New templates
for tpl in ['crash.html', 'mines.html', 'plinko.html']:
    exists = run(f'test -f /opt/bot/dashboard/templates/{tpl} && echo YES || echo NO')
    tests.append((f'Template {tpl}', exists == 'YES', exists))

# 7. WebApp routes
for route in ['crash', 'mines', 'plinko', 'aviator', 'games']:
    code = run(f'curl -s -o /dev/null -w "%{{http_code}}" http://localhost:8080/webapp/{route} 2>&1')
    tests.append((f'WebApp /{route}', code in ('200', '302'), f'HTTP {code}'))

# 8. Bot process
pid = run('pgrep -f comprehensive_bot | head -1')
tests.append(('Bot process', bool(pid), f'PID: {pid}'))

# 9. Dashboard service
status = run('systemctl is-active boterx-dashboard')
tests.append(('Dashboard service', status == 'active', status))

# 10. Bot service
status = run('systemctl is-active boterx')
tests.append(('Bot service', status == 'active', status))

# 11. Check for errors in bot logs
bot_logs = run('journalctl -u boterx --no-pager -n 30 2>&1')
has_errors = any(x in bot_logs for x in ['Traceback', 'Error:', 'Exception:', 'NameError', 'SyntaxError'])
tests.append(('Bot logs (no errors)', not has_errors, 'ERRORS FOUND' if has_errors else 'CLEAN'))

# 12. Check dashboard logs
dash_logs = run('journalctl -u boterx-dashboard --no-pager -n 30 2>&1')
has_dash_errors = any(x in dash_logs for x in ['Traceback', 'Error:', 'Exception:'])
tests.append(('Dashboard logs (no errors)', not has_dash_errors, 'ERRORS FOUND' if has_dash_errors else 'CLEAN'))

# 13. i18n files
i18n_count = run('ls /opt/bot/i18n/*.json 2>/dev/null | wc -l')
tests.append(('i18n files (17)', i18n_count.strip() == '17', f'{i18n_count.strip()} files'))

# 14. Game engine module
ge = run('cd /opt/bot && python3 -c "import game_engine; print(\'OK\')" 2>&1')
tests.append(('game_engine import', 'OK' in ge, ge[:100]))

# 15. Dashboard app module
app = run('cd /opt/bot && python3 -c "import py_compile; py_compile.compile(\'dashboard/app.py\', doraise=True); print(\'OK\')" 2>&1')
tests.append(('dashboard/app.py syntax', 'OK' in app, app[:100]))

# Print report
print('=' * 60)
print('           SERVER TEST REPORT')
print('=' * 60)
passed = 0
for name, ok, detail in tests:
    icon = '\u2705' if ok else '\u274c'
    print(f'{icon} {name}: {detail}')
    if ok:
        passed += 1
print(f'\nTotal: {passed}/{len(tests)} passed')
print('=' * 60)

ssh.close()
