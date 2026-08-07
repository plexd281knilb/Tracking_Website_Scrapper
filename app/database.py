from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Tracker(Base):
    __tablename__ = "trackers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    retailer = Column(String, nullable=False, default="goody_goody")  # goody_goody, total_wine, custom
    url = Column(Text, nullable=False)
    include_keywords = Column(Text, default="")  # Comma separated
    exclude_keywords = Column(Text, default="")  # Comma separated
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="tracker", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    tracker_id = Column(Integer, ForeignKey("trackers.id"), nullable=True)
    title = Column(String, nullable=False)
    price = Column(String, default="N/A")
    in_stock = Column(Boolean, default=False)
    url = Column(Text, nullable=False)
    store_location = Column(String, default="Online/Default")
    last_checked = Column(DateTime, default=datetime.utcnow)
    last_notified = Column(DateTime, nullable=True)

    tracker = relationship("Tracker", back_populates="products")


class Release(Base):
    __tablename__ = "releases"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, unique=True)
    distillery = Column(String, default="Unknown")
    release_date = Column(String, default="TBD")
    msrp = Column(String, default="N/A")
    details_url = Column(Text, default="")
    is_tracked = Column(Boolean, default=False)
    scraped_at = Column(DateTime, default=datetime.utcnow)


class SMTPSetting(Base):
    __tablename__ = "smtp_settings"

    id = Column(Integer, primary_key=True, default=1)
    host = Column(String, default="")
    port = Column(Integer, default=587)
    username = Column(String, default="")
    password = Column(String, default="")
    use_tls = Column(Boolean, default=True)
    use_ssl = Column(Boolean, default=False)
    sender_email = Column(String, default="")
    recipient_email = Column(String, default="")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)
    scrape_interval_minutes = Column(Integer, default=30)


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="SUCCESS")  # SUCCESS, WARNING, ERROR
    message = Column(Text, default="")
    items_found = Column(Integer, default=0)


def init_db():
    from app.config import DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Ensure default SystemSetting record exists
        sys_set = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
        if not sys_set:
            db.add(SystemSetting(id=1, scrape_interval_minutes=30))
            db.commit()

        # Ensure default SMTP record exists
        smtp = db.query(SMTPSetting).filter(SMTPSetting.id == 1).first()
        if not smtp:
            db.add(SMTPSetting(id=1))
            db.commit()

        # Seed initial trackers if database is brand new
        if db.query(Tracker).count() == 0:
            default_trackers = [
                Tracker(
                    name="Jack Daniel's Coy Hill & Special Releases (Goody Goody)",
                    retailer="goody_goody",
                    url="https://www.goodygoody.com",
                    include_keywords="coy hill, twice barreled, special release, heritage barrel, jack daniel",
                    exclude_keywords="old no 7, gentleman, honey, fire, apple, rye, Tennessee whiskey 750ml standard",
                    enabled=True,
                ),
                Tracker(
                    name="Jack Daniel's Special Releases (Total Wine)",
                    retailer="total_wine",
                    url="https://www.totalwine.com/spirits/bourbon/c/000887",
                    include_keywords="coy hill, twice barreled, special release, heritage barrel, jack daniel",
                    exclude_keywords="old no 7, gentleman, honey, fire, apple, rye, glenfiddich, glenlivet, buchanan, macallan",
                    enabled=True,
                ),
            ]
            db.add_all(default_trackers)
            db.commit()

        # Update existing trackers if they still contain generic scotch keywords
        for t in db.query(Tracker).all():
            if "10 year" in t.include_keywords or "12 year" in t.include_keywords:
                if "jack" not in t.include_keywords.lower():
                    t.include_keywords = "coy hill, twice barreled, special release, heritage barrel, jack daniel"
                    t.exclude_keywords = "old no 7, gentleman, honey, fire, apple, rye, glenfiddich, glenlivet, buchanan, macallan"
        db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
