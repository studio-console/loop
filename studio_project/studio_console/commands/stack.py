"""Studio Console command dispatch — STACK/STK, GO/BACK/GOTO/RELOAD, RECORD CUE, cue timing/note/shift, COPY/MOVE cue+stack.

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


def cmd_006_stack_select(t0, tokens, raw):
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


def cmd_007_record_stack_settings(t0, tokens, raw):
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


def cmd_009_assign_stk_to(t0, tokens, raw):
    # Was a run_command-local computed just before this branch in
    # the original file; inlined here since it depends on this
    # call's tokens, not something shareable across branches.
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


def cmd_017_go_fade(t0, tokens, raw):
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


def cmd_018_go(t0, tokens, raw):
    if t0 == 'GO' and len(tokens) == 1:
        cue_go()
        stk = _active_stack()
        cur = stk.current if stk else None
        return f"GO → cue {cur}" if cur else "GO (no cue)"


def cmd_019_back(t0, tokens, raw):
    if t0 == 'BACK' and len(tokens) == 1:
        cue_back()
        stk = _active_stack()
        cur = stk.current if stk else None
        return f"BACK → cue {cur}" if cur else "BACK (no cue)"


def cmd_020_goto(t0, tokens, raw):
    if t0 == 'GOTO' and len(tokens) > 1:
        try:
            num = float(tokens[1])
            result = goto_cue(num)
            return result or f"GOTO → cue {num}"
        except ValueError:
            return f"GOTO: bad cue number '{tokens[1]}'"


def cmd_021_reload(t0, tokens, raw):
    if t0 == 'RELOAD' and len(tokens) == 1:
        return cue_reload() or "reloaded"


def cmd_022_delete_cue(t0, tokens, raw):
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


def cmd_023_delete_other(t0, tokens, raw):
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


def cmd_024_record_stk_cue(t0, tokens, raw):
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


def cmd_025_record_cue(t0, tokens, raw):
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'CUE':
        try:
            cue_num = float(tokens[2])
        except ValueError:
            return f"RECORD: bad cue number '{tokens[2]}'"
        stk = _active_stack()
        if not stk:
            return "RECORD CUE: no active stack — use RECORD STACK 1 first"
        return _record_cue_into(stk, cue_num, tokens[3:], raw)


def cmd_026_update_alias(t0, tokens, raw):
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


def cmd_027_go_back_stk_no_cue(t0, tokens, raw):
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


def cmd_028_go_stk_cue(t0, tokens, raw):
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


def cmd_073_cues_list(t0, tokens, raw):
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


def cmd_098_cue_note(t0, tokens, raw):
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


def cmd_099_cue_show_info(t0, tokens, raw):
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


def cmd_100_cue_timing(t0, tokens, raw):
    # Was a run_command-local computed just before this branch (and
    # cmd_101, below) in the original file; inlined in both since it
    # depends on this call's tokens.
    _TIMING_KW = {'FADE', 'INFADE', 'OUTFADE', 'DELAY', 'FOLLOW',
                  'CFADE', 'CINFADE', 'DFADE', 'DINFADE', 'CDELAY', 'DDELAY'}
    _has_timing = bool(_TIMING_KW & set(tokens))
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


def cmd_101_stk_cue_timing(t0, tokens, raw):
    # See cmd_100_cue_timing above — same inlined constant.
    _TIMING_KW = {'FADE', 'INFADE', 'OUTFADE', 'DELAY', 'FOLLOW',
                  'CFADE', 'CINFADE', 'DFADE', 'DINFADE', 'CDELAY', 'DDELAY'}
    _has_timing = bool(_TIMING_KW & set(tokens))
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


def cmd_102_cue_shift(t0, tokens, raw):
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


def cmd_105_copy_cue_stk(t0, tokens, raw):
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


def cmd_106_move_cue_stk(t0, tokens, raw):
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


def cmd_107_copy_to_variant(t0, tokens, raw):
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


def cmd_125_update_main(t0, tokens, raw):
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
                    grouping=ld.get('grouping'),
                    low=ld.get('low', 0.0),
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


