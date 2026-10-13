"""Signed update notice.

Reads a small public file (latest.json) that says which version is the newest. Nothing about the
user or the pedal is sent. The file only counts if it carries a valid Ed25519 signature from the
release key, which never lives on the website or on GitHub: someone who breaks into the site can
replace the file but cannot sign it, so a forged notice is ignored.

Anything unexpected (no network, slow server, oversized file, redirect, bad signature, stale or
replayed notice) is treated as "no update" and never as an error.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .params import CACHE_DIR

LATEST_URL = "https://allankirsten.com/lab/gt-pilot/latest.json"
# Public half of the release key. The private half stays offline (macOS Keychain on the release Mac).
PUBLIC_KEYS = {
    "release-2026-1": "b2ZfdqqNstHX2MsqQMcuJJokZTQdrDCwBtecrdckOk0=",
}
TIMEOUT = 3
MAX_BYTES = 64 * 1024
STATE_FILE = CACHE_DIR / "update_state.json"
MANIFEST = Path(__file__).resolve().parents[2] / "manifest.json"

_checked = False
_result = None


class Rejected(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None  # a redirect means the file moved or was hijacked: do not follow


def enabled():
    return os.environ.get("DIALIN_CHECK_UPDATES", "true").strip().lower() not in ("false", "0", "no", "")


def current_version():
    try:
        return json.loads(MANIFEST.read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "0"


def _vtuple(v):
    """'0.4.0-beta.1' sorts below '0.4.0', so beta testers still hear about the final release."""
    base, _, pre = str(v).partition("-")
    return tuple(int(p) for p in base.split(".") if p.isdigit()) + (0 if pre else 1,)


def _load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_state(state):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))
    except OSError:
        pass


def verify(envelope_bytes, keys=None, now=None, last_seq=0):
    """Return the payload if the envelope is authentic, fresh and newer than last_seq; else raise Rejected."""
    keys = PUBLIC_KEYS if keys is None else keys
    now = time.time() if now is None else now
    try:
        env = json.loads(envelope_bytes)
        key_b64 = keys[env["key_id"]]
        payload_bytes = base64.b64decode(env["payload"], validate=True)
        signature = base64.b64decode(env["signature"], validate=True)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key_b64)).verify(signature, payload_bytes)
        payload = json.loads(payload_bytes)
        seq, issued, expires = int(payload["seq"]), float(payload["issued_at"]), float(payload["expires_at"])
        version, url = str(payload["version"]), str(payload["download_url"])
    except InvalidSignature:
        raise Rejected("bad signature")
    except (ValueError, KeyError, TypeError) as e:
        raise Rejected(f"malformed: {e}")
    if seq < last_seq:
        raise Rejected("older than a notice already seen (replay)")
    if issued > now + 300 or expires < now:
        raise Rejected("expired or not yet valid")
    if not url.startswith("https://"):
        raise Rejected("download link is not https")
    return {"seq": seq, "version": version, "download_url": url,
            "notes": str(payload.get("notes", ""))[:300], "sha256": str(payload.get("sha256", ""))[:64]}


def _fetch(url=None):
    url = url or LATEST_URL
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "gt-pilot-update-check"})
    with opener.open(req, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise Rejected(f"http {r.status}")
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Rejected("file too large")
    return data


def check():
    """Once per session: {'version','download_url','notes','sha256'} if a newer signed version exists, else None."""
    global _checked, _result
    if _checked:
        return _result
    _checked = True
    if not enabled():
        return None
    state = _load_state()
    try:
        notice = verify(_fetch(), last_seq=int(state.get("seq", 0)))
    except (Rejected, urllib.error.URLError, OSError, ValueError):
        return None
    _save_state({"seq": notice["seq"]})
    if _vtuple(notice["version"]) > _vtuple(current_version()):
        _result = {k: notice[k] for k in ("version", "download_url", "notes", "sha256")}
    return _result
