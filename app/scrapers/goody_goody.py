import httpx
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Any
from urllib.parse import urljoin
from app.scrapers.base import DEFAULT_HEADERS, is_safe_public_url, matches_filter_rules

logger = logging.getLogger(__name__)


class GoodyGoodyScraper:
    def __init__(self, url: str, include_keywords: str = "", exclude_keywords: str = ""):
        self.url = url or "https://www.goodygoody.com"
        self.include_keywords = include_keywords
        self.exclude_keywords = exclude_keywords

    def scrape(self) -> List[Dict[str, Any]]:
        raw_results = []
        if not is_safe_public_url(self.url):
            logger.warning(f"Blocked unsafe tracker URL: {self.url}")
            return raw_results
        logger.info(f"Fetching Goody Goody URL: {self.url}")

        html_content = ""

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

        try:
            with httpx.Client(headers=headers, timeout=12.0, follow_redirects=True, verify=True) as client:
                response = client.get(self.url)
                if response.status_code == 200:
                    html_content = response.text
                else:
                    logger.warning(f"Goody Goody HTTP {response.status_code}. Trying Playwright fallback...")
        except Exception as e:
            logger.warning(f"Goody Goody HTTP error: {e}. Trying Playwright fallback...")

        if not html_content:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                    )
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        viewport={"width": 1366, "height": 768}
                    )
                    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                    page = context.new_page()
                    page.goto(self.url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(3000)
                    html_content = page.content()
                    browser.close()
                    logger.info("Successfully fetched Goody Goody via Playwright.")
            except Exception as pe:
                logger.error(f"Playwright fallback failed for Goody Goody: {pe}")

        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        cards = soup.select(".product-card, .product-item, .search-result-item, .card, [data-product-id], article, div[class*='product']")
        if not cards:
            cards = soup.select("a[href*='/product'], a[href*='/p/']")

        for card in cards:
            title_elem = card.select_one(".product-title, .title, .name, h2, h3, h4, .card-title") or card
            title = title_elem.get_text(strip=True) if title_elem else ""

            if not title or len(title) < 3:
                continue

            link_elem = card if card.name == "a" else card.select_one("a[href]")
            href = link_elem["href"] if link_elem and link_elem.has_attr("href") else self.url
            full_url = urljoin(self.url, href)

            price_elem = card.select_one(".price, .product-price, .amount, [data-price]")
            price = price_elem.get_text(strip=True) if price_elem else "N/A"

            card_text = card.get_text().lower()
            out_of_stock_indicators = ["out of stock", "sold out", "unavailable", "backordered"]
            is_out_of_stock = any(indicator in card_text for indicator in out_of_stock_indicators)
            is_in_stock = not is_out_of_stock

            is_match, reason = matches_filter_rules(title, self.include_keywords, self.exclude_keywords)
            if not is_match:
                continue

            raw_results.append({
                "title": title,
                "price": price,
                "in_stock": is_in_stock,
                "url": full_url,
                "store_location": "Goody Goody Online / Store",
                "retailer": "goody_goody"
            })

        # Deduplicate results by title
        dedup_map = {}
        for item in raw_results:
            title_key = item["title"].strip().lower()
            if title_key not in dedup_map:
                dedup_map[title_key] = item
            else:
                if dedup_map[title_key]["price"] == "N/A" and item["price"] != "N/A":
                    dedup_map[title_key] = item

        final_results = list(dedup_map.values())
        logger.info(f"Goody Goody scraper found {len(final_results)} unique matching items.")
        return final_results
