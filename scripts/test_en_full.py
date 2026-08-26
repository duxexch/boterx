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

    # Click New Campaign
    btns = page.query_selector_all('button')
    for b in btns:
        t = b.inner_text().strip()
        if 'New Campaign' in t:
            b.click()
            break
    time.sleep(2)

    # Check wizard-specific elements
    checks = [
        ('Wizard title', 'Create Ad Campaign'),
        ('Step Content', 'Content'),
        ('Step Platform', 'Platform'),
        ('Step Audience', 'Audience'),
        ('Step Schedule', 'Schedule'),
        ('Campaign Name', 'Campaign Name'),
        ('Ad Text', 'Ad Text'),
        ('Promo', 'Promo/Offer'),
        ('Info', 'Info'),
        ('Event', 'Event'),
        ('Live', 'Live'),
        ('Result', 'Result'),
        ('Attachments', 'Attachments'),
        ('AI Generate', 'AI Generate'),
        ('Next', 'Next'),
    ]
    for label, text in checks:
        el = page.query_selector('text="' + text + '"')
        vis = el.is_visible() if el else False
        print('%s: %s' % (label, 'OK' if vis else 'MISSING'))

    # Navigate to step 2
    name = page.query_selector('input[placeholder*="Campaign"]')
    if name: name.fill('test')
    msg = page.query_selector('textarea')
    if msg: msg.fill('test')
    time.sleep(1)
    nexts = page.query_selector_all('button:has-text("Next")')
    for n in nexts:
        if n.is_visible():
            n.click()
            break
    time.sleep(1)

    s2_checks = [
        ('Telegram', 'Telegram'),
        ('WhatsApp', 'WhatsApp'),
        ('Instagram', 'Instagram'),
        ('Facebook', 'Facebook'),
        ('Website', 'Website'),
        ('Multiple', 'Multiple'),
        ('Channels+Groups', 'Channels + Groups'),
        ('API+Contacts', 'API + Contacts'),
        ('Web Notifications', 'Web Notifications'),
    ]
    for label, text in s2_checks:
        el = page.query_selector('text="' + text + '"')
        vis = el.is_visible() if el else False
        print('%s: %s' % (label, 'OK' if vis else 'MISSING'))

    # Step 3
    nexts = page.query_selector_all('button:has-text("Next")')
    for n in nexts:
        if n.is_visible():
            n.click()
            break
    time.sleep(1)

    s3_checks = [
        ('All', 'All'),
        ('Specific channels', 'Specific channels'),
        ('Channel group', 'Channel group'),
        ('Choose Channels', 'Choose Channels'),
        ('Select All', 'Select All'),
        ('Clear All', 'Clear All'),
    ]
    for label, text in s3_checks:
        el = page.query_selector('text="' + text + '"')
        vis = el.is_visible() if el else False
        print('%s: %s' % (label, 'OK' if vis else 'MISSING'))

    # Step 4
    nexts = page.query_selector_all('button:has-text("Next")')
    for n in nexts:
        if n.is_visible():
            n.click()
            break
    time.sleep(1)

    s4_checks = [
        ('Preview', 'Campaign Preview'),
        ('Priority', 'Priority'),
        ('Country', 'Country'),
        ('Frequency', 'Frequency'),
        ('Launch Now', 'Launch Now'),
        ('Normal', 'Normal'),
        ('High', 'High'),
        ('Urgent', 'Urgent'),
        ('Once', 'Once'),
        ('Daily', 'Daily'),
        ('Weekly', 'Weekly'),
        ('Egypt', 'Egypt'),
        ('Saudi Arabia', 'Saudi Arabia'),
        ('UAE', 'UAE'),
        ('Jordan', 'Jordan'),
        ('Morocco', 'Morocco'),
        ('Algeria', 'Algeria'),
    ]
    for label, text in s4_checks:
        el = page.query_selector('text="' + text + '"')
        vis = el.is_visible() if el else False
        print('%s: %s' % (label, 'OK' if vis else 'MISSING'))

    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/en_wizard_step4.png', full_page=True)
    print('\n=== VERIFICATION COMPLETE ===')
    browser.close()
