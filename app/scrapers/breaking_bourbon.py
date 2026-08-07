import httpx
from bs4 import BeautifulSoup
import logging
import re
from typing import List, Dict, Any
from urllib.parse import urljoin
from app.scrapers.base import DEFAULT_HEADERS

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://www.breakingbourbon.com/release-calendar"

KNOWN_BRANDS = [
    "Jack Daniel's", "Buffalo Trace", "WhistlePig", "Penelope", "Old Forester",
    "Maker's Mark", "Knob Creek", "Jim Beam", "James B. Beam", "Elijah Craig",
    "1792", "Still Austin", "Little Book", "Widow Jane", "Westward", "Westland",
    "Parker's Heritage", "King of Kentucky", "High West", "Dragon's Milk",
    "Bernheim", "Barrell", "Weller", "Michter's", "Stagg", "Fireside", "Heaven Hill",
    "Wild Turkey", "Russell's Reserve", "Woodford Reserve", "Larceny", "Shenk's", "Bomberger's"
]


def extract_brand(title: str) -> str:
    title_clean = title.strip()
    for brand in KNOWN_BRANDS:
        if brand.lower() in title_clean.lower():
            return brand
    parts = title_clean.split(":")[0].split("-")[0].strip().split(" ")
    return " ".join(parts[:2]) if len(parts) >= 2 else parts[0]


def calculate_date_score(desc: str, title: str) -> int:
    full = f"{desc} {title}".lower()
    year_match = re.search(r'202[3-9]', full)
    year = int(year_match.group(0)) if year_match else 2026

    season_score = 0
    if 'winter' in full or 'q4' in full or 'december' in full or 'november' in full:
        season_score = 12
    elif 'fall' in full or 'autumn' in full or 'q3' in full or 'september' in full or 'october' in full:
        season_score = 9
    elif 'summer' in full or 'q2' in full or 'june' in full or 'july' in full or 'august' in full:
        season_score = 6
    elif 'spring' in full or 'q1' in full or 'march' in full or 'april' in full or 'may' in full:
        season_score = 3

    return year * 100 + season_score


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

                    distillery = extract_brand(title)
                    score = calculate_date_score(desc, title)

                    releases.append({
                        "title": title,
                        "distillery": distillery,
                        "release_date": desc if desc else "Upcoming",
                        "msrp": msrp,
                        "details_url": full_url,
                        "date_score": score
                    })

                logger.info(f"Successfully scraped {len(releases)} releases from Breaking Bourbon.")

        except Exception as e:
            logger.error(f"Error scraping Breaking Bourbon: {e}", exc_info=True)

        return releases
