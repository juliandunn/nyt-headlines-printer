#!/usr/bin/env python3
import datetime
import json
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import main


class TestNYTPrinter(unittest.TestCase):

    # ---------------------------------------------------------------------------
    # 1. State Persistence Tests (load_state / save_state)
    # ---------------------------------------------------------------------------

    def test_save_and_load_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = pathlib.Path(tmpdir) / "state.json"
            now_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
            sample_state = {"nyt://article/1": now_iso}

            main.save_state(state_file, sample_state)
            loaded = main.load_state(state_file)

            self.assertIn("nyt://article/1", loaded)
            self.assertEqual(loaded["nyt://article/1"], now_iso)

    def test_load_state_ttl_pruning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = pathlib.Path(tmpdir) / "state.json"
            now = datetime.datetime.now(tz=datetime.timezone.utc)

            recent_iso = (now - datetime.timedelta(days=2)).isoformat()
            old_iso = (now - datetime.timedelta(days=10)).isoformat()

            raw_state = {
                "nyt://article/recent": recent_iso,
                "nyt://article/old": old_iso,
            }
            state_file.write_text(json.dumps(raw_state))

            loaded = main.load_state(state_file)
            self.assertIn("nyt://article/recent", loaded)
            self.assertNotIn("nyt://article/old", loaded)

    def test_load_state_legacy_list_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = pathlib.Path(tmpdir) / "state.json"
            state_file.write_text(json.dumps(["nyt://article/1", "nyt://article/2"]))

            loaded = main.load_state(state_file)
            self.assertEqual(loaded, {})

    def test_load_state_missing_file(self):
        state_file = pathlib.Path("/nonexistent/path/state.json")
        loaded = main.load_state(state_file)
        self.assertEqual(loaded, {})

    # ---------------------------------------------------------------------------
    # 2. Text Cleaning & Formatting Tests (clean_text / format_updated)
    # ---------------------------------------------------------------------------

    def test_clean_text(self):
        raw = "NYT&#8217;s &quot;breaking news&quot; \u2014 test\u2026\xa0done!"
        cleaned = main.clean_text(raw)
        self.assertEqual(cleaned, "NYT's \"breaking news\" - test... done!")

    def test_format_updated_valid_iso(self):
        iso_str = "2026-09-28T10:20:00-07:00"
        formatted = main.format_updated(iso_str)
        self.assertEqual(formatted, "09/28/2026 10:20 AM -0700")

    def test_format_updated_invalid(self):
        invalid_str = "not-a-timestamp"
        self.assertEqual(main.format_updated(invalid_str), invalid_str)

    def test_format_updated_empty(self):
        self.assertEqual(main.format_updated(""), "")

    # ---------------------------------------------------------------------------
    # 3. Top Stories Endpoint Tests (fetch_top_stories)
    # ---------------------------------------------------------------------------

    @patch("main.requests.get")
    def test_fetch_top_stories(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{"title": "Test Title", "uri": "nyt://article/1"}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        articles = main.fetch_top_stories("dummy_key", "home")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Test Title")

    # ---------------------------------------------------------------------------
    # 4. Printer Dispatch Tests (print_story)
    # ---------------------------------------------------------------------------

    @patch("main.subprocess.run")
    def test_print_story(self, mock_run):
        main.print_story("TEST PAYLOAD", "oki520")
        mock_run.assert_called_once_with(
            ["lp", "-s", "-d", "oki520", "-"],
            input=b"TEST PAYLOAD",
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
