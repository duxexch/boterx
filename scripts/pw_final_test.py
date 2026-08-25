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
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))

        t0 = time.time()
        await page.goto(f"{URL}/vex/admin/admin", wait_until="load", timeout=60000)
        out.append(f"login page: {time.time()-t0:.2f}s")

        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)
        await page.wait_for_timeout(4000)
        out.append(f"total login->ready: {time.time()-t0:.2f}s")

        await page.screenshot(path="final_ar_dark.png")

        # Sample sidebar texts in AR
        ar_texts = await page.evaluate("() => [...document.querySelectorAll('.vex-sidebar a span')].slice(0,8).map(s => s.textContent.trim())")
        out.append("AR sidebar: " + json.dumps(ar_texts, ensure_ascii=False))

        # Click language toggle (button containing x-text EN)
        lang_btn = page.locator("button", has_text="EN").first
        await lang_btn.click()
        await page.wait_for_timeout(4000)  # reload happens
        en_state = await page.evaluate("""() => {
            const d = document.documentElement._x_dataStack[0];
            return {
                lang: d.lang,
                dir: document.documentElement.dir,
                texts: [...document.querySelectorAll('.vex-sidebar a span')].slice(0,8).map(s => s.textContent.trim()),
            };
        }""")
        out.append("EN state: " + json.dumps(en_state, ensure_ascii=False))
        await page.screenshot(path="final_en_dark.png")

        # Toggle dark mode (click sun icon = switch to light)
        await page.evaluate("() => { document.documentElement._x_dataStack[0].toggleDarkMode(); }")
        await page.wait_for_timeout(800)
        dark = await page.evaluate("() => ({dark: document.documentElement._x_dataStack[0].darkMode, cls: document.documentElement.className})")
        out.append("after dark toggle: " + json.dumps(dark))
        await page.screenshot(path="final_en_light.png")

        # Reload persistence test
        await page.reload(wait_until="load")
        await page.wait_for_timeout(3500)
        persist = await page.evaluate("""() => {
            const d = document.documentElement._x_dataStack[0];
            return { lang: d.lang, dark: d.darkMode, firstText: (document.querySelector('.vex-sidebar a span')||{}).textContent };
        }""")
        out.append("after reload (persistence): " + json.dumps(persist, ensure_ascii=False))

        out.append("PAGE ERRORS: " + (("\n".join(errs)) if errs else "(none)"))
        await browser.close()

    with open("final_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")

asyncio.run(main())