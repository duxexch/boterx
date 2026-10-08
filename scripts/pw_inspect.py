import asyncio
import json
from playwright.async_api import async_playwright

URL = "https://vex.deals"
OUT = "pw_report.txt"

async def main():
    log = []
    errors = []
    console_msgs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()

        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text[:300]}"))
        page.on("pageerror", lambda e: errors.append(str(e)[:500]))
        page.on("requestfailed", lambda r: log.append(f"REQ FAIL: {r.url[:120]} -> {r.failure}"))

        # 1. Login page timing
        import time
        t0 = time.time()
        resp = await page.goto(f"{URL}/vex/admin/admin", wait_until="load", timeout=60000)
        t_load = time.time() - t0
        log.append(f"LOGIN PAGE: status={resp.status} load={t_load:.2f}s")

        await page.screenshot(path="pw_login.png")

        # 2. Login
        t0 = time.time()
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        try:
            await page.wait_for_url("**/dashboard", timeout=30000)
        except Exception as e:
            log.append(f"NAV to dashboard issue: {e}")
        t_login = time.time() - t0
        log.append(f"LOGIN->DASHBOARD: {t_login:.2f}s url={page.url}")

        # 3. Wait for Alpine to settle
        await page.wait_for_timeout(4000)
        await page.screenshot(path="pw_dashboard.png", full_page=False)

        # 4. Inspect state
        state = await page.evaluate("""() => {
            const html = document.documentElement;
            const sidebarLinks = [...document.querySelectorAll('.vex-sidebar a')];
            const linksWithText = sidebarLinks.filter(a => (a.textContent||'').trim().length > 0);
            const sample = sidebarLinks.slice(0, 6).map(a => (a.textContent||'').trim());
            const langBtn = [...document.querySelectorAll('button')].find(b => (b.getAttribute('@click')||'').includes('toggleLang') || (b.getAttribute('x-text')||'').match(/EN|ع/));
            const alpineData = html._x_dataStack ? html._x_dataStack[0] : null;
            return {
                alpineLoaded: typeof window.Alpine !== 'undefined',
                alpineInitialized: !!alpineData,
                lang: alpineData ? alpineData.lang : null,
                darkMode: alpineData ? alpineData.darkMode : null,
                tTest: alpineData ? alpineData.t('dashboard') : null,
                trType: typeof window.tr,
                sidebarTotal: sidebarLinks.length,
                sidebarWithText: linksWithText.length,
                sidebarSample: sample,
                docLang: html.lang, docDir: html.dir,
            };
        }""")
        log.append("STATE: " + json.dumps(state, ensure_ascii=False, indent=2))

        # 5. Refresh test (toggles disappearing?)
        await page.reload(wait_until="load")
        await page.wait_for_timeout(1500)
        early = await page.evaluate("""() => {
            const alpineData = document.documentElement._x_dataStack;
            return { alpineInitialized: !!alpineData };
        }""")
        log.append(f"AFTER RELOAD (1.5s): {json.dumps(early)}")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="pw_after_reload.png")

        await browser.close()

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n\n=== PAGE ERRORS ===\n" + ("\n".join(errors) if errors else "(none)") + "\n\n=== CONSOLE (last 60) ===\n" + "\n".join(console_msgs[-60:]))
    print("report written")

asyncio.run(main())