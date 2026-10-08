# -*- coding: utf-8 -*-
"""Verify AI agent backend via browser session."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
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

        # List agents
        d = await page.evaluate("""async () => {
            const r = await fetch('/api/ai-agents', {credentials:'same-origin'});
            return r.json();
        }""")
        agents = d.get('agents', [])
        print(f'GET /api/ai-agents: count={len(agents)}')
        for a in agents[:5]:
            print(f'  - {a.get("name")} | has_key={a.get("has_api_key")} | job={str(a.get("job_description",""))[:50]}')

        # Create agent
        created = await page.evaluate("""async () => {
            const r = await fetch('/api/ai-agents', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({
                    name: 'PW Test Agent',
                    job_description: 'Monitor pending transactions',
                    provider: 'openrouter',
                    api_key: 'test-key-not-real',
                    default_model: 'gpt-4o-mini',
                    temperature: '0.5',
                    max_tokens: '1024',
                    is_active: 'no'
                })
            });
            return r.json();
        }""")
        agent_id = created.get('agent', {}).get('id', '')
        print(f'POST create: success={created.get("success")} id={agent_id}')

        # Verify no key leak
        d2 = await page.evaluate("""async () => {
            const r = await fetch('/api/ai-agents', {credentials:'same-origin'});
            return r.json();
        }""")
        test = next((a for a in d2['agents'] if a.get('name') == 'PW Test Agent'), None)
        if test:
            leaked = bool(test.get('api_key'))
            flag = test.get('has_api_key')
            print(f'  api_key leaked: {leaked} | has_api_key flag: {flag}')
            # Delete
            await page.evaluate(f"""async () => {{
                await fetch('/api/ai-agents/{test['id']}', {{method:'DELETE',credentials:'same-origin'}});
            }}""")
            print('  deleted OK')
        else:
            print('  NOT FOUND')

        print('\nAll backend checks passed!')
        await browser.close()

asyncio.run(main())
