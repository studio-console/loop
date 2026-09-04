"""Studio Console command dispatch — PATCH, FIXTURE SWAP/GROUPS/INFO, COPY FIXTURE.

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


def cmd_062_patch_main(t0, tokens, raw):
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


def cmd_091_fixture_swap(t0, tokens, raw):
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


def cmd_092_fixture_groups(t0, tokens, raw):
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
            for _type, member_fid in g.members:
                if _type == 'master' and member_fid == fid:
                    containing.append(f"  group {gid}: {g.name} (whole fixture)")
                    break
                if _type == 'sub' and str(member_fid).split('.', 1)[0] == str(fid):
                    containing.append(f"  group {gid}: {g.name} (sub-fixture {member_fid})")
        if not containing:
            return f"fixture {fid} '{master.name}' is not in any group"
        lines = [f"Fixture {fid} '{master.name}' appears in {len(containing)} group entry/entries:"]
        lines.extend(containing)
        return "\n".join(lines)


def cmd_093_fixture_info(t0, tokens, raw):
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


def cmd_104_copy_fixture_to(t0, tokens, raw):
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


def cmd_126_viz_layout(t0, tokens, raw):
    """VIZ LAYOUT — set/clear/list a per-fixture stage-view pixel grid
    override, replacing what used to be a hardcoded fixture-id set in
    gui/stage.py. Stored on the fixture itself (MasterFixture.viz_layout)
    and persisted in patch.json alongside the rest of the patch, so it's
    real, editable show data instead of a code change.

    VIZ LAYOUT                                        — list all overrides
    VIZ LAYOUT [<range>] GRID <cols>x<rows> [ORDER]    — set an override
    VIZ LAYOUT [<range>] AUTO                          — clear an override
    <range> defaults to the current programmer selection if omitted.
    ORDER defaults to ROWMAJOR (left-to-right, top-to-bottom fill); use
    COLMAJOR for physical wiring that runs down each column before
    moving to the next (e.g. several vertical strips side by side).
    """
    if t0 != 'VIZ' or len(tokens) < 2 or tokens[1] != 'LAYOUT':
        return None

    if len(tokens) == 2:
        overrides = [(m.fixture_id, m.viz_layout) for m in patch.all_fixtures()
                     if getattr(m, 'viz_layout', None)]
        if not overrides:
            return "VIZ LAYOUT: no fixtures have a custom layout (all auto-fit)"
        lines = [f"  {fid}: {lay['cols']}x{lay['rows']} {lay.get('order', 'rowmajor')}"
                 for fid, lay in overrides]
        return "custom viz layouts:\n" + "\n".join(lines)

    rest = tokens[2:]
    kw_idx = next((i for i, t in enumerate(rest) if t in ('GRID', 'AUTO')), None)
    if kw_idx is None:
        return ("usage: VIZ LAYOUT [<range>] GRID <cols>x<rows> [ROWMAJOR|COLMAJOR]"
                 "  |  VIZ LAYOUT [<range>] AUTO  |  VIZ LAYOUT")
    range_tokens  = rest[:kw_idx]
    action_tokens = rest[kw_idx:]

    # A range given inline (e.g. "1 THRU 4") reuses the programmer's own
    # selection parser — same engine "1 THRU 6", "1 + 3", "ALL" etc. use
    # everywhere else, so range syntax here is identical to every other
    # command instead of a second, separately-maintained parser. No range
    # given falls back to whatever's currently selected.
    targets = prog._parse_selection(range_tokens) if range_tokens else list(prog.selection)
    if not targets:
        return "VIZ LAYOUT: no fixtures specified — give a range (e.g. 1 THRU 4) or select fixtures first"

    # A viz layout is a whole-fixture property — collapse any sub-fixture
    # selection up to its owning master rather than silently ignoring it
    # (the isinstance-MasterFixture-only bug that's recurred for other
    # commands earlier — see NEXT/PREV and cmd_sel_count's own fixes).
    master_ids = set()
    for f in targets:
        if isinstance(f, SubFixture):
            master_ids.add(f.master_id)
        elif isinstance(f, MasterFixture):
            master_ids.add(f.fixture_id)
    masters = [m for m in (patch.get(mid) for mid in sorted(master_ids)) if m]
    if not masters:
        return "VIZ LAYOUT: no valid fixtures in that range"

    if action_tokens[0] == 'AUTO':
        for m in masters:
            m.viz_layout = None
        save_show()
        return f"viz layout: {len(masters)} fixture(s) reset to auto-fit"

    if len(action_tokens) < 2:
        return "usage: VIZ LAYOUT [<range>] GRID <cols>x<rows> [ROWMAJOR|COLMAJOR]"
    grid_spec = _re.match(r'^(\d+)x(\d+)$', action_tokens[1].lower())
    if not grid_spec:
        return f"VIZ LAYOUT: bad grid spec '{action_tokens[1]}' — expected <cols>x<rows>, e.g. 6x9"
    cols, rows = int(grid_spec.group(1)), int(grid_spec.group(2))
    if cols < 1 or rows < 1:
        return "VIZ LAYOUT: cols and rows must both be at least 1"

    order = 'rowmajor'
    if len(action_tokens) >= 3:
        if action_tokens[2] not in ('ROWMAJOR', 'COLMAJOR'):
            return f"VIZ LAYOUT: bad order '{action_tokens[2]}' — expected ROWMAJOR or COLMAJOR"
        order = action_tokens[2].lower()

    mismatched = [m.fixture_id for m in masters if m.pixel_count != cols * rows]
    for m in masters:
        m.viz_layout = {"cols": cols, "rows": rows, "order": order}
    save_show()
    applied = [m.fixture_id for m in masters]
    warn = ""
    if mismatched:
        warn = (f"  — WARNING: fixture(s) {mismatched} don't have {cols * rows} pixels; "
                "stage view falls back to auto-fit for those until the grid size matches")
    return f"viz layout: {cols}x{rows} {order} set on fixture(s) {applied}{warn}"


def cmd_127_viz_position(t0, tokens, raw):
    """VIZ POSITION — set/clear/list a per-fixture placement in the 3D
    rig viz window. Stored on the fixture itself (MasterFixture.
    viz_position) and persisted in patch.json, mirroring VIZ LAYOUT
    above almost exactly — same dispatch shape, same range-parsing
    fallback to the current selection, same whole-fixture collapse, same
    list/set/clear three-way.

    VIZ POSITION                                  — list all overrides
    VIZ POSITION [<range>] AT x,y,z [yaw] [pitch]  — set a placement
    VIZ POSITION [<range>] CLEAR                   — clear (auto-arrange)
    <range> defaults to the current programmer selection if omitted.
    x,y,z are feet; yaw is degrees (spin left/right around the vertical
    axis), default 0; pitch is degrees (nose up/down — how the fixture
    is physically mounted, e.g. a truss par angled down at the stage),
    default 0, or whatever is already set if omitted (only yaw resets
    to 0 when left off — pitch is left alone so re-aiming a fixture's
    yaw doesn't undo its mount angle).
    """
    if t0 != 'VIZ' or len(tokens) < 2 or tokens[1] != 'POSITION':
        return None

    if len(tokens) == 2:
        overrides = [(m.fixture_id, m.viz_position) for m in patch.all_fixtures()
                     if getattr(m, 'viz_position', None)]
        if not overrides:
            return "VIZ POSITION: no fixtures have a custom placement (all auto-arranged)"
        lines = [f"  {fid}: x={p['x']:.1f} y={p['y']:.1f} z={p['z']:.1f} "
                 f"yaw={p.get('yaw', 0.0):.0f} pitch={p.get('pitch', 0.0):.0f}"
                 for fid, p in overrides]
        return "custom viz positions:\n" + "\n".join(lines)

    rest = tokens[2:]
    kw_idx = next((i for i, t in enumerate(rest) if t in ('AT', 'CLEAR')), None)
    if kw_idx is None:
        return ("usage: VIZ POSITION [<range>] AT x,y,z [yaw] [pitch]"
                 "  |  VIZ POSITION [<range>] CLEAR  |  VIZ POSITION")
    range_tokens  = rest[:kw_idx]
    action_tokens = rest[kw_idx:]

    targets = prog._parse_selection(range_tokens) if range_tokens else list(prog.selection)
    if not targets:
        return "VIZ POSITION: no fixtures specified — give a range (e.g. 1 THRU 4) or select fixtures first"

    master_ids = set()
    for f in targets:
        if isinstance(f, SubFixture):
            master_ids.add(f.master_id)
        elif isinstance(f, MasterFixture):
            master_ids.add(f.fixture_id)
    masters = [m for m in (patch.get(mid) for mid in sorted(master_ids)) if m]
    if not masters:
        return "VIZ POSITION: no valid fixtures in that range"

    if action_tokens[0] == 'CLEAR':
        for m in masters:
            m.viz_position = None
        save_show()
        return f"viz position: {len(masters)} fixture(s) reset to auto-arrange"

    if len(action_tokens) < 2:
        return "usage: VIZ POSITION [<range>] AT x,y,z [yaw] [pitch]"
    coord_spec = _re.match(r'^(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)$', action_tokens[1])
    if not coord_spec:
        return f"VIZ POSITION: bad coordinate '{action_tokens[1]}' — expected x,y,z, e.g. 3,0,-2"
    try:
        x, y, z = (float(coord_spec.group(i)) for i in (1, 2, 3))
    except ValueError:
        return f"VIZ POSITION: bad coordinate '{action_tokens[1]}'"

    yaw = 0.0
    if len(action_tokens) >= 3:
        try:
            yaw = float(action_tokens[2])
        except ValueError:
            return f"VIZ POSITION: bad yaw '{action_tokens[2]}' — expected a number in degrees"

    pitch_given = None
    if len(action_tokens) >= 4:
        try:
            pitch_given = float(action_tokens[3])
        except ValueError:
            return f"VIZ POSITION: bad pitch '{action_tokens[3]}' — expected a number in degrees"

    for m in masters:
        existing_pitch = (m.viz_position or {}).get('pitch', 0.0)
        pitch = pitch_given if pitch_given is not None else existing_pitch
        m.viz_position = {"x": x, "y": y, "z": z, "yaw": yaw, "pitch": pitch}
    save_show()
    applied = [m.fixture_id for m in masters]
    return f"viz position: x={x} y={y} z={z} yaw={yaw} pitch={pitch} set on fixture(s) {applied}"


