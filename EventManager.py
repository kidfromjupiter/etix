import asyncio
import re
from os import getenv

from area_seating_scraper import AreaSeatingScraper
from debug_ui import DebugUI
from logger import setup_logger
import httpx
from playwright.async_api import async_playwright, Page
import aiohttp
from dotenv import load_dotenv

load_dotenv()

from proxy_manager import ProxyManager

EVENT_URL = "https://www.etix.com/ticket/p/61485410/ludacris-with-special-guestsbow-wow-bone-thugsnharmony-albuquerque-sandia-casino-amphitheater"
HEADLESS_MODE = True

class EventManager:
    def __init__(self, base_url,  proxy_manager, debug_ui, network_sem):
        self.playwright = None
        self.base_url = base_url
        self.network_sem = network_sem
        self.context = None
        self.page = None
        self.debug_ui = debug_ui
        self.logger = setup_logger("EventManager")
        self.logger.propagate = False
        self.client = httpx.AsyncClient()
        self.timed_out = False
        self.event_id: int = 0
        self.proxy_manager: ProxyManager = proxy_manager

    async def init_browser(self):
        self.page = await self.proxy_manager.create_tab()
        await self.create_event()

    async def look_for_map(self, page: Page):
        self.logger.info("Image with usemap not found. Looking for seating chart button")
        button = await page.wait_for_selector("a:has-text('Seating Chart')")
        self.logger.info("Seating chart button found")
        async with page.expect_navigation() as _:
            await button.click()
            await page.wait_for_load_state("networkidle")
            try:
                await page.wait_for_selector('img[usemap="#EtixOnlineManifestMap"]', timeout=3000)
                return True
            except:
                self.logger.info("Image with usemap not found. Looking for seating chart button")
                return False


    async def check_manifest_image(self, page: Page):
        try:
            await page.wait_for_selector('img[usemap="#EtixOnlineManifestMap"]', timeout=3000)
            return True
        except:
            map_found = await self.look_for_map(page)
            return map_found

    async def run_main_monitor(self):
        try:
            await self.page.wait_for_selector('ul[id="ticket-type"]')
            if not await self.check_manifest_image(self.page):
                self.logger.info("Manifest image not found. Checking for seating canvas...")
                if await self.page.locator('div#seatingMap canvas').count() > 0:
                    self.logger.info("Seating canvas found")

                else:
                    self.logger.info("seating canvas not found.. Exiting")
                    return


            self.logger.info("Manifest image found. Starting main refresh loop...")

            seating_scraper = AreaSeatingScraper(self.page,  self.post_to_fastapi, self.proxy_manager, self.base_url, self.debug_ui, self.network_sem)
            await seating_scraper.run()
        except Exception as e:
            self.logger.error(f"Something went wrong with event {self.base_url}: {e}")


    async def post_to_fastapi(self, data: dict):
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{getenv('BACKEND_BASEURL', 'http://localhost:4000')}/ingest", json={**data, "event_id": self.event_id}) as response:
                if response.status != 200:
                    self.logger.warning(f"Post failed: {(await response.text())[:50]}...")
                else:
                    self.logger.info(f"Successfully posted data to webserver")

    async def create_event(self):
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{getenv('BACKEND_BASEURL', 'http://localhost:4000')}/create-event",
                                    json={"url": self.base_url}) as response:
                if response.status != 200:
                    self.logger.warning(f"Creating event failed for url {self.base_url}")
                else:
                    self.event_id = (await response.json())["event_id"]
                    self.logger.info(f"Successfully created event {self.base_url}")

    async def run(self):
        await self.init_browser()
        await self.page.goto(self.base_url)
        await self.run_main_monitor()

    async def close(self):
        self.logger.info("Shutting down...")
        await self.client.aclose()
        await self.playwright.stop()


async def main():
    lg = setup_logger("Main")
    lg.propagate = False
    lg.info("Launching browser...")
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=HEADLESS_MODE)
    debug_ui = DebugUI()

    with open("proxy_list") as proxy_list:
        proxies = proxy_list.readlines()
        sanitized_proxies = []
        for proxy in proxies:
            pattern = r"(\d.+):(\w+):(\w+)"
            matches = re.search(pattern, proxy)
            sanitized_proxies.append({
                "server": f'http://{matches.group(1)}',
                "username": matches.group(2),
                "password": matches.group(3)
            })
        proxy_manager = ProxyManager(
            browser, sanitized_proxies
        )
    manager = EventManager(EVENT_URL,
                           proxy_manager,
                            debug_ui

                           )
    lg.info("Browser launched")
    await manager.run()

if __name__ == "__main__":
    asyncio.run(main())
