import asyncio
import re
from dataclasses import dataclass
from typing import List, Dict, Callable, Optional
import logging
from playwright.async_api import async_playwright, Browser, Playwright
from EventManager import EventManager
from debug_ui import DebugUI
from logger import setup_logger
from priority_semaphore import PrioritySemaphore
from proxy_manager import ProxyManager


HEADLESS_MODE = True
@dataclass
class BrowserInstance:
    playwright_instance: Playwright
    browser: Browser
    proxy_manager: ProxyManager
    tasks: List[asyncio.Task]
    event_urls: List[str]
    proxies: List[str]

class BrowserManager:
    def __init__(self, max_browsers: int = 3, events_per_browser: int = 5):
        self.max_browsers = max_browsers
        self.events_per_browser = events_per_browser
        self.active_browsers: List[BrowserInstance] = []
        self.all_event_urls: List[str] = []
        self.all_proxies: List[str] = []
        self.logger = setup_logger("BrowserManager", logfile='./logs/browser_manager.log')
        self.network_sem = PrioritySemaphore(8)
        self.debug_ui = DebugUI()
        self.loading_lock = asyncio.Semaphore(1)
        self.num_browsers: int = 0 
        self.playwright = None

    async def initialize(self):
        # Load proxies and event URLs
        await self._load_proxies()
        await self._load_event_urls()
        self.playwright = await async_playwright().start()
        #asyncio.create_task(self.debug_ui.run_async())
        
        # Calculate how many browsers we actually need
        num_browsers = min(
            self.max_browsers,
            len(self.all_event_urls) // (self.events_per_browser or 1) + 1
        )
        self.num_browsers = num_browsers
        
        # Start all browsers and distribute events immediately
        for _ in range(num_browsers):
            browser = await self._spawn_browser()
            if browser:
                await self._dispatch_events_to_browser(browser)
        
    async def _load_proxies(self):
        with open("proxy_list") as proxy_list:
            proxies = proxy_list.readlines()
            for proxy in proxies:
                pattern = r"(\d.+):(\w+):(\w+)"
                matches = re.search(pattern, proxy)
                self.all_proxies.append({
                    "server": f'http://{matches.group(1)}',
                    "username": matches.group(2),
                    "password": matches.group(3)
                })
    
    async def _load_event_urls(self):
        with open("event_list") as event_list:
            self.all_event_urls = [url.strip() for url in event_list if url.strip()]
    
    async def _spawn_browser(self) -> BrowserInstance:
        if len(self.active_browsers) >= self.max_browsers:
            self.logger.warning("Max browsers reached, not spawning new one")
            return None
            
        self.logger.info("Launching new browser...")
        browser = await self.playwright.chromium.launch(headless=HEADLESS_MODE)
        
        # proxy manager is setup later when dispatching events 

        # Create browser instance
        browser_instance = BrowserInstance(
            playwright_instance=self.playwright,
            browser=browser,
            proxy_manager=None,
            tasks=[],
            event_urls=[],
            proxies=[]
        )
        
        # Setup disconnect handler
        browser.on("disconnected", lambda: self._handle_browser_disconnect(browser_instance))
        
        self.active_browsers.append(browser_instance)
        return browser_instance
    
    def _handle_browser_disconnect(self, browser_instance: BrowserInstance):
        self.logger.error(f"Browser disconnected with {browser_instance.event_urls} events\n respawning...")
        
        # Remove from active browsers
        self.active_browsers.remove(browser_instance)
        
        # Cancel all ongoing tasks for this browser
        for task in browser_instance.tasks:
            task.cancel()
        
        # Respawn with the same event URLs
        asyncio.create_task(self._respawn_browser(browser_instance.event_urls, browser_instance.proxies))
    
    async def _respawn_browser(self, event_urls: List[str], proxies: List[str]):
        new_browser = await self._spawn_browser() # new browser doesn't come with event_urls
        if new_browser:
            new_browser.event_urls = event_urls
            await self._dispatch_events_to_browser(new_browser, event_urls, proxies)
        self.logger.info(f"Browser respawned with events {event_urls}")
    
    async def _dispatch_events_to_browser(self, browser_instance: BrowserInstance, event_urls: list[str] = [], proxies: List[str] = []):
        if not self.all_event_urls and not event_urls:
            return
            
        if event_urls: # this is a respawn. Just respawn all the event_urls in the prev browser
            browser_instance.event_urls.extend(event_urls)
            browser_instance.proxies.extend(proxies)
            browser_instance.proxy_manager = ProxyManager(browser_instance.browser, proxies) 
            for event_url in event_urls:
                task = asyncio.create_task(self._run_event_manager(
                    browser_instance.browser,
                    event_url, 
                    browser_instance.proxy_manager,
                    lambda url=event_url: self.logger.info(f"Initial loading complete! {url}")
                ))
                browser_instance.tasks.append(task)

            return
        
        # Calculate how many events to assign to this browser
        if self.events_per_browser is None:
            # Distribute events evenly across all browsers
            events_per_browser = len(self.all_event_urls) // self.num_browsers + 1
        else:
            events_per_browser = self.events_per_browser

        # Calculate how many proxies to assign to this browser
        proxies_per_browser = len(self.all_proxies) // self.num_browsers + 1
            
        events_to_dispatch = self.all_event_urls[:events_per_browser]
        self.all_event_urls = self.all_event_urls[events_per_browser:]

        proxies_to_dispatch = self.all_proxies[:proxies_per_browser]
        self.all_proxies = self.all_proxies[proxies_per_browser:]

        browser_instance.event_urls.extend(events_to_dispatch)
        browser_instance.proxies.extend(proxies_to_dispatch)

        browser_instance.proxy_manager = ProxyManager(browser_instance.browser, proxies_to_dispatch) 
        for event_url in events_to_dispatch:
            task = asyncio.create_task(self._run_event_manager(
                browser_instance.browser,
                event_url, 
                browser_instance.proxy_manager,
                lambda url=event_url: self.logger.info(f"Initial loading complete! {url}")
            ))
            browser_instance.tasks.append(task)
    
    async def _run_event_manager(self,browser:Browser, event_url: str, proxy_manager: ProxyManager, callback: Callable):
        manager = EventManager(
            event_url,
            browser,
            proxy_manager,
            self.debug_ui,
            self.network_sem,
            callback
        )
        return await manager.run()

async def main():
    manager = BrowserManager(max_browsers=3, events_per_browser=5)
    await manager.initialize()
    
    # Keep main running while there are active tasks
    while any(b.tasks for b in manager.active_browsers):
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())