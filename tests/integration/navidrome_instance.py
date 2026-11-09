"""A real Navidrome in Docker, for checks the fake server cannot prove.

    python tests/integration/navidrome_instance.py --source <folder of audio files> [--keep]

It copies a few audio files from --source (only read) into a throwaway folder,
starts deluan/navidrome on 127.0.0.1 with an admin and a second user, waits for
the scan, then checks this app's Subsonic client against it for both users.
Without --keep, the container and the folder are removed at the end."""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import subsonic  # noqa: E402

IMAGE = "deluan/navidrome:latest"
NAME = "d2n-navidrome-test"
ADMIN = ("admin", "admin-pass-1")
SECOND = ("bob", "bob-pass-1")
AUDIO = (".flac", ".mp3", ".ogg", ".m4a")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def docker(*args, check=True):
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True, env=env)


def copy_library(source: Path, target: Path, count: int) -> int:
    files = [p for p in sorted(source.rglob("*")) if p.suffix.lower() in AUDIO][:count]
    for i, path in enumerate(files):
        shutil.copy2(path, target / f"{i:02} - {path.name}")
    return len(files)


def wait_for(url, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{url}/ping", timeout=2).ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def native_token(url, user, password):
    response = requests.post(f"{url}/auth/login", json={"username": user, "password": password}, timeout=10)
    response.raise_for_status()
    return response.json()["token"]


def create_user(url, token, user, password):
    response = requests.post(f"{url}/api/user", headers={"x-nd-authorization": f"Bearer {token}"},
                             json={"userName": user, "name": user.title(), "password": password, "isAdmin": False},
                             timeout=10)
    return response.status_code, response.text[:200]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--count", type=int, default=6)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="d2n-navidrome-"))
    (work / "music").mkdir()
    (work / "data").mkdir()
    copied = copy_library(args.source, work / "music", args.count)
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    docker("rm", "-f", NAME, check=False)
    docker("run", "-d", "--name", NAME, "-p", f"127.0.0.1:{port}:4533",
           "-e", f"ND_DEVAUTOCREATEADMINPASSWORD={ADMIN[1]}", "-e", "ND_LOGLEVEL=warn",
           "-v", f"{work / 'music'}:/music:ro", "-v", f"{work / 'data'}:/data", IMAGE)
    report = {"url": url, "copied": copied, "folder": str(work)}
    try:
        report["started"] = wait_for(url)
        token = native_token(url, *ADMIN)
        report["second_user"] = create_user(url, token, *SECOND)
        time.sleep(3)
        report["admin_test"] = subsonic.test_connection(url, ADMIN[0], "password", ADMIN[1])
        report["user_test"] = subsonic.test_connection(url, SECOND[0], "password", SECOND[1])
        report["wrong_password"] = subsonic.test_connection(url, ADMIN[0], "password", "nope")["error"]
        client = subsonic.Client(url, ADMIN[0], "password", ADMIN[1])
        report["extensions"] = client.extensions()
        report["scan"] = client.call("getScanStatus").get("scanStatus")
        print(json.dumps(report, indent=2, default=str))
    finally:
        if not args.keep:
            docker("rm", "-f", NAME, check=False)
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
