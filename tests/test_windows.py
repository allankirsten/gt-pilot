"""Windows paths, simulated on any OS: data folder, map lookup and messages. No pedal needed."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gt1 import params  # noqa: E402
from gt1.profiles import GT1, GT100  # noqa: E402

root = Path(tempfile.mkdtemp())
os.environ["ProgramFiles(x86)"] = str(root / "Program Files (x86)")
os.environ["ProgramFiles"] = str(root / "Program Files")
os.environ["LOCALAPPDATA"] = str(root / "Local")
params.IS_WINDOWS = True

# the GT-1 editor installs as "BOSS TONE STUDIO for GT-1" with the map in _assets/data
cands = params.map_candidates(GT1)
assert root / "Program Files (x86)" / "BOSS TONE STUDIO for GT-1" / "_assets/data/addressmap_gt.json" in cands
assert root / "Local" / "Programs" / "BOSS TONE STUDIO for GT-1" / "_assets/data/addressmap_gt.json" in cands
# the GT-100 editor folder never matches the GT-1 one, and vice versa
assert not any("for GT-1" in str(c) for c in params.map_candidates(GT100))

# find_map picks it up and caches it
target = root / "Program Files (x86)" / "BOSS TONE STUDIO for GT-1" / "_assets" / "data"
target.mkdir(parents=True)
(target / "addressmap_gt.json").write_text('{"temporary": [], "system": []}')
params.CACHE_DIR = root / "Roaming" / "GT Pilot"
found = params.find_map(GT1)
assert found == params.CACHE_DIR / "addressmap_gt.json" and found.exists()

# macOS lookup is unchanged
params.IS_WINDOWS = False
assert params.map_candidates(GT1)[0] == Path("/Applications/BOSS_TONE_STUDIO_for_GT1.app") / params.MAP_IN_APP
print("windows paths: all checks passed")
