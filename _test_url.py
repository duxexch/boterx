#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import urllib.request, json, ssl

# Test the WebApp URL from outside
url = 'https://69.169.108.197.sslip.io/webapp/games?uid=8038414871&lang=ar&currency=EGP'
try:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    html = resp.read().decode('utf-8', errors='replace')
    print(f'HTTP {resp.status}')
    print(f'Content length: {len(html)}')
    # Check if the page has games JS
    has_apiFetch = 'apiFetch' in html
    has_uid = '8038414871' in html
    print(f'Has apiFetch: {has_apiFetch}')
    print(f'Has uid: {has_uid}')
    print(f'First 200 chars: {html[:200]}')
except Exception as e:
    print(f'ERROR: {e}')

# Also test the SSL certificate
import socket
try:
    sock = socket.create_connection(('69.169.108.197.sslip.io', 443), timeout=10)
    ctx = ssl.create_default_context()
    ssock = ctx.wrap_socket(sock, server_hostname='69.169.108.197.sslip.io')
    cert = ssock.getpeercert()
    print(f'\nSSL cert subject: {cert.get("subject", "unknown")}')
    print(f'SSL cert issuer: {cert.get("issuer", "unknown")}')
    ssock.close()
except Exception as e:
    print(f'\nSSL ERROR: {e}')
