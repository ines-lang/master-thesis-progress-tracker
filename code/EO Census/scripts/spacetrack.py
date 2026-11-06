"""Space-Track session shared by the EO Census scripts. Credentials are never printed or written."""
import json
import os
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

CENSUS_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = CENSUS_DIR.parents[2] / "master-thesis" / ".env"       # <thesis folder>/master-thesis/.env
BASE = "https://www.space-track.org"


def credentials():
    """SPACETRACK_USERNAME / SPACETRACK_PASSWORD from the environment, else from ENV_FILE (KEY=value lines)."""
    keys = ["SPACETRACK_USERNAME", "SPACETRACK_PASSWORD"]
    env = {k: os.environ.get(k) for k in keys}
    if not all(env.values()) and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            k, _, v = line.partition("=")
            k = k.strip().removeprefix("export ").strip()
            if k in keys and not env[k]:
                env[k] = v.strip().strip('"').strip("'")
    missing = [k for k in keys if not env[k]]
    if missing:
        raise SystemExit(f"missing {missing}: set them in the environment or in {ENV_FILE}")
    return env["SPACETRACK_USERNAME"], env["SPACETRACK_PASSWORD"]


def session():
    """Logged-in opener; call query(opener, path) with it, then logout(opener)."""
    user, password = credentials()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    with opener.open(f"{BASE}/ajaxauth/login", timeout=60,
                     data=urllib.parse.urlencode({"identity": user, "password": password}).encode()) as r:
        if b"Failed" in r.read():
            raise SystemExit("Space-Track login failed (check the credentials)")
    return opener


def query(opener, path):
    """GET BASE/basicspacedata/query/<path> as JSON."""
    with opener.open(f"{BASE}/basicspacedata/query/{path}", timeout=300) as r:
        return json.load(r)


def logout(opener):
    opener.open(f"{BASE}/ajaxauth/logout", timeout=60)
