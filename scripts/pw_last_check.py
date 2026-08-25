import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    out = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()
        await page.goto("https://vex.deals/vex/admin/admin", wait_until="load", timeout=60000)
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.evaluate("() => { document.documentElement._x_dataStack[0].toggleLang(); }")
        await page.wait_for_timeout(4000)
        for pg in ["/clients", "/channels", "/lottery"]:
            await page.goto(f"https://vex.deals{pg}", wait_until="load", timeout=30000)
            await page.wait_for_timeout(2000)
            s = await page.evaluate("""() => {
                const AR = /[\\u0600-\\u06FF]/;
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let total = 0, arabic = 0, samples = [];
                while (walker.nextNode()) {
                    const t = walker.currentNode.nodeValue.trim();
                    if (!t) continue;
                    total++;
                    if (AR.test(t)) { arabic++; if (samples.length < 8) samples.push(t.slice(0, 60)); }
                }
                return { total, arabic, samples };
            }""")
            out.append(f"{pg}: {s['arabic']}/{s['total']} -> {json.dumps(s['samples'], ensure_ascii=False)[:400]}")
        await browser.close()
    with open("final_i18n_check.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")

asyncio.run(main())