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
                 "releases", "stats", "settings", "sign-in", "troubleshooting")


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
        self.set_config({"notes_seen": "1.12.0"})
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
