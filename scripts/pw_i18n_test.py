import asyncio
import json
import time
from playwright.async_api import async_playwright

URL = "https://vex.deals"
PAGES = ["/channels", "/broadcast", "/agents", "/clients", "/companies", "/payment-methods",
         "/apps", "/bots", "/referrals", "/themes", "/settings", "/backup", "/svrp",
         "/transactions", "/matching", "/trading", "/lottery", "/wheel", "/users",
         "/statistics", "/admins", "/exchange-addresses", "/send-message", "/complaints"]

async def main():
    out, all_errs = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()
        page.on("pageerror", lambda e: all_errs.append(str(e)[:150]))

        await page.goto(f"{URL}/vex/admin/admin", wait_until="load", timeout=60000)
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)
        await page.wait_for_timeout(2500)

        # Switch to English
        await page.evaluate("() => { document.documentElement._x_dataStack[0].toggleLang(); }")
        await page.wait_for_timeout(4000)

        AR = r'[\u0600-\u06FF]'
        results = []
        for pg in PAGES:
            try:
                await page.goto(f"{URL}{pg}", wait_until="load", timeout=30000)
                await page.wait_for_timeout(1800)
                stats = await page.evaluate("""() => {
                    const AR = /[\\u0600-\\u06FF]/;
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    let total = 0, arabic = 0, samples = [];
                    while (walker.nextNode()) {
                        const t = walker.currentNode.nodeValue.trim();
                        if (!t) continue;
                        total++;
                        if (AR.test(t)) { arabic++; if (samples.length < 6) samples.push(t.slice(0, 50)); }
                    }
                    return { total, arabic, samples };
                }""")
                results.append((pg, stats))
            except Exception as e:
                results.append((pg, {"error": str(e)[:100]}))

        out.append("=== EN MODE: Arabic text remaining per page ===")
        for pg, s in results:
            if "error" in s:
                out.append(f"{pg}: ERROR {s['error']}")
            else:
                pct = (100 * s["arabic"] / s["total"]) if s["total"] else 0
                flag = " <<<" if s["arabic"] > 15 else ""
                out.append(f"{pg}: {s['arabic']}/{s['total']} arabic nodes ({pct:.0f}%){flag}  samples: {json.dumps(s['samples'], ensure_ascii=False)[:220]}")

        out.append("\n=== PAGE ERRORS ===")
        out.append("\n".join(all_errs) if all_errs else "(none)")

        # Screenshots of the two previously-worst pages
        await page.goto(f"{URL}/channels", wait_until="load", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path="en_channels.png")
        await page.goto(f"{URL}/broadcast", wait_until="load", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path="en_broadcast.png")

        await browser.close()

    with open("i18n_test_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")

asyncio.run(main())