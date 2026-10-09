"""Pedal profiles: port matching, slots and type lists. No pedal, no editor app and no user folders needed."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["HOME"] = tempfile.mkdtemp()  # importing params must never touch the real Application Support
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gt1 import params  # noqa: E402
from gt1.device import find_pedal  # noqa: E402
from gt1.profiles import DEFAULT, GT001, GT1, GT100, for_port  # noqa: E402

# --- importing never migrates folders anymore
assert not (Path(os.environ["HOME"]) / "Library/Application Support/GT Pilot").exists()

# --- port matching: exact, so a GT-100 is never opened as a GT-1
assert for_port("GT-1") is GT1
assert for_port("GT-1 MIDI") is GT1
assert for_port("GT-100") is GT100
assert for_port("GT-100 MIDI") is GT100
assert for_port("GT-001") is GT001
for other in ("GT-1000", "GT-1000CORE", "GT-1B", "GT-10", "GX-100", "IAC Driver Bus 1"):
    assert for_port(other) is None, other
assert find_pedal(["IAC Driver Bus 1", "GT-100"]) == ("GT-100", GT100)
assert find_pedal(["GT-1B"]) == (None, None)

# --- slots: GT-1 addresses and labels are exactly what 0.1-0.3 used
for s in (1, 50, 99):
    assert GT1.slot_addr(s) == [0x10, s - 1, 0x00, 0x00]
    assert GT1.slot_label(s) == f"U{s:02d}"
assert GT1.parse_slot(5) == 5 and GT1.parse_slot("U05") == 5 and GT1.parse_slot("u5") == 5
for bad in (0, 100, "U12-3"):
    try:
        GT1.parse_slot(bad)
        raise AssertionError(f"GT-1 accepted {bad}")
    except ValueError:
        pass

# GT-100: U01-1..U50-4; 1-128 at 10 nn, 129-200 at 11 00..11 47 (MIDI Implementation)
assert GT100.slot_addr(1) == [0x10, 0x00, 0, 0]
assert GT100.slot_addr(128) == [0x10, 0x7F, 0, 0]
assert GT100.slot_addr(129) == [0x11, 0x00, 0, 0]
assert GT100.slot_addr(200) == [0x11, 0x47, 0, 0]
assert GT100.slot_label(1) == "U01-1" and GT100.slot_label(4) == "U01-4" and GT100.slot_label(5) == "U02-1"
assert GT100.slot_label(200) == "U50-4"
assert GT100.parse_slot("U12-3") == 47 and GT100.parse_slot("#U50-4") == 200 and GT100.parse_slot(129) == 129
assert all(GT100.parse_slot(GT100.slot_label(s)) == s for s in range(1, 201))

# --- model IDs (3 bytes on the GT-100)
assert GT1.model == (0, 0, 0, 0x30) and GT100.model == (0, 0, 0x60) and GT001.model == (0, 0, 0, 0x06)

# --- type lists: lengths match the documented value ranges, and the shifted orders are caught
assert len(GT100.types["OD_DS"]) == 0x17 and len(GT100.types["SUB_OD_DS"]) == 0x16
assert len(GT100.types["PREAMP"]) == 0x1C and len(GT100.types["FX"]) == 0x23
assert len(GT100.types["COMP"]) == 8 and len(GT100.types["REVERB"]) == 7
assert GT100.type_index("OD_DS", "BLUES OD") == 0x0A and GT1.type_index("OD_DS", "BLUES OD") == 11
assert GT100.type_index("OD_DS", "A-DIST") == 0x16 and GT100.type_index("OD_DS", "CUSTOM") == 0x15
assert GT100.type_index("PREAMP", "ORNG ROCK") == 0x1B and GT1.type_index("PREAMP", "ORNG ROCK") == 26
assert GT100.type_index("FX", "RING MOD") == 0x1B and GT1.type_index("FX", "RING MOD") is None
assert GT100.type_index("FX", "AC.GUITAR SIM") == 0x1F
# the doc's spellings are accepted
assert GT100.type_index("OD_DS", "DIST") == 0x0E
assert GT100.type_index("PREAMP", "R-FIRE MODERN") == 0x15
assert GT100.type_index("REVERB", "HALL1") == 2 and GT100.type_index("REVERB", "MODURATE") == 6
assert GT100.type_index("OD_DS", "'60S FUZZ") == 0x13
assert GT1.type_index("DELAY", "TERA ECHO") == 6 and GT100.type_index("DELAY", "TERA ECHO") is None

# --- ParamMap uses the profile's lists: same name, different value per pedal
fake = {"temporary": [
    {"name": "PATCH NAME1", "address": "60,00,00,00", "size": "00,00,00,01"},
    {"name": "OD/DS: TYPE", "address": "60,00,00,31", "size": "00,00,00,01"},
    {"name": "PREAMP A: GAIN", "address": "60,00,00,52", "size": "00,00,00,01"},
    {"name": "DELAY: DELAY TIME", "address": "60,00,05,62", "size": "00,00,00,02"}],
    "system": []}
path = Path(tempfile.mkdtemp()) / "map.json"
path.write_text(json.dumps(fake))
m1, m100 = params.ParamMap(GT1, path), params.ParamMap(GT100, path)
assert m1.value_for("OD/DS: TYPE", "Blues OD") == 11
assert m100.value_for("OD/DS: TYPE", "Blues OD") == 10
assert m100.label("OD/DS: TYPE", 10) == "BLUES OD" and m1.label("OD/DS: TYPE", 10) == "A-DIST"
assert m100.value_for("PREAMP A: GAIN", 120) == 120
assert m100.encode("DELAY: DELAY TIME", 2000) == ([0x60, 0, 0x05, 0x62], [0x0F, 0x50])
try:
    m1.value_for("OD/DS: TYPE", "CUSTOM")
    raise AssertionError("GT-1 accepted a GT-100-only drive")
except ValueError as e:
    assert "GT-1" in str(e)

# --- the default stays the GT-1, so nothing changes for existing users
assert DEFAULT is GT1 and params.PATCH_SIZE == 2175 and params.USER_SLOTS == 99
print("profiles: all checks passed")
