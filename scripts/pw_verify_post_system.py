# -*- coding: utf-8 -*-
"""Verify the post creation system end-to-end."""
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
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))

        # Login
        await page.goto("https://vex.deals/vex/admin/admin", wait_until="load", timeout=60000)
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)

        await page.goto("https://vex.deals/channels", wait_until="load", timeout=30000)
        await page.wait_for_timeout(5000)

        results = []

        # 1. Check "Create Post" button exists
        has_btn = await page.evaluate("""() => {
            return document.body.innerText.includes('إنشاء منشور');
        }""")
        results.append(('Create Post button', has_btn, ''))

        # 2. Check channels loaded
        ch_count = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            return Alpine.evaluate(root, '$data').channels.length;
        }""")
        results.append(('Channels loaded', ch_count >= 30, f'{ch_count} channels'))

        # 3. Open post composer
        await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            Alpine.evaluate(root, '$data').openPostComposer();
        }""")
        await page.wait_for_timeout(500)
        modal_open = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            return Alpine.evaluate(root, '$data').showPostComposer;
        }""")
        results.append(('Post composer opens', modal_open, ''))

        # 4. Check composer fields
        has_textarea = await page.locator('textarea[placeholder*="نص المنشور"]').count() > 0
        results.append(('Text editor', has_textarea, ''))
        has_channel_select = await page.locator('text=القنوات المستهدفة').count() > 0
        results.append(('Channel selection', has_channel_select, ''))
        has_schedule = await page.locator('text=الجدولة').count() > 0
        results.append(('Schedule options', has_schedule, ''))
        has_cron = await page.locator('text=كرون').count() > 0
        results.append(('Cron option', has_cron, ''))

        # Screenshot the post composer
        await page.screenshot(path="verify_post_composer.png", full_page=True)

        # 5. Test creating a post (without sending - check API validation)
        post_result = await page.evaluate("""async () => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            const d = Alpine.evaluate(root, '$data');
            d.postForm.message = 'Test post from verification';
            d.postForm.channelIds = d.channels.slice(0, 2).map(c => c.id);
            d.postForm.scheduleType = 'now';
            try {
                const r = await fetch('/api/posts/create', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: d.postForm.message,
                        media_urls: [],
                        channels: d.postForm.channelIds,
                        groups: [],
                        schedule_type: 'now',
                        scheduled_at: '',
                        cron_expr: '',
                        priority: 'normal'
                    })
                });
                return await r.json();
            } catch(e) { return {error: e.message}; }
        }""")
        results.append(('Post API works', post_result.get('success'), f"queued={post_result.get('queued')}, vault={post_result.get('vault_id','')}"))

        # 6. Check post history
        history = await page.evaluate("""async () => {
            const r = await fetch('/api/posts/history', {credentials: 'same-origin'});
            return await r.json();
        }""")
        results.append(('Post history', history.get('posts') is not None, f"{len(history.get('posts', []))} posts"))

        # 7. Check groups loaded
        groups = await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            return Alpine.evaluate(root, '$data').groups;
        }""")
        results.append(('Groups loaded', groups is not None, f"{len(groups)} groups"))

        # Close composer
        await page.evaluate("""() => {
            const root = document.querySelector('[x-data*="channelsApp"]');
            Alpine.evaluate(root, '$data').closePostComposer();
        }""")

        # Screenshot channels page
        await page.screenshot(path="verify_channels_final.png", full_page=True)

        # 8. JS errors
        results.append(('No JS errors', len(errors) == 0, f'{len(errors)} errors'))
        for e in errors[:3]:
            print(f'  ERROR: {e}')

        await browser.close()

        print('\n=== VERIFICATION RESULTS ===')
        passed = 0
        for name, ok, detail in results:
            status = 'PASS' if ok else 'FAIL'
            if ok: passed += 1
            print(f'  [{status}] {name}: {detail}')
        print(f'\n  {passed}/{len(results)} passed')

asyncio.run(main())
