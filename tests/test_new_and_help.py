import json
import os
import re
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from core import config
from core.patch_notes import RELEASES

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "templates" / "notes"
HELP = ROOT / "templates" / "help"
HELP_SECTIONS = ("getting-started", "playlists", "other-platforms", "search-player", "downloads", "library",
                 "releases", "stats", "made-for-you", "settings", "sign-in", "android-app", "troubleshooting")


def version_key(version):
    return tuple(int(part) for part in version.split("."))


class Notes(unittest.TestCase):
    def test_newest_note_is_this_version(self):
        self.assertEqual(RELEASES[0]["version"], (ROOT / "VERSION").read_text().strip())

    def test_seen_marker_follows_the_newest_note(self):
        self.assertEqual(config.WHATS_NEW_ID, RELEASES[0]["version"])

    def test_versions_run_newest_first_with_no_repeat(self):
        keys = [version_key(r["version"]) for r in RELEASES]
        self.assertEqual(keys, sorted(keys, reverse=True))
        self.assertEqual(len(keys), len(set(keys)))

    def test_starts_at_1_10_0(self):
        self.assertEqual(RELEASES[-1]["version"], "1.10.0")

    def test_every_release_has_a_note_and_every_note_a_release(self):
        files = {path.stem for path in NOTES.glob("*.html")}
        self.assertEqual(files, {r["version"] for r in RELEASES})

    def test_every_release_has_a_title_and_a_real_date(self):
        for release in RELEASES:
            self.assertTrue(release["title"], release["version"])
            date.fromisoformat(release["date"])

    def test_a_note_does_not_announce_a_newer_version(self):
        for release in RELEASES:
            text = (NOTES / f"{release['version']}.html").read_text(encoding="utf-8")
            for found in re.findall(r"\b(1\.\d+\.\d+)\b", text):
                self.assertLessEqual(version_key(found), version_key(release["version"]), (release["version"], found))


class WhatToChange(unittest.TestCase):
    """Each version says what matters most and what to change for it."""

    def test_every_release_has_its_highlights(self):
        for release in RELEASES:
            self.assertTrue(1 <= len(release.get("highlights", [])) <= 3, release["version"])

    def test_actions_are_well_formed(self):
        from core.patch_notes import FILES, LEVELS

        for release in RELEASES:
            self.assertIsInstance(release.get("actions"), list, release["version"])
            for action in release["actions"]:
                self.assertIn(action["level"], LEVELS, release["version"])
                self.assertIn(action["file"], FILES, release["version"])
                self.assertTrue(action["when"] and action["do"], release["version"])
                self.assertIsInstance(action["lines"], list, release["version"])

    def test_pending_actions_are_those_of_the_versions_not_read(self):
        from core.patch_notes import pending_actions, unread

        self.assertEqual(["1.21.0", "1.20.0", "1.19.0", "1.18.2"], [r["version"] for r in unread("1.17.0")][:4])
        self.assertEqual({"1.20.0", "1.19.0", "1.18.0"}, {a["version"] for a in pending_actions("1.17.0")})
        self.assertEqual([], pending_actions(RELEASES[0]["version"]))
        self.assertEqual(len(RELEASES), len(unread(None)))


class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.app.test_client()
        self.addCleanup(self.set_config, {})

    def set_config(self, values):
        cfg = config.load_config()
        cfg.update(values)
        for key, value in values.items():
            if value is None:
                cfg.pop(key)
        config.save_config(cfg)

    def page(self):
        return self.client.get("/", headers={"Accept": "text/html"}).data.decode()

    def test_two_buttons(self):
        page = self.page()
        self.assertIn('data-action="new"', page)
        self.assertIn('data-action="help"', page)

    def test_new_has_one_tab_per_version_on_the_latest(self):
        page = self.page()
        panel = page[page.index('id="new-modal"'):page.index('id="help-modal"')]
        tabs = re.findall(r'data-new-tab="([\d.]+)"[^>]*aria-selected="(true|false)"', panel)
        self.assertEqual([t[0] for t in tabs], [r["version"] for r in RELEASES])
        self.assertEqual([t[1] for t in tabs].count("true"), 1)
        self.assertEqual(tabs[0][1], "true")
        for release in RELEASES:
            self.assertIn(f'data-new-panel="{release["version"]}"', panel)

    def test_help_has_every_section(self):
        page = self.page()
        panel = page[page.index('id="help-modal"'):]
        for section in HELP_SECTIONS:
            self.assertIn(f'data-doc-section="{section}"', panel, section)
            self.assertIn(f'data-doc-go="{section}"', panel, section)

    def test_help_links_lead_to_real_sections(self):
        for path in HELP.glob("*.html"):
            for target in re.findall(r'data-doc-go="([\w-]+)"', path.read_text(encoding="utf-8")):
                self.assertIn(target, HELP_SECTIONS, path.name)

    def test_nothing_opens_by_itself(self):
        self.set_config({"notes_seen": "1.0.0"})
        self.assertNotIn("data-auto-open", self.page())

    def test_up_to_date_has_no_dot(self):
        self.set_config({"notes_seen": config.WHATS_NEW_ID})
        self.assertNotIn('class="new-dot"', self.page())

    def test_older_install_has_the_dot_until_opened(self):
        self.set_config({"notes_seen": "1.0.0"})
        self.assertIn('class="new-dot"', self.page())
        self.assertEqual(self.client.post("/api/whats-new/seen", json={}).status_code, 200)
        self.assertNotIn('class="new-dot"', self.page())

    def test_old_downloader_install_has_the_dot(self):
        self.set_config({"notes_seen": config.WHATS_NEW_ID, config.LEGACY_DOWNLOADER_KEY: "http://old"})
        self.assertIn('class="new-dot"', self.page())
        self.client.post("/api/whats-new/seen", json={})
        self.assertNotIn('class="new-dot"', self.page())

    def test_saving_settings_does_not_bring_the_dot_back(self):
        self.set_config({"notes_seen": "1.12.0"})
        self.client.post("/api/whats-new/seen", json={})
        form = {"scan_dirs": "/music/library", "playlists_base_dir": "/music/playlists"}
        self.client.post("/config", data=form)
        self.assertNotIn('class="new-dot"', self.page())

    def test_a_version_starts_with_what_to_change(self):
        self.set_config({"notes_seen": config.WHATS_NEW_ID})
        page = self.page()
        panel = page[page.index('id="new-modal"'):page.index('id="help-modal"')]
        with_actions = next(r["version"] for r in RELEASES if r["actions"])
        newest = panel[panel.index(f'data-new-panel="{with_actions}"'):]
        self.assertIn("To do", newest[:newest.index("note-details")])
        self.assertIn('data-copy-line="TRUSTED_PROXIES=1"', panel)
        self.assertIn("Nothing to change", panel)
        self.assertIn("note-flag", panel)
        # Up to date: no summary of the versions not read.
        self.assertNotIn("note-since", panel)

    def test_jumping_versions_shows_everything_to_change_since(self):
        self.set_config({"notes_seen": "1.17.0"})
        page = self.page()
        panel = page[page.index('id="new-modal"'):page.index('id="help-modal"')]
        since = panel[panel.index("note-since"):panel.index("doc-body")]
        self.assertIn("Since 1.17.0", since)
        self.assertIn("TRUSTED_PROXIES=1", since)
        self.assertIn("^/api/v1/", since)

    def test_the_api_says_what_to_change_since(self):
        self.set_config({"notes_seen": "1.17.0"})
        answer = self.client.get("/api/v1/content/notes").get_json()
        self.assertEqual("1.17.0", answer["since"])
        self.assertEqual({"1.20.0", "1.19.0", "1.18.0"}, {a["version"] for a in answer["pending_actions"]})
        newest = answer["notes"][0]
        self.assertTrue(newest["highlights"])
        older = next(n for n in answer["notes"] if n["version"] == "1.19.0")
        self.assertEqual(["TRUSTED_PROXIES=1", "COOKIE_SECURE=true"], older["actions"][0]["lines"])

    def test_live_setup_checks_stay_in_help(self):
        page = self.page()
        panel = page[page.index('id="help-modal"'):]
        self.assertIn("data-help-account", panel)
        self.assertIn("data-help-downloads", panel)

    def test_both_repair_buttons_exist(self):
        page = self.page()
        new = page[page.index('id="new-modal"'):page.index('id="help-modal"')]
        self.assertIn('data-action="repair-downloads"', new)
        self.assertIn('data-action="repair-downloads"', page[page.index('id="help-modal"'):])


if __name__ == "__main__":
    unittest.main()
