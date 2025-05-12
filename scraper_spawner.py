import asyncio
from browser_manager import BrowserManager
from dotenv import load_dotenv


load_dotenv(override=True)

HEADLESS_MODE = True

async def main():

    manager = BrowserManager(max_browsers=60, events_per_browser=2)
    await manager.initialize()
    
    # Keep main running while there are active tasks
    while any(b.tasks for b in manager.active_browsers):
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())