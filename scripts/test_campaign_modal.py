import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://vex.deals/vex/admin/admin')
    time.sleep(3)

    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/login_page.png', full_page=True)

    page.fill('input[name="admin_id"]', '7146701713')
    page.fill('input[name="password"]', 'Vex-LN36X_SG3bv-UNooqkME')
    page.click('button[type="submit"]')
    time.sleep(5)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/after_login.png', full_page=True)
    
    cur = page.url
    print('After login URL:', cur)
    
    if 'dashboard' in cur or 'channels' in cur:
        page.goto('https://vex.deals/channels')
        time.sleep(4)
    
    btns = page.query_selector_all('button')
    cmp_btn = None
    for b in btns:
        t = b.inner_text().strip()
        if '\u062d\u0645\u0644\u0629' in t:
            cmp_btn = b
            break

    if cmp_btn:
        cmp_btn.click()
        time.sleep(2)

        modal = page.query_selector('text=\u0625\u0646\u0634\u0627\u0621 \u062d\u0645\u0644\u0629 \u0625\u0639\u0644\u0627\u0646\u064a\u0629')
        print('Modal visible:', modal is not None and modal.is_visible())

        promo = page.query_selector('button:has-text("\u0639\u0631\u0636/\u0628\u0631\u0648\u0645\u0648")')
        print('Promo button:', promo is not None)
        info = page.query_selector('button:has-text("\u0645\u0639\u0644\u0648\u0645\u0629")')
        print('Info button:', info is not None)

        placeholders = page.query_selector('button:has-text("{company_name}")')
        print('Placeholder buttons:', placeholders is not None)

        ch_sel = page.query_selector('text=\u0627\u062e\u062a\u0631 \u0627\u0644\u0642\u0646\u0627\u0648\u062a')
        print('Channel selector exists:', ch_sel is not None)
        gr_sel = page.query_selector('text=\u0627\u062e\u062a\u0631 \u0627\u0644\u0645\u062c\u0645\u0648\u0639\u0627\u062a')
        print('Group selector exists:', gr_sel is not None)
        wa_sec = page.query_selector('text=\u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0648\u0627\u062a\u0633\u0627\u0628')
        print('WhatsApp section exists:', wa_sec is not None)

        page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/campaign_modal.png', full_page=True)
        print('Screenshot saved')
    else:
        print('Campaign button NOT found')
        for b in btns[:15]:
            t = b.inner_text().strip()
            if t:
                print(f'  btn: {t[:50]}')
    browser.close()
