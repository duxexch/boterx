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

    # Check AR mode
    print('=== AR MODE ===')
    # Get all visible text
    body = page.inner_text('body')
    lines = [l.strip() for l in body.split('\n') if l.strip()]
    for l in lines[:80]:
        print(l[:100])

    # Open wizard and check
    btns = page.query_selector_all('button')
    for b in btns:
        t = b.inner_text().strip()
        if '\u062d\u0645\u0644\u0629' in t and '\u062c\u062f\u064a\u062f\u0629' in t:
            b.click()
            break
    time.sleep(2)
    body2 = page.inner_text('body')
    lines2 = [l.strip() for l in body2.split('\n') if l.strip()]
    for l in lines2[:40]:
        print(l[:100])

    # Now switch to EN
    page.evaluate("localStorage.setItem('lang', 'en')")
    page.goto('https://vex.deals/channels', timeout=15000)
    time.sleep(5)
    print('\n=== EN MODE ===')
    body3 = page.inner_text('body')
    lines3 = [l.strip() for l in body3.split('\n') if l.strip()]
    for l in lines3[:80]:
        print(l[:100])

    browser.close()
