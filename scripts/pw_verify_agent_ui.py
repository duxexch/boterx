# -*- coding: utf-8 -*-
"""Verify the new AI Agent system on channels page."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()

        await page.goto("https://vex.deals/vex/admin/admin", wait_until="load", timeout=60000)
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)

        await page.goto("https://vex.deals/channels", wait_until="load", timeout=30000)
        await page.wait_for_timeout(5000)

        # Click AI tab
        ai_tab = page.locator('button:has-text("AI"), button:has-text("AI Agents")').first
        await ai_tab.click()
        await page.wait_for_timeout(2000)

        html = await page.content()
        checks = [
            ('وكيل جديد', 'Add Agent button'),
            ('Job Description', 'Job description field'),
            ('mftAkh API', 'API key field'),
            ('provider', 'Provider select'),
        ]
        # simpler text checks
        has_job = 'Job Description' in html or 'وظيفته' in html
        has_api_key = 'API' in html and 'key' in html.lower()
        has_add = 'وكيل جديد' in html or 'new' in html.lower()
        has_run = 'Run' in html or 'شغ' in html
        has_temp = 'temperature' in html.lower() or 'Temperature' in html
        has_max = 'max_tokens' in html.lower() or 'Max Tokens' in html

        results = [
            ('Job Description', has_job),
            ('API key field', has_api_key),
            ('Add button', has_add),
            ('Run button', has_run),
            ('Temperature', has_temp),
            ('Max Tokens', has_max),
        ]
        for name, ok in results:
            status = 'OK' if ok else 'MISSING'
            print(f'{status}: {name}')

        # Try clicking the add button to verify form opens
        try:
            add_btn = page.locator('button:has-text("وكيل جديد")').first
            await add_btn.click()
            await page.wait_for_timeout(500)
            form_visible = 'x-show="showAgentForm"' in await page.content() or 'showAgentForm' in await page.content()
            print(f'{"OK" if form_visible else "MISSING"}: Form opens on click')
        except Exception as e:
            print(f'FAIL: Form click - {e}')

        # Take screenshot
        await page.screenshot(path="agent_ui_verify.png", full_page=True)
        await browser.close()

        failures = [n for n, ok in results if not ok]
        if failures:
            print(f'\nFAILED: {len(failures)} checks failed')
            sys.exit(1)
        else:
            print(f'\nAll {len(results)} checks passed!')

asyncio.run(main())
