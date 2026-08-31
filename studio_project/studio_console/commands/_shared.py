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

from studio_console.state import (
    patch, prog, fade_engine, fader_pool, color_pool, dim_pool, group_pool,
    cue_pool, fx_engine, active_fx, _prog_fx_ids, _fx_params,
    _apply_timing_edit, _on_cue_fire, save_show,
)
from studio_console.engine.fx import _bucket_fx_defs, _expand_color_fx, _expand_group_fx


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
            grouping     = ld.get('grouping'),
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


__all__ = ["_record_cue_into", "_prog_fx_stop", "_prog_fx_start", "_prog_fx_rebuild"]
