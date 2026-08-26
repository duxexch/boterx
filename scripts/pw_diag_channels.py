# -*- coding: utf-8 -*-
"""Full diagnostic of channels page: screenshot + JS errors + data check."""
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
        page.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)[:400]))
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text[:300]}") if m.type in ("error",) else None)

        await page.goto("https://vex.deals/vex/admin/admin", wait_until="load", timeout=60000)
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)

        await page.goto("https://vex.deals/channels", wait_until="load", timeout=30000)
        await page.wait_for_timeout(6000)

        # Screenshot channels tab (default view)
        await page.screenshot(path="diag_1_channels.png", full_page=True)

        # Check data loaded
        state = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            if (!root) return {hasRoot: false};
            const d = Alpine.evaluate(root, '$data');
            return {
                hasRoot: true,
                tab: d.tab,
                channels: (d.channels || []).length,
                groups: (d.groups || []).length,
                partners: (d.partners || []).length,
                adNet: (d.adNet || []).length,
                channelGroups: (d.channelGroups || []).length,
                selectedChannels: (d.selectedChannels || []).length,
                showChannelDetail: d.showChannelDetail,
                showPostModal: d.showPostModal,
                detailChannel: d.detailChannel ? d.detailChannel.id : null,
            };
        }""")
        print(f'State: {json.dumps(state, indent=1)}')

        # Click AI tab
        await page.click('button:has-text("AI")')
        await page.wait_for_timeout(3000)
        await page.screenshot(path="diag_2_ai_tab.png", full_page=True)

        # Check AI agents data
        ai_state = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            return {
                aiAgents: (d.aiAgents || []).length,
                aiProviders: d.aiProviders,
                showAgentForm: d.showAgentForm,
                editingAgent: d.editingAgent ? d.editingAgent.id : null,
            };
        }""")
        print(f'AI State: {json.dumps(ai_state, indent=1)}')

        # Check what AI API keys exist in DB
        ai_keys = await page.evaluate("""async () => {
            try {
                const r = await fetch('/api/ai-api-keys', {credentials:'same-origin'});
                return await r.json();
            } catch(e) { return {error: e.message}; }
        }""")
        print(f'AI API Keys: {json.dumps(ai_keys, indent=1, default=str)[:500]}')

        # Check Channels tab display
        await page.click('button:has-text("Channels")')
        await page.wait_for_timeout(2000)

        # Get channel rows info
        channel_rows = await page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr, [class*="channel"]');
            return rows.length;
        }""")
        print(f'Channel rows in DOM: {channel_rows}')

        # JS Errors
        print(f'\nJS Errors ({len(errors)}):')
        for e in errors[:10]:
            print(f'  {e}')

        await browser.close()

asyncio.run(main())
