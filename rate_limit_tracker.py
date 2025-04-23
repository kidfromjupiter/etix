import asyncio
from playwright.async_api import async_playwright, Page
import time


class RateLimitTester:
    def __init__(self, url):
        self.url = url
        self.results = []
        self.successful_requests = 0
        self.failed_requests = 0

    async def make_request(self, page: Page, request_num):
        start_time = time.time()
        try:
            response = await page.goto(self.url, timeout=10000)
            await page.wait_for_load_state("networkidle")
            status = response.status
            if status == 200:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            elapsed_time = time.time() - start_time
            self.results.append((request_num, elapsed_time, status))
            print(f"Request {request_num}: Status {status}, Time {elapsed_time:.2f}s")
        except Exception as e:
            elapsed_time = time.time() - start_time
            self.failed_requests += 1
            self.results.append((request_num, elapsed_time, str(e)))
            print(f"Request {request_num}: Failed with {str(e)}")

    async def run_test(self, num_requests, delay_ms=0):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()

            # Create initial page
            page = await context.new_page()

            for i in range(1, num_requests + 1):
                # Create a new tab for each request
                if i > 1:
                    page = await context.new_page()

                await self.make_request(page, i)

                # Close the tab (except the last one)
                if i < num_requests:
                    await page.close()

                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

            await browser.close()

    def generate_report(self):
        print("\n=== Rate Limit Test Report ===")
        print(f"Total Requests: {len(self.results)}")
        print(f"Successful: {self.successful_requests}")
        print(f"Failed: {self.failed_requests}")

        # Calculate requests per minute
        if len(self.results) >= 2:
            total_time = self.results[-1][1] - self.results[0][1]
            rpm = len(self.results) / (total_time / 60)
            print(f"Approximate Request Rate: {rpm:.2f} requests per minute")

async def main():
    url = "https://www.etix.com/ticket/p/78414997/alison-krauss-union-station-featuring-jerry-douglas-redding-redding-civic-auditorium?clickref=1011lArps4TX"

    print("Starting rate limit test...")

    # First test - rapid requests to find initial limits
    tester = RateLimitTester(url)
    await tester.run_test(num_requests=20, delay_ms=100)  # 10 requests per second

    # Second test - slower pace if first test hits limits
    if tester.failed_requests > 5:
        print("\nFirst test hit rate limits, running slower test...")
        tester = RateLimitTester(url)
        await tester.run_test(num_requests=30, delay_ms=500)  # 2 requests per second

    tester.generate_report()


if __name__ == "__main__":
    asyncio.run(main())