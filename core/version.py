import time
from pathlib import Path

import requests

VERSION_CHECK_CACHE = {
    "latest_version": None,
    "latest_url": None,
    "cached_at": None,
}


def get_app_version():
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
    except Exception:
        pass
    return "unknown"


def fetch_latest_github_release():
    try:
        resp = requests.get(
            "https://api.github.com/repos/CatChow0/deezer-to-navidrome/releases/latest",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        version = data.get("tag_name", "").lstrip("v")
        url = data.get("html_url", "")
        return version if version else None, url
    except Exception:
        return None, None


def fetch_latest_docker_tag():
    try:
        resp = requests.get(
            "https://hub.docker.com/v2/repositories/catchow/deezer-to-navidrome/tags?page_size=25",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        semver_tags = []
        for r in results:
            name = r.get("name", "")
            parts = name.split(".")
            if len(parts) >= 2 and all(p.isdigit() for p in parts):
                semver_tags.append(name)
        if semver_tags:
            semver_tags.sort(key=lambda v: [int(x) for x in v.split(".")], reverse=True)
            return semver_tags[0], "https://hub.docker.com/r/catchow/deezer-to-navidrome/tags"
        return None, None
    except Exception:
        return None, None


def compare_versions(v1, v2):
    try:
        parts1 = [int(x) for x in v1.split("-")[0].split(".")]
        parts2 = [int(x) for x in v2.split("-")[0].split(".")]
        max_len = max(len(parts1), len(parts2))
        parts1.extend([0] * (max_len - len(parts1)))
        parts2.extend([0] * (max_len - len(parts2)))
        return parts1 < parts2
    except Exception:
        return False


def get_latest_available_version():
    now = time.time()
    cache_duration = 3600

    if (
        VERSION_CHECK_CACHE["cached_at"]
        and now - VERSION_CHECK_CACHE["cached_at"] < cache_duration
        and VERSION_CHECK_CACHE["latest_version"]
    ):
        return {
            "version": VERSION_CHECK_CACHE["latest_version"],
            "url": VERSION_CHECK_CACHE["latest_url"],
            "source": "cached",
        }

    current_version = get_app_version()
    latest_version = None
    latest_url = None
    source = None

    gh_version, gh_url = fetch_latest_github_release()
    if gh_version and compare_versions(current_version, gh_version):
        latest_version = gh_version
        latest_url = gh_url
        source = "github"

    if not latest_version:
        docker_version, docker_url = fetch_latest_docker_tag()
        if docker_version and compare_versions(current_version, docker_version):
            latest_version = docker_version
            latest_url = docker_url
            source = "docker"

    VERSION_CHECK_CACHE["latest_version"] = latest_version
    VERSION_CHECK_CACHE["latest_url"] = latest_url
    VERSION_CHECK_CACHE["cached_at"] = now

    return {"version": latest_version, "url": latest_url, "source": source}
