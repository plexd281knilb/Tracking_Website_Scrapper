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

        # Strategy 1: Mobile User Agent HTTP Request
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }

        try:
            with httpx.Client(headers=headers, timeout=15.0, follow_redirects=True, verify=False) as client:
                resp = client.get(self.url)
                if resp.status_code == 200:
                    html_content = resp.text
                else:
                    logger.warning(f"Total Wine HTTP status {resp.status_code}. Trying Playwright fallback...")
        except Exception as e:
            logger.warning(f"Total Wine HTTP request failed: {e}. Trying Playwright fallback...")

        # Strategy 2: Stealth Playwright Fallback
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
                    page.goto(self.url, wait_until="domcontentloaded", timeout=25000)
                    page.wait_for_timeout(3000)
                    html_content = page.content()
                    browser.close()
                    logger.info("Successfully fetched Total Wine page via Playwright.")
            except Exception as pe:
                logger.error(f"Playwright fallback failed for Total Wine: {pe}")

        if not html_content:
            return results

        soup = BeautifulSoup(html_content, "html.parser")
        cards = soup.select("[data-at='product-card'], article, .productCard__1VzC1l1O, .product-card, div[class*='productCard']")

        for card in cards:
            link_el = card if card.name == "a" else card.select_one("a[href]")
            href = link_el["href"] if link_el and link_el.has_attr("href") else ""
            if not href or href == "#":
                continue

            title_el = card.select_one("h2, h3, h4, [data-at='product-card-title'], .title") or link_el or card
            title = title_el.get_text(strip=True) if title_el else ""

            if not title or len(title) < 4:
                continue

            is_match, reason = matches_filter_rules(title, self.include_keywords, self.exclude_keywords)
            if not is_match:
                continue

            full_url = urljoin(self.url, href)
            price_el = card.select_one(".price, .amount, [class*='price']")
            price = price_el.get_text(strip=True) if price_el else "N/A"

            card_text = card.get_text().lower()
            in_stock = "out of stock" not in card_text and "unavailable" not in card_text

            results.append({
                "title": title,
                "price": price,
                "in_stock": in_stock,
                "url": full_url,
                "store_location": "Total Wine Store",
                "retailer": "total_wine"
            })

        logger.info(f"Total Wine scraper found {len(results)} matching items.")
        return results
