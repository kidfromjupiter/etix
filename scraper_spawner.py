import asyncio
import re
from EventManager import EventManager
from browser_manager import BrowserManager
from debug_ui import DebugUI
from logger import setup_logger
from priority_semaphore import PrioritySemaphore
from proxy_manager import ProxyManager
from playwright.async_api import async_playwright, Page, Playwright, Browser
from dotenv import load_dotenv


load_dotenv()

HEADLESS_MODE = True

async def main():

    manager = BrowserManager(max_browsers=10, events_per_browser=5)
    await manager.initialize()
    
    # Keep main running while there are active tasks
    while any(b.tasks for b in manager.active_browsers):
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main(), debug=True)