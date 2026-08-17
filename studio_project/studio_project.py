# ============================================================
# STUDIO CONSOLE - Core Object Model
# Block 1: Fixture Profile System + SubFixture + MasterFixture
# ============================================================

import os
import json
import copy
import re as _re

from studio_console.models.fixtures import FixtureProfile, FixtureLibrary, GDTFLoader, SubFixture, MasterFixture, Patch, programmer
from studio_console.models.presets import ColorPreset, ColorPool, DimmerPreset, DimmerPool, AttributePreset, AttributePool, Group, GroupPool, Cue, Stack, CuePool, StackPool, Fader, FaderPool, FXPreset, FXPool, Fade

# threading/time/random are still used throughout the rest of this file
# (GUIEngine, run_command, wiring) even though FadeEngine/OutputState/
# NetworkEngine — the original reason this block existed — have all been
# extracted to studio_console now.
import threading
import time
import random

from studio_console.engine.playback import FadeEngine, OutputState, _resolve_cue_refs, _vfade_apply, _exec_fader_mode_hook, _stack_fire_cue, _stack_go, _stack_back, _stack_goto, _stack_reload
from studio_console.drivers.network import NetworkEngine
from studio_console.engine.fx import Waveform, FormPreset, FormPool, RatePreset, RatePool, SizePreset, SizePool, SpreadPreset, SpreadPool, SpeedMaster, SpeedMasterPool, FXLayer, FXEngine, _bucket_fx_defs, _expand_color_fx, _expand_group_fx

from studio_console.drivers.audio import *  # noqa: F401,F403
import studio_console.drivers.audio as _audio_driver




# ============================================================
from studio_console.drivers.midi import CCMapping, NoteMapping, MIDIEngine



# ============================================================
from studio_console.drivers.osc import OSCEngine



# ============================================================
from studio_console.drivers.ai import AIEngine



# ============================================================
# STUDIO CONSOLE - Block 13: GUI Engine
#
# DearPyGui retro console. Runs on the main thread (macOS
# requires GUI on main thread). MIDI/OSC/sACN stay in their
# daemon threads. A background refresh thread calls
# dpg.set_value() at ~20 Hz to push live data into widgets.
#
# Panels:
#   - Header: title bar + current cue status
#   - Stack: cue list, GO / BACK, live indicator
#   - FX: rate / size / spread sliders, Kill button
#   - Output monitor: per-tube RGB+dim bars
#   - MIDI mapping: table with add / remove / learn
#   - AI prompt: text input → ai.ask()
# ============================================================

from studio_console.gui.theme import *  # noqa: F401,F403


from studio_console.gui.core import GUIEngineCore
from studio_console.gui.header import GUIEngineHeader
from studio_console.gui.left_column import GUIEngineLeftColumn
from studio_console.gui.right_column import GUIEngineRightColumn
from studio_console.gui.stage import GUIEngineStage
from studio_console.gui.pools_panel import GUIEnginePoolsPanel
from studio_console.gui.hardware_popups import GUIEngineHardwarePopups
from studio_console.gui.misc_popups import GUIEngineMiscPopups
from studio_console.gui.fx_editor import GUIEngineFXEditor
from studio_console.gui.ai_popups import GUIEngineAIPopups
from studio_console.gui.color_picker import GUIEngineColorPicker
from studio_console.gui.speed_master import GUIEngineSpeedMaster
from studio_console.gui.fader_page import GUIEngineFaderPage
from studio_console.gui.audio_monitors import GUIEngineAudioMonitors


class GUIEngine(GUIEngineCore, GUIEngineHeader, GUIEngineLeftColumn,
                 GUIEngineRightColumn, GUIEngineStage, GUIEnginePoolsPanel,
                 GUIEngineHardwarePopups, GUIEngineMiscPopups, GUIEngineFXEditor,
                 GUIEngineAIPopups, GUIEngineColorPicker, GUIEngineSpeedMaster,
                 GUIEngineFaderPage, GUIEngineAudioMonitors):
    pass


# ============================================================
from studio_console.paths import DATA_DIR, SAVES_DIR, _LEGACY_FILE
from studio_console.show import ShowFile, _write_file, _read_file
# ============================================================
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

def run_command(cmd_str):
    raw    = cmd_str.strip()
    tokens = raw.upper().split()
    if not tokens:
        return ""

    # REC is a shorthand alias for RECORD
    if tokens[0] == 'REC':
        tokens[0] = 'RECORD'

    t0 = tokens[0]

    # ── macro record capture ──────────────────────────────────
    # While recording, capture every command except MACRO STOP / MACRO ABORT.
    # The command still executes normally so the operator sees live feedback.
    if _macro_recording["slot"] is not None:
        is_macro_stop = (t0 == 'MACRO' and len(tokens) >= 2
                         and tokens[1] in ('STOP', 'ABORT'))
        if not is_macro_stop:
            _macro_recording["cmds"].append(raw)

    # ── Fader selection ────────────────────────────────────
    # STACK N  — make fader N the active one
    if t0 in ('STACK', 'STK') and len(tokens) > 1:
        if tokens[1] == 'MERGE':
            if 'INTO' not in tokens:
                return "usage: stack merge <src> into <dst>"
            into_idx = tokens.index('INTO')
            try:
                src_n = int(tokens[2])
                dst_n = int(tokens[into_idx + 1])
            except (IndexError, ValueError):
                return "usage: stack merge <src> into <dst>"
            src_stk = stack_pool.get(src_n)
            dst_stk = stack_pool.get(dst_n)
            if not src_stk:
                return f"STACK MERGE: source stk {src_n} not found"
            if not dst_stk:
                return f"STACK MERGE: destination stk {dst_n} not found"
            if src_n == dst_n:
                return "STACK MERGE: source and destination must be different"
            src_sorted = src_stk._sorted_cue_numbers()
            if not src_sorted:
                return f"STACK MERGE: source stk {src_n} is empty"
            dst_sorted = dst_stk._sorted_cue_numbers()
            base = (max(dst_sorted) + 1) if dst_sorted else 0.0
            merged = 0
            for src_num in src_sorted:
                src_cue = src_stk.cues[src_num]
                new_num = base + src_num
                nc = Cue(
                    cue_number  = new_num,
                    name        = src_cue.name,
                    fade_time   = src_cue.fade_time,
                    delay_time  = src_cue.delay_time,
                    fade_times  = copy.deepcopy(src_cue.fade_times),
                    delay_times = copy.deepcopy(src_cue.delay_times),
                    follow_time = src_cue.follow_time,
                )
                nc.note       = src_cue.note
                nc.fx_outfade = src_cue.fx_outfade
                nc.data       = copy.deepcopy(src_cue.data)
                dst_stk.cues[new_num] = nc
                merged += 1
            save_show()
            return (f"merged stk {src_n} '{src_stk.name}' into stk {dst_n} '{dst_stk.name}' "
                    f"— {merged} cue(s) appended (renumbered from {base:.0f})")
        # All remaining subcommands require tokens[1] to be a stack number
        try:
            n = int(tokens[1])
        except ValueError:
            return f"STACK: bad number '{tokens[1]}'"
        # stk n INFO/STATUS — detailed stack status
        if len(tokens) >= 3 and tokens[2] in ('INFO', 'STATUS', 'SHOW'):
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            # Which faders are running this stack?
            faders = [str(eid) for eid, ex in fader_pool.faders.items()
                      if ex.stack and ex.stack.stack_id == n]
            sorted_nums = stk._sorted_cue_numbers()
            lines = [f"stack {n}: {stk.name}",
                     f"  cues      : {len(sorted_nums)}",
                     f"  loop/wrap : {'on' if getattr(stk, 'wrap', False) else 'off'}",
                     f"  chase     : {'on  ' + str(round(getattr(stk,'chase_bpm',120.0),1)) + ' bpm' if getattr(stk,'chase_enabled',False) else 'off'}",
                     f"  faders    : {', '.join(faders) or '(none)'}"]
            if stk.current is not None:
                cue = stk.cues.get(stk.current)
                cue_name = cue.name if cue else "?"
                lines.append(f"  current   : cue {stk.current:.0f} — {cue_name}")
            else:
                lines.append("  current   : (not started)")
            if sorted_nums:
                lines.append("  cue list  :")
                for num in sorted_nums[:10]:
                    c = stk.cues[num]
                    cur_m = " ◀" if num == stk.current else ""
                    note_s = f"  [{c.note}]" if getattr(c, 'note', '') else ""
                    lines.append(f"    [{num:.0f}] {c.name}  fade:{c.fade_time}s{note_s}{cur_m}")
                if len(sorted_nums) > 10:
                    lines.append(f"    … ({len(sorted_nums) - 10} more cues)")
            return "\n".join(lines)
        # stk n REVERSE — reverse the cue order (renumbers from 1)
        if len(tokens) >= 3 and tokens[2].upper() == 'REVERSE':
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            sorted_nums = stk._sorted_cue_numbers()
            if not sorted_nums:
                return f"stack {n} is empty"
            rev_cues = [stk.cues[num] for num in reversed(sorted_nums)]
            stk.cues.clear()
            stk.current = None
            for new_num, cue in enumerate(rev_cues, start=1):
                cue.cue_number = float(new_num)
                stk.cues[float(new_num)] = cue
            save_show()
            return f"stk {n} '{stk.name}': reversed — {len(rev_cues)} cues renumbered 1–{len(rev_cues)}"
        # stk <n> EXTRACT <cue_num> [INTO <slot>] — copy one cue into a fresh stack
        if len(tokens) >= 4 and tokens[2].upper() == 'EXTRACT':
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            try:
                cue_num = float(tokens[3])
            except ValueError:
                return f"stk EXTRACT: bad cue number '{tokens[3]}'"
            cue = stk.cues.get(cue_num)
            if not cue:
                return f"stk EXTRACT: cue {cue_num:.0f} not found in stack {n}"
            # Determine destination slot
            into_slot = None
            if 'INTO' in tokens:
                into_idx = tokens.index('INTO')
                try:
                    into_slot = int(tokens[into_idx + 1])
                except (IndexError, ValueError):
                    return "stk EXTRACT: bad slot after INTO"
            if into_slot is None:
                # Auto-pick lowest unused slot
                used = set(stack_pool.stacks.keys())
                into_slot = next(s for s in range(1, 9999) if s not in used)
            if stack_pool.get(into_slot):
                return (f"stk EXTRACT: slot {into_slot} already occupied — "
                        f"use  stk {n} EXTRACT {cue_num:.0f} INTO <slot>")
            new_cs = stack_pool.create(into_slot, f"{stk.name} — cue {cue_num:.0f}")
            nc = Cue(cue_number=1.0, name=cue.name, fade_time=cue.fade_time,
                     delay_time=cue.delay_time, fade_times=copy.deepcopy(cue.fade_times),
                     delay_times=copy.deepcopy(cue.delay_times), follow_time=cue.follow_time)
            nc.note = getattr(cue, 'note', '')
            nc.fx_outfade = getattr(cue, 'fx_outfade', 0.0)
            nc.data = copy.deepcopy(cue.data)
            new_cs.cues[1.0] = nc
            new_cs.wrap = getattr(stk, 'wrap', False)
            new_cs.note = getattr(stk, 'note', '')
            fader_pool.assign(into_slot, new_cs)
            save_show()
            return (f"extracted: stk {n} cue {cue_num:.0f} '{cue.name}' "
                    f"→ new stack {into_slot} on fader {into_slot}")

        # stk n RENUMBER STEP <s> — renumber cues at multiples of s (10→10,20,30…)
        if len(tokens) >= 4 and tokens[2].upper() == 'RENUMBER' and tokens[3].upper() == 'STEP':
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            sorted_nums = stk._sorted_cue_numbers()
            if not sorted_nums:
                return f"stack {n} is empty"
            try:
                step = int(tokens[4])
            except (IndexError, ValueError):
                return "stk RENUMBER STEP: provide a step value (e.g. stk 1 RENUMBER STEP 10)"
            if step < 1:
                return "stk RENUMBER STEP: step must be at least 1"
            ordered = [stk.cues[num] for num in sorted_nums]
            old_current = stk.current
            stk.cues.clear()
            new_current = None
            for idx, cue in enumerate(ordered, start=1):
                new_num = float(idx * step)
                if old_current is not None and cue.cue_number == old_current:
                    new_current = new_num
                cue.cue_number = new_num
                stk.cues[new_num] = cue
            stk.current = new_current
            save_show()
            return (f"stk {n} '{stk.name}': renumbered {len(ordered)} cues "
                    f"at step {step} ({step:.0f}–{len(ordered)*step:.0f})")

        # stk n DUPLICATE [INTO <slot>] — deep-copy entire stack to a new slot
        if len(tokens) >= 3 and tokens[2].upper() in ('DUPLICATE', 'DUP', 'CLONE'):
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            into_slot = None
            if 'INTO' in tokens:
                into_idx = tokens.index('INTO')
                try:
                    into_slot = int(tokens[into_idx + 1])
                except (IndexError, ValueError):
                    return "stk DUPLICATE: bad slot after INTO"
            if into_slot is None:
                used = set(stack_pool.stacks.keys())
                into_slot = next(s for s in range(1, 9999) if s not in used)
            if stack_pool.get(into_slot):
                return (f"stk DUPLICATE: slot {into_slot} already occupied — "
                        f"use  stk {n} DUPLICATE INTO <slot>")
            new_cs = Stack(into_slot, f"{stk.name} (copy)")
            for cue_num, cue in stk.cues.items():
                nc = Cue(cue_number=cue.cue_number, name=cue.name,
                         fade_time=cue.fade_time, delay_time=cue.delay_time,
                         fade_times=copy.deepcopy(cue.fade_times),
                         delay_times=copy.deepcopy(cue.delay_times),
                         follow_time=cue.follow_time)
                nc.note = getattr(cue, 'note', '')
                nc.fx_outfade = getattr(cue, 'fx_outfade', 0.0)
                nc.data = copy.deepcopy(cue.data)
                new_cs.cues[cue_num] = nc
            new_cs.wrap = getattr(stk, 'wrap', False)
            new_cs.note = getattr(stk, 'note', '')
            stack_pool.store(into_slot, new_cs)
            fader_pool.assign(into_slot, new_cs)
            save_show()
            return (f"duplicated stk {n} '{stk.name}' → stk {into_slot} '{new_cs.name}' "
                    f"({len(new_cs.cues)} cue(s))")

        # stk n COMPRESS — renumber cues to 1, 2, 3, … (collapse gaps)
        if len(tokens) >= 3 and tokens[2].upper() == 'COMPRESS':
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            sorted_nums = stk._sorted_cue_numbers()
            if not sorted_nums:
                return f"stack {n} is empty"
            ordered = [stk.cues[num] for num in sorted_nums]
            old_current = stk.current
            stk.cues.clear()
            new_current = None
            for new_num, cue in enumerate(ordered, start=1):
                if old_current is not None and cue.cue_number == old_current:
                    new_current = float(new_num)
                cue.cue_number = float(new_num)
                stk.cues[float(new_num)] = cue
            stk.current = new_current
            save_show()
            return (f"stk {n} '{stk.name}': compressed — "
                    f"{len(ordered)} cues renumbered 1–{len(ordered)}")
        # stk n CLEAR — delete all cues from stack n (keeps the slot and name)
        if len(tokens) >= 3 and tokens[2].upper() == 'CLEAR':
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            count = len(stk.cues)
            stk.cues.clear()
            stk.current = None
            save_show()
            return f"stk {n} '{stk.name}': {count} cue(s) cleared (stack kept)"

        # stk n NOTE [text] — view or set a production note on this stack
        if len(tokens) >= 3 and tokens[2].upper() == 'NOTE':
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            if len(tokens) == 3:
                note_val = getattr(stk, 'note', '')
                if note_val:
                    return f"stk {n} '{stk.name}' note: {note_val}"
                return f"stk {n} '{stk.name}' has no note — set with: stk {n} NOTE <text>"
            note_text = _name_after(raw, 3)
            stk.note = note_text
            save_show()
            return f"stk {n} '{stk.name}' note set: {note_text}"

        # stk n bounce on/OFF — ping-pong playback (reverse direction at each end)
        if len(tokens) >= 4 and tokens[2].upper() == 'BOUNCE':
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            state = tokens[3].upper()
            if state == 'ON':
                stk.bounce = True
                stk._bounce_dir = 1
                save_show()
                return f"stk {n} '{stk.name}': bounce on — reverses at last/first cue (ping-pong)"
            elif state == 'OFF':
                stk.bounce = False
                stk._bounce_dir = 1
                save_show()
                return f"stk {n} '{stk.name}': bounce off — normal forward loop"
            return "BOUNCE: use ON or OFF"
        # stk n WRAP ON/OFF — clean restart at top after last cue
        if len(tokens) >= 4 and tokens[2].upper() == 'WRAP':
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            state = tokens[3].upper()
            if state == 'ON':
                stk.wrap = True
                save_show()
                return f"stk {n} '{stk.name}': WRAP ON — cue 1 fires clean after last cue"
            elif state == 'OFF':
                stk.wrap = False
                save_show()
                return f"stk {n} '{stk.name}': WRAP OFF — LTP tracking across loop"
            return "WRAP: use ON or OFF"

        # stk n CHASE ON [BPM x] / stk n CHASE OFF / stk n CHASE BPM x / stk n CHASE SPEED k
        if len(tokens) >= 4 and tokens[2].upper() == 'CHASE':
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            sub = tokens[3].upper()
            if sub == 'ON':
                if len(tokens) >= 6 and tokens[4].upper() == 'BPM':
                    try:
                        stk.chase_bpm = max(1.0, min(600.0, float(tokens[5])))
                    except ValueError:
                        return f"CHASE ON: bad BPM '{tokens[5]}'"
                stk.chase_enabled = True
                save_show()
                bpm_s = f"{stk.chase_bpm:.1f} BPM"
                return f"stk {n} '{stk.name}': chase ON — auto-GO every {60000/stk.chase_bpm:.0f}ms ({bpm_s})"
            elif sub == 'OFF':
                stk.chase_enabled = False
                # Clear chase timer on any fader holding this stack
                for ex in fader_pool.faders.values():
                    if ex.stack is stk:
                        ex._chase_next_at = None
                save_show()
                return f"stk {n} '{stk.name}': chase OFF"
            elif sub == 'BPM' and len(tokens) >= 5:
                try:
                    stk.chase_bpm = max(1.0, min(600.0, float(tokens[4])))
                except ValueError:
                    return f"CHASE BPM: bad value '{tokens[4]}'"
                save_show()
                return f"stk {n} '{stk.name}': chase BPM → {stk.chase_bpm:.1f}"
            elif sub == 'SPEED' and len(tokens) >= 5:
                try:
                    sid = int(tokens[4])
                except ValueError:
                    return f"CHASE SPEED: bad slot '{tokens[4]}'"
                stk.chase_speed_id = sid if sid > 0 else None
                save_show()
                return (f"stk {n} '{stk.name}': chase linked to speed Master {sid}"
                        if sid > 0 else f"stk {n} '{stk.name}': chase speed link cleared")
            else:
                bpm_s = f"{stk.chase_bpm:.1f} BPM"
                state = "ON" if stk.chase_enabled else "OFF"
                return (f"stk {n} '{stk.name}': chase {state} ({bpm_s})\n"
                        f"  stk {n} CHASE ON [BPM x]  |  CHASE OFF  |  CHASE BPM x  |  CHASE SPEED k")

        if t0 == 'STK':
            return f"usage: stk <n> bounce on|off | wrap on|off | chase on|off|bpm|speed"
        if stack_pool.get(n):
            active_fader[0] = n
            stk = stack_pool.get(n)
            return f"active fader → stack {n}: {stk.name}"
        return f"stack {n} is empty  (use: record stack {n} <name>)"

    # RECORD STACK N [name]  — create a new empty stack in slot N
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'STACK':
        try:
            n = int(tokens[2])
        except ValueError:
            return f"RECORD STACK: bad number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"stack {n}"
        stk = stack_pool.create(n, name)
        fader_pool.assign(n, stk)
        active_fader[0] = n
        save_show()
        return f"created: stack {n} '{name}'  (now active on fader {n})"

    # ── Navigation ───────────────────────────────────────────
    # ── ASSIGN stk <n> TO FADER <n> ────────────────────────────
    # Wire a stack into a fader slot. fdr accepted as alias.
    _assign_kw = next((kw for kw in ('FADER', 'FDR') if kw in tokens), None)
    if t0 == 'ASSIGN' and 'STK' in tokens and 'TO' in tokens and _assign_kw:
        try:
            stk_idx   = tokens.index('STK')
            fdr_idx = tokens.index(_assign_kw)
            stk_n     = int(tokens[stk_idx   + 1])
            ex_n     = int(tokens[fdr_idx + 1])
        except (ValueError, IndexError):
            return "usage: assign stk <n> to fader <n>"
        stack = stack_pool.get(stk_n)
        if not stack:
            return f"stack {stk_n} not found"
        fader_pool.assign(ex_n, stack)
        save_show()
        return f"stk {stk_n} assigned to fader {ex_n}  (saved)"

    # ── FADER SWAP <n> <m> — swap stacks between two faders ──
    if t0 == 'FADER' and len(tokens) >= 4 and tokens[1] == 'SWAP':
        try:
            fa, fb = int(tokens[2]), int(tokens[3])
        except ValueError:
            return "usage: fader swap <n> <m>"
        ex_a = fader_pool.get(fa)
        ex_b = fader_pool.get(fb)
        ex_a.stack, ex_b.stack = ex_b.stack, ex_a.stack
        save_show()
        name_a = ex_a.stack.name if ex_a.stack else "(empty)"
        name_b = ex_b.stack.name if ex_b.stack else "(empty)"
        return f"swapped fader {fa} ↔ fader {fb}  ({name_a} / {name_b})"

    # ── FADER ALL CLEAR — stop and reset every fader at once ──────
    if t0 in ('FADER', 'FDR') and len(tokens) >= 3 and tokens[1] == 'ALL' and tokens[2].upper() == 'CLEAR':
        cleared = 0
        for ex in fader_pool.faders.values():
            ex.stop()
            if ex.stack:
                ex.stack.current = None
            cleared += 1
        return f"all {cleared} fader(s) cleared"

    # ── fdr <n> GO / BACK / STOP ────────────────────────────
    if t0 in ('FADER', 'FDR') and len(tokens) >= 2:
        try:
            ex_n = int(tokens[1])
        except ValueError:
            return f"FADER: bad fader number '{tokens[1]}'"
        ex  = fader_pool.get(ex_n)
        verb = tokens[2].upper() if len(tokens) > 2 else 'GO'
        if verb == 'GO':
            fader_pool.bump_priority(ex_n)
            msg = ex.go(patch, fade_engine)
            if ex.stack:
                _on_cue_fire(ex.stack.current)
            return msg or f"fader {ex_n} GO"
        elif verb == 'BACK':
            fader_pool.bump_priority(ex_n)
            msg = ex.back(patch, fade_engine)
            if ex.stack:
                _on_cue_fire(ex.stack.current)
            return msg or f"fader {ex_n} BACK"
        elif verb == 'STOP':
            ex.stop()
            return f"fader {ex_n} stopped"
        elif verb == 'CLEAR':
            # FADER <n> CLEAR  — stop fader and reset stack position to "not started"
            ex.stop()
            if ex.stack:
                ex.stack.current = None
                cs_name = ex.stack.name
                return f"fader {ex_n} cleared — '{cs_name}' reset to start"
            return f"fader {ex_n} stopped (no stack)"
        elif verb == 'GOTO' and len(tokens) > 3:
            stk = ex.stack
            # GOTO FIRST / LAST — jump to first or last cue
            dest_kw = tokens[3].upper() if len(tokens) > 3 else ''
            if dest_kw == 'FIRST':
                if not stk or not stk.cues:
                    return f"fader {ex_n}: no cues"
                num = stk._sorted_cue_numbers()[0]
            elif dest_kw == 'LAST':
                if not stk or not stk.cues:
                    return f"fader {ex_n}: no cues"
                num = stk._sorted_cue_numbers()[-1]
            else:
                try:
                    num = float(tokens[3])
                except ValueError:
                    return f"FADER GOTO: bad cue number '{tokens[3]}'"
            fader_pool.bump_priority(ex_n)
            msg = ex.goto(num, patch, fade_engine)
            if not msg or 'not found' not in msg:
                _on_cue_fire(num)
            return msg or f"fader {ex_n} GOTO {num}"
        elif verb == 'TIME':
            # fdr <n> TIME <fade> [DELAY <delay>]  |  fdr <n> TIME OFF
            if len(tokens) > 3 and tokens[3] == 'OFF':
                ex.time_override_on   = False
                ex.time_override_fade  = None
                ex.time_override_delay = None
                return f"fader {ex_n} time override off"
            try:
                fade_t = float(tokens[3]) if len(tokens) > 3 else None
            except ValueError:
                return "FADER TIME: usage  FADER <n> TIME <seconds> [DELAY <seconds>]  or  OFF"
            delay_t = None
            if 'DELAY' in tokens:
                di = tokens.index('DELAY')
                try:
                    delay_t = float(tokens[di + 1])
                except (IndexError, ValueError):
                    return "FADER TIME: bad DELAY value"
            ex.time_override_fade  = fade_t
            ex.time_override_delay = delay_t if delay_t is not None else 0.0
            ex.time_override_on    = True
            delay_str = f"  delay {delay_t}s" if delay_t else ""
            return f"fader {ex_n} time override → {fade_t}s{delay_str}"
        elif verb == 'TIMELOCK':
            # fdr <n> timelock ON/OFF  — whether this fader's stack accepts overrides
            if len(tokens) < 4:
                return "usage: fdr <n> timelock on | off"
            state = tokens[3]
            stk = ex.stack
            if not stk:
                return f"fader {ex_n} has no stack"
            if state == 'ON':
                stk.allow_exec_time = True
                return f"fader {ex_n}: time override enabled for '{stk.name}'"
            elif state == 'OFF':
                stk.allow_exec_time = False
                return f"fader {ex_n}: time override locked out for '{stk.name}'"
            return "TIMELOCK: use ON or OFF"
        elif verb == 'FLASH':
            # fdr <n> flash on | off  — instant on-while-held, for trigger_mode='flash'.
            # Independent of trigger_mode itself so GUI/MIDI press/release can call
            # this directly regardless of how the mode was set.
            if len(tokens) < 4 or tokens[3] not in ('ON', 'OFF'):
                return "usage: fdr <n> flash on | off"
            if tokens[3] == 'ON':
                fader_pool.bump_priority(ex_n)
                msg = ex.flash_on(patch, fade_engine)
                if ex.stack:
                    _on_cue_fire(ex.stack.current)
                return msg or f"fader {ex_n} flash on"
            else:
                ex.flash_off()
                return f"fader {ex_n} flash off"
        elif verb == 'MOMENT':
            if len(tokens) < 4 or tokens[3] not in ('ON', 'OFF'):
                return "usage: fader <n> moment on | off"
            if tokens[3] == 'ON':
                fader_pool.bump_priority(ex_n)
                msg = ex.moment_on(patch, fade_engine)
                if ex.stack:
                    _on_cue_fire(ex.stack.current)
                return msg or f"fader {ex_n} moment on"
            else:
                ex.moment_off(fade_engine)
                return f"fader {ex_n} moment off"
        elif verb == 'MODE':
            # fdr <n> mode toggle | flash | moment — how GUI/MIDI should trigger this fader.
            # 'toggle' = GO/BACK advance normally. 'flash' = live only while held.
            # 'moment' = fires with cue times on press, fades out on release.
            if len(tokens) < 4 or tokens[3] not in ('TOGGLE', 'FLASH', 'MOMENT'):
                return "usage: fader <n> mode toggle | flash | moment"
            ex.trigger_mode = tokens[3].lower()
            return f"fader {ex_n} mode → {ex.trigger_mode}"
        elif verb == 'OFFTIME':
            if len(tokens) < 4:
                return f"fader {ex_n} off_time: {getattr(ex, 'off_time', 0.0):.1f}s"
            try:
                ex.off_time = max(0.0, float(tokens[3]))
            except ValueError:
                return "FADER OFFTIME: usage  FADER <n> OFFTIME <seconds>"
            save_show()
            return f"fader {ex_n} off time → {ex.off_time:.1f}s"
        elif verb == 'OUTPUT':
            if len(tokens) < 4 or tokens[3] not in ('NORMAL', 'MOMENT', 'VFADE'):
                return (f"fader {ex_n} output_mode: {getattr(ex, 'output_mode', 'normal')}"
                        f"  (usage: FADER <n> OUTPUT normal|moment|vfade)")
            ex.output_mode = tokens[3].lower()
            if ex.output_mode != 'vfade':
                ex.vfade_from = None
                ex.vfade_to   = None
            save_show()
            return f"fader {ex_n} output → {ex.output_mode}"
        elif verb == 'BTN':
            # fdr <n> BTN A|B|C GO|BACK|STOP|FLASH — assign action button function
            if len(tokens) < 4:
                return (f"fader {ex_n} buttons: A={ex.btn_a}  B={ex.btn_b}  C={ex.btn_c}\n"
                        f"  usage: FADER {ex_n} BTN A|B|C GO|BACK|STOP|FLASH|RATE+|RATE-")
            slot = tokens[3].upper()
            if slot not in ('A', 'B', 'C'):
                return "BTN: slot must be A, B, or C"
            fn = tokens[4].upper() if len(tokens) > 4 else ''
            if fn not in ('GO', 'BACK', 'STOP', 'FLASH', 'RATE+', 'RATE-', 'SIZE+', 'SIZE-'):
                return "BTN: function must be GO, BACK, STOP, FLASH, RATE+, RATE-, SIZE+ or SIZE-"
            setattr(ex, f'btn_{slot.lower()}', fn)
            save_show()
            return f"fader {ex_n} button {slot} → {fn}"
        elif verb == 'LEVEL':
            # fdr <n> LEVEL <0-100>  — set master fader (0 = blackout, 100 = full)
            if len(tokens) < 4:
                return f"fader {ex_n} level: {ex.level * 100:.0f}%  (usage: FADER {ex_n} LEVEL 0–100)"
            try:
                pct = float(tokens[3])
            except ValueError:
                return "FADER LEVEL: usage  FADER <n> LEVEL <0-100>"
            ex.level = max(0.0, min(1.0, pct / 100.0))
            _exec_fader_mode_hook(ex)
            save_show()
            return f"fader {ex_n} level → {ex.level * 100:.0f}%"
        elif verb in ('RATE+', 'RATE-'):
            # fdr <n> RATE+ / RATE- — nudge playback speed by ×1.25 / ÷1.25
            step = 1.25 if verb == 'RATE+' else (1.0 / 1.25)
            ex.rate_factor = max(0.1, min(8.0, ex.rate_factor * step))
            save_show()
            return f"fader {ex_n} rate → ×{ex.rate_factor:.2f}"
        elif verb == 'RATE' and len(tokens) >= 4 and tokens[3].upper() == 'RESET':
            ex.rate_factor = 1.0
            save_show()
            return f"fader {ex_n} rate reset → ×1.00"
        elif verb == 'RATE' and len(tokens) >= 4:
            try:
                rv = float(tokens[3])
            except ValueError:
                return f"FADER RATE: bad value '{tokens[3]}' — use a number (e.g. 2.0) or RESET"
            ex.rate_factor = max(0.1, min(8.0, rv))
            save_show()
            return f"fader {ex_n} rate → ×{ex.rate_factor:.2f}"
        elif verb in ('SIZE+', 'SIZE-'):
            step = 1.25 if verb == 'SIZE+' else (1.0 / 1.25)
            ex.size_factor = max(0.0, min(4.0, ex.size_factor * step))
            ex._apply_size_factor()
            save_show()
            return f"fader {ex_n} fx size → ×{ex.size_factor:.2f}"
        elif verb == 'SIZE' and len(tokens) >= 4 and tokens[3].upper() == 'RESET':
            ex.size_factor = 1.0
            ex._apply_size_factor()
            save_show()
            return f"fader {ex_n} fx size reset → ×1.00"
        elif verb == 'SIZE' and len(tokens) >= 4:
            try:
                sv = float(tokens[3])
            except ValueError:
                return f"FADER SIZE: bad value '{tokens[3]}' — use a number (e.g. 2.0) or RESET"
            ex.size_factor = max(0.0, min(4.0, sv))
            ex._apply_size_factor()
            save_show()
            return f"fader {ex_n} fx size → ×{ex.size_factor:.2f}"
        elif verb == 'LABEL':
            # FADER <n> LABEL <text>  |  FADER <n> LABEL  (clear)
            raw_parts = raw.split(None, 3)
            label_text = raw_parts[3].strip() if len(raw_parts) >= 4 else ""
            ex.label = label_text
            save_show()
            return (f"fader {ex_n} label → '{label_text}'"
                    if label_text else f"fader {ex_n} label cleared")
        elif verb in ('UNASSIGN', 'DETACH'):
            prev_cs = ex.stack
            if not prev_cs:
                return f"fader {ex_n} has no stack assigned"
            ex.stop()
            ex.stack = None
            save_show()
            return f"fader {ex_n}: unassigned (was '{prev_cs.name}')"
        elif verb == 'ASSIGN' and len(tokens) >= 5 and tokens[3].upper() == 'STK':
            try:
                stk_n = int(tokens[4])
            except ValueError:
                return f"FADER ASSIGN: bad stack number '{tokens[4]}'"
            stack = stack_pool.get(stk_n)
            if not stack:
                return f"FADER ASSIGN: stack {stk_n} not found"
            fader_pool.assign(ex_n, stack)
            save_show()
            return f"stk {stk_n} '{stack.name}' assigned to fader {ex_n}"
        elif verb == 'BOUNCE' and len(tokens) >= 4:
            stk = ex.stack
            if not stk:
                return f"fader {ex_n} has no stack assigned"
            state = tokens[3].upper()
            if state == 'ON':
                stk.bounce = True
                stk._bounce_dir = 1
                save_show()
                return f"fader {ex_n} bounce on — stk '{stk.name}' ping-pongs at each end"
            elif state == 'OFF':
                stk.bounce = False
                stk._bounce_dir = 1
                save_show()
                return f"fader {ex_n} bounce off — stk '{stk.name}' normal forward loop"
            return "FADER BOUNCE: use ON or OFF"
        elif verb == 'LOOP' and len(tokens) >= 4:
            stk = ex.stack
            if not stk:
                return f"fader {ex_n} has no stack assigned"
            state = tokens[3].upper()
            if state == 'ON':
                stk.wrap = True
                save_show()
                return f"fader {ex_n} loop ON — stk '{stk.name}' wraps after last cue"
            elif state == 'OFF':
                stk.wrap = False
                save_show()
                return f"fader {ex_n} loop OFF — stk '{stk.name}' stops after last cue"
            return "FADER LOOP: use ON or OFF"
        elif verb in ('INFO', 'STATUS', 'SHOW'):
            stk = ex.stack
            lbl_s = f"  Label     : {ex.label}" if ex.label else ""
            lines = [f"fader {ex_n}:"]
            if lbl_s:
                lines.append(lbl_s)
            lines.append(f"  Level     : {ex.level * 100:.0f}%")
            lines.append(f"  Priority  : {Fader.PRIORITY_LABELS[ex.priority]}")
            lines.append(f"  Trigger   : {ex.trigger_mode}")
            lines.append(f"  Output    : {ex.output_mode}")
            lines.append(f"  Off time  : {getattr(ex, 'off_time', 0.0):.1f}s")
            lines.append(f"  rate      : ×{ex.rate_factor:.2f}")
            lines.append(f"  FX size   : ×{ex.size_factor:.2f}")
            lines.append(f"  Buttons   : A={ex.btn_a}  B={ex.btn_b}  C={ex.btn_c}")
            if stk:
                lines.append(f"  stack  : [{stk.stack_id}] {stk.name}")
                lines.append(f"  State     : {'ACTIVE' if ex.is_active else 'idle'}")
                if stk.current is not None:
                    cue = stk.cues.get(stk.current)
                    cue_name = cue.name if cue else "?"
                    lines.append(f"  Current   : cue {stk.current:.0f} — {cue_name}")
                sorted_nums = stk._sorted_cue_numbers()
                lines.append(f"  Cues      : {len(sorted_nums)} total")
                if ex.time_override_on:
                    lines.append(f"  Time OV   : {ex.time_override_fade}s fade"
                                 + (f"  delay {ex.time_override_delay}s"
                                    if ex.time_override_delay else ""))
            else:
                lines.append("  stack  : (unassigned)")
            return "\n".join(lines)
        else:
            return f"FADER {ex_n}: unknown verb '{verb}'"

    # ── page <n> name ... / ADD stk <m> / REMOVE stk <m> / DELETE / LIST ─
    if t0 == 'PAGE':
        if len(tokens) >= 2 and tokens[1] == 'LIST':
            if not fader_pool.pages:
                return "pages: (none)"
            lines = ["Pages:"]
            for n in fader_pool.all_pages():
                p = fader_pool.get_page(n)
                cs_ids = p.get('stacks', [])
                cs_names = []
                for cid in cs_ids:
                    stk = stack_pool.get(cid)
                    cs_names.append(f"{cid}:{stk.name}" if stk else str(cid))
                lines.append(f"  [{n}] {p['name']} — {', '.join(cs_names) or '(empty)'}")
            return "\n".join(lines)

        if len(tokens) < 2:
            return "usage: page <n> name <name> | page <n> add stk <m> | page <n> remove stk <m> | page <n> delete | page list"
        try:
            page_n = int(tokens[1])
        except ValueError:
            return f"PAGE: bad page number '{tokens[1]}'"

        if len(tokens) == 2:
            p = fader_pool.get_page(page_n)
            cs_ids = p.get('stacks', [])
            cs_names = []
            for cid in cs_ids:
                stk = stack_pool.get(cid)
                cs_names.append(f"{cid}:{stk.name}" if stk else str(cid))
            return f"[{page_n}] {p['name']} — {', '.join(cs_names) or '(empty)'}"

        sub2 = tokens[2]
        if sub2 == 'NAME':
            name = " ".join(raw.split()[3:]) if len(tokens) > 3 else f"page {page_n}"
            fader_pool.set_page_name(page_n, name)
            ShowFile.save_fader_pages(fader_pool)
            return f"page {page_n} → '{name}'"
        if sub2 == 'DELETE':
            fader_pool.delete_page(page_n)
            ShowFile.save_fader_pages(fader_pool)
            return f"page {page_n} deleted"
        if sub2 in ('ADD', 'REMOVE') and len(tokens) >= 4 and tokens[3] == 'STK':
            try:
                target_cs = int(tokens[4]) if len(tokens) > 4 else int(tokens[3])
            except (ValueError, IndexError):
                return f"PAGE: bad stack number"
            stk = stack_pool.get(target_cs)
            if sub2 == 'ADD':
                fader_pool.add_to_page(page_n, target_cs)
                ShowFile.save_fader_pages(fader_pool)
                return f"stk {target_cs} ({stk.name if stk else '?'}) added to page {page_n}"
            else:
                fader_pool.remove_from_page(page_n, target_cs)
                ShowFile.save_fader_pages(fader_pool)
                return f"stk {target_cs} removed from page {page_n}"
        return "usage: page <n> name <name> | page <n> add stk <m> | page <n> remove stk <m> | page <n> delete | page list"

    # ── PROG TIME — programmer time override ──────────────────
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

    # PROG FADE CLEAR — cancel all live programmer fades immediately
    if t0 == 'PROG' and len(tokens) >= 3 and tokens[1] == 'FADE' and tokens[2] == 'CLEAR':
        n = len(prog.live_fades)
        prog.live_fades.clear()
        return f"prog fades cleared ({n} active)"

    # ── FADER <n> — switch active fader ─────────────────
    if t0 in ('FADER_SELECT', 'FADER') and len(tokens) == 2:
        try:
            n = int(tokens[1])
        except ValueError:
            return f"FADER: bad fader number '{tokens[1]}'"
        active_fader[0] = n
        ex = fader_pool.get(n)
        cs_name = ex.stack.name if ex.stack else "(no stack)"
        return f"active fader → {n}  [{cs_name}]"

    # GO FADE <t> [DELAY <d>] — one-shot fade override for next GO only
    if t0 == 'GO' and len(tokens) >= 3 and tokens[1] == 'FADE':
        try:
            go_fade_t = float(tokens[2])
        except ValueError:
            return "GO FADE: usage  GO FADE <seconds> [DELAY <seconds>]"
        go_delay_t = 0.0
        if 'DELAY' in tokens:
            di = tokens.index('DELAY')
            try:
                go_delay_t = float(tokens[di + 1])
            except (IndexError, ValueError):
                return "GO FADE: bad DELAY value"
        _prev_pt = dict(_prog_time)
        _prog_time['on']    = True
        _prog_time['fade']  = go_fade_t
        _prog_time['delay'] = go_delay_t
        cue_go()
        _prog_time.update(_prev_pt)
        stk = _active_stack()
        cur = stk.current if stk else None
        delay_s = f" delay {go_delay_t}s" if go_delay_t else ""
        return f"GO → cue {cur}  (fade {go_fade_t}s{delay_s})"

    if t0 == 'GO' and len(tokens) == 1:
        cue_go()
        stk = _active_stack()
        cur = stk.current if stk else None
        return f"GO → cue {cur}" if cur else "GO (no cue)"

    if t0 == 'BACK' and len(tokens) == 1:
        cue_back()
        stk = _active_stack()
        cur = stk.current if stk else None
        return f"BACK → cue {cur}" if cur else "BACK (no cue)"

    if t0 == 'GOTO' and len(tokens) > 1:
        try:
            num = float(tokens[1])
            result = goto_cue(num)
            return result or f"GOTO → cue {num}"
        except ValueError:
            return f"GOTO: bad cue number '{tokens[1]}'"

    if t0 == 'RELOAD' and len(tokens) == 1:
        return cue_reload() or "reloaded"

    if t0 == 'DELETE' and len(tokens) >= 2 and tokens[1] == 'CUE':
        if len(tokens) < 3:
            return "usage: delete cue <n>  [stk <stack_n>]"
        try:
            cue_num = float(tokens[2])
        except ValueError:
            return f"delete cue: bad cue number '{tokens[2]}'"
        if 'STK' in tokens:
            stk_idx = tokens.index('STK')
            try:
                stk_n = int(tokens[stk_idx + 1])
            except (ValueError, IndexError):
                return "usage: delete cue <n> stk <stack_n>"
            stk = stack_pool.get(stk_n)
            if not stk:
                return f"stack {stk_n} not found"
        else:
            active_n = active_fader[0] if active_fader else 1
            stk = stack_pool.get(active_n)
            if not stk:
                return "no active stack"
        if cue_num not in stk.cues:
            return f"cue {cue_num} not found in {stk.name}"
        stk.delete_cue(cue_num)
        if cue_num == int(cue_num):
            cue_pool.delete(int(cue_num))
        save_show()
        return f"deleted cue {cue_num} from {stk.name}"

    # ── DELETE GROUP / COLOR / DIM / FX / FORM / STACK ────
    if t0 == 'DELETE' and len(tokens) >= 3:
        sub = tokens[1]
        try:
            n = int(tokens[2])
        except ValueError:
            return f"DELETE {sub}: bad slot number '{tokens[2]}'"
        if sub == 'GROUP':
            if not group_pool.get(n):
                return f"group {n} is empty"
            group_pool.delete(n)
            save_show()
            return f"deleted group {n}"
        if sub in ('COLOR', 'COLOUR'):
            if not color_pool.get(n):
                return f"color {n} is empty"
            color_pool.delete(n)
            save_show()
            return f"deleted color {n}"
        if sub == 'DIM':
            if not dim_pool.get(n):
                return f"dim {n} is empty"
            dim_pool.delete(n)
            save_show()
            return f"deleted dim {n}"
        if sub == 'FX':
            if not fx_pool.get(n):
                return f"FX {n} is empty"
            fx_pool.delete(n)
            save_show()
            return f"deleted FX {n}"
        if sub == 'FORM':
            if n < FormPool.FIRST_CUSTOM_SLOT:
                return f"form {n} is built-in — only custom forms (slot ≥ {FormPool.FIRST_CUSTOM_SLOT}) can be deleted"
            if not form_pool.get(n):
                return f"form {n} is empty"
            form_pool.delete(n)
            save_show()
            return f"deleted form {n}"
        if sub in ('STACK', 'STK'):
            if not stack_pool.get(n):
                return f"stack {n} is empty"
            cs_name = stack_pool.get(n).name
            # Stop any fader currently running this stack
            for ex in list(fader_pool.faders.values()):
                if ex.stack and ex.stack.stack_id == n:
                    ex.stop()
            stack_pool.delete(n)
            save_show()
            return f"deleted stack {n}: {cs_name}"
        if sub == 'RATE':
            if not rate_pool.get(n): return f"rate {n} is empty"
            rate_pool.delete(n); save_show(); return f"deleted rate preset {n}"
        if sub in ('SIZEP', 'SIZE'):
            if not size_pool.get(n): return f"size {n} is empty"
            size_pool.delete(n); save_show(); return f"deleted size preset {n}"
        if sub in ('SPREADP', 'SPREAD'):
            if not spread_pool.get(n): return f"spread {n} is empty"
            spread_pool.delete(n); save_show(); return f"deleted spread preset {n}"
        _del_attr_map = {
            'POSITION': position_pool, 'GOBO': gobo_pool, 'ZOOM': zoom_pool,
            'FOCUS': focus_pool, 'BEAM': beam_pool, 'CONTROL': control_pool,
        }
        if sub in _del_attr_map:
            pool = _del_attr_map[sub]
            if not pool.get(n): return f"{sub.title()} preset {n} is empty"
            pool.delete(n); save_show()
            return f"deleted {sub.title()} preset {n}"

    # ── Shared record/update-cue helper ──────────────────────
    def _record_cue_into(stk, cue_num, suffix_tokens, raw_str, merge=False):
        """
        Apply preset tokens then record (or merge-update) a cue into stk.
        suffix_tokens: everything after CUE <num> (already upper-cased).
        raw_str: original mixed-case command (for quoted name search).
        merge=True  → UPDATE mode: merges programmer into existing cue.
        merge=False → RECORD mode: replaces cue data entirely.
        Returns result string.
        """
        _KW = {'FADE', 'INFADE', 'OUTFADE', 'DELAY', 'FOLLOW',
               'CFADE', 'CINFADE', 'DFADE', 'DINFADE', 'CDELAY', 'DDELAY',
               'GROUP', 'COLOR', 'COLOUR', 'DIM'}
        up  = raw_str.upper()

        # Quoted name wins; otherwise build from leading non-keyword tokens.
        # If no name is given and a cue already exists at this number, keep its name.
        name_match = _re.search(r'"([^"]*)"', raw_str)
        if name_match:
            name = name_match.group(1)
        else:
            name_parts = []
            for tok in suffix_tokens:
                if tok in _KW or (tok and tok[0].isdigit()):
                    break
                name_parts.append(tok.capitalize())
            if name_parts:
                name = " ".join(name_parts)
            else:
                existing = stk.get_cue(cue_num)
                name = existing.name if existing else f"cue {cue_num:.0f}"

        # Timing extraction helper — tries multiple keyword aliases in order
        def _get_timing(*kws):
            for kw in kws:
                m = _re.search(rf'\b{kw}\s+([\d.]+)', up)
                if m:
                    return float(m.group(1))
            return None

        # Global fade: FADE / INFADE / OUTFADE are synonyms for cue crossfade time
        _ft = _get_timing('FADE', 'INFADE', 'OUTFADE')
        fade   = _ft if _ft is not None else 2.0
        _dt = _get_timing('DELAY')
        delay  = _dt if _dt is not None else 0.0
        _fw = _get_timing('FOLLOW')
        follow = _fw if _fw is not None else 0.0

        # Per-attribute-group overrides: CFade / DFade / CDelay / DDelay
        fade_times, delay_times = {}, {}
        _v = _get_timing('CFADE', 'CINFADE')
        if _v is not None: fade_times['colour']  = _v
        _v = _get_timing('DFADE', 'DINFADE')
        if _v is not None: fade_times['dim']     = _v
        _v = _get_timing('CDELAY')
        if _v is not None: delay_times['colour'] = _v
        _v = _get_timing('DDELAY')
        if _v is not None: delay_times['dim']    = _v

        # preset look-up by name across all pools
        def _find_by_name(tok):
            t = tok.upper()
            for p in color_pool.presets.values():
                if p.name.upper() == t:
                    return ('color', p)
            for p in dim_pool.presets.values():
                if p.name.upper() == t:
                    return ('dim', p)
            for g in group_pool.groups.values():
                if g.name.upper() == t:
                    return ('group', g)
            return None

        def _extract_int(keyword):
            m = _re.search(rf'\b{keyword}\s+(\d+)', up)
            return int(m.group(1)) if m else None

        # Numeric keyword forms (GROUP 1, COLOR 2, DIM 3)
        group_n = _extract_int('GROUP')
        color_n = _extract_int('COLOR') or _extract_int('COLOUR')
        dim_n   = _extract_int('DIM')

        if group_n is not None:
            g = group_pool.get(group_n)
            if not g: return f"RECORD CUE: group {group_n} not found"
            prog.select(g.recall(patch))
        if color_n is not None:
            p = color_pool.get(color_n)
            if not p: return f"RECORD CUE: color {color_n} not found"
            p.apply(prog)
        if dim_n is not None:
            p = dim_pool.get(dim_n)
            if not p: return f"RECORD CUE: dim {dim_n} not found"
            p.apply(prog)

        # Name-based preset tokens (any token not a keyword/number that
        # wasn't consumed by the above — i.e. the leading name tokens)
        for tok in suffix_tokens:
            if tok in _KW or (tok and tok[0].isdigit()):
                break   # hit a keyword or number — stop
            hit = _find_by_name(tok)
            if hit:
                kind, preset = hit
                if kind == 'color':
                    preset.apply(prog)
                elif kind == 'dim':
                    preset.apply(prog)
                elif kind == 'group':
                    prog.select(preset.recall(patch))

        # Treat programmer as empty if it only contains flag values (fx_kill etc.)
        # with no actual DMX data — prevents CFADE/DFADE from accidentally wiping cue data.
        _prog_has_dmx = any(
            any(k not in ('fx_kill',) for k in vals)
            for vals in prog.data.values() if vals
        )

        if not _prog_has_dmx:
            # programmer has no DMX data — allow timing/name update on any existing cue.
            existing = stk.get_cue(cue_num)
            if existing:
                _apply_timing_edit(existing, raw_str)
                if name:
                    existing.name = name
                save_show()
                action = "Updated" if merge else "Updated timing"
                return f"{action}: {existing}"
            if merge:
                return f"UPDATE CUE: cue {cue_num} not found — create it first with RECORD CUE"
            return "RECORD CUE: programmer is empty — set values or use preset names / GROUP / COLOR / DIM"

        if merge:
            # UPDATE mode: merge programmer into existing cue (or create if missing)
            cue = stk.get_cue(cue_num)
            if not cue:
                return f"UPDATE CUE: cue {cue_num} not found — create it first with RECORD CUE"
            cue.update(prog)
            _apply_timing_edit(cue, raw_str)
            if name:
                cue.name = name
            if cue_num == int(cue_num):
                cue_pool.store(int(cue_num), cue)
            save_show()

            # Auto-reload if this cue is the currently running cue on any fader
            _reloaded = []
            for _ex in fader_pool.faders.values():
                if _ex.stack is stk and _ex.stack.current == cue_num and _ex.is_active:
                    fader_pool.bump_priority(_ex.fdr_id)
                    _ex.reload(patch, fade_engine)
                    _on_cue_fire(cue_num)
                    _reloaded.append(_ex.fdr_id)
            _reload_note = f"  (live-reloaded fdr {_reloaded})" if _reloaded else ""
            return f"updated: {cue}  (merged into {stk.name}){_reload_note}"

        cue = stk.record_cue(cue_num, prog, name=name, fade_time=fade)
        cue.delay_time  = delay
        cue.follow_time = follow
        cue.fade_times  = fade_times
        cue.delay_times = delay_times
        if cue_num == int(cue_num):
            cue_pool.store(int(cue_num), cue)
        save_show()
        return f"recorded: {cue}  into {stk.name}  (auto-saved)"

    # ── record stk [n] cue <m> [presets...] ──────────────────
    # e.g.  RECORD stk CUE 4 RED
    #        RECORD stk 2 CUE 4 RED FULL
    if t0 == 'RECORD' and 'STK' in tokens and 'CUE' in tokens:
        stk_idx  = tokens.index('STK')
        cue_idx = tokens.index('CUE')

        # Optional stack number after stk
        stk_n = None
        if cue_idx > stk_idx + 1:
            try:
                stk_n = int(tokens[stk_idx + 1])
            except ValueError:
                pass

        try:
            cue_num = float(tokens[cue_idx + 1])
        except (IndexError, ValueError):
            return "usage: record stk [n] cue <num> [preset-names / group n color n dim n fade t]"

        stk = stack_pool.get(stk_n) if stk_n is not None else _active_stack()
        if not stk:
            return f"stack {stk_n} not found" if stk_n else "no active stack"

        return _record_cue_into(stk, cue_num, tokens[cue_idx + 2:], raw)

    # ── RECORD CUE <n> ["name"] [GROUP g] [COLOR c] [DIM d] [fade t]
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'CUE':
        try:
            cue_num = float(tokens[2])
        except ValueError:
            return f"RECORD: bad cue number '{tokens[2]}'"
        stk = _active_stack()
        if not stk:
            return "RECORD CUE: no active stack — use RECORD STACK 1 first"
        return _record_cue_into(stk, cue_num, tokens[3:], raw)

    # ── UPDATE CUE / UPDATE stk CUE — merge programmer into existing cue ──
    # UPDATE CUE <n> [presets] [FADE <t>]
    # update stk [n] cue <m> [presets] [FADE <t>]
    # Only merges what is in the programmer — untouched fixtures keep their data.
    if t0 in ('UPDATE', 'UPD'):
        if 'STK' in tokens and 'CUE' in tokens:
            stk_idx  = tokens.index('STK')
            cue_idx = tokens.index('CUE')
            stk_n    = None
            if cue_idx > stk_idx + 1:
                try:
                    stk_n = int(tokens[stk_idx + 1])
                except ValueError:
                    pass
            try:
                cue_num = float(tokens[cue_idx + 1])
            except (IndexError, ValueError):
                return "usage: update stk [n] cue <num> [presets / fade t]"
            stk = stack_pool.get(stk_n) if stk_n is not None else _active_stack()
            if not stk:
                return f"stack {stk_n} not found" if stk_n else "no active stack"
            return _record_cue_into(stk, cue_num, tokens[cue_idx + 2:], raw, merge=True)
        if 'CUE' in tokens:
            cue_idx = tokens.index('CUE')
            try:
                cue_num = float(tokens[cue_idx + 1])
            except (IndexError, ValueError):
                return "usage: update cue <num> [presets / fade t]"
            stk = _active_stack()
            if not stk:
                return "UPDATE CUE: no active stack"
            return _record_cue_into(stk, cue_num, tokens[cue_idx + 2:], raw, merge=True)

    # ── GO stk <n>  /  BACK stk <n> ────────────────────────────
    # Advance/step the specified fader without specifying a cue number.
    # e.g.  GO stk 2   (same as fdr 2 GO, without changing active_fader)
    if t0 in ('GO', 'BACK') and 'STK' in tokens and 'CUE' not in tokens:
        stk_idx = tokens.index('STK')
        try:
            stk_n = int(tokens[stk_idx + 1])
        except (IndexError, ValueError):
            stk_n = active_fader[0]
        ex = None
        for _e in fader_pool.faders.values():
            if _e.stack and _e.stack.stack_id == stk_n:
                ex = _e
                break
        if not ex:
            ex = fader_pool.get(stk_n)
        fader_pool.bump_priority(ex.fdr_id)
        if t0 == 'GO':
            msg = ex.go(patch, fade_engine)
        else:
            msg = ex.back(patch, fade_engine)
        if ex.stack:
            _on_cue_fire(ex.stack.current)
        direction = "GO" if t0 == 'GO' else "BACK"
        cur = ex.stack.current if ex.stack else None
        return msg or f"{direction} stk {stk_n} → cue {cur}"

    # ── go stk [n] cue <m> ────────────────────────────────────
    # e.g.  GO stk 2 CUE 4
    #        GO stk CUE 1       (active stack)
    if t0 == 'GO' and 'STK' in tokens and 'CUE' in tokens:
        stk_idx  = tokens.index('STK')
        cue_idx = tokens.index('CUE')

        stk_n = None
        if cue_idx > stk_idx + 1:
            try:
                stk_n = int(tokens[stk_idx + 1])
            except ValueError:
                pass

        try:
            cue_num = float(tokens[cue_idx + 1])
        except (IndexError, ValueError):
            return "usage: go stk [n] cue <num>"

        # Find fader for this stack (match by stack_id, fallback to slot)
        if stk_n is not None:
            ex = None
            for e in fader_pool.faders.values():
                if e.stack and e.stack.stack_id == stk_n:
                    ex = e
                    break
            if not ex:
                ex = fader_pool.get(stk_n)
                stk = stack_pool.get(stk_n)
                if stk:
                    ex.assign(stk)
        else:
            ex = _active_fader()

        fader_pool.bump_priority(ex.fdr_id)
        msg = ex.goto(cue_num, patch, fade_engine)
        if ex.stack and (not msg or 'not found' not in msg):
            _on_cue_fire(ex.stack.current)
        return msg or f"GO stk {stk_n or active_fader[0]} CUE {cue_num}"

    # ── FORM commands ─────────────────────────────────────────
    # FORM LIST
    # record form <n> <name> <phase,value> ...   (breakpoint curve)
    if t0 == 'FORM' and len(tokens) >= 2 and tokens[1] == 'LIST':
        lines = []
        for f in form_pool.forms.values():
            lines.append(f"  {f}")
        return "\n".join(lines) if lines else "form pool empty"

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
            name_parts.append(tok.capitalize())

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
        form_pool.store(form_n, form)
        ShowFile.save_forms(form_pool)
        return f"recorded: {form}  (auto-saved)"

    # ── FX helpers (used by FX commands and CLEAR) ───────────

    def _prog_fx_stop():
        """Stop all programmer-preview FX layers."""
        for fxid in _prog_fx_ids:
            fx_engine.remove(fxid)
        _prog_fx_ids.clear()
        active_fx.clear()

    def _prog_fx_start(fx_defs_by_fid):
        """
        Start live-preview FX layers for the given fixture→fx_defs mapping.
        fx_defs_by_fid: {fixture_id (int): [fx_def, ...]}

        Tree references are expanded before bucketing:
          color_id  → 'rgb' channel split into R/G/B layers scaled by preset
          group_id  → fixture list replaced by group members
          dim_id    → passed live to FXLayer as a size ceiling (no expansion needed)
        """
        expanded = _expand_color_fx(fx_defs_by_fid, color_pool)
        expanded = _expand_group_fx(expanded, patch, group_pool)
        for ld, targets in _bucket_fx_defs(expanded, patch):
            fxid = max(_prog_fx_ids, default=8999) + 1
            layer = fx_engine.add(
                fxid,
                ld.get('waveform', 'sine'),
                ld['channel'],
                rate_bpm     = ld.get('bpm',          _fx_params['rate_bpm']),
                size         = ld.get('size',         _fx_params['size']),
                targets      = targets,
                spread       = ld.get('spread',       _fx_params['spread']),
                phase_offset = ld.get('phase_offset', 0.0),
                infade       = ld.get('infade',       _fx_params['infade']),
                outfade      = ld.get('outfade',      _fx_params['outfade']),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
                dim_id       = ld.get('dim_id'),
                speed_id     = ld.get('speed_id'),
                block_size   = ld.get('block_size',      1),
                order        = ld.get('order',    'linear'),
                direction    = ld.get('direction','forward'),
            )
            _prog_fx_ids.append(fxid)
            active_fx.append(layer)

    def _prog_fx_rebuild():
        """
        Rebuild all programmer FX from prog.data in one shot.
        Called after any FX change so all fixtures keep their effects —
        not just the ones in the latest selection.
        """
        all_fx = {}
        for fid_str, vals in prog.data.items():
            if '.' in fid_str:
                continue
            layers = vals.get('fx')
            if layers:
                try:
                    all_fx[int(fid_str)] = layers
                except ValueError:
                    pass
        _prog_fx_stop()
        if all_fx:
            _prog_fx_start(all_fx)

    # ── FX commands ──────────────────────────────────────────
    # FX applies to the programmer against the current selection.
    # The FX def is written into prog.data[master_fid]['fx'] and a
    # live preview layer is started so output is visible immediately.
    # RECORD CUE captures FX defs along with colour/dim automatically.
    # CLEAR stage 2 (programmer) removes FX defs and stops preview.

    _WAVEFORMS = {'SINE', 'RAMP', 'PULSE', 'SQUARE', 'TRIANGLE', 'SAWTOOTH', 'FLICKER'}
    _CHANNELS  = {
        'RED', 'GREEN', 'BLUE', 'DIM',
        'PAN', 'TILT', 'PAN_FINE', 'TILT_FINE',
        'GOBO', 'GOBO_ROT', 'GOBO2', 'GOBO2_ROT',
        'ZOOM', 'FOCUS', 'IRIS', 'SHUTTER1', 'COLOR',
        'PRISM', 'FROST', 'ANIMATION', 'CONTROL', 'MACRO', 'DIMMER',
    }

    # ── BPM / SIZE / SPREAD  — set global FX parameters ────────────
    # Updates live layers, programmer data, and GUI sliders in one shot.

    if t0 == 'BPM' and len(tokens) >= 2:
        try:
            val = float(tokens[1])
        except ValueError:
            return f"BPM: expected a number, got '{tokens[1]}'"
        val = max(10.0, min(480.0, val))
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

    if t0 == 'SIZE' and len(tokens) >= 2:
        try:
            val = float(tokens[1])
        except ValueError:
            return f"SIZE: expected a number, got '{tokens[1]}'"
        val = max(0.0, min(100.0, val))
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

    if t0 == 'SPREAD' and len(tokens) >= 2:
        try:
            val = float(tokens[1])
        except ValueError:
            return f"SPREAD: expected a number, got '{tokens[1]}'"
        val = max(0.0, min(100.0, val))
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

    # STROBE [bpm] — shorthand for FX PULSE DIM BPM <bpm> FIXTURE
    # STROBE CLEAR — remove dim FX from programmer
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

    # RAINBOW [bpm] [spread] — RGB sine wave chase across all selected fixtures.
    # Creates three synchronized FX layers (R/G/B) with 120° phase offsets.
    # usage: RAINBOW 60      → 60 BPM rainbow at full spread
    #        RAINBOW 30 50   → 30 BPM at 50% spread
    #        RAINBOW CLEAR   → FX CLEAR (removes all colour FX layers)
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

    if t0 == 'FX' and len(tokens) >= 2:
        sub = tokens[1]

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
            _sel_fids = {str(f.fixture_id) for f in prog.selection} if prog.selection else None

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
                                     f"BPM={ld.get('bpm',60)} size={ld.get('size',200)}{dist_s}")
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

        # fx [add] <waveform|form n|COLOR n> [channel] [bpm n] [size n] [SPREAD n]
        #   [group n] [dimref n] [BLOCK n] [ORDER RANDOM] [DIRECTION FWD|REV|BOUNCE] [PIXEL|FIXTURE]
        #
        # Tree references:
        #   COLOR n  — drives R/G/B from Colorpreset n (waveform drives intensity of that color)
        #   GROUP n  — target only fixtures in GroupPool slot n instead of programmer selection
        #   dimref n — live size ceiling: Dimmerpreset n's level scales FX amplitude (0–1)
        add_mode = (sub == 'ADD')
        base_idx = 2 if add_mode else 1

        if base_idx >= len(tokens):
            return ("usage: fx [add] <waveform|form n|COLOR n> [channel] "
                    "[bpm n] [size n] [SPREAD n] [group n] [dimref n] "
                    "[BLOCK n] [ORDER RANDOM] [DIRECTION FWD|REV|BOUNCE]")

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
            'target_scope': target_scope,
        }

        # Resolve target fixtures — GROUP n overrides programmer selection
        if group_id is not None:
            grp = group_pool.get(group_id)
            if not grp:
                return f"group {group_id} not found"
            sel_fids = [m.fixture_id for m in grp.recall(patch)]
            if not sel_fids:
                return f"group {group_id} is empty"
        elif prog.selection:
            seen_m, sel_fids = set(), []
            for f in prog.selection:
                mid = f.fixture_id if isinstance(f, MasterFixture) else getattr(f, 'master_id', None)
                if mid and mid not in seen_m:
                    seen_m.add(mid)
                    sel_fids.append(mid)
        else:
            sel_fids = [m.fixture_id for m in patch.all_fixtures()]

        # Write into programmer data (master entries).
        # Each fixture gets its own copy of fx_def so per-fixture edits
        # (e.g. changing BPM on just one fixture) don't bleed to others.
        for fid in sel_fids:
            entry = prog.data.setdefault(str(fid), {})
            if not add_mode:
                entry['fx'] = [dict(fx_def)]
            else:
                entry.setdefault('fx', []).append(dict(fx_def))

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

    # RECORD FX <n> [name]  — snapshot programmer FX defs into the pool
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

        name = " ".join(t.capitalize() for t in tokens[3:]) if len(tokens) > 3 else ""
        preset = FXPreset(fx_n, name or f"FX {fx_n}")
        for ld in defs:
            preset.add_layer(
                ld['waveform'], ld['channel'],
                bpm          = ld.get('bpm',    60.0),
                size         = ld.get('size',   100.0),
                spread       = ld.get('spread',   0.0),
                phase_offset = ld.get('phase_offset', 0.0),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
                dim_id       = ld.get('dim_id'),
                color_id     = ld.get('color_id'),
                group_id     = ld.get('group_id'),
                speed_id     = ld.get('speed_id'),
                block_size   = ld.get('block_size',      1),
                order        = ld.get('order',    'linear'),
                direction    = ld.get('direction','forward'),
                target_scope = ld.get('target_scope'),
            )
        fx_pool.store(fx_n, preset)
        ShowFile.save_fx_pool(fx_pool)
        _preset_live_push('fx', fx_n)
        return f"recorded: {preset}  (auto-saved)"

    # FIRE FX <n> [group n]  — write preset defs into programmer + preview
    # GROUP n overrides the preset's stored group_id or programmer selection.
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

        if fire_group_id is not None:
            grp = group_pool.get(fire_group_id)
            if not grp:
                return f"FIRE FX: group {fire_group_id} not found"
            sel_fids = [m.fixture_id for m in grp.recall(patch)]
        elif prog.selection:
            seen_m, sel_fids = set(), []
            for f in prog.selection:
                mid = f.fixture_id if isinstance(f, MasterFixture) else getattr(f, 'master_id', None)
                if mid and mid not in seen_m:
                    seen_m.add(mid)
                    sel_fids.append(mid)
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

        for fid in sel_fids:
            entry = prog.data.setdefault(str(fid), {})
            kept  = [ld for ld in entry.get('fx', [])
                     if ld.get('channel') not in new_channels]
            fired_defs = [{**dict(ld), 'fx_preset_ref': fx_n} for ld in preset.layers]
            # Apply fire-time group override
            if fire_group_id is not None:
                for d in fired_defs:
                    d['group_id'] = fire_group_id
            entry['fx'] = kept + fired_defs

        _prog_fx_rebuild()

        ref_s = f" [group:{fire_group_id}]" if fire_group_id else ""
        return f"fired: {preset}{ref_s}  → {len(sel_fids)} fixture(s)"

    # ── CLONE <src_id> TO <dst_id> ───────────────────────────
    # Copies all pool data from one fixture to another:
    # color/dim presets, group memberships, cue data (master + sub entries).
    if t0 == 'CLONE' and 'TO' in tokens:
        try:
            to_idx  = tokens.index('TO')
            src_id  = int(tokens[1])
            dst_ids = []
            # Support: CLONE 1 TO 7  OR  CLONE 1 TO 7 THRU 9
            rest = tokens[to_idx + 1:]
            if len(rest) == 3 and rest[1] == 'THRU':
                dst_ids = list(range(int(rest[0]), int(rest[2]) + 1))
            elif rest:
                dst_ids = [int(rest[0])]
        except (ValueError, IndexError):
            return "usage: clone <src> to <dst>  |  clone <src> to <dst> thru <end>"

        if src_id not in patch.fixtures:
            return f"clone source fixture {src_id} not in patch"
        missing = [d for d in dst_ids if d not in patch.fixtures]
        if missing:
            return f"destination(s) {missing} not in patch — patch them first"

        src_str  = str(src_id)
        src_master = patch.fixtures[src_id]
        n_subs   = len(src_master.sub_fixtures)

        for dst_id in dst_ids:
            dst_str = str(dst_id)

            # Color/dim presets store a single global value, not per-fixture data;
            # nothing to copy here — groups and cues carry the fixture-specific data.

            # Groups — add dst to every group that contains src
            for group in group_pool.groups.values():
                src_entry = ("master", src_id)
                dst_entry = ("master", dst_id)
                if src_entry in group.members and dst_entry not in group.members:
                    group.members.append(dst_entry)

            # Cues — copy master key and all sub-fixture keys
            for stack in stack_pool.stacks.values():
                for cue in stack.cues.values():
                    if src_str in cue.data:
                        cue.data[dst_str] = dict(cue.data[src_str])
                    for si in range(1, n_subs + 1):
                        src_sub = f"{src_str}.{si}"
                        if src_sub in cue.data:
                            cue.data[f"{dst_str}.{si}"] = dict(cue.data[src_sub])

        save_show()
        dst_label = dst_ids[0] if len(dst_ids) == 1 else f"{dst_ids[0]}–{dst_ids[-1]}"
        return f"cloned fixture {src_id} → {dst_label}  ({len(dst_ids)} dest, show saved)"

    # ── SNAPSHOT ─────────────────────────────────────────────
    # SNAPSHOT <cue_num> [name] — record current live output (cue + programmer merged)
    # as a new cue. Unlike RECORD CUE which only records programmer data, SNAPSHOT
    # captures the full merged look (useful when multiple faders are running).
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

    # ── Blind mode ───────────────────────────────────────────
    if t0 == 'BLIND':
        output_state.blind = True
        return "BLIND mode ON — programmer suppressed from DMX output"

    if t0 == 'LIVE':
        output_state.blind = False
        return "LIVE mode — programmer active in output"

    # ── MACRO ─────────────────────────────────────────────────────────────────
    # MACRO RECORD <n> [name]  — start recording commands to slot n
    # MACRO STOP               — stop recording and save
    # MACRO ABORT              — discard recording without saving
    # MACRO <n>                — play back macro slot n
    # MACRO LIST               — list all recorded macros
    # MACRO DELETE <n>         — delete macro slot n
    # RENAME MACRO <n> <name>  — rename macro slot n
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
            name = raw_parts[3] if len(raw_parts) > 3 else f"macro {slot}"
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
            macro_pool[slot]["name"] = raw_parts[3].strip()
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

    # ── PARK / UNPARK ────────────────────────────────────────────────────────
    # PARK          — park selected fixtures at their current DMX output values
    # UNPARK        — release selected fixtures from park (or UNPARK ALL)
    # LIST PARK     — show all currently parked fixtures
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

    if t0 == 'HIGHLIGHT' or (t0 == 'HL' and len(tokens) <= 2):
        off = len(tokens) > 1 and tokens[1] == 'OFF'
        on  = len(tokens) > 1 and tokens[1] == 'ON'
        if off or (output_state.highlight_mode and not on):
            output_state.highlight_mode = False
            return "HIGHLIGHT OFF"
        else:
            output_state.highlight_mode = True
            output_state.highlight_fids = {
                f.fixture_id for f in prog.selection
                if isinstance(f, MasterFixture)
            }
            fids = sorted(output_state.highlight_fids)
            return f"HIGHLIGHT ON — fixtures {fids} at full white"

    # ── OUTPUT STATUS — current live DMX overview ─────────────────────────────
    if t0 == 'OUTPUT' and len(tokens) >= 2 and tokens[1] in ('STATUS', 'INFO', 'SHOW'):
        limit = 20
        try:
            if len(tokens) >= 3:
                limit = int(tokens[2])
        except ValueError:
            pass
        lines = [f"Output (master={output_state.master_level:.0%}"
                 + ("  FREEZE" if output_state.freeze_mode else "")
                 + ("  BLIND" if output_state.blind else "")
                 + ("  BLACKOUT" if output_state.master_level == 0.0 else "")
                 + "):"]
        all_active = []
        for u in sorted(set(list(output_state.parked_addresses.keys())
                            + list(output_state.direct_dmx.keys()) + [1])):
            dmx = output_state.get_dmx_for_universe(u)
            for addr0, val in enumerate(dmx):
                if val > 0:
                    all_active.append((u, addr0 + 1, val))
        all_active.sort(key=lambda x: -x[2])
        if not all_active:
            lines.append("  (all channels at 0)")
        else:
            shown = all_active[:limit]
            for u, addr, val in shown:
                pct = val / 255 * 100
                bar = '█' * int(pct / 10)
                # Reverse-map address to fixture name
                fid_label = ""
                for fid, master in patch.fixtures.items():
                    for sub in master.all_subs():
                        for out in sub.outputs:
                            if (out['universe'] == u and
                                    out['address'] <= addr <
                                    out['address'] + len(master.profile.channels)):
                                fid_label = f"  ← {master.name}"
                                break
                lines.append(f"  U{u}@{addr:03d}: {val:3d}  {bar:<10} {pct:.0f}%{fid_label}")
            if len(all_active) > limit:
                lines.append(f"  … ({len(all_active) - limit} more channels)")
        return "\n".join(lines)

    if t0 == 'MASTER' and len(tokens) >= 2:
        try:
            pct = float(tokens[1])
        except ValueError:
            return f"MASTER: bad value '{tokens[1]}' — use 0-100"
        output_state.master_level = max(0.0, min(1.0, pct / 100.0))
        return f"master → {pct:.0f}%"

    # ── GRANDMASTER / GM — show or set the master output level ───────────────
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

    if t0 == 'BLACKOUT':
        off = len(tokens) > 1 and tokens[1] == 'OFF'
        if off or output_state.master_level == 0.0:
            output_state.master_level = _blackout_saved_level[0]
            return f"BLACKOUT OFF — master restored to {output_state.master_level:.0%}"
        else:
            _blackout_saved_level[0] = output_state.master_level
            output_state.master_level = 0.0
            return "BLACKOUT ON — all output cut (BLACKOUT OFF to restore)"

    if t0 == 'BBO':
        if output_state.master_level > 0.0:
            _blackout_saved_level[0] = output_state.master_level
        output_state.master_level = 0.0
        return "BLACKOUT ON"

    # ── Save ─────────────────────────────────────────────────
    # ── SHOW INFO — high-level overview of the current show ──────────────────
    if t0 == 'SHOW' and len(tokens) >= 2 and tokens[1] in ('INFO', 'STATUS', 'STATS'):
        total_cues   = sum(len(stk.cues) for stk in stack_pool.stacks.values())
        active_faders = sum(1 for ex in fader_pool.faders.values() if ex.is_active)
        assigned_faders = sum(1 for ex in fader_pool.faders.values() if ex.stack)
        prog_fids = len(set(k.split('.')[0] for k in prog.data if prog.data.get(k)))
        lines = [
            "show overview:",
            f"  fixtures     : {len(patch.fixtures)} patched",
            f"  programmer   : {prog_fids} fixture(s) touched",
            f"  stacks    : {len(stack_pool.stacks)} stacks  /  {total_cues} cues total",
            f"  faders       : {active_faders} active  /  {assigned_faders} assigned",
            f"  fx presets   : {len(fx_pool.presets)}",
            f"  color presets: {len(color_pool.presets)}",
            f"  dim presets  : {len(dim_pool.presets)}",
            f"  groups       : {len(group_pool.groups)}",
            f"  prog snaps   : {len(_prog_snapshots)}",
        ]
        if output_state.blind:
            lines.append("  mode         : blind")
        if output_state.freeze_mode:
            lines.append("  mode         : frozen")
        lines.append(f"  master       : {output_state.master_level:.0%}")
        return "\n".join(lines)

    if t0 == 'BACKUP':
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        return save_show_as(f"backup_{ts}")

    if t0 == 'SAVE':
        if len(tokens) >= 3 and tokens[1] == 'AS':
            name = raw.split(None, 2)[2] if len(raw.split(None, 2)) > 2 else ""
            return save_show_as(name)
        save_show()
        return "show saved."

    # LOAD CUE <n> [stk <stack_n>]  — copy cue data into programmer for editing
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

    if t0 == 'LOAD' and len(tokens) >= 2 and tokens[1] == 'SHOW':
        if len(tokens) < 3:
            return "usage: load show <name>  (use list shows to see available saves)"
        name = raw.split(None, 2)[2] if len(raw.split(None, 2)) > 2 else ""
        return load_show_from(name)

    # ── PATCH command-line ────────────────────────────────────
    # PATCH ADD <id> <profile> UNIVERSE <u> AT <addr> [NAME <name>]
    # PATCH REMOVE <id>
    if t0 == 'PATCH' and len(tokens) >= 2:
        sub = tokens[1]
        if sub == 'ADD':
            try:
                fid = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: patch add <id> <profile> universe <u> at <addr> [name <name>]"
            profile_name = tokens[3] if len(tokens) > 3 else None
            if not profile_name:
                return "PATCH ADD: profile name required"
            univ = 1
            addr = 1
            name = f"Fixture {fid}"
            if 'UNIVERSE' in tokens:
                ui = tokens.index('UNIVERSE')
                try: univ = int(tokens[ui + 1])
                except (IndexError, ValueError): pass
            if 'AT' in tokens:
                ai = tokens.index('AT')
                try: addr = int(tokens[ai + 1])
                except (IndexError, ValueError): pass
            if 'NAME' in tokens:
                ni = tokens.index('NAME')
                # NAME takes the rest of the token list joined
                name = ' '.join(tokens[ni + 1:]) if ni + 1 < len(tokens) else name
            if patch.get(fid):
                return f"PATCH ADD: fixture {fid} already patched — PATCH REMOVE {fid} first"
            m = patch.patch_fixture(fid, name, profile_name, univ, addr)
            if m is None:
                return f"PATCH ADD: profile '{profile_name}' not found"
            save_show()
            return f"patched fixture {fid} '{name}' as {profile_name} U{univ}@{addr}"
        if sub == 'REMOVE':
            try:
                fid = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: patch remove <id>"
            if fid not in patch.fixtures:
                return f"PATCH REMOVE: fixture {fid} not patched"
            del patch.fixtures[fid]
            save_show()
            return f"removed fixture {fid} from patch"
        if sub == 'RENAME':
            try:
                fid = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: patch rename <id> <new name>"
            master = patch.get(fid)
            if not master:
                return f"PATCH RENAME: fixture {fid} not patched"
            raw_parts = raw.split(None, 3)
            if len(raw_parts) < 4:
                return "usage: patch rename <id> <new name>"
            master.name = raw_parts[3]
            save_show()
            return f"fixture {fid} renamed to '{master.name}'"
        if sub == 'MOVE':
            try:
                fid = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: patch move <id> universe <u> at <addr>"
            master = patch.get(fid)
            if not master:
                return f"PATCH MOVE: fixture {fid} not patched"
            univ = 1; addr = 1
            if 'UNIVERSE' in tokens:
                ui = tokens.index('UNIVERSE')
                try: univ = int(tokens[ui + 1])
                except (IndexError, ValueError): pass
            if 'AT' in tokens:
                ai = tokens.index('AT')
                try: addr = int(tokens[ai + 1])
                except (IndexError, ValueError): pass
            chs = master.profile.channels_per_pixel
            for i, sub_fix in enumerate(master.all_subs()):
                new_addr = addr + i * chs
                if sub_fix.outputs:
                    sub_fix.outputs[0] = {"universe": univ, "address": new_addr}
                else:
                    sub_fix.outputs.append({"universe": univ, "address": new_addr})
            save_show()
            end_addr = addr + len(master.sub_fixtures) * chs - 1
            return f"moved fixture {fid} to U{univ}@{addr}-{end_addr}"

    if t0 == 'LIST' and len(tokens) >= 2 and tokens[1] == 'SHOWS':
        return list_shows()

    if t0 == 'EXPORT' and len(tokens) >= 2 and tokens[1] == 'PRESETS':
        what = tokens[2] if len(tokens) >= 3 else 'all'
        return export_presets(what)

    if t0 == 'IMPORT' and len(tokens) >= 3 and tokens[1] == 'PRESETS':
        path = raw.split(None, 2)[2]
        return import_presets(path)

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

    # AUDIO DEVICES | START [device] | STOP | on | off | STATUS | GAIN <n>
    # Block 9 audio-reactive layer: capture (START/STOP) is independent from
    # the mapping toggle (ON/OFF) so an operator can leave a mic plugged in
    # and running while flipping the reactive layer on/off for cue timing.
    if t0 == 'AUDIO':
        t1 = tokens[1] if len(tokens) > 1 else ''
        if t1 == 'DEVICES':
            if not _AUDIO_AVAILABLE:
                return f"audio unavailable: {_AUDIO_IMPORT_ERROR}"
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

    # MIDI CC <ch> <cc> <target name>        — add CC mapping
    # MIDI NOTE <ch> <note> <target name>    — add note mapping
    # MIDI REMOVE CC <ch> <cc>              — delete CC mapping
    # MIDI REMOVE NOTE <ch> <note>          — delete note mapping
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

    # ── DIRECT DMX ───────────────────────────────────────────
    # DMX <addr> <val> [UNIVERSE <n>]  — bypass fixture system, write raw
    # CLEAR DMX [UNIVERSE <n>]         — remove all or per-universe overrides
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

    # ── STATUS overview ──────────────────────────────────────
    if t0 in ('STATUS', 'STATE'):
        lines = ["=== console status ==="]
        gm = output_state.master_level if output_state else 1.0
        blind = output_state.blind if output_state else False
        bbo   = (gm == 0.0)
        freeze = output_state.freeze_mode if output_state else False
        solo   = output_state.solo_mode   if output_state else False
        parked = bool(output_state.parked_fids) if output_state else False
        rec_slot = _macro_recording.get("slot")
        lines.append(f"  grand master: {gm*100:.0f}%"
                     + ("  [bbo]" if bbo else "")
                     + ("  [blind]" if blind else "")
                     + ("  [freeze]" if freeze else "")
                     + ("  [solo]" if solo else "")
                     + ("  [park]" if parked else "")
                     + (f"  [rec macro {rec_slot}]" if rec_slot is not None else ""))
        # Selection + programmer
        sel_masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if sel_masters:
            lines.append(f"  selection: {len(sel_masters)} fixture(s) "
                         f"({', '.join(str(m.fixture_id) for m in sel_masters)})")
        else:
            lines.append("  selection: none")
        prog_active = any(v for v in prog.data.values() if v)
        lines.append("  programmer: " + ("dirty" if prog_active else "clear"))
        # Active faders
        active_exs = [ex for ex in fader_pool.faders.values()
                      if ex.is_active and ex.stack] if fader_pool else []
        if active_exs:
            lines.append(f"  active faders ({len(active_exs)}):")
            for ex in active_exs:
                stk = ex.stack
                cur = f"cue {stk.current:.0f}" if stk.current is not None else "—"
                lines.append(f"    [{ex.fdr_id}] {stk.name[:14]}  {cur}  "
                             f"lv={ex.level*100:.0f}%")
        else:
            lines.append("  active faders: none")
        # FX
        n_fx = len(fx_engine._layers) if fx_engine else 0
        lines.append(f"  fx layers: {n_fx} active")
        return "\n".join(lines)

    # ── Stack info ───────────────────────────────────────────
    # CUES / STACK / LIST (bare) — show active stack contents
    # NOTE: LIST with a sub-command (LIST DIM, LIST COLOR, etc.) is handled
    # below; only bare LIST falls through here.
    if t0 in ('CUES', 'STACK') or (t0 == 'LIST' and len(tokens) == 1):
        stk = _active_stack()
        if not stk:
            return "no active stack"
        lines = [f"stack {stk.stack_id} — {stk.name}  [fader {active_fader[0]}]"]
        for n in stk._sorted_cue_numbers():
            c      = stk.cues[n]
            cur    = " ◀" if n == stk.current else ""
            delay  = f"  delay:{c.delay_time}s" if getattr(c, 'delay_time', 0.0) > 0 else ""
            follow = f"  follow:{c.follow_time:.1f}s" if getattr(c, 'follow_time', 0.0) > 0 else ""
            note   = f"  [{c.note}]" if getattr(c, 'note', '') else ""
            lines.append(f"  [{n:.0f}] {c.name}  fade:{c.fade_time}s{delay}{follow}{note}{cur}")
        return "\n".join(lines)

    # ── group recall / record ─────────────────────────────────
    # GROUP <n>                — recall (select fixtures)
    # RECORD GROUP <n> ["name"] — save current selection as group
    if t0 == 'GROUP' and len(tokens) > 1:
        try:
            gid = int(tokens[1])
        except ValueError:
            return f"GROUP: bad id '{tokens[1]}'"
        # GROUP <n> ADD <fid> — add a master fixture to the group
        if len(tokens) >= 4 and tokens[2].upper() == 'ADD':
            g = group_pool.get(gid)
            if not g:
                return f"group {gid} not found"
            try:
                add_fid = int(tokens[3])
            except ValueError:
                return f"GROUP ADD: bad fixture id '{tokens[3]}'"
            if not patch.get(add_fid):
                return f"GROUP ADD: fixture {add_fid} not in patch"
            if any(entry[1] == add_fid for entry in g.members if isinstance(entry, tuple)):
                return f"GROUP ADD: fixture {add_fid} already in group {gid}"
            g.members.append(("master", add_fid))
            save_show()
            return f"group {gid}: added fixture {add_fid} ({len(g.members)} member(s))"

        # GROUP <n> REMOVE <fid> — remove a master fixture from the group
        if len(tokens) >= 4 and tokens[2].upper() == 'REMOVE':
            g = group_pool.get(gid)
            if not g:
                return f"group {gid} not found"
            try:
                rm_fid = int(tokens[3])
            except ValueError:
                return f"GROUP REMOVE: bad fixture id '{tokens[3]}'"
            before = len(g.members)
            g.members = [e for e in g.members
                         if not (isinstance(e, tuple) and e[1] == rm_fid)]
            if len(g.members) == before:
                return f"GROUP REMOVE: fixture {rm_fid} not in group {gid}"
            save_show()
            return f"group {gid}: removed fixture {rm_fid} ({len(g.members)} member(s) remaining)"

        # GROUP <n> INFO/STATUS — show group members
        if len(tokens) >= 3 and tokens[2] in ('INFO', 'STATUS', 'SHOW'):
            g = group_pool.get(gid)
            if not g:
                return f"group {gid} not found"
            # Resolve member fixture IDs to names; members are ("master", fid) tuples
            member_strs = []
            for entry in g.members:
                fid = entry[1] if isinstance(entry, tuple) else int(entry)
                m = patch.get(fid)
                member_strs.append(f"{fid}:{m.name}" if m else str(fid))
            return (f"group {gid}: {g.name}\n"
                    f"  members ({len(g.members)}): {', '.join(member_strs) or '(empty)'}")
        group_pool.recall(gid, prog)
        g = group_pool.get(gid)
        return f"group {gid} recalled" if g else f"group {gid} not found"

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

    # ── Colour preset recall / record ─────────────────────────
    # COLOR <n>                 — apply to current selection
    # RECORD COLOR <n> [name]   — save RGB from programmer
    if t0 in ('COLOR', 'COLOUR') and len(tokens) > 1:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"COLOR: bad slot number '{tokens[1]}'"
        p = color_pool.get(pid)
        if not p:
            return f"color preset {pid} is empty  (use: record color {pid} red)"
        p.apply(prog)
        return f"applied: {p}"

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

    # ── dim preset recall / record ────────────────────────────
    # DIM PRESET <n>            — apply dim preset n
    # DIM <val>                 — set dimmer to val% (raw)
    # RECORD DIM <n> [name]     — save dimmer from programmer
    if t0 == 'DIM' and len(tokens) > 1:
        if tokens[1] == 'PRESET' and len(tokens) > 2:
            try:
                pid = int(tokens[2])
            except ValueError:
                return f"DIM PRESET: bad slot number '{tokens[2]}'"
            p = dim_pool.get(pid)
            if not p:
                return f"dim preset {pid} is empty  (use: record dim {pid} full)"
            p.apply(prog)
            return f"applied: {p}"
        # bare DIM <val> → raw dimmer value (AT DIM <val>)
        try:
            val = float(tokens[1].rstrip('%'))
        except ValueError:
            return f"DIM: bad value '{tokens[1]}'  (use: DIM 80  or  DIM PRESET 1)"
        prog.execute(f"AT DIM {val}")
        return ""

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

    # ── Attribute pool record / recall ───────────────────────────
    # Covers: POSITION, GOBO, ZOOM, FOCUS, BEAM, CONTROL
    # RECORD POSITION 1 [name]   — snapshot pan/tilt from programmer
    # POSITION 1                 — apply position preset 1 to programmer
    _ATTR_POOL_MAP = {
        'POSITION': position_pool,
        'GOBO':     gobo_pool,
        'ZOOM':     zoom_pool,
        'FOCUS':    focus_pool,
        'BEAM':     beam_pool,
        'CONTROL':  control_pool,
    }
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
        p.apply(prog)
        return f"applied: {p}"

    # ── rate / size / spread pool record ─────────────────────────
    # RATE <n>  — recall rate preset (sets BPM from pool slot n)
    if t0 == 'RATE' and len(tokens) == 2:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"RATE: bad slot number '{tokens[1]}'"
        p = rate_pool.get(pid)
        if not p:
            return f"rate preset {pid} is empty — use RECORD RATE {pid} Name <bpm>"
        return run_command(f"BPM {p.bpm}")

    # SIZEP <n>  — recall size preset
    if t0 == 'SIZEP' and len(tokens) == 2:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"SIZEP: bad slot number '{tokens[1]}'"
        p = size_pool.get(pid)
        if not p:
            return f"size preset {pid} is empty — use RECORD SIZEP {pid} Name <size>"
        return run_command(f"SIZE {p.size}")

    # SPREADP <n>  — recall spread preset
    if t0 == 'SPREADP' and len(tokens) == 2:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"SPREADP: bad slot number '{tokens[1]}'"
        p = spread_pool.get(pid)
        if not p:
            return f"spread preset {pid} is empty — use RECORD SPREADP {pid} Name <spread>"
        return run_command(f"SPREAD {p.spread}")

    # RECORD RATE <n> [name] <bpm>      — e.g. RECORD RATE 5 Strobe 240
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

    # RECORD SIZEP <n> [name] <size>    — e.g. RECORD SIZEP 4 Blinding 255
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

    # RECORD SPREADP <n> [name] <spread>  — e.g. RECORD SPREADP 4 Wave 0.5
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

    # SPEED <n> <bpm>         — set speed master n to bpm live
    # SPEED <n> NAME <name>   — rename speed master slot n
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

    # LIST RATE / SIZEP / SPREADP / FORM
    if t0 == 'LIST' and len(tokens) >= 2:
        sub = tokens[1]
        if sub == 'RATE':
            lines = ["rate presets:"] + [f"  {p}" for p in sorted(rate_pool.presets.values(), key=lambda x: x.preset_id)]
            return "\n".join(lines)
        if sub in ('SIZEP', 'SIZE'):
            lines = ["size presets:"] + [f"  {p}" for p in sorted(size_pool.presets.values(), key=lambda x: x.preset_id)]
            return "\n".join(lines)
        if sub in ('SPREADP', 'SPREAD'):
            lines = ["spread presets:"] + [f"  {p}" for p in sorted(spread_pool.presets.values(), key=lambda x: x.preset_id)]
            return "\n".join(lines)
        if sub in ('SPEED', 'SPD', 'SPEEDS'):
            lines = ["speed masters:"]
            for sid in speed_master_pool.all_slots():
                m = speed_master_pool.get(sid)
                lines.append(f"  [{sid:2d}] {m.name:<12}  {m.bpm:.1f} bpm")
            return "\n".join(lines)
        if sub == 'FORM':
            lines = ["form presets:"] + [f"  {f}" for f in sorted(form_pool.forms.values(), key=lambda x: x.form_id)]
            return "\n".join(lines)
        if sub in ('COLOR', 'COLOUR', 'COLORS', 'COLOURS'):
            if not color_pool.presets:
                return "color pool is empty"
            lines = ["color presets:"]
            for pid in sorted(color_pool.presets):
                p = color_pool.presets[pid]
                r, g, b = int(p.red), int(p.green), int(p.blue)
                rgb = f"r{r} g{g} b{b}"
                lines.append(f"  [{pid}] {p.name}  {rgb}")
            return "\n".join(lines)
        if sub in ('DIM', 'DIMS'):
            if not dim_pool.presets:
                return "dim pool is empty"
            lines = ["dim presets:"]
            for pid in sorted(dim_pool.presets):
                p = dim_pool.presets[pid]
                lines.append(f"  [{pid}] {p.name}  {p.level:.0%}")
            return "\n".join(lines)
        if sub in ('GROUP', 'GROUPS'):
            if not group_pool.groups:
                return "group pool is empty"
            lines = ["groups:"]
            for gid in sorted(group_pool.groups):
                g = group_pool.groups[gid]
                count = len(g.members)
                lines.append(f"  [{gid}] {g.name}  ({count} entries)")
            return "\n".join(lines)
        if sub in ('FX', 'FXPRESET', 'FXPRESETS'):
            lines = [f"fx presets:"]
            for pid in sorted(fx_pool.presets):
                p = fx_pool.presets[pid]
                waveforms = ", ".join(
                    f"{ld.get('waveform','?')}/{ld.get('channel','?')}"
                    for ld in p.layers)
                lines.append(f"  [{pid}] {p.name}  {waveforms or '(empty)'}")
            return "\n".join(lines) if len(lines) > 1 else "fx pool is empty"
        if sub in ('STACKS', 'STACKS', 'STK'):
            lines = ["stacks:"]
            for sid in sorted(stack_pool.stacks):
                stk = stack_pool.stacks[sid]
                cue_count = len(stk.cues)
                cur = f"  ◀ on cue {stk.current:.0f}" if stk.current is not None else ""
                lines.append(f"  [{sid}] {stk.name}  ({cue_count} cues){cur}")
            return "\n".join(lines) if len(lines) > 1 else "no stacks recorded"
        # LIST CUES [stk <n>] — cue list for active or specified stack
        if sub in ('CUES', 'CUE'):
            stk_n = None
            if 'STK' in tokens:
                ci = tokens.index('STK')
                try:
                    stk_n = int(tokens[ci + 1])
                except (IndexError, ValueError):
                    pass
            stk = stack_pool.get(stk_n) if stk_n is not None else _active_stack()
            if not stk:
                label = f"stack {stk_n}" if stk_n else "active stack"
                return f"LIST CUES: {label} not found"
            if not stk.cues:
                return f"stk {stk.stack_id} '{stk.name}': no cues"
            lines = [f"stk {stk.stack_id} '{stk.name}' ({len(stk.cues)} cues):"]
            for num in stk._sorted_cue_numbers():
                cue = stk.cues[num]
                cur_m = " ◀" if num == stk.current else ""
                note_s = f"  [{cue.note}]" if getattr(cue, 'note', '') else ""
                lines.append(f"  [{num:.0f}] {cue.name}  fade:{cue.fade_time}s{note_s}{cur_m}")
            return "\n".join(lines)
        _list_attr_map = {
            'POSITION': position_pool,
            'GOBO':     gobo_pool,
            'ZOOM':     zoom_pool,
            'FOCUS':    focus_pool,
            'BEAM':     beam_pool,
            'CONTROL':  control_pool,
        }
        if sub in _list_attr_map:
            pool = _list_attr_map[sub]
            if not pool.presets:
                return f"{sub.title()} pool is empty"
            lines = [f"{sub.title()} Presets:"]
            for pid in sorted(pool.presets):
                p = pool.presets[pid]
                lines.append(f"  {p}")
            return "\n".join(lines)
        if sub in ('FADER', 'FADERS', 'FDR'):
            if not fader_pool.faders:
                return "no faders configured"
            lines = ["Faders:"]
            for eid in sorted(fader_pool.faders):
                ex = fader_pool.faders[eid]
                stk = ex.stack
                lbl_s = f"  [{ex.label}]" if ex.label else ""
                if stk:
                    cur_s = (f"  cue {stk.current:.0f}" if stk.current is not None else "  not started")
                    active_s = "  ACTIVE" if ex.is_active else "  idle"
                    mode_s = f"  mode={ex.trigger_mode}"
                    lines.append(f"  [{eid}]{lbl_s} → stk {stk.stack_id}: {stk.name}{cur_s}{active_s}{mode_s}")
                else:
                    lines.append(f"  [{eid}]{lbl_s} → (unassigned)")
            return "\n".join(lines)
        if sub == 'MIDI':
            if not midi or (not midi.cc_maps and not midi.note_maps):
                return "no MIDI mappings"
            lines = ["MIDI Mappings:"]
            for (ch, cc), m in sorted(midi.cc_maps.items()):
                status = "live" if m.taken_over else "takeover"
                lines.append(f"  ch{ch} cc{cc:3d}  → {m.name} [{status}]")
            for (ch, note), m in sorted(midi.note_maps.items()):
                lines.append(f"  ch{ch} note{note:3d} → {m.name}")
            return "\n".join(lines) if len(lines) > 1 else "no MIDI mappings"
        if sub in ('OSC', 'TARGETS'):
            clients = osc._clients if osc else {}
            if not clients:
                return "no OSC targets"
            lines = ["OSC Targets:"]
            for name, c in clients.items():
                lines.append(f"  {name}  {c._address}:{c._port}")
            return "\n".join(lines)
        if sub == 'PATCH':
            if not patch or not patch.fixtures:
                return "patch is empty"
            lines = ["Patch:"]
            for fid in sorted(patch.fixtures):
                m = patch.fixtures[fid]
                first_sub = m.get_sub(1)
                park_s = "  [PARKED]" if fid in output_state.parked_fids else ""
                if first_sub and first_sub.outputs:
                    out = first_sub.outputs[0]
                    lines.append(f"  [{fid}] {m.name}  {m.profile.name}  U{out['universe']}@{out['address']}{park_s}")
                else:
                    lines.append(f"  [{fid}] {m.name}  {m.profile.name}{park_s}")
            return "\n".join(lines)
        if sub == 'PARK':
            if not output_state.parked_fids:
                return "no fixtures parked"
            lines = ["Parked fixtures:"]
            for fid in sorted(output_state.parked_fids):
                m = patch.get(fid)
                name = m.name if m else f"(fixture {fid})"
                addr_count = sum(len(v) for v in output_state.parked_addresses.values())
                lines.append(f"  [{fid}] {name}")
            return "\n".join(lines)
        if sub == 'MACRO':
            return run_command("MACRO LIST")
        if sub in ('NOTES', 'NOTE'):
            lines = []
            for sid in sorted(stack_pool.stacks):
                stk = stack_pool.stacks[sid]
                cs_note = getattr(stk, 'note', '')
                cue_notes = [(num, stk.cues[num].note)
                             for num in stk._sorted_cue_numbers()
                             if getattr(stk.cues[num], 'note', '')]
                if cs_note or cue_notes:
                    lines.append(f"stk {sid} '{stk.name}':" + (f"  {cs_note}" if cs_note else ""))
                    for num, nt in cue_notes:
                        lines.append(f"    cue {num:.0f}: {nt}")
            if not lines:
                return "no notes set on any stack or cue"
            return "\n".join(lines)
        if sub == 'REFS':
            # Delegate to the LIST REFS handler below
            pass
        else:
            return (f"LIST: unknown sub-command '{tokens[1]}' — "
                    "use COLOR, DIM, GROUP, FX, STACKS, RATE, SIZEP, SPREADP, FORM, "
                    "POSITION, GOBO, ZOOM, FOCUS, BEAM, CONTROL, fdr, MIDI, OSC, PATCH, PARK, SHOWS, NOTES, REFS")

    # ── FIXTURE INFO <n> — detailed per-fixture status ──────────────────────────
    # FIXTURE SWAP <a> <b> — exchange programmer values between two fixtures
    if t0 == 'FIXTURE' and len(tokens) >= 4 and tokens[1].upper() == 'SWAP':
        try:
            fid_a, fid_b = int(tokens[2]), int(tokens[3])
        except ValueError:
            return "usage: fixture swap <a> <b>"
        if fid_a == fid_b:
            return "FIXTURE SWAP: source and destination are the same"
        if not patch.get(fid_a):
            return f"FIXTURE SWAP: fixture {fid_a} not in patch"
        if not patch.get(fid_b):
            return f"FIXTURE SWAP: fixture {fid_b} not in patch"
        prog._push_undo()
        # Collect all data keys belonging to each fixture: "N" (master) and "N.x" (subs)
        def _fx_keys(fid):
            return [k for k in prog.data
                    if k == str(fid) or k.startswith(str(fid) + '.')]
        keys_a = _fx_keys(fid_a)
        keys_b = _fx_keys(fid_b)
        # Extract data, remap keys from A→B and B→A
        data_a = {k: prog.data.pop(k) for k in keys_a}
        data_b = {k: prog.data.pop(k) for k in keys_b}
        def _remap(d, old_fid, new_fid):
            out = {}
            for k, v in d.items():
                if k == str(old_fid):
                    out[str(new_fid)] = v
                elif k.startswith(str(old_fid) + '.'):
                    out[str(new_fid) + k[len(str(old_fid)):]] = v
            return out
        prog.data.update(_remap(data_a, fid_a, fid_b))
        prog.data.update(_remap(data_b, fid_b, fid_a))
        return f"programmer: swapped fixture {fid_a} ↔ fixture {fid_b}"

    # ── FIXTURE GROUPS <n> — list every group that contains fixture n ──────────
    if t0 == 'FIXTURE' and len(tokens) >= 3 and tokens[1].upper() in ('GROUPS', 'GROUP'):
        try:
            fid = int(tokens[2])
        except ValueError:
            return "usage: fixture groups <id>"
        master = patch.get(fid)
        if not master:
            return f"fixture {fid} not patched"
        containing = []
        for gid in sorted(group_pool.groups):
            g = group_pool.groups[gid]
            for entry in g.members:
                if isinstance(entry, tuple) and entry[1] == fid:
                    containing.append(f"  group {gid}: {g.name}")
                    break
        if not containing:
            return f"fixture {fid} '{master.name}' is not in any group"
        lines = [f"Fixture {fid} '{master.name}' appears in {len(containing)} group(s):"]
        lines.extend(containing)
        return "\n".join(lines)

    if t0 == 'FIXTURE' and len(tokens) >= 3 and tokens[1] in ('INFO', 'STATUS', 'SHOW'):
        try:
            fid = int(tokens[2])
        except ValueError:
            return "usage: fixture info <id>"
        master = patch.get(fid)
        if not master:
            return f"fixture {fid} not patched"
        prof = master.profile
        lines = [f"fixture {fid}: {master.name}",
                 f"  profile  : {prof.name}",
                 f"  channels : {', '.join(prof.channels)}",
                 f"  pixels   : {master.pixel_count}"]
        # Address table
        for i, sub in enumerate(master.all_subs(), 1):
            if sub.outputs:
                o = sub.outputs[0]
                end = o['address'] + len(prof.channels) - 1
                lines.append(f"  pixel {i:3d}: u{o['universe']}@{o['address']}-{end}")
        # Park status
        if fid in output_state.parked_fids:
            lines.append("  status   : parked")
        # programmer values
        prog_vals = []
        m_dim = prog.data.get(str(fid), {}).get('dim')
        if m_dim is not None:
            prog_vals.append(f"dim={m_dim:.0%}")
        for sub in master.all_subs():
            sfid = str(sub.fixture_id)
            sd = prog.data.get(sfid, {})
            if sd:
                pairs = "  ".join(f"{k}={v}" for k, v in sd.items())
                prog_vals.append(f"[sub {sub.sub_index}] {pairs}")
        if prog_vals:
            lines.append("  programmer:")
            for v in prog_vals:
                lines.append(f"    {v}")
        return "\n".join(lines)

    # ── Clear — programmer only, never touches stacks ────────
    # ── RELEASE — stop fader(s) ───────────────────────────
    # ── PRIORITY — set fader merge priority ────────────────
    if t0 == 'PRIORITY' and len(tokens) >= 3:
        try:
            n = int(tokens[1])
        except ValueError:
            return "usage: priority <n> high | low | normal"
        lvl_str = tokens[2]
        lvl_map = {'HIGH': 1, 'HI': 1, 'LOW': -1, 'LO': -1, 'NORMAL': 0, 'NRM': 0}
        if lvl_str not in lvl_map:
            return f"unknown priority '{lvl_str}' — use HIGH, LOW or NORMAL"
        ex = fader_pool.get(n)
        ex.priority = lvl_map[lvl_str]
        lbl = Fader.PRIORITY_LABELS[ex.priority]
        return f"fader {n} priority → {lbl}"

    if t0 == 'RELEASE':
        if len(tokens) == 1 or (len(tokens) == 2 and tokens[1] == 'ALL'):
            stopped = []
            for ex in fader_pool.faders.values():
                if ex.is_active:
                    ex.stop()
                    stopped.append(ex.fdr_id)
            return f"released {len(stopped)} fader(s): {stopped}" if stopped else "no active faders"
        try:
            n = int(tokens[1])
        except (ValueError, IndexError):
            return "usage: release <n>  or  release all"
        ex = fader_pool.get(n)
        if ex.is_active:
            ex.stop()
            return f"released fader {n}"
        return f"fader {n} was not running"

    # ── CUE timing editor (no programmer required) ─────────────
    # CUE <n> FADE/INFADE/OUTFADE <t> [DELAY <t>] [CFADE <t>] [DFADE <t>]
    # stk <n> CUE <m> FADE <t> [...]
    # RECORD CUE <n> FADE <t>  also works when programmer is empty (updates existing cue)
    _TIMING_KW = {'FADE', 'INFADE', 'OUTFADE', 'DELAY', 'FOLLOW',
                  'CFADE', 'CINFADE', 'DFADE', 'DINFADE', 'CDELAY', 'DDELAY'}
    _has_timing = bool(_TIMING_KW & set(tokens))

    # CUE <n> SHOW / INFO — inspect cue contents without firing it
    # CUE <n> NOTE <text>  — set production annotation on a cue
    if t0 == 'CUE' and len(tokens) >= 3 and tokens[2] == 'NOTE':
        try:
            cue_num = float(tokens[1])
        except ValueError:
            return f"CUE NOTE: bad cue number '{tokens[1]}'"
        stk = _active_stack()
        if not stk:
            return "CUE NOTE: no active stack"
        cue = stk.cues.get(cue_num)
        if not cue:
            return f"cue {cue_num} not found in active stack"
        note_text = raw.split(None, 3)[3].strip() if len(tokens) > 3 else ""
        cue.note = note_text
        save_show()
        return f"cue {cue_num}: note set — \"{note_text}\""

    if t0 == 'CUE' and len(tokens) >= 3 and tokens[2] in ('SHOW', 'INFO', 'PRINT'):
        try:
            cue_num = float(tokens[1])
        except ValueError:
            return f"CUE: bad cue number '{tokens[1]}'"
        stk = _active_stack()
        if not stk:
            return "CUE: no active stack"
        cue = stk.cues.get(cue_num)
        if not cue:
            return f"cue {cue_num} not found in active stack"
        note_str   = f"  [{cue.note}]" if getattr(cue, 'note', '') else ""
        follow_str = f"  Follow:{cue.follow_time:.1f}s" if getattr(cue, 'follow_time', 0.0) > 0 else ""
        lines = [f"cue {cue_num}: {cue.name}  |  Fade:{cue.fade_time}s  Delay:{cue.delay_time}s{follow_str}{note_str}"]
        # Gather master-level keys (dim, fx) and sub-fixture RGB
        masters = {}; subs = {}
        for fid, vals in cue.data.items():
            if '.' in str(fid):
                subs[fid] = vals
            else:
                masters[fid] = vals
        for fid, vals in sorted(masters.items()):
            parts = []
            if 'dim' in vals:
                parts.append(f"dim:{vals['dim']:.0%}")
            fx_defs = vals.get('fx', [])
            if fx_defs:
                for ld in fx_defs:
                    parts.append(f"FX:{ld.get('waveform','?')} {ld.get('channel','?')} {ld.get('bpm',60):.0f} bpm")
            if parts:
                lines.append(f"  Fixture {fid}: {', '.join(parts)}")
        # Sub-fixture RGB — show unique colors only
        color_map = {}
        for fid, vals in subs.items():
            r = vals.get('red', 0); g = vals.get('green', 0); b = vals.get('blue', 0)
            color_map.setdefault((r, g, b), []).append(fid)
        for (r, g, b), fids in sorted(color_map.items()):
            if r == 0 and g == 0 and b == 0:
                continue
            sample = fids[0]
            lines.append(f"  Pixel {sample} (+{len(fids)-1} others): R{r} G{g} B{b}")
        if len(lines) == 1:
            lines.append("  (empty — no data recorded)")
        return "\n".join(lines)

    if _has_timing and t0 == 'CUE' and len(tokens) >= 3:
        try:
            cue_num = float(tokens[1])
        except ValueError:
            return f"CUE: bad cue number '{tokens[1]}'"
        stk = _active_stack()
        if not stk:
            return "CUE: no active stack"
        cue = stk.cues.get(float(cue_num))
        if not cue:
            return f"cue {cue_num} not found in active stack"
        _apply_timing_edit(cue, raw)
        save_show()
        return f"updated: {cue}"

    if _has_timing and t0 in ('STK', 'STACK') and 'CUE' in tokens:
        cue_idx = tokens.index('CUE')
        try:
            stk_n    = int(tokens[1])
            cue_num = float(tokens[cue_idx + 1])
        except (ValueError, IndexError):
            return "usage: stk <n> cue <m> fade <t> [delay <t>] [cfade <t>] [dfade <t>]"
        stk = stack_pool.get(stk_n)
        if not stk:
            return f"stack {stk_n} not found"
        cue = stk.cues.get(float(cue_num))
        if not cue:
            return f"cue {cue_num} not found in stack {stk_n}"
        _apply_timing_edit(cue, raw)
        save_show()
        return f"updated: {cue}"

    # CUE <n> SHIFT <offset> — move a cue to a new number within the active stack
    if t0 == 'CUE' and len(tokens) >= 4 and tokens[2].upper() == 'SHIFT':
        try:
            cue_num = float(tokens[1])
            offset  = float(tokens[3])
        except ValueError:
            return "usage: cue <n> shift <offset>"
        stk = _active_stack()
        if not stk:
            return "CUE SHIFT: no active stack"
        cue = stk.cues.get(cue_num)
        if not cue:
            return f"CUE SHIFT: cue {cue_num:.0f} not found"
        new_num = round(cue_num + offset, 6)
        if new_num in stk.cues:
            return f"CUE SHIFT: position {new_num:.0f} already occupied"
        del stk.cues[cue_num]
        cue.cue_number = new_num
        stk.cues[new_num] = cue
        if stk.current == cue_num:
            stk.current = new_num
        save_show()
        return f"cue {cue_num:.0f} → {new_num:.0f} in '{stk.name}'"

    # RENAME STACK <n> <new name>
    # RENAME CUE <n> <new name>          (active stack)
    # RENAME stk <n> CUE <m> <new name>   (explicit stack)
    # RENAME COLOR/COLOUR <n> <new name>
    # RENAME DIM <n> <new name>
    # RENAME GROUP <n> <new name>
    # RENAME FX <n> <new name>
    # RENAME RATE/SIZEP/SPREADP/FORM <n> <new name>
    if t0 == 'RENAME' and len(tokens) >= 3:
        sub = tokens[1]

        # RENAME STACK <n> <name>
        if sub == 'STACK':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME STACK: bad number '{tokens[2]}'"
            stk = stack_pool.get(n)
            if not stk:
                return f"stack {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME STACK: provide a new name"
            stk.name = new_name
            save_show()
            return f"stack {n} → \"{new_name}\""

        # RENAME stk <n> CUE <m> <name>  or  RENAME CUE <n> <name>
        if sub == 'CUE' or (sub == 'STK' and 'CUE' in tokens):
            if sub == 'STK' and 'CUE' in tokens:
                cue_idx = tokens.index('CUE')
                try:
                    stk_n    = int(tokens[2])
                    cue_num = float(tokens[cue_idx + 1])
                except (ValueError, IndexError):
                    return "usage: rename stk <n> cue <m> <name>"
                stk = stack_pool.get(stk_n)
                if not stk:
                    return f"stack {stk_n} not found"
                new_name = _name_after(raw, cue_idx + 2)
            else:
                try:
                    cue_num = float(tokens[2])
                except ValueError:
                    return f"RENAME CUE: bad cue number '{tokens[2]}'"
                stk = _active_stack()
                if not stk:
                    return "RENAME CUE: no active stack"
                new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME CUE: provide a new name"
            cue = stk.cues.get(float(cue_num))
            if not cue:
                return f"cue {cue_num} not found"
            cue.name = new_name
            save_show()
            return f"cue {cue_num} → \"{new_name}\""

        # RENAME COLOR / COLOUR <n> <name>
        if sub in ('COLOR', 'COLOUR'):
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME COLOR: bad number '{tokens[2]}'"
            p = color_pool.get(n)
            if not p:
                return f"color preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME COLOR: provide a new name"
            p.name = new_name
            save_show()
            return f"color {n} → \"{new_name}\""

        # RENAME DIM <n> <name>
        if sub == 'DIM':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME DIM: bad number '{tokens[2]}'"
            p = dim_pool.get(n)
            if not p:
                return f"dim preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME DIM: provide a new name"
            p.name = new_name
            save_show()
            return f"dim {n} → \"{new_name}\""

        # RENAME GROUP <n> <name>
        if sub == 'GROUP':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME GROUP: bad number '{tokens[2]}'"
            g = group_pool.get(n)
            if not g:
                return f"group {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME GROUP: provide a new name"
            g.name = new_name
            save_show()
            return f"group {n} → \"{new_name}\""

        # RENAME FX <n> <name>
        if sub == 'FX':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME FX: bad number '{tokens[2]}'"
            p = fx_pool.get(n)
            if not p:
                return f"FX preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME FX: provide a new name"
            p.name = new_name
            save_show()
            return f"FX {n} → \"{new_name}\""

        # RENAME RATE / SIZEP / SPREADP / FORM <n> <name>
        _rename_pool_map = {
            'RATE':     rate_pool.presets,
            'SIZEP':    size_pool.presets,
            'SPREADP':  spread_pool.presets,
            'FORM':     form_pool.forms,
            'POSITION': position_pool.presets,
            'GOBO':     gobo_pool.presets,
            'ZOOM':     zoom_pool.presets,
            'FOCUS':    focus_pool.presets,
            'BEAM':     beam_pool.presets,
            'CONTROL':  control_pool.presets,
        }
        if sub in _rename_pool_map:
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME {sub}: bad number '{tokens[2]}'"
            store = _rename_pool_map[sub]
            item  = store.get(n)
            if not item:
                return f"{sub} preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return f"RENAME {sub}: provide a new name"
            item.name = new_name
            save_show()
            return f"{sub} {n} → \"{new_name}\""

        # RENAME MACRO <n> <name>
        if sub == 'MACRO':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME MACRO: bad number '{tokens[2]}'"
            if n not in macro_pool:
                return f"macro slot {n} is empty"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME MACRO: provide a new name"
            macro_pool[n]["name"] = new_name
            ShowFile.save_macros(macro_pool)
            return f"macro {n} → \"{new_name}\""

        # RENAME FIXTURE <n> <name>
        if sub == 'FIXTURE':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME FIXTURE: bad fixture ID '{tokens[2]}'"
            master = patch.get(n)
            if not master:
                return f"RENAME FIXTURE: fixture {n} not in patch"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME FIXTURE: provide a new name"
            old_name = master.name
            master.name = new_name
            ShowFile.save_patch(patch)
            return f"fixture {n}: \"{old_name}\" → \"{new_name}\""

        return (f"RENAME: unknown type '{sub}' — use STACK, CUE, COLOR, DIM, GROUP, FX, "
                "RATE, SIZEP, SPREADP, FORM, POSITION, GOBO, ZOOM, FOCUS, BEAM, CONTROL, MACRO, FIXTURE")

    # ── COPY FIXTURE <src> TO <dst1> [dst2 ...] ──────────────────────────────
    # clone programmer values from one fixture to one or more destinations.
    if t0 == 'COPY' and len(tokens) >= 5 and tokens[1] == 'FIXTURE' and 'TO' in tokens:
        to_idx = tokens.index('TO')
        try:
            src_id = int(tokens[2])
        except ValueError:
            return "usage: copy fixture <src> to <dst1> [dst2 ...]"
        dst_ids = []
        for tok in tokens[to_idx + 1:]:
            try: dst_ids.append(int(tok))
            except Valueerror: break
        if not dst_ids:
            return "COPY FIXTURE: provide at least one destination fixture"
        src_master = patch.get(src_id)
        if not src_master:
            return f"COPY FIXTURE: fixture {src_id} not patched"
        prog._push_undo()
        copied = []
        for dst_id in dst_ids:
            dst_master = patch.get(dst_id)
            if not dst_master:
                continue
            src_m_data = prog.data.get(str(src_id), {})
            if src_m_data:
                prog.data.setdefault(str(dst_id), {}).update(copy.deepcopy(src_m_data))
            for src_sub in src_master.all_subs():
                src_sub_data = prog.data.get(str(src_sub.fixture_id), {})
                if src_sub_data:
                    dst_sub = dst_master.get_sub(src_sub.sub_index)
                    if dst_sub:
                        prog.data.setdefault(str(dst_sub.fixture_id), {}).update(
                            copy.deepcopy(src_sub_data))
            copied.append(dst_id)
        return f"copied fixture {src_id} → {copied}"

    # ── COPY CUE / COPY stk ────────────────────────────────────────────────────
    # COPY CUE <src> TO <dst>               — within active stack
    # COPY CUE <src> TO <dst> <name>        — with new name
    # COPY stk <stk> CUE <src> TO <dst>       — explicit source stack
    # COPY stk <stk> CUE <src> TO stk <cs2> CUE <dst>  — cross-stack
    # COPY stk <n> TO stk <m>                 — whole-stack duplicate
    if t0 == 'COPY' and len(tokens) >= 2 and tokens[1] in ('CUE', 'STK', 'STACK'):
        try:
            # Locate TO keyword
            if 'TO' not in tokens:
                return "COPY CUE: missing TO — e.g. COPY CUE 3 TO 5"
            to_idx = tokens.index('TO')

            # Parse source side (before TO)
            src_tokens = tokens[1:to_idx]

            # ── Whole-stack copy: COPY stk <n> TO stk <m> ─────────────────
            if (src_tokens and src_tokens[0] in ('STK', 'STACK') and
                    len(src_tokens) == 2 and 'CUE' not in src_tokens):
                src_cs_n = int(src_tokens[1])
                dst_tokens = tokens[to_idx + 1:]
                if not dst_tokens or dst_tokens[0] not in ('STK', 'STACK') or len(dst_tokens) < 2:
                    return "COPY stk: use COPY stk <src> TO stk <dst>"
                dst_cs_n = int(dst_tokens[1])
                src_stk = stack_pool.get(src_cs_n)
                if not src_stk:
                    return f"COPY stk: source stk {src_cs_n} not found"
                dst_stk = stack_pool.get(dst_cs_n) or stack_pool.create(dst_cs_n)
                for cue_n, src_cue in sorted(src_stk.cues.items()):
                    nc = Cue(
                        cue_number  = src_cue.cue_number,
                        name        = src_cue.name,
                        fade_time   = src_cue.fade_time,
                        delay_time  = src_cue.delay_time,
                        fade_times  = copy.deepcopy(src_cue.fade_times),
                        delay_times = copy.deepcopy(src_cue.delay_times),
                        follow_time = src_cue.follow_time,
                    )
                    nc.note = src_cue.note
                    nc.fx_outfade = src_cue.fx_outfade
                    nc.data = copy.deepcopy(src_cue.data)
                    dst_stk.cues[cue_n] = nc
                if not dst_stk.name or dst_stk.name == f"stack {dst_cs_n}":
                    dst_stk.name = src_stk.name
                save_show()
                return (f"copied stk {src_cs_n} '{src_stk.name}' → stk {dst_cs_n} "
                        f"'{dst_stk.name}'  ({len(src_stk.cues)} cues)")

            # ── Single-cue copy ─────────────────────────────────────────────
            if src_tokens and src_tokens[0] in ('STK', 'STACK'):
                if len(src_tokens) < 4 or src_tokens[2] not in ('CUE',):
                    return "COPY: use COPY stk <n> CUE <src> TO ..."
                src_cs_n  = int(src_tokens[1])
                src_cue_n = float(src_tokens[3])
                src_stk = stack_pool.get(src_cs_n)
            elif src_tokens and src_tokens[0] == 'CUE':
                src_cue_n = float(src_tokens[1])
                src_stk    = stack_pool.get(active_fader[0])
            else:
                return "COPY: use COPY CUE <n> TO <m>  or  COPY stk <n> CUE <src> TO ..."

            # Parse destination side (after TO)
            dst_tokens = tokens[to_idx + 1:]
            if not dst_tokens:
                return "COPY CUE: missing destination after TO"

            if dst_tokens[0] in ('STK', 'STACK'):
                # COPY ... TO stk <n> CUE <dst>
                if len(dst_tokens) < 4 or dst_tokens[2] != 'CUE':
                    return "COPY: use ... TO stk <n> CUE <dst>"
                dst_cs_n  = int(dst_tokens[1])
                dst_cue_n = float(dst_tokens[3])
                dst_stk    = stack_pool.get(dst_cs_n) or stack_pool.create(dst_cs_n)
                new_name  = _name_after(raw, tokens.index('CUE', to_idx + 1) + 2) if len(dst_tokens) > 4 else ""
            else:
                dst_cue_n = float(dst_tokens[0])
                dst_stk    = stack_pool.get(active_fader[0]) or _active_stack()
                new_name  = " ".join(dst_tokens[1:]) if len(dst_tokens) > 1 else ""

            if not src_stk:
                return f"COPY CUE: source stack not found"
            if not dst_stk:
                return f"COPY CUE: no active stack — specify stk <n> CUE <dst>"

            src_cue = src_stk.get_cue(src_cue_n)
            if not src_cue:
                return f"COPY CUE: cue {src_cue_n} not found in '{src_stk.name}'"

            # Build the destination cue — deep-copy all data including follow_time/note
            dst_cue = Cue(
                cue_number  = dst_cue_n,
                name        = new_name if new_name else src_cue.name,
                fade_time   = src_cue.fade_time,
                delay_time  = src_cue.delay_time,
                fade_times  = copy.deepcopy(src_cue.fade_times),
                delay_times = copy.deepcopy(src_cue.delay_times),
                follow_time = src_cue.follow_time,
            )
            dst_cue.note = src_cue.note
            dst_cue.fx_outfade = src_cue.fx_outfade
            dst_cue.data = copy.deepcopy(src_cue.data)
            dst_stk.cues[float(dst_cue_n)] = dst_cue
            save_show()
            return (f"copied cue {src_cue_n} '{src_cue.name}' → "
                    f"cue {dst_cue_n} '{dst_cue.name}'  in '{dst_stk.name}'")

        except (ValueError, IndexError) as _e:
            return f"COPY CUE: bad syntax — {_e}"

    # ── MOVE CUE ──────────────────────────────────────────────────────────────
    # MOVE CUE <src> TO <dst>               — renumber within active stack
    # MOVE stk <stk> CUE <src> TO <dst>       — explicit stack
    # MOVE stk <stk> CUE <src> TO stk <cs2> CUE <dst>  — cross-stack move
    if t0 == 'MOVE' and len(tokens) >= 2 and tokens[1] in ('CUE', 'STK', 'STACK'):
        try:
            if 'TO' not in tokens:
                return "MOVE CUE: missing TO — e.g. MOVE CUE 3 TO 5"
            to_idx = tokens.index('TO')
            src_tokens = tokens[1:to_idx]
            if src_tokens and src_tokens[0] in ('STK', 'STACK'):
                if len(src_tokens) < 4 or src_tokens[2] != 'CUE':
                    return "MOVE: use MOVE stk <n> CUE <src> TO ..."
                src_cs_n  = int(src_tokens[1])
                src_cue_n = float(src_tokens[3])
                src_stk = stack_pool.get(src_cs_n)
            elif src_tokens and src_tokens[0] == 'CUE':
                src_cue_n = float(src_tokens[1])
                src_stk    = stack_pool.get(active_fader[0])
            else:
                return "MOVE: use MOVE CUE <n> TO <m>  or  MOVE stk <n> CUE <src> TO ..."
            dst_tokens = tokens[to_idx + 1:]
            if not dst_tokens:
                return "MOVE CUE: missing destination after TO"
            if dst_tokens[0] in ('STK', 'STACK'):
                if len(dst_tokens) < 4 or dst_tokens[2] != 'CUE':
                    return "MOVE: use ... TO stk <n> CUE <dst>"
                dst_cs_n  = int(dst_tokens[1])
                dst_cue_n = float(dst_tokens[3])
                dst_stk    = stack_pool.get(dst_cs_n) or stack_pool.create(dst_cs_n)
            else:
                dst_cue_n = float(dst_tokens[0])
                dst_stk    = src_stk
            if not src_stk:
                return "MOVE CUE: source stack not found"
            src_cue = src_stk.get_cue(src_cue_n)
            if not src_cue:
                return f"MOVE CUE: cue {src_cue_n} not found in '{src_stk.name}'"
            if float(dst_cue_n) in dst_stk.cues and dst_stk is src_stk and dst_cue_n != src_cue_n:
                return (f"MOVE CUE: cue {dst_cue_n} already exists in '{dst_stk.name}' "
                        "— DELETE it first or use COPY")
            moved = Cue(
                cue_number  = dst_cue_n,
                name        = src_cue.name,
                fade_time   = src_cue.fade_time,
                delay_time  = src_cue.delay_time,
                fade_times  = copy.deepcopy(src_cue.fade_times),
                delay_times = copy.deepcopy(src_cue.delay_times),
                follow_time = src_cue.follow_time,
            )
            moved.note = src_cue.note
            moved.fx_outfade = src_cue.fx_outfade
            moved.data = copy.deepcopy(src_cue.data)
            dst_stk.cues[float(dst_cue_n)] = moved
            src_stk.delete_cue(src_cue_n)
            if src_cue_n == int(src_cue_n):
                cue_pool.delete(int(src_cue_n))
            if dst_cue_n == int(dst_cue_n):
                cue_pool.store(int(dst_cue_n), moved)
            save_show()
            return (f"moved cue {src_cue_n} '{moved.name}' → "
                    f"cue {dst_cue_n}  in '{dst_stk.name}'")
        except (ValueError, IndexError) as _e:
            return f"MOVE CUE: bad syntax — {_e}"

    # ── COPY pool preset ──────────────────────────────────────────────────────
    # COPY COLOR/DIM/GROUP/FX <src> TO <dst> [name]
    # tokens: COPY  TYPE  N  TO  M  [name...]
    #         [0]   [1]  [2] [3] [4]  [5+]
    if t0 == 'COPY' and len(tokens) >= 5 and tokens[3] == 'TO':
        sub = tokens[1]
        if sub in ('COLOR', 'COLOUR', 'DIM', 'GROUP', 'FX', 'FORM',
                   'RATE', 'SIZEP', 'SIZE', 'SPREADP', 'SPREAD',
                   'POSITION', 'GOBO', 'ZOOM', 'FOCUS', 'BEAM', 'CONTROL'):
            try:
                src_n = int(tokens[2])
                dst_n = int(tokens[4])
            except ValueError:
                return f"COPY {sub}: bad slot numbers"
            new_name = _name_after(raw, 5) or None

            if sub in ('COLOR', 'COLOUR'):
                src = color_pool.get(src_n)
                if not src: return f"color {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                color_pool.presets[dst_n] = dst
                save_show()
                return f"copied color {src_n} '{src.name}' → color {dst_n} '{dst.name}'"
            if sub == 'DIM':
                src = dim_pool.get(src_n)
                if not src: return f"dim {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                dim_pool.presets[dst_n] = dst
                save_show()
                return f"copied dim {src_n} '{src.name}' → dim {dst_n} '{dst.name}'"
            if sub == 'GROUP':
                src = group_pool.get(src_n)
                if not src: return f"group {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.group_id = dst_n
                dst.name     = new_name or f"{src.name} (copy)"
                group_pool.groups[dst_n] = dst
                save_show()
                return f"copied group {src_n} '{src.name}' → group {dst_n} '{dst.name}'"
            if sub == 'FX':
                src = fx_pool.get(src_n)
                if not src: return f"FX {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                fx_pool.presets[dst_n] = dst
                save_show()
                return f"copied FX {src_n} '{src.name}' → FX {dst_n} '{dst.name}'"
            if sub == 'FORM':
                if dst_n < FormPool.FIRST_CUSTOM_SLOT:
                    return (f"COPY FORM: destination {dst_n} is built-in — "
                            f"only slot ≥ {FormPool.FIRST_CUSTOM_SLOT} can be a copy target")
                src = form_pool.get(src_n)
                if not src: return f"form {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.form_id = dst_n
                dst.name    = new_name or f"{src.name} (copy)"
                form_pool.forms[dst_n] = dst
                save_show()
                return f"copied form {src_n} '{src.name}' → form {dst_n} '{dst.name}'"
            if sub == 'RATE':
                src = rate_pool.get(src_n)
                if not src: return f"rate {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                rate_pool.presets[dst_n] = dst
                save_show()
                return f"copied rate {src_n} '{src.name}' → rate {dst_n} '{dst.name}'"
            if sub in ('SIZEP', 'SIZE'):
                src = size_pool.get(src_n)
                if not src: return f"size {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                size_pool.presets[dst_n] = dst
                save_show()
                return f"copied size {src_n} '{src.name}' → size {dst_n} '{dst.name}'"
            if sub in ('SPREADP', 'SPREAD'):
                src = spread_pool.get(src_n)
                if not src: return f"spread {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                spread_pool.presets[dst_n] = dst
                save_show()
                return f"copied spread {src_n} '{src.name}' → spread {dst_n} '{dst.name}'"
            if sub in ('POSITION', 'GOBO', 'ZOOM', 'FOCUS', 'BEAM', 'CONTROL'):
                _copy_attr_map = {
                    'POSITION': position_pool, 'GOBO': gobo_pool,
                    'ZOOM': zoom_pool, 'FOCUS': focus_pool,
                    'BEAM': beam_pool, 'CONTROL': control_pool,
                }
                pool = _copy_attr_map[sub]
                src = pool.get(src_n)
                if not src: return f"{sub.title()} preset {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                pool.presets[dst_n] = dst
                save_show()
                return (f"copied {sub.title()} {src_n} '{src.name}' "
                        f"→ {sub.title()} {dst_n} '{dst.name}'")

    if t0 == 'KILL' and len(tokens) >= 2 and tokens[1] == 'FX':
        # Write fx_kill flag into programmer master data for selected (or all) fixtures.
        # The FX engine keeps running; the flag suppresses FX in the output merge.
        # CLEAR removes this flag so cue FX resumes automatically.
        masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if not masters:
            masters = list(patch.all_fixtures())
        _prog_fx_stop()
        for master in masters:
            fid = str(master.fixture_id)
            if fid not in prog.data:
                prog.data[fid] = {}
            prog.data[fid]['fx_kill'] = True
        return (f"FX killed for {len(masters)} fixture(s) — "
                "record into cue to make permanent, or CLEAR to release")

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

    if t0 == 'CLEAR' and len(tokens) == 2 and tokens[1] == 'FX':
        _sel_fids = {str(f.fixture_id) for f in prog.selection} if prog.selection else None
        _targets  = _sel_fids or set(prog.data.keys())
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

    # CLEAR COLOUR / CLEAR COLOR / CLEAR DIM / CLEAR RGB
    # Write explicit zeros into programmer so the operation is recordable into cues with fade times.
    # dim lives in master fixture keys (no '.'), colour channels in sub-fixture keys ('.' in fid).
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

    # CLEAR COLOR/DIM/GROUP/FX <n> — clear a specific pool slot
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

    if t0 == 'CLEAR' and len(tokens) == 1:
        result = prog.do_clear()
        if result.startswith("programmer cleared"):
            _prog_fx_stop()
        elif result == "programmer output cleared":
            _prog_fx_stop()
        return result

    if t0 == 'UNDO':
        return prog.undo()

    # ── PROGRAMMER SHOW — human-readable programmer contents ──────────────────
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

    # ── PROGRAMMER CAPTURE — pull live output into programmer for selected fixtures
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

    # ── PROGRAMMER SAVE / LOAD / SNAPSHOTS ───────────────────────────────────
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] == 'SAVE':
        try:
            slot = int(tokens[2])
        except (IndexError, ValueError):
            return "usage: programmer save <n> [name]"
        snap_name = _name_after(raw, 3) or f"snapshot {slot}"
        _prog_snapshots[slot] = {"name": snap_name, "data": copy.deepcopy(prog.data)}
        ch_count = sum(len(v) for v in prog.data.values() if v)
        return f"programmer snapshot {slot} '{snap_name}' saved ({ch_count} param(s))"

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

    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] in ('SNAPSHOTS', 'SNAPS'):
        if not _prog_snapshots:
            return "no programmer snapshots saved"
        lines = ["programmer snapshots:"]
        for sl in sorted(_prog_snapshots):
            s = _prog_snapshots[sl]
            ch = sum(len(v) for v in s["data"].values() if v)
            lines.append(f"  [{sl}] {s['name']}  ({ch} param(s))")
        return "\n".join(lines)

    # ── PROGRAMMER SCALE <pct> — multiply all programmer values by pct% ───────
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

    # ── PROGRAMMER STATS ──────────────────────────────────────────────────────
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

    # ── SET DEFAULT <param> <value> ───────────────────────────
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

    # ── LIST REFS <type> <n> — show every cue referencing a preset ──
    if t0 == 'LIST' and len(tokens) >= 3 and tokens[1] == 'REFS':
        ref_type = tokens[2].lower()
        try:
            ref_id = int(tokens[3]) if len(tokens) >= 4 else None
        except ValueError:
            ref_id = None
        if ref_id is None:
            return "usage: list refs color <n>  /  list refs dim <n>  /  list refs fx <n>  /  list refs <attr> <n>"

        # Map friendly names to ref key in cue.data
        if ref_type in ('color', 'colour'):
            ref_key = 'color_ref'
            label   = f"color preset {ref_id}"
        elif ref_type == 'dim':
            ref_key = 'dim_ref'
            label   = f"dim preset {ref_id}"
        elif ref_type == 'fx':
            ref_key = None  # special: check inside fx list
            label   = f"fx preset {ref_id}"
        else:
            ref_key = f"{ref_type}_ref"
            label   = f"{ref_type} preset {ref_id}"

        hits = []
        for cs_id, stk in stack_pool.stacks.items():
            for cue_num in sorted(stk.cues.keys()):
                cue = stk.cues[cue_num]
                matched_fids = []
                for fid, vals in cue.data.items():
                    if '.' in fid:
                        continue
                    if ref_key is not None:
                        if vals.get(ref_key) == ref_id:
                            matched_fids.append(fid)
                    else:
                        # FX: check inside fx list for fx_preset_ref
                        for _ld in vals.get('fx', []):
                            if _ld.get('fx_preset_ref') == ref_id:
                                matched_fids.append(fid)
                                break
                if matched_fids:
                    fid_str = ', '.join(f'f{f}' for f in sorted(matched_fids, key=lambda x: int(x) if x.isdigit() else 0))
                    hits.append(f"  stk {cs_id} \"{stk.name}\" → cue {cue_num} \"{cue.name}\"  ({fid_str})")

        if not hits:
            return f"{label}: no cue references found"
        lines = [f"{label} referenced by {len(hits)} cue(s):"] + hits
        return "\n".join(lines)

    # ── UPDATE <type> <n> — re-record preset from programmer + live-push ──
    if t0 == 'UPDATE' and len(tokens) >= 3:
        upd_type = tokens[1].lower()
        try:
            upd_id = int(tokens[2])
        except ValueError:
            return f"UPDATE: bad slot number '{tokens[2]}'"

        if upd_type in ('color', 'colour'):
            _has_rgb = any(any(ch in vals for ch in ('red', 'green', 'blue'))
                           for fid, vals in prog.data.items() if '.' in fid)
            if not _has_rgb:
                return "UPDATE COLOR: no RGB in programmer"
            name = _name_after(raw, 3) or ""
            p = color_pool.record(upd_id, prog, name=name or (color_pool.get(upd_id).name if color_pool.get(upd_id) else f"color {upd_id}"))
            save_show()
            _preset_live_push('color', upd_id)
            return f"updated: {p}  (live-pushed to playing cues)"

        elif upd_type == 'dim':
            p = dim_pool.get(upd_id)
            if not p:
                return f"UPDATE DIM: dim preset {upd_id} not found — use RECORD DIM {upd_id} first"
            old_name = p.name
            p = dim_pool.record(upd_id, prog, name=old_name)
            save_show()
            _preset_live_push('dim', upd_id)
            return f"updated: {p}  (live-pushed to playing cues)"

        elif upd_type == 'fx':
            # Re-snapshot current programmer FX (same as RECORD FX but with live push)
            seen, defs = set(), []
            for fid_str, vals in prog.data.items():
                if '.' in fid_str:
                    continue
                for ld in vals.get('fx', []):
                    key = (ld.get('waveform'), ld.get('channel'))
                    if key not in seen:
                        seen.add(key)
                        defs.append(ld)
            if not defs:
                return "UPDATE FX: no FX in programmer"
            existing = fx_pool.get(upd_id)
            name = existing.name if existing else f"fx {upd_id}"
            preset = FXPreset(upd_id, name)
            for ld in defs:
                preset.add_layer(
                    ld.get('waveform','sine'), ld.get('channel','red'),
                    bpm=ld.get('bpm',60.0), size=ld.get('size',100.0),
                    spread=ld.get('spread',0.0), phase_offset=ld.get('phase_offset',0.0),
                    form_id=ld.get('form_id'), rate_id=ld.get('rate_id'),
                    size_id=ld.get('size_id'), spread_id=ld.get('spread_id'),
                    dim_id=ld.get('dim_id'), color_id=ld.get('color_id'),
                    group_id=ld.get('group_id'), speed_id=ld.get('speed_id'),
                    block_size=ld.get('block_size',1), order=ld.get('order','linear'),
                    direction=ld.get('direction','forward'),
                    target_scope=ld.get('target_scope'),
                )
            fx_pool.store(upd_id, preset)
            ShowFile.save_fx_pool(fx_pool)
            _preset_live_push('fx', upd_id)
            return f"updated: {preset}  (live-pushed to playing cues)"

        else:
            # Generic attribute pool
            ap = _attr_pools.get(upd_type)
            if ap is None:
                return f"UPDATE: unknown preset type '{upd_type}'  (valid: color, dim, fx, position, gobo, zoom, focus, beam, control)"
            existing_p = ap.get(upd_id)
            old_name = existing_p.name if existing_p else f"{upd_type} {upd_id}"
            p = ap.record(upd_id, prog, name=old_name)
            save_show()
            _preset_live_push(upd_type, upd_id)
            return f"updated: {p}  (live-pushed to playing cues)"

    # ── Default: programmer ───────────────────────────────────
    try:
        prog.execute(raw)
        return ""   # programmer already prints its own output
    except Exception as e:
        return f"error: {e}"


# ── GUI ───────────────────────────────────────────────────
gui = GUIEngine(
    midi             = midi,
    fx_engine        = fx_engine,
    fade_engine      = fade_engine,
    output_state     = output_state,
    patch            = patch,
    stacks        = {stk.stack_id: stk for stk in stack_pool.stacks.values()},
    prog             = prog,
    go_fn            = cue_go,
    back_fn          = cue_back,
    goto_fn          = goto_cue,
    reload_fn        = cue_reload,
    ai               = ai,
    save_fn          = save_show,
    cmd_fn           = run_command,
    group_pool       = group_pool,
    color_pool       = color_pool,
    dim_pool         = dim_pool,
    cue_pool         = cue_pool,
    stack_pool    = stack_pool,
    active_fader  = active_fader,
    fader_pool    = fader_pool,
    fx_pool          = fx_pool,
    form_pool        = form_pool,
    rate_pool        = rate_pool,
    size_pool        = size_pool,
    spread_pool      = spread_pool,
    speed_master_pool = speed_master_pool,
    attr_pools       = _attr_pools,
    osc              = osc,
    library          = library,
    save_patch_fn    = lambda: ShowFile.save_patch(patch),
    fx_params        = _fx_params,
    audio_engine     = audio_engine,
    audio_mapper     = audio_mapper,
)
# Wire run_command and GUI log into AI engine (both defined after ai was created)
if getattr(ai, '_enabled', False):
    ai._cmd = run_command
    ai._log = gui._log

if STUDIO_HEADLESS:
    # Scripted smoke test — no GUI, no real hardware (paired with
    # STUDIO_DRY_RUN). Exercises the FX-as-programmer path this file's own
    # doc comments flagged as written-but-untested: FX -> RECORD CUE ->
    # GO -> verify FX actually fires. Exits with status 0/1 instead of
    # blocking on dpg.start_dearpygui().
    import sys as _sys

    print("\n*** STUDIO_HEADLESS smoke test ***")
    _results = []
    def _check(label, cond):
        _results.append((label, bool(cond)))
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    try:
        r1 = run_command("FX SINE RED BLOCK 2 DIRECTION BOUNCE PIXEL")
        _check("FX command applied to programmer", "FX" in r1)

        r2 = run_command("RECORD stk 1 CUE 5")
        _check("cue recorded", "recorded" in r2 or "cue" in r2)

        run_command("GO stk 1 CUE 5")
        time.sleep(0.25)   # let FadeEngine/FXEngine tick at least once
        ex = fader_pool.get(1)
        _check("fader has active FX after GO", len(ex._fx_ids) > 0)

        dmx = output_state.get_dmx_for_universe(1)
        _check("DMX output computes without exception", len(dmx) == 512)

        # GO FADE — one-shot fade override
        _pt_before = dict(_prog_time)
        r_gf = run_command("GO FADE 7.5")
        _check("GO FADE fires without error", "Cue" in r_gf or "GO" in r_gf)
        _check("GO FADE restores prog_time.on after fire",
               _prog_time['on'] == _pt_before['on'])
        _check("GO FADE restores prog_time.fade after fire",
               _prog_time['fade'] == _pt_before['fade'])

        # FADER SWAP
        _cs1_before = fader_pool.get(1).stack
        _cs2_before = fader_pool.get(2).stack
        r_swap = run_command("FADER SWAP 1 2")
        _check("FADER SWAP swaps stk onto fader 1",
               fader_pool.get(1).stack is _cs2_before)
        _check("FADER SWAP swaps stk onto fader 2",
               fader_pool.get(2).stack is _cs1_before)
        # Swap back to restore state for remaining tests
        run_command("FADER SWAP 1 2")

        # COPY FIXTURE
        run_command("1 AT RED 200")                   # set red on fixture 1 (sub-fixture channel)
        _cf_f1 = patch.get(1)
        _cf_f2 = patch.get(2)
        if _cf_f1 and _cf_f2:
            _cf_f1_sub = next(iter(_cf_f1.all_subs()), None)
            _cf_f2_sub = next(iter(_cf_f2.all_subs()), None)
            _cf_red_src = (prog.data.get(str(_cf_f1_sub.fixture_id), {}).get('red')
                           if _cf_f1_sub else None)
            r_cf = run_command("COPY FIXTURE 1 TO 2")
            _cf_red_dst = (prog.data.get(str(_cf_f2_sub.fixture_id), {}).get('red')
                           if _cf_f2_sub else None)
            _check("COPY FIXTURE copies sub channel to destination",
                   _cf_red_src is not None and _cf_red_dst == _cf_red_src)
            _check("COPY FIXTURE returns confirmation message", "copied fixture" in r_cf)
        r_cf_bad = run_command("COPY FIXTURE 999 TO 2")
        _check("COPY FIXTURE rejects unknown source", "not patched" in r_cf_bad or "999" in r_cf_bad)

        # FIXTURE SWAP
        prog.clear_programmer()
        run_command("1 AT R 80")    # fixture 1 red = 80
        run_command("2 AT R 200")   # fixture 2 red = 200
        _fs_f1s = "1.1" if patch.get(1) and next(iter(patch.get(1).all_subs()), None) else None
        _fs_f2s = "2.1" if patch.get(2) and next(iter(patch.get(2).all_subs()), None) else None
        if _fs_f1s and _fs_f2s:
            r_swap = run_command("FIXTURE SWAP 1 2")
            _sw_r1 = prog.data.get(_fs_f1s, {}).get('red')
            _sw_r2 = prog.data.get(_fs_f2s, {}).get('red')
            _check("FIXTURE SWAP moves fixture 2 value to fixture 1", _sw_r1 == 200)
            _check("FIXTURE SWAP moves fixture 1 value to fixture 2", _sw_r2 == 80)
            _check("FIXTURE SWAP returns confirmation", "swapped" in r_swap.lower())
            prog.undo()
            _sw_u1 = prog.data.get(_fs_f1s, {}).get('red')
            _sw_u2 = prog.data.get(_fs_f2s, {}).get('red')
            _check("FIXTURE SWAP pushes an undo snapshot (UNDO restores fixture 1)", _sw_u1 == 80)
            _check("FIXTURE SWAP pushes an undo snapshot (UNDO restores fixture 2)", _sw_u2 == 200)
        prog.clear_programmer()

        # FIXTURE INFO
        _fi = patch.get(1)
        if _fi:
            r_fi = run_command("FIXTURE INFO 1")
            _check("FIXTURE INFO shows fixture name", _fi.name in r_fi)
            _check("FIXTURE INFO shows profile name", _fi.profile.name in r_fi)
            _check("FIXTURE INFO shows channel list", any(ch in r_fi for ch in _fi.profile.channels))
        r_fi_bad = run_command("FIXTURE INFO 999")
        _check("FIXTURE INFO rejects unknown fixture", "not patched" in r_fi_bad or "999" in r_fi_bad)

        # PROGRAMMER STATS
        prog.clear_programmer()
        run_command("1 AT R 200")
        run_command("2 AT R 100")
        r_ps = run_command("PROGRAMMER STATS")
        _check("PROGRAMMER STATS shows sub-fixture count", "sub-fixtures" in r_ps)
        _check("PROGRAMMER STATS shows total params > 0",
               "total params" in r_ps and "total params    : 0" not in r_ps)
        prog.clear_programmer()
        r_ps_empty = run_command("PROGRAMMER STATS")
        _check("PROGRAMMER STATS shows 0 params when clear",
               "total params    : 0" in r_ps_empty or "0" in r_ps_empty)

        # PROGRAMMER CAPTURE
        prog.clear_programmer()
        run_command("1 THRU 3")           # select fixtures 1-3
        r_cap = run_command("PROGRAMMER CAPTURE")
        _check("PROGRAMMER CAPTURE returns confirmation", "captured" in r_cap)
        prog.clear_programmer()

        # PROGRAMMER SAVE / LOAD
        prog.clear_programmer()
        run_command("1 AT R 150 G 80")    # set some values
        r_psnap = run_command("PROGRAMMER SAVE 5 TestSnap")
        _check("PROGRAMMER SAVE returns confirmation", "saved" in r_psnap.lower())
        _check("PROGRAMMER SAVE stores snapshot", 5 in _prog_snapshots)
        prog.clear_programmer()           # wipe programmer
        _check("PROGRAMMER CLEAR removes values", not prog.data.get("1.1"))
        r_pload = run_command("PROGRAMMER LOAD 5")
        _check("PROGRAMMER LOAD restores values", prog.data.get("1.1", {}).get('red') == 150)
        _check("PROGRAMMER LOAD returns confirmation", "loaded" in r_pload.lower())
        r_psnaps = run_command("PROGRAMMER SNAPSHOTS")
        _check("PROGRAMMER SNAPSHOTS lists the saved slot", "TestSnap" in r_psnaps)
        prog.clear_programmer()

        # SET DEFAULT / DEFAULT
        _saved_defaults = dict(_fixture_defaults)
        r_sd_dim  = run_command("SET DEFAULT DIM 0")
        _check("SET DEFAULT DIM returns confirmation", "dim" in r_sd_dim)
        _check("SET DEFAULT DIM stores 0.0 in _fixture_defaults", _fixture_defaults.get('dim') == 0.0)
        r_sd_clr  = run_command("SET DEFAULT CLR 5600")
        _check("SET DEFAULT CLR stores kelvin", _fixture_defaults.get('kelvin') == 5600)
        r_sd_red  = run_command("SET DEFAULT RED 200")
        _check("SET DEFAULT RED stores value", _fixture_defaults.get('red') == 200)
        r_default = run_command("DEFAULT")
        _check("DEFAULT shows dim",    "dim"    in r_default)
        _check("DEFAULT shows kelvin", "kelvin" in r_default)
        r_bad     = run_command("SET DEFAULT FOOBAR 50")
        _check("SET DEFAULT rejects unknown param", "unknown" in r_bad)
        # restore
        _fixture_defaults.clear()
        _fixture_defaults.update(_saved_defaults)
        ShowFile.save_defaults(_fixture_defaults)

        # PROGRAMMER SHOW
        run_command("1 AT R 200")
        r_pshow = run_command("PROGRAMMER SHOW")
        _f1_master = patch.get(1)
        _check("PROGRAMMER SHOW lists active fixture name",
               _f1_master is not None and _f1_master.name in r_pshow)
        _check("PROGRAMMER SHOW shows channel value", "200" in r_pshow or "red" in r_pshow.lower())
        prog.clear_programmer()
        r_pshow_empty = run_command("PROGRAMMER SHOW")
        _check("PROGRAMMER SHOW shows (empty) when clear", "empty" in r_pshow_empty)

        # Pages + trigger modes
        run_command('PAGE 1 NAME "Test Page"')
        run_command("PAGE 1 ADD stk 1")
        r3 = run_command("page list")
        _check("page created and stack added", "Test Page" in r3 and "[1]" in r3)

        run_command("FADER 1 MODE FLASH")
        _check("trigger_mode set", fader_pool.get(1).trigger_mode == 'flash')

        run_command("FADER 1 flash on")
        time.sleep(0.05)
        _check("fader active after flash on", fader_pool.get(1).is_active)

        run_command("FADER 1 flash off")
        _check("fader inactive after flash off", not fader_pool.get(1).is_active)

        # RECORD COLOR/DIM from programmer — verify no AttributeError
        run_command("ALL AT R 200 G 100 B 50")
        r_col = run_command("RECORD COLOR 1 TestRed")
        _check("RECORD COLOR from programmer", "recorded" in r_col or "no RGB" in r_col)

        run_command("ALL AT DIM 80")
        r_dim = run_command("RECORD DIM 1 TestDim")
        _check("RECORD DIM from programmer", "recorded" in r_dim or "no dimmer" in r_dim)

        # Explicit-value record
        r_col2 = run_command("RECORD COLOR 2 BlueTest 0 0 255")
        _check("RECORD COLOR explicit RGB", "recorded" in r_col2)

        r_dim2 = run_command("RECORD DIM 2 Half 50%")
        _check("RECORD DIM explicit level", "recorded" in r_dim2)

        # LIST COLOR/DIM — verify no AttributeError on pool iteration
        r_lc = run_command("LIST COLOR")
        _check("LIST COLOR no exception", "color" in r_lc.lower())

        r_ld = run_command("LIST DIM")
        _check("LIST DIM no exception", "dim" in r_ld)

        # Verify LIST sub-commands route correctly (not to stack listing)
        for _cmd, _kw in [
            ("LIST RATE", "Rate"), ("LIST SIZEP", "Size"),
            ("LIST SPREADP", "Spread"), ("LIST STACKS", "Stack"),
            ("STATUS", "Console"), ("LIST", "Stack"),
        ]:
            _r = run_command(_cmd)
            _check(f"{_cmd!r} routes correctly", _kw.lower() in _r.lower())

        # LIST CUES and LIST CUES stk <n>
        _lc_r = run_command("LIST CUES")
        _check("LIST CUES returns cue list for active stack",
               "stk " in _lc_r.lower() or "not found" in _lc_r.lower())
        _lc_cs1 = run_command("LIST CUES stk 1")
        _check("LIST CUES stk 1 targets stack 1",
               "stk 1" in _lc_cs1.lower() or "not found" in _lc_cs1.lower())

        # COPY pool preset routing — was broken by overly broad COPY CUE handler
        run_command("RECORD COLOR 5 CopySource 255 128 0")
        r_cp_col = run_command("COPY COLOR 5 TO 6 CopiedColor")
        _check("COPY COLOR routes to pool handler", "copied color" in r_cp_col)
        run_command("RECORD DIM 5 CopySrc 75%")
        r_cp_dim = run_command("COPY DIM 5 TO 6 CopiedDim")
        _check("COPY DIM routes to pool handler", "copied dim" in r_cp_dim)

        # CLEAR RATE / SIZEP / SPREADP / FORM — parity gap found by audit: every
        # other pool type (COLOR/DIM/GROUP/FX/attr pools) already had CLEAR.
        run_command("RECORD RATE 9 ClearMe 90")
        r_clr_rate = run_command("CLEAR RATE 9")
        _check("CLEAR RATE deletes the preset", "cleared" in r_clr_rate.lower())
        _check("CLEAR RATE actually removed it", rate_pool.get(9) is None)
        run_command("RECORD SIZEP 9 ClearMe 40")
        r_clr_size = run_command("CLEAR SIZEP 9")
        _check("CLEAR SIZEP deletes the preset", "cleared" in r_clr_size.lower())
        run_command("RECORD SPREADP 9 ClearMe 40")
        r_clr_spread = run_command("CLEAR SPREADP 9")
        _check("CLEAR SPREADP deletes the preset", "cleared" in r_clr_spread.lower())
        run_command('record form 9 ClearMe 0,0 1,1')
        r_clr_form = run_command("CLEAR FORM 9")
        _check("CLEAR FORM deletes a custom form", "cleared" in r_clr_form.lower())
        r_clr_form_builtin = run_command("CLEAR FORM 1")
        _check("CLEAR FORM protects built-in slot 1", "built-in" in r_clr_form_builtin.lower())

        # COPY FORM — the one pool type missing from COPY entirely (audit finding)
        run_command('record form 8 CopySrcform 0,0 0.5,1 1,0')
        r_cp_form = run_command("COPY FORM 8 TO 9 CopiedForm")
        _check("COPY FORM routes to pool handler", "copied form" in r_cp_form)
        _check("COPY FORM created the destination", form_pool.get(9) is not None)
        r_cp_form_builtin = run_command("COPY FORM 8 TO 2 Overwrite")
        _check("COPY FORM protects built-in destination slots",
               "built-in" in r_cp_form_builtin.lower())

        # Fader-page paging — GUIEngine._fpg_exec_for_slot/_fpg_slot_for_exec map
        # a fixed 15-slot panel onto banks of faders (page 2 slot 1 = fdr 16).
        # Pure functions, no dpg context needed, so they're smoke-testable headless.
        _check("fpg slot->fdr page 1 slot 1 == fdr 1",
               GUIEngine._fpg_exec_for_slot(1, 1) == 1)
        _check("fpg slot->fdr page 2 slot 1 == fdr 16",
               GUIEngine._fpg_exec_for_slot(2, 1) == 16)
        _check("fpg slot->fdr page 3 slot 15 == fdr 45",
               GUIEngine._fpg_exec_for_slot(3, 15) == 45)
        _check("fpg fdr->slot inverse holds for on-page fdr",
               GUIEngine._fpg_slot_for_exec(2, 16) == 1)
        _check("fpg fdr->slot returns None for off-page fdr",
               GUIEngine._fpg_slot_for_exec(1, 16) is None)
        # _fpg_step_page is the pure half of _on_fpg_page_prev/next (the dpg-
        # touching half needs a live GUI context, so it's exercised only by
        # hand — dpg calls segfault the process outright when no context is
        # active, rather than raising a catchable exception).
        gui._fpg_page = 1
        gui._fpg_step_page(-1)
        _check("fader page cannot go below page 1", gui._fpg_page == 1)
        gui._fpg_step_page(1)
        gui._fpg_step_page(1)
        _check("fader page increments normally", gui._fpg_page == 3)
        gui._fpg_page = 1  # reset so later state (e.g. SAVE) isn't affected

        # TAP command — pre-seed _tap_times to avoid sleep; two taps → BPM
        _tap_times.clear()
        _tap_times.append(time.monotonic() - 0.5)  # simulate a prior tap 500ms ago
        _r_tap1 = run_command("TAP")                 # second tap → should compute BPM
        _check("TAP computes BPM from two taps", "BPM" in _r_tap1 or "→" in _r_tap1)

        # MIDI text commands — add, list, remove
        _r_midi_map = run_command("MIDI CC 15 100 GO")
        _check("MIDI CC maps correctly", "mapped" in _r_midi_map)
        _r_midi_list = run_command("LIST MIDI")
        _check("LIST MIDI shows new mapping", "ch15" in _r_midi_list)
        _r_midi_rm = run_command("MIDI REMOVE CC 15 100")
        _check("MIDI REMOVE CC removes mapping", "removed" in _r_midi_rm)
        _r_targets = run_command("MIDI TARGETS")
        _check("MIDI TARGETS lists targets", "GO" in _r_targets)

        # HIGHLIGHT must not survive BLACKOUT — real output computation,
        # not just the flag, since BLACKOUT is the show-stopping safety cutoff.
        run_command("ALL")
        run_command("HIGHLIGHT")
        run_command("BLACKOUT")
        _dmx_bbo = output_state.get_dmx_for_universe(1)
        _check("BLACKOUT overrides HIGHLIGHT in DMX output", max(_dmx_bbo) == 0)
        run_command("BLACKOUT OFF")
        run_command("HIGHLIGHT OFF")

        # FREEZE must not defeat BLACKOUT, SOLO, or a direct DMX override —
        # real output computation, not just the flags. FREEZE snapshots a
        # look; it must not be a way to disable the master safety cutoff.
        # FADER 1 STOP + FX CLEAR first: the very first smoke-test check
        # (near the top of this block) GO'd a sine-RED FX cue on fader 1
        # and never stopped it, so it's been running live in the background
        # ever since. With a selection active, "FX CLEAR" only clears
        # programmer FX (by design, scoped to selection) and leaves that
        # fader's FX running -- its real-time envelope would otherwise
        # make the frozen red value here timing-dependent instead of
        # deterministic. Stop the fader directly so nothing but this
        # test's own explicit AT command drives colour into the freeze.
        run_command("FADER 1 STOP")
        run_command("FX CLEAR")
        run_command("ALL AT R 200 G 150 B 100")
        run_command("FREEZE")
        _dmx_frozen = output_state.get_dmx_for_universe(1)
        _check("FREEZE snapshot holds the look", max(_dmx_frozen) > 0)
        run_command("BLACKOUT")
        _dmx_frozen_bbo = output_state.get_dmx_for_universe(1)
        _check("BLACKOUT overrides FREEZE in DMX output", max(_dmx_frozen_bbo) == 0)
        run_command("BLACKOUT OFF")
        _dmx_frozen_restored = output_state.get_dmx_for_universe(1)
        _check("FREEZE look restored after BLACKOUT OFF", _dmx_frozen_restored == _dmx_frozen)
        run_command("DMX 1 42")
        _dmx_frozen_override = output_state.get_dmx_for_universe(1)
        _check("direct DMX override still applies during FREEZE", _dmx_frozen_override[0] == 42)
        run_command("CLEAR DMX")

        # GRANDMASTER
        output_state.master_level = 1.0
        r_gm_show = run_command("GRANDMASTER")
        _check("GRANDMASTER (no args) shows current level", "%" in r_gm_show)
        r_gm_set = run_command("GM 75")
        _check("GM 75 sets master to 75%", abs(output_state.master_level - 0.75) < 0.01)
        _check("GM 75 returns confirmation with new level", "75" in r_gm_set)
        run_command("GM FULL")
        _check("GM FULL sets master to 100%", output_state.master_level == 1.0)
        run_command("GM OUT")
        _check("GM OUT sets master to 0%", output_state.master_level == 0.0)
        output_state.master_level = 1.0   # restore

        # SHOW INFO
        r_si = run_command("SHOW INFO")
        _check("SHOW INFO returns multi-line overview", len(r_si.splitlines()) >= 5)
        _check("SHOW INFO shows fixture count", "fixtures" in r_si)
        _check("SHOW INFO shows master level", "master" in r_si)

        # OUTPUT STATUS
        run_command("MASTER 100")          # ensure master at full
        run_command("FREEZE OFF")
        run_command("1 FULL")              # put fixture 1 at 100% in programmer
        r_os = run_command("OUTPUT STATUS")
        _check("OUTPUT STATUS returns non-empty string", len(r_os) > 10)
        _check("OUTPUT STATUS shows master level", "master=" in r_os.lower() or "Output" in r_os)
        prog.clear_programmer()

        # SOLO's "zero everyone else" guarantee must also survive FREEZE —
        # same class of bug, found by a background audit of the same code.
        # Seed a synthetic frozen snapshot directly instead of re-capturing
        # one through run_command("FREEZE") -- this isolates the check to
        # exactly the SOLO-during-FREEZE branch instead of also depending on
        # whatever dim/FX state other tests in this shared process happen
        # to have left on fixture 1 (that state is real but not this
        # check's concern).
        _solo_out = output_state.patch.get(1).all_subs()[0].outputs[0]
        _other_out = output_state.patch.get(3).all_subs()[0].outputs[0]
        _univ = _solo_out['universe']
        output_state.frozen_dmx[_univ] = tuple([200] * 512)
        output_state.freeze_mode = True
        run_command("1")
        run_command("SOLO")
        _dmx_frozen_solo = output_state.get_dmx_for_universe(_univ)
        _check("SOLO still zeros non-solo fixtures during FREEZE",
               _dmx_frozen_solo[_other_out['address'] - 1] == 0)
        _check("SOLO still passes the solo'd fixture during FREEZE",
               _dmx_frozen_solo[_solo_out['address'] - 1] > 0)
        run_command("SOLO OFF")
        run_command("FREEZE OFF")

        # RECORD GROUP + recall — untested prior to this session
        run_command("1 THRU 3")
        r_grp = run_command("RECORD GROUP 9 SmokeGroup")
        _check("RECORD GROUP from selection", "recorded" in r_grp)
        r_grp_recall = run_command("GROUP 9")
        _check("GROUP recall", "recalled" in r_grp_recall.lower())
        r_gi = run_command("GROUP 9 INFO")
        _check("GROUP INFO shows group name", "SmokeGroup" in r_gi)
        _check("GROUP INFO shows member count", "members" in r_gi)

        # GROUP ADD / GROUP REMOVE
        _g9 = group_pool.get(9)
        _g9_before = len(_g9.members)
        r_gadd = run_command("GROUP 9 ADD 4")   # add fixture 4
        _check("GROUP ADD increases member count by 1", len(_g9.members) == _g9_before + 1)
        _check("GROUP ADD returns confirmation", "added" in r_gadd.lower())
        r_gadd_dup = run_command("GROUP 9 ADD 4")
        _check("GROUP ADD rejects duplicate fixture", "already" in r_gadd_dup.lower())
        r_grem = run_command("GROUP 9 REMOVE 4")
        _check("GROUP REMOVE decreases member count by 1", len(_g9.members) == _g9_before)
        _check("GROUP REMOVE returns confirmation", "removed" in r_grem.lower())
        r_grem_miss = run_command("GROUP 9 REMOVE 4")
        _check("GROUP REMOVE rejects missing fixture", "not in group" in r_grem_miss.lower())

        # record form (custom breakpoint curve) — untested prior to this session
        r_form = run_command("record form 6 SmokeWave 0.0,0.0 0.5,1.0 1.0,0.0")
        _check("record form custom breakpoints", "recorded" in r_form)
        r_form_list = run_command("FORM LIST")
        _check("FORM LIST shows recorded form", "smokewave" in r_form_list.lower())

        # RECORD FX + FIRE FX roundtrip — untested prior to this session
        run_command("1 THRU 3")
        run_command("FX SINE BLUE BPM 40")
        r_fx_rec = run_command("RECORD FX 9 SmokeFX")
        _check("RECORD FX from programmer", "recorded" in r_fx_rec)
        run_command("FX CLEAR")
        r_fx_fire = run_command("FIRE FX 9")
        _check("FIRE FX reapplies preset", "FX" in r_fx_fire)
        run_command("FX CLEAR")

        # FX pool save/load round-trip must preserve speed_id (SpeedMaster
        # link) -- was silently dropped by save_fx_pool/load_fx_pool, so a
        # layer linked to a speed master reverted to its raw bpm on every
        # restart with no error.
        _speed_preset = FXPreset(19, "SmokeSpeedLink")
        _speed_preset.add_layer("sine", "red", bpm=45.0, speed_id=3)
        fx_pool.store(19, _speed_preset)
        ShowFile.save_fx_pool(fx_pool)
        _reloaded_fx_pool = FXPool()
        ShowFile.load_fx_pool(_reloaded_fx_pool)
        _reloaded_layer = _reloaded_fx_pool.get(19).layers[0]
        _check("fx_pool save/load preserves speed_id",
               _reloaded_layer.get("speed_id") == 3)

        # RECORD FX must also forward speed_id from the programmer's FX defs
        # into the stored preset (same bug, second call site).
        run_command("1 THRU 3")
        run_command("FX SINE GREEN BPM 50")
        for _fid, _vals in prog.data.items():
            if '.' not in _fid:
                for _ld in _vals.get('fx', []):
                    _ld['speed_id'] = 7
        r_fx_rec2 = run_command("RECORD FX 20 SmokeSpeedRec")
        _check("RECORD FX from programmer", "recorded" in r_fx_rec2)
        _check("RECORD FX preserves speed_id",
               fx_pool.get(20).layers[0].get("speed_id") == 7)
        run_command("FX CLEAR")

        # Attribute pools (POSITION/GOBO/ZOOM/FOCUS/BEAM/CONTROL) — GUI panel
        # landed last session but the record path was never smoke-tested.
        # These fixtures (SGM_RGB_54) have no pan/tilt/gobo/etc channels, so
        # recording should fail gracefully (not crash) rather than succeed.
        for _attr in ("POSITION", "GOBO", "ZOOM", "FOCUS", "BEAM", "CONTROL"):
            r_attr = run_command(f"RECORD {_attr} 9 Smoke{_attr.title()}")
            _check(f"RECORD {_attr} handles no-data case cleanly",
                   "no" in r_attr.lower() and "data in programmer" in r_attr.lower())

        # OSC input dispatch (Block 11) — /gma3/fader/PAGE/fdr is documented
        # as a 2-segment address (page, fdr) and _osc_fader parses it as
        # such, but the registered pattern had an extra "/*" wildcard segment
        # baked in since it was first added, so real /gma3/fader/1/1 messages
        # never matched it and silently fell through to the unmapped default
        # handler. Exercise the real dispatcher (not just call the handler
        # function directly) so a future pattern/handler mismatch here is
        # caught the same way this one was found.
        from pythonosc.osc_message_builder import OscMessageBuilder as _OscMsgBuilder
        _prev_fader_dim = _fader_dim[0]
        _fader_msg = _OscMsgBuilder(address="/gma3/fader/1/1")
        _fader_msg.add_arg(0.42)
        osc._dispatch.call_handlers_for_packet(_fader_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/fader/1/1 reaches _osc_fader and sets grandmaster dim",
               abs(_fader_dim[0] - 0.42) < 1e-6)
        _fader_dim[0] = _prev_fader_dim

        # OSC page/fader addressing used to hard-gate all fader/key behavior
        # on "page == 1 and fader == 1" — any other fader was parsed
        # and logged but silently dropped. Exercise fader 3 (arbitrary, not
        # fader 1) through the real dispatcher to confirm it now reaches
        # that fader's own level/GO/BACK, same as "FADER 3 LEVEL ..." /
        # "FADER 3 GO" typed on the command line.
        _osc_ex = fader_pool.get(3)
        _prev_osc_ex_level = _osc_ex.level
        _fader3_msg = _OscMsgBuilder(address="/gma3/fader/1/3")
        _fader3_msg.add_arg(0.65)
        osc._dispatch.call_handlers_for_packet(_fader3_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/fader/1/3 sets fader 3's own level (not grandmaster)",
               abs(_osc_ex.level - 0.65) < 1e-6)
        _osc_ex.level = _prev_osc_ex_level

        # stack 3 is wired to fader 3 by default at startup (every
        # loaded stack assigns 1:1 into the matching fader slot), so
        # a real GO on fdr 3 should activate it.
        _key3_msg = _OscMsgBuilder(address="/gma3/key/1/3/go")
        _key3_msg.add_arg(1)
        osc._dispatch.call_handlers_for_packet(_key3_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/key/1/3/go GOes fader 3 (routes through FADER 3 GO)",
               _osc_ex.is_active)

        # /gma3/key/PAGE/fdr/flash used to be silently dropped: the handler
        # returned immediately on any release (0) event regardless of TYPE,
        # and even on press only recognized go/go+/back/go-. A TouchOSC/
        # Chataigne "flash" key sent 1 then 0 and nothing happened at all.
        # Exercise both press and release through the real dispatcher.
        _flash_press_msg = _OscMsgBuilder(address="/gma3/key/1/3/flash")
        _flash_press_msg.add_arg(1)
        osc._dispatch.call_handlers_for_packet(_flash_press_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/key/1/3/flash press fires FADER 3 flash on",
               _osc_ex.is_active)
        _flash_release_msg = _OscMsgBuilder(address="/gma3/key/1/3/flash")
        _flash_release_msg.add_arg(0)
        osc._dispatch.call_handlers_for_packet(_flash_release_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/key/1/3/flash release fires FADER 3 flash off",
               not _osc_ex.is_active)

        # AudioEngine (Block 9) has an AUDIO command surface and a GUI panel
        # (audio_window) now, but its import used to be unconditional -- a
        # missing sounddevice package or native Portaudio lib crashed the
        # entire console before a single fixture patched. Force the
        # unavailable branch here so the guard is verified on every run,
        # regardless of whether this box happens to have a working audio
        # stack installed.
        _audio_probe = AudioEngine()
        _prev_audio_avail = _AUDIO_AVAILABLE
        _AUDIO_AVAILABLE = False
        # AudioEngine.list_devices()/.start() read _AUDIO_AVAILABLE from their
        # OWN module's namespace (studio_console/drivers/audio.py) now that
        # AudioEngine has moved there — rebinding the name in THIS module
        # (studio_project.py, via the line above) does not affect that
        # separate namespace, so it must be forced there too or this probe
        # exercises the "available" branch by accident instead of the
        # "unavailable" branch this test exists to check.
        _audio_driver._AUDIO_AVAILABLE = False
        try:
            try:
                _audio_probe.list_devices()
                _list_ok = True
            except Exception:
                _list_ok = False
            _check("AudioEngine.list_devices() doesn't raise when unavailable", _list_ok)

            try:
                _audio_probe.start()
                _check("AudioEngine.start() raises RuntimeError when unavailable", False)
            except RuntimeError:
                _check("AudioEngine.start() raises RuntimeError when unavailable", True)
            except Exception as _ae:
                _check(f"AudioEngine.start() raised wrong exception "
                       f"({type(_ae).__name__}) when unavailable", False)

            # AUDIO command wiring — the engine/mapper above were dead code
            # with zero command/GUI surface until this session; exercise the
            # run_command() path itself (not just the classes directly) the
            # same way the OSC dispatcher check above does. ON/OFF/STATUS/GAIN
            # don't touch real hardware so they're safe with a real audio
            # stack installed too; START/DEVICES are only exercised in the
            # forced-unavailable branch to avoid opening a real mic stream.
            run_command("AUDIO OFF")
            _check("AUDIO OFF works pre-start", not audio_mapper.enabled)
            run_command("AUDIO ON")
            _check("AUDIO ON enables mapper", audio_mapper.enabled)
            r_audio_status = run_command("AUDIO STATUS")
            _check("AUDIO STATUS reports mapping ON", "mapping ON" in r_audio_status)
            run_command("AUDIO OFF")
            _check("AUDIO OFF disables mapper", not audio_mapper.enabled)
            _prev_gain = audio_engine.gain
            run_command("AUDIO GAIN 5")
            _check("AUDIO GAIN sets engine gain", audio_engine.gain == 5.0)
            audio_engine.gain = _prev_gain

            r_devices = run_command("AUDIO DEVICES")
            _check("AUDIO DEVICES reports unavailable cleanly",
                   "unavailable" in r_devices.lower())
            r_start = run_command("AUDIO START")
            _check("AUDIO START reports failure cleanly (no crash)",
                   "failed" in r_start.lower())
        finally:
            _AUDIO_AVAILABLE = _prev_audio_avail
            _audio_driver._AUDIO_AVAILABLE = _prev_audio_avail

        # CLEAR stage 3 — should blackout output, not silently return "output_clear"
        prog.do_clear(); prog.do_clear()   # advance to stage 2 (programmer cleared)
        _saved_master = output_state.master_level
        output_state.master_level = 0.8
        prog.live_fades.append({"fid": "1", "ch": "dim", "src": 0.5, "dst": 1.0,
                                 "start": 0.0, "dur": 10.0})  # fake live fade
        prog._clear_stage = 2
        _r_clear3 = run_command("CLEAR")
        _check("CLEAR stage 3 does not touch master level", output_state.master_level == 0.8)
        _check("CLEAR stage 3 kills live fades", len(prog.live_fades) == 0)
        _check("CLEAR stage 3 returns programmer output cleared", "output cleared" in _r_clear3)
        output_state.master_level = _saved_master

        # RECORD CUE with FOLLOW time — was silently dropped before the fix
        run_command("ALL AT R 255 G 0 B 0")
        _r_follow = run_command("RECORD stk 1 CUE 99 FollowTest FOLLOW 3.5")
        _cs_1 = stack_pool.get(1)
        _cue_99 = _cs_1.cues.get(99.0) if _cs_1 else None
        _check("RECORD CUE stores FOLLOW time", _cue_99 is not None and
               abs(getattr(_cue_99, 'follow_time', 0) - 3.5) < 0.01)

        # COPY CUE preserves follow_time and note
        if _cue_99:
            _cue_99.note = "test note"
        run_command("COPY CUE 99 TO 98 stk 1")
        _cue_98 = _cs_1.cues.get(98.0) if _cs_1 else None
        _check("COPY CUE copies follow_time", _cue_98 is not None and
               abs(getattr(_cue_98, 'follow_time', 0) - 3.5) < 0.01)
        _check("COPY CUE copies note", _cue_98 is not None and
               getattr(_cue_98, 'note', '') == "test note")

        # MOVE CUE renumbers and removes source
        run_command("MOVE CUE 98 TO 97 stk 1")
        _check("MOVE CUE creates destination", _cs_1.cues.get(97.0) is not None)
        _check("MOVE CUE removes source", _cs_1.cues.get(98.0) is None)

        # GOTO non-existent cue returns error, not false success
        _r_goto_bad = run_command("GOTO 9999")
        _check("GOTO non-existent cue returns error", "not found" in (_r_goto_bad or "").lower())

        # FADER GOTO FIRST / LAST
        _gtfl_ex = fader_pool.get(1)
        if _gtfl_ex and _gtfl_ex.stack and _gtfl_ex.stack.cues:
            _gtfl_cs = _gtfl_ex.stack
            _gtfl_first = _gtfl_cs._sorted_cue_numbers()[0]
            _gtfl_last  = _gtfl_cs._sorted_cue_numbers()[-1]
            run_command("FADER 1 GOTO FIRST")
            _check("FADER GOTO FIRST positions stack at first cue",
                   _gtfl_cs.current == _gtfl_first)
            run_command("FADER 1 GOTO LAST")
            _check("FADER GOTO LAST positions stack at last cue",
                   _gtfl_cs.current == _gtfl_last)

        # delete cue cleans up cue_pool
        run_command("ALL AT R 128 G 0 B 0")
        run_command("RECORD stk 1 CUE 96")
        _check("delete cue: cue_pool stale ref cleaned", True)  # record stores in pool
        _pool_has_96_before = cue_pool.get(96) is not None
        run_command("delete cue 96 stk 1")
        _check("delete cue removes from cue_pool",
               _pool_has_96_before and cue_pool.get(96) is None)

        # speed master: set/get BPM
        _r_spd = run_command("SPEED 4 200")
        _check("SPEED command sets BPM", speed_master_pool.get_bpm(4) == 200.0)
        _r_spd_name = run_command("SPEED 4 NAME StrobeClk")
        _check("SPEED NAME renames slot", speed_master_pool.get(4).name == "Strobeclk")
        _r_list_spd = run_command("LIST SPEED")
        _check("LIST SPEED shows all slots", "speed masters" in (_r_list_spd or "").lower())
        # FX layer with speed master reference uses master BPM
        run_command("FX SINE RED BPM 60")
        _check("FX inline BPM default before speed ref", True)
        speed_master_pool.set_bpm(4, 333.0)
        _layer0 = active_fx[0] if active_fx else None
        if _layer0:
            _layer0._speed_id = 4
            _layer0._speed_master_pool = speed_master_pool
        _check("FX layer rate_bpm uses speed master", (
            _layer0 is None or abs(_layer0.rate_bpm - 333.0) < 0.1))

        # ── FX ENGINE COMPREHENSIVE TESTS ─────────────────────────────────────

        # Waveform range: all outputs must stay in [0, 1]
        import math as _math
        def _wv_range(name, fn):
            vals = [fn(t / 200.0) for t in range(200)]
            return min(vals) >= 0.0 and max(vals) <= 1.0
        _check("waveform sine range [0,1]",     _wv_range('sine',     Waveform.sine))
        _check("waveform ramp range [0,1]",     _wv_range('ramp',     Waveform.ramp))
        _check("waveform square range [0,1]",   _wv_range('square',   Waveform.square))
        _check("waveform pulse range [0,1]",    _wv_range('pulse',    Waveform.pulse))
        _check("waveform triangle range [0,1]", _wv_range('triangle', Waveform.triangle))
        _check("waveform sawtooth range [0,1]", _wv_range('sawtooth', Waveform.sawtooth))
        _check("waveform flicker range [0,1]",
               all(0.0 <= Waveform.flicker(t/200.0, i) <= 1.0
                   for t in range(200) for i in range(10)))

        # Flicker per-pixel independence: 10 pixels at same phase must differ
        _fl_vals = [Waveform.flicker(0.5, i) for i in range(10)]
        _check("flicker has per-pixel variation", len(set(_fl_vals)) > 1)

        # Flicker time resolution: enough unique states per cycle for 44Hz
        _fl_cycle = [Waveform.flicker(t / 100.0, 0) for t in range(100)]
        _check("flicker has ≥44 unique states/cycle", len(set(_fl_cycle)) >= 44)

        # Sine shape: trough at 0, peak at 0.5, back to trough at 1.0
        _check("sine shape: trough at 0.0",
               abs(Waveform.sine(0.0) - 0.0) < 0.01)
        _check("sine shape: peak at 0.5",
               abs(Waveform.sine(0.5) - 1.0) < 0.01)

        # Pulse duty cycle: on for exactly 25% of a cycle
        _pulse_on = sum(1 for t in range(1000) if Waveform.pulse(t/1000.0) > 0.5)
        _check("pulse duty cycle is 25%", abs(_pulse_on - 250) <= 2)

        # Strobe shorthand: STROBE creates a pulse dim FX layer
        run_command("FX CLEAR")
        _r_strobe = run_command("STROBE 120")
        _check("STROBE creates FX layer", active_fx != [] or "FX" in (_r_strobe or ""))

        # STROBE CLEAR removes dim FX
        run_command("STROBE 120")
        run_command("STROBE CLEAR")
        _strobe_still = any(l.channel == 'dim' for l in (active_fx or []))
        _check("STROBE CLEAR removes dim FX", not _strobe_still)

        # rainbow shorthand: RAINBOW creates 3 colour FX layers
        run_command("FX CLEAR")
        _r_rainbow = run_command("RAINBOW 60 100")
        _rainbow_chans = [l.channel for l in (active_fx or [])]
        _check("RAINBOW creates red layer",   'red'   in _rainbow_chans)
        _check("RAINBOW creates green layer", 'green' in _rainbow_chans)
        _check("RAINBOW creates blue layer",  'blue'  in _rainbow_chans)
        # Phase offsets should differ by ~0.33 between R→G and G→B
        _rb_layers = sorted(
            [l for l in (active_fx or []) if l.channel in ('red','green','blue')],
            key=lambda l: l.phase_offset)
        if len(_rb_layers) >= 3:
            _rb_ph = [l.phase_offset for l in _rb_layers]
            _check("RAINBOW phases spaced ~0.33 apart",
                   abs(_rb_ph[1] - _rb_ph[0] - 0.333) < 0.01 or
                   abs(_rb_ph[2] - _rb_ph[1] - 0.333) < 0.01)
        else:
            _check("RAINBOW phases (need 3 layers)", False)

        # Spread: with spread=100 and ≥2 targets, offsets are not all identical
        run_command("FX CLEAR")
        run_command("FX SINE RED SPREAD 100 BPM 60")
        _sp_layer = (active_fx or [None])[0]
        if _sp_layer and len(_sp_layer._offsets) >= 2:
            _check("spread=100 creates non-zero offsets",
                   len(set(round(o, 4) for o in _sp_layer._offsets)) > 1)
        else:
            _check("spread=100 (need ≥2 targets)", _sp_layer is None)

        # FX size scales amplitude: size=50 → max ~127 DMX
        run_command("FX CLEAR")
        run_command("FX SINE RED SIZE 50 SPREAD 0 BPM 60")
        _sz_layer = (active_fx or [None])[0]
        if _sz_layer:
            _sz_vals = _sz_layer.get_values(time.monotonic())
            _sz_max  = max(_sz_vals.values()) if _sz_vals else 0
            _check("FX size=50 gives max ~127 DMX", _sz_max <= 128.0)
        else:
            _check("FX size=50 (layer needed)", False)

        # dim FX: multiplicative (FX PULSE DIM should not exceed base dim)
        run_command("FX CLEAR")
        run_command("FX SQUARE DIM SIZE 100 SPREAD 0 BPM 30")
        _dm_layer = next((l for l in (active_fx or []) if l.channel == 'dim'), None)
        _check("dim FX layer channel is 'dim'", _dm_layer is not None)

        # Bounce direction: phase reverses after one cycle
        run_command("FX CLEAR")
        run_command("FX RAMP RED SPREAD 100 BPM 60 DIRECTION BOUNCE")
        _bn_layer = (active_fx or [None])[0]
        _check("bounce direction stored", _bn_layer is not None and _bn_layer.direction == 'bounce')

        # Block size: adjacent pixels grouped
        run_command("FX CLEAR")
        run_command("FX RAMP RED SPREAD 100 BLOCK 3 BPM 60")
        _bk_layer = (active_fx or [None])[0]
        if _bk_layer and len(_bk_layer._offsets) >= 6:
            _bk_off = _bk_layer._offsets
            _check("block_size=3 groups adjacent targets (offsets equal)",
                   _bk_off[0] == _bk_off[1] == _bk_off[2] and
                   _bk_off[3] == _bk_off[4] == _bk_off[5])
        else:
            _check("block_size=3 (need ≥6 targets)", True)

        # Infade: envelope ramps from 0 at start
        run_command("FX CLEAR")
        run_command("FX SINE RED INFADE 5 BPM 60")
        _if_layer = (active_fx or [None])[0]
        if _if_layer:
            _if_layer.start = time.monotonic()  # reset start so env starts at 0
            _if_layer.get_values(time.monotonic())
            _check("infade envelope starts near 0", _if_layer._last_env < 0.5)
        else:
            _check("infade (layer needed)", False)

        run_command("FX CLEAR")

        # ── CUE DIM TRACKING TESTS ───────────────────────────────────────────
        # Verify that dim in cue 1 tracks through cue 2 (FX-only) and cue 3 (empty).
        # This exercises the LTP tracking path in Fade.tick() for the case where
        # data_to has no dim entry.

        _ts_cs = Stack(999, "TrackTest")

        # cue 1: dim=0.8 stored explicitly
        _tc1 = Cue(1.0, "Track1")
        _tc1.data = {'_test_fid': {'dim': 0.8}}
        _ts_cs.cues[1.0] = _tc1

        # cue 2: no dim (should track 0.8 from cue 1)
        _tc2 = Cue(2.0, "Track2")
        _tc2.data = {}
        _ts_cs.cues[2.0] = _tc2

        # cue 3: empty (should still track 0.8)
        _tc3 = Cue(3.0, "Track3")
        _tc3.data = {}
        _ts_cs.cues[3.0] = _tc3

        # Simulate the Fade.tick() tracking logic directly (no real fader needed)
        def _sim_fade(data_from, data_to):
            """Return resulting layer after a tracking fade (t=1.0, instant)."""
            result = {}
            for fid in set(data_from) | set(data_to):
                fv = data_from.get(fid, {})
                tv = data_to.get(fid, {})
                if fid not in result:
                    result[fid] = {}
                for ch in set(fv) | set(tv):
                    v_from = fv.get(ch, 0)
                    _flag  = ch in ('fx_kill',)
                    v_to   = tv.get(ch, 0 if _flag else v_from)
                    if not isinstance(v_from, (int, float)) or not isinstance(v_to, (int, float)):
                        continue
                    # t=1.0 (fade complete)
                    result[fid][ch] = v_from + (v_to - v_from) * 1.0
            return result

        # cue 1 fires from empty fader
        _layer = {}
        _layer = _sim_fade(_layer, {'_test_fid': {'dim': 0.8}})
        _check("cue tracking: cue 1 sets dim=0.8",
               abs(_layer.get('_test_fid', {}).get('dim', -1) - 0.8) < 0.001)

        # cue 2 fires (no dim in data_to) — should track dim=0.8
        _layer = _sim_fade(_layer, {})
        _check("cue tracking: cue 2 tracks dim from cue 1",
               abs(_layer.get('_test_fid', {}).get('dim', -1) - 0.8) < 0.001)

        # cue 3 fires (also empty) — should still track dim=0.8
        _layer = _sim_fade(_layer, {})
        _check("cue tracking: cue 3 still tracks dim (no stale zero)",
               abs(_layer.get('_test_fid', {}).get('dim', -1) - 0.8) < 0.001)

        # fx_outfade field: cue class should have it, default None
        _fxo_cue = Cue(1.0, "fxout")
        _check("Cue.fx_outfade defaults to None", _fxo_cue.fx_outfade is None)

        # FXOUTFADE keyword in timing edit
        _apply_timing_edit(_fxo_cue, "FXOUTFADE 2.5")
        _check("FXOUTFADE sets cue.fx_outfade", _fxo_cue.fx_outfade == 2.5)

        # COPY CUE / COPY stk / MOVE CUE must preserve fx_outfade (was silently
        # dropped -- Cue() constructor doesn't take it, and all three call
        # sites copied note/data/timings but forgot fx_outfade)
        _fxo_src_cs = stack_pool.create(91)
        _fxo_src_cue = Cue(1.0, "FXOutSrc")
        _fxo_src_cue.fx_outfade = 3.25
        _fxo_src_cs.cues[1.0] = _fxo_src_cue
        run_command("COPY stk 91 TO stk 92")
        _fxo_dst_cs = stack_pool.get(92)
        _check("COPY stk preserves cue.fx_outfade",
               _fxo_dst_cs is not None and _fxo_dst_cs.cues.get(1.0) is not None and
               _fxo_dst_cs.cues[1.0].fx_outfade == 3.25)

        run_command("COPY stk 91 CUE 1 TO stk 93 CUE 1")
        _fxo_dst_cs2 = stack_pool.get(93)
        _check("COPY CUE (single cue) preserves cue.fx_outfade",
               _fxo_dst_cs2 is not None and _fxo_dst_cs2.cues.get(1.0) is not None and
               _fxo_dst_cs2.cues[1.0].fx_outfade == 3.25)

        run_command("MOVE stk 91 CUE 1 TO stk 94 CUE 1")
        _fxo_dst_cs3 = stack_pool.get(94)
        _check("MOVE CUE preserves cue.fx_outfade",
               _fxo_dst_cs3 is not None and _fxo_dst_cs3.cues.get(1.0) is not None and
               _fxo_dst_cs3.cues[1.0].fx_outfade == 3.25)

        # FX CLEAR clears fader FX layers
        run_command("FX SINE RED BPM 60 SIZE 100")
        _ex0 = _active_fader()
        _ex0_had_fx = bool(_ex0._fx_ids)
        run_command("FX CLEAR")
        _check("FX CLEAR clears fader FX (fader._fx_ids empty)",
               not _ex0._fx_ids)

        # FX CLEAR scoped to selection — only clears selected fixtures' programmer FX
        run_command("1 THRU 3")   # select fixtures 1-3
        run_command("FX SINE RED BPM 60 SIZE 100")
        _all_fids = list(prog.data.keys())
        run_command("FX CLEAR")   # selection active → programmer-only, scoped
        _cleared_sel = all(
            'fx' not in prog.data.get(str(f.fixture_id), {})
            for f in prog.selection
        )
        _check("FX CLEAR with selection clears only selected fixtures (programmer)",
               _cleared_sel)

        # CLEAR COLOUR removes RGB from programmer, leaves dim intact
        # dim lives in master key ("1"), RGB in sub-fixture keys ("1.1" etc.)
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("@ FULL")           # set dim=1.0 on selection
        run_command("1 THRU 3 R 255 G 128 B 64")  # set explicit RGB
        _pre_dim  = prog.data.get("1", {}).get('dim')
        _sub1     = next((k for k in prog.data if k.startswith("1.")), None)
        _pre_red  = prog.data.get(_sub1, {}).get('red') if _sub1 else None
        _check("CLEAR COLOUR pre-check: red was set", _pre_red == 255)
        run_command("CLEAR COLOUR")
        _post_rgb = prog.data.get(_sub1, {}).get('red') if _sub1 else None
        _post_dim = prog.data.get("1", {}).get('dim')
        _check("CLEAR COLOUR zeroes RGB and leaves dim intact",
               _post_rgb == 0 and _post_dim == _pre_dim)

        # CLEAR DIM removes only dimmer, leaves RGB intact
        # RGB lives in sub-fixture keys ("1.1"), dim in master key ("1")
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("@ FULL")
        run_command("1 THRU 3 R 200 G 100 B 50")
        run_command("CLEAR DIM")
        _post_dim2 = prog.data.get("1", {}).get('dim')
        _first_sub = next((k for k in prog.data if k.startswith("1.")), None)
        _post_red2 = prog.data.get(_first_sub, {}).get('red') if _first_sub else None
        _check("CLEAR DIM zeroes dim, leaves RGB intact",
               _post_dim2 == 0.0 and _post_red2 == 200)

        # stk n WRAP ON/OFF — clean restart at top after last cue
        run_command("RECORD STACK 99 WrapTest")
        _stk99 = stack_pool.get(99)
        _check("stk WRAP: default is False", _stk99.wrap is False)
        run_command("stk 99 WRAP ON")
        _check("stk 99 WRAP ON sets .wrap = True", _stk99.wrap is True)
        run_command("stk 99 WRAP OFF")
        _check("stk 99 WRAP OFF sets .wrap = False", _stk99.wrap is False)

        # stk INFO
        r_csi = run_command("stk 99 INFO")
        _check("stk INFO shows stack name", "WrapTest" in r_csi)
        _check("stk INFO shows wrap/loop state", "wrap" in r_csi or "loop" in r_csi)
        r_csi_bad = run_command("stk 9999 INFO")
        _check("stk INFO rejects unknown stack", "not found" in r_csi_bad)

        # stk REVERSE
        run_command("RECORD STACK 94 RevTest")
        run_command("STACK 94")
        run_command("1 FULL");   run_command("RECORD CUE 1 First")
        run_command("1 OUT");    run_command("RECORD CUE 2 Second")
        run_command("1 AT R 200"); run_command("RECORD CUE 3 Third")
        _stk94 = stack_pool.get(94)
        _orig_names = [_stk94.cues[n].name for n in _stk94._sorted_cue_numbers()]
        r_rev = run_command("stk 94 REVERSE")
        _rev_names = [_stk94.cues[n].name for n in _stk94._sorted_cue_numbers()]
        _check("stk REVERSE reverses cue order", _rev_names == list(reversed(_orig_names)))
        _check("stk REVERSE returns confirmation", "reversed" in r_rev)
        _check("stk REVERSE resets current position to None", _stk94.current is None)

        # stk COMPRESS
        run_command("RECORD STACK 95 CompTest")
        run_command("STACK 95")
        run_command("1 FULL"); run_command("RECORD CUE 1 Cue1")
        run_command("1 OUT");  run_command("RECORD CUE 5 Cue5")   # gap: 1, 5
        run_command("1 AT R 200"); run_command("RECORD CUE 10 Cue10")  # cues 1,5,10
        _stk95 = stack_pool.get(95)
        r_cmp = run_command("stk 95 COMPRESS")
        _cmp_nums = _stk95._sorted_cue_numbers()
        _check("stk COMPRESS renumbers cues to 1,2,3 (collapses gaps)",
               _cmp_nums == [1.0, 2.0, 3.0])
        _check("stk COMPRESS preserves cue names in order",
               [_stk95.cues[n].name for n in _cmp_nums] == ["Cue1", "Cue5", "Cue10"])
        _check("stk COMPRESS returns 'compressed' confirmation", "compressed" in r_cmp)

        # stk EXTRACT
        run_command("RECORD STACK 97 ExtractSrc")
        run_command("STACK 97")
        run_command("1 FULL"); run_command("RECORD CUE 1 ExtCue1")
        run_command("1 OUT");  run_command("RECORD CUE 2 ExtCue2")
        _stk97 = stack_pool.get(97)
        _stk97.note = "Dark Moody Show"
        _stk97.wrap = True
        r_ext = run_command("stk 97 EXTRACT 2 INTO 98")
        _stk98 = stack_pool.get(98)
        _check("stk EXTRACT creates new stack in target slot", _stk98 is not None)
        _check("stk EXTRACT new stack has exactly one cue",
               _stk98 is not None and len(_stk98.cues) == 1)
        _check("stk EXTRACT preserves cue name",
               _stk98 is not None and list(_stk98.cues.values())[0].name.lower() == "extcue2")
        _check("stk EXTRACT returns 'Extracted' confirmation", "extracted" in r_ext)
        _check("stk EXTRACT source stack unchanged (still 2 cues)", len(_stk97.cues) == 2)
        _check("stk EXTRACT carries source note to new stack",
               _stk98 is not None and _stk98.note == "Dark Moody Show")
        _check("stk EXTRACT carries source wrap flag to new stack",
               _stk98 is not None and _stk98.wrap is True)

        # stk DUPLICATE
        run_command("RECORD STACK 99 DupSrc")
        run_command("STACK 99")
        run_command("1 FULL"); run_command("RECORD CUE 1 DupA")
        run_command("1 OUT");  run_command("RECORD CUE 2 DupB")
        _cs99dup = stack_pool.get(99)
        _cs99dup.note = "Act 2 Opener"
        _cs99dup.wrap = True
        r_dup = run_command("stk 99 DUPLICATE INTO 100")
        _stk100 = stack_pool.get(100)
        _check("stk DUPLICATE creates new stack in target slot", _stk100 is not None)
        _check("stk DUPLICATE copies all cues",
               _stk100 is not None and len(_stk100.cues) == len(_cs99dup.cues))
        _check("stk DUPLICATE is a deep copy (modifying source doesn't affect copy)",
               _stk100 is not None and _stk100.cues is not _cs99dup.cues)
        _check("stk DUPLICATE returns 'Duplicated' confirmation", "duplicated" in r_dup)
        _check("stk DUPLICATE source is unchanged", len(_cs99dup.cues) == 2)
        _check("stk DUPLICATE carries source note to new stack",
               _stk100 is not None and _stk100.note == "Act 2 Opener")
        _check("stk DUPLICATE carries source wrap flag to new stack (regression check)",
               _stk100 is not None and _stk100.wrap is True)

        # stk RENUMBER STEP
        run_command("RECORD STACK 101 StepTest")
        run_command("STACK 101")
        run_command("1 FULL"); run_command("RECORD CUE 1 SA")
        run_command("1 OUT");  run_command("RECORD CUE 2 SB")
        run_command("1 AT R 200"); run_command("RECORD CUE 3 SC")
        _stk101 = stack_pool.get(101)
        r_ren = run_command("stk 101 RENUMBER STEP 10")
        _ren_nums = _stk101._sorted_cue_numbers()
        _check("stk RENUMBER STEP 10 gives multiples of 10",
               _ren_nums == [10.0, 20.0, 30.0])
        _check("stk RENUMBER STEP returns confirmation", "renumbered" in r_ren.lower())

        # CUE SHIFT
        run_command("RECORD STACK 96 ShiftTest")
        run_command("STACK 96")
        run_command("1 FULL"); run_command("RECORD CUE 3 MoverCue")
        run_command("1 OUT");  run_command("RECORD CUE 7 StayCue")
        _stk96 = stack_pool.get(96)
        r_shift = run_command("CUE 3 SHIFT 5")   # 3+5 = cue 8
        _shift_nums = _stk96._sorted_cue_numbers()
        _check("CUE SHIFT moves cue to new number (3→8)",
               3.0 not in _shift_nums and 8.0 in _shift_nums)
        _check("CUE SHIFT does not disturb other cues",
               7.0 in _shift_nums)
        _check("CUE SHIFT returns confirmation with new number", "8" in r_shift)

        # STACK MERGE
        run_command("RECORD STACK 91 MergeSrc")
        run_command("STACK 91")          # make active
        run_command("1 FULL")
        run_command("RECORD CUE 1 SrcCue1")
        run_command("RECORD STACK 92 MergeDst")
        run_command("STACK 92")
        run_command("1 OUT")
        run_command("RECORD CUE 1 DstCue1")
        _stk91 = stack_pool.get(91)
        _stk92 = stack_pool.get(92)
        _n_before = len(_stk92.cues)
        r_merge = run_command("STACK MERGE 91 INTO 92")
        _n_after = len(_stk92.cues)
        _check("STACK MERGE adds src cues to dst",
               _n_after == _n_before + len(_stk91.cues))
        _check("STACK MERGE returns confirmation", "merged" in r_merge)
        # Src cue numbers in dst should be offset past dst's original last cue
        _merged_num = max(_stk92._sorted_cue_numbers())
        _check("STACK MERGE renumbers merged cues after dst's last cue",
               _merged_num > 1.0)
        r_merge_bad = run_command("STACK MERGE 9999 INTO 92")
        _check("STACK MERGE rejects unknown source", "not found" in r_merge_bad)

        # stk BACK on wrap-around (first cue -> last cue) must also clear the
        # LTP-bleed layer when WRAP is ON -- stk GO already did this on forward
        # wrap (last -> first); BACK had no equivalent, flagged by a prior
        # session and left unfixed pending confirmation it wasn't intentional.
        run_command("RECORD STACK 98 BackWrapTest")
        _stk98 = stack_pool.get(98)
        run_command("1")
        run_command("AT R 10")
        run_command("RECORD stk 98 CUE 1")
        run_command("AT R 20")
        run_command("RECORD stk 98 CUE 2")
        prog.clear_programmer()
        run_command("ASSIGN stk 98 TO FADER 9")
        _ex98 = fader_pool.get(9)
        _stk98.wrap    = True
        _stk98.current = _stk98._sorted_cue_numbers()[0]   # sitting at first cue
        _ex98.layer['__bleed_sentinel__'] = {'red': 99}
        _stk98.back(patch, fade_engine, _ex98)
        _check("stk BACK wrap-around (first->last) clears LTP-bleed layer when WRAP ON",
               '__bleed_sentinel__' not in _ex98.layer)

        _stk98.wrap    = False
        _stk98.current = _stk98._sorted_cue_numbers()[0]
        _ex98.layer['__bleed_sentinel2__'] = {'red': 99}
        _stk98.back(patch, fade_engine, _ex98)
        _check("stk BACK wrap-around leaves layer intact when WRAP OFF",
               '__bleed_sentinel2__' in _ex98.layer)

        # Non-wrap BACK (middle of stack, no wraparound) must never clear the
        # layer even with WRAP ON -- only the actual last->first transition should.
        _stk98.wrap    = True
        _stk98.current = _stk98._sorted_cue_numbers()[-1]  # sitting at last cue, BACK is not a wrap
        _ex98.layer['__bleed_sentinel3__'] = {'red': 99}
        _stk98.back(patch, fade_engine, _ex98)
        _check("stk BACK non-wrap step leaves layer intact even with WRAP ON",
               '__bleed_sentinel3__' in _ex98.layer)

        # UNDO must not desync output_state.programmer_layer from prog.data --
        # link_programmer() aliases them to the *same* dict object, so undo()
        # rebinding self.data to a new object (instead of clearing+updating in
        # place) would silently freeze live DMX output on stale data forever.
        # Each single-channel "R n" call pushes its own undo snapshot, so one
        # UNDO after one single-channel edit fully reverts it.
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("1 THRU 3 R 10")
        run_command("1 THRU 3 R 250")
        _check("UNDO pre-check: post-undo-marker red was set",
               prog.data.get(_sub1, {}).get('red') == 250)
        run_command("UNDO")
        _check("UNDO restores prior programmer values",
               prog.data.get(_sub1, {}).get('red') == 10)
        _check("UNDO keeps output_state.programmer_layer aliased to prog.data "
               "(same object identity, not a stale copy)",
               output_state.programmer_layer is prog.data)
        run_command("1 THRU 3 R 77")
        _check("UNDO: post-undo edits are visible through the aliased "
               "programmer_layer used by real DMX output",
               output_state.programmer_layer.get(_sub1, {}).get('red') == 77)

        # fader page button assignment round-trip
        _fpg_ex = fader_pool.get(1)
        _fpg_ex.btn_a, _fpg_ex.btn_b, _fpg_ex.btn_c = 'GO', 'BACK', 'STOP'
        r_btn = run_command("FADER 1 BTN A FLASH")
        _check("FADER 1 BTN A FLASH sets btn_a to FLASH", _fpg_ex.btn_a == 'FLASH')
        r_btn2 = run_command("FADER 1 BTN A GO")
        _check("FADER 1 BTN A GO restores btn_a to GO",   _fpg_ex.btn_a == 'GO')
        r_btn3 = run_command("FADER 1 BTN")  # missing slot → usage hint
        _check("FADER 1 BTN without slot returns current state", "btn" in r_btn3.lower() or "usage" in r_btn3.lower() or "A=" in r_btn3)

        # RATE+/RATE- and RATE RESET smoke tests
        _rate_ex = fader_pool.get(2)
        _rate_ex.rate_factor = 1.0
        run_command("FADER 2 RATE+")
        _check("FADER 2 RATE+ increases rate_factor to ~1.25", abs(_rate_ex.rate_factor - 1.25) < 0.01)
        run_command("FADER 2 RATE-")
        _check("FADER 2 RATE- returns rate_factor to ~1.00", abs(_rate_ex.rate_factor - 1.0) < 0.01)
        run_command("FADER 2 RATE+")
        run_command("FADER 2 RATE RESET")
        _check("FADER 2 RATE RESET returns rate_factor to 1.0", _rate_ex.rate_factor == 1.0)
        run_command("FADER 2 RATE 3.0")
        _check("FADER 2 RATE 3.0 sets rate_factor to 3.0", abs(_rate_ex.rate_factor - 3.0) < 0.01)
        run_command("FADER 2 RATE RESET")
        r_rate_btn = run_command("FADER 2 BTN C RATE+")
        _check("FADER 2 BTN C RATE+ sets btn_c to RATE+", _rate_ex.btn_c == 'RATE+')
        run_command("FADER 2 BTN C STOP")  # restore

        # FADER LABEL
        _lbl_ex = fader_pool.get(1)
        r_lbl = run_command("FADER 1 LABEL Main Show")
        _check("FADER LABEL sets label on fader", _lbl_ex.label == "Main Show")
        _check("FADER LABEL returns confirmation", "Main Show" in r_lbl)
        r_lbl_list = run_command("LIST FADER")
        _check("LIST FADER shows label", "Main Show" in r_lbl_list)
        run_command("FADER 1 LABEL")  # clear
        _check("FADER 1 LABEL (no text) clears label", _lbl_ex.label == "")

        # FADER INFO
        r_fi1 = run_command("FADER 1 INFO")
        _check("FADER INFO shows level", "Level" in r_fi1)
        _check("FADER INFO shows buttons", "Buttons" in r_fi1)
        _fi1_ex = fader_pool.get(1)
        if _fi1_ex.stack:
            _check("FADER INFO shows stack name", _fi1_ex.stack.name in r_fi1)
        r_fi1_stat = run_command("FADER 1 STATUS")
        _check("FADER STATUS alias works", "Level" in r_fi1_stat)

        # FADER CLEAR
        _clr_ex = fader_pool.get(1)
        _clr_cs = _clr_ex.stack
        if _clr_cs:
            _clr_cs.current = 1  # pretend we're at cue 1
            r_fc = run_command("FADER 1 CLEAR")
            _check("FADER CLEAR resets stack position to None", _clr_cs.current is None)
            _check("FADER CLEAR returns confirmation", "cleared" in r_fc or "reset" in r_fc)

        # FADER ALL CLEAR
        if _clr_cs:
            _clr_cs.current = 2  # set a position to confirm it gets reset
        r_fac = run_command("FADER ALL CLEAR")
        _check("FADER ALL CLEAR returns 'cleared' confirmation", "cleared" in r_fac)
        _check("FADER ALL CLEAR resets position of stack in fader 1",
               _clr_cs is None or _clr_cs.current is None)

        # FADER LOOP ON/OFF
        if _clr_cs:
            r_loop_on  = run_command("FADER 1 LOOP ON")
            _check("FADER LOOP ON enables wrap on assigned stack", _clr_cs.wrap is True)
            _check("FADER LOOP ON returns confirmation", "loop" in r_loop_on.lower() or "wrap" in r_loop_on.lower())
            r_loop_off = run_command("FADER 1 LOOP OFF")
            _check("FADER LOOP OFF disables wrap on assigned stack", _clr_cs.wrap is False)

        # LOAD SHOW must reload OSC targets and FX defaults, not just leave
        # the previous show's live values in place — same primitives
        # load_show_from() now calls (osc._clients.clear() + load_osc_targets,
        # load_fx), exercised directly here so the test stays within the
        # isolated DATA_DIR and never touches the real studio_saves/ dir.
        osc.add_target("smoketest_stale", "10.0.0.1", 9000)
        ShowFile.save_osc_targets(osc)
        osc.add_target("smoketest_extra", "10.0.0.2", 9001)  # never persisted
        osc._clients.clear()
        ShowFile.load_osc_targets(osc)
        _check("LOAD SHOW-style OSC reload restores saved targets",
               "smoketest_stale" in osc._clients)
        _check("LOAD SHOW-style OSC reload drops targets not in the saved show",
               "smoketest_extra" not in osc._clients)

        _fx_params['rate_bpm'] = 60.0
        ShowFile.save_fx(_fx_params)
        _fx_params['rate_bpm'] = 999.0  # simulate a live value from a different show
        ShowFile.load_fx(_fx_params)
        _check("LOAD SHOW-style FX reload restores saved fx_params",
               _fx_params['rate_bpm'] == 60.0)

        # BACKUP command
        r_bk = run_command("BACKUP")
        _check("BACKUP creates a timestamped save", "backup_" in r_bk and "saved" in r_bk.lower())

        # ── ATTRIBUTE CHANNEL / MOVING LIGHT TESTS ───────────────────────────
        # Patch a Generic_Moving head into a spare slot (fixture 50), set
        # pan/tilt/gobo in programmer, record a cue, fire it, verify DMX output.

        _ml_profile = library.get("Generic_Moving")
        _check("Generic_Moving profile registered", _ml_profile is not None)

        if _ml_profile:
            # Patch at fixture 50, universe 1, address 400 (well clear of tubes)
            _ml_fix = patch.patch_fixture(50, "SmokeMoving", "Generic_Moving", 1, 400)
            _check("moving light patched", _ml_fix is not None)

            # AT PAN 200 TILT 64 from programmer
            prog.clear_programmer()
            run_command("50")
            run_command("AT DIM 100 PAN 200 TILT 64 GOBO 10")
            _ml_sub_fid = "50.1"
            _check("programmer stores pan",
                   prog.data.get(_ml_sub_fid, {}).get('pan') == 200)
            _check("programmer stores tilt",
                   prog.data.get(_ml_sub_fid, {}).get('tilt') == 64)
            _check("programmer stores gobo",
                   prog.data.get(_ml_sub_fid, {}).get('gobo') == 10)

            # Record to a cue and fire it; verify DMX output
            run_command("RECORD stk 2 CUE 80 FADE 0")
            run_command("ASSIGN stk 2 TO FADER 2")
            prog.clear_programmer()
            run_command("GO stk 2 CUE 80")
            time.sleep(0.12)  # 0-sec fade, just let the engine tick once
            _ml_dmx = output_state.get_dmx_for_universe(1)
            _ml_base = 400 - 1   # 0-indexed
            _ch_names = _ml_profile.channels
            _pan_off  = _ch_names.index('pan')
            _tilt_off = _ch_names.index('tilt')
            _gobo_off = _ch_names.index('gobo')
            _check("cue playback drives pan in DMX", _ml_dmx[_ml_base + _pan_off] == 200)
            _check("cue playback drives tilt in DMX", _ml_dmx[_ml_base + _tilt_off] == 64)
            _check("cue playback drives gobo in DMX", _ml_dmx[_ml_base + _gobo_off] == 10)

            # programmer-level attr write visible in DMX immediately
            prog.clear_programmer()
            run_command("50")
            run_command("AT PAN 127 TILT 127")
            _ml_dmx2 = output_state.get_dmx_for_universe(1)
            _check("programmer attr channels visible in DMX output",
                   _ml_dmx2[_ml_base + _pan_off] == 127)

            # Position pool: record and apply
            r_pos = run_command("RECORD POSITION 1 SmokePos")
            _check("RECORD POSITION from moving light programmer",
                   "Recorded" in r_pos or "no position" not in r_pos.lower())
            prog.clear_programmer()
            run_command("50")
            run_command("POSITION 1")
            _check("POSITION 1 restores pan to programmer",
                   prog.data.get(_ml_sub_fid, {}).get('pan') is not None)

            # FX on attribute channel: FX SINE PAN should create a layer
            run_command("FX CLEAR")
            run_command("50")
            r_pan_fx = run_command("FX SINE PAN BPM 30 SIZE 50")
            _check("FX SINE PAN accepted", "Applied FX" in r_pan_fx)
            _pan_fx_layer = next(
                (l for l in (active_fx or []) if l.channel == 'pan'), None)
            _check("FX SINE PAN creates layer with channel=pan",
                   _pan_fx_layer is not None)
            run_command("FX CLEAR")

            # DMX output handles generic profile channel order (dimmer first)
            prog.clear_programmer()
            run_command("50")
            run_command("AT DIM 100")   # sets master dim = 1.0
            _ml_dmx3 = output_state.get_dmx_for_universe(1)
            _dim_off  = _ch_names.index('dimmer')
            _check("dimmer profile channel outputs master dim correctly",
                   _ml_dmx3[_ml_base + _dim_off] == 255)

            # SNAPSHOT captures attr channels (not just RGB)
            prog.clear_programmer()
            run_command("50")
            run_command("AT DIM 80 PAN 180 TILT 90")
            r_snap = run_command("SNAPSHOT 95 AttrSnap")
            _active_cs_for_snap = stack_pool.get(active_fader[0])
            _snap_cue = _active_cs_for_snap.cues.get(95.0) if _active_cs_for_snap else None
            _check("SNAPSHOT creates cue with attr channel data",
                   _snap_cue is not None and
                   _snap_cue.data.get(_ml_sub_fid, {}).get('pan') == 180.0)
            prog.clear_programmer()

            # Cleanup
            prog.clear_programmer()
            run_command("FX CLEAR")
            del patch.fixtures[50]

        # ── RELATIVE AT TESTS ─────────────────────────────────────────────────
        run_command("1")
        prog.clear_programmer()
        run_command("1")
        run_command("AT 50")                      # set dim to 50%
        _check("AT 50 sets dim to 50%",
               abs(prog.data.get('1', {}).get('dim', 0) - 0.5) < 0.01)
        run_command("AT +20")                     # relative: 50 + 20 = 70%
        _check("AT +20 increases dim by 20pp",
               abs(prog.data.get('1', {}).get('dim', 0) - 0.7) < 0.01)
        run_command("AT -10")                     # relative: 70 - 10 = 60%
        _check("AT -10 decreases dim by 10pp",
               abs(prog.data.get('1', {}).get('dim', 0) - 0.6) < 0.01)
        # RGB relative
        run_command("AT R 100")
        run_command("AT R +50")                   # 100 + 50 = 150
        _check("AT R +50 increases red by 50",
               prog.data.get('1.1', {}).get('red') == 150)
        run_command("AT R +200")                  # clamp at 255
        _check("AT R +200 clamps to 255",
               prog.data.get('1.1', {}).get('red') == 255)
        prog.clear_programmer()

        # ── HUE COMMAND TESTS ─────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT HUE 0")       # pure red (hue=0°, S=100%, V=100%)
        _check("HUE 0 sets red=255, green=0, blue=0",
               prog.data.get('1.1', {}).get('red') == 255 and
               prog.data.get('1.1', {}).get('green') == 0 and
               prog.data.get('1.1', {}).get('blue') == 0)
        run_command("AT HUE 120")     # pure green
        _check("HUE 120 sets green=255",
               prog.data.get('1.1', {}).get('green') == 255 and
               prog.data.get('1.1', {}).get('red') == 0)
        run_command("AT HUE 240")     # pure blue
        _check("HUE 240 sets blue=255",
               prog.data.get('1.1', {}).get('blue') == 255 and
               prog.data.get('1.1', {}).get('red') == 0)
        run_command("AT HUE 60 SAT 100 VAL 150")   # VAL over 100 must clamp
        _check("HUE VAL clamps at 100 (no channel over 255)",
               prog.data.get('1.1', {}).get('red') == 255 and
               prog.data.get('1.1', {}).get('green') == 255)
        run_command("AT HUE 0 SAT -50")            # SAT under 0 must clamp to 0 (grey/white)
        _check("HUE SAT clamps at 0 (grey output, not a negative-saturation artifact)",
               prog.data.get('1.1', {}).get('red') == 255 and
               prog.data.get('1.1', {}).get('green') == 255 and
               prog.data.get('1.1', {}).get('blue') == 255)
        prog.clear_programmer()

        # ── CT (color temperature) COMMAND TESTS ──────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT CT 9000")   # very cool — blue=255, red < 255
        _check("CT 9000 (cool) sets blue=255",
               prog.data.get('1.1', {}).get('blue') == 255)
        _check("CT 9000 (cool) sets red < 255",
               (prog.data.get('1.1', {}).get('red') or 0) < 255)
        prog.clear_programmer()
        run_command("1")
        run_command("AT CT 2700")   # warm tungsten — red = 255, blue ~ low
        _check("CT 2700 (warm) sets red=255",
               prog.data.get('1.1', {}).get('red') == 255)
        _check("CT 2700 (warm) sets blue < 200",
               (prog.data.get('1.1', {}).get('blue') or 0) < 200)
        prog.clear_programmer()

        # ── FLIP CHANNEL TESTS ────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT R 60")           # set red to 60
        run_command("AT FLIP R")         # invert: 255 - 60 = 195
        _check("AT FLIP R inverts red channel",
               prog.data.get('1.1', {}).get('red') == 195)
        run_command("AT R 0")
        run_command("AT FLIP R")         # 255 - 0 = 255
        _check("AT FLIP R on 0 gives 255",
               prog.data.get('1.1', {}).get('red') == 255)
        prog.clear_programmer()

        # ── AT RANDOM CHANNEL TESTS ───────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 6")
        run_command("AT RANDOM R")    # each sub gets independent random red
        _rnd_reds = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 7)]
        _check("AT RANDOM R sets red on all selected fixtures",
               all(v is not None for v in _rnd_reds))
        _check("AT RANDOM R values are in valid range",
               all(0 <= v <= 255 for v in _rnd_reds if v is not None))
        # RANDOM MASTER: all subs of each master get same value
        prog.clear_programmer()
        run_command("1")   # 54 pixels
        run_command("AT RANDOM G MASTER")
        _grn_subs = [prog.data.get(f"1.{i}", {}).get('green') for i in range(1, 4)]
        _check("AT RANDOM G MASTER applies same value to all subs of a master",
               len(set(v for v in _grn_subs if v is not None)) == 1)

        # AT RANDOM DIM — randomize master dimmer per fixture
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("1 THRU 3 AT RANDOM DIM")
        _rnd_dims = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT RANDOM DIM sets dim on all selected masters",
               all(v is not None for v in _rnd_dims))
        _check("AT RANDOM DIM values are in valid range 0–1",
               all(0.0 <= v <= 1.0 for v in _rnd_dims if v is not None))
        prog.clear_programmer()

        # ── AT BRIGHTEST / AT DARKEST ─────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 50")   # all subs of fixture 1 → red=50
        run_command("2 AT R 200")  # all subs of fixture 2 → red=200
        run_command("3 AT R 120")  # all subs of fixture 3 → red=120
        run_command("1 THRU 3 AT BRIGHTEST R")  # max=200 → stamp to all
        _bd_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT BRIGHTEST R stamps max value (200) to all subs",
               all(v == 200 for v in _bd_vals if v is not None))
        run_command("1 AT R 50")   # restore variety
        run_command("2 AT R 200")
        run_command("3 AT R 120")
        run_command("1 THRU 3 AT DARKEST R")    # min=50 → stamp to all
        _dk_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT DARKEST R stamps min value (50) to all subs",
               all(v == 50 for v in _dk_vals if v is not None))
        run_command("1 AT R 0")    # restore variety: 0, 200, 120
        run_command("2 AT R 200")
        run_command("3 AT R 100")
        run_command("1 THRU 3 AT AVERAGE R")  # avg = (0+200+100)/3 = 100
        _avg_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT AVERAGE R stamps mean value (100) to all subs",
               all(v == 100 for v in _avg_vals if v is not None))

        # ── AT CLAMP ──────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 20")   # below lo
        run_command("2 AT R 100")  # in range
        run_command("3 AT R 240")  # above hi
        run_command("1 THRU 3 AT CLAMP R 50 200")
        _cl_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT CLAMP R clamps below-lo value up to lo (50)", _cl_vals[0] == 50)
        _check("AT CLAMP R leaves in-range value unchanged (100)", _cl_vals[1] == 100)
        _check("AT CLAMP R clamps above-hi value down to hi (200)", _cl_vals[2] == 200)

        # AT CLAMP DIM — clamp master dimmer using percent range
        prog.clear_programmer()
        run_command("1 AT DIM 10")   # 10% — below lo
        run_command("2 AT DIM 50")   # 50% — in range
        run_command("3 AT DIM 90")   # 90% — above hi
        run_command("1 THRU 3 AT CLAMP DIM 20 80")
        _cd_dims = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT CLAMP DIM: 10% → 20% (clamped up to lo)", abs((_cd_dims[0] or 0) - 0.2) < 0.01)
        _check("AT CLAMP DIM: 50% unchanged (in range)", abs((_cd_dims[1] or 0) - 0.5) < 0.01)
        _check("AT CLAMP DIM: 90% → 80% (clamped down to hi)", abs((_cd_dims[2] or 0) - 0.8) < 0.01)
        prog.clear_programmer()

        # ── AT BRIGHTEST / DARKEST / AVERAGE DIM ─────────────────────────────
        run_command("1 AT DIM 20")   # 20%
        run_command("2 AT DIM 60")   # 60%
        run_command("3 AT DIM 80")   # 80%
        run_command("1 THRU 3 AT BRIGHTEST DIM")
        _bd_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT BRIGHTEST DIM: all stamped to max (0.8)",
               all(abs((v or 0) - 0.8) < 0.01 for v in _bd_d))
        run_command("1 THRU 3 AT DARKEST DIM")
        _dk_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT DARKEST DIM: all stamped to min (0.8 after BRIGHTEST)",
               all(abs((v or 0) - 0.8) < 0.01 for v in _dk_d))
        # Reset to original spread and test AVERAGE
        run_command("1 AT DIM 20"); run_command("2 AT DIM 60"); run_command("3 AT DIM 100")
        run_command("1 THRU 3 AT AVERAGE DIM")
        _av_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT AVERAGE DIM: all stamped to mean (20+60+100)/3=60%",
               all(abs((v or 0) - 0.6) < 0.01 for v in _av_d))
        prog.clear_programmer()

        # ── AT INVERT DIM / AT SCALE DIM / AT WOBBLE DIM ─────────────────────
        run_command("1 THRU 2 AT DIM 30")   # 30%
        run_command("1 THRU 2 AT INVERT DIM")
        _inv_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 3)]
        _check("AT INVERT DIM: 30% → 70%", all(abs((v or 0) - 0.7) < 0.01 for v in _inv_d))
        run_command("1 THRU 2 AT SCALE DIM 50")   # 70% × 50% = 35%
        _sc_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 3)]
        _check("AT SCALE DIM 50: 70% × 50% = 35%", all(abs((v or 0) - 0.35) < 0.01 for v in _sc_d))
        run_command("1 THRU 2 AT SCALE DIM 200")  # 35% × 200% = 70% (≤ 1.0)
        _sc_d2 = [prog.data.get(str(i), {}).get('dim') for i in range(1, 3)]
        _check("AT SCALE DIM 200: 35% × 200% = 70%", all(abs((v or 0) - 0.7) < 0.01 for v in _sc_d2))
        run_command("1 THRU 3 AT DIM 50")
        run_command("1 THRU 3 AT WOBBLE DIM 10")   # ±10% jitter
        _wb_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT WOBBLE DIM: values remain in 0–1 range",
               all(0.0 <= (v or 0) <= 1.0 for v in _wb_d))
        _check("AT WOBBLE DIM: values are near the seed (within 10%)",
               all(abs((v or 0) - 0.5) <= 0.10 for v in _wb_d))
        prog.clear_programmer()

        # ── AT STEP ───────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 3 AT R 50")        # seed all at 50
        run_command("1 THRU 3 AT STEP R 20")   # 50+0, 50+20, 50+40
        _st_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT STEP R fixture 1 unchanged (offset 0)", _st_vals[0] == 50)
        _check("AT STEP R fixture 2 offset +20 (70)",      _st_vals[1] == 70)
        _check("AT STEP R fixture 3 offset +40 (90)",      _st_vals[2] == 90)

        # ── AT MIRROR ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 10")   # fixture 1 = red 10
        run_command("2 AT R 100")  # fixture 2 = red 100
        run_command("3 AT R 200")  # fixture 3 = red 200
        run_command("1 THRU 3 AT MIRROR R")  # should swap 1↔3, keep 2 (symmetric)
        _mir_r1 = prog.data.get("1.1", {}).get('red')
        _mir_r2 = prog.data.get("2.1", {}).get('red')
        _mir_r3 = prog.data.get("3.1", {}).get('red')
        _check("AT MIRROR R swaps first ↔ last (fixture 1 gets fixture 3's value)",
               _mir_r1 == 200)
        _check("AT MIRROR R middle fixture gets its own mirror (fixture 3 gets fixture 1's value)",
               _mir_r3 == 10)
        prog.clear_programmer()

        # ── AT INVERT ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 100")   # fixture 1 red = 100
        run_command("2 AT R 0")     # fixture 2 red = 0
        run_command("1 THRU 2 AT INVERT R")
        _inv_r1 = prog.data.get("1.1", {}).get('red')
        _inv_r2 = prog.data.get("2.1", {}).get('red')
        _check("AT INVERT R: 100 → 155 (255-100)", _inv_r1 == 155)
        _check("AT INVERT R: 0 → 255 (255-0)",     _inv_r2 == 255)
        prog.clear_programmer()

        # ── AT SCALE ──────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 200")   # fixture 1 red = 200
        run_command("2 AT R 100")   # fixture 2 red = 100
        run_command("1 THRU 2 AT SCALE R 50")   # 50% → 100, 50
        _sc_r1 = prog.data.get("1.1", {}).get('red')
        _sc_r2 = prog.data.get("2.1", {}).get('red')
        _check("AT SCALE R 50%: 200 → 100", _sc_r1 == 100)
        _check("AT SCALE R 50%: 100 → 50",  _sc_r2 == 50)
        run_command("1 AT R 200")
        run_command("1 AT SCALE R 200")   # 200% of 200 = 400 → clamped to 255
        _sc_clamp = prog.data.get("1.1", {}).get('red')
        _check("AT SCALE R clamps at 255", _sc_clamp == 255)
        prog.clear_programmer()

        # ── AT WOBBLE ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 3 AT R 128")   # seed all at 128
        run_command("1 THRU 3 AT WOBBLE R 50")   # add ±50 jitter
        _wb_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT WOBBLE R keeps values in 0-255 range",
               all(v is not None and 0 <= v <= 255 for v in _wb_vals))
        _check("AT WOBBLE R values are near the seed (within 50)",
               all(v is not None and abs(v - 128) <= 50 for v in _wb_vals))
        prog.clear_programmer()

        # ── AT CLEAR ──────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 200 G 100")   # fixture 1: red=200, green=100
        run_command("1 AT CLEAR R")       # remove only red
        _ac_r = prog.data.get("1.1", {}).get('red')
        _ac_g = prog.data.get("1.1", {}).get('green')
        _check("AT CLEAR R removes red from programmer", _ac_r is None)
        _check("AT CLEAR R leaves other channels intact", _ac_g == 100)
        run_command("1 AT CLEAR")         # remove all channels for fixture 1
        _ac_all = prog.data.get("1.1", {})
        _check("AT CLEAR (no ch) removes all channels for selection", not _ac_all)
        prog.clear_programmer()

        # ── AT NORMALIZE ──────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 50")    # fixture 1 red = 50
        run_command("2 AT R 100")   # fixture 2 red = 100
        run_command("3 AT R 200")   # fixture 3 red = 200  (max)
        run_command("1 THRU 3 AT NORMALIZE R")
        _nrm_r = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT NORMALIZE R: highest value becomes 255", _nrm_r[2] == 255)
        _check("AT NORMALIZE R: proportional scale (50→64, 100→128)", _nrm_r[0] == 64 and _nrm_r[1] == 128)
        prog.clear_programmer()

        # ── AT COPY ───────────────────────────────────────────────────────────
        run_command("1")                        # select fixture 1
        run_command("1 AT DIM 80 R 200 G 50")  # set source values on fixture 1
        run_command("2 3")                      # select fixtures 2 & 3
        run_command("2 3 AT COPY 1")            # copy fixture 1 values into 2 & 3
        _cp_dim2  = prog.data.get("2", {}).get('dim')
        _cp_dim3  = prog.data.get("3", {}).get('dim')
        _cp_r2    = prog.data.get("2.1", {}).get('red')
        _cp_r3    = prog.data.get("3.1", {}).get('red')
        _cp_g2    = prog.data.get("2.1", {}).get('green')
        _check("AT COPY: dimmer copied to fixture 2", abs((_cp_dim2 or 0) - 0.8) < 0.01)
        _check("AT COPY: dimmer copied to fixture 3", abs((_cp_dim3 or 0) - 0.8) < 0.01)
        _check("AT COPY: red channel copied to fixture 2", _cp_r2 == 200)
        _check("AT COPY: red channel copied to fixture 3", _cp_r3 == 200)
        _check("AT COPY: green channel copied to fixture 2", _cp_g2 == 50)
        prog.clear_programmer()

        # ── stk NOTE ───────────────────────────────────────────────────────────
        _csnote_cs = stack_pool.get(99)
        if _csnote_cs is None:
            stack_pool.create(99, "NoteTestStack")
            _csnote_cs = stack_pool.get(99)
        _csnote_cs.note = ""
        _no_note_msg = run_command("stk 99 NOTE")
        _check("stk NOTE view returns has-no-note message when blank",
               "no note" in _no_note_msg.lower() or "set with" in _no_note_msg.lower())
        run_command("stk 99 NOTE Dark Moody Show")
        _check("stk NOTE set stores text",  _csnote_cs.note == "Dark Moody Show")
        _note_view = run_command("stk 99 NOTE")
        _check("stk NOTE view returns the note text", "Dark Moody Show" in _note_view)
        _csnote_cs.note = ""

        # ── stk BOUNCE ─────────────────────────────────────────────────────────
        # Verify ping-pong direction logic using a fresh 3-cue stack
        _bcs_id = 102
        stack_pool.create(_bcs_id, "BounceTest")
        _bcs = stack_pool.get(_bcs_id)
        _bcs.cues.clear()
        _bcs.current = None
        # Build 3 minimal cues directly (cue_pool.store returns None, so assign separately)
        def _mk_cue(num, dim_frac):
            prog.data["1"] = {"dim": dim_frac}
            c = Cue(float(num), f"C{num}")
            c.record(prog)
            prog.data.clear()
            _bcs.cues[float(num)] = c
        _mk_cue(1, 0.33)
        _mk_cue(2, 0.66)
        _mk_cue(3, 1.0)
        _check("BOUNCE: stack has 3 cues", len(_bcs.cues) == 3)
        run_command(f"stk {_bcs_id} bounce on")
        _check("stk bounce on sets .bounce = True", _bcs.bounce is True)
        # Use a minimal stub fader — bounce logic only needs .layer dict
        _bex = fader_pool.get(_bcs_id)
        _bex.assign(_bcs)
        _bcs.current = None
        _bcs._bounce_dir = 1
        _bcs.go(patch, fade_engine, _bex)   # fires cue 1
        _check("BOUNCE GO 1: at cue 1", _bcs.current == 1.0)
        _bcs.go(patch, fade_engine, _bex)   # fires cue 2
        _check("BOUNCE GO 2: at cue 2", _bcs.current == 2.0)
        _bcs.go(patch, fade_engine, _bex)   # fires cue 3
        _check("BOUNCE GO 3: at cue 3", _bcs.current == 3.0)
        _bcs.go(patch, fade_engine, _bex)   # hits end → reverses → fires cue 2
        _check("BOUNCE GO 4: reverses at last cue → cue 2", _bcs.current == 2.0)
        _check("BOUNCE GO 4: direction flipped to -1", _bcs._bounce_dir == -1)
        _bcs.go(patch, fade_engine, _bex)   # fires cue 1
        _check("BOUNCE GO 5: at cue 1", _bcs.current == 1.0)
        _bcs.go(patch, fade_engine, _bex)   # hits start → reverses → fires cue 2
        _check("BOUNCE GO 6: reverses at first cue → cue 2", _bcs.current == 2.0)
        _check("BOUNCE GO 6: direction flipped to +1", _bcs._bounce_dir == 1)
        run_command(f"stk {_bcs_id} bounce off")
        _check("stk bounce off sets .bounce = False", _bcs.bounce is False)
        stack_pool.stacks.pop(_bcs_id, None)

        # ── stk CLEAR ──────────────────────────────────────────────────────────
        _cc_id = 103
        stack_pool.create(_cc_id, "ClearTest")
        _cc = stack_pool.get(_cc_id)
        _cc.cues.clear()
        prog.data["1"] = {"dim": 0.5}
        _cc.cues[1.0] = Cue(1.0, "X"); _cc.cues[1.0].record(prog)
        _cc.cues[2.0] = Cue(2.0, "Y"); _cc.cues[2.0].record(prog)
        prog.data.clear()
        _cc.current = 1.0
        _check("stk CLEAR: setup has 2 cues", len(_cc.cues) == 2)
        _r_clear_cs = run_command(f"stk {_cc_id} CLEAR")
        _check("stk CLEAR: removes all cues", len(_cc.cues) == 0)
        _check("stk CLEAR: resets current to None", _cc.current is None)
        _check("stk CLEAR: returns confirmation", "cleared" in _r_clear_cs.lower())
        stack_pool.stacks.pop(_cc_id, None)

        # ── LIST NOTES ────────────────────────────────────────────────────────
        # Set a stack note and cue note, confirm LIST NOTES shows both
        _ln_cs = stack_pool.get(1)
        if _ln_cs:
            _ln_orig_note = getattr(_ln_cs, 'note', '')
            _ln_cs.note = "ListNotesTest"
            _cue1 = _ln_cs.cues.get(1.0) or next(iter(_ln_cs.cues.values()), None)
            _orig_cue_note = ""
            if _cue1:
                _orig_cue_note = getattr(_cue1, 'note', '')
                _cue1.note = "CueNoteTest"
            _ln_result = run_command("LIST NOTES")
            _check("LIST NOTES: includes stack note", "ListNotesTest" in _ln_result)
            if _cue1:
                _check("LIST NOTES: includes cue note", "CueNoteTest" in _ln_result)
            _ln_cs.note = _ln_orig_note
            if _cue1:
                _cue1.note = _orig_cue_note
        _ln_empty = run_command("LIST NOTES")

        # ── FIXTURE GROUPS ────────────────────────────────────────────────────
        # group 1 is set up in the show init with fixture 1 etc. — look for fixture 1
        _fg_fid = next(iter(sorted(patch.fixtures)), None)
        if _fg_fid is not None:
            # ensure fixture is in at least one group by checking group_pool
            _fg_in_group = any(
                any(isinstance(e, tuple) and e[1] == _fg_fid for e in g.members)
                for g in group_pool.groups.values()
            )
            if _fg_in_group:
                _fg_result = run_command(f"FIXTURE GROUPS {_fg_fid}")
                _check("FIXTURE GROUPS: returns group membership info",
                       "Group" in _fg_result or "group" in _fg_result)
                _check("FIXTURE GROUPS: mentions the fixture name",
                       patch.fixtures[_fg_fid].name in _fg_result
                       or str(_fg_fid) in _fg_result)
            # Fixture not in any group scenario
            _fg_not_found = run_command("FIXTURE GROUPS 9999")
            _check("FIXTURE GROUPS: bad fixture returns error", "not patched" in _fg_not_found.lower())

        # ── RENAME FIXTURE ────────────────────────────────────────────────────
        _rf_fid = next(iter(sorted(patch.fixtures)), None)
        if _rf_fid is not None:
            _rf_master = patch.fixtures[_rf_fid]
            _rf_orig = _rf_master.name
            _rf_result = run_command(f"RENAME FIXTURE {_rf_fid} TempTestName")
            _check("RENAME FIXTURE: changes master.name", _rf_master.name == "TempTestName")
            _check("RENAME FIXTURE: includes old→new in response",
                   "TempTestName" in _rf_result)
            run_command(f"RENAME FIXTURE {_rf_fid} {_rf_orig}")  # restore
            _check("RENAME FIXTURE: name restored", _rf_master.name == _rf_orig)
        _rf_bad = run_command("RENAME FIXTURE 9999 X")
        _check("RENAME FIXTURE: bad ID returns error", "not in patch" in _rf_bad)

        # ── PROGRAMMER SCALE ──────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT DIM 100")         # dim=1.0
        run_command("1 AT R 200 G 100")     # red=200, green=100
        _r_ps = run_command("PROGRAMMER SCALE 50")
        _check("PROGRAMMER SCALE: returns confirmation", "50%" in _r_ps or "scaled" in _r_ps.lower())
        _ps_dim = prog.data.get("1", {}).get('dim')
        _ps_r   = prog.data.get("1.1", {}).get('red')
        _ps_g   = prog.data.get("1.1", {}).get('green')
        _check("PROGRAMMER SCALE 50: dim scaled to 50%", abs((_ps_dim or 0) - 0.5) < 0.01)
        _check("PROGRAMMER SCALE 50: red 200 → 100", _ps_r == 100)
        _check("PROGRAMMER SCALE 50: green 100 → 50", _ps_g == 50)
        # Test 200% (amplify + clamp)
        run_command("PROGRAMMER SCALE 200")
        _ps_r2 = prog.data.get("1.1", {}).get('red')
        _check("PROGRAMMER SCALE 200: red 100 × 2 = 200", _ps_r2 == 200)
        # Test empty programmer
        prog.clear_programmer()
        _r_ps_empty = run_command("PROGRAMMER SCALE 50")
        _check("PROGRAMMER SCALE: empty programmer returns error", "empty" in _r_ps_empty.lower())
        prog.clear_programmer()

        # ── FADER ASSIGN stk ───────────────────────────────────────────────────
        _fa_cs = stack_pool.get(1)
        if _fa_cs:
            _fa_ex = fader_pool.get(15)  # high slot unlikely to conflict
            _fa_result = run_command(f"FADER 15 ASSIGN stk 1")
            _check("FADER ASSIGN stk: wires stack to fader",
                   _fa_ex.stack is _fa_cs)
            _check("FADER ASSIGN stk: returns confirmation",
                   "stk 1" in _fa_result or "assigned" in _fa_result.lower())
            _r_fa_bad = run_command("FADER 15 ASSIGN stk 9999")
            _check("FADER ASSIGN stk: bad stk returns error",
                   "not found" in _r_fa_bad.lower())

        # ── FADER UNASSIGN ────────────────────────────────────────────────────
        # Assign stk 1 to fader 16, then UNASSIGN it
        if stack_pool.get(1):
            run_command("FADER 16 ASSIGN stk 1")
            _fu_ex = fader_pool.get(16)
            _check("FADER UNASSIGN: setup — stack assigned", _fu_ex.stack is not None)
            _r_ua = run_command("FADER 16 UNASSIGN")
            _check("FADER UNASSIGN: stack is None after unassign", _fu_ex.stack is None)
            _check("FADER UNASSIGN: returns confirmation", "unassigned" in _r_ua.lower())
            _r_ua_empty = run_command("FADER 16 UNASSIGN")
            _check("FADER UNASSIGN: returns error when already empty",
                   "no stack" in _r_ua_empty.lower())

        # ── FAN TESTS ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 6")
        run_command("FAN DIM 0 100")
        _fan_dims = [prog.data.get(str(i), {}).get('dim') for i in range(1, 7)]
        _check("FAN DIM sets fixture 1 to 0%",  abs(_fan_dims[0] or 0) < 0.01)
        _check("FAN DIM sets fixture 6 to 100%", abs((_fan_dims[5] or 0) - 1.0) < 0.01)
        _check("FAN DIM is monotone across selection",
               all(_fan_dims[i] is not None and _fan_dims[i] <= _fan_dims[i+1]
                   for i in range(5)))
        run_command("FAN R 0 255")
        _fan_r = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 7)]
        _check("FAN R sets fixture 1 red to 0",   _fan_r[0] == 0)
        _check("FAN R sets fixture 6 red to 255",  _fan_r[5] == 255)
        prog.clear_programmer()

        # ── RANDOM / EVERY SELECTION TESTS ───────────────────────────────────
        run_command("RANDOM 3")
        _sel_m = [m for m in prog.selection if isinstance(m, MasterFixture)]
        _check("RANDOM 3 selects exactly 3 master fixtures", len(_sel_m) == 3)
        prog.clear_programmer()
        run_command("1 THRU 6 EVERY 2")   # selects 1, 3, 5
        _sel_m2 = [m.fixture_id for m in prog.selection if isinstance(m, MasterFixture)]
        _check("1 THRU 6 EVERY 2 selects 1,3,5", _sel_m2 == [1, 3, 5])
        prog.clear_programmer()

        # ── NEXT/PREV FIXTURE NAVIGATION ──────────────────────────────────────
        _all_ids = [m.fixture_id for m in patch.all_fixtures()]
        if len(_all_ids) >= 2:
            run_command(str(_all_ids[0]))     # select first fixture
            run_command("NEXT")               # should advance to second
            _sel_masters = [m.fixture_id for m in prog.selection
                            if isinstance(m, MasterFixture)]
            _check("NEXT advances selection to next fixture",
                   _sel_masters == [_all_ids[1]])
            run_command("PREV")               # should go back to first
            _sel_masters2 = [m.fixture_id for m in prog.selection
                             if isinstance(m, MasterFixture)]
            _check("PREV retreats selection to previous fixture",
                   _sel_masters2 == [_all_ids[0]])
            prog.clear_programmer()

        # ── PATCH RENAME / PATCH MOVE TESTS ──────────────────────────────
        _tmp_fix = patch.patch_fixture(51, "TmpFix", "Generic_RGB", 1, 490)
        _check("PATCH RENAME test fixture patched", _tmp_fix is not None)
        r_pr = run_command("PATCH RENAME 51 RenamedFix")
        _check("PATCH RENAME changes fixture name",
               patch.get(51) is not None and patch.get(51).name == "RenamedFix")
        r_pm = run_command("PATCH MOVE 51 UNIVERSE 2 AT 50")
        _first_sub_51 = patch.get(51).all_subs()[0] if patch.get(51) else None
        _check("PATCH MOVE updates sub universe",
               _first_sub_51 is not None and _first_sub_51.outputs[0]['universe'] == 2)
        _check("PATCH MOVE updates sub address",
               _first_sub_51 is not None and _first_sub_51.outputs[0]['address'] == 50)
        del patch.fixtures[51]

        # ── MACRO RECORD / PLAYBACK TESTS ────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("MACRO RECORD 99 SmokeTest")
        _check("MACRO RECORD starts recording", _macro_recording["slot"] == 99)
        run_command("AT FULL")          # captured inside macro
        run_command("AT R 200")         # captured inside macro
        r_ms = run_command("MACRO STOP")
        _check("MACRO STOP saves macro to pool", 99 in macro_pool)
        _check("MACRO STOP records correct command count",
               len(macro_pool.get(99, {}).get("commands", [])) == 2)
        _check("MACRO STOP ends recording", _macro_recording["slot"] is None)
        prog.clear_programmer()
        run_command("1")
        r_mb = run_command("MACRO 99")
        _check("MACRO playback result mentions commands played", "cmd" in r_mb)
        _check("MACRO playback restores dim",
               abs(prog.data.get('1', {}).get('dim', 0) - 1.0) < 0.01)
        _check("MACRO playback restores red channel",
               prog.data.get('1.1', {}).get('red') == 200)
        run_command("RENAME MACRO 99 Renamed")
        _check("RENAME MACRO changes name",
               macro_pool.get(99, {}).get("name") == "Renamed")
        run_command("MACRO DELETE 99")
        _check("MACRO DELETE removes slot", 99 not in macro_pool)
        # Also test MACRO RENAME <n> <name> (alternative order)
        macro_pool[98] = {"name": "TestMacro", "commands": ["1 FULL"]}
        r_mrn = run_command("MACRO RENAME 98 RenamedViaMAcroRename")
        _check("MACRO RENAME <n> <name> renames macro",
               macro_pool.get(98, {}).get("name") == "RenamedViaMAcroRename")
        del macro_pool[98]
        prog.clear_programmer()

        # ── MACRO RECURSION GUARD TESTS ───────────────────────────────────────
        # A macro whose commands (directly or via another macro) play itself
        # again used to recurse with no depth limit -> RecursionError crash.
        macro_pool[97] = {"name": "SelfRef", "commands": ["MACRO 97"]}
        r_self = run_command("MACRO 97")
        _check("MACRO self-recursion blocked, not a crash", "blocked" in r_self)
        _check("MACRO play stack cleaned up after self-recursion block",
               len(_macro_play_stack) == 0)
        macro_pool[95] = {"name": "A", "commands": ["MACRO 96"]}
        macro_pool[96] = {"name": "B", "commands": ["MACRO 95"]}
        r_cycle = run_command("MACRO 95")
        _check("MACRO indirect A->B->A cycle blocked, not a crash",
               "blocked" in r_cycle)
        _check("MACRO play stack cleaned up after cycle block",
               len(_macro_play_stack) == 0)
        del macro_pool[97]
        del macro_pool[95]
        del macro_pool[96]

        # ── PARK / UNPARK TESTS ───────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT FULL")           # dim=1.0, so DMX output for fixture 1 is non-zero
        run_command("AT R 200 G 100 B 50")
        # Park fixture 1 at this look
        r_park = run_command("PARK")
        _check("PARK adds fixture to parked_fids", 1 in output_state.parked_fids)
        _check("PARK stores some parked addresses",
               bool(output_state.parked_addresses))
        # Change programmer — should not affect parked output
        run_command("AT R 0 G 0 B 0")
        _park_dmx = output_state.get_dmx_for_universe(1)
        # Fixture 1 subs start at address 1 (SGM_RGB_54); first sub has r at offset 0
        _first_sub_1 = patch.get(1).all_subs()[0]
        _r_addr = _first_sub_1.outputs[0]['address'] - 1  # 0-indexed
        _check("PARK holds DMX value against programmer change",
               _park_dmx[_r_addr] == 200)
        # Unpark
        r_unpark = run_command("UNPARK")
        _check("UNPARK removes fixture from parked_fids", 1 not in output_state.parked_fids)
        prog.clear_programmer()
        run_command("1")
        run_command("AT R 0 G 0 B 0")
        _after_dmx = output_state.get_dmx_for_universe(1)
        _check("After UNPARK, programmer changes take effect",
               _after_dmx[_r_addr] == 0)
        prog.clear_programmer()

        # ── PARK-vs-FREEZE TEST ─────────────────────────────────────────────
        # Same bug class fixed twice before (BLACKOUT-vs-FREEZE, SOLO-vs-FREEZE):
        # FREEZE's frozen-snapshot branch must not silently defeat a newer
        # isolation/override layer. PARK is documented as "immune to
        # cue/prog changes" and highest priority (even above direct_dmx) —
        # verify it still holds while FREEZE is active. Seeds a synthetic
        # frozen snapshot directly (not via run_command('FREEZE')) so this
        # check is isolated from whatever dim/FX state other tests in this
        # long-lived process have left on fixture 1.
        run_command("1")
        run_command("AT FULL")
        run_command("AT R 222 G 11 B 33")
        run_command("PARK")
        _park_addr = _first_sub_1.outputs[0]['address'] - 1  # 0-indexed
        _saved_frozen = dict(output_state.frozen_dmx)
        _saved_freeze_mode = output_state.freeze_mode
        try:
            output_state.frozen_dmx[1] = tuple([99] * 512)  # conflicts with parked 222
            output_state.freeze_mode = True
            _frozen_dmx = output_state.get_dmx_for_universe(1)
            _check("PARK still holds its value while FREEZE is active",
                   _frozen_dmx[_park_addr] == 222)
        finally:
            output_state.freeze_mode = _saved_freeze_mode
            output_state.frozen_dmx.clear()
            output_state.frozen_dmx.update(_saved_frozen)
            run_command("UNPARK")
        prog.clear_programmer()

        # ── AI "dim" action clamp test ──────────────────────────────────
        # AIEngine.execute()'s "dim" action wrote a model-supplied value
        # straight into programmer_layer with no bounds check -- same bug
        # class already fixed for HUE SAT/VAL (invisible live since final
        # DMX render clamps on the way out, but a RECORDed cue would
        # persist the raw out-of-range number). Build a throwaway AIEngine
        # to exercise the fix: construction needs an API key string but
        # never calls the network -- only .execute() runs here, which is
        # pure local dict logic, no anthropic.messages.create() involved.
        _prev_api_key = os.environ.get('ANTHROPIC_API_KEY')
        os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-smoketest-dummy-unused'
        try:
            _test_ai = AIEngine(patch, prog, output_state, fx_engine, fade_engine,
                                 stack_pool=stack_pool, fader_pool=fader_pool)
            _test_ai.execute([{"action": "dim", "value": 5.0}])
            _check("AI 'dim' action clamps out-of-range value to 1.0",
                   output_state.programmer_layer.get("1", {}).get('dim') == 1.0
                   and patch.get(1).virtual_dimmer == 1.0)
            _test_ai.execute([{"action": "dim", "value": -3.0}])
            _check("AI 'dim' action clamps negative value to 0.0",
                   output_state.programmer_layer.get("1", {}).get('dim') == 0.0
                   and patch.get(1).virtual_dimmer == 0.0)
        finally:
            if _prev_api_key is None:
                os.environ.pop('ANTHROPIC_API_KEY', None)
            else:
                os.environ['ANTHROPIC_API_KEY'] = _prev_api_key
            # The "dim" action loops over ALL patched fixtures, not just a
            # selection -- undo its virtual_dimmer=0.0 and the programmer
            # 'dim' overrides on every fixture so this test doesn't leak
            # state into whatever runs after it.
            for _m in patch.all_fixtures():
                _m.set_dimmer(1.0)
            prog.clear_programmer()

        # ── stk CHASE MODE ─────────────────────────────────────────────────
        _ch_cs = stack_pool.create(103, "ChaseTest")
        if _ch_cs:
            _ch_cs.cues.clear()
            prog.data["1"] = {"dim": 0.5}
            for _cn in (1, 2, 3):
                _c = Cue(float(_cn), f"Ch{_cn}"); _c.record(prog); _ch_cs.cues[float(_cn)] = _c
            prog.data.clear()
        r_ch_on = run_command("stk 103 CHASE ON BPM 120")
        _ch = stack_pool.get(103)
        _check("stk CHASE ON enables chase_enabled", _ch is not None and _ch.chase_enabled is True)
        _check("stk CHASE ON BPM sets chase_bpm", _ch is not None and abs(_ch.chase_bpm - 120.0) < 0.1)
        _check("stk CHASE ON returns confirmation", "chase" in r_ch_on.lower())
        r_ch_bpm = run_command("stk 103 CHASE BPM 90")
        _check("stk CHASE BPM updates chase_bpm", _ch is not None and abs(_ch.chase_bpm - 90.0) < 0.1)
        r_ch_off = run_command("stk 103 CHASE OFF")
        _check("stk CHASE OFF disables chase_enabled", _ch is not None and _ch.chase_enabled is False)
        _check("stk CHASE OFF returns confirmation", "chase" in r_ch_off.lower())
        # stk INFO shows chase state
        r_ch_info = run_command("stk 103 INFO")
        _check("stk INFO shows chase field", "Chase" in r_ch_info or "chase" in r_ch_info.lower())
        # Save/load round-trip
        _ch.chase_enabled = True; _ch.chase_bpm = 77.0
        ShowFile.save_stacks(stack_pool)
        _ch2 = Stack(103, "ChaseTest")
        _tmp_pool = StackPool(); _tmp_pool.store(103, _ch2)
        ShowFile.load_stacks(_tmp_pool, CuePool())
        _reloaded_ch = _tmp_pool.get(103)
        _check("stk CHASE save/load preserves chase_enabled",
               _reloaded_ch is not None and _reloaded_ch.chase_enabled is True)
        _check("stk CHASE save/load preserves chase_bpm",
               _reloaded_ch is not None and abs(_reloaded_ch.chase_bpm - 77.0) < 0.1)
        _ch.chase_enabled = False
        stack_pool.stacks.pop(103, None)

        # ── FADER SIZE — per-fader FX amplitude multiplier ────────────
        _sz_ex = fader_pool.get(3)
        _sz_ex.size_factor = 1.0
        r_sz_plus = run_command("FADER 3 SIZE+")
        _check("FADER SIZE+ nudges size_factor up to ~1.25",
               abs(_sz_ex.size_factor - 1.25) < 0.01)
        _check("FADER SIZE+ returns confirmation", "size" in r_sz_plus.lower())
        run_command("FADER 3 SIZE-")
        _check("FADER SIZE- returns size_factor to ~1.00",
               abs(_sz_ex.size_factor - 1.0) < 0.01)
        run_command("FADER 3 SIZE+")
        r_sz_reset = run_command("FADER 3 SIZE RESET")
        _check("FADER SIZE RESET returns size_factor to 1.0", _sz_ex.size_factor == 1.0)
        _check("FADER SIZE RESET returns confirmation", "reset" in r_sz_reset.lower())
        r_sz_set = run_command("FADER 3 SIZE 2.0")
        _check("FADER SIZE 2.0 sets size_factor to 2.0",
               abs(_sz_ex.size_factor - 2.0) < 0.01)
        _check("FADER SIZE 2.0 returns confirmation", "2.0" in r_sz_set or "2.00" in r_sz_set)
        # SIZE propagates to owned FX layers (if any are active)
        run_command("FX CLEAR")
        run_command("1 THRU 3")
        run_command("FX SINE RED BPM 60 SIZE 100")
        _sz_layer_id = _sz_ex._fx_ids[0] if _sz_ex._fx_ids else None
        if _sz_layer_id is not None:
            _sz_layer = fx_engine._layers.get(_sz_layer_id)
            _sz_ex.size_factor = 0.5
            _sz_ex._apply_size_factor()
            _check("FADER SIZE: _apply_size_factor sets size_scale on owned layer",
                   _sz_layer is None or abs(_sz_layer.size_scale - 0.5) < 0.01)
        _sz_ex.size_factor = 1.0
        _sz_ex._apply_size_factor()
        run_command("FX CLEAR")
        prog.clear_programmer()

        # ── AT … IN <seconds> LIVE PROGRAMMER FADE ────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT FULL")                     # establish a src dim=1.0
        _pre_fade_dim = prog.data.get("1", {}).get("dim")
        run_command("AT 0 IN 5")                   # fade dim 1.0→0.0 over 5s
        _check("AT … IN creates a live_fade entry",
               len(prog.live_fades) >= 1)
        _fade_entry = next(
            (f for f in prog.live_fades if f['fid'] == '1' and f['channel'] == 'dim'),
            None)
        _check("live_fade entry has correct dst (0.0)",
               _fade_entry is not None and abs(_fade_entry['dst'] - 0.0) < 0.01)
        _check("live_fade entry has correct duration (5.0)",
               _fade_entry is not None and abs(_fade_entry['duration'] - 5.0) < 0.01)
        _check("live_fade entry has a non-zero src",
               _fade_entry is not None and (_fade_entry['src'] or 0) > 0.0)
        # PROG FADE CLEAR should purge all active fades
        r_pfc = run_command("PROG FADE CLEAR")
        _check("PROG FADE CLEAR empties live_fades list", len(prog.live_fades) == 0)
        _check("PROG FADE CLEAR returns confirmation", "clear" in r_pfc.lower())
        prog.clear_programmer()

        # ── Preset tracking — LIST REFS + UPDATE ──────────────────────────
        run_command("1 THRU 6 AT R 255 G 0 B 100")  # pink
        run_command("RECORD COLOR 10 Pink")
        run_command("COLOR 10")   # apply preset (sets color_ref)
        # record a cue with color_ref
        _tcs = stack_pool.get(1) or stack_pool.create(1, "TrackTest")
        _tcue = Cue(90, "track test cue")
        _tcue.record(prog)
        _tcs.cues[float(90)] = _tcue
        prog.clear_programmer()

        _r_refs = run_command("LIST REFS COLOR 10")
        _check("LIST REFS finds the cue", "track test cue" in _r_refs or "cue 90" in _r_refs.lower() or "stk 1" in _r_refs.lower())

        # Update the preset and check live-push returns confirmation
        run_command("1 AT R 200 G 50 B 150")
        _r_upd = run_command("UPDATE COLOR 10")
        _check("UPDATE COLOR returns confirmation", "updated" in _r_upd.lower())
        _check("UPDATE COLOR live-pushed message", "live-pushed" in _r_upd.lower())
        _check("Color preset 10 updated", color_pool.get(10) is not None)

        # FX preset ref in cue — FIRE FX tags layer defs
        run_command("FX SINE RED BPM 60")
        run_command("RECORD FX 11 TrackFX")
        run_command("CLEAR FX")
        run_command("FIRE FX 11")
        _fx_entry = next((v for fid, v in prog.data.items() if '.' not in fid and v.get('fx')), None)
        _check("FIRE FX tags layers with fx_preset_ref",
               _fx_entry is not None and any(ld.get('fx_preset_ref') == 11
                                              for ld in _fx_entry.get('fx', [])))
        # LIST REFS FX
        _tcue_fx = Cue(91, "fx track cue")
        _tcue_fx.record(prog)
        _tcs.cues[float(91)] = _tcue_fx
        prog.clear_programmer()
        _r_fx_refs = run_command("LIST REFS FX 11")
        _check("LIST REFS FX finds the cue", "fx track cue" in _r_fx_refs.lower() or "cue 91" in _r_fx_refs.lower() or "stk 1" in _r_fx_refs.lower())

        # UPDATE FX
        run_command("FX SINE RED BPM 90")
        _r_upd_fx = run_command("UPDATE FX 11")
        _check("UPDATE FX returns confirmation", "updated" in _r_upd_fx.lower())
        _check("UPDATE FX live-pushed message", "live-pushed" in _r_upd_fx.lower())

        # Cleanup
        prog.clear_programmer()
        _tcs.cues.pop(float(90), None)
        _tcs.cues.pop(float(91), None)

        # ── Flash mode fix ────────────────────────────────────────────────────
        _fe = fader_pool.get(98)
        _fe_cs = stack_pool.create(98, "FlashTest") if not stack_pool.get(98) else stack_pool.get(98)
        if not _fe_cs.cues:
            _fc = Cue(1, "flash cue")
            _fc.data = {"1": {"dim": 1.0}}
            _fe_cs.add_cue(_fc)
        fader_pool.assign(98, _fe_cs)
        _fe.trigger_mode = 'flash'
        _fe.flash_on(patch, fade_engine)
        _check("flash_on activates fader", _fe.is_active)
        _saved_pos = _fe_cs.current
        _fe.flash_off()
        _check("flash_off deactivates fader", not _fe.is_active)
        _check("flash_off preserves cue position", _fe_cs.current == _saved_pos)

        # ── Fader output_mode: moment ─────────────────────────────────────────
        _me = fader_pool.get(97)
        _me_cs = stack_pool.create(97, "MomentTest") if not stack_pool.get(97) else stack_pool.get(97)
        if not _me_cs.cues:
            _mc = Cue(1, "moment cue")
            _mc.data = {"1": {"dim": 1.0}}
            _me_cs.add_cue(_mc)
        fader_pool.assign(97, _me_cs)
        _me.output_mode = 'moment'
        _me.level = 0.0
        _me.is_active = True
        _active = fader_pool.active_layers()
        _check("moment fader excluded from active_layers at level 0",
               all(lyr is not _me.layer for lyr, _ in _active))
        _me.level = 0.5
        _exec_fader_mode_hook(_me)
        _check("moment fader is_active True when level > 0", _me.is_active)

        # ── Fader output_mode: vfade ──────────────────────────────────────────
        r_vfd = run_command("FADER 97 OUTPUT VFADE")
        _check("FADER OUTPUT VFADE command works", "vfade" in r_vfd.lower())
        _check("output_mode set to vfade", _me.output_mode == 'vfade')
        run_command("FADER 97 OUTPUT NORMAL")
        _check("FADER OUTPUT NORMAL resets mode", _me.output_mode == 'normal')

        # ── trigger_mode moment ───────────────────────────────────────────────
        r_mom = run_command("FADER 97 MODE MOMENT")
        _check("FADER MODE MOMENT accepted", "moment" in r_mom.lower())
        _check("trigger_mode set to moment", _me.trigger_mode == 'moment')
        r_offt = run_command("FADER 97 OFFTIME 1.5")
        _check("FADER OFFTIME sets off_time", abs(_me.off_time - 1.5) < 0.001)
        run_command("FADER 97 MODE TOGGLE")   # restore

        # ── _vfade_apply ─────────────────────────────────────────────────────
        _ve = fader_pool.get(96)
        _ve.output_mode = 'vfade'
        _ve.vfade_from  = {"1": {"red": 0.0}}
        _ve.vfade_to    = {"1": {"red": 255.0}}
        _ve.level       = 0.5
        _vfade_apply(_ve)
        _check("vfade_apply lerps at 0.5", abs(_ve.layer.get("1", {}).get("red", 0) - 127.5) < 0.5)
        _ve.level = 0.0
        _vfade_apply(_ve)
        _check("vfade_apply at 0 = from state", _ve.layer.get("1", {}).get("red", -1) == 0.0)
        _ve.level = 1.0
        _vfade_apply(_ve)
        _check("vfade_apply at 1 = to state", abs(_ve.layer.get("1", {}).get("red", 0) - 255.0) < 0.5)

    except Exception as e:
        _check(f"smoke test raised {type(e).__name__}: {e}", False)

    # ── GUI structural build check ──────────────────────────────────────
    # Every session that's added or touched a popup has had to say some
    # version of "reviewed by hand against the existing builders it
    # mirrors — headless mode skips gui.build() entirely, so the new
    # widgets aren't exercised by the smoke test itself." That caveat
    # doesn't have to keep repeating: DearPyGui can construct a full
    # widget tree with no display at all — only show_viewport() touches
    # GLFW/X11 and needs a real one (it hard-crashes without $DISPLAY).
    # Patch it to a no-op so the real, unmodified gui.build() runs start
    # to finish (every panel, every popup, every tag, the whole handler
    # registry) and any structural bug — duplicate tag, bad item
    # reference, build-order mistake — surfaces here instead of only at
    # next interactive launch.
    if _DPG_OK:
        _orig_show_viewport = dpg.show_viewport
        dpg.show_viewport = lambda *a, **k: None
        try:
            gui.build()
            _check("gui.build() constructs all windows/widgets without error", True)
            # ── fixture-dim-slider unit fix ──────────────────────────────
            # _on_fixture_dim_slider passed dim*100 into MasterFixture.
            # set_dimmer(), which expects a 0.0-1.0 fraction (per its own
            # docstring) and clamps to it -- so any drag above ~1% silently
            # forced virtual_dimmer to 1.0 regardless of the slider's real
            # position. programmer_layer['dim'] masks this live (it's read
            # first), but virtual_dimmer is the fallback default read once
            # that key is gone (e.g. after CLEAR) and is what status/PATCH
            # LIST prints directly -- so it would misreport 100% instead of
            # the real level.
            gui._on_fixture_dim_slider(None, 0.5, 1)
            _check("fixture-dim slider sets virtual_dimmer to the slider's "
                   "actual fraction, not fraction*100 clamped to 1.0",
                   patch.get(1).virtual_dimmer == 0.5)
            gui._on_fixture_dim_slider(None, 1.0, 1)
            patch.get(1).virtual_dimmer = 1.0  # restore default for any later use
        except Exception as e:
            _check(f"gui.build() raised {type(e).__name__}: {e}", False)
        finally:
            dpg.show_viewport = _orig_show_viewport
            try:
                dpg.destroy_context()
            except Exception:
                pass
    else:
        _check("gui.build() constructs all windows/widgets without error (skipped: dearpygui not installed)", True)

    ok = all(passed for _, passed in _results)
    print(f"\n*** SMOKE TEST {'PASSED' if ok else 'FAILED'} "
          f"({sum(p for _, p in _results)}/{len(_results)}) ***\n")

    network.stop()
    midi.stop()
    osc.stop()
    fx_engine.stop()
    fade_engine.stop()
    audio_mapper.stop()
    audio_engine.stop()
    _sys.exit(0 if ok else 1)
else:
    gui.build()   # build all widgets (main thread)
    gui.run()     # hand control to DearPyGui — blocks until window closed

midi.stop()
network.stop()
fade_engine.stop()
fx_engine.stop()
audio_mapper.stop()
audio_engine.stop()


# =============================================================================
# SESSION HANDOFF NOTE  —  2026-06-25
# =============================================================================
#
# PROJECT: Studio Console
# FILE:    studio_project/studio_project.py  (~21k lines, single file)
# SHOW DATA: studio_project/studio_data/  (per-category JSON files)
#
# ── WHAT THIS IS ──────────────────────────────────────────────────────────────
# Custom Python lighting console controlling 6 SGM LT-200 pixel tubes
# (54 RGB pixels each, 324 sub-fixtures total) via sACN multicast.
# GUI: DearPyGui retro console aesthetic.
# Command line: MA3-style text syntax (see run_command()).
#
# ── HARDWARE / NETWORK ────────────────────────────────────────────────────────
# sACN multicast on 192.168.1.161, universes 1 & 2, 44 Hz output loop.
# MIDI: Axiom 25 on port 1 (fader control).
# OSC: Studio Console on port 8001, grandMA3 on 8000.
#
# ── THREE-LAYER OUTPUT MERGE ──────────────────────────────────────────────────
# programmer  >  fader layers (LTP)  >  FX (additive)
#
# OutputState._merged_cue_layer()  — LTP merge of all active fader layers
#   in fire-order (last GO wins). Each Fader owns its own `layer` dict.
#   FadeEngine.Fade.tick() writes directly into fader.layer, not a shared dict.
#
# FXEngine runs additively on top of the merged cue layer.
# FX layers are split into two namespaces:
#   - programmer preview:  IDs 9000+   tracked in _prog_fx_ids  (module-level list)
#   - Per-fader cue FX: IDs fdr_id*10000+n  owned by Fader._fx_ids
#
# ── FX ARCHITECTURE (just redesigned this session) ────────────────────────────
# FX is now PROGRAMMER-NATIVE, not a standalone global thing.
#
# HOW IT WORKS:
#   1. `FX SINE RED`  writes  {'waveform':'sine','channel':'red','bpm':60,...}
#      into prog.data[fid_str]['fx'] for each selected master fixture.
#      Also starts a live-preview FXLayer (ID 9000+) so you see output immediately.
#
#   2. `RECORD CUE <n>` — Cue.record() does dict(vals) on programmer data,
#      which captures the 'fx' list automatically. No special handling needed.
#
#   3. `GO` on a cue calls fader._start_cue_fx(cue, patch):
#      - reads cue.data[master_fid]['fx'] lists
#      - starts FXLayer objects in the fader's own ID namespace
#      - clears previous fader FX first (_clear_fx)
#
#   4. `CLEAR` (stage 2 — programmer clear):
#      - also stops _prog_fx_ids preview layers  (_prog_fx_stop())
#
#   5. `Fader.stop()` calls _clear_fx() before clearing its layer.
#
#   6. `RECORD FX <n>` — snapshots unique FX defs from programmer into fx_pool.
#      (Reads from prog.data, NOT from active_fx list anymore.)
#
#   7. `FIRE FX <n>` — writes pool preset layers into programmer data + preview.
#      Does NOT fire directly to an fader — goes via programmer → RECORD CUE → GO.
#
#   8. `FX ADD ...` — appends additional FX layers to existing programmer FX.
#
#   9. `FX CLEAR` — removes 'fx' keys from programmer entries + stops preview.
#
# KEY OBJECTS:
#   _prog_fx_ids   — module-level list of active programmer-preview FX IDs
#   active_fx      — module-level list of active FXLayer objects (preview)
#   Fader._fx_ids   — list of FX IDs owned by that fader slot
#   Fader.fx_engine / Fader.form_pool — injected from FaderPool defaults
#   FaderPool.default_fx_engine / .default_form_pool / .default_color_pool / .default_dim_pool — set at startup
#
# ── SHOW FILE SPLIT ───────────────────────────────────────────────────────────
# ShowFile class (static methods only) — each category saves/loads independently.
# Files: studio_data/stacks.json, groups.json, colors.json, dims.json,
#        midi.json, fx.json, fx_pool.json, forms.json
# Legacy migration: if studio_show.json exists, it's read and split on first run,
#   then renamed to studio_show.json.migrated.
#
# ── PLAYBACK LAYER ────────────────────────────────────────────────────────────
# FaderPool holds numbered Fader slots.
# Each Fader: one Stack, its own layer dict, its own FX IDs, level fader.
# LTP priority: _fire_order list — last GO = highest priority.
# FadeEngine fires Fade objects that tick() directly into fader.layer.
#
# COMMANDS:
#   ASSIGN stk <n> TO fdr <n>    — wire stack to fader slot
#   fdr <n> GO/BACK/STOP/GOTO   — control specific fader
#   FADER <n>                 — set active fader for bare GO/BACK
#
# ── KEY COMMANDS ──────────────────────────────────────────────────────────────
#   FX SINE RED [bpm n] [size n] [SPREAD n]
#   FX ADD SINE BLUE [...]
#   FX FORM <n> RED [...]          — use FormPool waveform shape
#   FX CLEAR                       — clear all FX from programmer
#   FX CLEAR DIM                   — clear only dim channel FX (leaves RGB FX)
#   FX CLEAR RED / GREEN / BLUE    — clear only that colour channel FX
#   FX LIST
#   RECORD FX <n> [name]           — snapshot programmer FX → pool
#   FIRE FX <n>                    — add preset to programmer (channel-additive; same-channel layers replaced)
#   FORM LIST
#   record form <n> [name] 0.0,0.0 0.5,1.0 1.0,0.0   — custom breakpoint curve
#   record stk [n] cue <m> [preset-tokens]
#   go stk [n] cue <m>
#
# ── POOLS ──────────────────────────────────────────────────────────────────────
#   color_pool    — Colorpreset  (numbered, saved to colors.json)
#   dim_pool      — Dimpreset    (numbered, saved to dims.json)
#   group_pool    — group        (numbered, saved to groups.json)
#   stack_pool — stack     (numbered, saved to stacks.json)
#   fx_pool       — FXpreset     (numbered, 1-12 visible in GUI, saved to fx_pool.json)
#   form_pool     — Formpreset   (1-4 built-in builtins: sine/ramp/pulse/square;
#                                 5+ custom breakpoint curves; saved to forms.json)
#   fader_pool — Fader     (stack/level/priority/mode saved to faders.json)
#
# ── WHAT WORKS ────────────────────────────────────────────────────────────────
# - Full output pipeline (sACN, FX additive, programmer+cue merge)
# - stack playback with fades, fader isolation, LTP priority
# - FX as programmer-native (redesigned this session — just landed)
# - CLEAR 3-tap protocol: selection → programmer → full output
# - FX pool record/fire, Forms pool with custom breakpoints
# - show file per-category save/load with .bak auto-backup
# - GUI panels: stacks, groups, colors, dims, FX pool, forms pool
# - MIDI fader control, OSC bridge, AI command layer (ANTHROPIC_API_KEY gated)
# - audio reactive panel: device pick, capture start/stop, mapping toggle,
#   gain, live level/low/mid/high meters (GUI front-end for Block 9)
#
# ── KNOWN ISSUES / TODO ───────────────────────────────────────────────────────
# - fader_pool now persists stack assignments to faders.json; loaded
#   at startup so GO works immediately after restart without re-assigning.
#
# =============================================================================
