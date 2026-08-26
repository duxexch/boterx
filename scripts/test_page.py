import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://vex.deals/channels')
    time.sleep(3)

    # Set token directly via localStorage
    token = 'eyJzY29wZSI6ImRlY2siLCJleHAiOjAsIm5vbmNlIjoibVFxSFp1aWdLTjVIIiwicGVybWFuZW50Ijp0cnVlfQ.9575f071aa4c3fb15a9c6c5fce498148e2a53749aa1ea6d3bb05f205cf7faf51'
    page.evaluate(f'localStorage.setItem("admin_token", "{token}")')
    page.goto('https://vex.deals/channels')
    time.sleep(5)
    page.screenshot(path='C:/Users/gnz/AppData/Local/Temp/after_token.png', full_page=True)
    
    body = page.inner_text('body')
    print('Body (first 800):', body[:800])
    
    btns = page.query_selector_all('button')
    print(f'Total buttons: {len(btns)}')
    for b in btns[:20]:
        t = b.inner_text().strip()
        if t:
            print(f'  btn: {t}')
    
    browser.close()
