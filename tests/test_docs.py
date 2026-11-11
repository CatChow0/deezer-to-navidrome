"""The documentation keeps up with the code: every environment variable the app
reads is in the tables of both READMEs (and nothing there is unknown), and the
README's Upgrading section lists what each version's notes ask to change."""
import re
import unittest
from pathlib import Path

from core.patch_notes import RELEASES

ROOT = Path(__file__).resolve().parent.parent
# Read by the code, documented nowhere on purpose: the tests' switch.
INTERNAL = {"D2N_SCHEDULER"}
# Documented as a pattern: one per Navidrome account.
PATTERNS = {"SCROBBLE_TOKEN_ND2"}

_READS = (
    r'environ(?:\.get)?\(\s*"([A-Z][A-Z0-9_]+)"',
    r'environ\[\s*"([A-Z][A-Z0-9_]+)"\s*\]',
    r'env_list\(\s*"([A-Z][A-Z0-9_]+)"',
    r'env_host_to_navidrome_roots\(\s*"([A-Z][A-Z0-9_]+)"',
    r'^(?:KEY_ENV|ENV_[A-Z]+)\s*=\s*"([A-Z][A-Z0-9_]+)"',
)


def variables_read() -> set:
    found = set()
    files = [ROOT / "app.py", *(ROOT / "core").glob("*.py"), *(ROOT / "routes").rglob("*.py")]
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in _READS:
            found |= set(re.findall(pattern, text, re.MULTILINE))
    entrypoint = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
    found |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]+):-", entrypoint))
    # Secrets an environment variable can set (core/config.py).
    from core import config

    for name in ("deezer_arl", "deezer_arl_premium", "api_token", "scrobble_token"):
        assert config._ENV_SECRETS.match(name), name
        found.add(name.upper())
    return found - INTERNAL


def documented(path) -> set:
    names = set()
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        if line.startswith("| `"):
            first_cell = line.split("|")[1]
            names |= set(re.findall(r"`([A-Z][A-Z0-9_]+)`", first_cell))
    return names


class EnvironmentTables(unittest.TestCase):
    def test_every_variable_read_is_in_both_tables(self):
        read = variables_read()
        for path in ("README.md", "DOCKERHUB_README.md"):
            with self.subTest(path=path):
                self.assertEqual(set(), read - documented(path))

    def test_every_variable_documented_is_read(self):
        read = variables_read() | PATTERNS
        for path in ("README.md", "DOCKERHUB_README.md"):
            with self.subTest(path=path):
                # The data files table names files, not variables.
                self.assertEqual(set(), {n for n in documented(path) if n.isupper()} - read)


class Upgrading(unittest.TestCase):
    def section(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        start = text.index('<a id="upgrading"></a>')
        return text[start:text.index("\n---", start)]

    def test_each_version_to_change_has_its_part(self):
        section = self.section()
        for release in RELEASES:
            if not release["actions"]:
                continue
            headings = [h for h in re.findall(r"^#### (.+)$", section, re.MULTILINE) if release["version"] in h]
            self.assertTrue(headings, release["version"])
            part = section[section.index(f"#### {headings[0]}"):]
            part = part[:part.find("\n#### ", 5) if "\n#### " in part[5:] else len(part)]
            for action in release["actions"]:
                for line in action["lines"]:
                    variable = line.split("=")[0].strip("- ").split(":")[0]
                    self.assertIn(variable, part, (release["version"], line))


if __name__ == "__main__":
    unittest.main()
