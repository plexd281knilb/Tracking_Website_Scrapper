# Project Specification: Spirit Tracker & Scraper (Bourbon Alert System)

> **Master Reference Document for Unraid Docker Deployment**  
> *Targeted web scraper, bourbon release calendar monitor, stock tracker, and SMTP alert notification web app.*

---

## 1. Overview & Objectives

The goal of this project is to build an automated, self-hosted web application deployed via Docker on Unraid. The application regularly scrapes select spirits retailer websites (e.g., **Goody Goody**, **Total Wine**) and spirit news sites (**Breaking Bourbon Release Calendar**) to track product availability for rare/special release bourbons (e.g., Jack Daniel's Coy Hill, Twice Barreled, Single Barrel Special Release) while filtering out regular stock (e.g., Jack Daniel's Old No. 7, Gentleman Jack, Flavored variants).

When a tracked item becomes **In Stock**, the system dispatches immediate email notifications using user-configured **SMTP settings**.

---

## 2. Key Scope & Requirements

### 2.1 General & Infrastructure
- **Self-Hosted & Private**: Designed for local network / Unraid hosting. No public user authentication/login required.
- **Docker & Unraid Ready**: Containerized with `Dockerfile` and `docker-compose.yml` for seamless GitHub synchronization and Unraid template pulling.
- **Persistent Data**: SQLite database stored in a persistent docker volume (`/data`).

### 2.2 Web Scraping Engine
- **Target Retailers**:
  - **Goody Goody**: Search/Product page availability scraper.
  - **Total Wine**: Retail scraper with support for location/store selection.
  - **Extensible Architecture**: Modular scraper drivers to add new retailers easily.
- **Breaking Bourbon Release Calendar Integration**:
  - Scrapes the Breaking Bourbon release calendar to automatically ingest upcoming and newly announced bourbon releases.
  - Allows 1-click addition of new releases directly into the tracking watchlist.
- **Smart Filtering System**:
  - Positive matching keywords (e.g., `Coy Hill`, `Twice Barreled`, `Special Release`, `Heritage Barrel`, `10 Year`, `12 Year`).
  - Negative matching / Exclusion rules to exclude common core lineup bottles (e.g., `Old No. 7`, `Gentleman Jack`, `Honey`, `Apple`, `Fire`, `Rye Standard`).

### 2.3 SMTP & Email Alerting
- **SMTP Settings Page**: Form UI to configure host, port, username, password, security (SSL/TLS), and sender/recipient email addresses.
- **Test Email**: Button to send a test email to verify credentials.
- **Availability Notifications**: Triggers an alert email only when a target product transitions from `Out of Stock` to `In Stock` (or on first detection in stock), preventing duplicate spam.

### 2.4 Web Dashboard & UI
- **Stock Dashboard**:
  - Visual status cards/table listing tracked products, retailer source, current stock status (`IN STOCK` / `OUT OF STOCK`), price, last checked timestamp, and direct product link.
  - Manual "Run Scrape Now" trigger button.
- **Bourbon Release Calendar Feed**:
  - Tab or page displaying upcoming releases from Breaking Bourbon with quick "Track This Release" action.
- **Tracking Rule Manager**:
  - Interface to add custom URLs, edit positive/negative keyword filters, set check intervals, and toggle active tracking status.
- **SMTP Configuration Page**:
  - Full management of email server credentials and test mailing.
- **Design System**: Sleek, modern dark-themed web dashboard with responsive layout, live status updates, and interactive feedback.

---

## 3. System Architecture & Tech Stack

```
 ┌─────────────────────────────────────────────────────────────┐
 │                      Unraid Docker Host                     │
 │                                                             │
 │  ┌───────────────────────────────────────────────────────┐  │
 │  │              Spirit Tracker Container                 │  │
 │  │                                                       │  │
 │  │  ┌─────────────────┐       ┌───────────────────────┐  │  │
 │  │  │   Dashboard UI   │ <---> │   FastAPI / Express   │  │  │
 │  │  │ (HTML/CSS/JS UI) │       │      Web Server       │  │  │
 │  │  └─────────────────┘       └───────────┬───────────┘  │  │
 │  │                                        │              │  │
 │  │  ┌─────────────────┐       ┌───────────▼───────────┐  │  │
 │  │  │  Scraper Engine │ <---> │    SQLite Database    │  │  │
 │  │  │(Playwright/BS4) │       │     (/data/db.sqlite) │  │  │
 │  │  └────────┬────────┘       └───────────┬───────────┘  │  │
 │  │           │                            │              │  │
 │  │  ┌────────▼────────┐       ┌───────────▼───────────┐  │  │
 │  │  │ BreakingBourbon │       │   SMTP Mail Engine    │  │  │
 │  │  │ Scraper Driver  │       │     (Email Alerts)    │  │  │
 │  │  └─────────────────┘       └───────────────────────┘  │  │
 └──┴───────────────────────────────────────────────────────┴──┘
```

- **Backend**: Python (FastAPI + SQLite + Playwright / BeautifulSoup4 + APScheduler) or Node.js (Express + SQLite + Puppeteer / Cheerio + node-cron).  
  *Python selected for superior web scraping libraries, headless browser fallback, and native scheduler support.*
- **Frontend**: Responsive HTML5, Vanilla JavaScript, CSS3 (Glassmorphism Dark Theme, modern typography, live status badges).
- **Database**: SQLite3 (`track_bourbon.db`) for lightweight, zero-config file persistence.
- **Container**: Minimal Docker image (`python:3.11-slim` or `node:20-alpine`) compatible with Unraid Community Applications / Docker manager.

---

## 4. Data Models & Database Schema

### 4.1 `trackers`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Unique ID |
| `name` | TEXT | Display name (e.g., "Jack Daniel's Coy Hill") |
| `retailer` | TEXT | Retailer name (`goody_goody`, `total_wine`, `custom`) |
| `url` | TEXT | Target URL or search URL to scrape |
| `include_keywords` | TEXT | Comma-separated positive keywords |
| `exclude_keywords` | TEXT | Comma-separated negative keywords |
| `enabled` | BOOLEAN | Active flag |
| `created_at` | DATETIME | Timestamp created |

### 4.2 `products` (Scraped items)
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Unique ID |
| `tracker_id` | INTEGER FK | Parent tracker |
| `title` | TEXT | Scraped product title |
| `price` | TEXT | Scraped price string |
| `in_stock` | BOOLEAN | Current stock status |
| `url` | TEXT | Product URL |
| `store_location` | TEXT | Retailer store location/zip if applicable |
| `last_checked` | DATETIME | Last scrape timestamp |
| `last_notified` | DATETIME | Last alert sent timestamp |

### 4.3 `releases` (Breaking Bourbon Feed)
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Unique ID |
| `title` | TEXT | Release title |
| `distillery` | TEXT | Brand / Distillery |
| `release_date` | TEXT | Expected release date/window |
| `msrp` | TEXT | Manufacturer suggested retail price |
| `details_url` | TEXT | Link to Breaking Bourbon post |
| `is_tracked` | BOOLEAN | Flag if added to custom tracker |
| `scraped_at` | DATETIME | Ingestion timestamp |

### 4.4 `smtp_settings`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY (Always 1) | Single config row |
| `host` | TEXT | SMTP Server host |
| `port` | INTEGER | SMTP Server port |
| `username` | TEXT | SMTP account user |
| `password` | TEXT | Encrypted/Stored SMTP password |
| `use_tls` | BOOLEAN | Use STARTTLS |
| `use_ssl` | BOOLEAN | Use Direct SSL |
| `sender_email` | TEXT | From address |
| `recipient_email` | TEXT | Destination alert address |

---

## 5. Retailer & Calendar Scraping Logic

### 5.1 Goody Goody Scraper
- Parses search results or specific product pages.
- Checks DOM element for availability badge (`In Stock`, `Add to Cart` presence vs `Out of Stock` text).
- Filters results by checking `title` against `include_keywords` and ensuring zero `exclude_keywords` hit.

### 5.2 Total Wine Scraper
- Handles dynamic rendering and optional store location cookies.
- Extracts inventory badge (`In Stock at [Store]`, `Pick Up Today` vs `Out of Stock`).
- Applies positive/negative term matching.

### 5.3 Breaking Bourbon Release Calendar Scraper
- Fetches `https://www.breakingbourbon.com/release-calendar` (or current calendar URI).
- Extracts release name, distillery, release window, MSRP, and description.
- Populates the "Bourbon Release Calendar" view in the dashboard.

---

## 6. Deployment & Workflow (Unraid / GitHub)

1. **GitHub Repository**:
   - Code pushed from local environment to GitHub repository.
2. **Unraid Container Setup**:
   - Add Container in Unraid Docker UI referencing GitHub repository build or Docker Hub / GitHub Container Registry (`ghcr.io`) image.
   - Bind Volume: `/mnt/user/appdata/spirit-tracker/data` -> `/app/data`
   - Port Mapping: `10812:10812`
3. **Environment Variables**:
   - `PORT=10812`
   - `DATA_DIR=/app/data`
   - `SCRAPE_INTERVAL_MINUTES=30`

---

## 7. Next Steps & Execution Plan

1. **Initialize Project Files**: Establish directory layout, dependency definitions, and configuration files.
2. **Build Scraping Engine & Keyword Filters**: Implement modules for Goody Goody, Total Wine, and Breaking Bourbon.
3. **Build Core Web Server & Database**: Implement SQLite models, REST endpoints, and background scheduler.
4. **Build Dashboard UI & Settings**: Design glassmorphism UI for stock monitoring, release calendar, and SMTP configuration.
5. **Add Docker Packaging**: Create `Dockerfile` and `docker-compose.yml` for Unraid deployment.
