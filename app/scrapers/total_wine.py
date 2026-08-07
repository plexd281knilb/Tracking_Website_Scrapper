import httpx
from bs4 import BeautifulSoup
import logging
import json
from typing import List, Dict, Any
from urllib.parse import urljoin
from app.scrapers.base import DEFAULT_HEADERS, matches_filter_rules

logger = logging.getLogger(__name__)


class TotalWineScraper:
    def __init__(self, url: str, include_keywords: str = "", exclude_keywords: str = ""):
        self.url = url or "https://www.totalwine.com/spirits/bourbon/c/000887"
        self.include_keywords = include_keywords
        self.exclude_keywords = exclude_keywords

    def scrape(self) -> List[Dict[str, Any]]:
        results = []
        logger.info(f"Fetching Total Wine URL: {self.url}")

        html_content = ""

        # Strategy 1: Fast HTTP GET
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            with httpx.Client(headers=headers, timeout=12.0, follow_redirects=True, verify=False) as client:
                resp = client.get(self.url)
                if resp.status_code == 200:
                    html_content = resp.text
                else:
                    logger.warning(f"Total Wine HTTP returned status {resp.status_code}. Trying Playwright fallback...")
        except Exception as e:
            logger.warning(f"Total Wine HTTP request failed: {e}. Trying Playwright fallback...")

        # Strategy 2: Headless Browser Fallback if HTTP request blocked/failed
        if not html_content:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 800}
                    )
                    page = context.new_page()
                    page.goto(self.url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(3000)
                    html_content = page.content()
                    browser.close()
                    logger.info("Successfully fetched Total Wine page via Playwright.")
            except Exception as pe:
                logger.error(f"Playwright fallback failed for Total Wine: {pe}")

        if not html_content:
            return results

        soup = BeautifulSoup(html_content, "html.parser")

        # Parse JSON-LD scripts
        json_scripts = soup.find_all("script", type="application/ld+json")
        for script in json_scripts:
            try:
                data = json.loads(script.string or "{}")
                items = data.get("itemListElement", []) if isinstance(data, dict) else []
                for item in items:
                    prod_data = item.get("item", {})
                    title = prod_data.get("name", "")
                    if not title:
                        continue

                    is_match, reason = matches_filter_rules(title, self.include_keywords, self.exclude_keywords)
                    if not is_match:
                        continue

                    prod_url = prod_data.get("url", self.url)
                    offers = prod_data.get("offers", {})
                    price = f"${offers.get('price', 'N/A')}" if 'price' in offers else "N/A"
                    availability = str(offers.get("availability", "")).lower()
                    in_stock = "instock" in availability or "in_stock" in availability

                    results.append({
                        "title": title,
                        "price": price,
                        "in_stock": in_stock,
                        "url": prod_url,
                        "store_location": "Total Wine Store / Online",
                        "retailer": "total_wine"
                    })
            except Exception:
                pass

        # Parse DOM elements if JSON-LD yield nothing
        if not results:
            cards = soup.select("[data-at='product-card'], article, .productCard__1VzC1l1O, .product-card")
            if not cards:
                cards = soup.select("a[href*='/p/']")

            for card in cards:
                title_elem = card.select_one("[data-at='product-card-title'], .title, h2, h3, a") or card
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title or len(title) < 4:
                    continue

                is_match, reason = matches_filter_rules(title, self.include_keywords, self.exclude_keywords)
                if not is_match:
                    continue

                link_elem = card if card.name == "a" else card.select_one("a[href]")
                href = link_elem["href"] if link_elem and link_elem.has_attr("href") else self.url
                full_url = urljoin(self.url, href)

                price_elem = card.select_one("[data-at='product-card-price'], .price, .amount")
                price = price_elem.get_text(strip=True) if price_elem else "N/A"

                card_text = card.get_text().lower()
                is_out_of_stock = "out of stock" in card_text or "unavailable" in card_text
                in_stock = not is_out_of_stock

                results.append({
                    "title": title,
                    "price": price,
                    "in_stock": in_stock,
                    "url": full_url,
                    "store_location": "Total Wine Store",
                    "retailer": "total_wine"
                })

        return results
