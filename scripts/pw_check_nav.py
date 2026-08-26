# -*- coding: utf-8 -*-
"""Verify AI Agent system on channels page."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright

TOKEN = 'eyJzY29wZSI6ImRlY2siLCJleHAiOjAsIm5vbmNlIjoibVFxSFp1aWdLTjVIIiwicGVybWFuZW50Ijp0cnVlfQ.9575f071aa4c3fb15a9c6c5fce498148e2a53749aa1ea6d3bb05f205cf7faf51'

with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    page = br.new_page()
    page.goto('https://vex.deals', wait_until='networkidle')
    page.evaluate("""(token) => {
        localStorage.setItem('admin_token', token);
        localStorage.setItem('admin_session', JSON.stringify({token, role:'superadmin', permissions:['superadmin']}));
    }""", TOKEN)
    page.goto('https://vex.deals', wait_until='networkidle')
    page.wait_for_timeout(3000)
    
    url = page.url
    print(f'URL: {url}')
    
    # Check if we need to log in via the login page
    html = page.content()
    has_admin = 'channels' in html.lower() or 'admin' in html.lower()
    print(f'Has admin nav: {has_admin}')
    
    # Try going to the admin dashboard directly
    page.goto('https://vex.deals/#channels', wait_until='networkidle')
    page.wait_for_timeout(2000)
    url2 = page.url
    print(f'After nav URL: {url2}')
    
    # Get all buttons text
    btns = page.locator('button').all()
    for b in btns[:30]:
        try:
            t = b.inner_text().strip()[:60]
            if t:
                print(f'  btn: {t}')
        except:
            pass
    
    br.close()
