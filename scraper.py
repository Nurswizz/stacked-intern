import logging
import os
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path

logger = logging.getLogger(__name__)

URL       = "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md"
ETAG_FILE = Path(os.environ.get("ETAG_FILE", Path(__file__).parent / ".last_etag"))


def _clean_location(td) -> str:
    """Remove <details>/<summary> noise; join multiple locations with ', '."""
    for tag in td.find_all(["details", "summary"]):
        tag.decompose()
    return td.get_text(separator=", ", strip=True)


def _parse_table(html: str) -> list[dict]:
    """Parse the internship table from raw HTML/Markdown text."""
    soup  = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        logger.warning("No table found in the document.")
        return []

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cols = tr.find_all("td")
        if len(cols) < 5:
            continue

        company = cols[0].get_text(strip=True)
        role    = cols[1].get_text(strip=True)
        if not company and not role:
            continue

        # Strip continuation marker (↳) so dedup works correctly
        company = re.sub(r"^↳\s*", "", company)

        location = _clean_location(cols[2])

        links         = cols[3].find_all("a")
        apply_link    = links[0]["href"] if len(links) > 0 else ""
        simplify_link = links[1]["href"] if len(links) > 1 else ""

        age = cols[4].get_text(strip=True)

        rows.append(dict(
            company=company,
            role=role,
            location=location,
            apply_link=apply_link,
            simplify_link=simplify_link,
            age=age,
        ))

    logger.info("Parsed %d rows.", len(rows))
    return rows


def fetch_if_changed() -> list[dict] | None:
    """
    Fetch and parse the README only when it has changed since last check.

    Uses the ETag header for efficient conditional requests:
      - Returns a list of dicts if the content is new.
      - Returns None if the file has not changed (HTTP 304).
      - Returns an empty list on network/parse errors.
    """
    last_etag = ETAG_FILE.read_text().strip() if ETAG_FILE.exists() else ""

    headers = {}
    if last_etag:
        headers["If-None-Match"] = last_etag

    logger.info("Checking for updates (ETag: %s)…", last_etag or "none")

    try:
        resp = requests.get(URL, headers=headers, timeout=30)
    except requests.RequestException as exc:
        logger.error("Request failed: %s", exc)
        return []

    if resp.status_code == 304:
        logger.info("No changes since last check (304 Not Modified).")
        return None

    if not resp.ok:
        logger.error("Unexpected status %s", resp.status_code)
        return []

    # Save new ETag for next run
    new_etag = resp.headers.get("ETag", "")
    if new_etag:
        ETAG_FILE.write_text(new_etag)
        logger.info("ETag updated → %s", new_etag)

    logger.info("Content changed – parsing table…")
    return _parse_table(resp.text)