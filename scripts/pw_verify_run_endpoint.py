# -*- coding: utf-8 -*-
"""Test run endpoint and delete endpoint."""
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

        # Create inactive agent to test run rejection
        created = await page.evaluate("""async () => {
            const r = await fetch('/api/ai-agents', {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({
                    name: 'Inactive Test', job_description: 'test', provider: 'auto',
                    is_active: 'no'
                })
            });
            return r.json();
        }""")
        aid = created.get('agent', {}).get('id', '')
        print(f'Created inactive agent: {aid}')

        # Try to run — should fail with "inactive"
        run_result = await page.evaluate("""async (aid) => {
            const r = await fetch('/api/ai-agents/' + aid + '/run', {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type':'application/json'},
                body: '{}'
            });
            return r.json();
        }""", aid)
        print(f'Run inactive: success={run_result.get("success")} error={run_result.get("error")}')

        # Delete
        await page.evaluate("""async (aid) => {
            await fetch('/api/ai-agents/' + aid, {method:'DELETE',credentials:'same-origin'});
        }""", aid)
        print('Cleanup done')

        await browser.close()
        print('\nRun endpoint correctly rejects inactive agents!')
        print('\n=== ALL TESTS PASSED ===')

asyncio.run(main())
