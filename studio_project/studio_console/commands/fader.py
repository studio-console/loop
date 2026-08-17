"""Studio Console command dispatch — FADER/FDR, PAGE, PRIORITY, RELEASE.

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


def cmd_010_fader_swap(t0, tokens, raw):
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


def cmd_011_fader_all_clear(t0, tokens, raw):
    if t0 in ('FADER', 'FDR') and len(tokens) >= 3 and tokens[1] == 'ALL' and tokens[2].upper() == 'CLEAR':
        cleared = 0
        for ex in fader_pool.faders.values():
            ex.stop()
            if ex.stack:
                ex.stack.current = None
            cleared += 1
        return f"all {cleared} fader(s) cleared"


def cmd_012_fader_main(t0, tokens, raw):
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


def cmd_013_page(t0, tokens, raw):
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


def cmd_016_fader_select(t0, tokens, raw):
    if t0 in ('FADER_SELECT', 'FADER') and len(tokens) == 2:
        try:
            n = int(tokens[1])
        except ValueError:
            return f"FADER: bad fader number '{tokens[1]}'"
        active_fader[0] = n
        ex = fader_pool.get(n)
        cs_name = ex.stack.name if ex.stack else "(no stack)"
        return f"active fader → {n}  [{cs_name}]"


def cmd_094_priority(t0, tokens, raw):
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


def cmd_095_release(t0, tokens, raw):
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


