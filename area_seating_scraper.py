import asyncio
import random
from os import getenv
import threading
from dotenv import load_dotenv

load_dotenv()

from playwright.async_api import Page, TimeoutError

from capsolver import Capsolver
from logger import setup_logger


ERROR_URL = "https://etix.com/ticket/online2z/flowError.jsp"


async def get_available_area_numbers(page):
    area_elements = await page.query_selector_all('map[name="EtixOnlineManifestMap"] > area[status="Available"]')
    return [await element.get_attribute('name') for element in area_elements]  # or extract some attribute if available


async def scrape_section_data(tab: Page, section: str):
    with open("scripts/ticketDataAdjacentShowManifest.js", "r") as data_scraper_script:
        seat_data =  await tab.evaluate(data_scraper_script.read(), section )

    return seat_data


class AreaSeatingScraper:
    def __init__(self, page: Page, ctx, tabs, data_callback):
        self.page = page
        self.context = ctx
        self.tabs = tabs
        self.timed_out = False
        self.logger = setup_logger("AreaSeatingScraper")
        self.data_callback = data_callback
        self.prev_available_area_numbers = []
        self.captcha_solved_event = asyncio.Event()  # Event to track CAPTCHA resolution
        self.looking_for_captcha_event = asyncio.Event()
        self.captcha_solved_event.set()  # Initially set to True (no CAPTCHA)

    async def run(self):
        while True:

            # Detecting a timeout error and restarting the process
            if self.timed_out:
                self.logger.warning("Flow error detected. Closing all tabs.")
                await self.close_all_tabs()

            await asyncio.sleep(random.uniform(1, 2))
            await self.page.reload()


            available_areas = await get_available_area_numbers(self.page)

            if available_areas != self.prev_available_area_numbers:
                self.logger.info(f"{len(available_areas)} available sections found.")

                # if new areas were found available, only spawn new tabs for the new areas.
                diff = list(set(available_areas) - set(self.prev_available_area_numbers))
                self.logger.info(f"Found new areas: {diff}")

                for area_number in diff:
                    # waiting till captcha is solved ( if there is )
                    await self.captcha_solved_event.wait()

                    new_tab: Page = await self.context.new_page()
                    await new_tab.goto(self.page.url)
                    self.tabs.append(new_tab)
                    asyncio.create_task(self.monitor_tab(new_tab, area_number))

                    # created one new tab. Now waiting before next iteration
                    await self.looking_for_captcha_event.wait()

                self.prev_available_area_numbers = available_areas


            elif not available_areas:
                self.logger.info("No available areas. Refreshing...")
            else:
                self.logger.info("No new available areas. Refreshing...")

    async def close_all_tabs(self):
        for tab in self.tabs:
            try:
                await tab.close()
                self.tabs.remove(tab)
            except:
                pass
        self.tabs.clear()

        # resetting the timedout flag
        self.timed_out = False

    async def monitor_tab(self, tab: Page, area_number: str):
        try:
            await tab.wait_for_selector('ul[id="ticket-type"]')
            async with tab.expect_navigation() as _:
                await tab.evaluate(f"chooseSection('{area_number}')")

                # Check for CAPTCHA after selection
                if await self.check_for_captcha(tab, area_number, first_load=True):
                    await self.handle_captcha(tab)

            self.logger.info(f"Selected section {area_number}")


            await tab.wait_for_selector("div[id='seatingChart']")
            self.logger.info("Selection complete")

            while True:
                await asyncio.sleep(random.uniform(1, 5))
                await tab.reload()

                # Check for CAPTCHA on reload
                if await self.check_for_captcha(tab, area_number, first_load=False):
                    await self.handle_captcha(tab)
                    return

                current_url = tab.url
                if current_url == ERROR_URL:
                    self.timed_out = True
                    return

                try:
                    seats = await scrape_section_data(tab, area_number)
                    self.logger.info(f"Extracted data for section {area_number}")
                    if not seats:
                        #await tab.close()
                        self.tabs.remove(tab)
                        self.logger.debug(f"No seats available in area {area_number}. Closing tab...")
                        break

                    if seats:
                        await self.data_callback(seats)
                except Exception as e:
                    self.logger.error(f"Error in tab {area_number}: {e}")

        except Exception as e:
            self.logger.error(f"Error in monitor_tab for area {area_number}: {e}")
            await tab.close()
            if tab in self.tabs:
                self.tabs.remove(tab)

    async def handle_captcha(self, tab: Page):
        """Handle CAPTCHA detection and wait for resolution"""
        self.captcha_solved_event.clear()  # This will make all waits block

        self.logger.warning("CAPTCHA detected! Pausing all operations...")

        async with Capsolver(getenv("CAPSOLVER_API_KEY")) as capsolver:
            solution = await capsolver.solve_recaptcha_v2_invisible(
                website_url="https://www.etix.com",
                website_key="6LedR4IUAAAAAN1WFw_JWomeQEZbfo75LAPLvMQG"
            )
            if solution:
                print(f"Solved captcha!")
                await tab.evaluate("response => recaptchaCallback(response)", solution)
            else:
                print("Failed to solve captcha")

        # For now, we'll just wait for manual resolution
        try:
            await tab.wait_for_selector("div.captcha:not(:visible)", timeout=300000)  # Wait up to 5 minutes
            self.logger.info("CAPTCHA appears to be resolved")
        except Exception as e:
            self.logger.error(f"Error waiting for CAPTCHA resolution: {e}")
        finally:
            self.captcha_solved_event.set()  # Resume operations
            await tab.close()
            if tab in self.tabs:
                self.tabs.remove(tab)

    async def check_for_captcha(self, page: Page, area_number: str, first_load: bool) -> bool:
        """Check if a CAPTCHA is present on the page"""
        if first_load : self.looking_for_captcha_event.clear() # this will pause new tab creation

        self.logger.info(f"Checking for captcha in {area_number}")
        try:
            element = await page.wait_for_selector("input#recaptcha-token",timeout=5000, state="attached")
            if element:
                return True
            self.logger.info(f"No captcha found in area {area_number}")
            return False
        except TimeoutError:
            self.logger.info("Recaptcha check timed out. Seems to be no captcha")
        except Exception as e:
            self.logger.error(f"Error checking for CAPTCHA: {e}")
            return False
        finally:
            self.looking_for_captcha_event.set()
