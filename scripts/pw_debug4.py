import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()
        
        await page.goto("https://vex.deals/vex/admin/admin", wait_until="load", timeout=60000)
        await page.fill('input[name="admin_id"]', "7146701713")
        await page.fill('input[name="password"]', "Vex-LN36X_SG3bv-UNooqkME")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard", timeout=30000)
        await page.wait_for_timeout(3000)
        
        await page.goto("https://vex.deals/channels", wait_until="load", timeout=30000)
        await page.wait_for_timeout(5000)
        
        buttons = await page.evaluate("""() => {
            const btns = [...document.querySelectorAll('.flex.flex-wrap.gap-1 button')];
            return btns.map(b => ({
                text: b.innerText.trim(),
                dataI18n: b.getAttribute('data-i18n'),
                className: b.className
            }));
        }""")
        
        with open("buttons_out.txt", "w", encoding="utf-8") as f:
            for b in buttons:
                f.write(f"Button: {b}\n")
        
        await browser.close()
        print("Done - check buttons_out.txt")

asyncio.run(main())