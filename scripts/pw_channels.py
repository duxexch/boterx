import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    out, errs = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errs.append("PAGEERROR: " + str(e)[:400]))
        page.on("console", lambda m: errs.append(f"[{m.type}] {m.text[:300]}") if m.type in ("error", "warning") else None)

        await page.goto("https://vex.deals/vex/admin/admin", wait_until="load", timeout=60000)
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)

        await page.goto("https://vex.deals/channels", wait_until="load", timeout=30000)
        await page.wait_for_timeout(6000)

        state = await page.evaluate("""() => {
            const root = document.querySelector('[x-data="channelsApp()"]');
            const d = root ? Alpine.evaluate(root, '$data') : null;
            const tabs = [...document.querySelectorAll('.vex-sidebar a')].map(a => a.getAttribute('href'));
            // count visible channel rows in the channels tab
            const bodyText = document.body.innerText.slice(0, 500);
            return {
                hasRoot: !!root,
                channelsCount: d ? (d.channels || []).length : 'no-data',
                groupsCount: d ? (d.groups || []).length : null,
                activeTab: d ? d.tab : null,
                partnersCount: d ? (d.partners || []).length : null,
                apiChannelsTest: null,
            };
        }""")

        # Direct API check from within the page
        api = await page.evaluate("""async () => {
            try {
                const r = await fetch('/api/channels', {credentials: 'same-origin'});
                const j = await r.json();
                return {status: r.status, count: (j.channels||[]).length};
            } catch(e) { return {error: e.message}; }
        }""")
        state["apiChannelsTest"] = api

        out.append("STATE: " + json.dumps(state, ensure_ascii=False, indent=1))
        out.append("\nERRORS/WARNINGS:\n" + ("\n".join(errs[:40]) if errs else "(none)"))
        await page.screenshot(path="channels_page.png", full_page=False)
        await browser.close()

    with open("channels_debug.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")

asyncio.run(main())