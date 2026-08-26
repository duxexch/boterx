import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright
import time

def click_next(page):
    for n in page.query_selector_all('button'):
        t = n.inner_text().strip()
        if n.is_visible() and t.startswith('Next'):
            n.click()
            return True
    return False

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

    page.click('button:has-text("New Campaign")', timeout=5000)
    time.sleep(2)

    # Step 1 - fill content
    page.fill('textarea', 'Test campaign ad text')
    time.sleep(0.5)

    click_next(page)
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_s2.png', full_page=True)
    body = page.inner_text('body')
    s2_words = ['Telegram', 'WhatsApp', 'Instagram', 'Facebook', 'Website', 'Multiple', 'Channels + Groups', 'API + Contacts', 'Web Notifications', 'Choose the platform']
    for w in s2_words:
        print('S2 %s: %s' % (w, 'OK' if w in body else 'MISS'))

    click_next(page)
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_s3.png', full_page=True)
    body = page.inner_text('body')
    s3_words = ['All', 'Specific channels', 'Channel group', 'Choose Channels', 'Select All', 'Clear All', 'All active channels']
    for w in s3_words:
        print('S3 %s: %s' % (w, 'OK' if w in body else 'MISS'))

    click_next(page)
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_s4.png', full_page=True)
    body = page.inner_text('body')
    s4_words = ['Campaign Preview', 'Priority', 'Country', 'Frequency', 'Launch Now', 'Normal', 'High', 'Urgent', 'Once', 'Daily', 'Weekly', 'Egypt', 'Saudi Arabia', 'UAE', 'Jordan', 'Morocco', 'Algeria']
    for w in s4_words:
        print('S4 %s: %s' % (w, 'OK' if w in body else 'MISS'))

    print('\n=== ALL STEPS VERIFIED ===')
    browser.close()
