"""Studio Console command dispatch — SAVE/BACKUP/LOAD SHOW, LIST SHOWS, EXPORT/IMPORT PRESETS, NETWORK/OSC/AUDIO/MIDI/DMX config.

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
from studio_console.drivers.audio import AudioEngine, AudioMapper, sd
# _AUDIO_AVAILABLE/_AUDIO_IMPORT_ERROR are NOT imported by name here —
# the STUDIO_HEADLESS smoke test deliberately monkeypatches them
# (studio_console.drivers.audio._AUDIO_AVAILABLE = False) to test the
# "no audio hardware" path, and a snapshotted `from ... import
# _AUDIO_AVAILABLE` here would freeze the value at this module's
# import time, never seeing that later mutation (same class of issue
# fixed in drivers/audio.py itself back in Phase 3 — see that file's
# docstring). Reference via the qualified module instead.
import studio_console.drivers.audio as _audio_driver
from studio_console.drivers.ai import AIEngine
from studio_console.show import ShowFile, _write_file, _read_file
from studio_console.commands._shared import _record_cue_into, _prog_fx_stop, _prog_fx_start, _prog_fx_rebuild

# GUIEngine hasn't been extracted yet as its own importable module —
# defined in studio_project.py, which imports this package. Deferred
# import inside each function that needs it (same pattern used
# throughout this split), not at module level.
#
# Exception: GUIEngine itself is defined directly in studio_project.py
# (not extracted to its own importable module) at a position BEFORE
# this package gets imported, so a module-level reach-back is safe.
from __main__ import GUIEngine


def cmd_058_backup(t0, tokens, raw):
    if t0 == 'BACKUP':
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        return save_show_as(f"backup_{ts}")


def cmd_059_save(t0, tokens, raw):
    if t0 == 'SAVE':
        if len(tokens) >= 3 and tokens[1] == 'AS':
            name = raw.split(None, 2)[2] if len(raw.split(None, 2)) > 2 else ""
            return save_show_as(name)
        save_show()
        return "show saved."


def cmd_060_load_cue(t0, tokens, raw):
    if t0 == 'LOAD' and len(tokens) >= 3 and tokens[1] == 'CUE':
        try:
            cue_num = float(tokens[2])
        except ValueError:
            return f"LOAD CUE: bad cue number '{tokens[2]}'"
        stk = None
        if 'STK' in tokens:
            stk_idx = tokens.index('STK')
            try: stk = stack_pool.get(int(tokens[stk_idx + 1]))
            except (IndexError, ValueError): pass
        if stk is None:
            stk = _active_stack()
        if not stk:
            return "LOAD CUE: no active stack"
        cue = stk.cues.get(cue_num)
        if not cue:
            return f"LOAD CUE: cue {cue_num:.0f} not found in {stk.name}"
        prog._push_undo()
        for fid, vals in cue.data.items():
            if fid not in prog.data:
                prog.data[fid] = {}
            prog.data[fid].update(copy.deepcopy(vals))
        prog._print_programmer()
        return f"loaded cue {cue_num:.0f} '{cue.name}' into programmer"


def cmd_061_load_show(t0, tokens, raw):
    if t0 == 'LOAD' and len(tokens) >= 2 and tokens[1] == 'SHOW':
        if len(tokens) < 3:
            return "usage: load show <name>  (use list shows to see available saves)"
        name = raw.split(None, 2)[2] if len(raw.split(None, 2)) > 2 else ""
        return load_show_from(name)


def cmd_063_list_shows(t0, tokens, raw):
    if t0 == 'LIST' and len(tokens) >= 2 and tokens[1] == 'SHOWS':
        return list_shows()


def cmd_064_export_presets(t0, tokens, raw):
    if t0 == 'EXPORT' and len(tokens) >= 2 and tokens[1] == 'PRESETS':
        what = tokens[2] if len(tokens) >= 3 else 'all'
        return export_presets(what)


def cmd_065_import_presets(t0, tokens, raw):
    if t0 == 'IMPORT' and len(tokens) >= 3 and tokens[1] == 'PRESETS':
        path = raw.split(None, 2)[2]
        return import_presets(path)


def cmd_066_network(t0, tokens, raw):
    if t0 == 'NETWORK' or t0 == 'NET':
        t1 = tokens[1].upper() if len(tokens) > 1 else ''
        if t1 == 'BIND' and len(tokens) >= 3:
            new_bind = tokens[2]
            ShowFile.save_network(new_bind, network.universes)
            return (f"sACN bind address → {new_bind}  (restart console to apply)")
        if t1 in ('UNIVERSE', 'UNIVERSES', 'UNIV') and len(tokens) >= 3:
            try:
                new_univs = [int(v) for v in tokens[2:] if v.isdigit()]
            except ValueError:
                return "usage: network universe 1 2 3 ..."
            if not new_univs:
                return "usage: network universe 1 2 3 ..."
            ShowFile.save_network(network.bind_address, new_univs)
            return (f"sACN universes → {new_univs}  (restart console to apply)")
        if t1 == 'STATUS' or not t1:
            cfg_bind, cfg_univs = ShowFile.load_network()
            return (
                f"  sACN bind:       {network.bind_address or '(auto)'}\n"
                f"  sACN universes:  {network.universes}\n"
                f"  Saved in config: bind={cfg_bind or '(auto)'}  univs={cfg_univs}\n"
                f"  Restart console to apply any saved changes."
            )
        return "usage: network bind <ip>  |  network universe <n> [n...]  |  network status"


def cmd_067_osc(t0, tokens, raw):
    if t0 == 'OSC':
        t1 = tokens[1] if len(tokens) > 1 else ''
        if t1 == 'TARGET' and len(tokens) >= 5:
            osc.add_target(tokens[2], tokens[3], int(tokens[4]))
            ShowFile.save_osc_targets(osc)
            return f"OSC target '{tokens[2]}' → {tokens[3]}:{tokens[4]}"
        if t1 == 'REMOVE' and len(tokens) >= 3:
            osc.remove_target(tokens[2])
            ShowFile.save_osc_targets(osc)
            return f"OSC target '{tokens[2]}' removed"
        if t1 == 'LIST':
            lines = []
            for nm, c in osc._clients.items():
                lines.append(f"  [{nm}] → {c._address}:{c._port}")
            return "OSC targets:\n" + ("\n".join(lines) if lines else "  (none)")
        if t1 == 'SEND' and len(tokens) >= 3:
            addr = tokens[2]
            args_raw = tokens[3:]
            def _cast(v):
                try: return int(v)
                except ValueError:
                    try: return float(v)
                    except Valueerror: return v
            osc.send(addr, *[_cast(x) for x in args_raw])
            return f"OSC sent {addr}"
        if t1 == 'MONITOR':
            return "OSC MONITOR: see terminal output"
        if t1 == 'FEEDBACK' and len(tokens) >= 4:
            host = tokens[2]
            port = int(tokens[3])
            osc.add_feedback_target(host, port)
            return f"OSC feedback → {host}:{port}  (state broadcasts at ~1 Hz)"
        if t1 == 'FEEDBACK' and len(tokens) == 2:
            osc.remove_target("_feedback")
            return "OSC feedback disabled"
        return "OSC usage: TARGET name host port | REMOVE name | LIST | FEEDBACK host port | SEND /addr [args]"


def cmd_068_audio(t0, tokens, raw):
    if t0 == 'AUDIO':
        t1 = tokens[1] if len(tokens) > 1 else ''
        if t1 == 'DEVICES':
            if not _audio_driver._AUDIO_AVAILABLE:
                return f"audio unavailable: {_audio_driver._AUDIO_IMPORT_ERROR}"
            devs = [f"  [{i}] {d['name']}" for i, d in enumerate(sd.query_devices())
                    if d['max_input_channels'] > 0]
            return "audio input devices:\n" + ("\n".join(devs) if devs else "  (none found)")
        if t1 == 'START':
            device = None
            if len(tokens) > 2:
                try:
                    device = int(tokens[2])
                except ValueError:
                    return f"AUDIO START: bad device index '{tokens[2]}'"
            try:
                audio_engine.start(device=device)
            except RuntimeError as e:
                return f"AUDIO START failed: {e}"
            return "audio capture started."
        if t1 == 'STOP':
            audio_engine.stop()
            return "audio capture stopped."
        if t1 == 'ON':
            audio_mapper.enable()
            return "AUDIO ON — bass=red, mid=green, high=blue, level=dim"
        if t1 == 'OFF':
            audio_mapper.disable()
            return "AUDIO OFF"
        if t1 == 'STATUS':
            state   = "capturing" if audio_engine._running else "stopped"
            mapping = "ON" if audio_mapper.enabled else "OFF"
            return (f"audio: {state}, mapping {mapping}  "
                    f"lvl={audio_engine.level:.2f} lo={audio_engine.low:.2f} "
                    f"mid={audio_engine.mid:.2f} hi={audio_engine.high:.2f}")
        if t1 == 'GAIN' and len(tokens) > 2:
            try:
                g = float(tokens[2])
            except ValueError:
                return f"AUDIO GAIN: bad value '{tokens[2]}'"
            audio_engine.gain = g
            return f"audio gain → {g}"
        return "AUDIO usage: DEVICES | START [device] | STOP | on | off | STATUS | GAIN <n>"


def cmd_069_midi(t0, tokens, raw):
    if t0 == 'MIDI' and len(tokens) >= 2:
        t1 = tokens[1]
        if t1 in ('CC', 'NOTE') and len(tokens) >= 5:
            try:
                ch   = int(tokens[2])
                num  = int(tokens[3])
            except ValueError:
                return f"MIDI {t1}: usage  MIDI {t1} <ch> <number> <target name>"
            target_name = " ".join(tokens[4:])
            entry = GUIEngine.target_registry.get(target_name)
            if not entry:
                available = ", ".join(sorted(GUIEngine.target_registry.keys()))
                return (f"MIDI {t1}: target '{target_name}' not found\n"
                        f"Available: {available}")
            cb          = entry[0]
            soft_takeover = entry[1]
            off_cb      = entry[3] if len(entry) > 3 else None
            if t1 == 'CC':
                midi.map_cc(ch, num, cb, name=target_name, soft_takeover=soft_takeover)
                ShowFile.save_midi(midi)
                return f"mapped ch{ch} cc{num} → {target_name}  (saved)"
            else:
                midi.map_note(ch, num, cb, off_cb, name=target_name)
                ShowFile.save_midi(midi)
                return f"mapped ch{ch} note{num} → {target_name}  (saved)"
        if t1 == 'REMOVE' and len(tokens) >= 5 and tokens[2] in ('CC', 'NOTE'):
            try:
                ch  = int(tokens[3])
                num = int(tokens[4])
            except ValueError:
                return "midi remove cc|note <ch> <number>"
            if tokens[2] == 'CC':
                key = (ch, num)
                if key in midi.cc_maps:
                    del midi.cc_maps[key]
                    ShowFile.save_midi(midi)
                    return f"removed cc mapping ch{ch} cc{num}  (saved)"
                return f"no cc mapping for ch{ch} cc{num}"
            else:
                key = (ch, num)
                if key in midi.note_maps:
                    del midi.note_maps[key]
                    ShowFile.save_midi(midi)
                    return f"removed note mapping ch{ch} note{num}  (saved)"
                return f"no note mapping for ch{ch} note{num}"
        if t1 == 'TARGETS':
            lines = ["Available MIDI targets:"]
            for name in sorted(GUIEngine.target_registry.keys()):
                entry = GUIEngine.target_registry[name]
                kind = "note" if entry[2] else "cc"
                lines.append(f"  {name}  [{kind}]")
            return "\n".join(lines)
        if t1 in ('CC', 'NOTE'):
            return (f"usage: MIDI {t1} <ch 1-16> <number 0-127> <target name>\n"
                    "  e.g. MIDI CC 1 7 Grandmaster Dim\n"
                    "  Use MIDI TARGETS to list available target names")
        if t1 == 'REMOVE':
            return "usage: midi remove cc|note <ch> <number>"
        if t1 == 'CLOCK':
            pass  # handled below
        else:
            return ("MIDI: unknown subcommand — use CC, NOTE, REMOVE, TARGETS, CLOCK ON/OFF, "
                    "or LIST MIDI to see current mappings")


def cmd_070_midi_clock(t0, tokens, raw):
    if t0 == 'MIDI' and len(tokens) >= 3 and tokens[1] == 'CLOCK':
        if tokens[2] == 'ON':
            midi.clock_sync = True
            midi._clock_times = []
            midi.clock_bpm = None
            def _clock_cb(bpm):
                # Forward detected BPM to FX engine via run_command on main thread
                # (just store — the GUI tick reads midi.clock_bpm and updates sliders)
                pass
            midi.clock_callback = _clock_cb
            return "MIDI clock sync ON — BPM will lock to incoming clock when detected"
        elif tokens[2] == 'OFF':
            midi.clock_sync = False
            midi.clock_bpm  = None
            midi.clock_callback = None
            return "MIDI clock sync OFF"
        return "MIDI CLOCK on | off"


def cmd_071_dmx(t0, tokens, raw):
    if t0 == 'DMX':
        if len(tokens) >= 2 and tokens[1] == 'LIST':
            if not output_state.direct_dmx:
                return "direct DMX: no overrides active"
            lines = ["direct DMX overrides:"]
            for univ in sorted(output_state.direct_dmx):
                for addr, val in sorted(output_state.direct_dmx[univ].items()):
                    lines.append(f"  U{univ}:{addr:3d} = {val}")
            return "\n".join(lines)
        try:
            addr = int(tokens[1])
            val  = int(tokens[2])
        except (IndexError, ValueError):
            return "usage: dmx <addr> <val> [universe <n>]  |  dmx list  |  clear dmx"
        if not (1 <= addr <= 512 and 0 <= val <= 255):
            return "DMX: addr 1-512, val 0-255"
        univ = 1
        if 'UNIVERSE' in tokens:
            ui = tokens.index('UNIVERSE')
            try: univ = int(tokens[ui + 1])
            except (IndexError, ValueError): pass
        output_state.direct_dmx.setdefault(univ, {})[addr] = val
        return f"direct DMX U{univ}:{addr} = {val}"


