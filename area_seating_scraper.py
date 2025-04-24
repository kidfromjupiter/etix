import asyncio
import random
import sys
import time
from os import getenv
import threading
from dotenv import load_dotenv

from proxy_manager import ProxyManager

load_dotenv()

from playwright.async_api import Page, TimeoutError

from capsolver import Capsolver
from logger import setup_logger

DEBUG=True

ERROR_URL = "https://etix.com/ticket/online2z/flowError.jsp"


async def get_available_area_numbers(page):
    area_elements = await page.query_selector_all('map[name="EtixOnlineManifestMap"] > area[status="Available"]')
    return [await element.get_attribute('name') for element in area_elements]  # or extract some attribute if available


async def scrape_section_data(tab: Page, section: str):
    with open("scripts/ticketDataAdjacentShowManifest.js", "r") as data_scraper_script:
        seat_data =  await tab.evaluate(data_scraper_script.read(), section )

    return seat_data


class AreaSeatingScraper:
    def __init__(self, page: Page, data_callback, proxy_manager: ProxyManager):
        self.last_rate_limit_time = None
        self.page = page
        self.tabs: dict[str, Page] = {}
        self.timed_out = False
        self.logger = setup_logger("AreaSeatingScraper")
        self.logger.propagate = False
        self.data_callback = data_callback
        self.proxy_manager = proxy_manager
        self.prev_available_area_numbers = []
        self.captcha_solved_event = asyncio.Event()  # Event to track CAPTCHA resolution
        self.looking_for_captcha_event = asyncio.Event()
        self.rate_limited_event = asyncio.Event() # Event to check rate limits
        self.rate_limited_event.set() # no rate limits initially
        self.captcha_solved_event.set()  # Initially set to True (no CAPTCHA)
        #self.rate_limit_cooldown = 0 # in seconds
        self.ready_areas = []
        self.initial_spawning_complete = False

    async def spawn_tab(self, area_number):

        # waiting till captcha is solved ( if there is )
        await self.captcha_solved_event.wait()

        new_tab: Page = await self.proxy_manager.create_tab()
        await new_tab.goto(self.page.url)

        self.tabs[area_number] = new_tab
        await self.navigate_to_seating_manifest(new_tab, area_number)

    async def run(self):
        # once off action
        asyncio.create_task(self.reload_tabs())

        while True:
            await self.page.wait_for_load_state("networkidle")

            available_areas = await get_available_area_numbers(self.page)

            for area_number in available_areas:
                if area_number not in self.tabs.keys() and self.initial_spawning_complete:
                    # probably was closed due to some exception. Should restart
                    self.logger.warning(f"Respawning previously closed tab {area_number}")
                    await self.spawn_tab(area_number)

            if available_areas != self.prev_available_area_numbers:
                self.logger.info(f"{len(available_areas)} available sections found.")

                # if new areas were found available, only spawn new tabs for the new areas.
                diff = list(set(available_areas) - set(self.prev_available_area_numbers))
                self.logger.info(f"Found new areas: {diff}")

                for area_number in diff:
                    await self.spawn_tab(area_number)


                self.prev_available_area_numbers = available_areas
                self.initial_spawning_complete = True


            elif not available_areas:
                self.logger.info("No available areas. Refreshing...")
            else:
                self.logger.info("No new available areas. Refreshing...")

            await asyncio.sleep(random.uniform(30, 60))
            await self.page.reload()

    async def reload_tabs(self):
        while True:
            if not self.tabs.keys():
                await asyncio.sleep(1)

            for area_number in list(self.tabs.keys()):
                if area_number not in self.ready_areas:
                    await asyncio.sleep(1)
                    continue

                tab = self.tabs[area_number]

                await asyncio.sleep(random.uniform(0, 4))

                self.logger.info(f"Reloading area {area_number} for updates..")
                await tab.reload()


                # Check for CAPTCHA on reload
                if await self.check_for_captcha(tab, area_number, first_load=False):
                    await self.handle_captcha(tab,area_number)

                await self.captcha_solved_event.wait()

                current_url = tab.url
                if current_url == ERROR_URL:
                    self.timed_out = True

                await asyncio.sleep(0)
                try:
                    seats = await scrape_section_data(tab, area_number)
                    self.logger.info(f"Extracted data for section {area_number}")
                    if isinstance(seats, dict) and 'adjacentSeats' in seats.keys():
                        # event_id will be appended to payload upstream
                        await self.data_callback({"rows":seats['adjacentSeats'], 'section': area_number})
                except Exception as e:
                    self.logger.error(f"Error in tab {area_number}: {e}")
                    await self.proxy_manager.close_tab(tab)
                    self.tabs.pop(area_number)



    async def navigate_to_seating_manifest(self, tab: Page, area_number: str):
        # setting up event handler to check for rate limits

        try:
            await tab.wait_for_selector('ul[id="ticket-type"]')
            async with tab.expect_navigation(timeout= 60000 if DEBUG else 30000) as _:

                if DEBUG: await tab.wait_for_load_state('networkidle')
                await tab.evaluate(f"chooseSection('{area_number}')")
                self.logger.info(f"Chosen section {area_number}")

                # Check for CAPTCHA after selection
                if await self.check_for_captcha(tab, area_number, first_load=True):
                    await self.handle_captcha(tab, area_number)

            self.logger.info(f"Selected section {area_number}")

            if DEBUG: await tab.wait_for_load_state('networkidle')

            await tab.wait_for_selector("div[id='seatingChart']")
            self.logger.info("Selection complete")
            self.ready_areas.append(area_number)

        except Exception as e:
            self.logger.error(f"Error in monitor_tab for area {area_number}: {e}")
            await self.proxy_manager.close_tab(tab)
            if tab in self.tabs:
                self.tabs.pop(area_number)

    async def handle_captcha(self, tab: Page, area_number: str):
        """Handle CAPTCHA detection and wait for resolution"""
        self.captcha_solved_event.clear()  # This will make all waits block

        self.logger.warning("CAPTCHA detected! Pausing all operations...")

        try:
            # waiting for the main captcha body to show up
            await (tab.frame_locator("iframe[src*='recaptcha.net']:not([role='presentation'])").locator("div.rc-imageselect-payload")
                   .wait_for(timeout=10000))

            try:
                #await asyncio.sleep(30)
                async with Capsolver(getenv("CAPSOLVER_API_KEY")) as capsolver:
                    self.logger.info("Trying to solve captcha..")
                    solution = await capsolver.solve_recaptcha_v2_invisible(
                        website_url="https://www.etix.com",
                        website_key="6LedR4IUAAAAAN1WFw_JWomeQEZbfo75LAPLvMQG"
                    )
                    if solution:
                        # automatically finding the recaptcha callback and calling it
                        with open("scripts/getRecaptchaCallback.js") as callback_finder:
                            results = await tab.evaluate(callback_finder.read())
                            await tab.evaluate(
                                f"solution => {results[0]['callback']}(solution)", solution)

                        self.logger.info(f"Solved captcha!")
                    else:
                        self.logger.info("Failed to solve captcha")

                # waiting for seating chart to appear
                await tab.wait_for_selector('div#seatingChart')

                self.logger.info("CAPTCHA appears to be resolved")
            except Exception as e:
                self.logger.error(f"Error waiting for CAPTCHA resolution: {e}. \n Clearing tab..")
                await self.proxy_manager.close_tab(tab)
                if tab in self.tabs:
                    self.tabs.pop(area_number)
            finally:
                self.logger.info("Resuming operations..")
                self.captcha_solved_event.set()  # Resume operations
        except TimeoutError:
            self.logger.info("Captcha wasn't fully launched. Resuming operations")
            self.captcha_solved_event.set()  # Resume operations

    async def check_for_captcha(self, page: Page, area_number: str, first_load: bool) -> bool:
        """Check if a CAPTCHA is present on the page"""

        self.logger.info(f"Checking for captcha in {area_number}")
        try:
            element = await page.wait_for_selector('iframe[src*="recaptcha.net"]',timeout=5000, state="attached")
            if element:
                self.logger.info(f"Found captcha in {area_number}")
                return True
            else:
                self.logger.info(f"No captcha found in area {area_number}")
                self.looking_for_captcha_event.set()
            return False
        except TimeoutError:
            self.logger.info("Recaptcha check timed out. Seems to be no captcha")
            self.looking_for_captcha_event.set()
            return False
        except Exception as e:
            self.logger.error(f"Error checking for CAPTCHA: {e}")
            self.looking_for_captcha_event.set()
            return False
