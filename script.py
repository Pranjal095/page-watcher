#!/usr/bin/env python3
"""
watch_page.py
Configure constants below directly (no environment variables).
Saves the last snapshot to a file instead of using a database.
"""

import os
import hashlib
import smtplib
import difflib
import time
from email.message import EmailMessage
from pathlib import Path

# === CONFIG (edit these directly) ===
URL = os.environ.get("URL")
CSS_SELECTOR = ""  # e.g. "#main" or ".article" ; empty -> whole page
SNAPSHOT_FILE = "./snapshot.txt"
USER_AGENT = "PageWatcher/1.0"

# SMTP settings
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
TO_EMAIL   = os.environ.get("TO_EMAIL")
FROM_EMAIL = os.environ.get("FROM_EMAIL")

# If the page requires JS to render, set to True and install playwright
USE_JS = False  # set to True to use Playwright (see notes below)

# === IMPORTS THAT MAY BE OPTIONAL ===
import requests
from bs4 import BeautifulSoup

# Optional: Playwright for JS-rendered pages
if USE_JS:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise SystemExit("Install playwright and run `playwright install` if USE_JS=True") from e

def fetch_content():
    headers = {"User-Agent": USER_AGENT}
    if USE_JS:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(URL, wait_until="networkidle", timeout=30000)
            html = page.content()
            browser.close()
    else:
        r = requests.get(URL, headers=headers, timeout=30)
        r.raise_for_status()
        html = r.text

    if CSS_SELECTOR:
        soup = BeautifulSoup(html, "html.parser")
        el = soup.select_one(CSS_SELECTOR)
        if not el:
            raise RuntimeError(f"Selector {CSS_SELECTOR} not found on page")
        text = el.get_text(separator="\n")
    else:
        # strip HTML to text to reduce noise
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n")
    return normalize_text(text)

def normalize_text(text):
    # Remove multiple blank lines and leading/trailing whitespace
    lines = [line.strip() for line in text.splitlines()]
    # Remove empty lines
    lines = [ln for ln in lines if ln]
    # Optional: add regex-based removals for timestamps/session IDs here
    return "\n".join(lines)

def make_hash(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def get_last_snapshot():
    """
    Returns (content, hash) of the last saved snapshot file.
    If snapshot file doesn't exist, returns (None, None).
    """
    p = Path(SNAPSHOT_FILE)
    if not p.exists():
        return (None, None)
    content = p.read_text(encoding="utf-8")
    return (content, make_hash(content))

def save_snapshot(content, h):
    """
    Writes the current snapshot to SNAPSHOT_FILE and creates a timestamped backup copy.
    """
    ts = int(time.time())
    p = Path(SNAPSHOT_FILE)
    p.write_text(content, encoding="utf-8")

def send_email(subject, body, diff_text=None):
    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject
    body_full = body
    if diff_text:
        body_full += "\n\n--- DIFF ---\n" + diff_text
    msg.set_content(body_full)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

def generate_diff(old, new):
    old_lines = old.splitlines() if old else []
    new_lines = new.splitlines()
    d = difflib.unified_diff(old_lines, new_lines, lineterm="")
    return "\n".join(d)

# === MAIN ===
def main():
    content = fetch_content()
    h = make_hash(content)
    old_content, old_hash = get_last_snapshot()

    # If no previous snapshot exists, old_hash will be None -> will treat as change (first run)
    if old_hash != h:
        diff = generate_diff(old_content, content)
        subject = f"[PageWatcher] Change detected: {URL}"
        body = (
            f"Change detected at {time.ctime()} for {URL}\n"
            f"Selector: {CSS_SELECTOR or '(whole page)'}\n"
            f"Hash: {h}\n"
        )
        send_email(subject, body, diff_text=diff)
        save_snapshot(content, h)
        print("Change detected -> email sent")
    else:
        print("No change")

if __name__ == "__main__":
    main()