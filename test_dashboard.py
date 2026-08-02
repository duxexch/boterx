#!/usr/bin/env python3
"""Test dashboard with proper .env loading"""

import os
from dotenv import load_dotenv
load_dotenv()

# Check env vars
admin_ids = [a.strip() for a in os.getenv('ADMIN_USER_IDS', '').split(',') if a.strip()]
password = os.getenv('DASHBOARD_PASSWORD', 'boterx_admin_2026')
print(f'Admin IDs: {admin_ids}')
print(f'Password: {password}')
print(f'7146701713 in admin_ids: {"7146701713" in admin_ids}')
print()

from dashboard.app import app

with app.test_client() as c:
    # Login
    r = c.post('/login', data={'admin_id': '7146701713', 'password': 'boterx_admin_2026'})
    loc = r.headers.get('Location', '')
    print(f'POST /login: {r.status_code} -> {loc}')
    
    # If login worked, test pages
    if r.status_code == 302 or '/dashboard' in loc:
        print('\n=== PAGES ===')
        pages = [
            '/dashboard', '/transactions', '/users', '/matching', '/svrp',
            '/trading', '/lottery', '/wheel', '/companies', '/payment-methods',
            '/apps', '/referrals', '/channels', '/bots', '/complaints',
            '/broadcast', '/settings', '/admins', '/themes',
            '/exchange-addresses', '/send-message', '/backup', '/statistics'
        ]
        for page in pages:
            r = c.get(page)
            ok = 'OK' if r.status_code == 200 else 'FAIL'
            print(f'  {page}: {r.status_code} {ok} ({len(r.data)} bytes)')
        
        print('\n=== APIs ===')
        apis = [
            '/api/stats', '/api/stats/charts', '/api/transactions',
            '/api/users', '/api/companies', '/api/payment-methods',
            '/api/payment-links', '/api/matching/active', '/api/matching/pending',
            '/api/matching/logs', '/api/svrp/wallets', '/api/svrp/requests',
            '/api/svrp/bonus-requests', '/api/svrp/promo-codes',
            '/api/trading/orders', '/api/lottery/rounds', '/api/wheel/rounds',
            '/api/apps', '/api/referrals', '/api/channels', '/api/bots',
            '/api/settings', '/api/button-labels', '/api/audit-log',
            '/api/recent-activity', '/api/complaints', '/api/exchange-addresses',
            '/api/admins', '/api/themes', '/api/backups',
            '/api/notifications-log', '/api/detailed-stats', '/api/support-data',
        ]
        for ep in apis:
            r = c.get(ep)
            ok = 'OK' if r.status_code == 200 else 'FAIL'
            try:
                data = r.get_json()
                size = len(str(data)) if data else 0
            except:
                size = len(r.data)
            print(f'  {ep}: {r.status_code} {ok} ({size} chars)')
    else:
        print('Login failed! Checking response...')
        print(r.data[:500].decode('utf-8'))
