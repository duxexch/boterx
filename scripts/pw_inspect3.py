import asyncio
import json
import time
from playwright.async_api import async_playwright

URL = "https://vex.deals"

async def main():
    out = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()

        errs = []
        page.on("pageerror", lambda e: errs.append("PAGEERROR: " + str(e)[:300]))

        # ---- LOGIN PAGE (isolated) ----
        await page.goto(f"{URL}/vex/admin/admin", wait_until="load", timeout=60000)
        await page.wait_for_timeout(2000)
        out.append("=== LOGIN PAGE ERRORS ===\n" + ("\n".join(errs) if errs else "(none)"))
        errs.clear()

        # ---- LOGIN ----
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)
        await page.wait_for_timeout(5000)

        out.append("=== DASHBOARD ERRORS ===\n" + ("\n".join(errs) if errs else "(none)"))
        errs.clear()

        info = await page.evaluate("""() => {
            const html = document.documentElement;
            const d = html._x_dataStack ? html._x_dataStack[0] : null;
            let alpineEval = null;
            try {
                alpineEval = Alpine.evaluate(html, 'baseApp()');
            } catch (e) { alpineEval = 'EVAL ERR: ' + e.message; }
            return {
                alpineVersion: window.Alpine ? Alpine.version : 'none',
                dataProto: d ? Object.getOwnPropertyNames(d).slice(0, 50) : 'none',
                dataT: d && d.t ? 'function' : String(d && d.t),
                dataLang: d ? d.lang : 'none',
                dataDark: d ? d.darkMode : 'none',
                evalType: typeof alpineEval,
                evalKeys: alpineEval && typeof alpineEval === 'object' ? Object.keys(alpineEval).slice(0,30) : String(alpineEval).slice(0,100),
                sidebarFirstLinkText: (document.querySelector('.vex-sidebar a span') || {}).textContent || 'EMPTY',
                sidebarTextCount: [...document.querySelectorAll('.vex-sidebar a span')].filter(s => s.textContent.trim()).length,
            };
        }""")
        out.append("=== DEEP STATE ===\n" + json.dumps(info, ensure_ascii=False, indent=1))

        await page.screenshot(path="pw_final.png")
        await browser.close()

    with open("pw_report2.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(out))
    print("done")

asyncio.run(main())