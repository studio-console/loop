"""Studio Console audio driver — extracted verbatim from studio_project.py
(the "Block 9: audio Engine" section: AudioEngine + AudioMapper). Pure move,
zero behavior change.

_AUDIO_AVAILABLE / _AUDIO_IMPORT_ERROR are read as bare globals elsewhere in
studio_project.py (GUIEngine, run_command) via `from studio_console.drivers.audio
import *`, AND are deliberately monkeypatched by the STUDIO_HEADLESS smoke test
to exercise the "no audio hardware" code path — that monkeypatch must go through
this module's own namespace (`studio_console.drivers.audio._AUDIO_AVAILABLE`),
not a locally re-imported copy, or AudioEngine's own methods won't observe it.
See the studio_project.py edit instructions, step 8.
"""

import threading
import time

# sounddevice binds to the native Portaudio library at import time (not
# lazily like mido/rtmidi), so a missing/broken Portaudio install raises
# OSError here rather than on first use. AudioEngine/AudioMapper are not
# wired into any command handler or GUI panel yet (see changelog), but the
# import used to be unconditional, so any environment without a working
# audio stack (most CI/headless/dry-run boxes) failed to start the entire
# console before a single fixture patched. Guard it the same way Block 10
# hardened MIDI startup against a missing backend/device.
try:
    import sounddevice as sd
    import numpy as np
    _AUDIO_AVAILABLE = True
    _AUDIO_IMPORT_ERROR = None
except Exception as e:
    sd = None
    np = None
    _AUDIO_AVAILABLE = False
    _AUDIO_IMPORT_ERROR = e


# ------------------------------------------------------------
# AudioEngine — capture + analyse
# ------------------------------------------------------------

class AudioEngine:
    """
    Captures audio input in real-time and outputs four
    normalized values (0.0 - 1.0):

      level — overall RMS loudness
      low   — bass energy     (20-250 Hz)
      mid   — mid energy      (250-4000 Hz)
      high  — treble energy   (4000-20000 Hz)

    Attack/release envelope smooths transitions:
      attack  — how fast values RISE  (higher = faster snap)
      release — how fast values FALL  (lower = slower decay)
    """

    SAMPLE_RATE = 44100
    CHUNK_SIZE  = 1024

    def __init__(self):
        self.level   = 0.0
        self.low     = 0.0
        self.mid     = 0.0
        self.high    = 0.0

        self.attack  = 0.8    # fast snap to transients
        self.release = 0.15   # slow decay so lights linger
        self.gain    = 3.0    # turn up if signal is quiet

        self._stream  = None
        self._running = False

    @staticmethod
    def list_devices():
        if not _AUDIO_AVAILABLE:
            print(f"audio engine unavailable ({_AUDIO_IMPORT_ERROR}); no input devices to list.")
            return
        print("\n===== AUDIO INPUT DEVICES =====")
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] > 0:
                print(f"  [{i}] {dev['name']}")
        print("================================\n")

    def start(self, device=None):
        """
        Start capturing. device=None uses the system default.
        Pass a device index from list_devices() to pick a specific input.
        """
        if not _AUDIO_AVAILABLE:
            raise RuntimeError(f"audio engine unavailable: {_AUDIO_IMPORT_ERROR}")
        self._running = True
        self._stream  = sd.InputStream(
            samplerate = self.SAMPLE_RATE,
            channels   = 1,
            dtype      = 'float32',
            blocksize  = self.CHUNK_SIZE,
            callback   = self._callback,
            device     = device,
        )
        self._stream.start()
        idx  = device if device is not None else sd.default.device[0]
        name = sd.query_devices(idx)['name']
        print(f"audio engine started — input: {name}")

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        print("audio engine stopped.")

    def _callback(self, indata, frames, time_info, status):
        samples = indata[:, 0]

        # Overall RMS level
        rms = min(1.0, float(np.sqrt(np.mean(samples ** 2))) * self.gain)

        # FFT frequency analysis
        window = np.hanning(len(samples))
        fft    = np.abs(np.fft.rfft(samples * window))
        freqs  = np.fft.rfftfreq(len(samples), 1.0 / self.SAMPLE_RATE)

        def band(f_low, f_high):
            mask = (freqs >= f_low) & (freqs < f_high)
            return float(np.mean(fft[mask])) if mask.any() else 0.0

        low_raw  = band(20,   250)
        mid_raw  = band(250,  4000)
        high_raw = band(4000, 20000)

        # Normalize bands relative to each other, scaled by overall level
        peak   = max(low_raw, mid_raw, high_raw, 0.0001)
        low_n  = min(1.0, (low_raw  / peak) * rms * 1.5)
        mid_n  = min(1.0, (mid_raw  / peak) * rms * 1.5)
        high_n = min(1.0, (high_raw / peak) * rms * 1.5)

        self.level = self._env(self.level, rms)
        self.low   = self._env(self.low,   low_n)
        self.mid   = self._env(self.mid,   mid_n)
        self.high  = self._env(self.high,  high_n)

    def _env(self, current, target):
        coef = self.attack if target > current else self.release
        return current + (target - current) * coef

    def print_levels(self):
        def bar(v, w=24):
            return '█' * int(v * w) + '░' * (w - int(v * w))
        print(f"\r  Lvl [{bar(self.level)}] Lo [{bar(self.low)}] "
              f"Mid [{bar(self.mid)}] Hi [{bar(self.high)}]", end='', flush=True)


# ------------------------------------------------------------
# AudioMapper — connects audio values to the lighting stack
# ------------------------------------------------------------

class AudioMapper:
    """
    Reads AudioEngine values every frame and writes to
    output_state.audio_layer.

    Default mapping:
      level → master dimmer on all fixtures
      low   → red   on all sub-fixtures  (bass = red)
      mid   → green on all sub-fixtures  (mids = green)
      high  → blue  on all sub-fixtures  (treble = blue)

    audio layer sits between FX+cue and programmer —
    programmer still overrides everything when active.
    """

    def __init__(self, audio_engine, output_state, patch):
        self.audio        = audio_engine
        self.output_state = output_state
        self.patch        = patch
        self.enabled      = False
        self._running     = True
        self._thread      = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enable(self):
        self.enabled = True
        print("audio mapping enabled — bass=red, mid=green, high=blue, level=dim")

    def disable(self):
        self.enabled = False
        self.output_state.audio_layer = {}
        print("audio mapping disabled.")

    def _run(self):
        while self._running:
            if self.enabled:
                out = {}
                r   = int(self.audio.low   * 255)
                g   = int(self.audio.mid   * 255)
                b   = int(self.audio.high  * 255)
                dim = self.audio.level

                for master in self.patch.all_fixtures():
                    out[str(master.fixture_id)] = {'dim': dim}
                    for sub in master.all_subs():
                        out[str(sub.fixture_id)] = {
                            'red': r, 'green': g, 'blue': b
                        }
                self.output_state.audio_layer = out
            time.sleep(1 / 44)

    def stop(self):
        self._running = False


__all__ = ["sd", "np", "_AUDIO_AVAILABLE", "_AUDIO_IMPORT_ERROR",
           "AudioEngine", "AudioMapper"]