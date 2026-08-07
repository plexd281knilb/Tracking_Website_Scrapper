import httpx
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Any
from urllib.parse import urljoin
from app.scrapers.base import DEFAULT_HEADERS, matches_filter_rules

logger = logging.getLogger(__name__)


class GoodyGoodyScraper:
    def __init__(self, url: str, include_keywords: str = "", exclude_keywords: str = ""):
        self.url = url or "https://www.goodygoody.com"
        self.include_keywords = include_keywords
        self.exclude_keywords = exclude_keywords

    def scrape(self) -> List[Dict[str, Any]]:
        results = []
        logger.info(f"Fetching Goody Goody URL: {self.url}")
        
        html_content = ""

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=12.0, follow_redirects=True, verify=False) as client:
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
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(viewport={"width": 1280, "height": 800})
                    page = context.new_page()
                    page.goto(self.url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    html_content = page.content()
                    browser.close()
            except Exception as pe:
                logger.error(f"Playwright fallback failed for Goody Goody: {pe}")

        if not html_content:
            return results

        soup = BeautifulSoup(html_content, "html.parser")
        cards = soup.select(".product-card, .product-item, .search-result-item, .card, [data-product-id]")
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
            in_stock_indicators = ["in stock", "add to cart", "pick up", "deliver"]

            is_out_of_stock = any(indicator in card_text for indicator in out_of_stock_indicators)
            is_in_stock = any(indicator in card_text for indicator in in_stock_indicators) or not is_out_of_stock

            is_match, reason = matches_filter_rules(title, self.include_keywords, self.exclude_keywords)
            if not is_match:
                continue

            results.append({
                "title": title,
                "price": price,
                "in_stock": is_in_stock,
                "url": full_url,
                "store_location": "Goody Goody Online / Store",
                "retailer": "goody_goody"
            })

        return results
