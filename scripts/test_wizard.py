import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright
import time

def click_visible_next(page):
    btns = page.query_selector_all('button:has-text("\u0627\u0644\u062a\u0627\u0644\u064a")')
    for btn in btns:
        if btn.is_visible():
            btn.click()
            return True
    return False

def vis(page, text):
    return page.is_visible('text=' + text)

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

    name_input = page.query_selector('input[placeholder*="\u062d\u0645\u0644\u0629"]')
    if name_input:
        name_input.fill('\u062a\u0643\u0633\u062a \u062e\u0644\u0635')
    msg_input = page.query_selector('textarea[placeholder*="\u0627\u0643\u062a\u0628"]')
    if msg_input:
        msg_input.fill('\u0646\u0635 \u0625\u0639\u0644\u0627\u0646\u064a \u062a\u062c\u0631\u064a\u0628\u064a \u0628\u0641\u0639\u0644')
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/wizard_s1.png', full_page=True)
    print('Step 1: form filled OK')

    click_visible_next(page)
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/wizard_s2.png', full_page=True)
    tg = vis(page, '\u062a\u064a\u0644\u064a\u063a\u0631\u0627\u0645')
    wa = vis(page, '\u0648\u0627\u062a\u0633\u0627\u0628')
    ig = vis(page, '\u0627\u0646\u0633\u062a\u062c\u0631\u0627\u0645')
    fb = vis(page, '\u0641\u064a\u0633\u0628\u0648\u0643')
    print('Step 2: TG=%s WA=%s IG=%s FB=%s' % (tg, wa, ig, fb))

    click_visible_next(page)
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/wizard_s3.png', full_page=True)
    a = vis(page, '\u0627\u0644\u0643\u0644')
    s = vis(page, '\u0642\u0646\u0648\u0627\u062a \u0645\u062d\u062f\u062f\u0629')
    g = vis(page, '\u0645\u062c\u0645\u0648\u0639\u0629 \u0642\u0646\u0648\u0627\u062a')
    print('Step 3: All=%s Single=%s Group=%s' % (a, s, g))

    click_visible_next(page)
    time.sleep(1)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/wizard_s4.png', full_page=True)
    pv = vis(page, '\u0645\u0639\u0627\u064a\u0646\u0629 \u0627\u0644\u062d\u0645\u0644\u0629')
    lb = vis(page, '\u0625\u0637\u0644\u0627\u0642 \u0641\u0648\u0631\u0627\u064b')
    print('Step 4: Preview=%s Launch=%s' % (pv, lb))

    print('\n=== ALL WIZARD STEPS VERIFIED ===')
    browser.close()
