import httpx
from bs4 import BeautifulSoup
import logging
import re
import datetime
import calendar
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


def calculate_release_date_info(desc: str, title: str) -> Dict[str, Any]:
    """
    Parses release date string. If exact day is unavailable, defaults to
    the END OF THE RELEASE MONTH, then computes abs(days from today).
    """
    today = datetime.date.today()
    full = f"{desc} {title}".lower()

    # 1. Year
    year_match = re.search(r'202[3-9]', full)
    year = int(year_match.group(0)) if year_match else today.year

    # 2. Month
    month = 12
    if 'january' in full or 'jan' in full: month = 1
    elif 'february' in full or 'feb' in full: month = 2
    elif 'march' in full or 'mar' in full: month = 3
    elif 'spring' in full or 'q1' in full: month = 5
    elif 'april' in full or 'apr' in full: month = 4
    elif 'may' in full: month = 5
    elif 'june' in full or 'jun' in full: month = 6
    elif 'summer' in full or 'q2' in full: month = 8
    elif 'july' in full or 'jul' in full: month = 7
    elif 'august' in full or 'aug' in full: month = 8
    elif 'september' in full or 'sep' in full: month = 9
    elif 'fall' in full or 'autumn' in full or 'q3' in full: month = 11
    elif 'october' in full or 'oct' in full: month = 10
    elif 'november' in full or 'nov' in full: month = 11
    elif 'december' in full or 'dec' in full or 'winter' in full or 'q4' in full: month = 12

    # 3. Day (Explicit day if present; otherwise default to END OF MONTH)
    day_match = re.search(r'\b(3[01]|[12][0-9]|[1-9])\b', desc)
    max_days = calendar.monthrange(year, month)[1]

    if day_match and int(day_match.group(0)) <= max_days:
        day = int(day_match.group(0))
    else:
        day = max_days

    parsed_dt = datetime.date(year, month, day)
    days_diff = (parsed_dt - today).days
    abs_days = abs(days_diff)

    return {
        "parsed_date": parsed_dt.strftime("%Y-%m-%d"),
        "abs_days": abs_days,
        "days_diff": days_diff,
        "date_score": year * 100 + month
    }


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
                    date_info = calculate_release_date_info(desc, title)

                    releases.append({
                        "title": title,
                        "distillery": distillery,
                        "release_date": desc if desc else "Upcoming",
                        "msrp": msrp,
                        "details_url": full_url,
                        "parsed_date": date_info["parsed_date"],
                        "abs_days": date_info["abs_days"],
                        "date_score": date_info["date_score"]
                    })

                logger.info(f"Successfully scraped {len(releases)} releases from Breaking Bourbon.")

        except Exception as e:
            logger.error(f"Error scraping Breaking Bourbon: {e}", exc_info=True)

        return releases
