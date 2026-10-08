import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright
import time

def vis(page, text):
    return page.is_visible('text=' + text)

def click_visible(page, text):
    btns = page.query_selector_all('button:has-text("' + text + '")')
    for b in btns:
        if b.is_visible():
            b.click()
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
    page.goto('https://vex.deals/channels', timeout=15000)
    time.sleep(4)

    # ===== ARABIC MODE =====
    print('=== ARABIC MODE ===')
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/ar_campaigns.png', full_page=True)
    print('AR: حملة جديدة button:', vis(page, '\u062d\u0645\u0644\u0629 \u062c\u062f\u064a\u062f\u0629'))
    print('AR: KPIs:', vis(page, '\u0625\u062c\u0645\u0627\u0644\u064a') and vis(page, '\u0646\u0634\u0637\u0629') and vis(page, '\u0645\u0643\u062a\u0645\u0644\u0629'))

    # Click new campaign
    click_visible(page, '\u062d\u0645\u0644\u0629 \u062c\u062f\u064a\u062f\u0629')
    time.sleep(2)

    # Check wizard in Arabic
    print('AR: wizard title:', vis(page, '\u0625\u0646\u0634\u0627\u0621 \u062d\u0645\u0644\u0629 \u0625\u0639\u0644\u0627\u0646\u064a\u0629'))
    print('AR: step content:', vis(page, '\u0627\u0644\u0645\u062d\u062a\u0648\u0649'))
    print('AR: step platform:', vis(page, '\u0627\u0644\u0645\u0646\u0635\u0629'))
    print('AR: step audience:', vis(page, '\u0627\u0644\u062c\u0645\u0647\u0648\u0631'))
    print('AR: step schedule:', vis(page, '\u0627\u0644\u062c\u062f\u0648\u0644\u0629'))
    print('AR: campaign name:', vis(page, '\u0627\u0633\u0645 \u0627\u0644\u062d\u0645\u0644\u0629'))
    print('AR: ad text:', vis(page, '\u0646\u0635 \u0627\u0644\u0625\u0639\u0644\u0627\u0646'))
    print('AR: promo button:', vis(page, '\u0639\u0631\u0636/\u0628\u0631\u0648\u0645\u0648'))
    print('AR: attachments:', vis(page, '\u0627\u0644\u0645\u0631\u0641\u0642\u0627\u062a'))
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/ar_wizard_s1.png', full_page=True)

    # Fill and navigate to step 2
    name = page.query_selector('input[placeholder*="\u062d\u0645\u0644\u0629"]')
    if name: name.fill('\u062a\u0643\u0633\u062a')
    msg = page.query_selector('textarea[placeholder*="\u0627\u0643\u062a\u0628"]')
    if msg: msg.fill('\u0646\u0635 \u062a\u062c\u0631\u064a\u0628\u064a')
    time.sleep(1)
    click_visible(page, '\u0627\u0644\u062a\u0627\u0644\u064a')
    time.sleep(1)
    print('AR: telegram:', vis(page, '\u062a\u064a\u0644\u064a\u063a\u0631\u0627\u0645'))
    print('AR: whatsapp:', vis(page, '\u0648\u0627\u062a\u0633\u0627\u0628'))
    print('AR: instagram:', vis(page, '\u0627\u0646\u0633\u062a\u062c\u0631\u0627\u0645'))
    print('AR: facebook:', vis(page, '\u0641\u064a\u0633\u0628\u0648\u0643'))
    print('AR: website:', vis(page, '\u0627\u0644\u0645\u0648\u0642\u0639'))
    print('AR: multiple:', vis(page, '\u0645\u062a\u0639\u062f\u062f'))
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/ar_wizard_s2.png', full_page=True)

    # ===== ENGLISH MODE =====
    print('\n=== SWITCHING TO ENGLISH ===')
    page.evaluate("localStorage.setItem('lang', 'en')")
    page.goto('https://vex.deals/channels', timeout=15000)
    time.sleep(5)

    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_campaigns.png', full_page=True)
    print('EN: new campaign btn:', vis(page, '\u2795 New Campaign') or vis(page, '\u2795 \u062d\u0645\u0644\u0629 \u062c\u062f\u064a\u062f\u0629'))

    # Click new campaign
    click_visible(page, 'New Campaign')
    if not click_visible(page, '\u062d\u0645\u0644\u0629 \u062c\u062f\u064a\u062f\u0629'):
        pass
    time.sleep(2)

    # Check wizard in English
    print('EN: wizard title:', vis(page, 'Create Ad Campaign'))
    print('EN: step content:', vis(page, 'Content'))
    print('EN: step platform:', vis(page, 'Platform'))
    print('EN: step audience:', vis(page, 'Audience'))
    print('EN: step schedule:', vis(page, 'Schedule'))
    print('EN: campaign name:', vis(page, 'Campaign Name'))
    print('EN: ad text:', vis(page, 'Ad Text'))
    print('EN: promo:', vis(page, 'Promo/Offer'))
    print('EN: attachments:', vis(page, 'Attachments'))
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wizard_s1.png', full_page=True)

    # Navigate to step 2
    name = page.query_selector('input[placeholder*="Campaign"]')
    if name: name.fill('Test campaign')
    msg = page.query_selector('textarea')
    if msg: msg.fill('Test ad text')
    time.sleep(1)
    click_visible(page, 'Next')
    time.sleep(1)
    print('EN: telegram:', vis(page, 'Telegram'))
    print('EN: whatsapp:', vis(page, 'WhatsApp'))
    print('EN: instagram:', vis(page, 'Instagram'))
    print('EN: facebook:', vis(page, 'Facebook'))
    print('EN: website:', vis(page, 'Website'))
    print('EN: multiple:', vis(page, 'Multiple'))
    print('EN: channels groups:', vis(page, 'Channels + Groups'))
    print('EN: api contacts:', vis(page, 'API + Contacts'))
    print('EN: web notifications:', vis(page, 'Web Notifications'))
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wizard_s2.png', full_page=True)

    # Step 3
    click_visible(page, 'Next')
    time.sleep(1)
    print('EN: all:', vis(page, 'All'))
    print('EN: specific:', vis(page, 'Specific channels'))
    print('EN: group:', vis(page, 'Channel group'))
    print('EN: choose channels:', vis(page, 'Choose Channels'))
    print('EN: select all:', vis(page, 'Select All'))
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wizard_s3.png', full_page=True)

    # Step 4
    click_visible(page, 'Next')
    time.sleep(1)
    print('EN: preview:', vis(page, 'Campaign Preview'))
    print('EN: priority:', vis(page, 'Priority'))
    print('EN: country:', vis(page, 'Country'))
    print('EN: frequency:', vis(page, 'Frequency'))
    print('EN: launch now:', vis(page, 'Launch Now'))
    print('EN: egypt:', vis(page, 'Egypt'))
    print('EN: saudi:', vis(page, 'Saudi Arabia'))
    print('EN: once:', vis(page, 'Once'))
    print('EN: daily:', vis(page, 'Daily'))
    print('EN: weekly:', vis(page, 'Weekly'))
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wizard_s4.png', full_page=True)

    print('\n=== TRANSLATION VERIFICATION COMPLETE ===')
    browser.close()
