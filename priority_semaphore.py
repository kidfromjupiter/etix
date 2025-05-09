import asyncio
import heapq
import itertools

class PrioritySemaphore:
    def __init__(self, value):
        self._semaphore = asyncio.Semaphore(value)
        self._wait_queue = []
        self._counter = itertools.count()
        self._lock = asyncio.Lock()

    async def acquire(self, priority=0):
        fut = asyncio.get_event_loop().create_future()
        count = next(self._counter)
        async with self._lock:
            heapq.heappush(self._wait_queue, (priority, count, fut))
        await self._dispatch()
        await fut

    def release(self):
        self._semaphore.release()
        asyncio.create_task(self._dispatch())

    async def _dispatch(self):
        async with self._lock:
            while self._wait_queue and self._semaphore._value > 0:
                _, _, fut = heapq.heappop(self._wait_queue)
                await self._semaphore.acquire()
                if not fut.done():
                    fut.set_result(None)

    # Async context manager with priority
    def priority(self, priority=0):
        return _PrioritySemaphoreContext(self, priority)


class _PrioritySemaphoreContext:
    def __init__(self, sem: PrioritySemaphore, priority: int):
        self._sem = sem
        self._priority = priority

    async def __aenter__(self):
        await self._sem.acquire(priority=self._priority)

    async def __aexit__(self, exc_type, exc, tb):
        self._sem.release()
