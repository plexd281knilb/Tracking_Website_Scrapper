from datetime import datetime
import logging
from sqlalchemy.orm import Session
from app.database import Tracker, Product, Release, ScrapeLog, SessionLocal
from app.scrapers.goody_goody import GoodyGoodyScraper
from app.scrapers.total_wine import TotalWineScraper
from app.scrapers.breaking_bourbon import BreakingBourbonScraper
from app.notifier import notify_stock_alert

logger = logging.getLogger(__name__)


def run_all_scrapers(db: Session = None) -> dict:
    """Orchestrates scraping of all configured trackers and Breaking Bourbon release calendar."""
    close_db_when_done = False
    if db is None:
        db = SessionLocal()
        close_db_when_done = True

    items_found_count = 0
    notifications_sent = 0
    errors = []

    try:
        logger.info("--- Starting Scrape Cycle ---")

        # 1. Scrape Active Trackers
        trackers = db.query(Tracker).filter(Tracker.enabled == True).all()

        for tracker in trackers:
            logger.info(f"Processing tracker '{tracker.name}' ({tracker.retailer})")
            scraped_products = []

            if tracker.retailer == "goody_goody":
                scraper = GoodyGoodyScraper(
                    url=tracker.url,
                    include_keywords=tracker.include_keywords,
                    exclude_keywords=tracker.exclude_keywords
                )
                scraped_products = scraper.scrape()
            elif tracker.retailer == "total_wine":
                scraper = TotalWineScraper(
                    url=tracker.url,
                    include_keywords=tracker.include_keywords,
                    exclude_keywords=tracker.exclude_keywords
                )
                scraped_products = scraper.scrape()
            else:
                # Custom / Fallback retailer scraper
                scraper = GoodyGoodyScraper(
                    url=tracker.url,
                    include_keywords=tracker.include_keywords,
                    exclude_keywords=tracker.exclude_keywords
                )
                scraped_products = scraper.scrape()

            for item in scraped_products:
                items_found_count += 1
                title = item["title"]

                # Find existing product in DB for this tracker
                existing_product = db.query(Product).filter(
                    Product.tracker_id == tracker.id,
                    Product.title == title
                ).first()

                now = datetime.utcnow()

                if existing_product:
                    was_out_of_stock = not existing_product.in_stock
                    is_now_in_stock = item["in_stock"]

                    # Update product properties
                    existing_product.price = item["price"]
                    existing_product.in_stock = is_now_in_stock
                    existing_product.url = item["url"]
                    existing_product.store_location = item["store_location"]
                    existing_product.last_checked = now

                    # Alert if transitioned from Out of Stock -> In Stock
                    if was_out_of_stock and is_now_in_stock:
                        logger.info(f"Stock Alert! Item '{title}' is now IN STOCK.")
                        success, msg = notify_stock_alert(
                            db=db,
                            product_title=title,
                            price=item["price"],
                            url=item["url"],
                            retailer=tracker.retailer
                        )
                        if success:
                            existing_product.last_notified = now
                            notifications_sent += 1
                else:
                    # New product detected
                    is_now_in_stock = item["in_stock"]
                    new_product = Product(
                        tracker_id=tracker.id,
                        title=title,
                        price=item["price"],
                        in_stock=is_now_in_stock,
                        url=item["url"],
                        store_location=item["store_location"],
                        last_checked=now,
                        last_notified=now if is_now_in_stock else None
                    )
                    db.add(new_product)

                    if is_now_in_stock:
                        logger.info(f"Stock Alert! New item '{title}' found IN STOCK.")
                        success, msg = notify_stock_alert(
                            db=db,
                            product_title=title,
                            price=item["price"],
                            url=item["url"],
                            retailer=tracker.retailer
                        )
                        if success:
                            notifications_sent += 1

            db.commit()

        # 2. Scrape Breaking Bourbon Release Calendar
        logger.info("Scraping Breaking Bourbon Release Calendar...")
        bb_scraper = BreakingBourbonScraper()
        releases = bb_scraper.scrape()

        for r in releases:
            existing_release = db.query(Release).filter(Release.title == r["title"]).first()
            if not existing_release:
                db.add(Release(
                    title=r["title"],
                    distillery=r["distillery"],
                    release_date=r["release_date"],
                    msrp=r["msrp"],
                    details_url=r["details_url"],
                    scraped_at=datetime.utcnow()
                ))
            else:
                existing_release.release_date = r["release_date"]
                existing_release.msrp = r["msrp"]
                existing_release.scraped_at = datetime.utcnow()

        db.commit()

        # 3. Log cycle completion
        log_entry = ScrapeLog(
            status="SUCCESS",
            message=f"Completed scrape cycle. Items found: {items_found_count}, Notifications sent: {notifications_sent}.",
            items_found=items_found_count
        )
        db.add(log_entry)
        db.commit()

        logger.info(f"Scrape cycle complete. {items_found_count} items processed.")

        return {
            "status": "success",
            "items_found": items_found_count,
            "notifications_sent": notifications_sent,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error during scrape cycle: {e}", exc_info=True)
        log_entry = ScrapeLog(
            status="ERROR",
            message=f"Scrape failed: {str(e)}",
            items_found=items_found_count
        )
        db.add(log_entry)
        db.commit()
        return {
            "status": "error",
            "message": str(e)
        }
    finally:
        if close_db_when_done:
            db.close()
