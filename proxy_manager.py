import asyncio
import logging
from typing import Dict, List, Optional, Set, Tuple
import httpx
from playwright.async_api import Browser, BrowserContext, Page, Response

import logger

class ProxyManager:
    def __init__(self, browser: Browser, proxies: List[Dict[str, str]], max_tabs_per_context: int = 10):
        """
        Initialize the ProxyManager with a Playwright Browser instance and a list of proxies.

        Args:
            browser: Playwright Browser instance
            proxies: List of proxy dictionaries with format:
                     [
                         {
                             "username": "user",
                             "server": "host:port",
                             "password": "pass"
                         },
                         ...
                     ]
            max_tabs_per_context: Maximum number of tabs allowed per browser context
        """
        self.browser = browser
        self.proxies = proxies
        self.max_tabs_per_context = max_tabs_per_context

        self.logger = logger.setup_logger("ProxyManager")
        self.logger.propagate = False
        # Disable httpx logs going to root logger (stdout)
        httpx_logger = logging.getLogger("httpx")
        httpx_logger.handlers = [logging.NullHandler()]
        httpx_logger.propagate = False

        # Track contexts and their associated proxies
        self.context_to_proxy: Dict[BrowserContext, Dict[str, str]] = {}
        self.proxy_to_contexts: Dict[tuple, List[BrowserContext]] = {
            self._proxy_to_key(proxy): [] for proxy in proxies
        }

        # Track tabs in each context
        self.context_to_tabs: Dict[BrowserContext, List[Page]] = {}

        # Preventing race conditions between other tasks requesting proxies that are already being assigned
        self.proxy_assignment_lock = asyncio.Lock()
        self.proxies_being_assigned: Set[tuple] = set()
        self.context_management_lock = asyncio.Lock()


        self.logger.info("Starting up...")

    def _proxy_to_key(self, proxy: Dict[str, str]) -> tuple:
        """Convert proxy dict to a tuple for use as dictionary key."""
        return (proxy["server"], proxy.get("username"), proxy.get("password"))

    def _proxy_to_playwright_format(self, proxy: Dict[str, str]) -> Dict[str, str]:
        """Convert our proxy format to Playwright's expected format."""
        pw_proxy = {"server": proxy["server"]}
        if "username" in proxy:
            pw_proxy["username"] = proxy["username"]
        if "password" in proxy:
            pw_proxy["password"] = proxy["password"]
        return pw_proxy

    async def _create_context_with_proxy(self, proxy: Dict[str, str]) -> BrowserContext:
        """Create a new browser context with the given proxy."""
        pw_proxy = self._proxy_to_playwright_format(proxy)
        context = await self.browser.new_context(proxy=pw_proxy)
        self.context_to_proxy[context] = proxy
        self.proxy_to_contexts[self._proxy_to_key(proxy)].append(context)
        self.context_to_tabs[context] = []
        return context

    def _get_available_proxies(self) -> List[Dict[str, str]]:
        """Get proxies that don't have any contexts assigned yet."""
        return [
            proxy for proxy in self.proxies 
            if not self.proxy_to_contexts[self._proxy_to_key(proxy)]
        ]

    def _get_least_loaded_context(self) -> BrowserContext:
        """Get the context with the fewest tabs across all proxies."""
        if not self.context_to_proxy:
            raise ValueError("No contexts available")
        return min(self.context_to_proxy.keys(), key=lambda ctx: len(self.context_to_tabs[ctx]))

    def _get_available_context_for_proxy(self, proxy: Dict[str, str]) -> Optional[BrowserContext]:
        """Get an available context for the specified proxy."""
        for context in self.proxy_to_contexts[self._proxy_to_key(proxy)]:
            return context
        return None

    async def get_or_create_context(self, proxy: Optional[Dict[str, str]] = None) -> BrowserContext:
        """
        Get or create an appropriate context following the specified logic:
        1. If proxy is specified:
           - Try to find available context for that proxy
           - If none available, create new context for that proxy
        2. If no proxy specified:
           - First check for proxies with no contexts and create one
           - If all proxies have contexts, use the least loaded context
        """
        # If proxy is specified
        if proxy:
            if proxy not in self.proxies:
                raise ValueError(f"Proxy {proxy} not in proxy list")

            # Try to find available context for this proxy
            available_ctx = self._get_available_context_for_proxy(proxy)
            if available_ctx:
                return available_ctx

            # If none available, create new context for this proxy
            return await self._create_context_with_proxy(proxy)

        # If no proxy specified
        # First check for proxies with no contexts
        available_proxies = self._get_available_proxies()
        if available_proxies:
            for proxy in available_proxies:
                proxy_key = self._proxy_to_key(proxy)


                async with self.proxy_assignment_lock:
                    if proxy_key in self.proxies_being_assigned: # prevent race conditions when checking proxies
                        continue
                    self.proxies_being_assigned.add(proxy_key)
                if await self.check_proxy(proxy):
                    # Create context for checked available proxy
                    self.logger.info("Found a proxy. Creating context...")
                    return await self._create_context_with_proxy(proxy)
                else:
                    # proxy failed check
                    self.logger.warning(f"Proxy {proxy['server']} not working! Moving to next proxy")
                    self.proxies.append(self.proxies.pop(self.proxies.index(proxy)))
        else:
            self.logger.warning("No more proxies available!")

        # All proxies have contexts - use least loaded one
        while True:
            async with self.proxy_assignment_lock:
                if not self.proxies_being_assigned:
                    break
            await asyncio.sleep(0.1)  # small backoff

        return self._get_least_loaded_context()

    async def create_tab(self, proxy: Optional[Dict[str, str]] = None, url: Optional[str] = None) -> Page:
        """
        Create a new tab following the specified logic:
        1. Get or create appropriate context
        2. If context is at max capacity, create new context (for same proxy if specified)
        3. Create new tab in selected context
        """

        # If context is at max capacity, create new one
        async with self.context_management_lock:
            context = await self.get_or_create_context(proxy)
            if len(self.context_to_tabs[context]) >= self.max_tabs_per_context:
                proxy_for_new = proxy if proxy else self.context_to_proxy[context]
                context = await self._create_context_with_proxy(proxy_for_new)

            page = await context.new_page()
            self.context_to_tabs[context].append(page)

        if url:
            await page.goto(url)

        return page

    async def close_tab(self, page: Page) -> None:
        """Close a specific tab and clean up if its context becomes empty."""
        context = None
        async with self.context_management_lock:
            for ctx, tabs in self.context_to_tabs.items():
                if page in tabs:
                    context = ctx
                    break

        if not context:
            self.logger.error("Page not found in any managed context. Probably already closed")
            return

        async with self.context_management_lock:
            self.context_to_tabs[context].remove(page)
            await page.close()

            # If context is now empty and we have more contexts for this proxy than needed, close it
            proxy_key = self._proxy_to_key(self.context_to_proxy[context])
            if (not self.context_to_tabs[context] and
                    len(self.proxy_to_contexts[proxy_key]) > 1):
                await self.close_context(context)

    async def close_context(self, context: BrowserContext) -> None:
        """Close a browser context and clean up tracking."""
        if context not in self.context_to_proxy:
            self.logger.error("Context not managed by this ProxyManager. Probably already closed")
            return

        async with self.context_management_lock:
            # Close all tabs in this context first
            for page in self.context_to_tabs[context][:]:
                await page.close()

            # Clean up tracking
            proxy = self.context_to_proxy[context]
            proxy_key = self._proxy_to_key(proxy)
            self.proxy_to_contexts[proxy_key].remove(context)
            del self.context_to_proxy[context]
            del self.context_to_tabs[context]

        await context.close()

    async def check_proxy(self, proxy: Dict[str, str]) -> bool:
        try:
            proxy_url = f"http://{proxy['username']}:{proxy['password']}@{proxy['server'][7:]}"
            async with httpx.AsyncClient(proxy=proxy_url, timeout=5) as client:
                response = await client.get("https://api.ipify.org/?format=json")
                async with self.proxy_assignment_lock:
                    self.proxies_being_assigned.discard(self._proxy_to_key(proxy))
                if response.status_code == 200:
                    self.logger.info(f"Proxy {proxy['server']} is working. IP: {response.json().get('ip')}")
                    return True
                else:
                    return False
            return True
        except Exception as e:
            async with self.proxy_assignment_lock:
                self.proxies_being_assigned.discard(self._proxy_to_key(proxy))
            self.logger.warning(f"Proxy check failed for {proxy['server']}: {e}")
            return False
