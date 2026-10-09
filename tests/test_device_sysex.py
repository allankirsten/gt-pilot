"""SysEx framing per pedal, with a fake MIDI port (no pedal needed)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gt1.device import GT1 as Pedal, checksum  # noqa: E402
from gt1.profiles import GT1, GT100  # noqa: E402


class FakeOut:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(list(msg.data))


class FakeIn:
    """Answers an RQ1 with a DT1 carrying `payload`, framed with the given model ID."""
    def __init__(self, out, model, payload):
        self.out, self.model, self.payload, self.done = out, list(model), payload, False

    def iter_pending(self):
        import mido
        if self.done or not self.out.sent:
            return iter(())
        self.done = True
        rq = self.out.sent[-1]
        addr = rq[2 + len(self.model) + 1:2 + len(self.model) + 5]
        body = addr + self.payload
        return iter([mido.Message("sysex", data=[0x41, 0x00] + self.model + [0x12] + body + [checksum(body)])])


def pedal(profile, payload):
    p = Pedal()
    p.profile = profile
    p.out = FakeOut()
    p.inp = FakeIn(p.out, profile.model, payload)
    return p


# GT-1: 4-byte model ID, as in 0.1-0.3
p = pedal(GT1, [0x41, 0x42])
assert p.read([0x60, 0, 0, 0], 2, timeout=0.5) == [0x41, 0x42]
assert p.out.sent[0][:7] == [0x41, 0x00, 0x00, 0x00, 0x00, 0x30, 0x11]

# GT-100: 3-byte model ID; the reply is parsed at the right offset
p = pedal(GT100, [0x47, 0x54, 0x31])
assert p.read([0x60, 0, 0, 0], 3, timeout=0.5) == [0x47, 0x54, 0x31]
assert p.out.sent[0][:6] == [0x41, 0x00, 0x00, 0x00, 0x60, 0x11]
assert p.out.sent[0][6:10] == [0x60, 0, 0, 0]

# a GT-1-framed reply is ignored by a GT-100 session (and vice versa)
p = pedal(GT100, [1, 2])
p.inp.model = list(GT1.model)
assert p.read([0x60, 0, 0, 0], 2, timeout=0.3) == [None, None]

# writes carry the pedal's model ID
p = pedal(GT100, [])
p.write([0x60, 0, 0, 0x31], [0x0A])
assert p.out.sent[0][:6] == [0x41, 0x00, 0x00, 0x00, 0x60, 0x12]
print("device sysex: all checks passed")
