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

    # Set English and go to channels
    page.evaluate("localStorage.setItem('lang', 'en')")
    page.goto('https://vex.deals/channels', timeout=15000)
    time.sleep(5)

    # Click New Campaign
    btns = page.query_selector_all('button')
    for b in btns:
        t = b.inner_text().strip()
        if 'New Campaign' in t or '\u2795' in t:
            b.click()
            break
    time.sleep(2)

    body = page.inner_text('body')
    lines = [l.strip() for l in body.split('\n') if l.strip()]
    for l in lines[:60]:
        print(l[:120])

    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wizard_final.png', full_page=True)
    print('\n=== WIZARD ENGLISH VERIFICATION ===')
    browser.close()
