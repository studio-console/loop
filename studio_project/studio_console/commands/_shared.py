"""Studio Console command-dispatch shared helpers — extracted from
run_command()'s nested closures (_record_cue_into, _prog_fx_stop,
_prog_fx_start, _prog_fx_rebuild). This is Phase 8 of the run_command
split: hoisting the shared logic to module-level functions with the SAME
signatures they already had (verified: none of the four closures over
run_command's own per-call locals — t0/tokens/raw/cmd_str — only over
module-level globals), done as its own step BEFORE touching any of
run_command's 117 dispatch branches, so this genuinely non-mechanical
transform (nested closures -> module functions) is isolated from the
mostly-mechanical branch relocation that comes after it.

All of patch/prog/fader_pool/etc. below are safe as plain top-level
imports (not the deferred from __main__ pattern used elsewhere in this
split): studio_console.state's import in studio_project.py comes BEFORE
run_command's definition in the original file, and this package replaces
run_command at that same position, so by the time anything in
studio_console.commands gets imported, state.py has already run.
"""

import re as _re
import copy as _copy

from studio_console.state import (
    patch, prog, fade_engine, fader_pool, color_pool, dim_pool, group_pool,
    cue_pool, fx_engine, active_fx, _prog_fx_ids, _fx_params,
    _apply_timing_edit, _on_cue_fire, save_show,
)
from studio_console.engine.fx import (
    _bucket_fx_defs, _expand_color_fx, _expand_group_fx, _fx_grouping_compat,
)
from studio_console.models.fixtures import MasterFixture


def _delete_with_undo(pool_dict, slot_id, description):
    """Delete pool_dict[slot_id], first snapshotting it onto prog's undo
    stack (see programmer.push_delete_undo in models/fixtures.py) so
    UNDO/Backspace/Ctrl+Z can put it right back.

    pool_dict — the raw {id: object} dict a pool keeps its slots in
        (color_pool.presets, group_pool.groups, stack_pool.stacks,
        form_pool.forms, ...). Every one of these pools' own delete()
        is a plain dict.pop() with no other side effect (verified against
        each class), so re-inserting the same object at the same key on
        undo is a complete, exact restore.
    slot_id     — the pool slot number.
    description — short human-readable label for the "N step(s)
        remaining" message (e.g. "color 4").

    Returns True if something was actually deleted, False if the slot was
    already empty (caller keeps its own "already empty" message in that
    case — nothing pushed onto the undo stack for a no-op).
    """
    slot_id = int(slot_id)
    if slot_id not in pool_dict:
        return False
    snapshot = pool_dict[slot_id]

    def _restore():
        pool_dict[slot_id] = snapshot
        save_show()

    prog.push_delete_undo(description, _restore)
    del pool_dict[slot_id]
    save_show()
    return True


def _snapshot_undo(pool_dict, slot_id, description):
    """Snapshot pool_dict[slot_id]'s CURRENT value — or the fact the slot
    is currently empty — onto prog's undo stack, before a RECORD or UPDATE
    command overwrites it. Call this right before the write; unlike
    _delete_with_undo, this doesn't perform the write itself (RECORD/UPDATE
    commands each build their own replacement object in ways too varied to
    standardize here), it just captures what to restore if the operator
    changes their mind.

    pool_dict   — the raw {id: object} dict a pool keeps its slots in.
    slot_id     — the pool slot number about to be written.
    description — short human-readable label for the "N step(s)
        remaining" message (e.g. "record color 4").
    """
    slot_id = int(slot_id)
    had_prior = slot_id in pool_dict
    prior = pool_dict.get(slot_id)

    def _restore():
        if had_prior:
            pool_dict[slot_id] = prior
        else:
            pool_dict.pop(slot_id, None)
        save_show()

    prog.push_delete_undo(description, _restore)


def _resolve_fx_selection_targets():
    """Resolve prog.selection into (sel_fids, sub_indices_by_fid) for FX
    targeting — shared by the FX-apply command (cmd_039_fx_main) and
    FIRE FX (cmd_041_fire_fx), which both used to independently collapse
    every selected SubFixture down to its master's plain fixture_id and
    lose the sub-selection entirely: selecting only some pixels of a
    fixture (e.g. "1.1 THRU 1.10" on a 54-pixel fixture) still applied FX
    to the whole fixture, because prog.data's 'fx' entries only ever live
    under the master's id and _bucket_fx_defs always expanded via
    master.all_subs() with no way to restrict it.

    sel_fids       — master fixture ids to apply FX to, patch order.
    sub_indices_by_fid — {master_id: [sub_index, ...]}, present ONLY for a
        fixture whose selection is a genuine partial sub-selection (some
        but not all of its subs, with the master itself never selected —
        selecting the MasterFixture auto-expands to every sub via
        programmer.select(), which is "the whole fixture", not partial).
        A fixture absent from this dict means "apply to the whole
        fixture", exactly like before this existed.
    """
    seen_m, sel_fids = [], []
    masters_selected = set()
    subs_by_master = {}
    for f in prog.selection:
        if isinstance(f, MasterFixture):
            mid = f.fixture_id
            masters_selected.add(mid)
        else:
            mid = f.master_id
            subs_by_master.setdefault(mid, set()).add(f.sub_index)
        if mid not in seen_m:
            seen_m.append(mid)
            sel_fids.append(mid)
    sub_indices_by_fid = {}
    for mid, subs in subs_by_master.items():
        if mid in masters_selected:
            continue
        master = patch.get(mid)
        if master and len(subs) < len(master.all_subs()):
            sub_indices_by_fid[mid] = sorted(subs)
    return sel_fids, sub_indices_by_fid


def _record_cue_into(stk, cue_num, suffix_tokens, raw_str, merge=False):
    """
    Apply preset tokens then record (or merge-update) a cue into stk.
    suffix_tokens: everything after CUE <num> (already upper-cased).
    raw_str: original mixed-case command (for quoted name search).
    merge=True  → UPDATE mode: merges programmer into existing cue.
    merge=False → RECORD mode: replaces cue data entirely.
    Returns result string.
    """
    # Snapshot whatever's there before any of this function's three write
    # paths (timing-only edit, UPDATE merge, full RECORD) touch it — all
    # three MUTATE the existing Cue object in place rather than replacing
    # the dict slot with a new one (cue.update()/_apply_timing_edit()), so
    # a reference-only snapshot ("prior = stk.cues.get(cue_num)") would
    # just point at the same, already-mutated object afterward. A deep
    # copy is required; stk.cues[n] and cue_pool.cues[n] are normally the
    # SAME object for a whole-numbered cue, but restored independently
    # here (each a slot-replace with its own snapshot) rather than relying
    # on that aliasing surviving undo — simpler, and nothing else in this
    # codebase depends on those two dicts holding the literal same object.
    _pool_n = int(cue_num) if cue_num == int(cue_num) else None
    _had_cue = cue_num in stk.cues
    _cue_snap = _copy.deepcopy(stk.cues[cue_num]) if _had_cue else None
    _had_pool_cue = _pool_n is not None and _pool_n in cue_pool.cues
    _pool_cue_snap = _copy.deepcopy(cue_pool.cues[_pool_n]) if _had_pool_cue else None

    def _push_cue_undo(description):
        def _restore():
            if _had_cue:
                stk.cues[cue_num] = _cue_snap
            else:
                stk.cues.pop(cue_num, None)
            if _pool_n is not None:
                if _had_pool_cue:
                    cue_pool.cues[_pool_n] = _pool_cue_snap
                else:
                    cue_pool.cues.pop(_pool_n, None)
            save_show()
        prog.push_delete_undo(description, _restore)

    _KW = {'FADE', 'INFADE', 'OUTFADE', 'DELAY', 'FOLLOW', 'FXOUTFADE',
           'CFADE', 'CINFADE', 'DFADE', 'DINFADE', 'CDELAY', 'DDELAY',
           'GROUP', 'COLOR', 'COLOUR', 'DIM'}

    # Quoted name wins; otherwise build from leading non-keyword tokens.
    # If no name is given and a cue already exists at this number, keep its name.
    name_match = _re.search(r'"([^"]*)"', raw_str)
    if name_match:
        name = name_match.group(1)
        # Everything below scans `up` with plain \bKEYWORD\s+<number>
        # regexes (_get_timing/_extract_int) that have no concept of
        # quote boundaries — a cue literally named e.g. "dim 25" or
        # "fade 3 to black" would otherwise get misread as FADE/DIM/etc.
        # keyword+value pairs baked into the quoted name text. Mask the
        # quoted span out before building `up` so only real keyword
        # tokens outside the name are ever matched.
        _scan_str = raw_str[:name_match.start()] + raw_str[name_match.end():]
    else:
        _scan_str = raw_str
        name_parts = []
        for tok in suffix_tokens:
            if tok in _KW or (tok and tok[0].isdigit()):
                break
            name_parts.append(tok.lower())
        if name_parts:
            name = " ".join(name_parts)
        else:
            existing = stk.get_cue(cue_num)
            name = existing.name if existing else f"cue {cue_num:.0f}"

    up = _scan_str.upper()

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
    # 0 resets to auto, same convention _apply_timing_edit already uses
    # for an existing cue — see the plain-RECORD branch below, which used
    # to never set this at all: FXOUTFADE only ever worked via a
    # follow-up UPDATE CUE, silently dropped on a brand-new RECORD CUE.
    _fxo = _get_timing('FXOUTFADE')
    fx_outfade = (None if _fxo == 0.0 else _fxo) if _fxo is not None else None

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

    # Name-based preset tokens — lets a BARE (unquoted) leading word
    # double as both the cue's name and a preset recall, e.g.
    # "RECORD CUE 1 red" naming the cue "red" AND applying a color
    # preset literally named "red" if one exists. Only runs when there's
    # no quoted name: with one (name_match truthy), the whole quoted
    # string is the name and nothing about it should be reinterpreted as
    # command syntax. This used to run unconditionally, scanning suffix_
    # tokens (which include a quoted name's own words) for anything
    # that happened to match a saved preset — so naming a cue e.g.
    # "violet low (both pool)" silently applied whatever preset was
    # named exactly "low" to the live programmer before recording,
    # overwriting a dim value that had nothing to do with the name at
    # all. Same bug class as the *_ref keyword-scanning fix a few
    # commits back (quoted user text getting reparsed as command
    # syntax), different mechanism (exact-name token match, not a
    # regex), so that fix didn't cover this one.
    if not name_match:
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

    # Any non-empty per-fixture entry counts as real programmer content —
    # including one that's fx_kill-only (from CLEAR FX / KILL FX). This used
    # to exclude fx_kill-only entries so a bare timing edit (CFADE/DFADE)
    # wouldn't accidentally wipe cue data, but that made fx_kill silently
    # NOT get merged by UPDATE CUE either: CLEAR FX -> UPDATE reported
    # "saved to cue" while actually falling through to the timing-only
    # branch below and never calling cue.update(prog) at all, so the kill
    # never made it into the cue and FX resumed on release. fx_kill is
    # meant to be recordable (see CLEAR FX / KILL FX's own return
    # messages), so it has to count here for that to work.
    _prog_has_dmx = any(bool(vals) for vals in prog.data.values())

    if not _prog_has_dmx:
        # programmer has no DMX data — allow timing/name update on any existing cue.
        existing = stk.get_cue(cue_num)
        if existing:
            _push_cue_undo(f"{'update' if merge else 'record'} cue {cue_num} timing")
            # _scan_str (not raw_str) — same quoted-name mask computed
            # above, so a rename like RECORD CUE 1 "cfade 9 rename" can't
            # also silently set a colour-group fade override from text
            # inside the name (_apply_timing_edit does its own
            # raw_str.upper() + \bKEYWORD\s+<number> scan internally,
            # with no awareness of quote boundaries either).
            _apply_timing_edit(existing, _scan_str)
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
        _push_cue_undo(f"update cue {cue_num}")
        cue.update(prog)
        _apply_timing_edit(cue, _scan_str)   # _scan_str — see comment above
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

    _push_cue_undo(f"record cue {cue_num}")
    cue = stk.record_cue(cue_num, prog, name=name, fade_time=fade)
    cue.delay_time  = delay
    cue.follow_time = follow
    cue.fade_times  = fade_times
    cue.delay_times = delay_times
    cue.fx_outfade  = fx_outfade
    if cue_num == int(cue_num):
        cue_pool.store(int(cue_num), cue)
    save_show()
    return f"recorded: {cue}  into {stk.name}  (auto-saved)"

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
        _mirror, _cluster, _order = _fx_grouping_compat(ld)
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
            order        = _order,
            direction    = ld.get('direction','forward'),
            mirror       = _mirror,
            cluster      = _cluster,
            low          = ld.get('low', 0.0),
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


__all__ = ["_record_cue_into", "_prog_fx_stop", "_prog_fx_start", "_prog_fx_rebuild",
           "_resolve_fx_selection_targets"]
