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
        await page.wait_for_timeout(2000)
        
        await page.goto("https://vex.deals/channels", wait_until="load", timeout=30000)
        await page.wait_for_timeout(5000)
        
        # Click channels tab
        await page.click("button[data-i18n='channels_tab']")
        await page.wait_for_timeout(3000)
        
        # Check channel cards
        cards = await page.evaluate("""() => {
            const cards = [...document.querySelectorAll('.grid.grid-cols-1.lg\\\\:grid-cols-2.gap-4 > div')];
            return cards.map(c => c.innerText.trim().slice(0, 120));
        }""")
        
        with open("cards_out.txt", "w", encoding="utf-8") as f:
            f.write(f"Total cards: {len(cards)}\n\n")
            for i, c in enumerate(cards[:10]):
                f.write(f"{i+1}. {c}\n\n")
        
        # Check component state
        comp = await page.evaluate("""() => {
            const root = document.querySelector('[x-data="channelsApp()"]');
            return root ? root.__x.$data : null;
        }""")
        
        with open("comp_out.txt", "w", encoding="utf-8") as f:
            f.write(str(comp))
        
        print("Done - check cards_out.txt and comp_out.txt")

asyncio.run(main())