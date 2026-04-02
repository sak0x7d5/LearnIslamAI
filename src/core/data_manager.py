import json
from pathlib import Path
import urllib.request
import urllib.error

from core.manifest_tracker import ManifestTracker
from core.config import DATA_DIR, logger

# ========================= CONFIG =========================
HADITH_ROOT = DATA_DIR / "hadith"
BASE_API_URL = "https://api.github.com/repos/fawazahmed0/hadith-api/contents/editions?ref=1"
RAW_BASE_URL = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/"

CONFIG = {
    "stale_after_hours": 24,
}

LANGUAGE_MAP = {
    "ara": "arabic",
    "eng": "english",
    "urd": "urdu",
    "ben": "bengali",
    "fra": "french",
    "ind": "indonesian",
    "rus": "russian",
    "spa": "spanish",
    "tam": "tamil",
    "tur": "turkish",
    "farsi": "farsi"
}
# =========================================================

def ensure_data_dir():
    HADITH_ROOT.mkdir(parents=True, exist_ok=True)
    logger.info(f"Hadith data root directory ensured: {HADITH_ROOT.resolve()}")


def fetch_github_contents(url: str) -> list[dict]:
    """Fetch contents from GitHub"""
    logger.info(f"Fetching contents from: {url}")
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "hadith-downloader/1.0"}
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


import re

def is_json_file(item: dict) -> bool:
    if item.get("type") != "file":
        return False
    name = item.get("name", "")
    if not name.endswith(".json"):
        return False
    if ".min." in name:
        return False
    if re.search(r'\d\.json$', name):
        return False
    return True


def download_file(url: str, save_path: Path) -> bool:
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=30) as response:
            save_path.write_bytes(response.read())
        logger.info(f"Downloaded: {save_path.relative_to(DATA_DIR)}")
        return True
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


def sync_hadith_data():
    """Download Hadith JSONs and organize them into language folders"""
    ensure_data_dir()

    tracker = ManifestTracker()

    if tracker.is_data_fresh(CONFIG["stale_after_hours"]):
        logger.info("Hadith data is fresh. Skipping full sync.")
        return

    logger.info("Starting Hadith data sync from GitHub...")

    try:
        # Fetch the flat list of files in the 'editions' folder
        items = fetch_github_contents(BASE_API_URL)
    except Exception as e:
        logger.error(f"Failed to fetch editions list: {e}")
        return

    downloaded_count = 0

    for file_item in items:
        if not is_json_file(file_item):
            continue

        file_name = file_item["name"]
        
        # Get language prefix (e.g., 'eng', 'ara', 'urd')
        prefix = file_name.split("-")[0]
        
        # Map to full language name or place under 'other_{prefix}'
        language_folder = LANGUAGE_MAP.get(prefix, f"other_{prefix}")
        
        file_url = RAW_BASE_URL + file_name
        dest_path = HADITH_ROOT / language_folder / file_name

        # Check if file needs update using the unified manifest tracker object
        if tracker.is_synced(file_name, file_item.get("sha")) and dest_path.exists():
            # Avoid spammy logging for skipped files
            continue

        if download_file(file_url, dest_path):
            tracker.mark_file_synced(file_name, file_item.get("sha"))
            downloaded_count += 1

    tracker.update_last_sync()
    logger.info(f"Hadith sync completed! Downloaded/Updated {downloaded_count} files.")


if __name__ == "__main__":
    sync_hadith_data()