import asyncio
import random
from playwright.async_api import async_playwright
from logger import setup_logger

class EventManager:
    def __init__(self, base_url):
        self.base_url = base_url
        self.context = None
        self.page = None
        self.tabs = []
        self.logger = setup_logger("EventManager")

    async def init_browser(self):
        self.logger.info("Launching browser...")
        self.playwright = await async_playwright().start()
        browser = await self.playwright.chromium.launch(headless=False)
        self.context = await browser.new_context()
        self.page = await self.context.new_page()
        self.logger.info("Browser launched and context created.")

    async def navigate_and_click(self, selector):
        self.logger.info(f"Navigating to {self.base_url}")
        await self.page.goto(self.base_url)

        self.logger.info(f"Clicking selector: {selector}")
        async with self.context.expect_page() as new_page_info:
            await self.page.click(selector)

        new_tab = await new_page_info.value
        self.tabs.append(new_tab)
        self.logger.info(f"New tab opened for selector: {selector}")

    async def refresh_and_scrape(self, tab, tab_id):
        while True:
            wait_time = random.uniform(1, 2)
            await asyncio.sleep(wait_time)
            await tab.reload()
            content = await tab.content()
            self.logger.info(f"[Tab {tab_id}] Refreshed and scraped {len(content)} characters")

    async def start_monitoring(self):
        self.logger.info("Starting monitoring of all tabs.")
        await asyncio.gather(*(self.refresh_and_scrape(tab, i) for i, tab in enumerate(self.tabs)))

    async def run(self):
        await self.init_browser()

        # Replace with actual selectors
        click_selectors = ['#event1', '#event2', '#event3']
        for sel in click_selectors:
            try:
                await self.navigate_and_click(sel)
            except Exception as e:
                self.logger.error(f"Error clicking {sel}: {e}")

        await self.start_monitoring()

    async def close(self):
        self.logger.info("Shutting down browser.")
        await self.playwright.stop()
