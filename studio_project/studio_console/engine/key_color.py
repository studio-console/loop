"""Studio Console key→colour engine — audio-reactive framework.

Part 2 of the audio-reactive framework: maps musical key (root note +
major/minor mode) to colour-palette presets, with a smooth crossfade
when the detected key shifts.

Design: minor keys default to cold palettes (blues/concert tones),
major keys to warm ones (whites/ambers). The palette is a list of
channel dicts using the same channel names as ColorPreset
(RELEVANT_CHANNELS in models/presets.py: red/green/blue/white/amber/
lime/uv, 0-255) so palettes recorded in the colour pool can be used
verbatim, or plain built-in fallbacks used when the pool has no entry.

Key detection is Krumhansl–Schmuckler tonal-centre correlation over a
decaying pitch-class histogram fed by AudioMIDIBridge note events —
pure math, no hardware, construct-safe headless (same convention as
every engine/driver module).

No threads are started at construction; update() must be called
regularly (from the GUI tick or an owner thread) to advance fades and
detection. Colour output lands in self.palette_now (list of channel
dicts, already crossfaded), ready for any consumer to push into
output_state.audio_layer or an FX/cue layer.
"""

import time


# ------------------------------------------------------------
# Pitch-class / key math (pure, module-level)
# ------------------------------------------------------------

NOTE_NAMES = ('C', 'C#', 'D', 'D#', 'E', 'F',
              'F#', 'G', 'G#', 'A', 'A#', 'B')

# Krumhansl–Kessler key profiles (tonic .. leading tone)
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def detect_key(histogram, min_confidence=0.35):
    """Best (root 0-11 = C..B, mode 'major'|'minor', confidence 0-1).

    histogram: 12-element pitch-class weights (index 0 = C). Confidence
    is the margin between the winning and runner-up correlation, so a
    ambiguous passage reports low instead of guessing confidently.
    """
    total = sum(histogram)
    if total <= 0.0:
        return None
    pc = [h / total for h in histogram]

    def corr(profile, rotation):
        # Pearson correlation between profile and rotated histogram.
        # rotation == the root note index: profile[(i - rotation) % n]
        # aligns the profile's tonic (index 0) with histogram slot
        # `rotation`, so a histogram peaked at A (9) correlates best
        # with rotation=9.
        n = 12
        mp = sum(profile) / n
        sp = sum((p - mp) ** 2 for p in profile) ** 0.5
        hp = sum(pc) / n
        shp = sum((h - hp) ** 2 for h in pc) ** 0.5
        if sp <= 0.0 or shp <= 0.0:
            return 0.0
        num = sum((profile[(i - rotation) % n] - mp) * (pc[i] - hp)
                  for i in range(n))
        return num / (sp * shp)

    best_major = max(((corr(MAJOR_PROFILE, r), r) for r in range(12)),
                     key=lambda t: t[0])
    best_minor = max(((corr(MINOR_PROFILE, r), r) for r in range(12)),
                     key=lambda t: t[0])
    if best_major[0] >= best_minor[0]:
        winner_score, root, mode = best_major[0], best_major[1], 'major'
        runner_score = best_minor[0]
    else:
        winner_score, root, mode = best_minor[0], best_minor[1], 'minor'
        runner_score = best_major[0]
    # confidence = margin over the best competing key (kills "confident
    # guesses" on ambiguous passages — reports None instead)
    margin = winner_score - runner_score
    conf = max(0.0, min(1.0, margin / 0.3))
    if winner_score <= 0.0 or conf < min_confidence:
        return None
    return root, mode, conf


# ------------------------------------------------------------
# Built-in fallback palettes
# ------------------------------------------------------------

def _cold_palette(root):
    """Minor-friendly cold palette: deep blues → concert cyan → steel.
    Root shifts the anchor hue slightly per key for variety."""
    r_shift = (root * 12) % 64
    return [
        {'red': 0,   'green': 30 + r_shift // 2, 'blue': 255},
        {'red': 0,   'green': 120, 'blue': 255},
        {'red': 40,  'green': 60,  'blue': 200},
        {'red': 160, 'green': 200, 'blue': 255, 'white': 60},
        {'red': 20,  'green': 0,   'blue': 180, 'uv': 120},
    ]


def _warm_palette(root):
    """Major-friendly warm palette: tungsten white → amber → gold."""
    a_shift = (root * 8) % 48
    return [
        {'red': 255, 'green': 230, 'blue': 190, 'white': 120},
        {'red': 255, 'green': 180 + a_shift, 'blue': 40},
        {'red': 255, 'green': 120, 'blue': 0},
        {'red': 255, 'green': 255, 'blue': 235, 'white': 200},
        {'red': 255, 'green': 200 + a_shift // 2, 'blue': 90},
    ]


def blend_channels(a, b, t):
    """Linear blend of two channel dicts over shared + union keys."""
    out = {}
    for k in set(a) | set(b):
        out[k] = a.get(k, 0) * (1.0 - t) + b.get(k, 0) * t
    return out


# ------------------------------------------------------------
# KeyColorMapper — detection state + crossfade
# ------------------------------------------------------------

class KeyColorMapper:
    """Tracks the musical key and crossfades to its palette.

    feed_note(note) — call for every AudioMIDIBridge note_on; weights
                      the decaying pitch-class histogram.
    update()        — call regularly (GUI tick / owner thread): expires
                      histogram weight, re-runs detection on a slow
                      interval, advances any in-progress crossfade.
    set_key()       — manual override (disables detection until
                      clear_override()); useful for pre-programmed
                      sections of a show.
    palette_now     — current (faded-in) list of channel dicts, in
                      ColorPreset channel format.

    Optional color_pool: if given, palettes named after the key (e.g.
    "Am minor") are looked up there first; built-in fallbacks are used
    when no matching preset exists. Entries are stored per-palette-name
    via register_palette() too, so GUI/commands can supply custom sets
    without touching the pool.
    """

    DETECT_INTERVAL = 2.0    # seconds between detection runs
    FADE_TIME       = 3.0    # seconds for a full crossfade
    HIST_DECAY      = 0.5    # histogram weight decay per new note

    def __init__(self, color_pool=None):
        self.color_pool    = color_pool
        self.enabled       = False
        self.key_root      = None    # 0-11 = C..B
        self.key_mode      = None    # 'major' | 'minor'
        self.key_conf      = 0.0
        self.palette_now   = _cold_palette(0)   # safe default look
        self.fade_time     = self.FADE_TIME

        self._hist         = [0.0] * 12
        self._hist_notes   = 0
        self._last_detect  = 0.0
        self._override     = False
        self._from_pal     = None
        self._to_pal       = None
        self._fade_start   = 0.0
        self._custom_pals  = {}    # name -> [channel dict, ...]

    # ----------------------------------------------------------
    # Input
    # ----------------------------------------------------------

    def feed_note(self, note, velocity=100):
        """Weight the pitch-class histogram with one incoming note."""
        weight = max(0.1, min(1.0, velocity / 127.0))
        pc = note % 12
        # exponential decay of old weight so recent playing dominates,
        # then add the new note at full (velocity-scaled) weight
        self._hist = [h * self.HIST_DECAY for h in self._hist]
        self._hist[pc] += weight
        self._hist_notes += 1

    def register_palette(self, name, channels_list):
        """Install a custom palette (list of channel dicts) under name."""
        self._custom_pals[name] = list(channels_list)

    # ----------------------------------------------------------
    # Key changes
    # ----------------------------------------------------------

    def set_key(self, root, mode):
        """Manually set the key; pins it (no detection) until cleared."""
        if isinstance(root, str):
            root = NOTE_NAMES.index(root.upper())
        if root == self.key_root and mode == self.key_mode:
            return
        self._begin_fade(root, mode)
        self._override = True

    def clear_override(self):
        """Re-enable automatic detection from the next update()."""
        self._override = False

    def _begin_fade(self, root, mode):
        self.key_root = root
        self.key_mode = mode
        self._from_pal = self.palette_now
        self._to_pal   = self._resolve_palette(root, mode)
        self._fade_start = time.monotonic()

    def _resolve_palette(self, root, mode):
        name = f"{NOTE_NAMES[root]} {mode}"
        if name in self._custom_pals:
            return self._custom_pals[name]
        if self.color_pool is not None:
            for preset in getattr(self.color_pool, 'presets', {}).values():
                if getattr(preset, 'name', '') == name and preset.channels:
                    return [dict(preset.channels)]
        return _warm_palette(root) if mode == 'major' else _cold_palette(root)

    # ----------------------------------------------------------
    # Tick
    # ----------------------------------------------------------

    def update(self):
        """Advance detection + fade. Call regularly while enabled."""
        now = time.monotonic()
        if not self.enabled:
            return self.palette_now
        if (not self._override and self._hist_notes > 4 and
                now - self._last_detect >= self.DETECT_INTERVAL):
            self._last_detect = now
            hit = detect_key(self._hist)
            if hit and (hit[0] != self.key_root or hit[1] != self.key_mode):
                self._begin_fade(hit[0], hit[1])
                self.key_conf = hit[2]
        if self._to_pal is not None:
            t = (now - self._fade_start) / max(0.01, self.fade_time)
            if t >= 1.0:
                self.palette_now = self._to_pal
                self._from_pal = self._to_pal = None
            else:
                self.palette_now = [
                    blend_channels(f, b, t)
                    for f, b in zip(self._from_pal, self._to_pal)
                ]
        return self.palette_now

    # ----------------------------------------------------------
    # Output
    # ----------------------------------------------------------

    def describe(self):
        """Human-readable current state for status displays / commands."""
        if self.key_root is None:
            return "key: (none detected)"
        return (f"key: {NOTE_NAMES[self.key_root]} {self.key_mode}"
                f"  conf {self.key_conf:.0%}"
                f"  {'[override]' if self._override else '[auto]'}")


__all__ = ["NOTE_NAMES", "MAJOR_PROFILE", "MINOR_PROFILE", "detect_key",
           "blend_channels", "KeyColorMapper"]
