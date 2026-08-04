#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko, json, urllib.request

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

token = run('grep BOT_TOKEN /opt/bot/.env | cut -d= -f2')

# Test 1: Send a simple inline button (callback_data) — should work
url = f'https://api.telegram.org/bot{token}/sendMessage'
data = {
    'chat_id': 7146701713,
    'text': 'اختبار: زر عادي',
    'reply_markup': json.dumps({'inline_keyboard': [[{'text': '🎮 اختبار', 'callback_data': 'test_123'}]]})
}
req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'))
req.add_header('Content-Type', 'application/json')
resp = urllib.request.urlopen(req, timeout=10)
result1 = json.loads(resp.read())
print('Test 1 (callback button):', 'OK' if result1.get('ok') else result1.get('description', 'FAIL'))

# Test 2: Send a web_app button — this is what show_games_hub does
games_url = 'https://69.169.108.197.sslip.io/webapp/games?uid=7146701713&lang=ar&currency=SAR'
data2 = {
    'chat_id': 7146701713,
    'text': 'اختبار: زر WebApp',
    'reply_markup': {
        'inline_keyboard': [
            [{'text': '🎮 افتح الألعاب', 'web_app': {'url': games_url}}]
        ]
    }
}
req2 = urllib.request.Request(url, data=json.dumps(data2).encode('utf-8'))
req2.add_header('Content-Type', 'application/json')
try:
    resp2 = urllib.request.urlopen(req2, timeout=10)
    result2 = json.loads(resp2.read())
    print('Test 2 (web_app button):', 'OK' if result2.get('ok') else f'FAIL: {result2.get("description", "unknown")}')
except Exception as e:
    print('Test 2 (web_app button): ERROR:', str(e))

# Test 3: Try with reply_markup as string (like the old broken code)
data3 = {
    'chat_id': 7146701713,
    'text': 'اختبار: زر WebApp (string markup)',
    'reply_markup': json.dumps({'inline_keyboard': [[{'text': '🎮 افتح الألعاب', 'web_app': {'url': games_url}}]]})
}
req3 = urllib.request.Request(url, data=json.dumps(data3).encode('utf-8'))
req3.add_header('Content-Type', 'application/json')
try:
    resp3 = urllib.request.urlopen(req3, timeout=10)
    result3 = json.loads(resp3.read())
    print('Test 3 (string markup):', 'OK' if result3.get('ok') else f'FAIL: {result3.get("description", "unknown")}')
except Exception as e:
    print('Test 3 (string markup): ERROR:', str(e))

ssh.close()
