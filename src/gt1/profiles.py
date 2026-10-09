"""What changes from one BOSS GT pedal to another.

The GT-1 and GT-100 share almost everything: the editor app ships the same addressmap_gt.json format,
every GT-100 parameter exists in the GT-1 map with the same name and address, and the edit buffer,
patch switching and write commands are identical. What differs lives here: the SysEx model ID, the
patch size, how many user slots there are and how they are named, where the editor app is installed,
and the order of the type lists (same model names, different values: sending a GT-1 value to a GT-100
silently picks another effect).

GT-100 / GT-001 values come from the official "GT-100/GT-001 MIDI Implementation" (BOSS) and the
address map in BOSS TONE STUDIO for GT 1.1.3. They are not yet tested on hardware.
"""
import os
import re
from dataclasses import dataclass, field


def _norm(name):
    """Compare model names loosely: 'HALL1' == 'Hall 1', "'60S FUZZ" == '60s fuzz'."""
    return re.sub(r"[^a-z0-9+]", "", name.lower())


@dataclass(frozen=True)
class Profile:
    key: str                  # stable id, used for cache and backup names
    name: str                 # what the player sees: "GT-1"
    port: str                 # regex matched against MIDI port and audio device names
    model: tuple              # SysEx model ID bytes
    patch_size: int           # bytes in one patch, from the edit buffer start
    user_slots: int
    app_label: str            # editor app, for messages
    app_candidates: tuple     # where that app may be installed
    map_cache: str            # cache file name for its address map
    types: dict               # type table name -> model names in value order
    type_params: dict         # parameter -> type table name
    aliases: dict = field(default_factory=dict)   # other spellings Claude may use -> table name
    slots_per_bank: int = 0   # 0 = plain U01..U99 numbering
    tested: bool = True

    def slot_addr(self, slot):
        """User patch address. Slots past 128 carry into the next address byte (10 7F -> 11 00)."""
        n = slot - 1
        return [0x10 + (n >> 7), n & 0x7F, 0x00, 0x00]

    def slot_label(self, slot):
        if not self.slots_per_bank:
            return f"U{slot:02d}"
        bank, num = divmod(slot - 1, self.slots_per_bank)
        return f"U{bank + 1:02d}-{num + 1}"

    def parse_slot(self, slot):
        """Accepts a number (1..user_slots) or a label as shown on the pedal ('U05', 'U12-3')."""
        if isinstance(slot, str):
            s = slot.strip().upper().lstrip("#")
            m = re.fullmatch(r"U?(\d{1,3})(?:-(\d))?", s)
            if not m:
                raise ValueError(f"'{slot}' is not a {self.name} slot. Use a number or a label like {self.slot_label(1)}.")
            if m.group(2):
                if not self.slots_per_bank:
                    raise ValueError(f"The {self.name} numbers slots {self.slot_label(1)} to {self.slot_label(self.user_slots)}.")
                slot = (int(m.group(1)) - 1) * self.slots_per_bank + int(m.group(2))
            else:
                slot = int(m.group(1))
        if not 1 <= slot <= self.user_slots:
            raise ValueError(f"Slot must be between {self.slot_label(1)} and {self.slot_label(self.user_slots)} "
                             f"(1 to {self.user_slots}).")
        return slot

    def matches(self, port_name):
        return re.search(self.port, port_name) is not None

    def type_index(self, table, value):
        """Model name -> value for this pedal, or None."""
        want = _norm(self.aliases.get(_norm(value), value))
        for i, t in enumerate(self.types[table]):
            if _norm(t) == want:
                return i
        return None


_GT1_TYPES = {
    "OD_DS": ["MID BOOST", "CLEAN BOOST", "TREBLE BOOST", "CRUNCH", "NATURAL OD", "WARM OD", "FAT DS",
              "LEAD DS", "METAL DS", "OCT FUZZ", "A-DIST", "BLUES OD", "OD-1", "T-SCREAM", "TURBO OD",
              "DISTORTION", "RAT", "GUV DS", "DST+", "METAL ZONE", "60S FUZZ", "MUFF FUZZ"],
    "PREAMP": ["NATURAL CLEAN", "FULL RANGE", "COMBO CRUNCH", "STACK CRUNCH", "HiGAIN STACK",
               "POWER DRIVE", "EXTREME LEAD", "CORE METAL", "JC-120", "CLEAN TWIN", "PRO CRUNCH", "TWEED",
               "DELUXE CRUNCH", "VO DRIVE", "VO LEAD", "MATCH DRIVE", "BG LEAD", "BG DRIVE", "MS1959 I",
               "MS1959 I+II", "R-FIER VINTAGE", "R-FIER MODERN", "T-AMP LEAD", "SLDN", "5150 DRIVE",
               "BGNR UB METAL", "ORNG ROCK"],
    "FX": ["COMPRESSOR", "LIMITER", "T.WAH", "GRAPHIC EQ", "PARAMETRIC EQ", "TONE MODIFY", "GUITAR SIM",
           "AC.GUITAR SIM", "SLOW GEAR", "OCTAVE", "PITCH SHIFTER", "HARMONIST", "OVERTONE", "FEEDBACKER",
           "AC.PROCESSOR", "PHASER", "FLANGER", "TREMOLO", "ROTARY", "UNI-V", "VIBRATO", "CHORUS", "SUB DELAY"],
    "COMP": ["BOSS COMP", "HI-BAND", "LIGHT", "D-COMP", "ORANGE", "FAT", "MILD", "STEREO COMP"],
    "DELAY": ["STANDARD", "PAN", "REVERSE", "ANALOG", "TAPE", "MODULATE", "TERA ECHO"],
    "REVERB": ["AMBIENCE", "ROOM", "HALL 1", "HALL 2", "PLATE", "SPRING", "MODULATE"],
}
_GT1_TYPE_PARAMS = {
    "OD/DS: TYPE": "OD_DS", "PREAMP A: TYPE": "PREAMP", "PREAMP B: TYPE": "PREAMP",
    "COMP: TYPE": "COMP", "FX1: FX TYPE": "FX", "FX2: FX TYPE": "FX", "DELAY: TYPE": "DELAY", "REVERB: TYPE": "REVERB",
}

# GT-100 lists in value order, from the MIDI Implementation tables. Models shared with the GT-1 keep the
# GT-1 spelling (the doc writes DIST, R-FIRE, HALL1, MODURATE); aliases below accept the doc's spellings.
_GT100_TYPES = {
    "OD_DS": ["MID BOOST", "CLEAN BOOST", "TREBLE BOOST", "CRUNCH", "NATURAL OD", "WARM OD", "FAT DS",
              "LEAD DS", "METAL DS", "OCT FUZZ", "BLUES OD", "OD-1", "T-SCREAM", "TURBO OD", "DISTORTION",
              "RAT", "GUV DS", "DST+", "METAL ZONE", "60S FUZZ", "MUFF FUZZ", "CUSTOM", "A-DIST"],
    "SUB_OD_DS": ["MID BOOST", "CLEAN BOOST", "TREBLE BOOST", "CRUNCH", "NATURAL OD", "WARM OD", "FAT DS",
                  "LEAD DS", "METAL DS", "OCT FUZZ", "BLUES OD", "OD-1", "T-SCREAM", "TURBO OD", "DISTORTION",
                  "RAT", "GUV DS", "DST+", "METAL ZONE", "60S FUZZ", "MUFF FUZZ", "A-DIST"],
    "PREAMP": ["NATURAL CLEAN", "FULL RANGE", "COMBO CRUNCH", "STACK CRUNCH", "HiGAIN STACK",
               "POWER DRIVE", "EXTREME LEAD", "CORE METAL", "JC-120", "CLEAN TWIN", "PRO CRUNCH", "TWEED",
               "DELUXE CRUNCH", "VO DRIVE", "VO LEAD", "MATCH DRIVE", "BG LEAD", "BG DRIVE", "MS1959 I",
               "MS1959 I+II", "R-FIER VINTAGE", "R-FIER MODERN", "T-AMP LEAD", "SLDN", "5150 DRIVE",
               "CUSTOM", "BGNR UB METAL", "ORNG ROCK"],
    "FX": ["T.WAH", "AUTO WAH", "SUB WAH", "ADV.COMP", "LIMITER", "SUB OD/DS", "GRAPHIC EQ", "PARAMETRIC EQ",
           "TONE MODIFY", "GUITAR SIM", "SLOW GEAR", "DEFRETTER", "WAVE SYNTH", "SITAR SIM", "OCTAVE",
           "PITCH SHIFTER", "HARMONIST", "SOUND HOLD", "AC.PROCESSOR", "PHASER", "FLANGER", "TREMOLO",
           "ROTARY 1", "UNI-V", "PAN", "SLICER", "VIBRATO", "RING MOD", "HUMANIZER", "2X2 CHORUS",
           "SUB DELAY", "AC.GUITAR SIM", "ROTARY 2", "TERA ECHO", "OVERTONE"],
    "COMP": ["BOSS COMP", "HI-BAND", "LIGHT", "D-COMP", "ORANGE", "FAT", "MILD", "STEREO COMP"],
    "DELAY": ["SINGLE", "PAN", "STEREO", "DUAL-S", "DUAL-P", "DUAL-L/R", "REVERSE", "ANALOG", "TAPE", "MODULATE"],
    "REVERB": ["AMBIENCE", "ROOM", "HALL 1", "HALL 2", "PLATE", "SPRING", "MODULATE"],
}
_GT100_TYPE_PARAMS = {
    **_GT1_TYPE_PARAMS,
    "FX1: SUB OD/DS: TYPE": "SUB_OD_DS", "FX2: SUB OD/DS: TYPE": "SUB_OD_DS",
}
_GT100_ALIASES = {
    "dist": "DISTORTION", "rfirevintage": "R-FIER VINTAGE", "rfiremodern": "R-FIER MODERN",
    "bgnrub": "BGNR UB METAL", "orngrb": "ORNG ROCK", "modurate": "MODULATE", "mod": "MODULATE",
    "teraecho": "TERA ECHO", "acsim": "AC.GUITAR SIM", "compressor": "ADV.COMP", "rotary": "ROTARY 1",
    "chorus": "2X2 CHORUS", "standard": "SINGLE",
}

_GT100_APPS = (
    "/Applications/BOSS TONE STUDIO for GT.app",
    "/Applications/BOSS/BOSS TONE STUDIO for GT.app",
    os.path.expanduser("~/Applications/BOSS TONE STUDIO for GT.app"),
)

GT1 = Profile(
    key="gt1", name="GT-1",
    port=r"(?<![\w-])GT-1(?![0-9A-Za-z])",          # not GT-100, GT-1000 or GT-1B
    model=(0x00, 0x00, 0x00, 0x30),
    patch_size=0x10 * 128 + 0x7F,                   # 2175 bytes, 60 00 00 00 .. 60 00 10 7E
    user_slots=99,
    app_label="BOSS TONE STUDIO for GT-1",
    app_candidates=(
        "/Applications/BOSS_TONE_STUDIO_for_GT1.app",
        "/Applications/BOSS/BOSS_TONE_STUDIO_for_GT1.app",
        os.path.expanduser("~/Applications/BOSS_TONE_STUDIO_for_GT1.app"),
    ),
    map_cache="addressmap_gt.json",                 # name kept from 0.1-0.3 so existing caches stay valid
    types=_GT1_TYPES, type_params=_GT1_TYPE_PARAMS,
    aliases={"dist": "DISTORTION", "rfirevintage": "R-FIER VINTAGE", "rfiremodern": "R-FIER MODERN",
             "hall1": "HALL 1", "hall2": "HALL 2", "modurate": "MODULATE"},
)

GT100 = Profile(
    key="gt100", name="GT-100",
    port=r"(?<![\w-])GT-100(?![0-9A-Za-z])",
    model=(0x00, 0x00, 0x60),                       # 3 bytes on the GT-100
    patch_size=0x10 * 128 + 0x3C,                   # 2108 bytes, through 60 00 10 3B (editor map, firmware Ver.2)
    user_slots=200, slots_per_bank=4,               # U01-1 .. U50-4
    app_label="BOSS TONE STUDIO for GT",
    app_candidates=_GT100_APPS,
    map_cache="addressmap_gt100.json",
    types=_GT100_TYPES, type_params=_GT100_TYPE_PARAMS, aliases=_GT100_ALIASES,
    tested=False,
)

GT001 = Profile(
    key="gt001", name="GT-001",
    port=r"(?<![\w-])GT-001(?![0-9A-Za-z])",
    model=(0x00, 0x00, 0x00, 0x06),
    patch_size=GT100.patch_size,
    user_slots=200, slots_per_bank=4,
    app_label="BOSS TONE STUDIO for GT",
    app_candidates=_GT100_APPS,
    map_cache="addressmap_gt100.json",              # same editor, same map
    types=_GT100_TYPES, type_params=_GT100_TYPE_PARAMS, aliases=_GT100_ALIASES,
    tested=False,
)

PROFILES = (GT1, GT100, GT001)
DEFAULT = GT1


def for_port(port_name):
    for p in PROFILES:
        if p.matches(port_name):
            return p
    return None
