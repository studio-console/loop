"""Studio Console command dispatch — GROUP/COLOR/DIM/attribute pools, RATE/SIZEP/SPREADP, SPEED.

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

_ATTR_POOL_MAP = {
    'POSITION': position_pool,
    'GOBO':     gobo_pool,
    'ZOOM':     zoom_pool,
    'FOCUS':    focus_pool,
    'BEAM':     beam_pool,
    'CONTROL':  control_pool,
}


def _parse_group_member_token(token, require_patched=True):
    """Parse a GROUP ADD/REMOVE token ("7" or "7.5") into a Group.members
    entry: ("master", fixture_id_int) for a whole fixture, or
    ("sub", "master.sub"_str) for a specific sub-fixture/pixel. Returns
    (entry, error_message) — error_message is None on success.
    require_patched=False skips the "must currently be in the patch"
    check, for REMOVE — a stale reference (fixture since unpatched)
    should still be removable from the group."""
    if '.' in token:
        parts = token.split('.')
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            return None, f"bad sub-fixture id '{token}'"
        m_id, s_idx = int(parts[0]), int(parts[1])
        if require_patched:
            master = patch.get(m_id)
            sub = master.get_sub(s_idx) if master else None
            if not sub:
                return None, f"sub-fixture {token} not in patch"
        return ("sub", f"{m_id}.{s_idx}"), None
    try:
        fid = int(token)
    except ValueError:
        return None, f"bad fixture id '{token}'"
    if require_patched and not patch.get(fid):
        return None, f"fixture {fid} not in patch"
    return ("master", fid), None


def cmd_074_group(t0, tokens, raw):
    if t0 == 'GROUP' and len(tokens) > 1:
        try:
            gid = int(tokens[1])
        except ValueError:
            return f"GROUP: bad id '{tokens[1]}'"
        # GROUP <n> ADD <fid|fid.sub> — add a whole fixture OR a specific
        # sub-fixture/pixel to the group (e.g. "GROUP 2 ADD 1.5")
        if len(tokens) >= 4 and tokens[2].upper() == 'ADD':
            g = group_pool.get(gid)
            if not g:
                return f"group {gid} not found"
            add_token = tokens[3]
            entry, err = _parse_group_member_token(add_token)
            if err:
                return f"GROUP ADD: {err}"
            if entry in g.members:
                return f"GROUP ADD: {add_token} already in group {gid}"
            g.members.append(entry)
            save_show()
            return f"group {gid}: added {add_token} ({len(g.members)} member(s))"

        # GROUP <n> REMOVE <fid|fid.sub> — remove a whole fixture OR a
        # specific sub-fixture/pixel from the group
        if len(tokens) >= 4 and tokens[2].upper() == 'REMOVE':
            g = group_pool.get(gid)
            if not g:
                return f"group {gid} not found"
            rm_token = tokens[3]
            entry, err = _parse_group_member_token(rm_token, require_patched=False)
            if err:
                return f"GROUP REMOVE: {err}"
            before = len(g.members)
            g.members = [e for e in g.members if e != entry]
            if len(g.members) == before:
                return f"GROUP REMOVE: {rm_token} not in group {gid}"
            save_show()
            return f"group {gid}: removed {rm_token} ({len(g.members)} member(s) remaining)"

        # GROUP <n> INFO/STATUS — show group members
        if len(tokens) >= 3 and tokens[2] in ('INFO', 'STATUS', 'SHOW'):
            g = group_pool.get(gid)
            if not g:
                return f"group {gid} not found"
            # Resolve members to names; entries are ("master", fid_int) or
            # ("sub", "master.sub"_str) tuples.
            member_strs = []
            for _type, fid in g.members:
                if _type == 'sub':
                    m_str, s_str = str(fid).split('.', 1)
                    m = patch.get(int(m_str))
                    member_strs.append(f"{fid}:{m.name}.{s_str}" if m else str(fid))
                else:
                    m = patch.get(int(fid))
                    member_strs.append(f"{fid}:{m.name}" if m else str(fid))
            return (f"group {gid}: {g.name}\n"
                    f"  members ({len(g.members)}): {', '.join(member_strs) or '(empty)'}")
        # group_pool.recall() calls prog.select(...) directly — bypasses
        # programmer's self-undoing setters entirely, so nothing was ever on
        # the undo stack to reverse a group recall. Push before, not inside
        # recall(), since a not-found group below shouldn't waste a slot.
        if group_pool.get(gid):
            prog._push_undo()
        group_pool.recall(gid, prog)
        g = group_pool.get(gid)
        return f"group {gid} recalled" if g else f"group {gid} not found"


def cmd_075_record_group(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'GROUP':
        try:
            gid = int(tokens[2])
        except ValueError:
            return f"RECORD GROUP: bad slot number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"group {gid}"
        if not prog.selection:
            return (f"RECORD GROUP: nothing selected — "
                    f"first type  1 THRU 6  (or any fixture range)  "
                    f"then  RECORD GROUP {gid} {name}")
        g = group_pool.record(gid, prog, name=name)
        if g:
            save_show()
            return f"recorded: {g}  (show saved)"
        return "RECORD GROUP: nothing selected"


def cmd_076_color(t0, tokens, raw):
    if t0 in ('COL', 'COLOR', 'COLOUR') and len(tokens) > 1:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"COLOR: bad slot number '{tokens[1]}'"
        p = color_pool.get(pid)
        if not p:
            return f"color preset {pid} is empty  (use: record color {pid} red)"
        # ColorPreset.apply() writes programmer.data[fid][...] directly and
        # calls the *fixture's* set_rgb (channels, for DMX output) — not
        # programmer's own self-undoing set_rgb — so nothing was ever
        # pushed to the undo stack for a color preset recall.
        prog._push_undo()
        p.apply(prog)
        return f"applied: {p}"


def cmd_077_record_color(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] in ('COLOR', 'COLOUR'):
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD COLOR: bad slot number '{tokens[2]}'"
        # RECORD COLOR <n> <R> <G> <B> [name]  — explicit RGB values
        _raw_num = [t for t in tokens[3:] if t.lstrip('-').replace('.','',1).isdigit()]
        if len(_raw_num) >= 3:
            try:
                er, eg, eb = int(_raw_num[0]), int(_raw_num[1]), int(_raw_num[2])
            except ValueError:
                return "RECORD COLOR: bad R/G/B values"
            _non_num = [t for t in tokens[3:] if not t.lstrip('-').replace('.','',1).isdigit()]
            name = " ".join(_non_num).title() or f"color {pid}"
            p = ColorPreset(pid, name)
            p.red, p.green, p.blue = float(er), float(eg), float(eb)
            color_pool.presets[pid] = p
            save_show()
            _preset_live_push('color', pid)
            return f"recorded: {p}  (show saved)"
        name = _name_after(raw, 3) or f"color {pid}"
        _has_rgb = any(any(ch in vals for ch in ('red', 'green', 'blue'))
                       for fid, vals in prog.data.items()
                       if '.' in fid)
        if not _has_rgb:
            return "RECORD COLOR: no RGB data in programmer  (set a colour first)"
        p = color_pool.record(pid, prog, name=name)
        save_show()
        _preset_live_push('color', pid)
        return f"recorded: {p}  (show saved)"


def cmd_078_dim(t0, tokens, raw):
    if t0 == 'DIM' and len(tokens) > 1:
        if tokens[1] == 'PRESET' and len(tokens) > 2:
            try:
                pid = int(tokens[2])
            except ValueError:
                return f"DIM PRESET: bad slot number '{tokens[2]}'"
            p = dim_pool.get(pid)
            if not p:
                return f"dim preset {pid} is empty  (use: record dim {pid} full)"
            # Same gap as ColorPreset.apply(): writes programmer.data
            # directly + the fixture's own set_dimmer, bypassing
            # programmer's self-undoing set_dimmer entirely.
            prog._push_undo()
            p.apply(prog)
            return f"applied: {p}"
        # bare DIM <val> → raw dimmer value (AT DIM <val>)
        try:
            val = float(tokens[1].rstrip('%'))
        except ValueError:
            return f"DIM: bad value '{tokens[1]}'  (use: DIM 80  or  DIM PRESET 1)"
        prog.execute(f"AT DIM {val}")
        return ""


def cmd_079_record_dim(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'DIM':
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD DIM: bad slot number '{tokens[2]}'"
        # RECORD DIM <n> [name] <level%>  — explicit percentage value
        _raw_num = [t.rstrip('%') for t in tokens[3:]
                    if t.rstrip('%').replace('.','',1).lstrip('-').isdigit()]
        if _raw_num:
            try:
                pct = float(_raw_num[0])
            except ValueError:
                return "RECORD DIM: bad level value"
            level = max(0.0, min(1.0, pct / 100.0 if pct > 1.0 else pct))
            _non_num = [t for t in tokens[3:] if not t.rstrip('%').replace('.','',1).lstrip('-').isdigit()]
            name = " ".join(_non_num).title() or f"dimmer {pid}"
            p = DimmerPreset(pid, name)
            p.level = level
            dim_pool.presets[pid] = p
            save_show()
            _preset_live_push('dim', pid)
            return f"recorded: {p}  (show saved)"
        name = _name_after(raw, 3) or f"dimmer {pid}"
        # Check if programmer has dim data before recording
        _has_dim = any('dim' in vals
                       for fid, vals in prog.data.items()
                       if '.' not in fid)
        if not _has_dim:
            return "RECORD DIM: no dimmer data in programmer  (set a dim level first)"
        p = dim_pool.record(pid, prog, name=name)
        save_show()
        _preset_live_push('dim', pid)
        return f"recorded: {p}  (show saved)"


def cmd_081_record_attr(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] in _ATTR_POOL_MAP:
        pool_key = tokens[1]
        pool     = _ATTR_POOL_MAP[pool_key]
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD {pool_key}: bad slot number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"{pool_key.title()} {pid}"
        p = pool.record(pid, prog, name=name)
        if p and p.data:
            save_show()
            _preset_live_push(pool_key.lower(), pid)
            return f"recorded: {p}  (show saved)"
        return (f"RECORD {pool_key}: no {pool_key.lower()} data in programmer "
                f"(channels: {', '.join(pool.relevant_channels)})")


def cmd_082_attr_bare(t0, tokens, raw):
    if t0 in _ATTR_POOL_MAP and len(tokens) > 1:
        pool_key = t0
        pool     = _ATTR_POOL_MAP[pool_key]
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"{pool_key}: bad slot number '{tokens[1]}'"
        p = pool.get(pid)
        if not p:
            return f"{pool_key} preset {pid} is empty  (use: record {pool_key} {pid} Name)"
        # AttributePreset.apply() does programmer.data[fid].update(...)
        # directly, same self-undoing-setter bypass as color/dim presets.
        prog._push_undo()
        p.apply(prog)
        return f"applied: {p}"


def cmd_083_rate(t0, tokens, raw):
    # run_command is defined by commands/__init__.py's dispatcher,
    # which imports from this module — true circular dependency, not
    # just an ordering one. Deferred import, resolved only when this
    # function is actually called (well after all modules load).
    from __main__ import run_command
    if t0 == 'RATE' and len(tokens) == 2:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"RATE: bad slot number '{tokens[1]}'"
        p = rate_pool.get(pid)
        if not p:
            return f"rate preset {pid} is empty — use RECORD RATE {pid} Name <bpm>"
        return run_command(f"BPM {p.bpm}")


def cmd_084_sizep(t0, tokens, raw):
    # run_command is defined by commands/__init__.py's dispatcher,
    # which imports from this module — true circular dependency, not
    # just an ordering one. Deferred import, resolved only when this
    # function is actually called (well after all modules load).
    from __main__ import run_command
    if t0 == 'SIZEP' and len(tokens) == 2:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"SIZEP: bad slot number '{tokens[1]}'"
        p = size_pool.get(pid)
        if not p:
            return f"size preset {pid} is empty — use RECORD SIZEP {pid} Name <size>"
        return run_command(f"SIZE {p.size}")


def cmd_085_spreadp(t0, tokens, raw):
    # run_command is defined by commands/__init__.py's dispatcher,
    # which imports from this module — true circular dependency, not
    # just an ordering one. Deferred import, resolved only when this
    # function is actually called (well after all modules load).
    from __main__ import run_command
    if t0 == 'SPREADP' and len(tokens) == 2:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"SPREADP: bad slot number '{tokens[1]}'"
        p = spread_pool.get(pid)
        if not p:
            return f"spread preset {pid} is empty — use RECORD SPREADP {pid} Name <spread>"
        return run_command(f"SPREAD {p.spread}")


def cmd_086_record_rate(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) >= 4 and tokens[1] == 'RATE':
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD RATE: bad slot '{tokens[2]}'"
        try:
            bpm = float(tokens[-1])
        except ValueError:
            return "RECORD RATE: last token must be BPM value  e.g. RECORD RATE 5 Strobe 240"
        name = " ".join(tokens[3:-1]).title() or f"rate {pid}"
        p = RatePreset(pid, name, bpm)
        rate_pool.store(pid, p)
        ShowFile.save_rate_pool(rate_pool)
        return f"recorded: {p}  (saved)"


def cmd_087_record_sizep(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) >= 4 and tokens[1] == 'SIZEP':
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD SIZEP: bad slot '{tokens[2]}'"
        try:
            size = float(tokens[-1])
        except ValueError:
            return "RECORD SIZEP: last token must be size value 0-100  e.g. RECORD SIZEP 4 Big 100"
        name = " ".join(tokens[3:-1]).title() or f"size {pid}"
        p = SizePreset(pid, name, size)
        size_pool.store(pid, p)
        ShowFile.save_size_pool(size_pool)
        return f"recorded: {p}  (saved)"


def cmd_088_record_spreadp(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) >= 4 and tokens[1] == 'SPREADP':
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD SPREADP: bad slot '{tokens[2]}'"
        try:
            spread = float(tokens[-1])
        except ValueError:
            return "RECORD SPREADP: last token must be spread 0-100  e.g. RECORD SPREADP 4 Wave 50"
        name = " ".join(tokens[3:-1]).title() or f"spread {pid}"
        p = SpreadPreset(pid, name, spread)
        spread_pool.store(pid, p)
        ShowFile.save_spread_pool(spread_pool)
        return f"recorded: {p}  (saved)"


def cmd_089_speed(t0, tokens, raw):
    if t0 == 'SPEED' and len(tokens) >= 3:
        try:
            sid = int(tokens[1])
        except ValueError:
            return f"SPEED: bad slot '{tokens[1]}'  (SPEED <1-{SpeedMasterPool._DEFAULT_SLOTS}> <bpm>)"
        if tokens[2] == 'NAME':
            name = " ".join(tokens[3:]).title() if len(tokens) > 3 else f"spd{sid}"
            m = speed_master_pool.get(sid)
            if not m:
                speed_master_pool.masters[sid] = SpeedMaster(sid, 120.0, name)
            else:
                m.name = name
            ShowFile.save_speed_masters(speed_master_pool)
            return f"speed master {sid} renamed → {name}"
        try:
            bpm = float(tokens[2])
        except ValueError:
            return f"SPEED: expected bpm value, got '{tokens[2]}'"
        if bpm <= 0:
            return "SPEED: bpm must be > 0"
        speed_master_pool.set_bpm(sid, bpm)
        ShowFile.save_speed_masters(speed_master_pool)
        m = speed_master_pool.get(sid)
        return f"speed master {sid} ({m.name}) → {bpm:.1f} BPM"


