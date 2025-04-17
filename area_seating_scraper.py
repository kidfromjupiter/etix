import asyncio
import random

from playwright.async_api import Page

from logger import setup_logger


ERROR_URL = "https://etix.com/ticket/online2z/flowError.jsp"

class AreaSeatingScraper:
    def __init__(self, page: Page, ctx, tabs, data_callback):
        self.page = page
        self.context = ctx
        self.tabs = tabs
        self.timed_out = False
        self.logger = setup_logger("AreaSeatingScraper")
        self.data_callback = data_callback
        self.prev_available_area_numbers = []

    async def run(self):
        while True:

            # Detecting a timeout error and restarting the process
            if self.timed_out:
                self.logger.warning("Flow error detected. Closing all tabs.")
                await self.close_all_tabs()

            await asyncio.sleep(random.uniform(1, 2))
            await self.page.reload()
            available_areas = await self.get_available_area_numbers(self.page)

            if available_areas != self.prev_available_area_numbers:
                self.logger.info(f"{len(available_areas)} available sections found.")

                # if new areas were found available, only spawn new tabs for the new areas.
                diff = list(set(available_areas) - set(self.prev_available_area_numbers))

                for area_number in diff:
                    new_tab = await self.context.new_page()
                    self.tabs.append(new_tab)
                    asyncio.create_task(self.monitor_tab(new_tab, area_number))

                self.prev_available_area_numbers = available_areas
            elif not available_areas:
                self.logger.info("No available areas. Refreshing...")
            else:
                self.logger.info("No new available areas. Refreshing...")

    async def get_available_area_numbers(self, page):
        area_elements = await page.query_selector_all('map[name="EtixOnlineManifestMap"] > area[status="Available"]')
        return list(range(len(area_elements)))  # or extract some attribute if available

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

    async def monitor_tab(self, tab: Page, area_number: int):
        await tab.evaluate(f"chooseSection({area_number})")

        # Wait for redirection
        await tab.wait_for_load_state("domcontentloaded")

        while True:
            await asyncio.sleep(random.uniform(1, 2))
            await tab.reload()

            current_url = tab.url
            if current_url == ERROR_URL:
                self.timed_out = True

                return
            try:
                seats = await self.scrape_section_data(tab)

                if not seats:
                    # no seats available. close page
                    await tab.close()
                    self.tabs.remove(tab)
                    self.logger.debug(f"No seats available in area {area_number}. Closing tab...")
                    break

                for seat in seats:
                    await self.data_callback(seat)
            except Exception as e:
                self.logger.error(f"Error in tab {area_number}: {e}")

    async def scrape_section_data(self, tab: Page):
        circles = await tab.query_selector_all('div#seatingChart circle.uncheckedTd')

        seat_data = []
        for circle in circles:
            section = await circle.get_attribute("s")
            row_number = await circle.get_attribute("rn")
            seat_number = await circle.get_attribute("c")

            seat_data.append({
                "seat": seat_number,
                "row": row_number,
                "price": float(100),
                "info": "",  # Add custom logic if needed
                "section": section,  # You can extract from URL or page content
                "eventUrl": tab.url
            })

        return seat_data
