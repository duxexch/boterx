# -*- coding: utf-8 -*-
"""Final verification of all channels fixes."""
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
        await page.wait_for_timeout(5000)

        # Check state
        state = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            if (!root) return {error: 'no root'};
            const d = Alpine.evaluate(root, '$data');
            return {
                lang: d.lang,
                channels: (d.channels || []).length,
                tab: d.tab,
                filteredChannels: (d.filteredChannels || []).length,
                hasToggleClasses: typeof d.toggleClasses === 'function',
                hasLang: d.lang !== undefined,
            };
        }""")
        print(f'State: {json.dumps(state, indent=1)}')

        # Screenshot the compact cards
        await page.screenshot(path="verify_1_compact.png", full_page=True)

        # Check RTL: switch to Arabic, check toggle classes
        is_rtl = state.get('lang') == 'ar'
        print(f'RTL mode: {is_rtl}')

        # Test toggleClasses in RTL
        toggle_test = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            return {
                on: d.toggleClasses(true),
                off: d.toggleClasses(false),
                lang: d.lang
            };
        }""")
        print(f'Toggle classes: ON={toggle_test["on"]}, OFF={toggle_test["off"]}')

        # Check if OpenRouter shows in AI providers
        ai_state = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            return {
                providers: d.aiProviders || [],
                agents: (d.aiAgents || []).length
            };
        }""")
        print(f'AI: {json.dumps(ai_state, indent=1)}')

        # Click AI tab and check OpenRouter
        await page.click('button:has-text("AI")')
        await page.wait_for_timeout(3000)
        await page.screenshot(path="verify_2_ai.png", full_page=True)

        # Check if OpenRouter provider is now visible
        has_or = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            return (d.aiProviders || []).some(p => p.name === 'openrouter');
        }""")
        print(f'OpenRouter in providers: {has_or}')

        # Click on a channel card to open modal
        await page.click('button:has-text("Channels")')
        await page.wait_for_timeout(2000)
        
        # Click first channel card
        first_card = page.locator('[x-data*="channelsApp"] [\\@click*="openChannelModal"]').first
        if await first_card.count() > 0:
            await first_card.click()
            await page.wait_for_timeout(1000)
            modal_visible = await page.evaluate("() => { const root = document.querySelector('[x-data*=\"channelsApp\"]'); const d = Alpine.evaluate(root, '$data'); return d.showChannelModal; }")
            print(f'Modal opened: {modal_visible}')
            await page.screenshot(path="verify_3_modal.png", full_page=True)
            # Close modal
            close_btn = page.locator('.modal button:has-text("×"), .modal [class*="times"]').first
            if await close_btn.count() > 0:
                await close_btn.click()
        else:
            print('No channel cards found to click')

        # JS errors
        print(f'\nJS Errors: {len(errors)}')
        for e in errors[:5]:
            print(f'  {e}')

        await browser.close()
        print('\n=== VERIFICATION COMPLETE ===')

asyncio.run(main())
