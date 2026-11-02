"""Checks for the signed update notice. Run: uv run tests/test_updates.py"""
import base64
import json
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gt1.updates import Rejected, verify  # noqa: E402

NOW = 1_800_000_000
key = Ed25519PrivateKey.generate()
other = Ed25519PrivateKey.generate()


def pub(k):
    return base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw,
                                                        serialization.PublicFormat.Raw)).decode()


KEYS = {"k1": pub(key)}


def envelope(signer=key, key_id="k1", tamper=False, **over):
    payload = {"seq": NOW, "issued_at": NOW, "expires_at": NOW + 86400, "version": "0.2.0",
               "notes": "Faster patch loading", "download_url": "https://allankirsten.com/lab/gt-pilot/download"}
    payload.update(over)
    body = json.dumps(payload).encode()
    sig = signer.sign(body)
    if tamper:
        body = body.replace(b"allankirsten.com", b"evil.example.com")
    return json.dumps({"key_id": key_id, "payload": base64.b64encode(body).decode(),
                       "signature": base64.b64encode(sig).decode()}).encode()


def rejects(data, last_seq=0, why=""):
    try:
        verify(data, keys=KEYS, now=NOW, last_seq=last_seq)
    except Rejected as e:
        assert why in str(e), f"expected '{why}', got '{e}'"
        return
    raise AssertionError(f"accepted but should reject ({why})")


ok = verify(envelope(), keys=KEYS, now=NOW)
assert ok["version"] == "0.2.0" and ok["download_url"].startswith("https://allankirsten.com/")
rejects(envelope(tamper=True), why="bad signature")              # site hacked, link swapped
rejects(envelope(signer=other), why="bad signature")             # signed with someone else's key
rejects(envelope(key_id="unknown"), why="malformed")             # unknown key id
rejects(envelope(seq=NOW - 10), last_seq=NOW, why="replay")      # old legit notice put back
rejects(envelope(expires_at=NOW - 1), why="expired")             # stale notice
rejects(envelope(issued_at=NOW + 3600), why="not yet valid")     # clock games
rejects(envelope(download_url="http://allankirsten.com/x"), why="https")
rejects(b"<html>hacked</html>", why="malformed")                 # junk instead of json
rejects(json.dumps({"key_id": "k1", "payload": "!!", "signature": "x"}).encode(), why="malformed")
print("all update-notice checks passed")


# The request says version, system and "first" once per computer, never anything else.
import tempfile  # noqa: E402

from gt1 import updates  # noqa: E402

def sessions(n, fetch):
    updates._fetch = fetch
    for _ in range(n):
        updates._checked = False
        updates.check()

with tempfile.TemporaryDirectory() as d:
    updates.STATE_FILE, updates.CACHE_DIR = Path(d) / "update_state.json", Path(d)
    updates.enabled = lambda: True
    seen = []

    def offline(url=None, ua=None):
        seen.append(ua)
        raise Rejected("offline")

    sessions(2, offline)  # the site never heard from this computer: keep saying "first"
    assert all(u.endswith(" first") for u in seen), seen
    assert seen[0].startswith(f"gt-pilot/{updates.current_version()} ") and seen[0].split()[1] in ("mac", "windows", "other")
    sessions(2, lambda url=None, ua=None: seen.append(ua) or b"{}")  # reached the site (invalid notice is fine)
    assert seen[-2].endswith(" first") and not seen[-1].endswith(" first"), seen

with tempfile.TemporaryDirectory() as d:  # installed before 0.4.0: already has "seq", so not a new person
    (Path(d) / "update_state.json").write_text('{"seq": 3}')
    updates.STATE_FILE, updates.CACHE_DIR = Path(d) / "update_state.json", Path(d)
    seen = []
    sessions(1, lambda url=None, ua=None: seen.append(ua) or b"{}")
    assert not seen[0].endswith(" first"), seen
print("user agent checks passed")
