import asyncio
import random
from os import getenv
from dotenv import load_dotenv

from debug_ui import DebugUI
from priority_semaphore import PrioritySemaphore
from proxy_manager import ProxyManager

load_dotenv()

from playwright.async_api import Page, TimeoutError, Browser
from playwright._impl._errors import TargetClosedError

from capsolver import Capsolver
from logger import setup_logger

DEBUG=True if getenv("DEBUG") == "True" else False

ERROR_URL = "https://etix.com/ticket/online2z/flowError.jsp"


INITIAL_LOADING_PRIORITY = 9
TAB_RELOAD_PRIORITY = 11
MAIN_RELOAD_PRIORITY = 10

async def get_available_area_numbers(page):
    area_elements = await page.query_selector_all('map[name="EtixOnlineManifestMap"] > area[status="Available"]')
    return [await element.get_attribute('name') for element in area_elements]  # or extract some attribute if available

async def scrape_section_data(tab: Page, section: str):
    with open("scripts/ticketDataAdjacentShowManifest.js", "r") as data_scraper_script:
        seat_data =  await tab.evaluate(data_scraper_script.read(), section )

    return seat_data

async def wait_for_function(page: Page, function_name, timeout=5000):
    """Waits until a function is defined in the page context."""
    await page.wait_for_function(
        f"typeof {function_name} === 'function'",
        timeout=timeout
    )

async def wait_for_window_property(page: Page, prop_name: str, timeout=5000):
    await page.wait_for_function(
        f"() => window.hasOwnProperty('{prop_name}')",
        timeout=timeout
    )

class AreaSeatingScraper:
    def __init__(self,browser: Browser, page: Page, data_callback, proxy_manager: ProxyManager, base_url, debug_ui, network_sem,
                 initial_load_complete_callback):
        self.last_rate_limit_time = None
        self.browser: Browser = browser
        self.page = page
        self.base_url = base_url
        self.network_sem: PrioritySemaphore = network_sem
        self.tabs: dict[str, Page] = {}
        self.timed_out = False
        self.logger = setup_logger("AreaSeatingScraper")
        self.data_logger = setup_logger("Datalogger", logfile="datalogs.log")
        self.data_logger.propagate = False
        self.debug_ui: DebugUI = debug_ui
        self.logger.propagate = False
        self.data_callback = data_callback
        self.proxy_manager = proxy_manager
        self.prev_available_area_numbers = []
        self.captcha_solved_event = asyncio.Event()  # Event to track CAPTCHA resolution
        self.looking_for_captcha_event = asyncio.Event()
        self.captcha_solved_event.set()  # Initially set to True (no CAPTCHA)
        self.ready_areas = []
        self.initial_loading_complete_dict: dict[str, bool] = {}
        self.initial_loading_complete_callback = initial_load_complete_callback
        self.initial_spawning_complete = False # spawning is just for spawning the tabs. initial loading is different
        self.section_blacklist = [] # sections that should not be respawned
        self.spawn_target_closed_errors: dict[str, int] ={}
        self.quit_flag: bool = False # gets set when faced with critical error and can't continue
        
    async def _initial_load_complete_check(self):
        while not self.quit_flag:
            if self.initial_loading_complete_dict and all(self.initial_loading_complete_dict.values()):
                self.initial_loading_complete_callback()
                return
            else:
                await asyncio.sleep(1)

    async def spawn_tab(self, area_number):
        # waiting till captcha is solved ( if there is )
        await self.captcha_solved_event.wait()

        try:
            new_tab: Page = await self.proxy_manager.create_tab()
            self.initial_loading_complete_dict[area_number] = False

            async with self.network_sem.priority(INITIAL_LOADING_PRIORITY):
                    await new_tab.goto(self.base_url) 
                    await new_tab.wait_for_load_state("domcontentloaded")
                    # url changes to a common URL when seating chart isn't displayed on first load. So 
                    # cant use self.page.url
                    await self.debug_ui.update_status(self.base_url,area_number,f"Waiting till initial loading complete..." )
                    try:
                        await self.debug_ui.update_status(self.base_url,area_number,f"Initial loading: checking for map " )
                        await new_tab.wait_for_selector('img[usemap="#EtixOnlineManifestMap"]', timeout=3000) 
                    except TimeoutError:
                        try:
                            #await new_tab.screenshot(path=f"./no_map/{random.randint(0,1000)}.jpg", full_page=True)
                            await self.debug_ui.update_status(self.base_url,area_number,f"Initial loading: no map, checking for ticket type " )
                            await new_tab.wait_for_selector('ul[id="ticket-type"]')
                        except TimeoutError as e:
                            self.logger.error(f"Error in spawn_tab for area {area_number}: {e}")
                            await self.debug_ui.update_status(self.base_url,area_number,f"Error in monitor_tab for area {str(e)[:50]}..." )
                            await self.proxy_manager.close_tab(new_tab)
                            if new_tab in self.tabs.values():
                                self.tabs.pop(area_number)
                            return
                    self.tabs[area_number] = new_tab
                    await self.navigate_to_seating_manifest(new_tab, area_number)
        except TargetClosedError:
            if self.browser.is_connected():
                if self.proxy_manager.check_context_status(new_tab):
                    await self.debug_ui.update_status(self.base_url,area_number,f"Initial load fail. Page crashed" )
                    return
                else:
                    await self.debug_ui.update_status(self.base_url,area_number,f"Initial load fail. Context crashed" )
                    self.quit_flag = True
            else:
                await self.debug_ui.update_status(self.base_url,area_number,f"Initial load fail. browser crashed" )
                self.quit_flag = True

    async def run(self):
        # TargetClosedError in run will be handled by EventManager run_main_monitor
        await self.debug_ui.update_status(self.base_url,"main", "Waiting till loading finish..")
        await self.page.wait_for_load_state("networkidle")
        asyncio.create_task(self._initial_load_complete_check(), name=f"__initial_load_complete_check_{self.base_url}")

        while not self.quit_flag:
            # Some pages don't load the manifest automatically. You need to navigate to it
            await self.seating_chart_selected(self.page)

            available_areas = await get_available_area_numbers(self.page)

            for area_number in available_areas:
                if (area_number not in self.tabs.keys() and self.initial_spawning_complete 
                    and area_number not in self.section_blacklist):
                    # probably was closed due to some exception and not in section blacklist. Should restart
                    self.logger.warning(f"Respawning previously closed tab {area_number}")
                    await self.spawn_tab(area_number)

            if available_areas != self.prev_available_area_numbers:
                self.logger.info(f"{len(available_areas)} available sections found.")
                await self.debug_ui.update_status(self.base_url,"main", f"{len(available_areas)} available sections found.")

                # if new areas were found available, only spawn new tabs for the new areas.
                diff = list(set(available_areas) - set(self.prev_available_area_numbers))
                self.logger.info(f"Found new areas: {diff}")
                await self.debug_ui.update_status(self.base_url,"main", f"Found new areas: {diff}")

                for area_number in diff:
                    asyncio.create_task(self.spawn_tab(area_number), name=f"spawn_tab_{area_number}:{self.base_url}")


                self.prev_available_area_numbers = available_areas
                self.initial_spawning_complete = True


            elif not available_areas:
                self.logger.info("No available areas. Refreshing...")
                await self.debug_ui.update_status(self.base_url,"main", f"No available areas. Refreshing...")
            else:
                self.logger.info("No new available areas. Refreshing...")
                await self.debug_ui.update_status(self.base_url,"main", f"No available areas. Refreshing...")

            sleep_time = random.uniform(30, 60)
            await self.debug_ui.update_status(self.base_url,"main", f"Sleeping for {str(sleep_time)[:5]}s...")
            await asyncio.sleep(sleep_time)

            async with self.network_sem.priority(MAIN_RELOAD_PRIORITY):
                await self.page.reload()
                await self.debug_ui.update_status(self.base_url,"main", "Waiting till reloading finish..")
                await self.page.wait_for_load_state("networkidle")
        else:
            self.logger.error(f"AreaSeatingScraper quit because of critical error: {self.base_url}")

    async def reload_tab_and_monitor(self, area_number: str):
        while not self.quit_flag:
            #await self.debug_ui.update_status(self.base_url,"open tabs", str(self.tabs.keys()))
            if area_number not in self.ready_areas:
                await asyncio.sleep(1)
                continue

            try:
                tab = self.tabs[area_number]
            except KeyError:
                # This tab was closed somewhere else. Just return the function. It will be spawned back
                return
            

            self.logger.info(f"Reloading area {area_number} for updates..")
            await self.debug_ui.update_status(self.base_url,area_number,"Reloading area for updates.." )
            try:
                async with self.network_sem.priority(TAB_RELOAD_PRIORITY):
                    try:
                        await tab.reload()
                    except TimeoutError:
                        self.logger.error(f"Got timeout error in reload. Try reducing the concurrency semaphore.\n"
                                          f"Section: {area_number}, event: {self.base_url}.")
                        await self.debug_ui.update_status(self.base_url, area_number, f"Got timeout error in reload."
                                                    f"Try reducing the concurrency semaphore.")
                        continue # try going for another round


                # Check for CAPTCHA on reload
                if await self.check_for_captcha(tab, area_number):
                    await self.handle_captcha(tab,area_number)

                await self.captcha_solved_event.wait()

                await asyncio.sleep(0)
                try:
                    await tab.wait_for_load_state("networkidle")
                    await wait_for_window_property(tab, 'rowSeatStatus', timeout=3000)
                except TimeoutError:
                    # Probably an error page
                    continue
                seats = await scrape_section_data(tab, area_number)
                self.logger.info(f"Extracted data for section {area_number}")
                await self.debug_ui.update_status(self.base_url,area_number,"Extracted data" )
                if isinstance(seats, dict) and 'adjacentSeats' in seats.keys():
                    # event_id will be appended to payload upstream
                    await self.data_callback({"rows":seats['adjacentSeats'], 'section': area_number})
                    self.logger.info(f"Sent data to backend")
                    await self.debug_ui.update_status(self.base_url,area_number,"Sent data to backend" )
                else: self.logger.info("Didn't find anything")
            except TargetClosedError:
                if self.browser.is_connected():
                    if self.proxy_manager.check_context_status(tab):
                        await self.debug_ui.update_status(self.base_url,area_number,f"Initial load fail. Page crashed" )
                        self.logger.warning(f"Page crashed. Respawning")
                        await self.debug_ui.update_status(self.base_url,area_number,f"Page crashed. Respawning" )
                        await self.proxy_manager.close_tab(tab)
                        if area_number in self.tabs: self.tabs.pop(area_number)
                        return
                    else:
                        await self.debug_ui.update_status(self.base_url,area_number,f"Initial load fail. Context crashed" )
                        self.quit_flag = True
                else:
                    await self.debug_ui.update_status(self.base_url,area_number,f"Initial load fail. browser crashed" )
                    self.quit_flag = True

            except Exception as e:
                self.logger.error(f"Error in tab {area_number}: {e}")
                await self.debug_ui.update_status(self.base_url,area_number,f"Error in tab {str(e)[:50]}..." )
                await self.proxy_manager.close_tab(tab)
                self.tabs.pop(area_number)
                return

    async def seating_chart_selected(self, tab: Page):

        try:
            await tab.wait_for_selector('img[usemap="#EtixOnlineManifestMap"]', timeout=3000) 
        except:
            # Wait for the <ul> element
            ul = await tab.wait_for_selector('ul#ticket-type')

            # Get all <li> children
            lis = await ul.query_selector_all('li')

            for li in lis:
                class_attr = await li.get_attribute('class') or ""
                # Check if li has the active tab classes
                if 'ui-state-active' in class_attr and 'ui-tabs-selected' in class_attr:
                    # Check if it contains an <a> with 'Seating Chart'
                    a = await li.query_selector("a:has-text('Seating Chart')")
                    if a:
                        # Already on the correct tab
                        break
                    else:
                        # Not the Seating Chart tab, find and click the correct one
                        for other_li in lis:
                            a = await other_li.query_selector("a:has-text('Seating Chart')")
                            if a:
                                async with self.network_sem.priority(INITIAL_LOADING_PRIORITY):
                                    await a.click()
                                    await tab.wait_for_selector('img[usemap="#EtixOnlineManifestMap"]', timeout=3000) 
                                    #await tab.wait_for_load_state('networkidle')
                                break
                    break

    async def navigate_to_seating_manifest(self, tab: Page, area_number: str):
        # setting up event handler to check for rate limits

        try:
            # Some pages don't load the manifest automatically. You need to navigate to it
            await self.seating_chart_selected(tab)


            async with self.network_sem.priority(INITIAL_LOADING_PRIORITY):
                await wait_for_function(tab, "isGASection")
                if await tab.evaluate(f"isGASection('{area_number}')"):
                    #this is a general admission section
                    self.logger.info("This is a ga section. Adding to section blacklist...")
                    await self.debug_ui.update_status(self.base_url,area_number,f"GA section. Adding to section blacklist" )
                    self.section_blacklist.append(area_number)
                    await self.proxy_manager.close_tab(tab)
                    if tab in self.tabs.values():
                        self.tabs.pop(area_number)
                    return
                async with tab.expect_navigation(timeout= 60000 if DEBUG else 30000) as _:
                    await wait_for_function(tab, 'chooseSection')


                    await tab.evaluate(f"chooseSection('{area_number}')")

                    await self.debug_ui.update_status(self.base_url,area_number,f"Chosen section" )
                    self.logger.info(f"Chosen section {area_number}")

                    # Check for CAPTCHA after selection
                    if await self.check_for_captcha(tab, area_number):
                        await self.handle_captcha(tab, area_number)

            self.logger.info(f"Selected section {area_number}")

            await self.debug_ui.update_status(self.base_url,area_number,f"Waiting till loading manifest" )

            await tab.wait_for_selector("div[id='seatingChart']")

            await self.debug_ui.update_status(self.base_url,area_number,f"Manifest loaded" )
            self.logger.info("Selection complete")
            self.ready_areas.append(area_number)

            # Block unnecessary resource types
            async def route_intercept(route, request):
                if request.resource_type in ['document']:
                    await route.continue_()
                else:
                    await route.abort()

            await tab.route("**/*", route_intercept)

            self.initial_loading_complete_dict[area_number] = True
            asyncio.create_task(self.reload_tab_and_monitor(area_number),name=f"reload_tab_and_monitor_{area_number}:{self.base_url}")

        except TargetClosedError:
            if self.browser.is_connected():
                await self.debug_ui.update_status(self.base_url,area_number,f"Initial load fail. Browser crashed" )
                self.quit_flag = True
            elif self.proxy_manager.check_context_status(tab):
                await self.debug_ui.update_status(self.base_url,area_number,f"Initial load fail. Context crashed" )
                self.quit_flag = True
            else:
                self.logger.warning(f"Page crashed. Respawning")
                await self.debug_ui.update_status(self.base_url,area_number,f"Page crashed. Respawning" )
                await self.proxy_manager.close_tab(tab)
                if area_number in self.tabs: self.tabs.pop(area_number)
                return
        except Exception as e:
            self.logger.error(f"Error in monitor_tab for area {area_number}: {e}")
            await self.debug_ui.update_status(self.base_url,area_number,f"Error in monitor_tab for area {str(e)[:50]}..." )
            await self.proxy_manager.close_tab(tab)
            if tab in self.tabs.values():
                self.tabs.pop(area_number)
            return

    async def handle_captcha(self, tab: Page, area_number: str):
        """Handle CAPTCHA detection and wait for resolution"""
        self.captcha_solved_event.clear()  # This will make all waits block

        self.logger.warning(f"CAPTCHA detected! Pausing operations in {area_number}")
        await self.debug_ui.update_status(self.base_url,area_number,f"CAPTCHA detected! Pausing operations." )

        try:
            # waiting for the main captcha body to show up
            await (tab.frame_locator("iframe[src*='recaptcha.net']:not([role='presentation'])").locator("div.rc-imageselect-payload")
                   .wait_for(timeout=10000))

            try:
                #await asyncio.sleep(30)
                async with Capsolver(getenv("CAPSOLVER_API_KEY")) as capsolver:
                    self.logger.info("Trying to solve captcha..")
                    await self.debug_ui.update_status(self.base_url,area_number,f"Trying to solve captcha.." )
                    try:
                        # need to solve captcha within 2 minutes. Otherwise it is an illegal solve
                        solution = await asyncio.wait_for(
                                capsolver.solve_recaptcha_v2_invisible(
                                website_url="https://www.etix.com",
                                website_key="6LedR4IUAAAAAN1WFw_JWomeQEZbfo75LAPLvMQG"
                            ),
                            timeout=120
                        )
                        if solution:
                            # automatically finding the recaptcha callback and calling it
                            with open("scripts/getRecaptchaCallback.js") as callback_finder:
                                results = await tab.evaluate(callback_finder.read())
                                await tab.evaluate(
                                    f"solution => {results[0]['callback']}(solution)", solution)

                            self.logger.info(f"Solved captcha!")
                            await self.debug_ui.update_status(self.base_url,area_number,f"Solved captcha!" )
                        else:
                            self.logger.info("Failed to solve captcha")
                            await self.debug_ui.update_status(self.base_url,area_number,f"Failed to solve captcha" )
                    
                    except asyncio.TimeoutError:
                        self.debug_ui.update_status(self.base_url, area_number, f"Failed to solve captcha within 2 minutes.."
                                                    f" Closing tab and respawning.")
                        self.logger.info(f"Failed to solve captcha within 2 minutes.."
                                                    f" Closing tab and respawning. area: {area_number}")

                        await self.proxy_manager.close_tab(tab)
                        if tab in self.tabs:
                            self.tabs.pop(area_number)

                
                # waiting for seating chart to appear
                await tab.wait_for_selector('div#seatingChart')

                self.logger.info("CAPTCHA appears to be resolved")
                await self.debug_ui.update_status(self.base_url,area_number,f"CAPTCHA appears to be resolved" )
            except Exception as e:
                self.logger.error(f"Error waiting for CAPTCHA resolution: {e}. \n Clearing tab {area_number}..")
                await self.debug_ui.update_status(self.base_url,area_number,f"Error waiting for CAPTCHA resolution: {e}. \n Clearing tab.." )
                if ERROR_URL in tab.url:
                    self.logger.error(f"URL: {tab.url}")
                await self.proxy_manager.close_tab(tab)
                if tab in self.tabs:
                    self.tabs.pop(area_number)
            finally:
                self.logger.info("Resuming operations..")
                await self.debug_ui.update_status(self.base_url,area_number,f"Resuming operations.." )
                self.captcha_solved_event.set()  # Resume operations
        except TimeoutError:
            self.logger.info(f"Captcha wasn't fully launched. Resuming operations on {area_number}")
            await self.debug_ui.update_status(self.base_url,area_number,f"Captcha wasn't fully launched. Resuming operations" )
            self.captcha_solved_event.set()  # Resume operations

    async def check_for_captcha(self, page: Page, area_number: str) -> bool:
        """Check if a CAPTCHA is present on the page"""

        self.logger.info(f"Checking for captcha in {area_number}")
        await self.debug_ui.update_status(self.base_url,area_number,f"Checking for captcha" )
        try:
            element = await page.wait_for_selector('iframe[src*="recaptcha.net"]',timeout=5000, state="attached")
            if element:
                self.logger.info(f"Found captcha in {area_number}")
                await self.debug_ui.update_status(self.base_url,area_number,f"Found captcha" )
                return True
            else:
                self.logger.info(f"No captcha found in area {area_number}")
                await self.debug_ui.update_status(self.base_url,area_number,f"No captcha found" )
                self.looking_for_captcha_event.set()
            return False
        except TimeoutError:
            self.logger.info("Recaptcha check timed out. Seems to be no captcha")
            await self.debug_ui.update_status(self.base_url,area_number,f"Recaptcha check timed out. Seems to be no captcha" )
            self.looking_for_captcha_event.set()
            return False
        except TargetClosedError:
            # pass on TargetClosedError to top level error handlers
            raise TargetClosedError
        except Exception as e:
            self.logger.error(f"Error checking for CAPTCHA: {e}")
            await self.debug_ui.update_status(self.base_url,area_number,f"Error checking for CAPTCHA: {str(e)[:50]}..." )
            self.looking_for_captcha_event.set()
            return False
