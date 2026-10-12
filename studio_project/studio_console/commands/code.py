"""Studio Console command dispatch — CODE *.

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

Renamed from MACRO to CODE (file was macro.py) — "macro" collided with
the real DMX "macro" channel some moving-light profiles carry (see
AttributePool("control", [..., "macro", ...]) in state.py and
AT MACRO <n> channel-setting syntax in models/fixtures.py), which was
confusing since they're unrelated concepts. Only this feature (recorded
command sequences) was renamed — the DMX channel keeps its real name.
"""

import os
import json
import time
import copy
import re as _re

from studio_console.state import (
    LIGHTFORM_CUE_MAP, STUDIO_DRY_RUN, STUDIO_HEADLESS, _NET_BIND, _NET_UNIVERSES, _active_fader,
    _active_stack, _apply_fixture_defaults, _apply_timing_edit, _attr_pools, _blackout_saved_level, _cs_loaded,
    _fader_dim, _fixture_defaults, _fx_params, _code_active, _code_recording, _make_set_speed_master,
    _midi_doc, _name_after, _on_cue_fire, _osc_cmd, _osc_fader, _osc_key,
    _preset_live_push, _prog_fx_ids, _prog_snapshots, _prog_time, _start_magenta_sine, _stop_fx,
    _stop_prog_fx_preview, _tap_times, active_fader, active_fx, ai, all_subs,
    audio_engine, audio_mapper, beam_pool, color_pool, control_pool, cs1,
    cue_back, cue_go, cue_pool, cue_reload, dim_pool, export_presets,
    fade_engine, fader_pool, flash_off, flash_on, focus_pool, form_pool,
    fx_engine, fx_pool, gobo_pool, goto_1, goto_2, goto_3,
    goto_4, goto_cue, group_pool, import_presets, library, list_shows,
    load_show_from, code_pool, midi, network, osc, output_state,
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

import threading

_DELAY_RE = _re.compile(r'(?i)^DELAY\s+(\d+)\s*$')


def _run_code_from(slot, cmds, idx, results):
    """Execute cmds[idx:] for `slot`, one at a time, until either the list
    ends or a "DELAY <ms>" step is hit.

    A DELAY step doesn't block: it schedules a threading.Timer to call
    this same function again (resuming right after the DELAY line) once
    the interval elapses, then returns immediately. This runs on whatever
    thread the CODE trigger happened on for the segment BEFORE the first
    delay (so a delay-free code still completes synchronously, in the
    calling thread, exactly as before this feature existed — no behavior
    change for the common case) — but every segment AFTER a delay runs on
    a Timer thread instead. run_command()/dpg calls already happen
    routinely from a background thread elsewhere in this app (the ~20Hz
    GUI update loop), so this isn't a new category of risk, and it's the
    only way to honor a millisecond delay without freezing the console
    for that long, which a real time.sleep() here would do.

    `results` accumulates every non-empty command result across the WHOLE
    playback (all segments) — the caller only sees the first segment's
    slice of it immediately; anything appended after that is for whoever
    inspects code_pool/logs later, not returned synchronously.

    On reaching the end of cmds, releases the slot from _code_active —
    the recursion guard, which otherwise treats a paused-on-delay code as
    still "running" for its entire lifetime (see _code_active's comment
    in state.py).
    """
    from __main__ import run_command
    i = idx
    while i < len(cmds):
        c = cmds[i]
        _dm = _DELAY_RE.match(c.strip())
        if _dm:
            ms = max(0, int(_dm.group(1)))
            i += 1
            t = threading.Timer(ms / 1000.0, _run_code_from, args=(slot, cmds, i, results))
            t.daemon = True
            t.start()
            return
        r = run_command(c)
        if r:
            results.append(r)
        i += 1
    _code_active.discard(slot)


def cmd_128_delay_info(t0, tokens, raw):
    # A bare "DELAY 500" typed directly at the command line, rather than
    # encountered as a step inside a running code's own command list
    # (which _run_code_from intercepts by pattern-matching the string
    # directly — it never reaches run_command()'s normal dispatch at all
    # for a real delay step, so this branch only exists to explain the
    # syntax when someone tries it outside that context instead of
    # falling through to "not a valid command"/fixture-selection
    # confusion).
    if t0 == 'DELAY':
        return "DELAY: only meaningful as a step inside a code's own command list (see CODE RECORD)"


def cmd_046_code_main(t0, tokens, raw):
    # run_command is defined by commands/__init__.py's dispatcher,
    # which imports from this module — true circular dependency, not
    # just an ordering one. Deferred import, resolved only when this
    # function is actually called (well after all modules load).
    from __main__ import run_command
    if t0 == 'CODE':
        t1 = tokens[1] if len(tokens) > 1 else ''
        if t1 == 'RECORD':
            try:
                slot = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: code record <n> [name]"
            if _code_recording["slot"] is not None:
                return f"already recording code {_code_recording['slot']} — CODE STOP first"
            raw_parts = raw.split(None, 3)
            name = raw_parts[3].lower() if len(raw_parts) > 3 else f"code {slot}"
            _code_recording["slot"] = slot
            _code_recording["cmds"] = []
            _code_recording["name"] = name
            return f"CODE {slot} '{name}' — recording started (CODE STOP to save)"
        if t1 == 'STOP':
            slot = _code_recording["slot"]
            if slot is None:
                return "CODE STOP: not currently recording"
            name = _code_recording.get("name", f"code {slot}")
            code_pool[slot] = {"name": name, "commands": list(_code_recording["cmds"])}
            n_cmds = len(code_pool[slot]["commands"])
            _code_recording["slot"] = None
            _code_recording["cmds"] = []
            ShowFile.save_codes(code_pool)
            return f"CODE {slot} '{name}' saved — {n_cmds} command(s)"
        if t1 == 'ABORT':
            if _code_recording["slot"] is None:
                return "CODE ABORT: not currently recording"
            slot = _code_recording["slot"]
            _code_recording["slot"] = None
            _code_recording["cmds"] = []
            return f"CODE {slot} recording discarded"
        if t1 == 'LIST':
            if not code_pool:
                return "no codes recorded."
            lines = [f"  {s:>3}: [{len(m['commands'])} cmds] {m['name']}"
                     for s, m in sorted(code_pool.items())]
            rec = _code_recording["slot"]
            suffix = f"\n  (recording code {rec}...)" if rec is not None else ""
            return "codes:\n" + "\n".join(lines) + suffix
        if t1 == 'DELETE':
            try:
                slot = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: code delete <n>"
            if slot not in code_pool:
                return f"CODE DELETE: slot {slot} empty"
            del code_pool[slot]
            ShowFile.save_codes(code_pool)
            return f"code {slot} deleted"
        if t1 == 'RENAME':
            try:
                slot = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: code rename <n> <new name>"
            if slot not in code_pool:
                return f"CODE RENAME: slot {slot} empty"
            raw_parts = raw.split(None, 3)
            if len(raw_parts) < 4:
                return "CODE RENAME: provide a new name"
            code_pool[slot]["name"] = raw_parts[3].strip().lower()
            ShowFile.save_codes(code_pool)
            return f"code {slot} renamed to '{code_pool[slot]['name']}'"
        # CODE <n> — playback
        try:
            slot = int(t1)
        except ValueError:
            return f"CODE: unknown subcommand '{t1}'"
        if slot not in code_pool:
            return f"CODE {slot}: empty slot"
        if slot in _code_active:
            return f"CODE {slot}: blocked — already running (recursive reference, directly or indirectly)"
        cmds = code_pool[slot]["commands"]
        name = code_pool[slot]["name"]
        _code_active.add(slot)
        results = []
        _run_code_from(slot, cmds, 0, results)
        if slot in _code_active:
            # _run_code_from hit a DELAY step and returned without finishing
            # — it scheduled its own continuation on a background timer
            # (see that function's docstring) rather than blocking this
            # call, so playback is still "in flight" past this point.
            return (f"CODE {slot} '{name}' — {len(results)} cmd(s) played so far, "
                    f"delayed step(s) pending (won't block the console)")
        return f"CODE {slot} '{name}' — {len(cmds)} cmd(s) played\n" + "\n".join(results)
