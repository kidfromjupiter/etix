from typing import Callable, Dict
from textual.app import App, ComposeResult
from textual.widgets import TabbedContent, TabPane, DataTable, Header, Footer, Label, Static
from textual.containers import Container
from datetime import datetime
from collections import defaultdict
import asyncio

class ContextStatsWidget(Static):
    def __init__(self):
        super().__init__()
        self.label = Label()
        self.total_tabs = 0
        self.avg_tabs_per_proxy = 0.0

    def compose(self) -> ComposeResult:
        yield Label("Context Stats", id="context-stats-label")
        yield self.label

    def update_stats(self, total_tabs: int, avg_tabs_per_proxy: float):
        self.total_tabs = total_tabs
        self.avg_tabs_per_proxy = avg_tabs_per_proxy
        self.label.update(
            f"Total Tabs: {self.total_tabs} | "
            f"Avg Tabs per Proxy: {self.avg_tabs_per_proxy:.2f}"
        )


class EventTab(TabPane):
    def __init__(self, event_id: str):
        truncated_name = (event_id[30:67] + "...") if len(event_id) > 40 else event_id
        super().__init__(truncated_name)
        self.event_id = event_id
        self.table = DataTable(zebra_stripes=True)
        self.table.add_columns("Area", "Status", "Last Updated")
        self._latest_context_stats = {"total_tabs": 0, "avg_tabs_per_proxy": 0.0}

    def compose(self) -> ComposeResult:
        yield self.table

    def update_table(self, areas: dict):
        self.table.clear()
        now = datetime.now()
        for area, (status, timestamp) in sorted(areas.items()):
            seconds_ago = int((now - timestamp).total_seconds())
            self.table.add_row(str(area), status, f"{seconds_ago}s ago")

class DebugUI(App):
    CSS_PATH = None
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "toggle_context_stats", "Toggle Context Stats")
    ]

    def __init__(self):
        super().__init__()
        self._event_status = defaultdict(dict)  # event_id -> {area_number: (status, timestamp)}
        self._lock = asyncio.Lock()
        self._running = True
        self._tab_panes = {}
        self._context_stats_widget = None
        self._latest_context_stats = {"total_tabs": 0, "avg_tabs_per_proxy": 0.0}

    async def update_status(self, event_id, area_number, status):
        async with self._lock:
            self._event_status[event_id][area_number] = (status, datetime.now())

    async def stop(self):
        self._running = False
        self.exit()

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            self._tabs = TabbedContent()
            yield self._tabs
        yield Footer()

    async def on_mount(self):
        self.set_interval(0.5, self.refresh_tabs)

    def action_toggle_context_stats(self):
        if self._context_stats_widget:
            self._context_stats_widget.remove()
            self._context_stats_widget = None
        else:
            self._context_stats_widget = ContextStatsWidget()
            self.mount(self._context_stats_widget, after=self.query_one(Header))
            stats = self._latest_context_stats
            self._context_stats_widget.update_stats(stats["total_tabs"], stats["avg_tabs_per_proxy"])

    def update_context_stats_widget(self, total_tabs: int, avg_tabs_per_proxy: float):
        self._latest_context_stats = {
            "total_tabs": total_tabs,
            "avg_tabs_per_proxy": avg_tabs_per_proxy
        }

        if self._context_stats_widget:
            self._context_stats_widget.update_stats(total_tabs, avg_tabs_per_proxy)

    async def refresh_tabs(self):
        async with self._lock:
            snapshot = dict(self._event_status)

        for event_id, areas in snapshot.items():
            if event_id not in self._tab_panes:
                tab = EventTab(event_id)
                self._tab_panes[event_id] = tab
                self._tabs.add_pane(tab)

            self._tab_panes[event_id].update_table(areas)

        current_ids = set(snapshot.keys())
        for stale_id in list(self._tab_panes.keys()):
            if stale_id not in current_ids:
                self._tabs.remove_pane(self._tab_panes[stale_id])
                del self._tab_panes[stale_id]

