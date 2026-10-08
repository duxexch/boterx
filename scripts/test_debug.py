import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://vex.deals/vex/admin/admin', timeout=15000)
    time.sleep(2)
    page.fill('input[name="admin_id"]', '7146701713')
    page.fill('input[name="password"]', 'Vex-LN36X_SG3bv-UNooqkME')
    page.click('button[type="submit"]')
    time.sleep(4)
    page.goto('https://vex.deals/channels', timeout=15000)
    time.sleep(4)

    page.click('text=\u062d\u0645\u0644\u0629 \u062c\u062f\u064a\u062f\u0629', timeout=5000)
    time.sleep(2)

    # Check what's visible
    body = page.inner_text('body')
    lines = [l.strip() for l in body.split('\n') if l.strip()]
    for l in lines[:60]:
        print(l[:80])

    # Check inputs
    inputs = page.query_selector_all('input, textarea, select')
    for inp in inputs:
        vis = inp.is_visible()
        tag = inp.evaluate('el => el.tagName')
        ph = inp.get_attribute('placeholder') or ''
        tp = inp.get_attribute('type') or ''
        print(f'  {tag} type={tp} ph={ph[:40]} visible={vis}')

    browser.close()
