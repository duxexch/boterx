import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    out = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append("PAGEERROR: " + str(e)[:400]))
        page.on("console", lambda m: errs.append(f"[{m.type}] {m.text[:200]}") if m.type in ("error", "warning") else None)

        await page.goto("https://vex.deals/vex/admin/admin", wait_until="load", timeout=60000)
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)
        await page.wait_for_timeout(3000)

        # Click channels tab by data-i18n attribute
        await page.wait_for_selector("button[data-i18n='channels_tab']", state="visible", timeout=10000)
        await page.click("button[data-i18n='channels_tab']")
        await page.wait_for_timeout(3000)

        # Check if channel cards are visible
        visible = await page.evaluate("""() => {
            const cards = [...document.querySelectorAll('.grid.grid-cols-1.lg\\:grid-cols-2.gap-4 > div')];
            return cards.map(c => c.innerText.slice(0, 80));
        }""")
        out.append(f"Visible channel cards: {len(visible)}")
        for i, t in enumerate(visible[:10]):
            out.append(f"  {i+1}. {t}")

        # Check for any visible text on page
        bodyText = await page.evaluate("() => document.body.innerText.slice(0, 500)")
        out.append(f"\nBody text preview:\n{bodyText}")

        await browser.close()

    with open("visibility_check.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")

asyncio.run(main())