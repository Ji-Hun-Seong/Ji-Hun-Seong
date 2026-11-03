import asyncio, json, os
from playwright.async_api import async_playwright
B = "http://127.0.0.1:8080/"
async def main():
    os.makedirs("shots", exist_ok=True)
    async with async_playwright() as p:
        br = await p.chromium.launch()
        pg = await br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        logs = []
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
        await pg.goto(B); await pg.wait_for_timeout(1500)
        await pg.click('nav button[data-t="pick"]'); await pg.wait_for_timeout(6000)
        await pg.screenshot(path="shots/1_surge.png", full_page=True)
        await pg.click('#p-seg button[data-k="value"]'); await pg.wait_for_timeout(5000)
        await pg.screenshot(path="shots/2_value.png", full_page=True)
        await pg.click('#p-out [data-pi="0"]'); await pg.wait_for_timeout(9000)
        await pg.screenshot(path="shots/3_detail_value.png", full_page=True)
        await pg.click('#sd-bb-btn'); await pg.wait_for_timeout(8000)
        await pg.screenshot(path="shots/3b_detail_bb.png", full_page=True)
        await pg.click('nav button[data-t="pick"]'); await pg.wait_for_timeout(500)
        await pg.click('#p-seg button[data-k="ackman"]'); await pg.wait_for_timeout(5000)
        await pg.screenshot(path="shots/4_ackman.png", full_page=True)
        await pg.click('#p-out [data-pi="0"]'); await pg.wait_for_timeout(12000)
        await pg.screenshot(path="shots/5_detail_us.png", full_page=True)
        await pg.click('nav button[data-t="pick"]'); await pg.wait_for_timeout(500)
        await pg.click('#p-seg button[data-k="surge"]'); await pg.wait_for_timeout(1500)
        if await pg.query_selector('#p-out [data-pi="0"]'):
            await pg.click('#p-out [data-pi="0"]'); await pg.wait_for_timeout(9000)
            await pg.screenshot(path="shots/6_detail_surge.png", full_page=True)
        open("shots/console.txt", "w").write("\n".join(logs))
        await br.close()
asyncio.run(main())
