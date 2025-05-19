import asyncio
import os
import shutil
from scraper.managers.browser_manager import BrowserManager
from dotenv import load_dotenv


load_dotenv(override=True)

HEADLESS_MODE = True

async def main():

    # Housekeeping
    for dirname in ["logs", "fails"]:
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        os.makedirs(dirname)


    manager = BrowserManager(max_browsers=1, events_per_browser=50)
    await manager.initialize()
    
    # Keep main running while there are active tasks
    while any(b.tasks for b in manager.active_browsers):
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())