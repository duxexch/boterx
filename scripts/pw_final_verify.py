# -*- coding: utf-8 -*-
"""Final comprehensive verification of all channels fixes."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append("PAGE: " + str(e)[:300]))

        # Login
        await page.goto("https://vex.deals/vex/admin/admin", wait_until="load", timeout=60000)
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)

        # Go to channels
        await page.goto("https://vex.deals/channels", wait_until="load", timeout=30000)
        await page.wait_for_timeout(6000)

        results = []

        # 1. Check RTL toggle
        t = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            return { lang: d.lang, on: d.toggleClasses(true), off: d.toggleClasses(false) };
        }""")
        ok = t['lang'] == 'ar' and '[-20px]' in t['on'] and 'translate-x-0' in t['off']
        results.append(('RTL toggle', ok, f"ON={t['on']}, OFF={t['off']}"))

        # 2. Check channels loaded
        ch_count = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            return Alpine.evaluate(root, '$data').channels.length;
        }""")
        results.append(('Channels loaded', ch_count == 37, f'{ch_count} channels'))

        # 3. Check OpenRouter in AI providers
        has_or = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            const or_prov = (d.aiProviders || []).find(p => p.name === 'openrouter');
            return or_prov ? or_prov.available : false;
        }""")
        results.append(('OpenRouter available', has_or, f'available={has_or}'))

        # 4. Screenshot channels
        await page.screenshot(path="final_1_channels.png", full_page=True)

        # 5. Check AI tab has OpenRouter
        await page.evaluate("() => { const root = document.querySelector('[x-data*=\"channelsApp\"]'); Alpine.evaluate(root, '$data').setTab('ai'); }")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="final_2_ai.png", full_page=True)

        has_or_tab = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            return (d.aiProviders || []).some(p => p.name === 'openrouter');
        }""")
        results.append(('OpenRouter in AI tab', has_or_tab, ''))

        # 6. Test channel modal open/close
        await page.evaluate("() => { const root = document.querySelector('[x-data*=\"channelsApp\"]'); Alpine.evaluate(root, '$data').setTab('campaigns'); }")
        await page.wait_for_timeout(1000)

        modal_test = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            if (d.channels.length > 0) {
                d.openChannelModal(d.channels[0]);
                return { opened: d.showChannelModal, ch: d.selectedChannel ? d.selectedChannel.title : null };
            }
            return { opened: false, ch: null };
        }""")
        results.append(('Modal opens', modal_test.get('opened'), f"channel={modal_test.get('ch')}"))

        await page.screenshot(path="final_3_modal.png", full_page=True)

        # 7. Test send message (dry - check function exists)
        send_fn = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            return typeof d.sendChannelMessage === 'function';
        }""")
        results.append(('sendChannelMessage exists', send_fn, ''))

        # 8. JS errors
        results.append(('No JS errors', len(errors) == 0, f'{len(errors)} errors'))
        for e in errors[:3]:
            print(f'  ERROR: {e}')

        await browser.close()

        # Print results
        print('\n=== VERIFICATION RESULTS ===')
        passed = 0
        for name, ok, detail in results:
            status = 'PASS' if ok else 'FAIL'
            if ok: passed += 1
            print(f'  [{status}] {name}: {detail}')
        print(f'\n  {passed}/{len(results)} passed')

asyncio.run(main())
