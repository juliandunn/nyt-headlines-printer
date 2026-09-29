#!/usr/bin/env python3
"""NYT Headline Teletype Daemon for Raspberry Pi (Raspbian)

Continuously polls the New York Times Top Stories API, prints new headlines
and abstracts to a CUPS printer (e.g., OKI520) via the `lp` command, and
remembers which stories have already been printed.
"""
import argparse
import datetime
import html
import json
import logging
import pathlib
import subprocess
import time

import requests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config() -> dict:
    cfg_path = pathlib.Path(__file__).with_name("config.json")
    return json.loads(cfg_path.read_text())


# ---------------------------------------------------------------------------
# State persistence (TTL-pruned dict: {uri -> printed_at_iso})
# ---------------------------------------------------------------------------

_TTL_DAYS = 5


def load_state(state_path: pathlib.Path) -> dict:
    """Load printed-article state, pruning entries older than _TTL_DAYS days.

    State is stored as {uri: printed_at_iso} so we can discard stale entries.
    Articles disappear from the NYT Top Stories feed within a few days, so
    there is no need to remember them indefinitely.
    """
    if not state_path.is_file():
        return {}
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=_TTL_DAYS)
    try:
        data = json.loads(state_path.read_text())
        # Support old list-style state files gracefully.
        if isinstance(data, list):
            return {}
        return {
            uri: ts for uri, ts in data.items()
            if datetime.datetime.fromisoformat(ts) > cutoff
        }
    except Exception:
        return {}


def save_state(state_path: pathlib.Path, state: dict):
    state_path.write_text(json.dumps(state))


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Clean text by unescaping HTML entities, mapping smart punctuation to

    ASCII equivalents, and ensuring valid UTF-8 encoding for CUPS printing.
    """
    if not text:
        return ""
    text = html.unescape(text)
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201b": "'",
        "\u201c": '"', "\u201d": '"', "\u201f": '"',
        "\u2013": "-", "\u2014": "-", "\u2015": "-",
        "\u2026": "...",
        "\xa0": " ", "\u200b": "", "\ufeff": "",
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    return text.encode("utf-8", errors="replace").decode("utf-8")


def format_updated(updated: str) -> str:
    """Parse an ISO 8601 timestamp and return a human-readable date + time string.

    Output format: MM/DD/YYYY HH:MM AM/PM ±HHMM
    Falls back to the raw string on parse failure.
    """
    if not updated:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(updated)
        return dt.strftime("%m/%d/%Y %I:%M %p %z").strip()
    except ValueError:
        return updated


# ---------------------------------------------------------------------------
# NYT API helpers
# ---------------------------------------------------------------------------

def fetch_top_stories(api_key: str, section: str) -> list:
    """Return list of top-story articles for the given section."""
    url = f"https://api.nytimes.com/svc/topstories/v2/{section}.json"
    resp = requests.get(url, params={"api-key": api_key}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("results", [])


# ---------------------------------------------------------------------------
# Printer
# ---------------------------------------------------------------------------

def print_story(payload: str, printer: str):
    """Send plain-text payload to the configured CUPS printer via stdin."""
    cleaned_payload = clean_text(payload)
    subprocess.run(
        ["lp", "-s", "-d", printer, "-"],
        input=cleaned_payload.encode("utf-8", errors="replace"),
        check=True,
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    cfg = load_config()
    state_path = pathlib.Path(cfg["state_path"])
    state = load_state(state_path)

    parser = argparse.ArgumentParser(
        description="NYT headline daemon – default prints to STDOUT; use -t/--teletype to send to printer"
    )
    parser.add_argument("-t", "--teletype", action="store_true",
                        help="Redirect output to the configured teletype printer")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Enable debug logging level")
    args = parser.parse_args()
    teletype = args.teletype

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)

    logger.info("Entering polling loop")
    while True:
        try:
            articles = fetch_top_stories(cfg["nyt_api_key"], cfg["section"])
            for art in articles:
                uid = art.get("uri")
                if uid in state:
                    continue

                # Extract and format updated timestamp
                updated = art.get("updated") or art.get("updated_date") or ""
                date_str = format_updated(updated)

                # Uppercase headline
                title = clean_text(art.get("title", "(no title)")).upper()

                # Extract abstract from Top Stories payload
                abstract = art.get("abstract")
                if not abstract:
                    # Nothing printable – mark seen to avoid repeated attempts
                    state[uid] = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
                    continue

                # Uppercase abstract; indent first line five spaces (newswire style)
                body = "     " + clean_text(abstract).upper()

                # Build final payload before any output
                payload = f"{date_str}\n{title}\n{body}\n\n"

                if teletype:
                    print_story(payload, cfg["printer_name"])
                    logger.info(f"Printed: {title}")
                else:
                    print(payload)

                state[uid] = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()

            save_state(state_path, state)
        except Exception:
            logger.exception("Error during polling/printing")

        time.sleep(cfg.get("poll_interval_seconds", 300))


if __name__ == "__main__":
    main()
