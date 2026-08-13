"""Studio Console show-file persistence — extracted from studio_project.py
(the "Block 14: show File Persistence" section: _write_file, _read_file,
ShowFile). Pure move, zero behavior change, EXCEPT one deliberate addition:
ShowFile's static methods construct several model classes (Cue, Stack, Group,
ColorPreset, DimmerPreset, FXPreset, FormPreset, RatePreset, SizePreset,
SpreadPreset, SpeedMaster) that haven't been extracted into
studio_console/models/ yet (a later phase). Since this module is only ever
imported by studio_project.py itself, and all of those classes are defined
earlier in studio_project.py than ShowFile was, a module-level `from __main__
import (...)` is safe here — by the time studio_project.py's own execution
reaches the line that imports this module, those classes already exist in
`__main__`'s namespace. (This is different from a similar situation in
drivers/ai.py, which needed a function-local deferred import instead — for a
different reason, see that file's docstring if you're curious. Don't copy that
pattern here; the module-level form below is correct for this file.) Once
those classes move to studio_console/models/, update the import below to pull
from there instead — do not do that now, that path doesn't exist yet.
"""

import os
import json
import copy
import shutil as _shutil

from studio_console.paths import DATA_DIR, SAVES_DIR, _LEGACY_FILE
from __main__ import (
    Cue, Stack, Group, ColorPreset, DimmerPreset, FXPreset, FormPreset,
    RatePreset, SizePreset, SpreadPreset, SpeedMaster,
)

def _write_file(path, doc):
    """Backup the existing file then write doc as JSON."""
    if os.path.exists(path):
        _shutil.copy2(path, path + '.bak')
    with open(path, 'w') as f:
        json.dump(doc, f, indent=2)


def _read_file(path):
    """Return parsed JSON or None if missing/corrupt."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"  {os.path.basename(path)}: unreadable — {e}")
        return None


class ShowFile:
    VERSION    = "3.0"
    FX_SCALE   = 2       # bump when size/spread scale changes

    # ── Per-category file paths ──────────────────────────────
    STACKS = os.path.join(DATA_DIR, "stacks.json")
    GROUPS    = os.path.join(DATA_DIR, "groups.json")
    COLORS    = os.path.join(DATA_DIR, "colors.json")
    DIMS      = os.path.join(DATA_DIR, "dims.json")
    MIDI      = os.path.join(DATA_DIR, "midi.json")
    FX        = os.path.join(DATA_DIR, "fx.json")
    FX_POOL   = os.path.join(DATA_DIR, "fx_pool.json")
    FORMS     = os.path.join(DATA_DIR, "forms.json")
    RATES     = os.path.join(DATA_DIR, "rate_pool.json")
    SIZES     = os.path.join(DATA_DIR, "size_pool.json")
    SPREADS   = os.path.join(DATA_DIR, "spread_pool.json")
    SPEEDS    = os.path.join(DATA_DIR, "speedmaster_pool.json")
    PATCH     = os.path.join(DATA_DIR, "patch.json")
    # Attribute pools — one file per attribute family
    POSITION  = os.path.join(DATA_DIR, "position_pool.json")
    GOBO      = os.path.join(DATA_DIR, "gobo_pool.json")
    ZOOM      = os.path.join(DATA_DIR, "zoom_pool.json")
    FOCUS     = os.path.join(DATA_DIR, "focus_pool.json")
    BEAM      = os.path.join(DATA_DIR, "beam_pool.json")
    CONTROL   = os.path.join(DATA_DIR, "control_pool.json")
    GDTF_DIR  = os.path.join(DATA_DIR, "gdtf")
    STATE     = os.path.join(DATA_DIR, "state.json")
    FADER_PAGES   = os.path.join(DATA_DIR, "fader_pages.json")
    FADERS    = os.path.join(DATA_DIR, "faders.json")
    CHANGELOG    = os.path.join(DATA_DIR, "changelog.json")
    AI_PROMPTS   = os.path.join(DATA_DIR, "ai_prompts.json")
    DEFAULTS     = os.path.join(DATA_DIR, "defaults.json")
    OSC_TARGETS  = os.path.join(DATA_DIR, "osc_targets.json")
    NETWORK      = os.path.join(DATA_DIR, "network.json")
    MACROS       = os.path.join(DATA_DIR, "macros.json")

    # ── Save ────────────────────────────────────────────────

    @staticmethod
    def _migrate_fx_ld(ld):
        """Rescale a single FX layer dict from old (size 0-255, spread 0-1/10) to new 0-100."""
        sz = ld.get('size', 100.0)
        if sz > 100.0:
            ld['size'] = round((sz / 255.0) * 100.0, 1)
        sp = ld.get('spread', 0.0)
        if 0.0 < sp <= 10.0:
            ld['spread'] = min(100.0, round(sp * 100.0, 1))   # old 0-1.0 → new 0-100
        elif sp > 100.0:
            ld['spread'] = 100.0

    @staticmethod
    def _migrate_fx_scale(data):
        """Walk a cue data dict and migrate all embedded FX layer dicts."""
        for fvals in data.values():
            if not isinstance(fvals, dict):
                continue
            for ld in fvals.get('fx', []):
                ShowFile._migrate_fx_ld(ld)

    @staticmethod
    def save_stacks(stack_pool):
        doc = {"version": ShowFile.VERSION, "fx_scale": ShowFile.FX_SCALE, "stacks": {}}
        for sid, stack in stack_pool.stacks.items():
            cues_out = {}
            for num in stack._sorted_cue_numbers():
                cue = stack.cues[num]
                entry = {
                    "name":       cue.name,
                    "fade_time":  cue.fade_time,
                    "delay_time": cue.delay_time,
                    "data":       cue.data,
                }
                if cue.fade_times:
                    entry["fade_times"]  = cue.fade_times
                if cue.delay_times:
                    entry["delay_times"] = cue.delay_times
                if getattr(cue, 'follow_time', 0.0) > 0:
                    entry["follow_time"] = cue.follow_time
                if getattr(cue, 'fx_outfade', None) is not None:
                    entry["fx_outfade"] = cue.fx_outfade
                if getattr(cue, 'note', ''):
                    entry["note"] = cue.note
                cues_out[str(num)] = entry
            entry_cs = {
                "name":            stack.name,
                "allow_exec_time": stack.allow_exec_time,
                "wrap":            stack.wrap,
                "cues":            cues_out,
            }
            if getattr(stack, 'bounce', False):
                entry_cs["bounce"] = True
            if getattr(stack, 'note', ''):
                entry_cs["note"] = stack.note
            if getattr(stack, 'chase_enabled', False):
                entry_cs["chase_enabled"] = True
            if getattr(stack, 'chase_bpm', 120.0) != 120.0:
                entry_cs["chase_bpm"] = stack.chase_bpm
            if getattr(stack, 'chase_speed_id', None) is not None:
                entry_cs["chase_speed_id"] = stack.chase_speed_id
            doc["stacks"][str(sid)] = entry_cs
        _write_file(ShowFile.STACKS, doc)
        total = sum(len(s.cues) for s in stack_pool.stacks.values())
        print(f"  Saved stacks → {len(stack_pool.stacks)} stack(s), {total} cue(s)")

    @staticmethod
    def save_groups(group_pool):
        doc = {"version": ShowFile.VERSION, "groups": {}}
        for gid, group in group_pool.groups.items():
            doc["groups"][str(gid)] = {
                "name":    group.name,
                "members": [{"type": m[0], "fixture_id": m[1]} for m in group.members],
            }
        _write_file(ShowFile.GROUPS, doc)
        print(f"  Saved groups    → {len(group_pool.groups)}")

    @staticmethod
    def save_fader_pages(fader_pool):
        doc = {"version": ShowFile.VERSION, "pages": {}}
        for n, page in fader_pool.pages.items():
            doc["pages"][str(n)] = {
                "name":       page.get("name", f"page {n}"),
                "stacks":  list(page.get("stacks", [])),
            }
        _write_file(ShowFile.FADER_PAGES, doc)
        print(f"  Saved fdr pages → {len(fader_pool.pages)}")

    @staticmethod
    def load_fader_pages(fader_pool):
        doc = _read_file(ShowFile.FADER_PAGES)
        if not doc:
            return False
        for n_str, pdata in doc.get("pages", {}).items():
            n = int(n_str)
            # "slots" was the old key (fader IDs); "stacks" is the current key
            stacks = pdata.get("stacks", pdata.get("slots", []))
            fader_pool.pages[n] = {
                "name":      pdata.get("name", f"page {n}"),
                "stacks": list(stacks),
            }
        print(f"  Loaded fdr pages — {len(fader_pool.pages)}")
        return True

    @staticmethod
    def save_faders(fader_pool):
        """Persist fader slot assignments (stack, level, priority, trigger_mode)."""
        doc = {"version": ShowFile.VERSION, "faders": {}}
        for eid, ex in fader_pool.faders.items():
            cs_id = ex.stack.stack_id if ex.stack else None
            doc["faders"][str(eid)] = {
                "stack_id":  cs_id,
                "level":        ex.level,
                "priority":     ex.priority,
                "trigger_mode": ex.trigger_mode,
                "output_mode":  ex.output_mode,
                "off_time":     getattr(ex, 'off_time', 0.0),
                "btn_a":        ex.btn_a,
                "btn_b":        ex.btn_b,
                "btn_c":        ex.btn_c,
                "rate_factor":  ex.rate_factor,
                "size_factor":  ex.size_factor,
                "label":        ex.label,
            }
        _write_file(ShowFile.FADERS, doc)
        print(f"  Saved faders  → {len(doc['faders'])} slot(s)")

    @staticmethod
    def load_faders(fader_pool, stack_pool):
        """Re-wire fader→stack assignments and settings from disk."""
        doc = _read_file(ShowFile.FADERS)
        if not doc:
            return False
        count = 0
        for eid_str, edata in doc.get("faders", {}).items():
            eid  = int(eid_str)
            ex   = fader_pool.get(eid)
            cs_id = edata.get("stack_id")
            if cs_id is not None:
                stk = stack_pool.get(int(cs_id))
                if stk:
                    fader_pool.assign(eid, stk)
                    count += 1
            ex.level        = float(edata.get("level",  1.0))
            ex.priority     = int(edata.get("priority", 0))
            ex.trigger_mode = edata.get("trigger_mode", "toggle")
            ex.output_mode  = edata.get("output_mode", "normal")
            ex.off_time     = float(edata.get("off_time", 0.0))
            _valid_fns      = {'GO', 'BACK', 'STOP', 'FLASH', 'RATE+', 'RATE-', 'SIZE+', 'SIZE-'}
            ex.btn_a        = edata.get("btn_a", "GO")  if edata.get("btn_a", "GO")   in _valid_fns else "GO"
            ex.btn_b        = edata.get("btn_b", "BACK") if edata.get("btn_b", "BACK") in _valid_fns else "BACK"
            ex.btn_c        = edata.get("btn_c", "STOP") if edata.get("btn_c", "STOP") in _valid_fns else "STOP"
            _rf             = float(edata.get("rate_factor", 1.0))
            ex.rate_factor  = max(0.1, min(8.0, _rf))
            _sf             = float(edata.get("size_factor", 1.0))
            ex.size_factor  = max(0.0, min(4.0, _sf))
            ex.label        = edata.get("label", "")
        print(f"  Loaded faders — {count} assignment(s)")
        return True

    @staticmethod
    def save_colors(color_pool):
        doc = {"version": ShowFile.VERSION, "colors": {}}
        for pid, preset in color_pool.presets.items():
            doc["colors"][str(pid)] = {
                "name":  preset.name,
                "red":   preset.red,
                "green": preset.green,
                "blue":  preset.blue,
            }
        _write_file(ShowFile.COLORS, doc)
        print(f"  Saved colors    → {len(color_pool.presets)}")

    @staticmethod
    def save_dims(dim_pool):
        doc = {"version": ShowFile.VERSION, "dims": {}}
        for pid, preset in dim_pool.presets.items():
            doc["dims"][str(pid)] = {"name": preset.name, "level": preset.level}
        _write_file(ShowFile.DIMS, doc)
        print(f"  Saved dims      → {len(dim_pool.presets)}")

    @staticmethod
    def save_midi(midi):
        doc = {"version": ShowFile.VERSION, "midi_cc": [], "midi_note": []}
        for (ch, cc), m in midi.cc_maps.items():
            doc["midi_cc"].append({
                "channel": ch, "cc": cc, "target": m.name,
                "soft_takeover": m.soft_takeover,
                "software_val":  m.software_val,
                "taken_over":    m.taken_over,
            })
        for (ch, note), m in midi.note_maps.items():
            doc["midi_note"].append({"channel": ch, "note": note, "target": m.name})
        _write_file(ShowFile.MIDI, doc)
        print(f"  Saved midi      → {len(midi.cc_maps)} CC, {len(midi.note_maps)} note")

    @staticmethod
    def save_osc_targets(osc_engine):
        targets = []
        for name, client in osc_engine._clients.items():
            targets.append({"name": name, "host": client._address, "port": client._port})
        _write_file(ShowFile.OSC_TARGETS, {"targets": targets})
        if targets:
            print(f"  Saved OSC targets → {len(targets)}")

    @staticmethod
    def load_osc_targets(osc_engine):
        doc = _read_file(ShowFile.OSC_TARGETS)
        if not doc:
            return
        for t in doc.get("targets", []):
            osc_engine.add_target(t["name"], t["host"], int(t["port"]))

    @staticmethod
    def save_fx(fx_params):
        doc = {"version": ShowFile.VERSION, "fx_scale": ShowFile.FX_SCALE, "fx_params": dict(fx_params)}
        _write_file(ShowFile.FX, doc)

    @staticmethod
    def save_state(output_state, fader_pool, active_fader,
                   prog_time=None, fader_dim=0.0):
        """Save live session state: master level, active fader, fdr→stack assignments."""
        execs = {}
        for eid, ex in fader_pool.faders.items():
            execs[str(eid)] = {
                "stack_id":  ex.stack.stack_id if ex.stack else None,
                "current":   ex.stack.current  if ex.stack else None,
                "priority":  ex.priority,
                "level":     ex.level,
                "time_on":   ex.time_override_on,
                "time_fade": ex.time_override_fade,
                "time_delay":ex.time_override_delay,
            }
        doc = {
            "version":        ShowFile.VERSION,
            "master_level":   output_state.master_level,
            "active_fader": active_fader[0] if active_fader else 1,
            "faders":      execs,
            "prog_time":      prog_time or {"on": False, "fade": 0.0, "delay": 0.0},
            "fader_dim":      float(fader_dim),
        }
        _write_file(ShowFile.STATE, doc)

    @staticmethod
    def load_state(output_state, fader_pool, stack_pool, active_fader,
                   prog_time=None, fader_dim=None):
        """Restore master level, active fader, and fdr→stack assignments."""
        doc = _read_file(ShowFile.STATE)
        if not doc:
            return False
        output_state.master_level = float(doc.get("master_level", 1.0))
        if active_fader is not None:
            active_fader[0] = int(doc.get("active_fader", 1))
        for eid_str, edata in doc.get("faders", {}).items():
            eid = int(eid_str)
            sid = edata.get("stack_id")
            cur = edata.get("current")
            if sid is None:
                continue
            stk = stack_pool.get(sid)
            if stk:
                fader_pool.assign(eid, stk)
                if cur is not None:
                    stk.current = float(cur)
            ex = fader_pool.get(eid)
            ex.priority            = int(edata.get("priority", 0))
            ex.level               = float(edata.get("level", 1.0))
            ex.time_override_on    = bool(edata.get("time_on",    False))
            ex.time_override_fade  = edata.get("time_fade",  None)
            ex.time_override_delay = edata.get("time_delay", None)
        if prog_time is not None and "prog_time" in doc:
            pt = doc["prog_time"]
            prog_time['on']    = bool(pt.get('on',    False))
            prog_time['fade']  = float(pt.get('fade',  0.0))
            prog_time['delay'] = float(pt.get('delay', 0.0))
        if fader_dim is not None and "fader_dim" in doc:
            fader_dim[0] = float(doc["fader_dim"])
        print(f"  Loaded state    — master={output_state.master_level:.0%} "
              f"active_exec={active_fader[0] if active_fader else '?'}")
        return True

    # ── Load ────────────────────────────────────────────────

    @staticmethod
    def load_stacks(stack_pool, cue_pool):
        doc = _read_file(ShowFile.STACKS)
        if not doc:
            return False
        needs_migration = doc.get("fx_scale", 1) < ShowFile.FX_SCALE
        for sid_str, sdata in doc.get("stacks", {}).items():
            sid   = int(sid_str)
            stack = Stack(sid, sdata["name"])
            stack.allow_exec_time = bool(sdata.get("allow_exec_time", True))
            stack.wrap            = bool(sdata.get("wrap", False))
            stack.bounce          = bool(sdata.get("bounce", False))
            stack.note            = sdata.get("note", "")
            stack.chase_enabled   = bool(sdata.get("chase_enabled", False))
            stack.chase_bpm       = float(sdata.get("chase_bpm", 120.0))
            stack.chase_speed_id  = sdata.get("chase_speed_id")
            for num_str, cdata in sdata["cues"].items():
                num      = float(num_str)
                cue      = Cue(num, cdata["name"],
                               cdata.get("fade_time", 2.0),
                               cdata.get("delay_time", 0.0),
                               cdata.get("fade_times"),
                               cdata.get("delay_times"),
                               cdata.get("follow_time", 0.0))
                cue.note      = cdata.get("note", "")
                _fxo = cdata.get("fx_outfade")
                cue.fx_outfade = float(_fxo) if _fxo is not None else None
                cue.data = copy.deepcopy(cdata["data"])
                if needs_migration:
                    ShowFile._migrate_fx_scale(cue.data)
                stack.cues[num] = cue
                if num == int(num):   # decimal cues have no panel button
                    cue_pool.store(int(num), cue)
            stack_pool.store(sid, stack)
        total = sum(len(s.cues) for s in stack_pool.stacks.values())
        if needs_migration:
            print(f"  Migrated FX scale (0-255/0-1 → 0-100) in {total} cue(s)")
        print(f"  Loaded stacks — {len(stack_pool.stacks)} stack(s), {total} cue(s)")
        return True

    @staticmethod
    def load_groups(group_pool):
        doc = _read_file(ShowFile.GROUPS)
        if not doc:
            return False
        for gid_str, gdata in doc.get("groups", {}).items():
            gid   = int(gid_str)
            group = Group(gid, gdata.get("name", f"group {gid}"))
            group.members = [(m["type"], m["fixture_id"])
                             for m in gdata.get("members", [])]
            group_pool.groups[gid] = group
        print(f"  Loaded groups   — {len(group_pool.groups)}")
        return True

    @staticmethod
    def load_colors(color_pool):
        doc = _read_file(ShowFile.COLORS)
        if not doc:
            return False
        for pid_str, pdata in doc.get("colors", {}).items():
            pid    = int(pid_str)
            preset = ColorPreset(pid, pdata.get("name", f"color {pid}"))
            if "data" in pdata:
                # Migrate old per-fixture format: sample first entry
                for fdata in pdata["data"].values():
                    preset.red   = fdata.get("red",   0)
                    preset.green = fdata.get("green", 0)
                    preset.blue  = fdata.get("blue",  0)
                    break
            else:
                preset.red   = pdata.get("red",   0)
                preset.green = pdata.get("green", 0)
                preset.blue  = pdata.get("blue",  0)
            color_pool.presets[pid] = preset
        print(f"  Loaded colors   — {len(color_pool.presets)}")
        return True

    @staticmethod
    def load_dims(dim_pool):
        doc = _read_file(ShowFile.DIMS)
        if not doc:
            return False
        for pid_str, pdata in doc.get("dims", {}).items():
            pid    = int(pid_str)
            preset = DimmerPreset(pid, pdata.get("name", f"Dimmer {pid}"))
            if "data" in pdata:
                # Migrate old per-fixture format: sample first entry
                for fdata in pdata["data"].values():
                    preset.level = fdata.get("dim", 0.0)
                    break
            else:
                preset.level = pdata.get("level", 0.0)
            dim_pool.presets[pid] = preset
        print(f"  Loaded dims     — {len(dim_pool.presets)}")
        return True

    @staticmethod
    def load_midi(doc, midi, target_registry):
        """doc is already-parsed JSON (passed in because MIDI restore must happen
        after target_registry is built, which is after GUI setup)."""
        if not doc:
            return
        midi.clear_maps()
        skipped = 0
        for entry in doc.get("midi_cc", []):
            name = entry["target"]
            if name not in target_registry:
                skipped += 1
                continue
            reg = target_registry[name]
            m = midi.map_cc(entry["channel"], entry["cc"], reg[0],
                            name=name,
                            soft_takeover=entry.get("soft_takeover", reg[1]))
            m.software_val = entry.get("software_val", 0.0)
            m.taken_over   = entry.get("taken_over",   not reg[1])
        for entry in doc.get("midi_note", []):
            name = entry["target"]
            if name not in target_registry:
                skipped += 1
                continue
            reg    = target_registry[name]
            off_cb = reg[3] if len(reg) > 3 else None
            midi.map_note(entry["channel"], entry["note"], reg[0], off_cb, name=name)
        s = f", {skipped} skipped" if skipped else ""
        print(f"  Loaded midi     — {len(midi.cc_maps)} CC, {len(midi.note_maps)} note{s}")

    @staticmethod
    def load_fx(fx_params):
        doc = _read_file(ShowFile.FX)
        if doc and doc.get("fx_params"):
            p = doc["fx_params"]
            if doc.get("fx_scale", 1) < ShowFile.FX_SCALE:
                sz = p.get('size', 100.0)
                if sz > 100.0:
                    p['size'] = round((sz / 255.0) * 100.0, 1)
                sp = p.get('spread', 0.0)
                if 0.0 < sp <= 10.0:
                    p['spread'] = min(100.0, round(sp * 100.0, 1))
            fx_params.update(p)

    @staticmethod
    def save_fx_pool(fx_pool):
        doc = {"version": ShowFile.VERSION, "fx_scale": ShowFile.FX_SCALE, "fx_presets": {}}
        for pid, preset in fx_pool.presets.items():
            layers_out = []
            for ld in preset.layers:
                layers_out.append({
                    'waveform':     ld.get('waveform', 'sine'),
                    'channel':      ld.get('channel', 'red'),
                    'bpm':          ld.get('bpm', 60.0),
                    'size':         ld.get('size', 100.0),
                    'spread':       ld.get('spread', 0.0),
                    'phase_offset': ld.get('phase_offset', 0.0),
                    'form_id':      ld.get('form_id'),
                    'rate_id':      ld.get('rate_id'),
                    'size_id':      ld.get('size_id'),
                    'spread_id':    ld.get('spread_id'),
                    'dim_id':       ld.get('dim_id'),
                    'color_id':     ld.get('color_id'),
                    'group_id':     ld.get('group_id'),
                    'speed_id':     ld.get('speed_id'),
                    'block_size':   ld.get('block_size', 1),
                    'order':        ld.get('order', 'linear'),
                    'direction':    ld.get('direction', 'forward'),
                    'target_scope': ld.get('target_scope'),
                })
            doc["fx_presets"][str(pid)] = {"name": preset.name, "layers": layers_out}
        _write_file(ShowFile.FX_POOL, doc)
        print(f"  Saved fx_pool   → {len(fx_pool.presets)}")

    @staticmethod
    def load_fx_pool(fx_pool):
        doc = _read_file(ShowFile.FX_POOL)
        if not doc:
            return False
        needs_migration = doc.get("fx_scale", 1) < ShowFile.FX_SCALE
        for pid_str, pdata in doc.get("fx_presets", {}).items():
            pid    = int(pid_str)
            preset = FXPreset(pid, pdata.get("name", f"FX {pid}"))
            for ld in pdata.get("layers", []):
                if needs_migration:
                    ShowFile._migrate_fx_ld(ld)
                preset.add_layer(
                    ld["waveform"], ld["channel"],
                    bpm          = ld.get("bpm", ld.get("rate_bpm", 60.0)),
                    size         = ld.get("size",         100.0),
                    spread       = ld.get("spread",         0.0),
                    phase_offset = ld.get("phase_offset",   0.0),
                    form_id      = ld.get("form_id"),
                    rate_id      = ld.get("rate_id"),
                    size_id      = ld.get("size_id"),
                    spread_id    = ld.get("spread_id"),
                    dim_id       = ld.get("dim_id"),
                    color_id     = ld.get("color_id"),
                    group_id     = ld.get("group_id"),
                    speed_id     = ld.get("speed_id"),
                    block_size   = ld.get("block_size",     1),
                    order        = ld.get("order",   "linear"),
                    direction    = ld.get("direction","forward"),
                    target_scope = ld.get("target_scope"),
                )
            fx_pool.store(pid, preset)
        print(f"  Loaded fx_pool  — {len(fx_pool.presets)}")
        return True

    @staticmethod
    def save_forms(form_pool):
        """Only persist custom (non-builtin) forms — builtins are always reconstructed."""
        custom = form_pool.custom_forms()
        doc = {"version": ShowFile.VERSION, "forms": {}}
        for fid, form in custom.items():
            doc["forms"][str(fid)] = {
                "name":        form.name,
                "form_type":   form.form_type,
                "breakpoints": form.breakpoints,
            }
        _write_file(ShowFile.FORMS, doc)
        print(f"  Saved forms     → {len(custom)} custom")

    @staticmethod
    def load_forms(form_pool):
        doc = _read_file(ShowFile.FORMS)
        if not doc:
            return False
        for fid_str, fdata in doc.get("forms", {}).items():
            fid  = int(fid_str)
            form = FormPreset(
                fid,
                fdata.get("name", f"form {fid}"),
                fdata.get("form_type", "breakpoints"),
                breakpoints=fdata.get("breakpoints", []),
            )
            form_pool.store(fid, form)
        n = len(doc.get("forms", {}))
        if n:
            print(f"  Loaded forms    — {n} custom")
        return True

    @staticmethod
    def save_rate_pool(rate_pool):
        doc = {"version": ShowFile.VERSION, "rate_presets": {}}
        for pid, p in rate_pool.presets.items():
            doc["rate_presets"][str(pid)] = {"name": p.name, "bpm": p.bpm}
        _write_file(ShowFile.RATES, doc)
        print(f"  Saved rate_pool  → {len(rate_pool.presets)}")

    @staticmethod
    def load_rate_pool(rate_pool):
        doc = _read_file(ShowFile.RATES)
        if not doc: return False
        for pid_str, pd in doc.get("rate_presets", {}).items():
            pid = int(pid_str)
            rate_pool.store(pid, RatePreset(pid, pd.get("name", f"rate {pid}"),
                                            pd.get("bpm", 60.0)))
        n = len(doc.get("rate_presets", {}))
        if n: print(f"  Loaded rate_pool — {n}")
        return True

    @staticmethod
    def save_size_pool(size_pool):
        doc = {"version": ShowFile.VERSION, "size_presets": {}}
        for pid, p in size_pool.presets.items():
            doc["size_presets"][str(pid)] = {"name": p.name, "size": p.size}
        _write_file(ShowFile.SIZES, doc)
        print(f"  Saved size_pool  → {len(size_pool.presets)}")

    @staticmethod
    def load_size_pool(size_pool):
        doc = _read_file(ShowFile.SIZES)
        if not doc: return False
        for pid_str, pd in doc.get("size_presets", {}).items():
            pid = int(pid_str)
            size_pool.store(pid, SizePreset(pid, pd.get("name", f"size {pid}"),
                                            pd.get("size", 200.0)))
        n = len(doc.get("size_presets", {}))
        if n: print(f"  Loaded size_pool — {n}")
        return True

    @staticmethod
    def save_spread_pool(spread_pool):
        doc = {"version": ShowFile.VERSION, "spread_presets": {}}
        for pid, p in spread_pool.presets.items():
            doc["spread_presets"][str(pid)] = {"name": p.name, "spread": p.spread}
        _write_file(ShowFile.SPREADS, doc)
        print(f"  Saved spread_pool → {len(spread_pool.presets)}")

    @staticmethod
    def load_spread_pool(spread_pool):
        doc = _read_file(ShowFile.SPREADS)
        if not doc: return False
        for pid_str, pd in doc.get("spread_presets", {}).items():
            pid = int(pid_str)
            spread_pool.store(pid, SpreadPreset(pid, pd.get("name", f"spread {pid}"),
                                                pd.get("spread", 1.0)))
        n = len(doc.get("spread_presets", {}))
        if n: print(f"  Loaded spread_pool — {n}")
        return True

    @staticmethod
    def save_speed_masters(pool):
        doc = {"version": ShowFile.VERSION, "speed_masters": {}}
        for sid, m in pool.masters.items():
            doc["speed_masters"][str(sid)] = {"name": m.name, "bpm": m.bpm}
        _write_file(ShowFile.SPEEDS, doc)
        print(f"  Saved speed masters → {len(pool.masters)}")

    @staticmethod
    def load_speed_masters(pool):
        doc = _read_file(ShowFile.SPEEDS)
        if not doc: return False
        for sid_str, md in doc.get("speed_masters", {}).items():
            sid = int(sid_str)
            pool.masters[sid] = SpeedMaster(sid, md.get("bpm", 120.0),
                                            md.get("name", f"spd{sid}"))
        n = len(doc.get("speed_masters", {}))
        if n: print(f"  Loaded speed masters — {n}")
        return True

    @staticmethod
    def save_network(bind_address, universes):
        _write_file(ShowFile.NETWORK, {
            "version":      ShowFile.VERSION,
            "bind_address": bind_address,
            "universes":    list(universes),
        })

    @staticmethod
    def load_network():
        """Return (bind_address, universes) from network.json, or (None, None) if missing."""
        doc = _read_file(ShowFile.NETWORK)
        if not doc:
            return None, None
        return doc.get("bind_address", ""), doc.get("universes", [1, 2])

    # ── Generic attribute pools ──────────────────────────────

    @staticmethod
    def save_attribute_pool(pool, path):
        """Persist any AttributePool to the given JSON path."""
        doc = {
            "version":   ShowFile.VERSION,
            "attribute": pool.attribute,
            "presets":   {str(pid): p.to_dict() for pid, p in pool.presets.items()},
        }
        _write_file(path, doc)
        print(f"  Saved {pool.attribute} pool → {len(pool.presets)} preset(s)")

    @staticmethod
    def load_attribute_pool(pool, path):
        """Restore an AttributePool from its JSON file."""
        doc = _read_file(path)
        if not doc:
            return False
        for pdata in doc.get("presets", {}).values():
            p = AttributePreset.from_dict(pdata)
            pool.presets[p.preset_id] = p
        print(f"  Loaded {pool.attribute} pool — {len(pool.presets)} preset(s)")
        return True

    # Convenience wrappers so call sites don't need to know the path

    @staticmethod
    def save_position_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.POSITION)

    @staticmethod
    def load_position_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.POSITION)

    @staticmethod
    def save_gobo_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.GOBO)

    @staticmethod
    def load_gobo_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.GOBO)

    @staticmethod
    def save_zoom_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.ZOOM)

    @staticmethod
    def load_zoom_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.ZOOM)

    @staticmethod
    def save_focus_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.FOCUS)

    @staticmethod
    def load_focus_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.FOCUS)

    @staticmethod
    def save_beam_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.BEAM)

    @staticmethod
    def load_beam_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.BEAM)

    @staticmethod
    def save_control_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.CONTROL)

    @staticmethod
    def load_control_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.CONTROL)

    @staticmethod
    def save_ai_prompts(prompts):
        """Save list of {name, prompt} dicts to ai_prompts.json."""
        _write_file(ShowFile.AI_PROMPTS, {"version": 1, "prompts": prompts})

    @staticmethod
    def load_ai_prompts(default_prompts=None):
        """Load AI prompt list from file; return defaults if file missing."""
        doc = _read_file(ShowFile.AI_PROMPTS)
        if doc and "prompts" in doc:
            return list(doc["prompts"])
        return list(default_prompts) if default_prompts else []

    # ── Legacy migration ─────────────────────────────────────

    @staticmethod
    def save_patch(patch):
        fixtures = []
        for master in patch.all_fixtures():
            # Collect primary output from first sub-fixture
            first_sub = next(iter(master.sub_fixtures.values()), None)
            if not first_sub or not first_sub.outputs:
                continue
            primary = first_sub.outputs[0]
            extra = first_sub.outputs[1:] if len(first_sub.outputs) > 1 else []
            fixtures.append({
                "fixture_id":    master.fixture_id,
                "name":          master.name,
                "profile":       master.profile.name,
                "universe":      primary["universe"],
                "start_address": primary["address"],
                "extra_outputs": [{"universe": o["universe"], "address": o["address"] - (primary["address"] - 1)}
                                  for o in extra],
            })
        doc = {"version": ShowFile.VERSION, "fixtures": fixtures}
        _write_file(ShowFile.PATCH, doc)
        print(f"  Saved patch     → {len(fixtures)} fixture(s)")

    @staticmethod
    def load_patch(patch):
        doc = _read_file(ShowFile.PATCH)
        if not doc:
            return False
        for f in doc.get("fixtures", []):
            patch.patch_fixture(
                fixture_id    = int(f["fixture_id"]),
                name          = f.get("name", f"Fixture {f['fixture_id']}"),
                profile_name  = f.get("profile", "Generic_RGB"),
                universe      = int(f.get("universe", 1)),
                start_address = int(f.get("start_address", 1)),
                extra_outputs = f.get("extra_outputs") or None,
            )
        print(f"  Loaded patch    — {len(patch.fixtures)} fixture(s)")
        return True

    @staticmethod
    def save_macros(macro_pool):
        data = {
            str(slot): {"name": m["name"], "commands": list(m["commands"])}
            for slot, m in macro_pool.items()
        }
        _write_file(ShowFile.MACROS, {"version": ShowFile.VERSION, "macros": data})
        print(f"  Saved macros     → {len(macro_pool)} macro(s)")

    @staticmethod
    def load_macros(macro_pool):
        doc = _read_file(ShowFile.MACROS)
        if not doc:
            return False
        for slot_str, m in doc.get("macros", {}).items():
            try:
                slot = int(slot_str)
            except ValueError:
                continue
            macro_pool[slot] = {
                "name":     m.get("name", f"macro {slot}"),
                "commands": list(m.get("commands", [])),
            }
        print(f"  Loaded macros    — {len(macro_pool)} macro(s)")
        return True

    @staticmethod
    def save_defaults(defaults: dict):
        """Save fixture/programmer defaults dict to disk."""
        _write_file(ShowFile.DEFAULTS, defaults)

    @staticmethod
    def load_defaults() -> dict:
        """Load fixture/programmer defaults. Returns {} if file missing."""
        doc = _read_file(ShowFile.DEFAULTS)
        return doc if isinstance(doc, dict) else {}

    @staticmethod
    def migrate_legacy(stack_pool, cue_pool, group_pool, color_pool, dim_pool, fx_params):
        """Read old studio_show.json and write to new per-file format, then rename it."""
        if not os.path.exists(_LEGACY_FILE):
            return False
        try:
            with open(_LEGACY_FILE) as f:
                old = json.load(f)
        except Exception:
            return False

        print("  Migrating studio_show.json → studio_data/ ...")

        # Stacks
        if old.get("stacks"):
            for sid_str, sdata in old["stacks"].items():
                sid   = int(sid_str)
                stack = Stack(sid, sdata["name"])
                for num_str, cdata in sdata["cues"].items():
                    num      = float(num_str)
                    cue      = Cue(num, cdata["name"],
                                   cdata.get("fade_time", 2.0),
                                   cdata.get("delay_time", 0.0),
                                   cdata.get("fade_times"),
                                   cdata.get("delay_times"))
                    cue.data = copy.deepcopy(cdata["data"])
                    stack.cues[num] = cue
                    if num == int(num):
                        cue_pool.store(int(num), cue)
                stack_pool.store(sid, stack)
            ShowFile.save_stacks(stack_pool)

        # Groups
        for gid_str, gdata in old.get("groups", {}).items():
            gid   = int(gid_str)
            group = Group(gid, gdata.get("name", f"group {gid}"))
            group.members = [(m["type"], m["fixture_id"])
                             for m in gdata.get("members", [])]
            group_pool.groups[gid] = group
        if group_pool.groups:
            ShowFile.save_groups(group_pool)

        # Colors — old format stored per-fixture data dict; migrate to global RGB
        for pid_str, pdata in old.get("color_presets", {}).items():
            pid    = int(pid_str)
            preset = ColorPreset(pid, pdata.get("name", f"color {pid}"))
            old_data = pdata.get("data", {})
            # Take first fixture's RGB as the global value
            for fvals in old_data.values():
                preset.red   = fvals.get("red",   0)
                preset.green = fvals.get("green", 0)
                preset.blue  = fvals.get("blue",  0)
                break
            color_pool.presets[pid] = preset
        if color_pool.presets:
            ShowFile.save_colors(color_pool)

        # Dims — old format stored per-fixture data dict; migrate to global level
        for pid_str, pdata in old.get("dim_presets", {}).items():
            pid    = int(pid_str)
            preset = DimmerPreset(pid, pdata.get("name", f"Dimmer {pid}"))
            old_data = pdata.get("data", {})
            for fvals in old_data.values():
                raw = fvals.get("dim", 0)
                preset.level = max(0.0, min(1.0, float(raw) / 255.0 if float(raw) > 1.0 else float(raw)))
                break
            dim_pool.presets[pid] = preset
        if dim_pool.presets:
            ShowFile.save_dims(dim_pool)

        # FX
        if old.get("fx_params"):
            fx_params.update(old["fx_params"])
            ShowFile.save_fx(fx_params)

        # Rename old file so we don't migrate twice
        _shutil.move(_LEGACY_FILE, _LEGACY_FILE + '.migrated')
        if os.path.exists(_LEGACY_FILE + '.bak'):
            _shutil.move(_LEGACY_FILE + '.bak', _LEGACY_FILE + '.bak.migrated')
        print("  Migration complete — studio_show.json renamed to .migrated")
        return True

__all__ = ["ShowFile", "_write_file", "_read_file"]
