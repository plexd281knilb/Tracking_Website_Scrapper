import httpx
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Any
from urllib.parse import urljoin
from app.scrapers.base import DEFAULT_HEADERS

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://www.breakingbourbon.com/release-calendar"


class BreakingBourbonScraper:
    def __init__(self, url: str = CALENDAR_URL):
        self.url = url

    def scrape(self) -> List[Dict[str, Any]]:
        releases = []
        logger.info(f"Fetching Breaking Bourbon Release Calendar: {self.url}")

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=15.0, follow_redirects=True) as client:
                response = client.get(self.url)
                if response.status_code != 200:
                    logger.warning(f"Breaking Bourbon returned status {response.status_code}")
                    return releases

                soup = BeautifulSoup(response.text, "html.parser")

                # Locate release blocks / table rows / cards
                items = soup.select(".release-item, .release-card, .calendar-item, tr, .summary-item, article, [data-release]")
                if not items:
                    items = soup.select("a[href*='/release-calendar/'], a[href*='/bourbon-rye-whiskey-reviews/']")

                for item in items:
                    title_elem = item.select_one(".title, .name, h2, h3, h4, .summary-title") or item
                    title = title_elem.get_text(strip=True) if title_elem else ""

                    if not title or len(title) < 4 or "calendar" in title.lower() or "newsletter" in title.lower():
                        continue

                    # Extract details link
                    link_elem = item if item.name == "a" else item.select_one("a[href]")
                    href = link_elem["href"] if link_elem and link_elem.has_attr("href") else self.url
                    full_url = urljoin(self.url, href)

                    # Extract metadata if present
                    text = item.get_text()
                    distillery = "Unknown"
                    msrp = "N/A"
                    release_date = "TBD"

                    # Simple heuristic parsing for MSRP and Date inside element text
                    if "msrp:" in text.lower():
                        parts = text.lower().split("msrp:")
                        if len(parts) > 1:
                            msrp = parts[1].split("\n")[0].strip().split(" ")[0].upper()

                    if "release:" in text.lower():
                        parts = text.lower().split("release:")
                        if len(parts) > 1:
                            release_date = parts[1].split("\n")[0].strip()

                    releases.append({
                        "title": title,
                        "distillery": distillery,
                        "release_date": release_date,
                        "msrp": msrp,
                        "details_url": full_url
                    })

        except Exception as e:
            logger.error(f"Error scraping Breaking Bourbon: {e}", exc_info=True)

        return releases
