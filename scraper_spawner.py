import asyncio
import re
from EventManager import EventManager
from debug_ui import DebugUI
from logger import setup_logger
from proxy_manager import ProxyManager
from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv

load_dotenv()

EVENT_URL = "https://www.etix.com/ticket/p/61485410/ludacris-with-special-guestsbow-wow-bone-thugsnharmony-albuquerque-sandia-casino-amphitheater"
HEADLESS_MODE = True

def wrapper(event_url: str, proxy_manager: ProxyManager, debug_ui: DebugUI, loading_lock: asyncio.Semaphore):
    manager = EventManager(event_url,
                       proxy_manager,
                       debug_ui,
                       loading_lock
                       )
    return manager.run()


async def main():
    lg = setup_logger("MultiEventManager")
    lg.propagate = False
    lg.info("Launching browser...")
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=HEADLESS_MODE)
    lg.info("Browser launched")

    network_sem = asyncio.Semaphore(8) # network semaphore. Should control concurrency according to network 
    # Sempaphore(1) allows only 1 section to load

    tasks = []
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
    debug_ui = DebugUI()
    with open("event_list") as event_list:
        for event_url in event_list:
            tasks.append(wrapper(
                event_url, proxy_manager, debug_ui, network_sem
            ))

    tasks.append(debug_ui.run())

    await asyncio.gather(*tasks)





if __name__ == "__main__":
    asyncio.run(main())