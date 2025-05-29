## Prerequisites
- Python 3.10+
- Python virtual environment

# How to run
## Platform specific
These steps differ on operating system used 

**Step 1**<br>
Clone the repository to your local machine

**Step 2**<br>
Create and activate python virtual environment inside extracted folder

**Step 3**<br>
Install playwright
Follow installation and getting started steps over here: 
[Playwright docs](https://playwright.dev/docs/getting-started-vscode)




## Platform Agnostic

**Step 4**<br>
Install requirements using `pip install -r requirements.txt` 

**Step 5**<br>
Create `.env` file according to the `.env-sample`. `.env` file MUST be name `.env` instead of `.env-sample`. 

**Step 6**<br>
Add/remove proxies to proxy_list

>*These commands must be called from inside the root directory*
>
>**Step 7**<br>
>Run the backend using `python -m backend.backend_main`
>
>**Step 8**<br>
>Run main scraper script using `python -m scraper_spawner`


# Configs

**proxy_list**

This file controls the proxies that will be used in the scraper.<br>
- Single proxy per line<br>
- Proxy format: `host:port:username:password`

**event_list**

This file contains all the events that should be scraped along with their respective webhook urls.<br>
- Single event url per line<br>
- Event url format: `event_url@webhook_url`

**.env**

Environment variables for the scraper

## Environment variables

>**`CONCURRENCY`**
>Controls how many pages are fetched and refreshed simultaneously. Some actions have higher priority than others, like fetching pages and 
>respawning previously closed pages. The ideal value depends on network conditions and CPU power allocated.

>**`DEFAULT_NAVIGATION_TIMEOUT`**
>Change this only if you know what you're doing. Increasing this may increase the time between reloads, and subsequently, reduce the resolution ( refreshes per unit time ) of the scraper. But may help in slow network / CPU bottlenecked situations


>**`CAPSOLVER_API_KEY`**
>Required for operation of the scraper. 


>**`BACKEND_BASEURL`**
>Do not change unless you know what you're doing. You shouldn't need to change this unless you're planning to decouple the backend and run it elsewhere



