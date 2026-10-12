"""Studio Console audio→MIDI bridge — pitch tracking driver.

Part of the audio-reactive framework. Intercepts the live capture stream
from drivers/audio.py's AudioEngine and converts the primary tracked
pitch into clean, hysteresis-stabilised MIDI note values (note number +
velocity), exposed as attributes and fired through optional note_on /
note_off callbacks.

np / _AUDIO_AVAILABLE are read from the audio driver's own namespace at
call time (never copied into this module's globals at import) — the
STUDIO_HEADLESS smoke test monkeypatches
studio_console.drivers.audio._AUDIO_AVAILABLE to exercise the
"no audio hardware" path, and a snapshot import would silently miss that
(see drivers/audio.py's docstring for the same warning).

No hardware and no threads at construction — pitch detection is pure
math over a chunk, invoked from AudioEngine's on_chunk hook, so this
constructs safely in headless/CI environments like every other driver.
"""

import math
import time

import studio_console.drivers.audio as _audio_driver
import mido


# ------------------------------------------------------------
# Pure pitch math (module-level so it's testable headless,
# no AudioEngine instance needed)
# ------------------------------------------------------------

def detect_freq(samples, sample_rate, fmin=55.0, fmax=2000.0):
    """Estimate the fundamental frequency of one audio chunk.

    Normalised autocorrelation (FFT-based for speed) with parabolic
    peak interpolation — robust on monophonic sources (voice, guitar,
    bass) in the presence of harmonic content, which defeats a naive
    "biggest FFT bin" approach when the fundamental isn't the loudest
    partial (common on guitar low strings).

    Returns (freq_hz, confidence 0.0-1.0); (0.0, 0.0) on silence/noise.

    Resolution limit: the chunk must contain at least ~2 periods of the
    pitch — with AudioEngine's 1024-sample chunks (~23 ms) that floors
    reliable tracking at roughly 85 Hz. For low-bass tracking, capture
    with a larger CHUNK_SIZE (e.g. 4096 reaches ~27 Hz floor).
    """
    np = _audio_driver.np
    if np is None or samples is None or len(samples) < 64:
        return 0.0, 0.0
    x = np.asarray(samples, dtype=np.float64)
    # DC offset + very low rumble out; noise gate against hiss
    x = x - np.mean(x)
    rms = float(np.sqrt(np.mean(x * x)))
    if rms < 1e-4:
        return 0.0, 0.0
    n = len(x)
    # FFT autocorrelation: r = IFFT(|FFT(x)|^2), normalised by lag-0 energy
    nfft = 1 << (2 * n - 1).bit_length()
    fx = np.fft.rfft(x, nfft)
    r = np.fft.irfft(fx * np.conj(fx), nfft)[:n]
    if r[0] <= 0.0:
        return 0.0, 0.0
    r = r / r[0]
    # Unbiased estimator: at lag L only (n-L) samples overlap, so the
    # biased autocorrelation is artificially inflated at SHORT lags —
    # without this correction every low pitch aliases to the smallest
    # lag in the search window (classic pitch-tracker bug, caught by
    # the framework's headless math checks). Search can extend past
    # n/2 (an 82 Hz bass needs lag ~535 in a 1024-sample chunk); the
    # < 0.3 confidence threshold below rejects the noise amplification
    # the correction can cause at very long lags.
    lags = np.arange(n)
    with np.errstate(divide='ignore', invalid='ignore'):
        r = r * n / np.maximum(n - lags, 1)
    r[:2] = 0.0
    lag_lo = max(2, int(sample_rate / fmax))
    # +2 margin so a pitch exactly at fmin (peak at a fractional lag
    # straddling the boundary) still has its local max inside the window
    lag_hi = min(n - 2, int(sample_rate / fmin) + 2)
    if lag_hi <= lag_lo:
        return 0.0, 0.0
    window = r[lag_lo:lag_hi + 1]
    # Find all local maxima in the window; pick the SMALLEST-lag peak
    # that's close to the global max. For a periodic signal every
    # integer-multiple lag correlates ~1.0 equally, so a plain argmax
    # (especially with the unbiased correction, which multiplies by
    # n/(n-lag) and thus favours LONG lags) locks onto sub-harmonics
    # — 440 Hz reads as 55 Hz. First-peak-above-threshold is the
    # standard defence (same idea as YIN's absolute-threshold step).
    peaks = []
    # inclusive upper bound: the peak at exactly int(sr/fmin) must be
    # scannable (r[lag_hi] > r[lag_hi-1] is a valid local max)
    for i in range(lag_lo + 1, min(lag_hi + 1, n - 1)):
        if r[i] >= r[i - 1] and r[i] > r[i + 1]:
            peaks.append(i)
    if not peaks:
        return 0.0, 0.0
    gmax = max(float(r[i]) for i in peaks)
    if gmax < 0.3:  # too weak/decorrelated to call it a pitch
        return 0.0, 0.0
    peak_i = next((i for i in peaks if r[i] >= 0.85 * gmax), peaks[-1])
    peak_v = float(r[peak_i])
    # Parabolic interpolation around the peak for sub-lag precision
    if lag_lo < peak_i < n - 2:
        a, b, c = float(r[peak_i - 1]), float(r[peak_i]), float(r[peak_i + 1])
        denom = a - 2 * b + c
        delta = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
        delta = max(-0.5, min(0.5, delta))
    else:
        delta = 0.0
    freq = sample_rate / (peak_i + delta)
    # tolerance: an exact-fmin tone quantizes to the integer lag just
    # below fmin (44100/803 = 54.92 for fmin=55) — reject only clear
    # out-of-range values, not this rounding edge
    if not (fmin * 0.97 <= freq <= fmax * 1.03):
        return 0.0, 0.0
    return freq, max(0.0, min(1.0, peak_v))


def freq_to_midi(freq):
    """Continuous MIDI note number (float, 69 = A4 = 440 Hz) for a frequency."""
    if freq <= 0.0:
        return None
    return 69.0 + 12.0 * math.log2(freq / 440.0)


def quantize(midi_note):
    """Snap a continuous MIDI note to the nearest integer semitone."""
    if midi_note is None:
        return None
    return max(0, min(127, int(round(midi_note))))

    return max(0, min(127, int(round(midi_note))))


# ------------------------------------------------------------
# AudioMIDIBridge — tracker state + note-event emission
# ------------------------------------------------------------

class AudioMIDIBridge:
    """Turns AudioEngine's captured chunks into a clean MIDI note stream.

    Attach with attach(audio_engine) — registers a chunk hook on the
    engine; the engine's capture thread calls feed_chunk(), which runs
    pitch detection and emits note events. Nothing runs until attach()
    is called and the AudioEngine has a live stream (AUDIO START).

    "Clean" means two layers of jitter rejection, both tunable:
      stability_frames — a new note must be detected this many chunks
                         in a row before it replaces the current one
                         (kills single-frame pitch glitches)
      min_hold         — seconds the current note is honoured before
                         another replacement is allowed (stops machine-
                         gun chatter on fast passages)
    Velocity comes from the chunk RMS (loudness), floor-clamped so a
    quiet but steady note still reads as a real trigger.
    """

    def __init__(self, stability_frames=3, min_hold=0.08, vel_floor=0.25,
                 release_after=0.25):
        self.stability_frames = stability_frames
        self.min_hold         = min_hold
        self.vel_floor        = vel_floor
        self.release_after    = release_after   # seconds of pitch-free
                                                # audio before note_off

        self.freq       = 0.0    # last confident tracked pitch (Hz)
        self.confidence = 0.0
        self.midi_cont  = None   # continuous (unquantised) note number
        self.note       = None   # current emitted note (int) or None
        self.velocity   = 0      # velocity of last note_on (1-127)

        self.note_on_callback  = None   # (note, velocity)
        self.note_off_callback = None   # (note,)

        self.midi_out = None     # optional mido output port; set externally

        self._candidate      = None
        self._candidate_hits = 0
        self._last_change    = 0.0
        self._attached_to    = None

    # ----------------------------------------------------------
    # Attach / detach
    # ----------------------------------------------------------

    def attach(self, audio_engine):
        """Register feed_chunk() on the engine's capture hook."""
        audio_engine.on_chunk = self.feed_chunk
        self._attached_to = audio_engine

    def detach(self):
        if self._attached_to is not None:
            self._attached_to.on_chunk = None
            self._attached_to = None

    # ----------------------------------------------------------
    # Chunk feed — called on the audio capture thread
    # ----------------------------------------------------------

    def feed_chunk(self, samples):
        """Process one captured chunk. Returns the emitted note or None."""
        np = _audio_driver.np
        if np is None:
            return None
        freq, conf = detect_freq(samples, _audio_driver.AudioEngine.SAMPLE_RATE)
        self.confidence = conf
        if freq <= 0.0 or conf < 0.35:
            # below the pitch floor: let the current note go after a
            # short gap so breath noise between notes doesn't clip them
            if self.note is not None and time.monotonic() - self._last_change > self.release_after:
                self._emit_off()
            return None
        self.freq      = freq
        self.midi_cont = freq_to_midi(freq)
        snapped        = quantize(self.midi_cont)
        now            = time.monotonic()

        if snapped == self.note:
            self._candidate      = None
            self._candidate_hits = 0
            return self.note

        # track the new candidate; commit only once stable + hold elapsed
        if snapped == self._candidate:
            self._candidate_hits += 1
        else:
            self._candidate      = snapped
            self._candidate_hits = 1
        if (self._candidate_hits >= self.stability_frames and
                now - self._last_change >= self.min_hold):
            self._emit_off()
            self._emit_on(snapped, samples, np)
            return snapped
        return None

    def _emit_on(self, note, samples, np):
        rms = float(np.sqrt(np.mean(np.asarray(samples, dtype=np.float64) ** 2)))
        vel = int(max(self.vel_floor, min(1.0, rms * 4.0)) * 127)
        vel = max(1, min(127, vel))
        self.note       = note
        self.velocity   = vel
        self._last_change = time.monotonic()
        if self.note_on_callback:
            try:
                self.note_on_callback(note, vel)
            except Exception as e:
                print(f"  !! AudioMIDIBridge note_on callback error: {e}")
        if self.midi_out is not None:
            try:
                self.midi_out.send(mido.Message('note_on', note=note,
                                                velocity=vel, channel=0))
            except Exception as e:
                print(f"  !! AudioMIDIBridge MIDI out error: {e}")

    def _emit_off(self):
        if self.note is None:
            return
        off, self.note = self.note, None
        if self.note_off_callback:
            try:
                self.note_off_callback(off)
            except Exception as e:
                print(f"  !! AudioMIDIBridge note_off callback error: {e}")
        if self.midi_out is not None:
            try:
                self.midi_out.send(mido.Message('note_off', note=off,
                                                velocity=0, channel=0))
            except Exception as e:
                print(f"  !! AudioMIDIBridge MIDI out error: {e}")


__all__ = ["detect_freq", "freq_to_midi", "quantize", "AudioMIDIBridge"]
