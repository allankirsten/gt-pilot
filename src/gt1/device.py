"""MIDI connection to a BOSS GT pedal (Roland SysEx RQ1/DT1). What differs per pedal is in profiles.py."""
import subprocess
import sys
import time

import mido

from .params import EDIT_BUFFER, to_addr, to_int
from .profiles import DEFAULT, PROFILES, for_port

ROLAND = 0x41
DEVICE_ID = 0x00
RQ1, DT1 = 0x11, 0x12
CURRENT_PATCH = [0x00, 0x01, 0x00, 0x00]
EDITOR_MODE = [0x7F, 0x00, 0x00, 0x01]  # without it the pedal ignores setup/system requests


class NotConnected(RuntimeError):
    pass


def checksum(body):
    return (128 - sum(body) % 128) % 128


IS_WINDOWS = sys.platform == "win32"


def tone_studio_running():
    try:
        if IS_WINDOWS:
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return "boss tone studio" in out.stdout.lower()
        out = subprocess.run(["pgrep", "-f", "BOSS TONE STUDIO"], capture_output=True, text=True)
        return bool(out.stdout.strip())
    except OSError:
        return False


def midi_ports():
    """MIDI port names as this computer sees them, for diagnostics."""
    try:
        return sorted(set(mido.get_output_names()) | set(mido.get_input_names()))
    except Exception:  # noqa: BLE001
        return []


def find_pedal(outputs):
    """First MIDI output that belongs to a supported pedal, matched exactly: "GT-1" never picks a GT-100."""
    for name in outputs:
        profile = for_port(name)
        if profile:
            return name, profile
    return None, None


class GT1:
    """One connected GT pedal. The class keeps its old name; `profile` says which pedal it is."""

    def __init__(self):
        self.inp = self.out = None
        self.profile = DEFAULT

    @property
    def model(self):
        return list(self.profile.model)

    # connection -------------------------------------------------------------
    def connect(self):
        if self.inp:
            return
        out_name, profile = find_pedal(mido.get_output_names())
        if not out_name:
            supported = ", ".join(p.name for p in PROFILES)
            ports = midi_ports()
            raise NotConnected(
                f"No BOSS GT pedal found ({supported}). Check that it is powered on, the USB cable is connected, "
                "and its USB driver is installed. MIDI ports this computer sees: "
                f"{', '.join(ports) if ports else 'none'}.")
        last = None
        for _ in range(3):  # CoreMIDI sometimes fails the first open (-304)
            try:
                self.out = mido.open_output(out_name)
                self.inp = mido.open_input([n for n in mido.get_input_names() if profile.matches(n)][0])
                self.profile = profile
                self._editor_mode()
                return
            except Exception as e:  # noqa: BLE001
                last = e
                self.close()
                time.sleep(0.5)
        if IS_WINDOWS:
            raise NotConnected(
                f"Could not open the {profile.name} MIDI port ({last}). On Windows only one program can use it at a "
                "time: close BOSS TONE STUDIO and any other music software, then try again. If it still fails, "
                "unplug and replug the USB cable.")
        raise NotConnected(f"Could not open the {profile.name} MIDI port ({last}). Unplug and replug the USB cable.")

    def close(self):
        for p in (self.inp, self.out):
            if p:
                p.close()
        self.inp = self.out = None

    def _editor_mode(self):
        """Same handshake BOSS TONE STUDIO does. Must be repeated if the pedal was power-cycled."""
        self.write(EDITOR_MODE, [1])
        time.sleep(0.2)

    # raw I/O ----------------------------------------------------------------
    def _drain(self):
        for _ in self.inp.iter_pending():
            pass

    def read(self, addr, size, timeout=2.0):
        """RQ1. Returns a list of `size` bytes (None where the pedal did not answer).
        If nothing comes back, re-sends the editor handshake once and retries."""
        result = self._read_once(addr, size, timeout)
        if all(b is None for b in result):
            self._editor_mode()
            result = self._read_once(addr, size, timeout)
        return result

    def _read_once(self, addr, size, timeout):
        self.connect()
        self._drain()
        body = list(addr) + to_addr(size)
        self.out.send(mido.Message("sysex", data=[ROLAND, DEVICE_ID] + self.model + [RQ1] + body + [checksum(body)]))
        start, got = to_int(addr), {}
        head = [ROLAND, DEVICE_ID] + self.model + [DT1]
        h = len(head)  # the model ID is 4 bytes on the GT-1 and GT-001, 3 on the GT-100
        deadline, quiet = time.time() + timeout, None
        while time.time() < deadline:
            msgs = list(self.inp.iter_pending())
            for m in msgs:
                d = list(m.data) if m.type == "sysex" else []
                if d[:h] == head:
                    base = to_int(d[h:h + 4])
                    for k, b in enumerate(d[h + 4:-1]):
                        if start <= base + k < start + size:
                            got[base + k - start] = b
            if len(got) >= size:
                break
            if msgs:
                quiet = time.time()
            elif quiet and time.time() - quiet > 0.25:
                break
            time.sleep(0.005)
        return [got.get(i) for i in range(size)]

    def write(self, addr, data):
        """DT1, split so no message crosses a 128-byte address boundary."""
        self.connect()
        pos = to_int(addr)
        i = 0
        while i < len(data):
            room = 128 - (pos & 0x7F)
            chunk = data[i:i + min(room, 128)]
            body = to_addr(pos) + chunk
            self.out.send(mido.Message("sysex", data=[ROLAND, DEVICE_ID] + self.model + [DT1] + body + [checksum(body)]))
            time.sleep(0.03 if len(chunk) > 8 else 0.015)
            pos += len(chunk)
            i += len(chunk)

    # patches ----------------------------------------------------------------
    def slot_addr(self, slot):
        """slot is 1..profile.user_slots."""
        return self.profile.slot_addr(slot)

    def read_patch(self, slot=None):
        self.connect()
        addr = EDIT_BUFFER if slot is None else self.slot_addr(slot)
        raw = self.read(addr, self.profile.patch_size, timeout=4.0)
        if None in raw:
            raise NotConnected(f"The {self.profile.name} did not answer completely. Check the USB cable and try again.")
        return raw

    def write_patch(self, slot, raw):
        self.write(self.slot_addr(slot), raw)

    def write_buffer(self, raw):
        self.write(EDIT_BUFFER, raw)

    def patch_name(self, slot=None):
        addr = EDIT_BUFFER if slot is None else self.slot_addr(slot)
        raw = self.read(addr, 16)
        return bytes(b if b is not None else 63 for b in raw).decode("ascii", "replace").rstrip()

    def current_slot(self):
        raw = self.read(CURRENT_PATCH, 2)
        if None in raw:
            raise NotConnected(f"The {self.profile.name} did not answer. Check the USB cable.")
        return (raw[0] << 7 | raw[1]) + 1

    def load_slot(self, slot, timeout=3.0):
        """Switch patches and wait until the pedal itself reports the new slot. Returns False if it never
        did (a menu or the tuner open on the pedal can keep it from switching); one retry before giving up."""
        n = slot - 1
        for _ in range(2):
            self.write(CURRENT_PATCH, [n >> 7, n & 0x7F])
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(0.3)
                try:
                    if self.current_slot() == slot:
                        time.sleep(0.5)  # let the edit buffer settle before anyone reads it
                        return True
                except NotConnected:
                    pass
        return False
