"""
kompass_scraper.py
Robust Selenium + BeautifulSoup scraper for Kompass (India) with:
- robots.txt check
- user-agent rotation
- randomized delays & exponential backoff
- retries & checkpointing
- SQLite persistent storage + CSV backup
- captcha detection (stops and logs)
- optional proxy support

Usage:
  python kompass_scraper.py

Config at top of the file.
"""

import os
import time
import random
import csv
import sqlite3
import json
import logging
import signal
from datetime import datetime
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, NoSuchElementException
)

# ----------------- CONFIG -----------------
START_URL = "https://in.kompass.com/searchCompanies/facet?value=IN&label=India&filterType=country&searchType=COMPANYNAME&checked=true"
OUTPUT_CSV = "kompass_companies.csv"
SQLITE_DB = "kompass_companies.db"
CHECKPOINT_FILE = "checkpoint.json"

# Optional: configure proxies (list of "http://user:pass@ip:port" or "http://ip:port")
PROXIES = []  # e.g. ["http://12.34.56.78:8000", ...]

# Selenium settings
HEADLESS = True
PAGE_LOAD_TIMEOUT = 30
ELEMENT_WAIT = 12

# Scraping limits (be polite)
MAX_COMPANIES = None   # None = unlimited
MIN_DELAY = 3.0
MAX_DELAY = 7.0

# Retries/backoff
MAX_RETRIES = 3
BACKOFF_FACTOR = 2.0

# Rotate user agents
USER_AGENTS = [
    # a short list; add more if needed
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("kompass_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# ------------------------------------------

# ----------------- Utilities -----------------
def check_robots(url):
    """Check robots.txt for disallow rules for the path."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        logger.info(f"Fetching robots.txt from {robots_url}")
        r = requests.get(robots_url, timeout=10)
        if r.status_code != 200:
            logger.warning("robots.txt not accessible; proceeding cautiously.")
            return True
        txt = r.text
        # Simple heuristic: if "Disallow: /" present for all user agents, stop.
        if "Disallow: /" in txt:
            logger.warning("robots.txt contains 'Disallow: /' — aborting by default.")
            return False
        return True
    except Exception as e:
        logger.warning(f"Failed to fetch robots.txt: {e}. Proceeding cautiously.")
        return True

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_company_url": None, "visited": []}

def save_checkpoint(cp):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2)

def init_db():
    conn = sqlite3.connect(SQLITE_DB, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        link TEXT UNIQUE,
        phone TEXT,
        email TEXT,
        website TEXT,
        address TEXT,
        other_info TEXT,
        scraped_at TEXT
    )
    """)
    conn.commit()
    return conn

def append_csv(rows):
    exists = os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["name","link","phone","email","website","address","other_info","scraped_at"])
        w.writerows(rows)

def is_captcha_page(soup):
    """Simple detection for captcha/reCAPTCHA presence."""
    if soup is None:
        return False
    text = soup.get_text(separator=" ").lower()
    if "captcha" in text or "recaptcha" in text or "please verify" in text:
        return True
    # also look for iframe with recaptcha
    if soup.find("iframe") and any("recaptcha" in (iframe.get("src") or "") for iframe in soup.find_all("iframe")):
        return True
    return False

# ----------------- Selenium Setup -----------------
def build_driver(proxy=None, user_agent=None, headless=True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # user agent
    if user_agent:
        options.add_argument(f"user-agent={user_agent}")
    # proxy
    if proxy:
        options.add_argument(f'--proxy-server={proxy}')
    # avoid automation flags where possible (but do not advise bypassing)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    # create driver
    service = ChromeService()
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver

# ----------------- Parsers -----------------
def parse_listing_page(html, base_url):
    """Return list of company profile links found on a listing page (absolute URLs)."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    # best-effort selectors — Kompass markup may change; adjust if needed
    for a in soup.select("a[href]"):
        href = a["href"]
        # company detail links often have '/c/' or '/company' patterns; refine as you test
        if "/c/" in href or "/company" in href or "/company/" in href:
            full = urljoin(base_url, href)
            links.append(full)
    # dedupe preserving order
    seen = set()
    out = []
    for l in links:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return out

def parse_company_page(html):
    soup = BeautifulSoup(html, "html.parser")
    # Heuristics: adjust these selectors based on actual page structure
    name = (soup.select_one("h1") or soup.select_one(".company-name") or soup.select_one(".company_title")).get_text(strip=True) if soup.select_one("h1") or soup.select_one(".company-name") or soup.select_one(".company_title") else ""
    phone = ""
    # try common selectors
    phone_elem = soup.select_one(".phone") or soup.select_one(".phoneNumber") or soup.select_one("a[href^='tel:']")
    if phone_elem:
        phone = phone_elem.get_text(strip=True)
    # email
    email_elem = soup.select_one("a[href^='mailto:']")
    email = email_elem.get_text(strip=True) if email_elem else ""
    # website
    site_elem = soup.select_one("a[href^='http'][target='_blank']")
    website = site_elem["href"] if site_elem else ""
    # address
    addr = ""
    addr_elem = soup.select_one(".address") or soup.select_one(".company-address") or soup.select_one(".addressBlock")
    if addr_elem:
        addr = addr_elem.get_text(" ", strip=True)
    # other info
    other = ""
    descr = soup.select_one(".company-intro") or soup.select_one(".description") or soup.select_one(".company-description")
    if descr:
        other = descr.get_text(" ", strip=True)
    return {
        "name": name,
        "phone": phone,
        "email": email,
        "website": website,
        "address": addr,
        "other_info": other
    }

# ----------------- Main Scraping Loop -----------------
def scrape():
    if not check_robots(START_URL):
        logger.error("Robots.txt disallows scraping — aborting.")
        return

    conn = init_db()
    cur = conn.cursor()
    checkpoint = load_checkpoint()
    visited = set(checkpoint.get("visited", []))
    last_company = checkpoint.get("last_company_url")

    rows_to_csv = []

    # choose initial proxy and user agent
    proxy_pool = list(PROXIES)
    ua_pool = list(USER_AGENTS)

    driver = None
    try:
        driver = build_driver(proxy=random.choice(proxy_pool) if proxy_pool else None,
                              user_agent=random.choice(ua_pool),
                              headless=HEADLESS)
        driver.get(START_URL)
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        # iterate pages (pagination) — use "next" link heuristics
        while True:
            html = driver.page_source
            listing_links = parse_listing_page(html, base_url=START_URL)
            logger.info(f"Found {len(listing_links)} candidate company links on listing page.")
            # process each company link
            for comp_link in listing_links:
                if MAX_COMPANIES and cur.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= MAX_COMPANIES:
                    logger.info("Reached MAX_COMPANIES limit.")
                    raise KeyboardInterrupt

                if comp_link in visited:
                    logger.info(f"Skipping already visited: {comp_link}")
                    continue

                success = False
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        logger.info(f"[Attempt {attempt}] Visiting company: {comp_link}")
                        driver.get(comp_link)
                        # explicit wait for main content
                        try:
                            WebDriverWait(driver, ELEMENT_WAIT).until(
                                EC.presence_of_element_located((By.TAG_NAME, "body"))
                            )
                        except TimeoutException:
                            logger.warning("Timeout waiting for body element.")
                        page_html = driver.page_source
                        soup = BeautifulSoup(page_html, "html.parser")

                        if is_captcha_page(soup):
                            logger.error(f"CAPTCHA detected at {comp_link}. Stopping for manual intervention.")
                            # Save state and exit gracefully
                            checkpoint["last_company_url"] = comp_link
                            save_checkpoint({"last_company_url": comp_link, "visited": list(visited)})
                            return

                        data = parse_company_page(page_html)
                        data["link"] = comp_link
                        data["scraped_at"] = datetime.utcnow().isoformat()

                        # insert into DB (ignore duplicates)
                        try:
                            cur.execute("""
                                INSERT OR IGNORE INTO companies (name, link, phone, email, website, address, other_info, scraped_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (data["name"], data["link"], data["phone"], data["email"], data["website"], data["address"], data["other_info"], data["scraped_at"]))
                            conn.commit()
                        except Exception as e:
                            logger.exception("DB insert failed: %s", e)

                        rows_to_csv.append([data["name"], data["link"], data["phone"], data["email"], data["website"], data["address"], data["other_info"], data["scraped_at"]])

                        visited.add(comp_link)
                        # periodically flush to CSV
                        if len(rows_to_csv) >= 10:
                            append_csv(rows_to_csv)
                            rows_to_csv = []

                        checkpoint["last_company_url"] = comp_link
                        checkpoint["visited"] = list(visited)
                        save_checkpoint(checkpoint)

                        # polite randomized sleep
                        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                        success = True
                        break
                    except WebDriverException as e:
                        logger.warning(f"WebDriverException on attempt {attempt}: {e}")
                        # optional: rotate proxy or user agent on failure
                        time.sleep((BACKOFF_FACTOR ** attempt) + random.random())
                    except Exception as e:
                        logger.exception(f"Unexpected error while scraping {comp_link}: {e}")
                        time.sleep((BACKOFF_FACTOR ** attempt) + random.random())

                if not success:
                    logger.error(f"Failed to scrape {comp_link} after {MAX_RETRIES} attempts. Skipping.")
                    visited.add(comp_link)
                    checkpoint["visited"] = list(visited)
                    save_checkpoint(checkpoint)

            # handle pagination: look for next page link on the current listing page
            try:
                # heuristics: find link/button with text 'Next' or class 'next'
                next_el = None
                try:
                    next_el = driver.find_element(By.LINK_TEXT, "Next")
                except Exception:
                    try:
                        next_el = driver.find_element(By.CSS_SELECTOR, ".next, .pagination-next, a[rel='next']")
                    except Exception:
                        next_el = None

                if next_el:
                    logger.info("Clicking Next page.")
                    try:
                        next_el.click()
                    except Exception:
                        # fallback: get href and driver.get
                        href = next_el.get_attribute("href")
                        if href:
                            driver.get(href)
                        else:
                            logger.info("Next element not clickable and no href found. Ending.")
                            break
                    # polite wait
                    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                    continue
                else:
                    logger.info("No Next link found. Attempting to stop (end of listings).")
                    break
            except Exception as e:
                logger.exception("Error while trying to paginate: %s", e)
                break

        # final flush csv
        if rows_to_csv:
            append_csv(rows_to_csv)

    except KeyboardInterrupt:
        logger.info("Interrupted by user; saving checkpoint and exiting.")
        save_checkpoint({"last_company_url": checkpoint.get("last_company_url"), "visited": list(visited)})
    except Exception as e:
        logger.exception("Fatal error: %s", e)
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        if conn:
            conn.close()
        logger.info("Scraper finished.")

if __name__ == "__main__":
    scrape()
