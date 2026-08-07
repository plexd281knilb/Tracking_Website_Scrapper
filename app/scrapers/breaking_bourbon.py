import httpx
from bs4 import BeautifulSoup
import logging
import re
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
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=15.0, follow_redirects=True, verify=False) as client:
                response = client.get(self.url)
                if response.status_code != 200:
                    logger.warning(f"Breaking Bourbon returned status {response.status_code}")
                    return releases

                soup = BeautifulSoup(response.text, "html.parser")

                # Locate Webflow collection items
                items = soup.select(".w-dyn-item")
                if not items:
                    items = soup.select(".release-item, .release-card, tr, article")

                for item in items:
                    title_elem = item.select_one(".calendar-text.bold, .name-div, h2, h3, h4")
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    if not title or len(title) < 3 or "calendar" in title.lower():
                        continue

                    # Clean up badge tags from title
                    title = re.sub(r'NEW\s*INFO|NEW|EXPECTED\s*DATE', '', title).strip()

                    # Description / Details
                    desc_elem = item.select_one(".calendar-text.w-richtext, p")
                    desc = desc_elem.get_text(strip=True) if desc_elem else ""

                    # Extract MSRP ($XX)
                    msrp_match = re.search(r'\$\d+(?:,\d+)?', desc)
                    msrp = msrp_match.group(0) if msrp_match else "N/A"

                    # Extract details link
                    link_elem = item.select_one("a[href]:not([href='#'])")
                    href = link_elem["href"] if link_elem else ""
                    full_url = urljoin(self.url, href) if href else self.url

                    # Distillery heuristic
                    distillery = title.split(":")[0].split("-")[0].strip()
                    words = distillery.split(" ")
                    if len(words) > 3:
                        distillery = " ".join(words[:2])

                    releases.append({
                        "title": title,
                        "distillery": distillery,
                        "release_date": desc if desc else "Upcoming",
                        "msrp": msrp,
                        "details_url": full_url
                    })

                logger.info(f"Successfully scraped {len(releases)} releases from Breaking Bourbon.")

        except Exception as e:
            logger.error(f"Error scraping Breaking Bourbon: {e}", exc_info=True)

        return releases
