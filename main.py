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
import argparse


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
    If the API call fails or the field is missing, we fall back to fetching the
    article's web page and extracting the first paragraph from the HTML.
    """
    if not uri:
        return ""
    # Build filter query for the Article Search API.
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
        # Prefer the lead_paragraph if available.
        lead = docs[0].get("lead_paragraph", "")
        if lead:
            return lead
        # Otherwise attempt to scrape the first paragraph from the article URL.
        article_url = docs[0].get("web_url")
        if not article_url:
            return ""
        page_resp = requests.get(article_url, timeout=10)
        page_resp.raise_for_status()
        html = page_resp.text
        # Simple regex to find the first <p> element with non‑empty content.
        import re
        match = re.search(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
        if match:
            # Strip HTML tags that may be inside the paragraph.
            paragraph = re.sub(r'<[^>]+>', '', match.group(1))
            return paragraph.strip()
        return ""
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



def print_story(payload: str, printer: str):
    """Send plain‑text to the configured CUPS printer.

    CUPS reads from stdin when the final argument is "-".
    """
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

    # Parse command‑line arguments
    parser = argparse.ArgumentParser(
        description="NYT headline daemon – default prints to STDOUT; use -t/--teletype to send to printer"
    )
    parser.add_argument("-t", "--teletype", action="store_true",
                        help="Redirect output to the configured teletype printer")
    args = parser.parse_args()
    teletype = args.teletype

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

                payload = f"{title}\n{'=' * len(title)}\n\n{lead}\n"
                if teletype:
                    print_story(payload, cfg["printer_name"])
                    logger.info(f"Printed: {title}")
                else:
                    print(payload)
                printed_ids.add(uid)
            save_state(state_path, printed_ids)
        except Exception as e:
            logger.exception("Error during polling/printing")

        time.sleep(cfg.get("poll_interval_seconds", 300))


if __name__ == "__main__":
    main()
