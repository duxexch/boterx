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
    page.evaluate("localStorage.setItem('lang', 'en')")
    page.goto('https://vex.deals/channels', timeout=15000)
    time.sleep(5)

    # Find all buttons and their visibility
    btns = page.query_selector_all('button')
    for b in btns:
        t = b.inner_text().strip()[:60]
        v = b.is_visible()
        if t and ('campaign' in t.lower() or 'new' in t.lower() or 'next' in t.lower() or '\u2795' in t):
            print('btn: "%s" visible=%s' % (t, v))

    # Click new campaign
    page.click('button:has-text("New Campaign")', timeout=5000)
    time.sleep(2)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wiz_s1.png', full_page=True)

    # Check wizard step 1 content
    body = page.inner_text('body')
    lines = [l.strip() for l in body.split('\n') if l.strip()]
    # Find wizard-related lines
    for l in lines:
        if any(kw in l.lower() for kw in ['campaign', 'ad text', 'content', 'platform', 'audience', 'schedule', 'attach', 'promo', 'info', 'event', 'live', 'result', 'next', 'previous', 'generat']):
            print('  WIZ: %s' % l[:100])

    # Click Next using visible button with exact text
    nexts = page.query_selector_all('button')
    for n in nexts:
        t = n.inner_text().strip()
        v = n.is_visible()
        if 'Next' in t and v:
            print('Clicking visible Next button: %s' % t[:40])
            n.click()
            break
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wiz_s2.png', full_page=True)

    # Check what step we're on
    body2 = page.inner_text('body')
    lines2 = [l.strip() for l in body2.split('\n') if l.strip()]
    for l in lines2:
        if any(kw in l for kw in ['Telegram', 'WhatsApp', 'Instagram', 'Facebook', 'Website', 'Multiple', 'Choose', 'Platform']):
            print('  S2: %s' % l[:100])

    # Click Next again
    for n in page.query_selector_all('button'):
        t = n.inner_text().strip()
        if 'Next' in t and n.is_visible():
            n.click()
            break
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wiz_s3.png', full_page=True)

    body3 = page.inner_text('body')
    lines3 = [l.strip() for l in body3.split('\n') if l.strip()]
    for l in lines3:
        if any(kw in l for kw in ['All', 'Specific', 'Group', 'Choose', 'Select', 'Clear', 'Audience']):
            print('  S3: %s' % l[:100])

    # Click Next again
    for n in page.query_selector_all('button'):
        t = n.inner_text().strip()
        if 'Next' in t and n.is_visible():
            n.click()
            break
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wiz_s4.png', full_page=True)

    body4 = page.inner_text('body')
    lines4 = [l.strip() for l in body4.split('\n') if l.strip()]
    for l in lines4:
        if any(kw in l.lower() for kw in ['preview', 'priority', 'country', 'frequency', 'launch', 'schedule', 'egypt', 'saudi', 'once', 'daily', 'weekly']):
            print('  S4: %s' % l[:100])

    print('\n=== DONE ===')
    browser.close()
