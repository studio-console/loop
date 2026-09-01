"""Studio Console playback engine — extracted from studio_project.py:
FadeEngine, the cue/stack firing helpers (_resolve_cue_refs, _vfade_apply,
_exec_fader_mode_hook, _stack_fire_cue, _stack_go/back/goto/reload), and
OutputState. These were interleaved with the FX engine section (now
studio_console/engine/fx.py) in the original file — reassembled here into
one contiguous module, not just cut-and-pasted from one spot.

Two dependencies needed correction after the initial extraction:

1. FadeEngine.fire()/fire_release() construct Fade(...) objects, and the
   stack helpers monkey-patch Stack.go/back/goto/reload after defining
   them (`Stack.go = _stack_go`, etc.) — both need the Stack/Fade classes
   from the already-extracted studio_console.models.presets. Direct
   top-level import, no circular risk (models/presets.py has no
   dependency back on this module).

2. _stack_fire_cue() reads a module-level mutable dict `_prog_time`
   (programmer time-override state), defined in studio_project.py's
   wiring section — not extracted yet (a later phase: state.py). Since
   that dict is defined LATER in studio_project.py than this module's
   own import point, a module-level `from __main__ import _prog_time`
   would fail at import time. Deferred (function-local) import instead,
   same category as drivers/ai.py's Fader import — see that file's
   docstring for the general rationale. Reading a mutable dict's
   contents via a fresh deferred import each call is safe: it's the
   same dict object every time (only ever mutated in place, never
   reassigned), so there's no staleness concern.
"""

import threading
import time
import copy

from studio_console.models.presets import Stack, Fade


# ------------------------------------------------------------
# FadeEngine
# ------------------------------------------------------------

class FadeEngine:
    """
    Manages all active Fade objects.
    Runs in a background thread at 44Hz.
    Multiple fades can overlap — new cue fires while previous
    is still running and they crossfade naturally.
    Each fade writes to its fader's own layer.
    """
    def __init__(self):
        self._fades  = []
        self._lock   = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def fire(self, cue, fader, data_to=None,
             override_fade=None, override_delay=None):
        """snapshot fader's current layer and fade to new cue state.
        data_to: pre-resolved DMX dict; falls back to cue.data if not provided.
        override_fade / override_delay: time override from fader or programmer."""
        ft = override_fade  if override_fade  is not None else cue.fade_time
        dt = override_delay if override_delay is not None else cue.delay_time
        # Per-attribute times are suppressed when a global override is active
        fat = None if override_fade  is not None else (cue.fade_times  or None)
        dat = None if override_delay is not None else (cue.delay_times or None)
        fade = Fade(
            data_from   = fader.snapshot_layer(),
            data_to     = data_to if data_to is not None else cue.data,
            fade_time   = ft,
            delay_time  = dt,
            fader    = fader,
            fade_times  = fat,
            delay_times = dat,
        )
        with self._lock:
            self._fades.append(fade)
        src = " [override]" if override_fade is not None else ""
        print(f"  Fade: {dt}s delay → {ft}s crossfade{src}")

    def fire_release(self, fader, off_time, done_callback=None):
        """Fade fader's current layer to dark over off_time, then call done_callback."""
        fade = Fade(
            data_from     = fader.snapshot_layer(),
            data_to       = {},   # empty = all channels fade to 0
            fade_time     = max(0.0, float(off_time)),
            delay_time    = 0.0,
            fader      = fader,
            done_callback = done_callback,
        )
        with self._lock:
            self._fades.append(fade)

    def _run(self):
        while self._running:
            now = time.monotonic()
            with self._lock:
                for fade in self._fades:
                    fade.tick(now)
                self._fades = [f for f in self._fades if not f.done]
            time.sleep(1 / 44)

    def fade_progress(self, fader):
        """Return (elapsed_fraction, total_seconds) for the most recent active fade on
        this fader, or None if no fade is currently running."""
        now = time.monotonic()
        best = None
        with self._lock:
            for fade in self._fades:
                if fade.fader is fader and not fade.done:
                    ft = fade._default_ft
                    elapsed = now - fade._default_start
                    t = 1.0 if ft == 0 else min(1.0, max(0.0, elapsed / ft))
                    if best is None or elapsed > best[0]:
                        best = (elapsed, t, ft)
        if best is None:
            return None
        return best[1], best[2]   # (progress 0–1, total_seconds)

    def stop(self):
        self._running = False


# ------------------------------------------------------------
# Updated stack playback methods
# go / back / goto now route through FadeEngine
# ------------------------------------------------------------

def _resolve_cue_refs(cue_data, patch, color_pool, dim_pool, attr_pools=None):
    """
    Expand all *_ref keys in cue_data to raw DMX values.

    color_ref  → sub-fixture RGB via ColorPool
    dim_ref    → master dim via DimmerPool
    <x>_ref    → master/fixture channel values via attr_pools dict
                 e.g. attr_pools={"position": position_pool, "gobo": gobo_pool}

    Returns a new dict safe to pass to FadeEngine (no ref metadata, no lists).
    """
    attr_pools   = attr_pools or {}
    attr_ref_keys = {f"{name}_ref" for name in attr_pools}
    _SKIP_KEYS   = {'fx', 'color_ref', 'dim_ref', 'color_baked'} | attr_ref_keys
    masters_with_color_ref = set()
    resolved = {}

    # First pass: master entries
    for fid, vals in cue_data.items():
        if '.' in fid:
            continue
        color_ref = vals.get('color_ref')
        dim_ref   = vals.get('dim_ref')
        master_vals = {k: v for k, v in vals.items() if k not in _SKIP_KEYS}

        if dim_ref and dim_pool:
            dp = dim_pool.get(int(dim_ref))
            if dp:
                master_vals['dim'] = dp.level

        # Generic attribute ref expansion (position_ref, gobo_ref, zoom_ref, etc.)
        for attr_name, pool in attr_pools.items():
            ref_id = vals.get(f"{attr_name}_ref")
            if ref_id is not None:
                ap = pool.get(int(ref_id))
                if ap:
                    src = ap.data.get(fid)
                    if src:
                        master_vals.update(src)

        if master_vals:
            resolved[fid] = master_vals

        if color_ref and color_pool:
            masters_with_color_ref.add(fid)
            preset = color_pool.get(int(color_ref))
            if preset:
                try:
                    master = patch.get(int(fid))
                except (ValueError, TypeError):
                    master = None
                if master:
                    for sub in master.all_subs():
                        resolved[str(sub.fixture_id)] = {
                            'red':   preset.red,
                            'green': preset.green,
                            'blue':  preset.blue,
                        }

    # Second pass: sub-fixture entries not covered by a color_ref expansion
    for fid, vals in cue_data.items():
        if '.' not in fid:
            continue
        master_fid = fid.split('.')[0]
        if master_fid in masters_with_color_ref:
            continue  # already written by color_ref expansion
        if fid not in resolved:
            resolved[fid] = {k: v for k, v in vals.items() if k not in _SKIP_KEYS}

    return resolved


def _vfade_apply(ex):
    """Lerp fader.layer between vfade_from and vfade_to at ex.level.
    Channels in 'from' only fade out; channels in 'to' only fade in.
    FX and metadata keys are skipped."""
    t       = max(0.0, min(1.0, ex.level))
    from_d  = ex.vfade_from or {}
    to_d    = ex.vfade_to   or {}
    _SKIP   = {'fx', 'fx_kill', 'color_ref', 'dim_ref', 'color_baked'}
    all_fids = set(from_d) | set(to_d)
    ex.layer.clear()
    for fid in all_fids:
        fv = from_d.get(fid, {})
        tv = to_d.get(fid,   {})
        all_chs = (set(fv) | set(tv)) - _SKIP
        row = {}
        for ch in all_chs:
            f_val = fv.get(ch, 0.0)
            t_val = tv.get(ch, 0.0)
            if isinstance(f_val, (int, float)) and isinstance(t_val, (int, float)):
                row[ch] = f_val + (t_val - f_val) * t
        if row:
            ex.layer[fid] = row


def _exec_fader_mode_hook(ex):
    """Called whenever an fader's fader level changes. Handles output_mode side-effects."""
    mode = getattr(ex, 'output_mode', 'normal')
    if mode == 'moment':
        if ex.level <= 0.0:
            ex.is_active = False
        elif ex.stack and ex.stack.current is not None:
            ex.is_active = True
    elif mode == 'vfade':
        if getattr(ex, 'vfade_to', None) is not None:
            ex.is_active = True
            _vfade_apply(ex)


def _stack_fire_cue(self, cue_number, patch, fade_engine, fader):
    cue = self.cues[cue_number]
    self.current = cue_number
    fader.is_active = True

    # fx_kill: instant-apply by default so FX dies immediately without waiting
    # for the fade to interpolate 0→1.  Pre-setting fader.layer to 1.0 before
    # FadeEngine.fire() snapshots it means v_from==v_to==1 — no interpolation.
    # Leaving an fx_kill cue: clear it now so the Fade starts from 0 (not stale 1).
    new_cue_has_fx_kill = any(
        isinstance(v, dict) and v.get('fx_kill')
        for v in cue.data.values()
    )
    if new_cue_has_fx_kill:
        for fid_str, vals in cue.data.items():
            if isinstance(vals, dict) and vals.get('fx_kill'):
                fader.layer.setdefault(fid_str, {})['fx_kill'] = 1.0
    else:
        for fid_vals in fader.layer.values():
            fid_vals.pop('fx_kill', None)

    resolved = _resolve_cue_refs(
        cue.data, patch,
        getattr(fader, 'color_pool',    None),
        getattr(fader, 'dim_pool',      None),
        getattr(fader, 'attr_pools',    None),
    )
    print(f"\nGO → {cue}  [fader {fader.fdr_id}]")

    # Resolve time override: fader override wins; programmer time is fallback
    ov_fade = ov_delay = None
    stk = fader.stack
    if (fader.time_override_on
            and (stk is None or stk.allow_exec_time)):
        if fader.time_override_fade  is not None:
            ov_fade  = fader.time_override_fade
        if fader.time_override_delay is not None:
            ov_delay = fader.time_override_delay
    # programmer time fallback — only if no fader override applied
    # _prog_time is defined in studio_project.py's wiring section, not yet
    # extracted (a later phase). Deferred import — see module docstring.
    from __main__ import _prog_time
    if ov_fade is None and _prog_time.get('on'):
        ov_fade  = float(_prog_time['fade'])
        ov_delay = float(_prog_time['delay'])

    # Apply fader rate_factor — scales fade (and delay) times; >1.0 = faster
    _rate = getattr(fader, 'rate_factor', 1.0)
    if _rate > 0 and _rate != 1.0:
        ov_fade  = (ov_fade  if ov_fade  is not None else cue.fade_time)  / _rate
        ov_delay = (ov_delay if ov_delay is not None else cue.delay_time) / _rate
        if ov_delay == 0.0:
            ov_delay = None  # avoid setting a zero override that masks auto

    # Effective fade time — used as default FX infade so FX ramps match DMX fades
    eff_fade = ov_fade if ov_fade is not None else cue.fade_time

    # FX outfade strategy:
    #  - fx_kill cue or non-FX cue → snap old FX off so the DMX crossfade runs
    #    without FX overriding the new cue's base values.
    #  - FX→FX transition → keep a short (≤1s) tail so waveforms crossfade
    #    rather than cutting between them abruptly.
    new_cue_has_fx = any(
        isinstance(vals, dict) and vals.get('fx')
        for fk, vals in cue.data.items()
        if '.' not in str(fk)
    )
    if new_cue_has_fx_kill or not new_cue_has_fx:
        fx_outfade = 0.0   # snap: static or kill cue — let DMX carry the crossfade
    else:
        fx_outfade = min(eff_fade, 1.0)   # FX→FX: brief tail

    # Cue-stored fx_outfade overrides auto-computed value (set via RECORD CUE FXOUTFADE)
    _cue_fx_out = getattr(cue, 'fx_outfade', None)
    if _cue_fx_out is not None:
        fx_outfade = float(_cue_fx_out)

    fader._start_cue_fx(cue, patch, default_infade=eff_fade, default_outfade=fx_outfade)

    # Auto-follow: arm timer so _tick() fires GO after follow_time seconds
    follow = getattr(cue, 'follow_time', 0.0)
    fader._follow_at = (time.monotonic() + follow) if follow > 0 else None

    if getattr(fader, 'output_mode', 'normal') == 'vfade':
        fader.vfade_from = fader.snapshot_layer()
        fader.vfade_to   = copy.deepcopy(resolved)
        fader.is_active  = True
        _vfade_apply(fader)
        # auto-follow still works
        follow = getattr(cue, 'follow_time', 0.0)
        fader._follow_at = (time.monotonic() + follow) if follow > 0 else None
        return f"vfade → {cue.name}  (fader controls crossfade)"
    # Normal path: FadeEngine drives the crossfade
    fade_engine.fire(cue, fader, data_to=resolved,
                     override_fade=ov_fade, override_delay=ov_delay)
    return f"GO → {cue.name}"

def _stack_go(self, patch, fade_engine, fader):
    numbers = self._sorted_cue_numbers()
    if not numbers:
        return "stack is empty"
    if getattr(self, 'bounce', False):
        if self.current is None:
            self._bounce_dir = 1
            return _stack_fire_cue(self, numbers[0], patch, fade_engine, fader)
        try:
            idx = numbers.index(self.current)
        except ValueError:
            self._bounce_dir = 1
            return _stack_fire_cue(self, numbers[0], patch, fade_engine, fader)
        d = getattr(self, '_bounce_dir', 1)
        next_idx = idx + d
        if next_idx >= len(numbers):
            self._bounce_dir = -1
            next_idx = idx - 1
            if next_idx < 0:
                next_idx = 0
        elif next_idx < 0:
            self._bounce_dir = 1
            next_idx = idx + 1
            if next_idx >= len(numbers):
                next_idx = len(numbers) - 1
        return _stack_fire_cue(self, numbers[next_idx], patch, fade_engine, fader)
    wrap_occurred = False
    if self.current is None:
        next_num = numbers[0]
    else:
        try:
            idx      = numbers.index(self.current)
            next_idx = (idx + 1) % len(numbers)
            next_num = numbers[next_idx]
            wrap_occurred = (next_idx == 0 and idx == len(numbers) - 1)
        except ValueError:
            next_num = numbers[0]
    if wrap_occurred and getattr(self, 'wrap', False):
        fader.layer.clear()  # no LTP bleed from last cue back to first
    return _stack_fire_cue(self, next_num, patch, fade_engine, fader)

def _stack_back(self, patch, fade_engine, fader):
    numbers = self._sorted_cue_numbers()
    if not numbers:
        return "stack is empty"
    wrap_occurred = False
    if self.current is None:
        prev_num = numbers[-1]
    else:
        try:
            idx      = numbers.index(self.current)
            prev_idx = (idx - 1) % len(numbers)
            prev_num = numbers[prev_idx]
            wrap_occurred = (idx == 0 and prev_idx == len(numbers) - 1)
        except ValueError:
            prev_num = numbers[-1]
    if wrap_occurred and getattr(self, 'wrap', False):
        fader.layer.clear()  # no LTP bleed from first cue back to last
    return _stack_fire_cue(self, prev_num, patch, fade_engine, fader)

def _stack_goto(self, cue_number, patch, fade_engine, fader):
    num = float(cue_number)
    if num not in self.cues:
        return f"cue {cue_number} not found"
    return _stack_fire_cue(self, num, patch, fade_engine, fader)

def _stack_reload(self, patch, fade_engine, fader):
    """Re-fire the current cue without advancing the pointer."""
    if self.current is None:
        return "no active cue — use go to start"
    return _stack_fire_cue(self, self.current, patch, fade_engine, fader)

Stack.go     = _stack_go
Stack.back   = _stack_back
Stack.goto   = _stack_goto
Stack.reload = _stack_reload


# ------------------------------------------------------------
# Final OutputState — merges all fader layers + programmer
# + audio + FX.
# Priority (base layers, highest → lowest):
#   programmer  > audio  > fader layers (LTP)
# FX is additive on top of whichever base layer wins — FX always visible
# ------------------------------------------------------------

class OutputState:
    """
    The final resolved DMX state for every sub-fixture.

    Layers merged in priority order (lowest → highest):
      cue (via fader_pool LTP merge) → audio_layer → programmer_layer → fx_layer
    Master fader and per-fixture dim are applied last.

    get_dmx_for_universe() builds a 512-slot tuple ready to hand
    straight to the sACN sender.
    """
    def __init__(self, patch):
        self.patch            = patch
        self.programmer_layer = {}
        self.fx_layer         = {}
        self.audio_layer      = {}
        self.fader_pool    = None   # set via link_fader_pool()
        self.master_level     = 1.0   # grand master fader (0.0–1.0)
        self.blind            = False  # when True, programmer layer is suppressed from DMX output
        self.highlight_mode   = False  # when True, selected fixtures go full-white at 100%
        self.highlight_fids   = set()  # mixed set: master fixture_id ints (whole fixture)
                                        # and/or "master.sub" strings (SubFixture.fixture_id,
                                        # a specific pixel) — a fixture is highlighted if
                                        # EITHER its own id or the current sub's own id is in here
        self.direct_dmx       = {}    # {universe: {address(1-512): value(0-255)}}
        self.freeze_mode      = False  # when True, frozen_dmx is output verbatim
        self.frozen_dmx       = {}    # {universe: tuple(512)} — snapshot at FREEZE time
        self.solo_mode        = False  # when True, only solo_fids get output
        self.solo_fids        = set() # set of master fixture_id ints to pass through
        self.parked_fids      = set() # set of master fixture_id ints that are parked
        self.parked_addresses = {}    # {universe: {address(1-512): value}} — snapshot at park time
        self._lock            = threading.Lock()

    def link_programmer(self, programmer):
        self.programmer_layer = programmer.data

    def link_fader_pool(self, pool):
        self.fader_pool = pool

    def _merged_cue_layer(self):
        """LTP merge of all active fader layers. Called inside _lock."""
        merged = {}
        if not self.fader_pool:
            return merged
        for (layer, level) in self.fader_pool.active_layers():
            for fid, vals in layer.items():
                if fid not in merged:
                    merged[fid] = {}
                for ch, val in vals.items():
                    merged[fid][ch] = val * level
        return merged

    def get_dmx_for_universe(self, universe):
        if self.freeze_mode and universe in self.frozen_dmx:
            # FREEZE locks the *look*, not the master fader, SOLO isolation,
            # a direct DMX override, or PARK — BLACKOUT/MASTER must still be
            # able to cut a frozen output (safety-critical: BLACKOUT is
            # documented as "cut all output NOW" and must not be silently
            # defeated by FREEZE), SOLO's "zero everyone else" guarantee must
            # still hold, a direct DMX override is documented as
            # highest-priority/applied-last regardless of what else is
            # happening, and PARK is documented as "immune to cue/prog
            # changes" and higher priority still (even above direct_dmx).
            gm = self.master_level
            dmx = [int(v * gm) for v in self.frozen_dmx[universe]]
            if self.solo_mode:
                for master in self.patch.all_fixtures():
                    if master.fixture_id in self.solo_fids:
                        continue
                    for sub in master.all_subs():
                        for output in sub.outputs:
                            if output['universe'] != universe:
                                continue
                            addr = output['address'] - 1
                            for offset in range(len(sub.profile.channels)):
                                if addr + offset > 511:
                                    break
                                dmx[addr + offset] = 0
            for addr1, val in self.direct_dmx.get(universe, {}).items():
                if 1 <= addr1 <= 512:
                    dmx[addr1 - 1] = max(0, min(255, int(val)))
            for addr1, val in self.parked_addresses.get(universe, {}).items():
                if 1 <= addr1 <= 512:
                    dmx[addr1 - 1] = max(0, min(255, int(val)))
            return tuple(dmx)
        dmx = [0] * 512
        with self._lock:
            cue_merged = self._merged_cue_layer()

            _blind_prog = self.blind
            for master in self.patch.all_fixtures():
                master_fid   = str(master.fixture_id)
                prog_master  = {} if _blind_prog else self.programmer_layer.get(master_fid, {})
                cue_master   = cue_merged.get(master_fid, {})
                audio_master = self.audio_layer.get(master_fid, {})

                # Priority model:
                #   Colour FX (red/green/blue) → replaces base colour on that channel
                #     (highest priority: FX > programmer > audio > cue)
                #   dim FX (dim channel) → multiplied against the base dim hierarchy
                #     (programmer dim × FX_dim, so programmer can still kill output)
                #   RGB FX implicit dim → when colour FX is running but no explicit dim
                #     source exists (FX-only cue), default to 1.0 so fixtures are visible.
                #     Explicit cue/programmer dim is respected and NOT overridden.
                # fx_kill in programmer or cue explicitly suppresses all FX for this fixture
                #
                # dim FX can target this whole fixture (target_scope='fixture' —
                # fx_layer[master_fid]['dim']) or drive each pixel independently
                # (target_scope='pixel' — fx_layer[sub_fid]['dim']). Per-pixel value
                # wins when present; otherwise it falls back to the fixture-level one.
                _fx_kill      = (prog_master.get('fx_kill', 0) >= 0.5 or
                                 cue_master.get('fx_kill',  0) >= 0.5)

                fx_master        = {} if _fx_kill else self.fx_layer.get(master_fid, {})
                _fixture_dim_fx  = fx_master.get('dim')
                _first_sub       = next(iter(master.sub_fixtures.values()), None)
                # _rgb_fx_on: only True when colour FX has actually faded in (env > 0).
                # Checking _env_ keys avoids a dim-snap at infade t=0 where the FX
                # layer exists but all amplitudes are still 0.
                if _fx_kill or not _first_sub:
                    _rgb_fx_on = False
                else:
                    _fsub_fx = self.fx_layer.get(str(_first_sub.fixture_id), {})
                    _rgb_fx_on = any(
                        _fsub_fx.get(f'_env_{c}', 0.0) > 0.001
                        for c in ('red', 'green', 'blue')
                    )

                _base_dim = prog_master.get('dim', audio_master.get('dim',
                             cue_master.get('dim', master.virtual_dimmer)))
                _explicit_cue_dim = cue_master.get('dim')
                _rgb_fallback_dim = prog_master.get('dim', audio_master.get('dim',
                             _explicit_cue_dim if _explicit_cue_dim is not None else 1.0))

                for sub in master.all_subs():
                    fid        = str(sub.fixture_id)
                    prog_vals  = {} if _blind_prog else self.programmer_layer.get(fid, {})
                    audio_vals = self.audio_layer.get(fid, {})
                    cue_vals   = cue_merged.get(fid, {})
                    fx_vals    = {} if _fx_kill else self.fx_layer.get(fid, {})

                    fx_dim_raw = fx_vals.get('dim', _fixture_dim_fx)
                    if fx_dim_raw is not None:
                        # dim FX: multiplicative on top of static dim hierarchy
                        sub_dim = max(0.0, min(1.0, _base_dim * (fx_dim_raw / 255.0)))
                    elif _rgb_fx_on:
                        # Colour FX running: respect explicit programmer/cue dim;
                        # fall back to 1.0 only when no explicit source exists.
                        sub_dim = _rgb_fallback_dim
                    else:
                        sub_dim = _base_dim

                    gm        = self.master_level
                    highlight = (self.highlight_mode and
                                 (master.fixture_id in self.highlight_fids
                                  or fid in self.highlight_fids))

                    # Build resolved values for all profile channels on this sub.
                    # Colour channels: FX envelope-blend + dimmer applied.
                    # 'dimmer' profile channel: maps from master dim hierarchy (0-255).
                    # Attribute channels (pan/tilt/gobo/etc): LTP only, no dimmer,
                    #   FX additive (same blend formula as colour).
                    _COLOUR_CHS = frozenset({'red', 'green', 'blue', 'white', 'amber'})
                    ch_resolved = {}
                    for ch in sub.profile.channels:
                        if ch in _COLOUR_CHS:
                            if highlight:
                                ch_resolved[ch] = int(255 * gm)
                            else:
                                base_val = prog_vals.get(ch, audio_vals.get(ch, cue_vals.get(ch, 0)))
                                if ch in fx_vals:
                                    env = fx_vals.get(f'_env_{ch}', 1.0)
                                    merged = max(0, min(255, int(base_val * (1.0 - env) + fx_vals[ch])))
                                else:
                                    merged = base_val
                                ch_resolved[ch] = max(0, min(255, int(merged * sub_dim * gm)))
                        elif ch == 'dimmer':
                            if highlight:
                                ch_resolved[ch] = int(255 * gm)
                            else:
                                # Explicit 'dimmer' stored on sub wins; otherwise use master dim.
                                # sub_dim already folds in dim FX modulation, so use it in both paths.
                                base_val = prog_vals.get('dimmer', audio_vals.get('dimmer',
                                           cue_vals.get('dimmer', None)))
                                if base_val is not None:
                                    fx_ratio = (sub_dim / _base_dim) if _base_dim > 0.0001 else 1.0
                                    ch_resolved[ch] = max(0, min(255, int(base_val * fx_ratio * gm)))
                                else:
                                    ch_resolved[ch] = max(0, min(255, int(sub_dim * gm * 255)))
                        else:
                            # Attribute channel: LTP, no dimmer, FX envelope-blend additive
                            base_val = prog_vals.get(ch, audio_vals.get(ch, cue_vals.get(ch, 0)))
                            if ch in fx_vals:
                                env = fx_vals.get(f'_env_{ch}', 1.0)
                                val = max(0, min(255, int(base_val * (1.0 - env) + fx_vals[ch])))
                            else:
                                val = base_val
                            ch_resolved[ch] = max(0, min(255, int(val)))

                    # SOLO: if active, zero out non-solo fixtures
                    _solo_suppress = (self.solo_mode and
                                      master.fixture_id not in self.solo_fids)
                    for output in sub.outputs:
                        if output['universe'] != universe:
                            continue
                        addr = output['address'] - 1
                        for offset, ch in enumerate(sub.profile.channels):
                            if addr + offset > 511:
                                break
                            dmx[addr + offset] = 0 if _solo_suppress else ch_resolved.get(ch, 0)
            # direct DMX overrides — applied after all other layers
            for addr1, val in self.direct_dmx.get(universe, {}).items():
                if 1 <= addr1 <= 512:
                    dmx[addr1 - 1] = max(0, min(255, int(val)))
            # Parked fixture values — absolute, highest priority (even above direct_dmx)
            for addr1, val in self.parked_addresses.get(universe, {}).items():
                if 1 <= addr1 <= 512:
                    dmx[addr1 - 1] = max(0, min(255, int(val)))
        return tuple(dmx)


__all__ = ["FadeEngine", "OutputState", "_resolve_cue_refs", "_vfade_apply",
           "_exec_fader_mode_hook", "_stack_fire_cue", "_stack_go",
           "_stack_back", "_stack_goto", "_stack_reload"]
