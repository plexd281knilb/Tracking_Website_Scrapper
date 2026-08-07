import logging
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import HOST, PORT, SCRAPE_INTERVAL_MINUTES
from app.database import init_db, get_db, Tracker, Product, Release, SMTPSetting, ScrapeLog
from app.scrapers.manager import run_all_scrapers
from app.notifier import send_test_email

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("spirit_tracker")

# Initialize Background Scheduler
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    logger.info("Initializing Spirit Tracker database...")
    init_db()

    logger.info(f"Starting background scraper scheduler (interval: {SCRAPE_INTERVAL_MINUTES} minutes)...")
    scheduler.add_job(
        run_all_scrapers,
        'interval',
        minutes=SCRAPE_INTERVAL_MINUTES,
        id="bg_scrape_job",
        replace_existing=True
    )
    scheduler.start()

    yield

    # Shutdown tasks
    logger.info("Shutting down background scheduler...")
    scheduler.shutdown()


app = FastAPI(
    title="Spirit Tracker & Scraper API",
    description="Web scraper and notification dashboard for rare bourbon releases.",
    version="1.0.0",
    lifespan=lifespan
)

# Mount Static Files and Templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# --- Pydantic Schemas ---
class TrackerSchema(BaseModel):
    name: str
    retailer: str
    url: str
    include_keywords: Optional[str] = ""
    exclude_keywords: Optional[str] = ""
    enabled: bool = True


class SMTPSchema(BaseModel):
    host: str
    port: int = 587
    username: Optional[str] = ""
    password: Optional[str] = ""
    use_tls: bool = True
    use_ssl: bool = False
    sender_email: Optional[str] = ""
    recipient_email: str


# --- Web Page Route ---
@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# --- API Routes ---

@app.get("/api/products")
def get_products(db: Session = Depends(get_db)):
    products = db.query(Product).order_by(Product.in_stock.desc(), Product.last_checked.desc()).all()
    result = []
    for p in products:
        result.append({
            "id": p.id,
            "tracker_id": p.tracker_id,
            "title": p.title,
            "price": p.price,
            "in_stock": p.in_stock,
            "url": p.url,
            "store_location": p.store_location,
            "retailer": p.tracker.retailer if p.tracker else "custom",
            "last_checked": p.last_checked.isoformat() if p.last_checked else None,
            "last_notified": p.last_notified.isoformat() if p.last_notified else None
        })
    return result


@app.get("/api/releases")
def get_releases(db: Session = Depends(get_db)):
    releases = db.query(Release).order_by(Release.scraped_at.desc()).all()
    return [{
        "id": r.id,
        "title": r.title,
        "distillery": r.distillery,
        "release_date": r.release_date,
        "msrp": r.msrp,
        "details_url": r.details_url,
        "is_tracked": r.is_tracked,
        "scraped_at": r.scraped_at.isoformat() if r.scraped_at else None
    } for r in releases]


@app.get("/api/trackers")
def get_trackers(db: Session = Depends(get_db)):
    trackers = db.query(Tracker).all()
    return [{
        "id": t.id,
        "name": t.name,
        "retailer": t.retailer,
        "url": t.url,
        "include_keywords": t.include_keywords,
        "exclude_keywords": t.exclude_keywords,
        "enabled": t.enabled,
        "created_at": t.created_at.isoformat() if t.created_at else None
    } for t in trackers]


@app.post("/api/trackers")
def create_tracker(payload: TrackerSchema, db: Session = Depends(get_db)):
    tracker = Tracker(**payload.model_dump())
    db.add(tracker)
    db.commit()
    db.refresh(tracker)
    return {"status": "success", "id": tracker.id}


@app.put("/api/trackers/{tracker_id}")
def update_tracker(tracker_id: int, payload: TrackerSchema, db: Session = Depends(get_db)):
    tracker = db.query(Tracker).filter(Tracker.id == tracker_id).first()
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    for key, val in payload.model_dump().items():
        setattr(tracker, key, val)

    db.commit()
    return {"status": "success"}


@app.delete("/api/trackers/{tracker_id}")
def delete_tracker(tracker_id: int, db: Session = Depends(get_db)):
    tracker = db.query(Tracker).filter(Tracker.id == tracker_id).first()
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    db.delete(tracker)
    db.commit()
    return {"status": "success"}


@app.get("/api/smtp")
def get_smtp(db: Session = Depends(get_db)):
    smtp = db.query(SMTPSetting).filter(SMTPSetting.id == 1).first()
    if not smtp:
        return {}
    return {
        "host": smtp.host,
        "port": smtp.port,
        "username": smtp.username,
        "password": smtp.password,
        "use_tls": smtp.use_tls,
        "use_ssl": smtp.use_ssl,
        "sender_email": smtp.sender_email,
        "recipient_email": smtp.recipient_email
    }


@app.post("/api/smtp")
def save_smtp(payload: SMTPSchema, db: Session = Depends(get_db)):
    smtp = db.query(SMTPSetting).filter(SMTPSetting.id == 1).first()
    if not smtp:
        smtp = SMTPSetting(id=1)
        db.add(smtp)

    for key, val in payload.model_dump().items():
        setattr(smtp, key, val)

    db.commit()
    return {"status": "success"}


@app.post("/api/smtp/test")
def trigger_test_email(db: Session = Depends(get_db)):
    try:
        send_test_email(db)
        return {"status": "success", "message": "Test email dispatched successfully."}
    except Exception as e:
        logger.error(f"Test email failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/logs")
def get_logs(db: Session = Depends(get_db)):
    logs = db.query(ScrapeLog).order_by(ScrapeLog.timestamp.desc()).limit(50).all()
    return [{
        "id": l.id,
        "timestamp": l.timestamp.isoformat(),
        "status": l.status,
        "message": l.message,
        "items_found": l.items_found
    } for l in logs]


@app.post("/api/scrape-now")
def trigger_manual_scrape(db: Session = Depends(get_db)):
    result = run_all_scrapers(db)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
