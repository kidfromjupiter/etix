import asyncio
import random

from area_seating_scraper import AreaSeatingScraper
from logger import setup_logger
import httpx
from playwright.async_api import async_playwright, Page
import aiohttp


class EventManager:
    def __init__(self, base_url, api_url):
        self.base_url = base_url
        self.api_url = api_url
        self.context = None
        self.page = None
        self.tabs = []
        self.logger = setup_logger("EventManager")
        self.client = httpx.AsyncClient()
        self.timed_out = False

    async def init_browser(self):
        self.logger.info("Launching browser...")
        self.playwright = await async_playwright().start()
        browser = await self.playwright.chromium.launch(headless=False)
        self.context = await browser.new_context()
        self.page = await self.context.new_page()
        self.logger.info("Browser launched and context created.")

    async def check_manifest_image(self, page):
        try:
            await page.wait_for_selector('img[usemap="#EtixOnlineManifestMap"]', timeout=3000)
            return True
        except:
            self.logger.info("Image with usemap not found.")
            return False



    async def run_main_monitor(self):
        if not await self.check_manifest_image(self.page):
            self.logger.info("Manifest image not found. Checking for seating canvas...")
            if await self.page.locator('div#seatingMap canvas').count() > 0:
                self.logger.info("Seating canvas found")

            else:
                self.logger.info("seating canvas not found.. Exiting")
                return


        self.logger.info("Manifest image found. Starting main refresh loop...")

        seating_scraper = AreaSeatingScraper(self.page, self.context, self.tabs, self.post_to_fastapi)
        await seating_scraper.run()


    async def post_to_fastapi(self, data: dict):
        async with aiohttp.ClientSession() as session:
            async with session.post("http://localhost:8000/ingest", json=data) as response:
                if response.status != 200:
                    self.logger.warning(f"Post failed: {await response.text()}")

    async def run(self):
        await self.init_browser()
        await self.page.goto(self.base_url)
        await self.run_main_monitor()

    async def close(self):
        self.logger.info("Shutting down...")
        await self.client.aclose()
        await self.playwright.stop()
