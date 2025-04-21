import asyncio
from playwright.async_api import async_playwright
from datetime import datetime


async def test_rate_limits_with_tabs(base_url, max_tabs=5, headless=True):
    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        # Test increasing numbers of tabs
        for num_tabs in range(1, max_tabs + 1):
            print(f"\n🔍 Testing with {num_tabs} tabs...")
            tabs = []
            rate_limit_hit = False
            captcha_detected = False
            retry_after = None

            # Open tabs
            for _ in range(num_tabs):
                tab = await context.new_page()
                tabs.append(tab)


                # Monitor responses in each tab
                tab.on('response', lambda response: (
                        print(f"[Tab {len(tabs)}] Status: {response.status}") or
                        handle_response(response)
                ))

                def handle_response(response):
                    nonlocal rate_limit_hit, captcha_detected, retry_after
                    if response.status == 429:
                        rate_limit_hit = True
                        retry_after = response.headers.get('retry-after', 5)
                    if "captcha" in response.url.lower():
                        captcha_detected = True

            # Navigate all tabs to the target URL
            start_time = datetime.now()
            await asyncio.gather(*[tab.goto(base_url) for tab in tabs])

            # Check for visual CAPTCHAs
            for tab in tabs:
                if await tab.query_selector('iframe[src*="recaptcha"]'):
                    captcha_detected = True

            # Record results
            results[num_tabs] = {
                'time': (datetime.now() - start_time).total_seconds(),
                'rate_limit': rate_limit_hit,
                'captcha': captcha_detected,
                'retry_after': retry_after
            }

            # Cleanup
            await asyncio.gather(*[tab.close() for tab in tabs])

            if rate_limit_hit or captcha_detected:
                print(f"⛔ Blocked at {num_tabs} tabs")
                break

        await browser.close()

    return results


async def main():
    target_url = "https://www.etix.com/ticket/p/78414997/alison-krauss-union-station-featuring-jerry-douglas-redding-redding-civic-auditorium?clickref=1011lArps4TX"  # Replace with your target
    results = await test_rate_limits_with_tabs(target_url, max_tabs=5)

    print("\n📊 Results:")
    for num_tabs, data in results.items():
        print(f"{num_tabs} tabs: "
              f"Time={data['time']:.2f}s | "
              f"RateLimited={data['rate_limit']} | "
              f"CAPTCHA={data['captcha']} | "
              f"RetryAfter={data.get('retry_after', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())