"""
fetch_data.py
--------------
Pulls hospital-level data from the CMS Provider Data Catalog API and saves
raw JSON + CSV snapshots to /raw, timestamped.

Datasets pulled:
  1. Hospital General Information  (facility name, address, ownership, rating)
  2. Hospital Readmissions Reduction Program  (excess readmission ratios, penalties)

HOW TO GET THE DATASET IDs (they can change when CMS refreshes a dataset):
  1. Go to the dataset's page on https://data.cms.gov/provider-data/
  2. Click the "Access API" button near the top of the page
  3. Copy the UUID/ID out of the endpoint shown, e.g.:
     https://data.cms.gov/provider-data/api/1/datastore/query/<THIS-PART>/0
  4. Paste it into DATASETS below

Usage:
    python fetch_data.py
"""

import requests
import json
import csv
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# CONFIG — update these two IDs by following the steps in the docstring above
# --------------------------------------------------------------------------
DATASETS = {
    "hospital_general_info": "xubh-q36u",       # Hospital General Information
    "hrrp_readmissions": "9n3s-kdb3"             # Hospital Readmissions Reduction Program
                                                  # NOTE: this ID is from the legacy, retired
                                                  # data.medicare.gov site. It failed once already.
                                                  # If it 400s again, get the current ID directly
                                                  # from data.cms.gov/provider-data (see docstring).
}

BASE_URL = "https://data.cms.gov/provider-data/api/1/datastore/query/{dataset_id}/0"
PAGE_SIZE = 500            # CMS datastore/query hard caps "limit" at 500 — a request
                           # above this returns 400 Bad Request, not a truncated page
MAX_RETRIES = 4
BACKOFF_SECONDS = 2       # doubles each retry: 2s, 4s, 8s, 16s
REQUEST_TIMEOUT = 30

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)


def fetch_page(dataset_id: str, offset: int, limit: int = PAGE_SIZE) -> dict:
    """Fetch a single page of results with retry + exponential backoff."""
    url = BASE_URL.format(dataset_id=dataset_id)
    params = {"limit": limit, "offset": offset}

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            last_error = e
            wait = BACKOFF_SECONDS * (2 ** (attempt - 1))
            log.warning(
                f"Request failed (attempt {attempt}/{MAX_RETRIES}) for "
                f"dataset={dataset_id} offset={offset}: {e}. Retrying in {wait}s..."
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Failed to fetch dataset={dataset_id} offset={offset} after "
        f"{MAX_RETRIES} attempts. Last error: {last_error}"
    )


def fetch_full_dataset(dataset_id: str, name: str) -> list:
    """Paginate through a CMS datastore dataset and return all rows."""
    all_rows = []
    offset = 0

    log.info(f"Starting pull for '{name}' (dataset_id={dataset_id})")

    while True:
        page = fetch_page(dataset_id, offset)

        # CMS datastore API returns either a bare list or a dict with "results"
        rows = page if isinstance(page, list) else page.get("results", page)

        if not rows:
            break

        all_rows.extend(rows)
        log.info(f"  fetched {len(rows)} rows (running total: {len(all_rows)})")

        if len(rows) < PAGE_SIZE:
            break  # last page

        offset += PAGE_SIZE
        time.sleep(0.5)  # be polite to the API

    log.info(f"Finished '{name}': {len(all_rows)} total rows")
    return all_rows


def save_raw(rows: list, name: str, timestamp: str) -> None:
    """Save both JSON (full fidelity) and CSV (easy inspection) snapshots."""
    if not rows:
        log.warning(f"No rows returned for '{name}' — skipping save.")
        return

    json_path = RAW_DIR / f"{name}_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(rows, f, indent=2)
    log.info(f"Saved {json_path}")

    csv_path = RAW_DIR / f"{name}_{timestamp}.csv"
    fieldnames = sorted({k for row in rows for k in row.keys()})
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    log.info(f"Saved {csv_path}")


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for name, dataset_id in DATASETS.items():
        if dataset_id.startswith("REPLACE_WITH"):
            log.error(
                f"Skipping '{name}': placeholder dataset_id still in config. "
                f"See the docstring at the top of this file for how to find it."
            )
            continue

        try:
            rows = fetch_full_dataset(dataset_id, name)
            save_raw(rows, name, timestamp)
        except RuntimeError as e:
            log.error(f"Giving up on '{name}': {e}")

    log.info("Done. Check the /raw folder for output files.")


if __name__ == "__main__":
    main()