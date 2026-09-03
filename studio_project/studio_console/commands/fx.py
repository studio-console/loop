"""Studio Console command dispatch — FX, FORM/BPM/TAP/SIZE/SPREAD/STROBE/RAINBOW, FIRE FX, KILL/CLEAR FX.

Part of the run_command split (Phase 9). Each function here corresponds
to exactly one of run_command's original top-level `if` branches (same
name suffix as the branch's index in the original file, for traceability),
converted to a standalone function returning the result string on match
or None to signal "not handled" so commands/__init__.py's dispatcher tries
the next branch in the ORIGINAL file's exact order — this is what
preserves the original first-match-wins semantics across branches that
got split into different category files (e.g. RECORD-prefixed branches
are scattered across stack.py/presets.py/fx.py/misc.py, in the original
file interspersed with many other tokens' branches).

Import surface is broad (every already-extracted module's public exports)
rather than hand-trimmed per branch — verified safe and complete with an
AST-based undefined-name checker, same as every other phase of this split.
"""

import os
import json
import time
import copy
import re as _re

from studio_console.state import (
    LIGHTFORM_CUE_MAP, STUDIO_DRY_RUN, STUDIO_HEADLESS, _NET_BIND, _NET_UNIVERSES, _active_fader,
    _active_stack, _apply_fixture_defaults, _apply_timing_edit, _attr_pools, _blackout_saved_level, _cs_loaded,
    _fader_dim, _fixture_defaults, _fx_params, _macro_play_stack, _macro_recording, _make_set_speed_master,
    _midi_doc, _name_after, _on_cue_fire, _osc_cmd, _osc_fader, _osc_key,
    _preset_live_push, _prog_fx_ids, _prog_snapshots, _prog_time, _start_magenta_sine, _stop_fx,
    _stop_prog_fx_preview, _tap_times, active_fader, active_fx, ai, all_subs,
    audio_engine, audio_mapper, beam_pool, color_pool, control_pool, cs1,
    cue_back, cue_go, cue_pool, cue_reload, dim_pool, export_presets,
    fade_engine, fader_pool, flash_off, flash_on, focus_pool, form_pool,
    fx_engine, fx_pool, gobo_pool, goto_1, goto_2, goto_3,
    goto_4, goto_cue, group_pool, import_presets, library, list_shows,
    load_show_from, macro_pool, midi, network, osc, output_state,
    patch, position_pool, prog, rate_pool, save_show, save_show_as,
    set_all_dim, set_fx_rate, set_fx_size, set_fx_spread, size_pool, speed_master_pool,
    spread_pool, stack_pool, tap_tempo, transport_back, transport_go, transport_rewind,
    zoom_pool,
)

from studio_console.models.fixtures import (
    FixtureProfile, FixtureLibrary, GDTFLoader, SubFixture, MasterFixture, Patch,
    programmer,
)
from studio_console.models.presets import (
    ColorPreset, ColorPool, DimmerPreset, DimmerPool, AttributePreset, AttributePool,
    Group, GroupPool, Cue, Stack, CuePool, StackPool,
    Fader, FaderPool, FXPreset, FXPool, Fade,
)

from studio_console.engine.playback import (
    FadeEngine, OutputState, _resolve_cue_refs, _vfade_apply, _exec_fader_mode_hook, _stack_fire_cue,
    _stack_go, _stack_back, _stack_goto, _stack_reload,
)
from studio_console.engine.fx import (
    Waveform, FormPreset, FormPool, RatePreset, RatePool, SizePreset,
    SizePool, SpreadPreset, SpreadPool, SpeedMaster, SpeedMasterPool, FXLayer,
    FXEngine, _bucket_fx_defs, _expand_color_fx, _expand_group_fx,
    _fx_grouping_compat,
)

from studio_console.drivers.network import NetworkEngine
from studio_console.drivers.midi import CCMapping, NoteMapping, MIDIEngine
from studio_console.drivers.osc import OSCEngine
from studio_console.drivers.audio import AudioEngine, AudioMapper
from studio_console.drivers.ai import AIEngine
from studio_console.show import ShowFile, _write_file, _read_file
from studio_console.commands._shared import (
    _record_cue_into, _prog_fx_stop, _prog_fx_start, _prog_fx_rebuild,
    _resolve_fx_selection_targets, _snapshot_undo,
)

# GUIEngine hasn't been extracted yet as its own importable module —
# defined in studio_project.py, which imports this package. Deferred
# import inside each function that needs it (same pattern used
# throughout this split), not at module level.

_WAVEFORMS = {'SINE', 'RAMP', 'PULSE', 'SQUARE', 'TRIANGLE', 'SAWTOOTH', 'FLICKER'}
_CHANNELS  = {
    'RED', 'GREEN', 'BLUE', 'DIM',
    'PAN', 'TILT', 'PAN_FINE', 'TILT_FINE',
    'GOBO', 'GOBO_ROT', 'GOBO2', 'GOBO2_ROT',
    'ZOOM', 'FOCUS', 'IRIS', 'SHUTTER1', 'COLOR',
    'PRISM', 'FROST', 'ANIMATION', 'CONTROL', 'MACRO', 'DIMMER',
}


def cmd_029_form_list(t0, tokens, raw):
    if t0 == 'FORM' and len(tokens) >= 2 and tokens[1] == 'LIST':
        lines = []
        for f in form_pool.forms.values():
            lines.append(f"  {f}")
        return "\n".join(lines) if lines else "form pool empty"


def cmd_030_record_form(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) >= 3 and tokens[1] == 'FORM':
        try:
            form_n = int(tokens[2])
        except ValueError:
            return f"record form: bad number '{tokens[2]}'"
        if form_n < FormPool.FIRST_CUSTOM_SLOT:
            return f"slots 1–{FormPool.FIRST_CUSTOM_SLOT - 1} are built-in read-only. Use slot {FormPool.FIRST_CUSTOM_SLOT}+."

        # Collect name tokens until first phase,value pattern
        name_parts  = []
        bp_start    = 3
        for i, tok in enumerate(tokens[3:], 3):
            if ',' in tok:
                bp_start = i
                break
            name_parts.append(tok.lower())

        name = " ".join(name_parts) if name_parts else f"form {form_n}"

        # Parse breakpoints: "0.0,0.0" "0.5,1.0" "1.0,0.0"
        breakpoints = []
        for tok in tokens[bp_start:]:
            try:
                p, v = tok.split(',')
                breakpoints.append([float(p), float(v)])
            except ValueError:
                return f"bad breakpoint '{tok}' — format: phase,value  e.g. 0.5,1.0"

        if not breakpoints:
            return "usage: record form <n> [name] <phase,value> <phase,value> ..."

        form = FormPreset(form_n, name, 'breakpoints', breakpoints=breakpoints)
        _snapshot_undo(form_pool.forms, form_n, f"record form {form_n}")
        form_pool.store(form_n, form)
        ShowFile.save_forms(form_pool)
        return f"recorded: {form}  (auto-saved)"


def cmd_033_bpm(t0, tokens, raw):
    if t0 == 'BPM' and len(tokens) >= 2:
        try:
            val = float(tokens[1])
        except ValueError:
            return f"BPM: expected a number, got '{tokens[1]}'"
        val = max(10.0, min(480.0, val))
        prog._push_undo()
        _fx_params['rate_bpm'] = val
        now = time.monotonic()
        for layer in fx_engine._layers.values():
            if layer.fx_id >= 10000:  # skip fader (cue) FX
                continue
            layer.set_rate_smooth(val, now)
        for fvals in prog.data.values():
            for ld in fvals.get('fx', []):
                ld['bpm'] = val
        if not STUDIO_HEADLESS:
            try:
                import dearpygui.dearpygui as _dpg_local
                _dpg_local.set_value("fx_rate", val)
            except Exception:
                pass
        return f"BPM → {val:.1f}"


def cmd_034_tap(t0, tokens, raw):
    if t0 == 'TAP':
        # TAP — tap-tempo; compute BPM from last 4 inter-tap intervals (<3 s window).
        # Shares _tap_times with the GUI tap button so either source is valid.
        # Updates _fx_params and running layers directly to avoid dpg.set_value
        # being called without a context (headless mode).
        _now = time.monotonic()
        _tap_times.append(_now)
        _tap_times[:] = [t for t in _tap_times if _now - t < 3.0]
        if len(_tap_times) > 5:
            _tap_times[:] = _tap_times[-5:]
        if len(_tap_times) >= 2:
            _intervals = [_tap_times[i + 1] - _tap_times[i]
                          for i in range(len(_tap_times) - 1)]
            _avg = sum(_intervals) / len(_intervals)
            _bpm = round(60.0 / _avg, 1) if _avg > 0 else 60.0
            _bpm = max(10.0, min(480.0, _bpm))
            _fx_params['rate_bpm'] = _bpm
            for _layer in fx_engine._layers.values():
                if _layer.fx_id < 10000:
                    _layer.set_rate_smooth(_bpm, _now)
            for _fvals in prog.data.values():
                for _ld in _fvals.get('fx', []):
                    _ld['bpm'] = _bpm
            if not STUDIO_HEADLESS:
                try:
                    import dearpygui.dearpygui as _dpg_l
                    _dpg_l.set_value("fx_rate", _bpm)
                except Exception:
                    pass
            return f"BPM → {_bpm:.1f}"
        return "TAP (tap again to lock BPM…)"


def cmd_035_size(t0, tokens, raw):
    if t0 == 'SIZE' and len(tokens) >= 2:
        try:
            val = float(tokens[1])
        except ValueError:
            return f"SIZE: expected a number, got '{tokens[1]}'"
        val = max(0.0, min(100.0, val))
        prog._push_undo()
        _fx_params['size'] = val
        for layer in fx_engine._layers.values():
            if layer.fx_id >= 10000:  # skip fader (cue) FX
                continue
            layer.size = val
        for fvals in prog.data.values():
            for ld in fvals.get('fx', []):
                ld['size'] = val
        if not STUDIO_HEADLESS:
            try:
                import dearpygui.dearpygui as _dpg_local
                _dpg_local.set_value("fx_size", val)
            except Exception:
                pass
        return f"size → {val:.0f}"


def cmd_036_spread(t0, tokens, raw):
    if t0 == 'SPREAD' and len(tokens) >= 2:
        try:
            val = float(tokens[1])
        except ValueError:
            return f"SPREAD: expected a number, got '{tokens[1]}'"
        val = max(0.0, min(100.0, val))
        prog._push_undo()
        _fx_params['spread'] = val
        for layer in fx_engine._layers.values():
            if layer.fx_id >= 10000:  # skip fader (cue) FX
                continue
            layer.spread = val
        for fvals in prog.data.values():
            for ld in fvals.get('fx', []):
                ld['spread'] = val
        if not STUDIO_HEADLESS:
            try:
                import dearpygui.dearpygui as _dpg_local
                _dpg_local.set_value("fx_spread", val)
            except Exception:
                pass
        return f"spread → {val:.1f}"


def cmd_037_strobe(t0, tokens, raw):
    # run_command is defined by commands/__init__.py's dispatcher,
    # which imports from this module — true circular dependency, not
    # just an ordering one. Deferred import, resolved only when this
    # function is actually called (well after all modules load).
    from __main__ import run_command
    if t0 == 'STROBE':
        t1 = tokens[1].upper() if len(tokens) > 1 else ''
        if t1 == 'CLEAR':
            return run_command("FX CLEAR DIM")
        _strobe_presets = {'SLOW': 60, 'MEDIUM': 120, 'FAST': 240}
        if t1 in _strobe_presets:
            bpm = _strobe_presets[t1]
        elif t1 and t1.replace('.', '', 1).isdigit():
            bpm = float(t1)
        else:
            bpm = 120  # default
        return run_command(f"FX PULSE DIM BPM {bpm} FIXTURE")


def cmd_038_rainbow(t0, tokens, raw):
    # run_command is defined by commands/__init__.py's dispatcher,
    # which imports from this module — true circular dependency, not
    # just an ordering one. Deferred import, resolved only when this
    # function is actually called (well after all modules load).
    from __main__ import run_command
    if t0 == 'RAINBOW':
        t1 = tokens[1].upper() if len(tokens) > 1 else ''
        if t1 == 'CLEAR':
            return run_command("FX CLEAR")
        _rb_bpm  = float(t1) if t1 and t1.replace('.','',1).isdigit() else 60.0
        t2 = tokens[2] if len(tokens) > 2 else ''
        _rb_spread = float(t2) if t2 and t2.replace('.','',1).isdigit() else 100.0
        run_command(f"FX SINE RED    BPM {_rb_bpm} SPREAD {_rb_spread} PHASE 0.0   SIZE 100")
        run_command(f"FX ADD SINE GREEN BPM {_rb_bpm} SPREAD {_rb_spread} PHASE 0.333 SIZE 100")
        run_command(f"FX ADD SINE BLUE  BPM {_rb_bpm} SPREAD {_rb_spread} PHASE 0.667 SIZE 100")
        return f"rainbow → {_rb_bpm:.0f} BPM  spread {_rb_spread:.0f}%  (3 layers R/G/B)"


def cmd_039_fx_main(t0, tokens, raw):
    if t0 == 'FX' and len(tokens) >= 2:
        sub = tokens[1]
        # Pushed once here rather than at each of this function's several
        # prog.data mutation points (FX FORM, FX COLOR, the main
        # waveform-apply path) — undo's snapshot/restore already covers FX
        # correctly since FX defs live inside prog.data itself (see
        # programmer._push_undo/.undo in models/fixtures.py); this command
        # was simply never calling it, so there was nothing to undo *to*.
        # A malformed sub-command below still wastes one undo slot on a
        # no-op snapshot (immediately identical to the one below it) —
        # accepted in exchange for not needing to track every mutation
        # site in a function this size individually.
        prog._push_undo()

        # FX FORM <n>  — set form on all running layers + store as pending in programmer
        if sub == 'FORM' and len(tokens) == 3:
            try:
                fid_n = int(tokens[2])
            except ValueError:
                return f"FX FORM: bad slot '{tokens[2]}'"
            form = form_pool.get(fid_n)
            if not form:
                return f"form {fid_n} is empty"

            # Store pending form_id in programmer so next FX command picks it up
            _fx_params['pending_form_id'] = fid_n

            changed = 0
            # Update every active programmer-preview layer live
            for fxid in _prog_fx_ids:
                layer = fx_engine._layers.get(fxid)
                if layer:
                    layer.form_id = fid_n
                    changed += 1
            # Update FX defs already in programmer data
            for vals in prog.data.values():
                for ld in vals.get('fx', []):
                    ld['form_id'] = fid_n

            if changed:
                return f"form → {form.name}  ({changed} layer(s) updated live)"
            return f"form → {form.name}  (pending — next FX command will use this form)"

        if sub == 'CLEAR':
            # FX CLEAR            → clear all FX (programmer + all running faders)
            # FX CLEAR <channel>  → clear only that channel in programmer
            # Both scope to selection when fixtures are selected.
            # 'fx' entries always live under the MASTER fixture's id
            # (never a sub-fixture's own "1.1"-style id) — resolving
            # through _resolve_fx_selection_targets() rather than using
            # each selected object's own .fixture_id directly is what
            # makes CLEAR actually find anything when the selection is
            # sub-fixtures (a bare {f.fixture_id ...} set of "1.1"/"1.2"/
            # ... never matched the "1" key the fx data was ever stored
            # under, so CLEAR silently did nothing).
            _sel_fids = ({str(fid) for fid in _resolve_fx_selection_targets()[0]}
                        if prog.selection else None)

            if len(tokens) >= 3 and tokens[2].upper() in _CHANNELS:
                ch = tokens[2].upper().lower()
                _targets = _sel_fids or set(prog.data.keys())
                for fid in _targets:
                    vals = prog.data.get(fid)
                    if vals is None:
                        continue
                    existing = vals.get('fx', [])
                    filtered = [ld for ld in existing if ld.get('channel') != ch]
                    if filtered:
                        vals['fx'] = filtered
                    else:
                        vals.pop('fx', None)
                _prog_fx_rebuild()
                _scope = f" ({len(_targets)} fixture(s))" if _sel_fids else ""
                return f"FX {ch} cleared from programmer{_scope}"

            if _sel_fids:
                # Selection active — clear programmer FX for selected fixtures only
                for fid in _sel_fids:
                    vals = prog.data.get(fid)
                    if vals:
                        vals.pop('fx', None)
                _prog_fx_rebuild()
                return f"FX cleared for {len(_sel_fids)} selected fixture(s) (programmer)"

            # No selection — global clear (programmer + all running faders)
            _prog_fx_stop()
            for vals in prog.data.values():
                vals.pop('fx', None)
            _cleared_exec = 0
            for _ex in fader_pool.faders.values():
                if _ex._fx_ids:
                    _ex._clear_fx()
                    _cleared_exec += 1
            _exec_note = f"  + {_cleared_exec} fader(s)" if _cleared_exec else ""
            return f"FX cleared (programmer{_exec_note})"

        if sub == 'LIST':
            lines = []
            # programmer FX
            prog_fx = {fid: v['fx'] for fid, v in prog.data.items()
                       if '.' not in fid and 'fx' in v}
            if prog_fx:
                lines.append("programmer FX:")
                for fid, defs in prog_fx.items():
                    for ld in defs:
                        dist = []
                        if ld.get('block_size', 1) != 1:      dist.append(f"block={ld['block_size']}")
                        if ld.get('order', 'linear') != 'linear': dist.append(f"order={ld['order']}")
                        if ld.get('direction', 'forward') != 'forward': dist.append(f"dir={ld['direction']}")
                        if ld.get('target_scope'):             dist.append(ld['target_scope'])
                        dist_s = f" [{' '.join(dist)}]" if dist else ""
                        lines.append(f"  fixture {fid}: {ld['waveform']} {ld['channel']} "
                                     f"BPM={ld.get('bpm',60)} size={ld.get('size',100)}{dist_s}")
            else:
                lines.append("programmer FX: (none)")
            # Active fader FX
            exec_fx_lines = []
            for eid, ex in sorted(fader_pool.faders.items()):
                if ex.is_active and ex._fx_ids and ex.fx_engine:
                    for fxid in ex._fx_ids:
                        layer = ex.fx_engine._layers.get(fxid)
                        if layer:
                            exec_fx_lines.append(
                                f"  fdr {eid}: {layer.waveform} {layer.channel} "
                                f"BPM={layer.rate_bpm:.0f} size={layer.size:.0f}")
            if exec_fx_lines:
                lines.append("Active fader FX:")
                lines.extend(exec_fx_lines)
            # FX pool
            if fx_pool.presets:
                lines.append("Pool:")
                for p in fx_pool.presets.values():
                    lines.append(f"  {p}")
            else:
                lines.append("Pool: (empty)")
            return "\n".join(lines)

        # fx [add] <waveform|form n|COLOR n> [channel] [bpm n] [size n] [LOW n] [SPREAD n]
        #   [group n] [dimref n] [BLOCK n] [MIRROR] [CLUSTER] [ORDER RANDOM]
        #   [DIRECTION FWD|REV|BOUNCE] [PIXEL|FIXTURE]
        #
        # Tree references:
        #   COLOR n  — drives R/G/B from Colorpreset n (waveform drives intensity of that color)
        #   GROUP n  — target only fixtures in GroupPool slot n instead of programmer selection
        #   dimref n — live size ceiling: Dimmerpreset n's level scales FX amplitude (0–1)
        #   LOW n    — floor for the oscillation range (0-100, default 0); the
        #              waveform swings between LOW and SIZE instead of 0 and
        #              SIZE, e.g. LOW 40 SIZE 70 keeps a dim/strobe sync
        #              between 40% and 70% instead of ever going fully dark.
        #   MIRROR / CLUSTER / BLOCK n / ORDER RANDOM / DIRECTION — all
        #              independent and combine freely; see the comment
        #              further down where they're parsed.
        add_mode = (sub == 'ADD')
        base_idx = 2 if add_mode else 1

        if base_idx >= len(tokens):
            return ("usage: fx [add] <waveform|form n|COLOR n> [channel] "
                    "[bpm n] [size n] [low n] [SPREAD n] [group n] [dimref n] "
                    "[BLOCK n] [MIRROR] [CLUSTER] [ORDER RANDOM] [DIRECTION FWD|REV|BOUNCE]")

        form_id  = None
        color_id = None
        waveform = tokens[base_idx]
        ch_idx   = base_idx + 1

        if waveform == 'FORM':
            try:
                form_id  = int(tokens[base_idx + 1])
                form     = form_pool.get(form_id)
                waveform = form.builtin_name or form.name.lower() if form else 'sine'
                ch_idx   = base_idx + 2
            except (IndexError, ValueError):
                return "usage: fx [add] form <n> <channel> [...]"
        elif waveform == 'COLOR':
            # FX COLOR <preset_id> — drives R/G/B channels from the preset's color
            try:
                color_id = int(tokens[base_idx + 1])
                ch_idx   = base_idx + 2
            except (IndexError, ValueError):
                return "usage: fx [add] color <preset_id> [bpm n] [size n] [group n] [dimref n]"
            waveform = 'sine'
            channel  = 'rgb'   # virtual; expanded into R/G/B at _prog_fx_start time
        elif waveform not in _WAVEFORMS:
            return f"unknown waveform '{waveform}' — use sine|ramp|pulse|square, FORM <n>, or COLOR <n>"

        if color_id is None:
            # Check if channel position is 'COLOR' (e.g. FX RAMP COLOR 3)
            if ch_idx < len(tokens) and tokens[ch_idx] == 'COLOR':
                try:
                    color_id = int(tokens[ch_idx + 1])
                    ch_idx  += 2
                except (IndexError, ValueError):
                    return "usage: fx [add] <waveform> color <preset_id>"
                waveform = waveform.lower()
                channel  = 'rgb'
            elif ch_idx >= len(tokens) or tokens[ch_idx] not in _CHANNELS:
                return (f"usage: fx [add] <waveform> red|green|blue|dim|pan|tilt|gobo|zoom|focus|… "
                        f"[bpm n] [size n] [SPREAD n]")
            else:
                channel = tokens[ch_idx]

        up = raw.upper()
        def _fx_val(key, default):
            m = _re.search(rf'\b{key}\s+([\d.]+)', up)
            return float(m.group(1)) if m else default

        bpm       = _fx_val('BPM',     _fx_params['rate_bpm'])
        size      = _fx_val('SIZE',    _fx_params['size'])
        low       = _fx_val('LOW',     0.0)
        spread    = _fx_val('SPREAD',  _fx_params['spread'])
        phase     = _fx_val('PHASE',   0.0)
        infade    = _fx_val('INFADE',  _fx_params['infade'])
        outfade   = _fx_val('OUTFADE', _fx_params['outfade'])

        def _fx_pool_id(key):
            m = _re.search(rf'\b{key}\s+(\d+)', up)
            return int(m.group(1)) if m else None

        rate_id   = _fx_pool_id('RATE')
        size_id   = _fx_pool_id('SIZEP')
        spread_id = _fx_pool_id('SPREADP')
        dim_id    = _fx_pool_id('DIMREF')   # Dimmerpreset slot as live size ceiling
        group_id  = _fx_pool_id('GROUP')    # GroupPool slot as target override

        # Distribution: BLOCK n groups adjacent targets into steps of n.
        # ORDER RANDOM shuffles step order (stable per effect); default LINEAR.
        # DIRECTION FWD|REV|BOUNCE — patch order / reversed / sweeps out-and-back.
        # PIXEL|FIXTURE picks target_scope; omit to use the per-channel default
        # (dim → whole fixtures, colour → individual pixels — see _bucket_fx_defs).
        up_tokens = up.split()

        block_m = _re.search(r'\bBLOCK\s+(\d+)', up)
        block_size = int(block_m.group(1)) if block_m else 1

        order = 'random' if 'RANDOM' in up_tokens else 'linear'

        direction = 'forward'
        dir_m = _re.search(r'\bDIRECTION\s+(\w+)', up)
        dir_word = dir_m.group(1) if dir_m else None
        if dir_word in ('REV', 'REVERSE') or 'REVERSE' in up_tokens:
            direction = 'reverse'
        elif dir_word == 'BOUNCE' or 'BOUNCE' in up_tokens:
            direction = 'bounce'
        elif dir_word in ('FWD', 'FORWARD'):
            direction = 'forward'

        # MIRROR / CLUSTER — independent, combinable distribution toggles
        # (see FXLayer's distribution comments in engine/fx.py). Distinct
        # from the bare GROUP n above, which selects the target *fixtures*
        # — these pick the chase *pattern* across whatever targets end up
        # in play, and combine freely with each other, with BLOCK n, with
        # ORDER RANDOM, and with DIRECTION: e.g.
        #   FX SINE RED BLOCK 3 MIRROR RANDOM
        # blocks of 3, folded symmetrically, then shuffled.
        mirror  = 'MIRROR'  in up_tokens
        cluster = 'CLUSTER' in up_tokens

        # Backward compat: the old single-mode "GROUPING <BLOCK|MIRROR|
        # CLUSTER|RANDOM|NONE>" still parses, translated onto today's
        # independent toggles instead of the mutually-exclusive mode it
        # used to select.
        grouping_m = _re.search(r'\bGROUPING\s+(\w+)', up)
        if grouping_m:
            _gw = grouping_m.group(1)
            if _gw == 'MIRROR':
                mirror = True
            elif _gw == 'CLUSTER':
                cluster = True
            elif _gw == 'RANDOM':
                order = 'random'
            # BLOCK / NONE need no action — already today's default state

        target_scope = None
        if 'PIXEL' in up_tokens:
            target_scope = 'pixel'
        elif 'FIXTURE' in up_tokens:
            target_scope = 'fixture'

        # Use pending form from a prior "FX FORM <n>" call if none explicit here
        if form_id is None:
            form_id = _fx_params.pop('pending_form_id', None)

        fx_def = {
            'waveform':     waveform.lower(),
            'channel':      channel.lower(),
            'bpm':          bpm,
            'size':         size,
            'low':          low,
            'spread':       spread,
            'phase_offset': phase,
            'infade':       infade,
            'outfade':      outfade,
            'form_id':      form_id,
            'rate_id':      rate_id,
            'size_id':      size_id,
            'spread_id':    spread_id,
            'dim_id':       dim_id,
            'color_id':     color_id,
            'group_id':     group_id,
            'block_size':   block_size,
            'order':        order,
            'direction':    direction,
            'mirror':       mirror,
            'cluster':      cluster,
            'target_scope': target_scope,
        }

        # Resolve target fixtures — GROUP n overrides programmer selection
        sub_indices_by_fid = {}
        if group_id is not None:
            grp = group_pool.get(group_id)
            if not grp:
                return f"group {group_id} not found"
            sel_fids = [m.fixture_id for m in grp.recall(patch)]
            if not sel_fids:
                return f"group {group_id} is empty"
        elif prog.selection:
            sel_fids, sub_indices_by_fid = _resolve_fx_selection_targets()
        else:
            sel_fids = [m.fixture_id for m in patch.all_fixtures()]

        # Write into programmer data (master entries).
        # Each fixture gets its own copy of fx_def so per-fixture edits
        # (e.g. changing BPM on just one fixture) don't bleed to others.
        # A fixture selected as only some of its own sub-fixtures (see
        # _resolve_fx_selection_targets) gets its own 'sub_indices' so
        # _bucket_fx_defs restricts targets to just those subs instead of
        # every sub-fixture on the fixture.
        for fid in sel_fids:
            entry = prog.data.setdefault(str(fid), {})
            this_def = dict(fx_def)
            if fid in sub_indices_by_fid:
                this_def['sub_indices'] = sub_indices_by_fid[fid]
            if not add_mode:
                entry['fx'] = [this_def]
            else:
                entry.setdefault('fx', []).append(this_def)

        # Live preview — rebuild ALL programmer FX so other fixtures keep their effects
        _prog_fx_rebuild()

        ref_parts = []
        if group_id  is not None: ref_parts.append(f"group:{group_id}")
        if color_id  is not None: ref_parts.append(f"color:{color_id}")
        if dim_id    is not None: ref_parts.append(f"dimref:{dim_id}")
        ref_s = f" [{', '.join(ref_parts)}]" if ref_parts else ""
        verb  = "Added FX" if add_mode else "Applied FX"
        disp_ch = "rgb" if channel == 'rgb' else channel
        lines = [f"{verb}: {waveform} {disp_ch}{ref_s} → {len(sel_fids)} fixture(s)"]
        if color_id is not None and channel == 'rgb':
            cp = color_pool.get(color_id) if color_pool else None
            if not cp:
                lines.append(f"⚠ color preset {color_id} is empty — running white until you RECORD COLOR {color_id}")
        return "\n".join(lines)


def cmd_040_record_fx(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) >= 3 and tokens[1] == 'FX':
        try:
            fx_n = int(tokens[2])
        except ValueError:
            return f"RECORD FX: bad number '{tokens[2]}'"

        # Collect unique FX defs from programmer master entries
        seen, defs = set(), []
        for fid_str, vals in prog.data.items():
            if '.' in fid_str:
                continue
            for ld in vals.get('fx', []):
                key = (ld['waveform'], ld['channel'])
                if key not in seen:
                    seen.add(key)
                    defs.append(ld)

        if not defs:
            return "RECORD FX: no FX in programmer — apply with  FX SINE RED  first"

        name = " ".join(t.lower() for t in tokens[3:]) if len(tokens) > 3 else ""
        preset = FXPreset(fx_n, name or f"FX {fx_n}")
        for ld in defs:
            _mirror, _cluster, _order = _fx_grouping_compat(ld)
            preset.add_layer(
                ld['waveform'], ld['channel'],
                bpm          = ld.get('bpm',    60.0),
                size         = ld.get('size',   100.0),
                spread       = ld.get('spread',   0.0),
                phase_offset = ld.get('phase_offset', 0.0),
                infade       = ld.get('infade', 0.0),
                outfade      = ld.get('outfade', 0.0),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
                dim_id       = ld.get('dim_id'),
                color_id     = ld.get('color_id'),
                group_id     = ld.get('group_id'),
                speed_id     = ld.get('speed_id'),
                block_size   = ld.get('block_size',      1),
                order        = _order,
                direction    = ld.get('direction','forward'),
                mirror       = _mirror,
                cluster      = _cluster,
                low          = ld.get('low', 0.0),
                target_scope = ld.get('target_scope'),
            )
        _snapshot_undo(fx_pool.presets, fx_n, f"record fx {fx_n}")
        fx_pool.store(fx_n, preset)
        ShowFile.save_fx_pool(fx_pool)
        _preset_live_push('fx', fx_n)
        return f"recorded: {preset}  (auto-saved)"


def cmd_041_fire_fx(t0, tokens, raw):
    if t0 == 'FIRE' and len(tokens) >= 3 and tokens[1] == 'FX':
        try:
            fx_n = int(tokens[2])
        except ValueError:
            return f"FIRE FX: bad number '{tokens[2]}'"
        preset = fx_pool.get(fx_n)
        if not preset:
            return f"FX preset {fx_n} not found"

        # FIRE FX n GROUP g — group override at fire time
        _re_fire = _re
        fire_grp_m = _re_fire.search(r'\bGROUP\s+(\d+)', raw.upper())
        fire_group_id = int(fire_grp_m.group(1)) if fire_grp_m else None

        sub_indices_by_fid = {}
        if fire_group_id is not None:
            grp = group_pool.get(fire_group_id)
            if not grp:
                return f"FIRE FX: group {fire_group_id} not found"
            sel_fids = [m.fixture_id for m in grp.recall(patch)]
        elif prog.selection:
            sel_fids, sub_indices_by_fid = _resolve_fx_selection_targets()
        else:
            sel_fids = [m.fixture_id for m in patch.all_fixtures()]

        # Write preset layers into programmer — channel-additive merge.
        # Layers on channels already covered by this preset are replaced;
        # layers on other channels (e.g. existing rainbow stays when adding dim) are kept.
        # For 'rgb' virtual channel, treat red/green/blue as the replaced set.
        new_channels = set()
        for ld in preset.layers:
            if ld['channel'] == 'rgb':
                new_channels.update(('red', 'green', 'blue'))
            else:
                new_channels.add(ld['channel'])

        prog._push_undo()
        for fid in sel_fids:
            entry = prog.data.setdefault(str(fid), {})
            kept  = [ld for ld in entry.get('fx', [])
                     if ld.get('channel') not in new_channels]
            fired_defs = [{**dict(ld), 'fx_preset_ref': fx_n} for ld in preset.layers]
            # Apply fire-time group override
            if fire_group_id is not None:
                for d in fired_defs:
                    d['group_id'] = fire_group_id
            # Restrict to only the sub-fixtures actually selected on this
            # fixture, if it was a partial sub-selection (see
            # _resolve_fx_selection_targets) — otherwise firing a preset
            # onto "1.1 THRU 1.10" still lit up the whole fixture.
            if fid in sub_indices_by_fid:
                for d in fired_defs:
                    d['sub_indices'] = sub_indices_by_fid[fid]
            entry['fx'] = kept + fired_defs

        _prog_fx_rebuild()

        ref_s = f" [group:{fire_group_id}]" if fire_group_id else ""
        return f"fired: {preset}{ref_s}  → {len(sel_fids)} fixture(s)"


def cmd_108_kill_fx(t0, tokens, raw):
    if t0 == 'KILL' and len(tokens) >= 2 and tokens[1] == 'FX':
        # Write fx_kill flag into programmer master data for selected (or all) fixtures.
        # The FX engine keeps running; the flag suppresses FX in the output merge.
        # CLEAR removes this flag so cue FX resumes automatically.
        # fx_kill is a master-level flag (no sub-fixture granularity is
        # meaningful for it), but the fixtures it applies to still need
        # to come from the actual selection — including a sub-fixture-
        # only selection, which used to leave `masters` empty here and
        # silently fall through to "every patched fixture", killing FX
        # rig-wide instead of just on the selected fixture.
        if prog.selection:
            _fids = _resolve_fx_selection_targets()[0]
            masters = [patch.get(fid) for fid in _fids]
            masters = [m for m in masters if m]
        else:
            masters = list(patch.all_fixtures())
        prog._push_undo()
        _prog_fx_stop()
        for master in masters:
            fid = str(master.fixture_id)
            if fid not in prog.data:
                prog.data[fid] = {}
            prog.data[fid]['fx_kill'] = True
        return (f"FX killed for {len(masters)} fixture(s) — "
                "record into cue to make permanent, or CLEAR to release")


def cmd_110_clear_fx(t0, tokens, raw):
    if t0 == 'CLEAR' and len(tokens) == 2 and tokens[1] == 'FX':
        # fx/fx_kill always live under the MASTER fixture's id — resolve
        # through _resolve_fx_selection_targets() so a sub-fixture-only
        # selection (e.g. "1.1 THRU 1.10") maps to "1", not the dead-end
        # "1.1"/"1.2"/... keys that used to make this a no-op.
        _sel_fids = ({str(fid) for fid in _resolve_fx_selection_targets()[0]}
                    if prog.selection else None)
        _targets  = _sel_fids or set(prog.data.keys())
        prog._push_undo()
        n_masters = 0
        for fid in _targets:
            if '.' in fid:
                continue  # fx_kill and fx live in master keys only
            n_masters += 1
            if fid not in prog.data:
                prog.data[fid] = {}
            vals = prog.data[fid]
            vals.pop('fx', None)
            vals['fx_kill'] = True  # explicit kill state — recordable into cues with fx_outfade
        if _sel_fids:
            _prog_fx_rebuild()  # keep FX on unselected fixtures alive
        else:
            _prog_fx_stop()
            _fx_params.pop('pending_form_id', None)
        _scope = f" ({len(_sel_fids)} fixture(s))" if _sel_fids else ""
        return f"FX kill written for {n_masters} fixture(s){_scope} — record into a cue to store"


