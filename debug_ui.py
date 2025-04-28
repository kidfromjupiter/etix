import asyncio

class DebugUI:
    def __init__(self):
        self.area_status = {}
        self._lock = asyncio.Lock()
        self._running = True

    async def update_status(self, area_number, status):
        async with self._lock:
            self.area_status[area_number] = status

    async def stop(self):
        self._running = False

    async def run(self):
        while self._running:
            await asyncio.sleep(1)
            async with self._lock:
                self._draw()

    def _draw(self):
        print("\033c", end="")  # Clear terminal
        print("===== Status =====")
        for area, status in sorted(self.area_status.items()):
            print(f"{area}: {status}")


