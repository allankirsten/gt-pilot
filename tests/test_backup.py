"""The first-connection backup prompt: shown until this pedal has a full backup on this computer."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["HOME"] = os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import server  # noqa: E402
from gt1.profiles import GT1, GT100  # noqa: E402

server.CACHE_DIR = Path(tempfile.mkdtemp())
assert not server._has_full_backup(GT1)
folder = server.CACHE_DIR / "backups"
folder.mkdir(parents=True)
(folder / "gt100_all_user_patches_20261013-120000.json").write_text("{}")
assert server._has_full_backup(GT100) and not server._has_full_backup(GT1)   # one pedal's backup never counts for another
(folder / "patch_U05_before_save.json").write_text("{}")
assert not server._has_full_backup(GT1)                                      # a single-slot backup is not a full one
(folder / "all_user_patches_20261013-120000.json").write_text("{}")
assert server._has_full_backup(GT1)
print("first backup: all checks passed")
