"""Studio Console FX engine — extracted verbatim from studio_project.py
(Block 8: FX Engine). Pure move, zero behavior change. Fully self-contained:
no references to models/, drivers/, show.py, gui/theme.py, or anything in
studio_project.py itself — verified before extraction, not just assumed.
"""

import math
import random
import threading
import time


# ------------------------------------------------------------
# Waveform functions
# Input:  t = phase 0.0 → 1.0
# Output: value 0.0 → 1.0
# ------------------------------------------------------------

class Waveform:
    @staticmethod
    def sine(t):
        return (math.sin(2 * math.pi * t - math.pi / 2) + 1) / 2

    @staticmethod
    def ramp(t):
        return t % 1.0

    @staticmethod
    def square(t):
        return 1.0 if (t % 1.0) < 0.5 else 0.0

    @staticmethod
    def pulse(t):
        return 1.0 if (t % 1.0) < 0.25 else 0.0

    @staticmethod
    def triangle(t):
        t = t % 1.0
        return 1.0 - abs(2 * t - 1.0)

    @staticmethod
    def sawtooth(t):
        return 1.0 - (t % 1.0)

    @staticmethod
    def flicker(t, idx=0):
        # Deterministic per-pixel noise: idx XOR into hash gives each pixel an
        # independent random sequence. 97 steps/cycle = visible change at 44 Hz.
        n = (int(t * 97) ^ (idx * 0x4B1D) ^ 0xA5B3) & 0xFFFF
        n = ((n ^ (n << 13)) ^ (n >> 7) ^ (n << 17)) & 0xFF
        return n / 255.0

    @staticmethod
    def get(name):
        return {
            'sine':     Waveform.sine,
            'ramp':     Waveform.ramp,
            'pulse':    Waveform.pulse,
            'square':   Waveform.square,
            'triangle': Waveform.triangle,
            'sawtooth': Waveform.sawtooth,
            'flicker':  Waveform.flicker,
        }.get(name.lower(), Waveform.sine)


# ============================================================
# Formpreset + FormPool
# A Formpreset is a waveform shape: either a reference to one
# of the built-in Waveform functions, or a user-defined
# breakpoint curve (list of [phase, value] pairs, 0.0-1.0).
#
# FormPool pre-seeds slots 1-4 with the built-in shapes.
# Custom forms (slot 5+) are persisted to studio_data/forms.json.
# The FX engine resolves form functions at runtime from this pool.
# ============================================================

class FormPreset:
    """One named waveform shape — built-in or breakpoint curve."""

    def __init__(self, form_id, name, form_type='builtin',
                 builtin_name=None, breakpoints=None):
        self.form_id      = int(form_id)
        self.name         = name
        self.form_type    = form_type       # 'builtin' | 'breakpoints'
        self.builtin_name = builtin_name    # e.g. 'sine'
        self.breakpoints  = breakpoints or []  # [[phase, value], ...]

    def get_fn(self):
        """Return a callable: phase (0.0–1.0) → value (0.0–1.0)."""
        if self.form_type == 'builtin':
            return Waveform.get(self.builtin_name or 'sine')

        # Breakpoint interpolation — captured in closure at call time
        preset = self

        def _interp(phase):
            pts = sorted(preset.breakpoints, key=lambda p: p[0])
            if not pts:
                return 0.0
            p = float(phase) % 1.0
            if p <= pts[0][0]:
                return float(pts[0][1])
            if p >= pts[-1][0]:
                return float(pts[-1][1])
            for i in range(len(pts) - 1):
                p0, v0 = pts[i][0], pts[i][1]
                p1, v1 = pts[i + 1][0], pts[i + 1][1]
                if p0 <= p <= p1:
                    t = (p - p0) / (p1 - p0) if p1 != p0 else 0.0
                    return float(v0 + (v1 - v0) * t)
            return 0.0

        return _interp

    def __repr__(self):
        if self.form_type == 'builtin':
            return f"[form {self.form_id}] {self.name}  (builtin: {self.builtin_name})"
        return (f"[form {self.form_id}] {self.name}  "
                f"(custom breakpoints: {len(self.breakpoints)} pts)")


class FormPool:
    """Numbered library of Formpreset waveform shapes (1-based).
    slots 1-4 are always the built-ins; 5+ are user-defined."""

    _BUILTINS = [
        (1, 'Sine',   'sine'),
        (2, 'Ramp',   'ramp'),
        (3, 'Pulse',  'pulse'),
        (4, 'Square', 'square'),
    ]
    FIRST_CUSTOM_SLOT = 5

    def __init__(self):
        self.forms = {}
        for fid, name, bname in self._BUILTINS:
            self.forms[fid] = FormPreset(fid, name, 'builtin', bname)

    def get(self, n):
        return self.forms.get(int(n))

    def get_by_name(self, name):
        """Case-insensitive lookup by name or builtin_name."""
        nu = name.upper()
        for f in self.forms.values():
            if f.name.upper() == nu:
                return f
            if f.builtin_name and f.builtin_name.upper() == nu:
                return f
        return None

    def get_fn(self, ref):
        """
        Resolve a waveform function from a form ID (int) or name (str).
        Falls back to Waveform.get() if not found.
        """
        if isinstance(ref, int):
            form = self.get(ref)
        else:
            form = self.get_by_name(str(ref))
        return form.get_fn() if form else Waveform.get(str(ref))

    def store(self, n, form):
        self.forms[int(n)] = form

    def delete(self, n):
        n = int(n)
        if n < self.FIRST_CUSTOM_SLOT:
            return  # built-ins are read-only
        self.forms.pop(n, None)

    def custom_forms(self):
        """Only the user-defined (non-builtin) forms."""
        return {fid: f for fid, f in self.forms.items()
                if f.form_type != 'builtin'}

    def all_slots(self):
        return sorted(self.forms.keys())


# ============================================================
# RatePool / SizePool / SpreadPool
# Separate numbered pools for each FX property so that
# updating one entry propagates live to all referencing layers.
# ============================================================

class RatePreset:
    """BPM / timing preset."""
    _BUILTINS = [(1,'Slow',30.0),(2,'Medium',60.0),(3,'Fast',120.0),(4,'Very Fast',240.0)]
    def __init__(self, preset_id, name, bpm=60.0):
        self.preset_id = int(preset_id)
        self.name      = name
        self.bpm       = float(bpm)
    def __repr__(self):
        return f"[rate {self.preset_id}] {self.name}  ({self.bpm:.1f} BPM)"

class RatePool:
    def __init__(self):
        self.presets = {}
        for pid, name, bpm in RatePreset._BUILTINS:
            self.presets[pid] = RatePreset(pid, name, bpm)
    def get(self, n):       return self.presets.get(int(n))
    def store(self, n, p):  self.presets[int(n)] = p
    def delete(self, n):    self.presets.pop(int(n), None)
    def all_slots(self):    return sorted(self.presets.keys())

class SizePreset:
    """Amplitude preset (0–100, where 100 = full DMX 255)."""
    _BUILTINS = [(1,'Subtle',25.0),(2,'Medium',50.0),(3,'Full',100.0)]
    def __init__(self, preset_id, name, size=100.0):
        self.preset_id = int(preset_id)
        self.name      = name
        self.size      = float(size)
    def __repr__(self):
        return f"[size {self.preset_id}] {self.name}  (size={self.size:.0f})"

class SizePool:
    def __init__(self):
        self.presets = {}
        for pid, name, size in SizePreset._BUILTINS:
            self.presets[pid] = SizePreset(pid, name, size)
    def get(self, n):       return self.presets.get(int(n))
    def store(self, n, p):  self.presets[int(n)] = p
    def delete(self, n):    self.presets.pop(int(n), None)
    def all_slots(self):    return sorted(self.presets.keys())

class SpreadPreset:
    """Phase-distribution preset (0 = sync, 100 = full chase)."""
    _BUILTINS = [(1,'Sync',0.0),(2,'Half',50.0),(3,'Chase',100.0)]
    def __init__(self, preset_id, name, spread=100.0):
        self.preset_id = int(preset_id)
        self.name      = name
        self.spread    = float(spread)
    def __repr__(self):
        return f"[spread {self.preset_id}] {self.name}  (spread={self.spread:.2f})"

class SpreadPool:
    def __init__(self):
        self.presets = {}
        for pid, name, spread in SpreadPreset._BUILTINS:
            self.presets[pid] = SpreadPreset(pid, name, spread)
    def get(self, n):       return self.presets.get(int(n))
    def store(self, n, p):  self.presets[int(n)] = p
    def delete(self, n):    self.presets.pop(int(n), None)
    def all_slots(self):    return sorted(self.presets.keys())


class SpeedMaster:
    """One live BPM master slot — FXLayers referencing this slot track its BPM live."""
    def __init__(self, slot_id, bpm=120.0, name=""):
        self.slot_id = int(slot_id)
        self.bpm     = float(bpm)
        self.name    = name or f"spd{slot_id}"
    def __repr__(self):
        return f"[SpeedMaster {self.slot_id}] {self.name}  ({self.bpm:.1f} BPM)"

class SpeedMasterPool:
    """16 live BPM master slots (expandable).

    Each FXLayer can reference a slot by speed_id; changing a master's BPM
    updates all linked layers on the next tick — no preset reload needed.
    """
    _DEFAULT_SLOTS = 16

    def __init__(self):
        self.masters = {}
        for i in range(1, self._DEFAULT_SLOTS + 1):
            self.masters[i] = SpeedMaster(i)

    def get(self, n):
        return self.masters.get(int(n))

    def set_bpm(self, n, bpm):
        n = int(n)
        if n not in self.masters:
            self.masters[n] = SpeedMaster(n)
        self.masters[n].bpm = float(bpm)

    def get_bpm(self, n):
        m = self.masters.get(int(n))
        return m.bpm if m else None

    def all_slots(self):
        return sorted(self.masters.keys())


# ------------------------------------------------------------
# FXLayer — one running effect
# ------------------------------------------------------------

class FXLayer:
    """
    A single FX running across a list of sub-fixtures.

    pool references (form_id, rate_id, size_id, spread_id) are live-tracked:
    updating a pool entry propagates to all FXLayers referencing it on the
    next tick. Inline values (_bpm_inline, _size_inline, _spread_inline) are
    used as fallbacks when no pool ID is set.
    """
    def __init__(self, fx_id, waveform, channel, rate_bpm, size,
                 targets, spread=0.0,
                 form_pool=None, rate_pool=None, size_pool=None, spread_pool=None,
                 dim_pool=None, speed_master_pool=None, group_pool=None,
                 form_id=None, rate_id=None, size_id=None, spread_id=None,
                 dim_id=None, speed_id=None,
                 phase_offset=0.0, infade=0.0, outfade=0.0,
                 block_size=1, order='linear', direction='forward',
                 grouping=None, low=0.0):
        self.fx_id        = fx_id
        self.waveform     = waveform
        self.channel      = channel
        self.phase_offset = float(phase_offset)   # 0.0–1.0; shifts entire layer in time
        self.targets      = targets
        self.start        = time.monotonic()
        self.is_active    = True

        # Distribution — how targets are grouped/sequenced across the spread.
        # `grouping` selects the algorithm that buckets the target list
        # into phase-steps, which is what actually produces different
        # chase *patterns* from the same waveform/targets:
        #   grouping=None (default) — legacy behavior, unchanged: plain
        #       block_size chunking (adjacent targets per step) + the
        #       separate order='random'/direction knobs below. Existing
        #       saved shows/layers have no grouping field and must
        #       reproduce their exact original pattern.
        #   'block'   — same block_size chunking, named explicitly.
        #   'mirror'  — folds the target list in half: target i and target
        #       (n-1-i) share a phase-step, so the pattern runs
        #       symmetrically from both ends inward (or center outward,
        #       with direction='reverse') — e.g. a stage-left/stage-right
        #       mirrored chase instead of a single sweep across everything.
        #   'cluster' — phase-step is which GroupPool group a target's
        #       fixture belongs to (by group_id order; ungrouped fixtures
        #       share one trailing step) instead of raw list position —
        #       e.g. "front truss" and "back truss" step separately
        #       regardless of patch order, if those are two Groups.
        #   'random'  — steps shuffled once (stable per fx_id) — same
        #       mechanism order='random' already provided, just reachable
        #       from the one grouping selector alongside the others.
        # block_size — adjacent targets per step (1 = one target per step);
        #              only meaningful when grouping is None or 'block'.
        # order      — 'linear' (patch order) or 'random' (shuffled once, stable per fx_id).
        #              Superseded by grouping='random' but kept for the
        #              grouping=None legacy path.
        # direction  — 'forward' | 'reverse' (flips step sequence) | 'bounce' (phase
        #              folds forward-then-back in time instead of wrapping — the whole
        #              chase sweeps out across targets and back).
        self.block_size = max(1, int(block_size))
        self.order      = order
        self.direction  = direction
        self.grouping   = grouping
        self._group_pool = group_pool
        self._offsets   = self._compute_offsets()

        # Amplitude envelope
        self.infade      = float(infade)    # seconds to ramp 0→1 at start
        self.outfade     = float(outfade)   # seconds to ramp 1→0 when fading out
        self._out_start  = None             # set by begin_outfade()

        # pool references
        self._form_pool         = form_pool
        self._rate_pool         = rate_pool
        self._size_pool         = size_pool
        self._spread_pool       = spread_pool
        self._dim_pool          = dim_pool
        self._speed_master_pool = speed_master_pool

        # pool IDs — live-tracked via properties
        self.form_id     = form_id
        self._rate_id    = rate_id
        self._size_id    = size_id
        self._spread_id  = spread_id
        self._dim_id     = dim_id   # DimmerPreset.level used as amplitude ceiling
        self._speed_id   = speed_id  # SpeedMaster slot; overrides rate_bpm when set

        # Inline fallback values
        self._bpm_inline    = float(rate_bpm)
        self._size_inline   = float(size)
        self._spread_inline = float(spread)

        # Per-fader amplitude multiplier — set by FADER n SIZE; 1.0 = normal
        self.size_scale = 1.0

        # Floor for the oscillation range (0-100, same units as size) — the
        # waveform swings between `low` and `size` instead of between 0 and
        # `size`, e.g. low=40 size=70 keeps a strobe/dim sync between 40%
        # and 70% instead of ever going fully dark. No pool backing (unlike
        # rate/size/spread) — a plain inline value, since there's no
        # existing "low" concept to reuse a preset pool for. 0 (default)
        # reproduces the exact original 0-to-size behavior.
        self.low = max(0.0, min(100.0, float(low)))

    def begin_outfade(self, now=None):
        """Trigger amplitude ramp-out. Engine auto-removes when amplitude hits 0."""
        if self._out_start is None:
            self._out_start = time.monotonic() if now is None else now

    @property
    def rate_bpm(self):
        # Priority: speed master > rate preset > inline BPM
        if self._speed_id is not None and self._speed_master_pool:
            m = self._speed_master_pool.get(self._speed_id)
            if m: return m.bpm
        if self._rate_pool and self._rate_id is not None:
            p = self._rate_pool.get(self._rate_id)
            if p: return p.bpm
        return self._bpm_inline

    @rate_bpm.setter
    def rate_bpm(self, val):
        self._bpm_inline = float(val)
        self._rate_id = None
        # speed_id is intentionally NOT cleared — rate_bpm.setter is used by the
        # global rate slider which should not detach a layer from its speed master

    def set_rate_smooth(self, new_bpm, now=None):
        """Change BPM while preserving current phase position (no jump/glitch)."""
        if now is None:
            now = time.monotonic()
        old_hz = self.rate_bpm / 60.0
        current_phase = ((now - self.start) * old_hz) % 1.0 if old_hz > 0 else 0.0
        self._bpm_inline = float(new_bpm)
        self._rate_id = None
        new_hz = self._bpm_inline / 60.0
        self.start = (now - current_phase / new_hz) if new_hz > 0 else now

    @property
    def size(self):
        if self._size_pool and self._size_id is not None:
            p = self._size_pool.get(self._size_id)
            val = p.size if p else self._size_inline
        else:
            val = self._size_inline
        # dim_id: live ceiling — DimmerPreset.level (0-1) scales max amplitude
        if self._dim_pool and self._dim_id is not None:
            dp = self._dim_pool.get(self._dim_id)
            if dp:
                val = val * dp.level
        return val

    @size.setter
    def size(self, val):
        self._size_inline = float(val)
        self._size_id = None

    @property
    def spread(self):
        if self._spread_pool and self._spread_id is not None:
            p = self._spread_pool.get(self._spread_id)
            if p: return p.spread
        return self._spread_inline

    @spread.setter
    def spread(self, val):
        self._spread_inline = float(val)
        self._spread_id = None

    def _get_fn(self):
        """Resolve waveform function live from FormPool on every call."""
        if self._form_pool and self.form_id is not None:
            form = self._form_pool.get(self.form_id)
            if form:
                return form.get_fn()
        return Waveform.get(self.waveform)

    def _compute_offsets(self):
        """
        Precompute each target's 0.0-1.0 phase offset (before the spread
        multiplier is applied), honoring grouping/block_size/order/direction.
        Computed once at construction — random shuffles groups with a seed
        stable for this layer's lifetime, not re-rolled every tick.

        grouping=None, block_size=1, order='linear', direction='forward'
        reproduces the original i/count offset exactly, so existing saved
        shows are unaffected.
        """
        n = len(self.targets)
        if n <= 1:
            return [0.0] * n

        if self.grouping == 'mirror':
            # Target i and target (n-1-i) share a phase-step — the pattern
            # runs symmetrically from both ends inward.
            group_of = [min(i, n - 1 - i) for i in range(n)]
        elif self.grouping == 'cluster':
            group_of = self._cluster_indices()
        else:
            # None or 'block' — plain adjacent-target chunking.
            group_of = [i // self.block_size for i in range(n)]

        num_groups  = max(group_of) + 1
        positions   = list(range(num_groups))
        if self.grouping == 'random' or self.order == 'random':
            random.Random(self.fx_id).shuffle(positions)
        if self.direction == 'reverse':
            positions = positions[::-1]

        denom        = num_groups if num_groups > 1 else 1
        group_offset = [p / denom for p in positions]
        return [group_offset[g] for g in group_of]

    def _cluster_indices(self):
        """Bucket targets by GroupPool membership instead of raw list
        order — targets whose containing fixture is in the same Group
        step together (grouped by group_id order; a target whose fixture
        isn't in any group falls into one trailing shared bucket)."""
        n = len(self.targets)
        if not self._group_pool:
            return [0] * n
        fids = []
        for t in self.targets:
            fid = getattr(t, 'master_id', None)
            if fid is None:
                fid = getattr(t, 'fixture_id', None)
            fids.append(fid)
        group_ids_sorted = sorted(self._group_pool.groups.keys())
        fid_to_bucket = {}
        for bucket_idx, gid in enumerate(group_ids_sorted):
            grp = self._group_pool.groups[gid]
            for _type, member_fid in grp.members:
                if member_fid not in fid_to_bucket:
                    fid_to_bucket[member_fid] = bucket_idx
        ungrouped_bucket = len(group_ids_sorted)
        return [fid_to_bucket.get(fid, ungrouped_bucket) for fid in fids]

    def get_values(self, now):
        if not self.is_active or not self.targets:
            self._last_env = 0.0
            return {}

        # Amplitude envelope: outfade → infade → full
        if self._out_start is not None:
            elapsed_out = now - self._out_start
            env = max(0.0, 1.0 - elapsed_out / self.outfade) if self.outfade > 0 else 0.0
            if env <= 0.0:
                self.is_active = False   # engine will sweep this layer out
                self._last_env = 0.0
                return {}
        elif self.infade > 0:
            env = min(1.0, (now - self.start) / self.infade)
        else:
            env = 1.0
        self._last_env = env  # expose for FXEngine to store in fx_layer

        fn      = self._get_fn()
        rate_hz = self.rate_bpm / 60.0

        # 'bounce' folds elapsed cycles into a triangle wave (0→1→0) instead
        # of wrapping (0→1→0→1), so the whole chase sweeps across targets
        # and back rather than always restarting from the same end.
        if self.direction == 'bounce':
            cycles = (now - self.start) * rate_hz
            frac   = cycles % 2.0
            cycle_phase = frac if frac <= 1.0 else 2.0 - frac
        else:
            cycle_phase = (now - self.start) * rate_hz
        base_phase = cycle_phase + self.phase_offset

        # size 0-100 → 0-255 DMX high bound; low 0-100 → 0-255 DMX floor;
        # spread 0-100 → 0.0-1.0 phase fraction. The waveform swings
        # between `base` (low) and `base + swing` (high) instead of
        # between 0 and high — low=0 (default) makes swing == the
        # original sz and base == 0, i.e. the exact original 0-to-size
        # behavior. Both base and swing scale with env/size_scale
        # together so the whole effect (floor included) still fades to
        # true 0 on infade/outfade/FADER SIZE, rather than leaving a
        # residual floor lit after the effect has "faded out".
        env_scale = env * max(0.0, self.size_scale)
        lo_frac = max(0.0, min(1.0, self.low  / 100.0))
        hi_frac = max(0.0, min(1.0, self.size / 100.0))
        if hi_frac < lo_frac:
            hi_frac = lo_frac
        base   = lo_frac * 255.0 * env_scale
        swing  = (hi_frac - lo_frac) * 255.0 * env_scale
        sp     = self.spread / 100.0
        result = {}
        for i, sub in enumerate(self.targets):
            phase = (base_phase + self._offsets[i] * sp) % 1.0
            wave_val = (Waveform.flicker(phase, i) if self.waveform == 'flicker'
                        else fn(phase))
            result[str(sub.fixture_id)] = base + wave_val * swing
        return result

    def __repr__(self):
        refs = []
        if self.form_id    is not None: refs.append(f"form:{self.form_id}")
        if self._rate_id   is not None: refs.append(f"rate:{self._rate_id}")
        if self._size_id   is not None: refs.append(f"size:{self._size_id}")
        if self._spread_id is not None: refs.append(f"spread:{self._spread_id}")
        if self._dim_id    is not None: refs.append(f"dimref:{self._dim_id}")
        ref_s = f" [{','.join(refs)}]" if refs else ""
        dist = []
        if self.grouping is not None: dist.append(f"grouping:{self.grouping}")
        if self.block_size != 1:    dist.append(f"block:{self.block_size}")
        if self.order != 'linear':  dist.append(f"order:{self.order}")
        if self.direction != 'forward': dist.append(f"dir:{self.direction}")
        dist_s = f" ({','.join(dist)})" if dist else ""
        low_s = f" low={self.low:.0f}" if self.low else ""
        return (f"[FX {self.fx_id}] {self.waveform}{ref_s} on {self.channel} | "
                f"{self.rate_bpm:.1f}BPM size={self.size:.0f}{low_s} spread={self.spread:.2f}{dist_s} "
                f"[{len(self.targets)} targets]")


# ------------------------------------------------------------
# FXEngine — manages all active FX layers
# ------------------------------------------------------------

class FXEngine:
    """
    Runs all active FX layers at 44Hz.
    Writes combined output to output_state.fx_layer.
    Multiple FX on the same channel are additive (clamped later).

    form_pool — optional FormPool; when set, waveform functions are
                resolved from the pool at add() time so custom forms
                are used automatically.
    """
    def __init__(self, output_state, form_pool=None, rate_pool=None,
                 size_pool=None, spread_pool=None, dim_pool=None,
                 speed_master_pool=None, group_pool=None):
        self.output_state      = output_state
        self.form_pool         = form_pool
        self.rate_pool         = rate_pool
        self.size_pool         = size_pool
        self.spread_pool       = spread_pool
        self.dim_pool          = dim_pool
        self.speed_master_pool = speed_master_pool
        self.group_pool        = group_pool   # for grouping='cluster' layers
        self._layers      = {}
        self._lock        = threading.Lock()
        self._running     = True
        self._thread      = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def add(self, fx_id, waveform, channel, rate_bpm, size,
            targets, spread=1.0, form_id=None,
            rate_id=None, size_id=None, spread_id=None, dim_id=None,
            speed_id=None,
            phase_offset=0.0, infade=0.0, outfade=0.0,
            block_size=1, order='linear', direction='forward',
            grouping=None, low=0.0):
        """
        Add an FX layer.
        waveform    — name string ('sine', 'ramp' …) or ignored when form_id given.
        form_id     — explicit FormPool slot; overrides waveform name lookup.
        dim_id      — DimmerPool slot; live ceiling on amplitude (0–1 scales size).
        infade      — seconds to ramp amplitude 0→1 from layer start.
        outfade     — seconds to ramp amplitude 1→0 when remove() is called.
        block_size  — adjacent targets grouped per step (default 1).
        order       — 'linear' or 'random' target sequencing (default 'linear').
        direction   — 'forward' | 'reverse' | 'bounce' (default 'forward').
        grouping    — None | 'block' | 'mirror' | 'cluster' | 'random' — see
                      FXLayer's own docstring/comments for what each does.
        low         — 0-100 floor for the oscillation range; the waveform
                      swings between low and size instead of 0 and size
                      (default 0 — unchanged original behavior).
        """
        layer = FXLayer(
            fx_id, waveform, channel, rate_bpm, size, targets, spread,
            form_pool         = self.form_pool,
            rate_pool         = self.rate_pool,
            size_pool         = self.size_pool,
            spread_pool       = self.spread_pool,
            dim_pool          = self.dim_pool,
            speed_master_pool = self.speed_master_pool,
            group_pool        = self.group_pool,
            form_id      = form_id,
            rate_id      = rate_id,
            size_id      = size_id,
            spread_id    = spread_id,
            dim_id       = dim_id,
            speed_id     = speed_id,
            phase_offset = phase_offset,
            infade       = infade,
            outfade      = outfade,
            block_size   = block_size,
            order        = order,
            direction    = direction,
            grouping     = grouping,
            low          = low,
        )
        with self._lock:
            self._layers[fx_id] = layer
        print(f"Added: {layer}")
        return layer

    def remove(self, fx_id, now=None, default_outfade=0.0):
        """Remove a layer. Triggers outfade if the layer has outfade > 0;
        otherwise removes immediately. default_outfade is used when the
        layer was created with outfade=0 (callers pass the cue fade time)."""
        with self._lock:
            layer = self._layers.get(fx_id)
            if layer is None:
                return
            # Apply default_outfade when the layer has no explicit outfade set
            if layer.outfade == 0.0 and default_outfade > 0:
                layer.outfade = float(default_outfade)
            if layer.outfade > 0 and layer._out_start is None:
                layer.begin_outfade(now)
                print(f"FX {fx_id} outfading ({layer.outfade}s).")
            else:
                self._layers.pop(fx_id, None)
                print(f"FX {fx_id} removed.")

    def clear(self):
        with self._lock:
            self._layers.clear()
            self.output_state.fx_layer = {}
        print("All FX cleared.")

    def print_fx(self):
        print("\n===== FX LAYERS =====")
        if not self._layers:
            print("  (none active)")
        for layer in self._layers.values():
            print(f"  {layer}")
        print("=====================\n")

    def compute_merged(self, now):
        """Evaluate all active FX layers at timestamp `now`, update output_state.fx_layer,
        and remove any layers whose outfade has finished. Thread-safe via internal lock.

        Called by the network thread right before each sACN transmission so strobe
        transitions are evaluated at the exact send moment, not from a cached snapshot
        that could be up to one full FX tick (22ms at 44Hz) stale."""
        merged = {}
        dead   = []
        with self._lock:
            for fx_id, layer in self._layers.items():
                vals = layer.get_values(now)
                env  = getattr(layer, '_last_env', 1.0)
                if not layer.is_active:
                    dead.append(fx_id)
                    continue
                for fid, value in vals.items():
                    if fid not in merged:
                        merged[fid] = {}
                    merged[fid][layer.channel] = (
                        merged[fid].get(layer.channel, 0) + value
                    )
                    env_key = f'_env_{layer.channel}'
                    if env > merged[fid].get(env_key, 0.0):
                        merged[fid][env_key] = env
            for fx_id in dead:
                self._layers.pop(fx_id, None)
                print(f"FX {fx_id} outfade complete — removed.")
        self.output_state.fx_layer = merged

    def _run(self):
        # Background loop for envelope/outfade tracking when the network thread
        # is not driving compute_merged() (e.g. dry_run with no network engine).
        while self._running:
            self.compute_merged(time.monotonic())
            time.sleep(1 / 44)

    def stop(self):
        self._running = False


# ------------------------------------------------------------
# _bucket_fx_defs — shared by _prog_fx_start and Fader._start_cue_fx
# ------------------------------------------------------------

def _bucket_fx_defs(fx_defs_by_fid, patch):
    """
    Bucket per-fixture FX defs into (ld, targets) groups so identical defs
    across multiple fixtures share ONE FXLayer — this lets spread/chase
    cross fixture boundaries instead of being confined to a single tube.

    fx_defs_by_fid: {master_fixture_id (int or numeric str): [fx_def, ...]}

    Each def's 'target_scope' controls what 'targets' becomes:
      'fixture' — one target per whole master fixture; a chase step moves
                  a whole tube at once. Default for the 'dim' channel.
      'pixel'   — flattened sub-fixture pixels across every matching master,
                  so a chase can run pixel-by-pixel straight through
                  multiple tubes. Default for colour channels.

    Returns a list of (ld, targets) tuples ready for fx_engine.add().
    """
    buckets = {}   # key → (ld, scope, [masters])
    for fid, defs in fx_defs_by_fid.items():
        try:
            master = patch.get(int(fid))
        except (ValueError, TypeError):
            continue
        if not master:
            continue
        for ld in defs:
            scope = ld.get('target_scope') or 'pixel'
            key = (ld.get('waveform', 'sine'), ld.get('channel'),
                   round(ld.get('bpm',    60.0), 3),
                   round(ld.get('size',  100.0), 2),
                   round(ld.get('low',     0.0), 2),
                   round(ld.get('spread',  0.0), 4),
                   ld.get('phase_offset', 0.0),
                   ld.get('form_id'), ld.get('rate_id'),
                   ld.get('size_id'), ld.get('spread_id'), ld.get('dim_id'),
                   ld.get('group_id'), ld.get('color_id'),
                   ld.get('speed_id'),
                   scope,
                   ld.get('block_size', 1),
                   ld.get('order',      'linear'),
                   ld.get('direction',  'forward'),
                   ld.get('grouping'),
                   ld.get('infade', 0.0), ld.get('outfade', 0.0))
            if key not in buckets:
                buckets[key] = (ld, scope, [])
            buckets[key][2].append(master)

    grouped = []
    for ld, scope, masters in buckets.values():
        if scope == 'pixel':
            targets = [sub for m in masters for sub in m.all_subs()]
        else:
            targets = masters
        grouped.append((ld, targets))
    return grouped


def _expand_color_fx(fx_defs_by_fid, color_pool):
    """
    Expand any fx_def with channel='rgb' and color_id into three separate
    defs (red, green, blue) with sizes scaled by the preset's RGB values.
    Defs on other channels are passed through unchanged.
    color_pool may be None — in that case 'rgb' defs are dropped with a warning.
    """
    expanded = {}
    for fid, defs in fx_defs_by_fid.items():
        out = []
        for ld in defs:
            cid = ld.get('color_id')
            if ld.get('channel') == 'rgb' and cid is not None:
                cp = color_pool.get(cid) if color_pool else None
                if cp:
                    base_size = ld.get('size', 100.0)
                    for ch, val in (('red', cp.red), ('green', cp.green), ('blue', cp.blue)):
                        if val > 0:
                            sub = dict(ld)
                            sub['channel'] = ch
                            sub['size']    = (val / 255.0) * base_size
                            out.append(sub)
                else:
                    # color preset empty — use white fallback so FX is visible immediately
                    base_size = ld.get('size', 100.0)
                    for ch in ('red', 'green', 'blue'):
                        sub = dict(ld)
                        sub['channel'] = ch
                        sub['size']    = base_size
                        out.append(sub)
            else:
                out.append(ld)
        if out:
            expanded[fid] = out
    return expanded


def _expand_group_fx(fx_defs_by_fid, patch, group_pool):
    """
    For any fx_def with a group_id set, add that def to every fixture
    in the referenced group (in addition to whatever fixture already holds it).
    The group_id is kept in the def so _bucket_fx_defs can form a shared layer.
    Defs without group_id are passed through unchanged.
    """
    if not group_pool:
        return fx_defs_by_fid
    out = dict(fx_defs_by_fid)
    for fid, defs in fx_defs_by_fid.items():
        for ld in defs:
            gid = ld.get('group_id')
            if gid is None:
                continue
            grp = group_pool.get(gid)
            if not grp:
                continue
            for master in grp.recall(patch):
                mfid = str(master.fixture_id)
                if mfid not in out:
                    out[mfid] = []
                if ld not in out[mfid]:
                    out[mfid].append(ld)
    return out


__all__ = ["Waveform", "FormPreset", "FormPool", "RatePreset", "RatePool",
           "SizePreset", "SizePool", "SpreadPreset", "SpreadPool",
           "SpeedMaster", "SpeedMasterPool", "FXLayer", "FXEngine",
           "_bucket_fx_defs", "_expand_color_fx", "_expand_group_fx"]
