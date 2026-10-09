"""Hear the pedal over USB audio: record, measure, metronome."""
import math
import threading

import numpy as np
import sounddevice as sd

RATE = 44100


class NoAudio(RuntimeError):
    pass


# Set by the server to the connected pedal's profile; the audio device carries the same name as the MIDI port.
profile = None


def _device(kind):
    from .profiles import DEFAULT
    p = profile or DEFAULT
    for i, d in enumerate(sd.query_devices()):
        if p.matches(d["name"]) and d[f"max_{kind}_channels"] > 0:
            return i
    raise NoAudio(f"The {p.name} does not show up as an audio device. Check the USB cable and the {p.name} driver.")


def record(seconds):
    audio = sd.rec(int(seconds * RATE), samplerate=RATE, channels=2, device=_device("input"), dtype="float32")
    sd.wait()
    return audio


def _db(x):
    return 20 * math.log10(x) if x > 0 else -120.0


def frame_levels(mono, frame=0.1):
    n = int(RATE * frame)
    x = mono[: len(mono) // n * n].reshape(-1, n)
    return 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-12)


def analyze(audio):
    mono = audio.mean(axis=1)
    levels = frame_levels(mono)
    playing = float(np.percentile(levels, 90))
    gaps = levels[levels < playing - 20]
    spec = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
    f = np.fft.rfftfreq(len(mono), 1 / RATE)

    def band(lo, hi):
        return float(spec[(f >= lo) & (f < hi)].sum())

    total = band(40, 12000) or 1.0
    return {
        "playing_level_dbfs": round(playing, 1),
        "peak_dbfs": round(_db(float(np.abs(mono).max())), 1),
        "brightness_hz": round(float((spec * f).sum() / (spec.sum() or 1))),
        "bands_percent": {
            "lows 80-250 Hz": round(100 * band(80, 250) / total),
            "low-mids 250-800 Hz": round(100 * band(250, 800) / total),
            "mids 800-2500 Hz": round(100 * band(800, 2500) / total),
            "highs 2.5-6 kHz": round(100 * band(2500, 6000) / total),
            "fizz 6-12 kHz": round(100 * band(6000, 12000) / total),
        },
        "noise_in_pauses_dbfs": round(float(np.median(gaps)), 1) if len(gaps) >= 5 else None,
        "pauses_percent": round(100 * len(gaps) / len(levels)),
        "clipped": bool((np.abs(audio) > 0.988).any()),
        "is_silent": playing < -70,
        "digital_silence": not np.any(audio),
    }


class Metronome:
    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self.bpm = None

    def _click(self, freq, vol):
        n = int(RATE * 0.03)
        t = np.arange(n) / RATE
        return (vol * np.sin(2 * np.pi * freq * t) * (1 - t / t[-1])).astype("float32")

    def start(self, bpm, beats=4, volume=0.15):
        self.stop()
        beat = int(RATE * 60 / bpm)
        bar = np.zeros(beat * beats, dtype="float32")
        for b in range(beats):
            c = self._click(1500 if b == 0 else 1000, volume)
            bar[b * beat:b * beat + len(c)] = c
        stereo = np.column_stack([bar, bar])
        self._stop.clear()
        self.bpm = bpm

        def loop():
            with sd.OutputStream(samplerate=RATE, channels=2, device=_device("output"), dtype="float32") as s:
                while not self._stop.is_set():
                    s.write(stereo)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        if self._thread:
            self._stop.set()
            self._thread.join(timeout=3)
        self._thread = None
        self.bpm = None
