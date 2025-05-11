import asyncio
import re
from EventManager import EventManager
from debug_ui import DebugUI
from logger import setup_logger
from priority_semaphore import PrioritySemaphore
from proxy_manager import ProxyManager
from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv

load_dotenv()

HEADLESS_MODE = True

def wrapper(event_url: str, proxy_manager: ProxyManager, debug_ui: DebugUI, loading_lock: asyncio.Semaphore, initial_loading_complete_callback):
    manager = EventManager(event_url,
                       proxy_manager,
                       debug_ui,
                       loading_lock,
                       initial_loading_complete_callback
                       )
    return manager.run()

async def main():
    lg = setup_logger("MultiEventManager")
    lg.propagate = False
    lg.info("Launching browser...")
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=HEADLESS_MODE)
    browser.on("disconnected", lambda: lg.error("Browser crashed"))
    lg.info("Browser launched")

    network_sem = PrioritySemaphore(12)
    # network semaphore. Should control concurrency according to network 
    # Sempaphore(1) allows only 1 section to load
    # Also applies for CPU bottlenecked systems since loading the webpage is the most CPU intensive

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
                event_url, proxy_manager, debug_ui, network_sem,
                lambda: lg.info(f"Initial loading complete! {event_url}")
            ))

    #tasks.append(debug_ui.run_async())

    await asyncio.gather(*tasks)
        
if __name__ == "__main__":
    asyncio.run(main())