#!/usr/bin/env python3
"""NYT Headline Teletype Daemon for Raspberry Pi (Raspbian)

Continuously polls the New York Times Top Stories API, prints new headlines
and the first paragraph to a CUPS printer (e.g., OKI520) via the `lp`
command, and remembers which stories have already been printed.
"""

import json
import pathlib
import time
import logging
import subprocess
import requests
import urllib.parse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    cfg_path = pathlib.Path(__file__).with_name("config.json")
    return json.loads(cfg_path.read_text())


def load_state(state_path: pathlib.Path) -> set:
    if state_path.is_file():
        return set(json.loads(state_path.read_text()))
    return set()


def save_state(state_path: pathlib.Path, ids: set):
    state_path.write_text(json.dumps(list(ids)))


# ---------------------------------------------------------------------------
# Helper to fetch lead paragraph via Article Search API using the article's URI
# ---------------------------------------------------------------------------

def fetch_lead_paragraph_from_uri(uri: str, api_key: str) -> str:
    """Retrieve the lead paragraph for an article identified by its NYT ``uri``.

    The NYT Article Search API supports a filter query (``fq``) on the ``uri``
    field.  We request the ``lead_paragraph`` field and return it if present.
    If the API call fails or the field is missing, an empty string is returned.
    """
    if not uri:
        return ""
    # The ``uri`` field can contain characters like ':' and '/' which need to be
    # URL‑encoded when used inside the ``fq`` parameter.
    fq = f'uri:"{uri}"'
    search_url = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
    params = {
        "fq": fq,
        "api-key": api_key,
        "sort": "oldest",
        "page": 0,
    }
    try:
        resp = requests.get(search_url, params=params, timeout=10)
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        if not docs:
            return ""
        return docs[0].get("lead_paragraph", "") or ""
    except Exception as exc:
        logging.getLogger(__name__).debug(
            f"Failed to fetch lead paragraph for uri {uri}: {exc}"
        )
        return ""

# ---------------------------------------------------------------------------
# Main loop modifications to use the new helper
# ---------------------------------------------------------------------------

def fetch_top_stories(api_key: str, section: str) -> list:
    """Return list of top‑story articles for the given section."""
    url = f"https://api.nytimes.com/svc/topstories/v2/{section}.json"
    resp = requests.get(url, params={"api-key": api_key}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("results", [])



def print_story(title: str, abstract: str, printer: str):
    """Send plain‑text to the configured CUPS printer.

    CUPS reads from stdin when the final argument is "-".
    """
    payload = f"{title}\n{'=' * len(title)}\n\n{abstract}\n\n"
    subprocess.run(
        ["lp", "-d", printer, "-"],
        input=payload.encode("utf-8"),
        check=True,
    )

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    cfg = load_config()
    state_path = pathlib.Path(cfg["state_path"])
    printed_ids = load_state(state_path)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)

    while True:
        try:
            articles = fetch_top_stories(cfg["nyt_api_key"], cfg["section"])
            for art in articles:
                uid = art.get("uri")  # unique identifier for the article
                if uid in printed_ids:
                    continue
                title = art.get("title", "(no title)")
                # Try the lead paragraph that may already be present; fall back to abstract.
                lead = art.get("lead_paragraph") or art.get("abstract", "")
                # If still missing, fetch it via the Article Search API using the article's URI.
                if not lead:
                    lead = fetch_lead_paragraph_from_uri(uid, cfg["nyt_api_key"])
                if not lead:
                    # Nothing printable – skip but mark as seen to avoid repeated attempts.
                    printed_ids.add(uid)
                    continue

                print_story(title, lead, cfg["printer_name"])
                printed_ids.add(uid)
                logger.info(f"Printed: {title}")
            save_state(state_path, printed_ids)
        except Exception as e:
            logger.exception("Error during polling/printing")

        time.sleep(cfg.get("poll_interval_seconds", 300))


if __name__ == "__main__":
    main()
