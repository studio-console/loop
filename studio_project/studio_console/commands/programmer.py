"""Studio Console command dispatch — PROG TIME, BLIND/LIVE/HIGHLIGHT, BLACKOUT/MASTER, CLEAR, UNDO, PROGRAMMER *.

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
from studio_console.commands._shared import _prog_fx_rebuild

from studio_console.engine.playback import (
    FadeEngine, OutputState, _resolve_cue_refs, _vfade_apply, _exec_fader_mode_hook, _stack_fire_cue,
    _stack_go, _stack_back, _stack_goto, _stack_reload,
)
from studio_console.engine.fx import (
    Waveform, FormPreset, FormPool, RatePreset, RatePool, SizePreset,
    SizePool, SpreadPreset, SpreadPool, SpeedMaster, SpeedMasterPool, FXLayer,
    FXEngine, _bucket_fx_defs, _expand_color_fx, _expand_group_fx,
)

from studio_console.drivers.network import NetworkEngine
from studio_console.drivers.midi import CCMapping, NoteMapping, MIDIEngine
from studio_console.drivers.osc import OSCEngine
from studio_console.drivers.audio import AudioEngine, AudioMapper
from studio_console.drivers.ai import AIEngine
from studio_console.show import ShowFile, _write_file, _read_file
from studio_console.commands._shared import _record_cue_into, _prog_fx_stop, _prog_fx_start, _prog_fx_rebuild

# GUIEngine hasn't been extracted yet as its own importable module —
# defined in studio_project.py, which imports this package. Deferred
# import inside each function that needs it (same pattern used
# throughout this split), not at module level.


def cmd_014_prog_time(t0, tokens, raw):
    if t0 == 'PROG' and len(tokens) >= 2 and tokens[1] == 'TIME':
        if len(tokens) == 3 and tokens[2] == 'OFF':
            _prog_time['on'] = False
            return "programmer time override OFF"
        try:
            fade_t = float(tokens[2]) if len(tokens) > 2 else None
        except ValueError:
            return "PROG TIME: usage  PROG TIME <seconds> [DELAY <seconds>]  or  OFF"
        if fade_t is None:
            return "PROG TIME: usage  PROG TIME <seconds> [DELAY <seconds>]  or  OFF"
        delay_t = 0.0
        if 'DELAY' in tokens:
            di = tokens.index('DELAY')
            try:
                delay_t = float(tokens[di + 1])
            except (IndexError, ValueError):
                return "PROG TIME: bad DELAY value"
        _prog_time['fade']  = fade_t
        _prog_time['delay'] = delay_t
        _prog_time['on']    = True
        delay_str = f"  delay {delay_t}s" if delay_t else ""
        return f"programmer time → {fade_t}s{delay_str}"


def cmd_015_prog_fade_clear(t0, tokens, raw):
    if t0 == 'PROG' and len(tokens) >= 3 and tokens[1] == 'FADE' and tokens[2] == 'CLEAR':
        n = len(prog.live_fades)
        prog.live_fades.clear()
        return f"prog fades cleared ({n} active)"


def cmd_043_snapshot(t0, tokens, raw):
    if t0 == 'SNAPSHOT' and len(tokens) >= 2:
        try:
            cue_num = float(tokens[1])
        except ValueError:
            return f"SNAPSHOT: bad cue number '{tokens[1]}'"
        stk = _active_stack()
        if not stk:
            return "SNAPSHOT: no active stack"
        cue_name = _name_after(raw, 2) or f"snapshot {cue_num}"

        cue_merged = output_state._merged_cue_layer()
        prog_layer = output_state.programmer_layer

        snapshot_data = {}
        for master in patch.all_fixtures():
            fid = str(master.fixture_id)
            pm  = prog_layer.get(fid, {})
            cm  = cue_merged.get(fid, {})
            dim = pm.get('dim', cm.get('dim'))
            if dim is not None:
                snapshot_data.setdefault(fid, {})['dim'] = float(dim)
            for sub in master.sub_fixtures.values():
                sfid = str(sub.fixture_id)
                ps   = prog_layer.get(sfid, {})
                cs_  = cue_merged.get(sfid, {})
                sub_data = {}
                for ch in sub.profile.channels:
                    val = ps.get(ch, cs_.get(ch))
                    if val is not None:
                        sub_data[ch] = float(val)
                if sub_data:
                    snapshot_data[sfid] = sub_data

        if not snapshot_data:
            return "SNAPSHOT: nothing in output — all fixtures are dark"

        cue = Cue(cue_num, cue_name)
        cue.data = snapshot_data
        stk.cues[float(cue_num)] = cue
        save_show()
        fixture_count = len({k.split('.')[0] for k in snapshot_data})
        return f"snapshot → cue {cue_num}: {cue_name}  ({fixture_count} fixtures, show saved)"


def cmd_044_blind(t0, tokens, raw):
    if t0 == 'BLIND':
        output_state.blind = True
        return "BLIND mode ON — programmer suppressed from DMX output"


def cmd_045_live(t0, tokens, raw):
    if t0 == 'LIVE':
        output_state.blind = False
        return "LIVE mode — programmer active in output"


def cmd_047_freeze(t0, tokens, raw):
    if t0 == 'FREEZE':
        off = len(tokens) > 1 and tokens[1] in ('OFF', 'RELEASE')
        if off or output_state.freeze_mode:
            output_state.freeze_mode = False
            output_state.frozen_dmx.clear()
            return "FREEZE OFF — live output restored"
        # snapshot universes present in patch
        univs = {out['universe']
                 for m in output_state.patch.all_fixtures()
                 for sub in m.sub_fixtures.values()
                 for out in sub.outputs}
        for u in univs:
            output_state.frozen_dmx[u] = output_state.get_dmx_for_universe(u)
        output_state.freeze_mode = True
        return f"FREEZE ON — output locked at current look ({len(univs)} universe(s))"


def cmd_048_solo(t0, tokens, raw):
    if t0 == 'SOLO':
        off = len(tokens) > 1 and tokens[1] in ('OFF', 'RELEASE')
        if off or (output_state.solo_mode and len(tokens) == 1):
            output_state.solo_mode = False
            output_state.solo_fids.clear()
            return "SOLO OFF — all fixtures restored to normal output"
        output_state.solo_mode = True
        output_state.solo_fids = {
            f.fixture_id for f in prog.selection
            if isinstance(f, MasterFixture)
        }
        fids = sorted(output_state.solo_fids)
        return f"SOLO ON — only fixtures {fids} pass through; others zeroed"


def cmd_049_park(t0, tokens, raw):
    # run_command is defined by commands/__init__.py's dispatcher,
    # which imports from this module — true circular dependency, not
    # just an ordering one. Deferred import, resolved only when this
    # function is actually called (well after all modules load).
    from __main__ import run_command
    if t0 == 'PARK':
        off = len(tokens) > 1 and tokens[1] in ('OFF', 'RELEASE')
        if off:
            return run_command("UNPARK")
        sel_masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if not sel_masters:
            return "PARK: select fixtures first"
        for master in sel_masters:
            # Temporarily remove from parked set so we get live output (not the old park)
            was_parked = master.fixture_id in output_state.parked_fids
            output_state.parked_fids.discard(master.fixture_id)
            univs = {out['universe'] for sub in master.all_subs() for out in sub.outputs}
            for u in univs:
                dmx_snap = output_state.get_dmx_for_universe(u)
                for sub in master.all_subs():
                    for out in sub.outputs:
                        if out['universe'] != u:
                            continue
                        for off_i, _ in enumerate(sub.profile.channels):
                            a = out['address'] + off_i
                            if 1 <= a <= 512:
                                output_state.parked_addresses.setdefault(u, {})[a] = dmx_snap[a - 1]
            output_state.parked_fids.add(master.fixture_id)
        fids = sorted(f.fixture_id for f in sel_masters)
        return f"PARK — fixture(s) {fids} frozen at current DMX output (UNPARK to release)"


def cmd_050_unpark(t0, tokens, raw):
    if t0 == 'UNPARK':
        all_mode = len(tokens) > 1 and tokens[1] == 'ALL'
        if all_mode:
            output_state.parked_fids.clear()
            output_state.parked_addresses.clear()
            return "UNPARK ALL — all fixtures released"
        sel_masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if not sel_masters:
            output_state.parked_fids.clear()
            output_state.parked_addresses.clear()
            return "UNPARK ALL — all fixtures released"
        for master in sel_masters:
            output_state.parked_fids.discard(master.fixture_id)
            for sub in master.all_subs():
                for out in sub.outputs:
                    u = out['universe']
                    for off_i in range(len(sub.profile.channels)):
                        a = out['address'] + off_i
                        output_state.parked_addresses.get(u, {}).pop(a, None)
        fids = sorted(f.fixture_id for f in sel_masters)
        return f"UNPARK — fixture(s) {fids} released from park"


def cmd_051_highlight(t0, tokens, raw):
    if t0 == 'HIGHLIGHT' or (t0 == 'HL' and len(tokens) <= 2):
        off = len(tokens) > 1 and tokens[1] == 'OFF'
        on  = len(tokens) > 1 and tokens[1] == 'ON'
        if off or (output_state.highlight_mode and not on):
            output_state.highlight_mode = False
            return "HIGHLIGHT OFF"
        else:
            output_state.highlight_mode = True
            # Every selected object's own .fixture_id, master or sub —
            # MasterFixture's is a plain int (whole fixture); SubFixture's
            # is already the "master.sub" composite string (a specific
            # pixel). Filtering to MasterFixture only (as this used to)
            # meant a sub-fixture-only selection (e.g. "1.1 THRU 1.10")
            # produced an empty set and highlighted nothing at all.
            output_state.highlight_fids = {f.fixture_id for f in prog.selection}
            fids = sorted(output_state.highlight_fids, key=str)
            return f"HIGHLIGHT ON — fixtures {fids} at full white"


def cmd_053_master(t0, tokens, raw):
    if t0 == 'MASTER' and len(tokens) >= 2:
        try:
            pct = float(tokens[1])
        except ValueError:
            return f"MASTER: bad value '{tokens[1]}' — use 0-100"
        output_state.master_level = max(0.0, min(1.0, pct / 100.0))
        return f"master → {pct:.0f}%"


def cmd_054_grandmaster(t0, tokens, raw):
    if t0 in ('GRANDMASTER', 'GM'):
        if len(tokens) == 1:
            return f"grandmaster: {output_state.master_level:.0%}"
        arg = tokens[1]
        if arg == 'FULL':
            output_state.master_level = 1.0
        elif arg == 'OUT':
            output_state.master_level = 0.0
        else:
            try:
                pct = float(arg.rstrip('%'))
                output_state.master_level = max(0.0, min(1.0, pct / 100.0))
            except ValueError:
                return f"GRANDMASTER: unrecognised value '{arg}' — use 0-100 or FULL/OUT"
        return f"grandmaster → {output_state.master_level:.0%}"


def cmd_055_blackout(t0, tokens, raw):
    if t0 == 'BLACKOUT':
        off = len(tokens) > 1 and tokens[1] == 'OFF'
        if off or output_state.master_level == 0.0:
            output_state.master_level = _blackout_saved_level[0]
            return f"BLACKOUT OFF — master restored to {output_state.master_level:.0%}"
        else:
            _blackout_saved_level[0] = output_state.master_level
            output_state.master_level = 0.0
            return "BLACKOUT ON — all output cut (BLACKOUT OFF to restore)"


def cmd_056_bbo(t0, tokens, raw):
    if t0 == 'BBO':
        if output_state.master_level > 0.0:
            _blackout_saved_level[0] = output_state.master_level
        output_state.master_level = 0.0
        return "BLACKOUT ON"


def cmd_109_clear_dmx(t0, tokens, raw):
    if t0 == 'CLEAR' and len(tokens) >= 2 and tokens[1] == 'DMX':
        univ = None
        if 'UNIVERSE' in tokens:
            ui = tokens.index('UNIVERSE')
            try: univ = int(tokens[ui + 1])
            except (IndexError, ValueError): pass
        if univ is not None:
            removed = len(output_state.direct_dmx.pop(univ, {}))
            return f"cleared {removed} direct DMX override(s) on universe {univ}"
        count = sum(len(v) for v in output_state.direct_dmx.values())
        output_state.direct_dmx.clear()
        return f"cleared {count} direct DMX override(s)"


def cmd_111_clear_len2(t0, tokens, raw):
    if t0 == 'CLEAR' and len(tokens) == 2:
        _pclear = tokens[1].upper()
        _colour_chs = {'red', 'green', 'blue', 'white', 'amber', 'warm_white', 'cool_white'}
        _param_map = {
            'COLOUR': _colour_chs,
            'COLOR':  _colour_chs,
            'RGB':    {'red', 'green', 'blue'},
            'DIM':    {'dim'},
        }
        if _pclear in _param_map:
            _chs = _param_map[_pclear]
            _is_dim = _pclear == 'DIM'
            _sel_fids = {str(f.fixture_id) for f in prog.selection} if prog.selection else None
            _targets  = _sel_fids or set(prog.data.keys())
            _n_written = 0
            for fid in _targets:
                # Colour channels live in sub-fixture keys; dim in master keys
                if _is_dim and '.' in fid:
                    continue
                if not _is_dim and '.' not in fid:
                    continue
                if fid not in prog.data:
                    prog.data[fid] = {}
                vals = prog.data[fid]
                for ch in _chs:
                    vals[ch] = 0.0 if _is_dim else 0
                    _n_written += 1
            _scope = f" ({len(_sel_fids)} fixture(s))" if _sel_fids else ""
            return f"{_pclear.title()} zeroed in programmer{_scope} — record into a cue to store"


def cmd_112_clear_len3(t0, tokens, raw):
    if t0 == 'CLEAR' and len(tokens) == 3:
        sub = tokens[1]
        try:
            slot = int(tokens[2])
        except ValueError:
            return f"CLEAR {sub}: bad slot number '{tokens[2]}'"
        if sub in ('COLOR', 'COLOUR'):
            if slot in color_pool.presets:
                del color_pool.presets[slot]
                save_show()
                return f"color preset {slot} cleared (show saved)"
            return f"color preset {slot} is already empty"
        if sub == 'DIM':
            if slot in dim_pool.presets:
                del dim_pool.presets[slot]
                save_show()
                return f"dim preset {slot} cleared (show saved)"
            return f"dim preset {slot} is already empty"
        if sub in ('GROUP', 'GRP'):
            if slot in group_pool.groups:
                del group_pool.groups[slot]
                save_show()
                return f"group {slot} cleared (show saved)"
            return f"group {slot} is already empty"
        if sub == 'FX':
            if slot in fx_pool.presets:
                del fx_pool.presets[slot]
                save_show()
                return f"FX preset {slot} cleared (show saved)"
            return f"FX preset {slot} is already empty"
        if sub == 'FORM':
            if slot < FormPool.FIRST_CUSTOM_SLOT:
                return f"form {slot} is built-in — only custom forms (slot ≥ {FormPool.FIRST_CUSTOM_SLOT}) can be cleared"
            if slot in form_pool.forms:
                del form_pool.forms[slot]
                save_show()
                return f"form {slot} cleared (show saved)"
            return f"form {slot} is already empty"
        if sub == 'RATE':
            if slot in rate_pool.presets:
                del rate_pool.presets[slot]
                save_show()
                return f"rate preset {slot} cleared (show saved)"
            return f"rate preset {slot} is already empty"
        if sub in ('SIZEP', 'SIZE'):
            if slot in size_pool.presets:
                del size_pool.presets[slot]
                save_show()
                return f"size preset {slot} cleared (show saved)"
            return f"size preset {slot} is already empty"
        if sub in ('SPREADP', 'SPREAD'):
            if slot in spread_pool.presets:
                del spread_pool.presets[slot]
                save_show()
                return f"spread preset {slot} cleared (show saved)"
            return f"spread preset {slot} is already empty"
        _clear_attr_map = {
            'POSITION': position_pool,
            'GOBO':     gobo_pool,
            'ZOOM':     zoom_pool,
            'FOCUS':    focus_pool,
            'BEAM':     beam_pool,
            'CONTROL':  control_pool,
        }
        if sub in _clear_attr_map:
            pool = _clear_attr_map[sub]
            if slot in pool.presets:
                del pool.presets[slot]
                save_show()
                return f"{sub.title()} preset {slot} cleared (show saved)"
            return f"{sub.title()} preset {slot} is already empty"


def cmd_113_clear_len1(t0, tokens, raw):
    if t0 == 'CLEAR' and len(tokens) == 1:
        result = prog.do_clear()
        if result.startswith("programmer cleared"):
            _prog_fx_stop()
        elif result == "programmer output cleared":
            _prog_fx_stop()
        return result


def cmd_114_undo(t0, tokens, raw):
    if t0 == 'UNDO':
        result = prog.undo()
        # prog.undo() only restores prog.data/.disabled/.selection — it has
        # no idea the live fx_engine layers exist. Every FX-mutating command
        # (FX ..., FX CLEAR, FIRE FX, ...) ends by calling _prog_fx_rebuild()
        # to resync fx_engine._layers from prog.data['fx'] entries; undo was
        # the one path that skipped this, so restoring prog.data to a state
        # with the FX def removed still left the old layer running live
        # (e.g. select fixtures, STROBE, Backspace — strobe kept going).
        _prog_fx_rebuild()
        return result


def cmd_115_programmer_show(t0, tokens, raw):
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] in ('SHOW', 'PRINT', 'DUMP'):
        lines = ["programmer:"]
        for fid in sorted(patch.fixtures, key=int):
            master = patch.fixtures[fid]
            m_data = prog.data.get(str(fid), {})
            subs_data = {k: v for k, v in prog.data.items()
                         if k.startswith(f"{fid}.") and v}
            if not m_data and not subs_data:
                continue
            name_s = master.name
            dim_s = (f"  Dim={m_data['dim']:.0%}" if 'dim' in m_data else "")
            lines.append(f"  [{fid}] {name_s}{dim_s}")
            for sfid, vals in sorted(subs_data.items()):
                sub_idx = sfid.split('.')[1]
                pairs = "  ".join(f"{k}={v}" for k, v in sorted(vals.items()))
                lines.append(f"       sub {sub_idx}: {pairs}")
        if len(lines) == 1:
            lines.append("  (empty)")
        return "\n".join(lines)


def cmd_116_programmer_capture(t0, tokens, raw):
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] == 'CAPTURE':
        sel_masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if not sel_masters:
            return "PROGRAMMER CAPTURE: select fixtures first"
        cue_merged = output_state._merged_cue_layer()
        prog._push_undo()
        captured = 0
        for master in sel_masters:
            fid = str(master.fixture_id)
            cm = cue_merged.get(fid, {})
            dim = cm.get('dim')
            if dim is not None:
                prog.data.setdefault(fid, {})['dim'] = float(dim)
                captured += 1
            for sub in master.all_subs():
                sfid = str(sub.fixture_id)
                cs_sub = cue_merged.get(sfid, {})
                for ch in sub.profile.channels:
                    val = cs_sub.get(ch)
                    if val is not None:
                        prog.data.setdefault(sfid, {})[ch] = int(val)
                        captured += 1
        return f"captured {captured} param(s) from live output into programmer"


def cmd_117_programmer_save(t0, tokens, raw):
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] == 'SAVE':
        try:
            slot = int(tokens[2])
        except (IndexError, ValueError):
            return "usage: programmer save <n> [name]"
        snap_name = _name_after(raw, 3) or f"snapshot {slot}"
        _prog_snapshots[slot] = {"name": snap_name, "data": copy.deepcopy(prog.data)}
        ch_count = sum(len(v) for v in prog.data.values() if v)
        return f"programmer snapshot {slot} '{snap_name}' saved ({ch_count} param(s))"


def cmd_118_programmer_load(t0, tokens, raw):
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] == 'LOAD':
        try:
            slot = int(tokens[2])
        except (IndexError, ValueError):
            return "usage: programmer load <n>"
        snap = _prog_snapshots.get(slot)
        if not snap:
            return f"programmer snapshot {slot} not found"
        prog._push_undo()
        prog.data.clear()
        prog.data.update(copy.deepcopy(snap["data"]))
        ch_count = sum(len(v) for v in prog.data.values() if v)
        return f"programmer loaded from snapshot {slot} '{snap['name']}' ({ch_count} param(s))"


def cmd_119_programmer_snapshots(t0, tokens, raw):
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] in ('SNAPSHOTS', 'SNAPS'):
        if not _prog_snapshots:
            return "no programmer snapshots saved"
        lines = ["programmer snapshots:"]
        for sl in sorted(_prog_snapshots):
            s = _prog_snapshots[sl]
            ch = sum(len(v) for v in s["data"].values() if v)
            lines.append(f"  [{sl}] {s['name']}  ({ch} param(s))")
        return "\n".join(lines)


def cmd_120_programmer_scale(t0, tokens, raw):
    if t0 == 'PROGRAMMER' and len(tokens) >= 3 and tokens[1] == 'SCALE':
        try:
            pct = float(tokens[2].rstrip('%'))
        except ValueError:
            return f"PROGRAMMER SCALE: bad value '{tokens[2]}'"
        if pct < 0 or pct > 1000:
            return "PROGRAMMER SCALE: use a percentage 0–1000"
        factor = pct / 100.0
        if not prog.data:
            return "PROGRAMMER SCALE: programmer is empty"
        prog._push_undo()
        scaled = 0
        for key, vals in prog.data.items():
            if not vals:
                continue
            if 'dim' in vals:
                vals['dim'] = max(0.0, min(1.0, vals['dim'] * factor))
                scaled += 1
            for ch in list(vals):
                if ch == 'dim':
                    continue
                vals[ch] = max(0, min(255, int(round(vals[ch] * factor))))
                scaled += 1
        return f"programmer scaled to {pct:.0f}% — {scaled} value(s) updated"


def cmd_121_programmer_stats(t0, tokens, raw):
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] in ('STATS', 'STATUS', 'INFO'):
        m_count   = sum(1 for k in prog.data if '.' not in k and prog.data[k])
        sub_count = sum(1 for k in prog.data if '.' in k and prog.data[k])
        ch_total  = sum(len(v) for v in prog.data.values() if v)
        sel_count = len(prog.selection)
        lines = [
            "programmer:",
            f"  masters touched : {m_count}",
            f"  sub-fixtures    : {sub_count}",
            f"  total params    : {ch_total}",
            f"  selection       : {sel_count} fixture(s)",
        ]
        if prog.data:
            active_fids = sorted(set(k.split('.')[0] for k in prog.data if prog.data[k]),
                                 key=lambda x: int(x) if x.isdigit() else 0)
            lines.append(f"  active fixtures : {', '.join(active_fids)}")
        return "\n".join(lines)


def cmd_122_set_default(t0, tokens, raw):
    if t0 == 'SET' and len(tokens) >= 4 and tokens[1] == 'DEFAULT':
        param = tokens[2].lower()
        raw_val = tokens[3]
        _VALID_DEFAULTS = {'dim', 'red', 'green', 'blue', 'kelvin', 'clr'}
        if param not in _VALID_DEFAULTS:
            return f"unknown default param '{param}'  (valid: dim, red, green, blue, kelvin/clr)"
        try:
            num = float(raw_val)
        except ValueError:
            return f"set default: value must be a number"
        if param == 'dim':
            num = max(0.0, min(1.0, num / 100.0 if num > 1.0 else num))
            _fixture_defaults['dim'] = num
        elif param in ('kelvin', 'clr'):
            _fixture_defaults['kelvin'] = int(num)
        else:
            _fixture_defaults[param] = int(max(0, min(255, num)))
        ShowFile.save_defaults(_fixture_defaults)
        _apply_fixture_defaults()
        return f"default {param} → {raw_val}"


def cmd_123_default(t0, tokens, raw):
    if t0 == 'DEFAULT' and len(tokens) == 1:
        if not _fixture_defaults:
            return "no defaults set  (use: set default dim 0, set default clr 5600, etc.)"
        lines = ["fixture defaults:"]
        for k, v in sorted(_fixture_defaults.items()):
            if k == 'dim':
                lines.append(f"  dim    : {int(v * 100)}%")
            elif k == 'kelvin':
                lines.append(f"  kelvin : {v}K")
            else:
                lines.append(f"  {k:<6} : {v}")
        return "\n".join(lines)


