"""Studio Console command dispatch — MACRO *.

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


def cmd_046_macro_main(t0, tokens, raw):
    # run_command is defined by commands/__init__.py's dispatcher,
    # which imports from this module — true circular dependency, not
    # just an ordering one. Deferred import, resolved only when this
    # function is actually called (well after all modules load).
    from __main__ import run_command
    if t0 == 'MACRO':
        t1 = tokens[1] if len(tokens) > 1 else ''
        if t1 == 'RECORD':
            try:
                slot = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: macro record <n> [name]"
            if _macro_recording["slot"] is not None:
                return f"already recording macro {_macro_recording['slot']} — MACRO STOP first"
            raw_parts = raw.split(None, 3)
            name = raw_parts[3].lower() if len(raw_parts) > 3 else f"macro {slot}"
            _macro_recording["slot"] = slot
            _macro_recording["cmds"] = []
            _macro_recording["name"] = name
            return f"MACRO {slot} '{name}' — recording started (MACRO STOP to save)"
        if t1 == 'STOP':
            slot = _macro_recording["slot"]
            if slot is None:
                return "MACRO STOP: not currently recording"
            name = _macro_recording.get("name", f"macro {slot}")
            macro_pool[slot] = {"name": name, "commands": list(_macro_recording["cmds"])}
            n_cmds = len(macro_pool[slot]["commands"])
            _macro_recording["slot"] = None
            _macro_recording["cmds"] = []
            ShowFile.save_macros(macro_pool)
            return f"MACRO {slot} '{name}' saved — {n_cmds} command(s)"
        if t1 == 'ABORT':
            if _macro_recording["slot"] is None:
                return "MACRO ABORT: not currently recording"
            slot = _macro_recording["slot"]
            _macro_recording["slot"] = None
            _macro_recording["cmds"] = []
            return f"MACRO {slot} recording discarded"
        if t1 == 'LIST':
            if not macro_pool:
                return "no macros recorded."
            lines = [f"  {s:>3}: [{len(m['commands'])} cmds] {m['name']}"
                     for s, m in sorted(macro_pool.items())]
            rec = _macro_recording["slot"]
            suffix = f"\n  (recording macro {rec}...)" if rec is not None else ""
            return "macros:\n" + "\n".join(lines) + suffix
        if t1 == 'DELETE':
            try:
                slot = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: macro delete <n>"
            if slot not in macro_pool:
                return f"MACRO DELETE: slot {slot} empty"
            del macro_pool[slot]
            ShowFile.save_macros(macro_pool)
            return f"macro {slot} deleted"
        if t1 == 'RENAME':
            try:
                slot = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: macro rename <n> <new name>"
            if slot not in macro_pool:
                return f"MACRO RENAME: slot {slot} empty"
            raw_parts = raw.split(None, 3)
            if len(raw_parts) < 4:
                return "MACRO RENAME: provide a new name"
            macro_pool[slot]["name"] = raw_parts[3].strip().lower()
            ShowFile.save_macros(macro_pool)
            return f"macro {slot} renamed to '{macro_pool[slot]['name']}'"
        # MACRO <n> — playback
        try:
            slot = int(t1)
        except ValueError:
            return f"MACRO: unknown subcommand '{t1}'"
        if slot not in macro_pool:
            return f"MACRO {slot}: empty slot"
        if slot in _macro_play_stack:
            chain = " -> ".join(str(s) for s in _macro_play_stack) + f" -> {slot}"
            return f"MACRO {slot}: blocked — recursive playback ({chain})"
        cmds = macro_pool[slot]["commands"]
        results = []
        _macro_play_stack.append(slot)
        try:
            for c in cmds:
                r = run_command(c)
                if r:
                    results.append(r)
        finally:
            _macro_play_stack.pop()
        return f"MACRO {slot} '{macro_pool[slot]['name']}' — {len(cmds)} cmd(s) played\n" + "\n".join(results)


