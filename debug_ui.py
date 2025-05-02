from collections import defaultdict
from datetime import datetime
import asyncio
from rich.console import Console
from rich.table import Table
from rich.live import Live

class DebugUI:
    def __init__(self):
        self.event_status = defaultdict(dict)  # event_id -> {area_number: (status, timestamp)}
        self._lock = asyncio.Lock()
        self._running = True
        self.console = Console()

    async def update_status(self, event_id, area_number, status):
        async with self._lock:
            self.event_status[event_id][area_number] = (
                status, datetime.now()
            )

    async def stop(self):
        self._running = False

    def _build_table(self):
        table = Table(title="📊 Event Scraping Status", expand=True)

        table.add_column("Event ID", style="bold white")
        table.add_column("Area", justify="right", style="cyan", no_wrap=True)
        table.add_column("Status", style="magenta")
        table.add_column("Last Updated", style="green")

        now = datetime.now()
        for event_id in sorted(self.event_status.keys()):
            for area, (status, timestamp) in sorted(self.event_status[event_id].items()):
                seconds_ago = int((now - timestamp).total_seconds())
                time_display = f"{seconds_ago}s ago"
                table.add_row(str(event_id)[10:], str(area), status, time_display)

        return table

    async def run(self):
        with Live(self._build_table(), console=self.console, refresh_per_second=4) as live:
            while self._running:
                await asyncio.sleep(0.5)
                async with self._lock:
                    live.update(self._build_table())

