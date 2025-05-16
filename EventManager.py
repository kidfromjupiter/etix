import asyncio
from datetime import datetime
import re
from os import getenv
import random

from area_seating_scraper import AreaSeatingScraper
from debug_ui import DebugUI
from logger import setup_logger
import httpx
from playwright.async_api import  Page, Request, Browser
import aiohttp
from dotenv import load_dotenv

from playwright._impl._errors import TargetClosedError

load_dotenv(override=True)

from priority_semaphore import PrioritySemaphore
from proxy_manager import ProxyManager

EVENT_URL = "https://www.etix.com/ticket/p/61485410/ludacris-with-special-guestsbow-wow-bone-thugsnharmony-albuquerque-sandia-casino-amphitheater"
HEADLESS_MODE = True

class EventManager:
    def __init__(self, base_url,browser,  proxy_manager, debug_ui, network_sem, initial_load_complete_callback):
        self.playwright = None
        self.base_url = base_url
        self.browser: Browser = browser
        self.network_sem: PrioritySemaphore = network_sem
        self.context = None
        self.page = None
        self.debug_ui = debug_ui
        self.logger = setup_logger("EventManager")
        self.logger.propagate = False
        self.client = httpx.AsyncClient()
        self.timed_out = False
        self.event_id: int = 0
        self.proxy_manager: ProxyManager = proxy_manager
        self.retries_remaining = 3
        self.has_manifest_image_event = asyncio.Event()
        self.initial_load_complete_callback = initial_load_complete_callback

    async def init_browser(self):
        self.page = await self.proxy_manager.create_tab()

    async def look_for_map(self, page: Page):
        self.logger.info("Image with usemap not found. Looking for seating chart button")
        button = page.locator("a:has-text('Seating Chart')")
        await button.wait_for()
        self.logger.info("Seating chart button found")
        async with page.expect_navigation() as _:
            await button.click()
            try:
                await asyncio.wait_for(self.has_manifest_image_event.wait(), timeout=5)
                #await page.wait_for_selector('img[usemap="#EtixOnlineManifestMap"]', timeout=3000)
                return True
            except:
                self.logger.info("Image with usemap not found. Looking for seating chart button")
                return False


    async def check_manifest_image(self, page: Page):
        try:
            #await page.wait_for_selector('img[usemap="#EtixOnlineManifestMap"]')
            await asyncio.wait_for(self.has_manifest_image_event.wait(), timeout=5)
            return True
        except:
            map_found = await self.look_for_map(page)
            return map_found

    async def get_event_time(self, page: Page):
        try:
            time_div = page.locator("div[class='time']")
            await time_div.wait_for()
            time_string = await time_div.inner_text()
            matches = re.search(r'\b[A-Z][a-z]+ \d+, \d+ \d+:\d+ [A|P]M',time_string)
            if matches:
                formatted_time = datetime.strptime(matches.group(), "%B %d, %Y %I:%M %p")
                iso_time = formatted_time.isoformat()
                return iso_time
            else: 
                self.logger.warning(f"Couldn't get time for event {self.base_url}. No matches for time found!. Time string returned: {time_string}")
                return None
        except Exception as e: 
            self.logger.error(f"Couldn't get time for event {self.base_url}: {e}")
            return None

    async def run_main_monitor(self):
        while self.retries_remaining > 0:
            try:
                async with self.network_sem.priority(8): 
                    if not await self.check_manifest_image(self.page):
                        # Current version can't handle seating canvas anyway.
                        return

                self.logger.info("Manifest image found. Starting main refresh loop...")

                time_str = await self.get_event_time(self.page)

                self.retries_remaining = 3 # resetting the retries
                await self.create_event(time_str)
                seating_scraper = AreaSeatingScraper(self.browser, self.page,  self.post_to_fastapi,
                                                      self.proxy_manager, self.base_url, self.debug_ui,
                                                      self.network_sem,
                                                      self.initial_load_complete_callback)
                await seating_scraper.run()
            except TimeoutError:
                self.retries_remaining -= 1
                self.logger.error(f"Something went wrong with event {self.base_url}:\nRetries remaining: {self.retries_remaining}")
                #await self.page.screenshot(path=f"./.fails/{random.randint(1,1000)}.jpg", full_page=True, timeout=0)
                # need to pass timeout 0. Otherwise, another timeout error


    async def post_to_fastapi(self, data: dict):
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{getenv('BACKEND_BASEURL', 'http://localhost:4000')}/ingest", json={**data, "event_id": self.event_id}) as response:
                if response.status != 200:
                    self.logger.warning(f"Post failed: {(await response.text())[:50]}...")
                else:
                    self.logger.info(f"Successfully posted data to webserver")

    async def create_event(self, time):
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{getenv('BACKEND_BASEURL', 'http://localhost:4000')}/create-event",
                                    json={"url": self.base_url, "time": time}) as response:
                if response.status != 200:
                    self.logger.warning(f"Creating event failed for url {self.base_url}")
                else:
                    self.event_id = (await response.json())["event_id"]
                    self.logger.info(f"Successfully created event {self.base_url}")

    async def _on_request(self, request: Request):
        if request.url.startswith("https://cdn.etix.com/etix/viewable_chart/"):
            self.has_manifest_image_event.set()
            
    async def run(self):
        while True:
            try:
                await self.init_browser()
                async with self.network_sem.priority(7):
                    await self.page.goto(self.base_url) # waiting for 10 minutes
                    self.page.on('request', lambda req: self._on_request(req))
                await self.run_main_monitor()
                break  # If everything finishes without crash, exit the loop
            except TargetClosedError:
                if self.browser.is_connected():
                    self.logger.warning(f"Browser is up. Page or context crashed. Respawning..")
                    # we can continue after a page/context crash since proxy manager create a new context if context has crashed.
                else:
                    self.logger.warning(f"Browser crashed... Exiting ")
                    break
            except Exception as e:
                self.logger.error(f"Unhandled exception in run loop: {e}")
                if self.page:
                    try:
                        await self.page.close()
                        self.logger.info(f"Closing page: {self.base_url}")
                    except:
                        pass



