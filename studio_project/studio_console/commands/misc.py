"""Studio Console command dispatch — STATUS/SHOW INFO, LIST, RENAME, CLONE, output status, list refs.

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


def cmd_042_clone_to(t0, tokens, raw):
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


def cmd_052_output_status(t0, tokens, raw):
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


def cmd_057_show_info(t0, tokens, raw):
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


def cmd_072_status_state(t0, tokens, raw):
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


def cmd_090_list_main(t0, tokens, raw):
    # run_command is defined by commands/__init__.py's dispatcher,
    # which imports from this module — true circular dependency, not
    # just an ordering one. Deferred import, resolved only when this
    # function is actually called (well after all modules load).
    from __main__ import run_command
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


def cmd_103_rename(t0, tokens, raw):
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


def cmd_124_list_refs(t0, tokens, raw):
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


