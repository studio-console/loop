"""Studio Console sub-harmonic strobe engine — audio-reactive framework.

Part 3 of the audio-reactive framework: divides tracked pitch
frequencies down into integer sub-harmonics and translates low bass
hits into precise stroboscopic rates, ready to feed:

  sACN  — via the standard output_state layer merge (the engine
          publishes a strobe_gate/strobe_rate dict in the same format
          as audio_layer, consumed by whoever merges it — a future
          tick-hook or the audio_mapper pattern)
  OSC   — direct sends to a named target (e.g. a Resolume machine):
          /resolume/strobe/rate   float  Hz
          /resolume/strobe/gate   int    0/1 (current gate phase)
          /resolume/strobe/fire   (sent once per detected bass onset)

The core math (module-level, pure, testable headless):
  freq_to_subharmonics(freq)  — freq/1, freq/2, freq/4 ... down to a
                                floor, i.e. the octave ladder beneath
                                a tracked pitch
  subharmonic_for(freq, target_hz) — the division whose result lands
                                closest to a target strobe rate
  bass_onset(level, prev, threshold) — simple transient detector on
                                the audio_engine's low-band envelope

Rate safety: strobe_hz_to_duty() converts Hz → gate duty for a caller
driving its own phase accumulator, and rates are clamped to
STROBE_MIN_HZ/STROBE_MAX_HZ so a wild frequency estimate can never
produce DC (0 Hz = stuck on) or ultrasonic flicker (hazardous for
photosensitive viewers — the clamp is deliberate and safety-relevant,
not cosmetic).
"""

import time


# ------------------------------------------------------------
# Safety clamps — deliberately conservative
# ------------------------------------------------------------

STROBE_MIN_HZ = 0.5    # below this reads as "stuck on" for humans
STROBE_MAX_HZ = 25.0   # above ~25 Hz fuses to solid; also the
                       # photosensitivity-safety ceiling we refuse to exceed


def clamp_rate(hz):
    """Clamp a strobe rate into the safe, visually meaningful band."""
    return max(STROBE_MIN_HZ, min(STROBE_MAX_HZ, float(hz)))


# ------------------------------------------------------------
# Pure division math
# ------------------------------------------------------------

def freq_to_subharmonics(freq, max_div=8, floor_hz=STROBE_MIN_HZ):
    """Octave ladder of sub-harmonics beneath freq.

    Returns [freq/1, freq/2, ..., freq/max_div] truncated at floor_hz.
    Example: 80 Hz bass → [80, 40, 20, 10, 5, 2.5, 1.25, 0.625].
    """
    if freq <= 0.0:
        return []
    out = []
    for div in range(max_div + 1):
        hz = freq / (2 ** div)
        if hz < floor_hz:
            break
        out.append(hz)
    return out


def subharmonic_for(freq, target_hz, max_div=8):
    """Division of freq whose result is closest to target_hz.

    Returns (rate_hz, division) clamped to the safe band, or
    (None, None) when freq isn't usable.
    """
    if freq <= 0.0:
        return None, None
    candidates = freq_to_subharmonics(freq, max_div=max_div)
    if not candidates:
        return None, None
    best = min(candidates, key=lambda hz: abs(clamp_rate(hz) - target_hz))
    return clamp_rate(best), 2 ** candidates.index(best)


def strobe_hz_to_duty(hz, base_hz=100.0):
    """Gate duty fraction for a caller stepping at base_hz.

    phase accumulator: gate = 1 while frac(phase) < duty, else 0.
    duty = rate / base gives a consistent ~short pulse per cycle.
    """
    hz = clamp_rate(hz)
    return max(0.02, min(0.5, hz / base_hz))


def bass_onset(low_now, low_prev, threshold=0.25, rise=0.15):
    """True when the low-band envelope crosses upward past threshold.

    Simple, robust transient test: must be above absolute threshold
    AND risen by `rise` since the previous frame — rejects steady
    drone (high level, no rise) and noise floor (no threshold cross).
    """
    return low_now >= threshold and (low_now - low_prev) >= rise


# ------------------------------------------------------------
# SubHarmonicStrobe — tracking state + output feeds
# ------------------------------------------------------------

class SubHarmonicStrobe:
    """Bass-onset-triggered strobe generator at sub-harmonic rates.

    tick(low_level, freq) — call every frame (audio thread or GUI tick,
                            ~44 Hz matches AudioMapper's loop): detects
                            onsets, advances the gate phase, returns
                            the current gate (0.0/1.0).
    strobe_rate           — current rate in Hz (last onset's division
                            of the tracked pitch, clamped safe).
    fire_count            — increments on every detected bass onset
                            (handy for GUI flash indicators / tests).

    OSC feed: set osc + target_name (constructor or attributes) and
    each onset sends /resolume/<target>/strobe fire/rate/gate messages.
    The default target_name 'strobe' yields /resolume/strobe/... —
    rename to match your Resolume composition's OSC shortcuts.

    sACN feed: gate_dict property publishes {sub_fid: {'strobe': 0/255}}
    in the same shape as OutputState.audio_layer, ready to merge.
    """

    DEFAULT_TARGET_HZ = 8.0   # ~bass-drum visual feel per onset
    PHASE_BASE_HZ     = 100.0 # assumed caller tick rate for duty math

    def __init__(self, osc=None, target_name='strobe'):
        self.osc          = osc
        self.target_name  = target_name
        self.enabled      = False
        self.strobe_rate  = None    # current Hz (clamped)
        self.division     = None    # power-of-2 divider in effect
        self.gate         = 0.0     # current gate phase 0.0/1.0
        self.target_hz    = self.DEFAULT_TARGET_HZ
        self.onset_threshold = 0.25
        self.onset_rise      = 0.15
        self.fire_count      = 0

        self._phase       = 0.0
        self._prev_low    = 0.0
        self._last_gate   = 0

    # ----------------------------------------------------------
    # Frame tick
    # ----------------------------------------------------------

    def tick(self, low_level, freq):
        """Advance one frame. Returns the gate value (0.0/1.0)."""
        if not self.enabled:
            self.gate = 0.0
            self._prev_low = low_level
            return self.gate

        if bass_onset(low_level, self._prev_low,
                      self.onset_threshold, self.onset_rise):
            rate, div = subharmonic_for(freq or 0.0, self.target_hz)
            if rate is not None:
                self.strobe_rate = rate
                self.division    = div
                self._phase      = 0.0   # resync phase to the hit
                self.fire_count += 1
                self._send_osc_fire()
        self._prev_low = low_level

        if self.strobe_rate:
            duty = strobe_hz_to_duty(self.strobe_rate, self.PHASE_BASE_HZ)
            self._phase = (self._phase + self.strobe_rate / self.PHASE_BASE_HZ) % 1.0
            self.gate = 1.0 if self._phase < duty else 0.0
        else:
            self.gate = 0.0

        g = int(self.gate)
        if g != self._last_gate and self.strobe_rate:
            self._send_osc_gate(g)
            self._last_gate = g
        return self.gate

    # ----------------------------------------------------------
    # OSC feed (Resolume)
    # ----------------------------------------------------------

    def _addr(self, leaf):
        return f"/resolume/{self.target_name}/strobe/{leaf}"

    def _send_osc_fire(self):
        if self.osc is None or self.strobe_rate is None:
            return
        try:
            self.osc.send(self._addr('fire'), 1)
            self.osc.send(self._addr('rate'), float(self.strobe_rate))
        except Exception as e:
            print(f"  !! SubHarmonicStrobe OSC error: {e}")

    def _send_osc_gate(self, g):
        if self.osc is None:
            return
        try:
            self.osc.send(self._addr('gate'), g)
        except Exception as e:
            print(f"  !! SubHarmonicStrobe OSC error: {e}")

    # ----------------------------------------------------------
    # sACN feed — audio_layer-compatible dict
    # ----------------------------------------------------------

    def gate_dict(self, sub_fixture_ids):
        """{sub_fid: {'strobe': 0|255}} for the current gate phase.

        Pass the sub-fixture ids to drive (or leave it to the consumer
        to broadcast); strobe is written as a normal 0-255 channel so
        any profile with a strobe attribute (see models/fixtures.py
        AttributePool) picks it up in the standard layer merge.
        """
        v = 255 if self.gate >= 0.5 else 0
        return {str(fid): {'strobe': v} for fid in sub_fixture_ids}


__all__ = ["STROBE_MIN_HZ", "STROBE_MAX_HZ", "clamp_rate",
           "freq_to_subharmonics", "subharmonic_for", "strobe_hz_to_duty",
           "bass_onset", "SubHarmonicStrobe"]
