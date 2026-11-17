import logging
import os
import secrets
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import HOST, PORT, SCRAPE_INTERVAL_MINUTES, SCRAPER_API_TOKEN
from app.database import init_db, get_db, Tracker, Product, Release, SMTPSetting, SystemSetting, ScrapeLog, SessionLocal
from app.scrapers.base import is_safe_public_url
from app.scrapers.manager import run_all_scrapers
from app.notifier import send_test_email

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("spirit_tracker")

# Initialize Background Scheduler
scheduler = BackgroundScheduler()


def schedule_bg_job(minutes: int):
    """Dynamically schedules or updates the background scrape job."""
    if minutes < 1:
        minutes = 1
    logger.info(f"Scheduling background scraper job every {minutes} minutes.")
    scheduler.add_job(
        run_all_scrapers,
        'interval',
        minutes=minutes,
        id="bg_scrape_job",
        replace_existing=True
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    logger.info("Initializing Spirit Tracker database...")
    try:
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)

    db = SessionLocal()
    try:
        sys_set = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
        interval = sys_set.scrape_interval_minutes if sys_set else SCRAPE_INTERVAL_MINUTES
    except Exception:
        interval = SCRAPE_INTERVAL_MINUTES
    finally:
        db.close()

    try:
        schedule_bg_job(interval)
        scheduler.start()
        # Trigger immediate initial scrape on startup so calendar & products populate automatically
        scheduler.add_job(run_all_scrapers, id="initial_startup_scrape", replace_existing=True)
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)

    yield

    # Shutdown tasks
    logger.info("Shutting down background scheduler...")
    try:
        scheduler.shutdown()
    except Exception:
        pass


app = FastAPI(
    title="Spirit Tracker & Scraper API",
    description="Web scraper and notification dashboard for rare bourbon releases.",
    version="1.0.0",
    lifespan=lifespan
)

# Mount Static Files and Templates using absolute paths
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
    return response

def verify_optional_api_token(request: Request):
    configured = os.getenv("SCRAPER_API_TOKEN") or os.getenv("ADMIN_PASSWORD") or SCRAPER_API_TOKEN
    if not configured:
        return True
    auth_hdr = request.headers.get("authorization", "")
    token = auth_hdr[7:].strip() if auth_hdr.lower().startswith("bearer ") else request.headers.get("x-api-token", "").strip()
    if not token or not secrets.compare_digest(token, configured):
        raise HTTPException(status_code=401, detail="Valid API token required.")
    return True


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


from app.ai_agent import generate_smart_keywords

class ScheduleSchema(BaseModel):
    scrape_interval_minutes: int


class AISuggestSchema(BaseModel):
    bourbon_name: str


class AISettingSchema(BaseModel):
    gemini_api_key: Optional[str] = ""
    gemini_model: Optional[str] = "gemini-2.5-flash"


@app.get("/favicon.svg")
def favicon_svg():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="14" fill="#090d16"/>'
        '<path d="M22 14h20l-2 18a12 12 0 0 1-8 10v10h8v4H24v-4h8V42a12 12 0 0 1-8-10z" fill="#f59e0b"/>'
        '<path d="M25 27h14l-.6 5a7 7 0 0 1-12.8 0z" fill="#d97706"/>'
        '</svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


# --- Web Page Route ---
@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


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
def get_releases(sort: str = "closest", db: Session = Depends(get_db)):
    if sort == "closest":
        # Default: Closest to today in BOTH directions (abs(days_from_today))
        releases = db.query(Release).order_by(Release.abs_days.asc(), Release.id.desc()).all()
    elif sort == "forward":
        # Future releases first
        releases = db.query(Release).order_by(Release.date_score.desc(), Release.id.desc()).all()
    elif sort == "backward":
        # Past releases first
        releases = db.query(Release).order_by(Release.date_score.asc(), Release.id.asc()).all()
    elif sort == "title":
        releases = db.query(Release).order_by(Release.title.asc()).all()
    else:
        releases = db.query(Release).order_by(Release.abs_days.asc()).all()

    return [{
        "id": r.id,
        "title": r.title,
        "distillery": r.distillery,
        "release_date": r.release_date,
        "msrp": r.msrp,
        "details_url": r.details_url,
        "date_score": r.date_score or 202600,
        "parsed_date": r.parsed_date or "",
        "abs_days": r.abs_days if r.abs_days is not None else 9999,
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


@app.post("/api/trackers", dependencies=[Depends(verify_optional_api_token)])
def create_tracker(payload: TrackerSchema, db: Session = Depends(get_db)):
    if not is_safe_public_url(payload.url):
        raise HTTPException(status_code=400, detail="Tracker URL must be a valid public http(s) address.")
    tracker = Tracker(**payload.model_dump())
    db.add(tracker)
    db.commit()
    db.refresh(tracker)
    return {"status": "success", "id": tracker.id}


@app.put("/api/trackers/{tracker_id}", dependencies=[Depends(verify_optional_api_token)])
def update_tracker(tracker_id: int, payload: TrackerSchema, db: Session = Depends(get_db)):
    if not is_safe_public_url(payload.url):
        raise HTTPException(status_code=400, detail="Tracker URL must be a valid public http(s) address.")
    tracker = db.query(Tracker).filter(Tracker.id == tracker_id).first()
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    for key, val in payload.model_dump().items():
        setattr(tracker, key, val)

    db.commit()
    return {"status": "success"}


@app.delete("/api/trackers/{tracker_id}", dependencies=[Depends(verify_optional_api_token)])
def delete_tracker(tracker_id: int, db: Session = Depends(get_db)):
    tracker = db.query(Tracker).filter(Tracker.id == tracker_id).first()
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    db.delete(tracker)
    db.commit()
    return {"status": "success"}


@app.get("/api/smtp", dependencies=[Depends(verify_optional_api_token)])
def get_smtp(db: Session = Depends(get_db)):
    smtp = db.query(SMTPSetting).filter(SMTPSetting.id == 1).first()
    if not smtp:
        return {}
    return {
        "host": smtp.host,
        "port": smtp.port,
        "username": smtp.username,
        "password": "",
        "has_password": bool(smtp.password),
        "use_tls": smtp.use_tls,
        "use_ssl": smtp.use_ssl,
        "sender_email": smtp.sender_email,
        "recipient_email": smtp.recipient_email
    }


@app.post("/api/smtp", dependencies=[Depends(verify_optional_api_token)])
def save_smtp(payload: SMTPSchema, db: Session = Depends(get_db)):
    smtp = db.query(SMTPSetting).filter(SMTPSetting.id == 1).first()
    if not smtp:
        smtp = SMTPSetting(id=1)
        db.add(smtp)

    data = payload.model_dump()
    if not data.get("password"):
        data.pop("password", None)
    for key, val in data.items():
        setattr(smtp, key, val)

    db.commit()
    return {"status": "success"}


@app.post("/api/smtp/test", dependencies=[Depends(verify_optional_api_token)])
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


@app.post("/api/scrape-now", dependencies=[Depends(verify_optional_api_token)])
def trigger_manual_scrape(db: Session = Depends(get_db)):
    result = run_all_scrapers(db)
    return result


@app.get("/api/schedule")
def get_schedule(db: Session = Depends(get_db)):
    sys_set = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    interval = sys_set.scrape_interval_minutes if sys_set else 30

    job = scheduler.get_job("bg_scrape_job")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    return {
        "scrape_interval_minutes": interval,
        "next_run": next_run
    }


@app.post("/api/schedule", dependencies=[Depends(verify_optional_api_token)])
def update_schedule(payload: ScheduleSchema, db: Session = Depends(get_db)):
    minutes = payload.scrape_interval_minutes
    if minutes < 1 or minutes > 10080:
        raise HTTPException(status_code=400, detail="Interval must be between 1 and 10080 minutes.")

    sys_set = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    if not sys_set:
        sys_set = SystemSetting(id=1, scrape_interval_minutes=minutes)
        db.add(sys_set)
    else:
        sys_set.scrape_interval_minutes = minutes
    db.commit()

    schedule_bg_job(minutes)

    job = scheduler.get_job("bg_scrape_job")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    return {
        "status": "success",
        "scrape_interval_minutes": minutes,
        "next_run": next_run
    }


@app.get("/api/ai/settings", dependencies=[Depends(verify_optional_api_token)])
def get_ai_settings(db: Session = Depends(get_db)):
    sys_set = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    key = sys_set.gemini_api_key if sys_set else ""
    model = sys_set.gemini_model if sys_set and sys_set.gemini_model else "gemini-2.5-flash"
    
    masked_key = (key[:6] + "..." + key[-4:]) if len(key) > 10 else key
    return {
        "has_key": bool(key),
        "masked_key": masked_key,
        "gemini_model": model
    }


@app.post("/api/ai/settings", dependencies=[Depends(verify_optional_api_token)])
def save_ai_settings(payload: AISettingSchema, db: Session = Depends(get_db)):
    sys_set = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    if not sys_set:
        sys_set = SystemSetting(id=1)
        db.add(sys_set)

    if payload.gemini_api_key is not None and not payload.gemini_api_key.startswith("..."):
        sys_set.gemini_api_key = payload.gemini_api_key.strip()
    if payload.gemini_model:
        sys_set.gemini_model = payload.gemini_model.strip()

    db.commit()
    return {"status": "success"}


@app.post("/api/ai/suggest-keywords", dependencies=[Depends(verify_optional_api_token)])
def ai_suggest_keywords(payload: AISuggestSchema):
    if not payload.bourbon_name:
        raise HTTPException(status_code=400, detail="Bourbon name is required.")
    return generate_smart_keywords(payload.bourbon_name)


if __name__ == "__main__":
    import uvicorn
    dev_reload = os.getenv("DEV_RELOAD", "false").lower() == "true"
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=dev_reload)
