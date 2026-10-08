import asyncio
import json
import time
from playwright.async_api import async_playwright

URL = "https://vex.deals"

async def main():
    log, errors, console_msgs = [], [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()
        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text[:300]}"))
        page.on("pageerror", lambda e: errors.append(str(e)[:500]))
        page.on("requestfailed", lambda r: log.append(f"REQ FAIL: {r.url[:120]}"))

        t0 = time.time()
        resp = await page.goto(f"{URL}/vex/admin/admin", wait_until="load", timeout=60000)
        log.append(f"LOGIN PAGE: {resp.status} in {time.time()-t0:.2f}s")
        await page.screenshot(path="pw_login.png")

        t0 = time.time()
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        try:
            await page.wait_for_url("**/dashboard", timeout=30000)
        except Exception as e:
            log.append(f"NAV issue: {e}")
        log.append(f"LOGIN->DASH: {time.time()-t0:.2f}s url={page.url}")

        await page.wait_for_timeout(5000)
        info = await page.evaluate("""() => {
            const html = document.documentElement;
            const stack = html._x_dataStack;
            const d = stack ? stack[0] : null;
            return {
                url: location.href,
                title: document.title,
                htmlAttrXData: html.getAttribute('x-data'),
                hasStack: !!stack,
                stackLen: stack ? stack.length : 0,
                dataType: d ? typeof d : 'none',
                dataKeys: d && typeof d === 'object' ? Object.keys(d).slice(0,40) : String(d).slice(0,80),
                hasGlobalBaseApp: typeof window.baseApp,
                baseAppSrc: typeof window.baseApp === 'function' ? window.baseApp.toString().slice(0,120) : '',
                scripts: [...document.querySelectorAll('script[src]')].map(s => s.getAttribute('src')),
                swController: !!(navigator.serviceWorker && navigator.serviceWorker.controller),
            };
        }""")
        log.append("INFO: " + json.dumps(info, ensure_ascii=False, indent=1))
        await page.screenshot(path="pw_dashboard.png")
        await browser.close()

    with open("pw_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n\n=== PAGE ERRORS ===\n" + ("\n".join(errors) if errors else "(none)") + "\n\n=== CONSOLE (last 40) ===\n" + "\n".join(console_msgs[-40:]))
    print("done")

asyncio.run(main())