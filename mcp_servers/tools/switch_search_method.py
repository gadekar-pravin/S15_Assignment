import random
import asyncio
import httpx
from typing import List
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import urllib.parse
import time
from playwright.async_api import async_playwright
import sys

# MCP Protocol Safety: Redirect print to stderr
def print(*args, **kwargs):
    sys.stderr.write(" ".join(map(str, args)) + "\n")
    sys.stderr.flush()

SEARCH_ENGINES = [
    "duck_http",
    "duck_playwright",
    "bing_playwright",
    "yahoo_playwright",
    "ecosia_playwright",
    "mojeek_playwright"
]

class RateLimiter:
    """
    A simple rate limiter to prevent making requests too frequently to the same engine.
    """
    def __init__(self, cooldown_seconds=2):
        """
        Initializes the RateLimiter.

        Args:
            cooldown_seconds (int, optional): Minimum time in seconds between requests to the same key. Defaults to 2.
        """
        # Use monotonic time for stable cooldown behavior even if system clock changes
        self.cooldown_seconds = float(cooldown_seconds)
        self.last_called = {}  # key -> monotonic timestamp
        self._lock = asyncio.Lock()

    async def acquire(self, key: str):
        """
        Acquires permission to proceed for a given key. Sleeps if within the cooldown period.

        Args:
            key (str): The identifier for the resource (e.g., search engine name).
        """
        # Concurrency-safe: ensure cooldown is enforced even with parallel calls
        async with self._lock:
            now = time.monotonic()
            last = self.last_called.get(key)
            if last is not None:
                elapsed = now - last
                if elapsed < self.cooldown_seconds:
                    wait = self.cooldown_seconds - elapsed
                    print(f"Rate limiting {key}, sleeping for {wait:.1f}s")
                    await asyncio.sleep(wait)
                    now = time.monotonic()
            self.last_called[key] = now

rate_limiter = RateLimiter(cooldown_seconds=2)

def get_random_headers():
    """
    Generates random HTTP headers to mimic a real browser.

    Returns:
        dict: Headers dictionary.
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 Chrome/113.0.5672.92 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/605.1.15 Version/16.3 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 Chrome/117.0.5938.132 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-G998B) AppleWebKit/537.36 Chrome/92.0.4515.159 Mobile Safari/537.36 SamsungBrowser/15.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 Version/16.6 Mobile Safari/604.1"
    ]
    return {"User-Agent": random.choice(user_agents)}

async def use_duckduckgo_http(query: str) -> List[str]:
    """
    Performs a search using DuckDuckGo HTML interface via HTTP requests.

    Args:
        query (str): The search query.

    Returns:
        List[str]: A list of result URLs.
    """
    await rate_limiter.acquire("duck_http")
    url = "https://html.duckduckgo.com/html"
    headers = get_random_headers()
    data = {"q": query}

    print(f"[duck_http] 🔍 Searching for: {query!r}")
    print(f"[duck_http] 📡 Request URL: {url}")
    print(f"[duck_http] 🎭 User-Agent: {headers.get('User-Agent', 'N/A')[:50]}...")

    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.post(url, data=data, headers=headers)
        r.raise_for_status()

        # Log response details
        print(f"[duck_http] ✅ HTTP Status: {r.status_code}")
        print(f"[duck_http] 📄 Response length: {len(r.text)} characters")
        print(f"[duck_http] 🔗 Final URL (after redirects): {r.url}")

        # Log HTML preview
        html_preview = r.text[:800].replace('\n', ' ')
        print(f"[duck_http] 📋 HTML Preview (first 800 chars):\n{html_preview}")

        soup = BeautifulSoup(r.text, "html.parser")

        # Check for common anti-bot indicators
        if "captcha" in r.text.lower():
            print("[duck_http] ⚠️  CAPTCHA detected in response")
        if "unusual traffic" in r.text.lower():
            print("[duck_http] ⚠️  'Unusual traffic' message detected")
        if "javascript" in r.text.lower() and "enable" in r.text.lower():
            print("[duck_http] ⚠️  JavaScript enable message detected")

        # Try to find result containers with multiple selectors
        result_selectors = [
            "a.result__a",           # Current selector
            "div.result__body a",    # Alternative
            "a[class*='result']",    # Wildcard
            "div[class*='result'] a" # Broader wildcard
        ]

        print(f"[duck_http] 🔎 Testing {len(result_selectors)} different selectors...")
        for selector in result_selectors:
            found = soup.select(selector)
            print(f"[duck_http]    - '{selector}': {len(found)} elements found")

        links = []
        seen = set()

        result_elements = soup.select("a.result__a")
        print(f"[duck_http] 🎯 Using primary selector 'a.result__a': {len(result_elements)} elements")

        for idx, a in enumerate(result_elements):
            href = a.get("href", "")
            print(f"[duck_http]    [{idx+1}] Raw href: {href[:100] if href else '(empty)'}")

            if not href:
                print(f"[duck_http]    [{idx+1}] ❌ Skipped: empty href")
                continue
            if "uddg=" in href:
                parts = href.split("uddg=")
                if len(parts) > 1:
                    decoded = urllib.parse.unquote(parts[1].split("&")[0])
                    print(f"[duck_http]    [{idx+1}] 🔓 Decoded uddg: {decoded[:80]}")
                    href = decoded
            if href.startswith("http") and href not in seen:
                seen.add(href)
                links.append(href)
                print(f"[duck_http]    [{idx+1}] ✅ Added: {href[:80]}")
            else:
                reason = "duplicate" if href in seen else "not http URL"
                print(f"[duck_http]    [{idx+1}] ⏭️  Skipped: {reason}")

        print(f"[duck_http] 📊 Final result: {len(links)} unique URLs extracted")
        if not links:
            print("[duck_http] ⚠️  No links found in results - possible parsing failure")
            # Save HTML to file for debugging
            try:
                debug_file = f"/tmp/duckduckgo_debug_{int(time.time())}.html"
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(r.text)
                print(f"[duck_http] 💾 Saved full HTML response to: {debug_file}")
            except Exception as e:
                print(f"[duck_http] ⚠️  Could not save debug HTML: {e}")

        return links

async def use_playwright_search(query: str, engine: str) -> List[str]:
    """
    Performs a search using a headless browser (Playwright) on various search engines.
    Useful when simple HTTP requests are blocked or require JS.

    Args:
        query (str): The search query.
        engine (str): The identifier of the search engine to use (e.g., 'duck_playwright').

    Returns:
        List[str]: A list of result URLs.
    """
    await rate_limiter.acquire(engine)
    print(f"[{engine}] 🌐 Starting Playwright browser search for: {query!r}")
    urls = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # changed to headless=True for stability
        page = await browser.new_page()
        print(f"[{engine}] 🚀 Browser launched, page created")

        try:
            engine_url_map = {
                "duck_playwright": "https://html.duckduckgo.com/html",
                "bing_playwright": "https://www.bing.com/search",
                "yahoo_playwright": "https://search.yahoo.com/search",
                "ecosia_playwright": "https://www.ecosia.org/search",
                "mojeek_playwright": "https://www.mojeek.com/search"
            }

            q = urllib.parse.quote_plus(query)
            search_url = f"{engine_url_map[engine]}?q={q}"
            print(f"[{engine}] 🔗 Navigating to {search_url}")
            await page.goto(search_url, timeout=15000)
            print(f"[{engine}] ✅ Page loaded, waiting 2 seconds for JS...")
            await asyncio.sleep(2)

            # Determine selector based on engine
            selector_map = {
                "duck_playwright": "a.result__a",
                "bing_playwright": "li.b_algo h2 a",
                "yahoo_playwright": "div.compTitle h3.title a",
                "ecosia_playwright": "a.result__link",
                "mojeek_playwright": "a.title",
            }

            if engine == "duck_playwright":
                selector = "a.result__a"
                print(f"[{engine}] 🔍 Waiting for selector '{selector}'...")
                await page.wait_for_selector(selector, timeout=10000)
                results = await page.query_selector_all(selector)

            elif engine == "bing_playwright":
                selector = "li.b_algo h2 a"
                print(f"[{engine}] 🔍 Querying for selector '{selector}'...")
                results = await page.query_selector_all(selector)

            elif engine == "yahoo_playwright":
                selector = "div.compTitle h3.title a"
                print(f"[{engine}] 🔍 Querying for selector '{selector}'...")
                results = await page.query_selector_all(selector)

            elif engine == "ecosia_playwright":
                selector = "a.result__link"
                print(f"[{engine}] 🔍 Waiting for selector '{selector}'...")
                await page.wait_for_selector(selector, timeout=10000)
                results = await page.query_selector_all(selector)

            elif engine == "mojeek_playwright":
                selector = "a.title"
                print(f"[{engine}] 🔍 Waiting for selector '{selector}'...")
                await page.wait_for_selector(selector, timeout=10000)
                results = await page.query_selector_all(selector)

            else:
                print(f"[{engine}] ❌ Unknown engine")
                return []

            print(f"[{engine}] 📊 Found {len(results)} result elements")

            if not results:
                print(f"[{engine}] ⚠️  No URLs found — possibly blocked or CAPTCHA. Retrying...")
                # In headless mode, CAPTCHAs cannot be solved interactively; do a short retry then bail.
                await asyncio.sleep(2)
                sel = selector_map.get(engine)
                if sel:
                    print(f"[{engine}] 🔄 Retry: querying '{sel}' again...")
                    results = await page.query_selector_all(sel)
                    print(f"[{engine}] 📊 Retry found {len(results)} elements")

            seen = set()
            for idx, r in enumerate(results):
                try:
                    href = await r.get_attribute("href")
                    print(f"[{engine}]    [{idx+1}] Raw href: {href[:100] if href else '(empty)'}")

                    if not href:
                        print(f"[{engine}]    [{idx+1}] ⏭️  Skipped: empty href")
                        continue
                    if "uddg=" in href:
                        parts = href.split("uddg=")
                        if len(parts) > 1:
                            decoded = urllib.parse.unquote(parts[1].split("&")[0])
                            print(f"[{engine}]    [{idx+1}] 🔓 Decoded uddg: {decoded[:80]}")
                            href = decoded
                    if href.startswith("http") and href not in seen:
                        seen.add(href)
                        urls.append(href)
                        print(f"[{engine}]    [{idx+1}] ✅ Added: {href[:80]}")
                    else:
                        reason = "duplicate" if href in seen else "not http URL"
                        print(f"[{engine}]    [{idx+1}] ⏭️  Skipped: {reason}")
                except Exception as e:
                    print(f"[{engine}]    [{idx+1}] ❌ Error: {e}")
        except Exception as e:
            print(f"[{engine}] ❌ Error while processing: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()
            print(f"[{engine}] 🔒 Browser closed")

    print(f"[{engine}] 📊 Final result: {len(urls)} URLs extracted")
    if not urls:
        print(f"[{engine}] ⚠️  Still no URLs found after retry.")

    return urls

async def smart_search(query: str, limit: int = 5) -> List[str]:
    """
    Performs a robust search by trying multiple engines in random order.
    Attempts to bypass blocks and fall back to different providers.

    Args:
        query (str): The search query.
        limit (int, optional): Maximum number of results to return. Defaults to 5.

    Returns:
        List[str]: A list of result URLs.
    """
    print(f"\n{'='*80}")
    print(f"🔍 SMART_SEARCH: Starting search orchestration")
    print(f"📝 Query: {query!r}")
    print(f"📊 Requested limit: {limit}")
    print(f"{'='*80}\n")

    query = (query or "").strip()
    if not query:
        print("⚠️  SMART_SEARCH: Empty query provided, returning []")
        return []

    # Avoid mutating the global list (thread/concurrency safe).
    # Prefer cheap HTTP first, then randomized fallbacks.
    fallbacks = [e for e in SEARCH_ENGINES if e != "duck_http"]
    engines = ["duck_http"] + random.sample(fallbacks, k=len(fallbacks))

    print(f"🎲 SMART_SEARCH: Engine order: {engines}\n")

    for idx, engine in enumerate(engines, 1):
        print(f"\n{'─'*80}")
        print(f"🚀 SMART_SEARCH: Attempt {idx}/{len(engines)} - Trying engine: {engine}")
        print(f"{'─'*80}")
        try:
            if engine == "duck_http":
                # Only use duck_http for first attempt if query likely to succeed
                timeout_val = 20
                print(f"⏱️  SMART_SEARCH: Using duck_http with {timeout_val}s timeout")
                results = await asyncio.wait_for(use_duckduckgo_http(query), timeout=timeout_val)
            else:
                timeout_val = 25
                print(f"⏱️  SMART_SEARCH: Using {engine} with {timeout_val}s timeout")
                results = await asyncio.wait_for(use_playwright_search(query, engine), timeout=timeout_val)

            print(f"✅ SMART_SEARCH: {engine} returned {len(results) if results else 0} results")

            if results:
                limited_results = results[:limit]
                print(f"🎉 SMART_SEARCH: SUCCESS! Returning {len(limited_results)} results (limit={limit})")
                print(f"📋 URLs returned:")
                for i, url in enumerate(limited_results, 1):
                    print(f"   {i}. {url}")
                print(f"\n{'='*80}\n")
                return limited_results
            else:
                print(f"⚠️  SMART_SEARCH: {engine} returned empty results. Trying next...")
        except asyncio.TimeoutError:
            print(f"⏱️  SMART_SEARCH: {engine} timed out after {timeout_val}s. Trying next...")
        except Exception as e:
            print(f"❌ SMART_SEARCH: {engine} failed with error: {e}")
            import traceback
            traceback.print_exc()
            print(f"   Trying next engine...")

    print(f"\n{'='*80}")
    print(f"❌ SMART_SEARCH: All {len(engines)} engines failed - returning empty list")
    print(f"{'='*80}\n")
    return []

if __name__ == "__main__":
    query = "Model Context Protocol"
    results = asyncio.run(smart_search(query))
    print("\n[URLs]:")
    for url in results:
        print("-", url)
