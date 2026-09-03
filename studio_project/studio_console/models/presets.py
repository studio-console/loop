"""Studio Console preset/pool/playback data models — extracted verbatim from
studio_project.py (Blocks 4 & 5: Presets, Pools, Groups, plus Cue/Stack/Fader/
Fade). Pure move, zero behavior change, with two corrections applied after
the initial extraction (both found by the smoke test, not caught by the
original boundary check):

1. Several Fader methods use isinstance(f, MasterFixture) — a direct,
   non-circular import from the sibling models.fixtures module (safe:
   fixtures.py has no dependency back on this module).
2. Fader._start_cue_fx() calls _expand_color_fx/_expand_group_fx/
   _bucket_fx_defs, module-level helpers defined near FXEngine in
   studio_project.py that haven't been extracted yet (a later phase:
   engine/fx.py). These need a deferred (function-local) `from __main__
   import (...)` inside that method specifically — see the comment there
   for why a module-level import doesn't work for this one.
"""

import os
import json
import copy
import time

from studio_console.models.fixtures import MasterFixture
from studio_console.models.naming import LowercaseName
from studio_console.engine.fx import _fx_grouping_compat

# ============================================================
# Blocks 4 & 5: Presets, Pools, Groups
# Colorpreset / ColorPool — referenced RGB presets
# Dimmerpreset / DimmerPool — referenced dimmer presets
# Attributepreset / AttributePool — generic attribute presets
#   (position, gobo, zoom, focus, beam, control)
# group / GroupPool — fixture selection groups
# ============================================================

class ColorPreset:
    """
    Selective colour preset — stores a single RGB value.
    apply() pushes it to every sub-fixture in the current programmer selection.
    record() samples from the first selected sub-fixture that carries colour data.

    # Future: add a `scope` field ("selective" | "universe" | "global") to expand
    # targeting without changing the stored RGB format.
    """
    name = LowercaseName()

    def __init__(self, preset_id, name=""):
        self.preset_id = preset_id
        self.name      = name if name else f"color {preset_id}"
        self.red   = 0
        self.green = 0
        self.blue  = 0

    def record(self, programmer):
        for f in programmer._get_sub_selection():
            vals = programmer.data.get(str(f.fixture_id), {})
            if any(ch in vals for ch in ('red', 'green', 'blue')):
                self.red   = vals.get('red',   0)
                self.green = vals.get('green', 0)
                self.blue  = vals.get('blue',  0)
                break
        print(f"recorded: {self}")

    def apply(self, programmer):
        applied = 0
        masters_written = set()
        for f in programmer._get_sub_selection():
            programmer._ensure_data(f)
            fid = str(f.fixture_id)
            programmer.data[fid]['red']   = self.red
            programmer.data[fid]['green'] = self.green
            programmer.data[fid]['blue']  = self.blue
            f.set_rgb(self.red, self.green, self.blue)
            applied += 1
            masters_written.add(str(f.master_id))
        for mfid in masters_written:
            programmer.data.setdefault(mfid, {})['color_ref'] = self.preset_id
        print(f"Applied {self} to {applied} sub-fixture(s).")

    def __repr__(self):
        return (f"[color preset {self.preset_id}] \"{self.name}\" "
                f"RGB({self.red},{self.green},{self.blue})")


class ColorPool:
    def __init__(self):
        self.presets = {}   # { preset_id (int): Colorpreset }

    def get(self, pid):
        return self.presets.get(int(pid))

    def record(self, preset_id, programmer, name=""):
        preset = ColorPreset(preset_id, name or f"color {preset_id}")
        preset.record(programmer)
        self.presets[preset.preset_id] = preset
        return preset

    def apply(self, preset_id, programmer):
        p = self.get(preset_id)
        if p:
            p.apply(programmer)
        else:
            print(f"color preset {preset_id} not found.")

    def delete(self, preset_id):
        self.presets.pop(int(preset_id), None)

    def print_pool(self):
        print("\n===== COLOR PRESETS =====")
        for p in self.presets.values():
            print(f"  {p}")


class DimmerPreset:
    """
    Selective dimmer preset — stores a single level (0.0–1.0).
    apply() pushes it to every master fixture in the current programmer selection.
    record() samples from the first selected master that carries dim data.

    # Future: add a `scope` field ("selective" | "universe" | "global") to expand
    # targeting without changing the stored level format.
    """
    name = LowercaseName()

    def __init__(self, preset_id, name=""):
        self.preset_id = preset_id
        self.name      = name if name else f"Dimmer {preset_id}"
        self.level     = 0.0   # 0.0 – 1.0

    def record(self, programmer):
        for f in programmer.selection:
            if isinstance(f, MasterFixture):
                vals = programmer.data.get(str(f.fixture_id), {})
                if 'dim' in vals:
                    self.level = vals['dim']
                    break
        print(f"recorded: {self}")

    def apply(self, programmer):
        applied = 0
        for f in programmer.selection:
            if isinstance(f, MasterFixture):
                programmer._ensure_data(f)
                fid = str(f.fixture_id)
                programmer.data[fid]['dim']     = self.level
                programmer.data[fid]['dim_ref'] = self.preset_id
                f.set_dimmer(self.level)
                applied += 1
        print(f"Applied {self} to {applied} fixture(s).")

    def __repr__(self):
        return f"[Dimmer preset {self.preset_id}] \"{self.name}\" ({self.level:.0%})"


class DimmerPool:
    def __init__(self):
        self.presets = {}   # { preset_id (int): Dimmerpreset }

    def get(self, pid):
        return self.presets.get(int(pid))

    def record(self, preset_id, programmer, name=""):
        preset = DimmerPreset(preset_id, name or f"Dimmer {preset_id}")
        preset.record(programmer)
        self.presets[preset.preset_id] = preset
        return preset

    def apply(self, preset_id, programmer):
        p = self.get(preset_id)
        if p:
            p.apply(programmer)
        else:
            print(f"Dimmer preset {preset_id} not found.")

    def delete(self, preset_id):
        self.presets.pop(int(preset_id), None)

    def print_pool(self):
        print("\n===== DIM PRESETS =====")
        for p in self.presets.values():
            print(f"  {p}")


# ── Generic attribute pools (position, gobo, zoom, focus, beam, control) ──
#
# To add a new pool type:
#   1. Instantiate AttributePool("position") etc. in the main init block.
#   2. Add ShowFile path + save_attribute_pool / load_attribute_pool call.
#   3. Wire RECORD <ATTR> <n> and <ATTR> <n> commands in run_command().
#   4. <attr>_ref expansion is already handled generically in _resolve_cue_refs().

class AttributePreset:
    """
    Generic preset for any fixture attribute family.

    attribute  — logical name (e.g. "position", "gobo", "zoom")
    data       — {fixture_id_str: {channel_name: value, ...}}
    """
    name = LowercaseName()

    def __init__(self, preset_id, name, attribute):
        self.preset_id = int(preset_id)
        self.name      = name or f"{attribute.lower()} {preset_id}"
        self.attribute = attribute
        self.data      = {}

    def record(self, programmer_data, relevant_channels):
        self.data = {}
        for fid, vals in programmer_data.items():
            snap = {k: vals[k] for k in relevant_channels if k in vals}
            if snap:
                self.data[fid] = snap

    def apply(self, programmer):
        ref_key = f"{self.attribute}_ref"
        for fid, vals in self.data.items():
            programmer.data.setdefault(fid, {}).update(vals)
            if '.' not in str(fid):
                programmer.data[fid][ref_key] = self.preset_id

    def to_dict(self):
        return {
            "preset_id": self.preset_id,
            "name":      self.name,
            "attribute": self.attribute,
            "data":      self.data,
        }

    @classmethod
    def from_dict(cls, d):
        p = cls(d["preset_id"], d.get("name", ""), d.get("attribute", "unknown"))
        p.data = d.get("data", {})
        return p

    def __repr__(self):
        return (f"[{self.attribute.upper()} preset {self.preset_id}] "
                f"{self.name}  ({len(self.data)} fixtures)")


class AttributePool:
    """Registry of AttributePresets for one attribute family."""
    def __init__(self, attribute, relevant_channels=None):
        self.attribute         = attribute
        self.relevant_channels = list(relevant_channels or [attribute])
        self.presets           = {}   # { preset_id: Attributepreset }

    def get(self, preset_id):
        return self.presets.get(int(preset_id))

    def record(self, preset_id, programmer, name=""):
        preset = AttributePreset(preset_id, name, self.attribute)
        preset.record(programmer.data, self.relevant_channels)
        self.presets[preset.preset_id] = preset
        return preset

    def apply(self, preset_id, programmer):
        p = self.get(preset_id)
        if p:
            p.apply(programmer)
        else:
            print(f"{self.attribute.title()} preset {preset_id} not found.")

    def delete(self, preset_id):
        self.presets.pop(int(preset_id), None)

    def print_pool(self):
        label = self.attribute.upper()
        print(f"\n===== {label} PRESETS =====")
        for p in self.presets.values():
            print(f"  {p}")


class Group:
    """
    A named selection of fixtures and/or specific sub-fixtures — a group
    can mix whole fixtures with individual pixels of other fixtures (e.g.
    "all the .1s across a rig" alongside a couple of complete fixtures).
    """
    name = LowercaseName()

    def __init__(self, group_id, name=""):
        self.group_id = group_id
        self.name     = name or f"group {group_id}"
        # [ ("master", fixture_id_int) | ("sub", "master.sub"_str), ... ]
        # A "master" entry auto-expands to every one of that fixture's
        # subs on recall (via programmer.select()'s own MasterFixture
        # handling) — recording one whenever the WHOLE fixture was
        # selected, rather than every individual sub, keeps the group
        # resilient to the fixture's pixel count changing later and
        # keeps a plain "select fixture, record group" the same one-line
        # entry it always was.
        self.members  = []

    def record(self, programmer):
        masters_selected = []
        seen_masters = set()
        subs_by_master = {}
        for f in programmer.selection:
            if isinstance(f, MasterFixture):
                if f.fixture_id not in seen_masters:
                    seen_masters.add(f.fixture_id)
                    masters_selected.append(f.fixture_id)
            else:
                subs_by_master.setdefault(f.master_id, []).append(f)
        self.members = [("master", mid) for mid in masters_selected]
        for mid, subs in subs_by_master.items():
            if mid in seen_masters:
                continue  # whole fixture already covers these subs
            for sub in subs:
                self.members.append(("sub", sub.fixture_id))
        print(f"recorded: {self}")

    def recall(self, patch):
        """Return list of MasterFixture/SubFixture objects for this group."""
        fixtures = []
        for _type, fid in self.members:
            f = None
            if _type == 'sub':
                try:
                    m_str, s_str = str(fid).split('.', 1)
                    f = patch.get_sub(int(m_str), int(s_str))
                except (ValueError, IndexError):
                    f = None
            else:
                try:
                    f = patch.get(int(fid))
                except (ValueError, TypeError):
                    f = None
            if f:
                fixtures.append(f)
        return fixtures

    def __repr__(self):
        return f"[group {self.group_id}] \"{self.name}\" ({len(self.members)} member(s))"


class GroupPool:
    def __init__(self):
        self.groups = {}   # { group_id (int): group }

    def get(self, gid):
        return self.groups.get(int(gid))

    def record(self, group_id, programmer, name=""):
        g = Group(group_id, name or f"group {group_id}")
        g.record(programmer)
        self.groups[g.group_id] = g
        return g

    def recall(self, group_id, programmer):
        """Select the group's fixtures into the programmer."""
        g = self.get(group_id)
        if g:
            fixtures = g.recall(programmer.patch)
            programmer.select(fixtures)
        return g

    def delete(self, group_id):
        self.groups.pop(int(group_id), None)

    def print_pool(self):
        print("\n===== GROUPS =====")
        for g in self.groups.values():
            print(f"  {g}")


# ============================================================
# STUDIO CONSOLE - Core Object Model
# Block 6: cue and Stack
# Delta-based tracking, decimal cue numbers,
# fade/delay times, GO/BACK/GOTO playback.
# ============================================================

class Cue:
    """
    A single cue — a snapshot of active programmer data
    at the moment of recording.

    Stores delta only — what changed, not the full state
    of every fixture. Unmentioned fixtures track from
    previous cues.

    cue_number  — supports decimals (1.0, 1.5, 2.0 etc)
    fade_time   — global default crossfade seconds
    delay_time  — global default pre-fade delay seconds
    fade_times  — per-attribute-group overrides: {'colour': float, 'dim': float, ...}
    delay_times — per-attribute-group delay overrides
    """
    name = LowercaseName()

    def __init__(self, cue_number, name="", fade_time=0.0, delay_time=0.0,
                 fade_times=None, delay_times=None, follow_time=0.0):
        self.cue_number  = float(cue_number)
        self.name        = name if name else f"cue {cue_number}"
        self.fade_time   = float(fade_time)
        self.delay_time  = float(delay_time)
        self.fade_times  = dict(fade_times)  if fade_times  else {}
        self.delay_times = dict(delay_times) if delay_times else {}
        self.follow_time = float(follow_time)  # >0 = auto-GO after N seconds
        self.fx_outfade  = None               # override FX outfade time (None = auto)
        self.note        = ""                 # production annotation (saved, optional)

        # Delta snapshot: { fixture_id_string: { channel: value } }
        # Only contains what was active in the programmer at record time
        self.data = {}

    def record(self, programmer):
        """
        snapshot active programmer data into this cue.
        When a master entry carries color_ref, sub-fixture RGB entries are
        omitted — the reference resolves them live at playback time.
        dim_ref is stored alongside the inline dim value as a fallback.
        """
        self.data = {}
        color_ref_masters = {
            fid for fid, vals in programmer.data.items()
            if '.' not in fid and vals.get('color_ref')
        }
        for fid, vals in programmer.data.items():
            if not vals:
                continue
            if '.' in fid and fid.split('.')[0] in color_ref_masters:
                continue  # color_ref on master covers these sub-fixtures
            self.data[fid] = copy.deepcopy(vals)

        count = len(self.data)
        print(f"recorded: {self} ({count} fixture/pixel entries)")

    def update(self, programmer):
        """
        Merge programmer data INTO this cue (channel-level LTP).
        Fixtures not in the programmer are left exactly as-is.
        Channels present in the programmer overwrite the cue's value for
        that channel; channels already in the cue but not in the programmer
        are preserved.
        """
        color_ref_masters = {
            fid for fid, vals in programmer.data.items()
            if '.' not in fid and vals.get('color_ref')
        }
        for fid, vals in programmer.data.items():
            if not vals:
                continue
            if '.' in fid and fid.split('.')[0] in color_ref_masters:
                continue
            if fid not in self.data:
                self.data[fid] = {}
            self.data[fid].update(copy.deepcopy(vals))

        count = len(self.data)
        print(f"updated: {self} ({count} fixture/pixel entries total)")

    def __repr__(self):
        timing = f"Fade:{self.fade_time}s"
        if self.delay_time > 0:
            timing += f" Delay:{self.delay_time}s"
        if self.fade_times:
            for grp, ft in self.fade_times.items():
                dt = self.delay_times.get(grp, 0.0)
                timing += f" {grp.capitalize()}Fade:{ft}s"
                if dt > 0:
                    timing += f"+{dt}s"
        if getattr(self, 'fx_outfade', None) is not None:
            timing += f" FXOut:{self.fx_outfade}s"
        return f"[cue {self.cue_number}] \"{self.name}\" | {timing}"


class Stack:
    """
    An ordered list of cues — like a sequence/fader in MA3.
    Supports decimal cue numbers for inserting between existing cues.
    Tracks current playback position.

    Playback commands:
        GO      — advance to next cue
        BACK    — step to previous cue
        GOTO n  — jump to specific cue number
    """
    name = LowercaseName()

    def __init__(self, stack_id, name=""):
        self.stack_id        = stack_id
        self.name            = name if name else f"stack {stack_id}"
        self.cues            = {}        # { cue_number (float): cue }
        self.current         = None      # Current cue number (float) or None
        self.allow_exec_time = True      # False = ignore fader time override for this stack
        self.wrap            = False     # True = fire cue 1 clean on wrap-around (no LTP bleed)
        self.bounce          = False     # True = reverse direction at ends (ping-pong)
        self._bounce_dir     = 1        # 1 = forward, -1 = backward (runtime, not saved)
        self.note            = ""        # Production annotation (saved, optional)
        # True = a cue's effective playback state is the LTP-merge of
        # every earlier cue's own delta up through it (real-console
        # "tracking" — see Cue's own docstring: "Unmentioned fixtures
        # track from previous cues"), not just that one cue's raw delta.
        # False = a cue fires with ONLY what's explicitly recorded into
        # it — anything it doesn't mention stays at the fixture's default
        # (dark), matching the pre-tracking-fix behavior for shows that
        # were deliberately recorded assuming no tracking.
        self.tracking        = True
        # Chase mode — auto-advance through cues at a fixed BPM
        self.chase_enabled  = False
        self.chase_bpm      = 120.0
        self.chase_speed_id = None   # SpeedMaster slot (overrides chase_bpm when set)

    def _sorted_cue_numbers(self):
        """Returns cue numbers in ascending order."""
        return sorted(self.cues.keys())

    def record_cue(self, cue_number, programmer,
                   name="", fade_time=0.0, delay_time=0.0):
        """
        Record a new cue from the programmer.
        If cue_number already exists it gets overwritten.
        """
        if not programmer.data:
            print("programmer is empty — nothing to record.")
            return None

        cue = Cue(cue_number, name, fade_time, delay_time)
        cue.record(programmer)
        self.cues[float(cue_number)] = cue
        return cue

    def get_cue(self, cue_number):
        return self.cues.get(float(cue_number), None)

    def delete_cue(self, cue_number):
        num = float(cue_number)
        if num in self.cues:
            del self.cues[num]
            if self.current == num:
                self.current = None
            print(f"deleted cue {cue_number} from {self.name}")
        else:
            print(f"cue {cue_number} not found.")

    # ----------------------------------------------------------
    # Playback
    # ----------------------------------------------------------

    def go(self, patch):
        """
        Advance to the next cue and apply it.
        Loops back to first cue after the last.
        """
        numbers = self._sorted_cue_numbers()
        if not numbers:
            print("stack is empty.")
            return

        if self.current is None:
            next_num = numbers[0]
        else:
            try:
                idx      = numbers.index(self.current)
                next_num = numbers[(idx + 1) % len(numbers)]
            except ValueError:
                next_num = numbers[0]

        self._fire_cue(next_num, patch)

    def back(self, patch):
        """Step to the previous cue."""
        numbers = self._sorted_cue_numbers()
        if not numbers:
            print("stack is empty.")
            return

        if self.current is None:
            prev_num = numbers[-1]
        else:
            try:
                idx      = numbers.index(self.current)
                prev_num = numbers[(idx - 1) % len(numbers)]
            except ValueError:
                prev_num = numbers[-1]

        self._fire_cue(prev_num, patch)

    def goto(self, cue_number, patch):
        """Jump directly to a specific cue number."""
        num = float(cue_number)
        if num not in self.cues:
            print(f"cue {cue_number} not found in {self.name}.")
            return
        self._fire_cue(num, patch)

    def _fire_cue(self, cue_number, patch):
        """
        Apply a cue's data directly to fixtures.
        This is the playback output layer — separate from
        the programmer. cue data goes straight to fixtures.

        Note: In the full engine this will merge with the
        output merger (HTP/LTP). For now it writes directly
        so we can verify cue data is correct before the
        network engine is built.
        """
        cue = self.cues[cue_number]
        self.current = cue_number

        applied = 0
        for fid, vals in cue.data.items():
            if '.' in fid:
                parts   = fid.split('.')
                fixture = patch.get_sub(int(parts[0]), int(parts[1]))
                if fixture:
                    if 'red'   in vals: fixture.red   = vals['red']
                    if 'green' in vals: fixture.green = vals['green']
                    if 'blue'  in vals: fixture.blue  = vals['blue']
                    applied += 1
            else:
                fixture = patch.get(int(fid))
                if fixture:
                    if 'dim' in vals:
                        fixture.virtual_dimmer = vals['dim']
                    applied += 1

        print(f"\nFired: {cue}")
        print(f"  Applied to {applied} fixture/pixel entries")
        print(f"  Timing: delay {cue.delay_time}s → fade {cue.fade_time}s")
        print(f"  (Fade engine connects in Block 7)\n")

    # ----------------------------------------------------------
    # Display
    # ----------------------------------------------------------

    def print_stack(self):
        print(f"\n===== {self.name} =====")
        if not self.cues:
            print("  (empty)")
        for num in self._sorted_cue_numbers():
            cue    = self.cues[num]
            marker = " ◀ CURRENT" if num == self.current else ""
            print(f"  {cue}{marker}")
        print("=" * (len(self.name) + 12) + "\n")


class CuePool:
    """Numbered library of standalone cue objects (1-based slots)."""
    def __init__(self):
        self.cues = {}      # { int slot: cue }

    def get(self, n):
        return self.cues.get(int(n))

    def store(self, n, cue):
        self.cues[int(n)] = cue

    def delete(self, n):
        self.cues.pop(int(n), None)

    def record(self, n, programmer, name="", fade_time=0.0):
        cue = Cue(n, name or f"cue {n}", fade_time)
        cue.record(programmer)
        self.cues[int(n)] = cue
        return cue


class StackPool:
    """Pool of stack objects (faders), numbered 1-based."""
    def __init__(self):
        self.stacks = {}    # { int slot: stack }

    def get(self, n):
        return self.stacks.get(int(n))

    def store(self, n, stack):
        self.stacks[int(n)] = stack

    def create(self, n, name=""):
        existing = self.stacks.get(int(n))
        if existing:
            # Rename in-place — preserves cues and fader references
            existing.name = name or f"stack {n}"
            return existing
        stk = Stack(int(n), name or f"stack {n}")
        self.stacks[int(n)] = stk
        return stk

    def delete(self, n):
        self.stacks.pop(int(n), None)

    def all_slots(self):
        return sorted(self.stacks.keys())


# ============================================================
# Fader + FaderPool
# Each fader is a live playback slot that holds a Stack
# reference and owns its own output layer dict.
# OutputState reads from all active fader layers and merges
# them LTP (most recently fired = highest priority).
# ============================================================

class Fader:
    """One physical playback slot — a stack running in real time."""

    # Priority constants
    PRIORITY_LOW    = -1
    PRIORITY_NORMAL =  0
    PRIORITY_HIGH   =  1
    PRIORITY_LABELS = {-1: 'lo', 0: 'nrm', 1: 'hi'}

    def __init__(self, fdr_id):
        self.fdr_id      = fdr_id
        self.stack     = None
        self.is_active    = False
        self.level        = 1.0      # master fader, 0.0–1.0
        self.priority     = 0        # -1 low / 0 normal / 1 high
        self.trigger_mode = 'toggle' # 'toggle' (GO/BACK advance) or 'flash' (live only while held)
        self.layer     = {}       # { fid_str: { channel: value } }
        self._fx_ids     = []     # FX engine layer IDs currently active for this fader
        self._fx_counter = 0      # ever-increasing; avoids ID reuse during outfade overlap
        self.fx_engine  = None    # injected from FaderPool
        self.form_pool  = None    # injected from FaderPool
        self.color_pool = None    # injected from FaderPool
        self.dim_pool   = None    # injected from FaderPool
        self.group_pool = None    # injected from FaderPool
        # Time overrides — None means "use cue's own time"
        self.time_override_fade  = None   # float seconds or None
        self.time_override_delay = None   # float seconds or None
        self.time_override_on    = False  # master enable for this fader's override
        self._follow_at          = None   # monotonic time to auto-GO via FOLLOW
        self._chase_next_at      = None   # monotonic time for next chase GO
        # Three assignable action buttons per fader slot
        self.btn_a = 'GO'    # GO / BACK / STOP / FLASH / RATE+ / RATE-
        self.btn_b = 'BACK'
        self.btn_c = 'STOP'
        # Playback rate multiplier: 1.0 = normal, 2.0 = twice as fast (divides fade times)
        self.rate_factor = 1.0
        # FX amplitude multiplier: 1.0 = normal, 2.0 = double, 0.5 = half (applied to all owned layers)
        self.size_factor = 1.0
        # Optional human-readable label for this fader slot (independent of the stack name)
        self.label = ""
        self.fx_pool = None    # injected from FaderPool
        self.output_mode  = 'normal'   # 'normal' | 'moment' | 'vfade'
        self.vfade_from   = None       # snapshot when vfade cue loaded
        self.vfade_to     = None       # resolved target cue data
        self.off_time     = 0.0        # release fade time (seconds) for moment button mode

    def assign(self, stack):
        self.stack = stack

    def set_value(self, fid, channel, value):
        """Called by Fade.tick() on every interpolation step."""
        if fid not in self.layer:
            self.layer[fid] = {}
        self.layer[fid][channel] = value

    def snapshot_layer(self):
        """Deep copy used as the 'from' state when starting a new fade."""
        return {fid: dict(vals) for fid, vals in self.layer.items()}

    # ── FX management ────────────────────────────────────────

    def _clear_fx(self):
        """Remove all FX layers owned by this fader from the shared engine."""
        if self.fx_engine:
            for fxid in self._fx_ids:
                self.fx_engine.remove(fxid)
        self._fx_ids.clear()

    def _start_cue_fx(self, cue, patch, default_infade=0.0, default_outfade=0.0,
                      cue_data=None):
        """
        Read FX defs from master entries and start layers.
        Old layers are outfaded (not instant-killed) so FX crossfades naturally.
        Each layer ID is fdr_id * 10000 + ever-increasing counter so IDs never
        repeat even while outfading layers are still in the engine.
        default_infade  — fallback infade when the FX def doesn't set one;
                          callers pass the effective cue fade time.
        default_outfade — fallback outfade applied to outgoing layers that
                          had no explicit outfade; callers pass eff_fade so
                          old FX ramps out in sync with the DMX crossfade.
        cue_data        — per-fixture data to scan for 'fx' defs; defaults
                          to cue.data (that one cue's own raw delta) when
                          not given. Callers that want FX to track
                          forward the same way DMX values do (see
                          engine/playback.py's _tracked_cue_data) pass
                          the fully-merged dict here instead, so an FX
                          started in an earlier cue keeps running through
                          a later cue that doesn't touch that fixture.
        """
        if not self.fx_engine:
            self._fx_ids = []
            return
        cue_data = cue_data if cue_data is not None else cue.data

        # Outfade old layers — they self-remove when amplitude reaches 0
        now = time.monotonic()
        for fxid in self._fx_ids:
            self.fx_engine.remove(fxid, now, default_outfade=default_outfade)
        self._fx_ids = []

        fx_defs_by_fid = {}
        for fid_str, vals in cue_data.items():
            if '.' in fid_str:
                continue
            fx_defs = vals.get('fx', [])
            if fx_defs:
                _fp = getattr(self, 'fx_pool', None)
                if _fp:
                    _resolved_defs = []
                    _seen_pids = {}
                    for _ld in fx_defs:
                        _pid = _ld.get('fx_preset_ref')
                        if _pid is not None:
                            if _pid not in _seen_pids:
                                _seen_pids[_pid] = True
                                _p = _fp.get(_pid)
                                if _p:
                                    _resolved_defs.extend(_p.layers)
                        else:
                            _resolved_defs.append(_ld)
                    fx_defs = _resolved_defs
                if fx_defs:
                    fx_defs_by_fid[fid_str] = fx_defs

        # _expand_color_fx/_expand_group_fx/_bucket_fx_defs (below) are
        # module-level helpers defined near FXEngine in studio_project.py —
        # not extracted yet (a later phase: engine/fx.py). Deferred
        # (function-local) import, not module-level: unlike models/presets.py
        # itself (loaded very early in studio_project.py's execution), these
        # functions are defined much LATER in the file, so a module-level
        # `from __main__ import (...)` here would fail at import time. By
        # the time this method actually runs (a cue firing during normal
        # operation), the whole file has finished loading and __main__ has
        # them. Same pattern as drivers/ai.py's Fader import, opposite
        # direction (that one's dependency was defined earlier; this one's
        # is defined later) — see that file's docstring for the general
        # rationale. Update these once engine/fx.py exists.
        from __main__ import _expand_color_fx, _expand_group_fx, _bucket_fx_defs

        # Expand color_id refs and resolve group_id targets
        expanded = _expand_color_fx(fx_defs_by_fid, self.color_pool)
        expanded = _expand_group_fx(expanded, patch, self.group_pool)

        def _add(ld, ch, targets):
            self._fx_counter += 1
            fxid = self.fdr_id * 10000 + self._fx_counter
            # Use default_infade (cue fade time) when the FX def has no explicit infade
            infade = ld['infade'] if 'infade' in ld else default_infade
            _mirror, _cluster, _order = _fx_grouping_compat(ld)
            self.fx_engine.add(
                fxid, ld.get('waveform', 'sine'), ch,
                rate_bpm     = ld.get('bpm',          60.0),
                size         = ld.get('size',        100.0),
                targets      = targets,
                spread       = ld.get('spread',        0.0),
                phase_offset = ld.get('phase_offset',  0.0),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
                dim_id       = ld.get('dim_id'),
                speed_id     = ld.get('speed_id'),
                infade       = infade,
                outfade      = ld.get('outfade',       0.0),
                block_size   = ld.get('block_size',      1),
                order        = _order,
                direction    = ld.get('direction','forward'),
                mirror       = _mirror,
                cluster      = _cluster,
                low          = ld.get('low', 0.0),
            )
            self._fx_ids.append(fxid)
            # Apply fader size_factor to the newly-created layer
            if self.size_factor != 1.0:
                layer = self.fx_engine._layers.get(fxid)
                if layer is not None:
                    layer.size_scale = self.size_factor

        # _bucket_fx_defs (module-level, defined near FXEngine) merges
        # identical defs across fixtures into one layer so spread/chase can
        # cross fixture boundaries — see target_scope in FX command docs.
        for ld, targets in _bucket_fx_defs(expanded, patch):
            _add(ld, ld['channel'], targets)

    def _apply_size_factor(self):
        """Push current size_factor to all owned FX layers immediately."""
        if not self.fx_engine:
            return
        for fxid in self._fx_ids:
            layer = self.fx_engine._layers.get(fxid)
            if layer is not None:
                layer.size_scale = self.size_factor

    # ── Playback ─────────────────────────────────────────────

    def go(self, patch, fade_engine):
        if not self.stack:
            return f"fader {self.fdr_id}: no stack assigned"
        self.is_active = True
        return self.stack.go(patch, fade_engine, self)

    def back(self, patch, fade_engine):
        if not self.stack:
            return f"fader {self.fdr_id}: no stack assigned"
        self.is_active = True
        return self.stack.back(patch, fade_engine, self)

    def goto(self, num, patch, fade_engine):
        if not self.stack:
            return f"fader {self.fdr_id}: no stack assigned"
        self.is_active = True
        return self.stack.goto(num, patch, fade_engine, self)

    def reload(self, patch, fade_engine):
        """Re-fire the current cue from scratch without advancing."""
        if not self.stack:
            return f"fader {self.fdr_id}: no stack assigned"
        self.is_active = True
        return self.stack.reload(patch, fade_engine, self)

    def flash_on(self, patch, fade_engine):
        """
        Snap the current (or first) cue on instantly, bypassing crossfade —
        for 'flash' trigger_mode: live only while held, released via
        flash_off(). Always snaps (override=0, no fade, no delay, bypass TIMELOCK).
        """
        if not self.stack:
            return f"fader {self.fdr_id}: no stack assigned"
        prev_override = (self.time_override_on, self.time_override_fade, self.time_override_delay)
        prev_allow    = self.stack.allow_exec_time
        self.time_override_on    = True
        self.time_override_fade  = 0.0
        self.time_override_delay = 0.0
        self.stack.allow_exec_time = True   # bypass TIMELOCK — flash always snaps
        try:
            if self.stack.current is not None:
                result = self.goto(self.stack.current, patch, fade_engine)
            else:
                result = self.go(patch, fade_engine)
        finally:
            (self.time_override_on, self.time_override_fade,
             self.time_override_delay) = prev_override
            self.stack.allow_exec_time = prev_allow
        return result

    def flash_off(self):
        """Release flash — deactivates output but preserves cue position."""
        self._clear_fx()
        self.is_active = False
        self.layer.clear()
        self._follow_at = None
        # stack.current intentionally not reset — position is preserved

    def stop(self):
        self._clear_fx()
        self.is_active = False
        self.layer.clear()
        self._follow_at = None
        if self.stack:
            self.stack.current = None

    def moment_on(self, patch, fade_engine):
        """Press a moment button: fire the current (or first) cue with normal fade times.
        Unlike flash, moment respects cue fade times and TIMELOCK."""
        if not self.stack:
            return f"fader {self.fdr_id}: no stack assigned"
        if self.stack.current is not None:
            return self.goto(self.stack.current, patch, fade_engine)
        return self.go(patch, fade_engine)

    def moment_off(self, fade_engine):
        """Release a moment button: fade out over off_time, then stop."""
        off_t = getattr(self, 'off_time', 0.0)
        if off_t <= 0.0:
            self._clear_fx()
            self.is_active = False
            self.layer.clear()
            return
        # Start release fade; stop() is called when fade completes
        self._clear_fx()
        fade_engine.fire_release(self, off_t, done_callback=self.stop)


class FaderPool:
    """Numbered bank of Fader slots (1-based)."""

    def __init__(self):
        self.faders       = {}    # { int: Fader }
        self._fire_order     = []    # exec_ids ordered by last GO (last = highest priority)
        self.default_fx_engine   = None
        self.default_form_pool   = None
        self.default_color_pool  = None
        self.default_dim_pool    = None
        self.default_group_pool  = None
        self.default_attr_pools  = None   # dict of {attribute_name: AttributePool}
        self.default_fx_pool     = None   # FXPool instance, injected at startup
        # Pages group fader slots for display/navigation — organizational
        # only, doesn't affect playback. { int: {'name': str, 'slots': [int, ...]} }
        self.pages = {}

    def get(self, n):
        n = int(n)
        if n not in self.faders:
            ex = Fader(n)
            ex.fx_engine  = self.default_fx_engine
            ex.form_pool  = self.default_form_pool
            ex.color_pool = self.default_color_pool
            ex.dim_pool   = self.default_dim_pool
            ex.group_pool = self.default_group_pool
            ex.attr_pools = self.default_attr_pools
            ex.fx_pool    = self.default_fx_pool
            self.faders[n] = ex
        return self.faders[n]

    def assign(self, fdr_id, stack):
        ex = self.get(fdr_id)
        ex.assign(stack)
        return ex

    def bump_priority(self, fdr_id):
        """Move fdr to top of the LTP stack (called when it fires GO)."""
        if fdr_id in self._fire_order:
            self._fire_order.remove(fdr_id)
        self._fire_order.append(fdr_id)

    def active_layers(self):
        """
        Returns list of (layer_dict, level) in merge order.
        First entry = lowest priority, last entry = highest (LTP — last written wins).
        Sorted by: fader priority level first, then fire order within same level.
        """
        entries = []
        for i, eid in enumerate(self._fire_order):
            ex = self.faders.get(eid)
            if ex and ex.is_active and ex.stack:
                if getattr(ex, 'output_mode', 'normal') == 'moment' and ex.level <= 0.0:
                    continue  # moment fader: excluded from LTP when at floor
                entries.append((ex.priority, i, ex.layer, ex.level))
        entries.sort(key=lambda e: (e[0], e[1]))
        return [(layer, level) for _, _, layer, level in entries]

    def all_slots(self):
        return sorted(self.faders.keys())

    # ── Pages ────────────────────────────────────────────────

    def get_page(self, n):
        n = int(n)
        if n not in self.pages:
            self.pages[n] = {'name': f'page {n}', 'stacks': []}
        return self.pages[n]

    def set_page_name(self, n, name):
        self.get_page(n)['name'] = name.lower() if isinstance(name, str) else name

    def add_to_page(self, n, cs_id):
        page = self.get_page(n)
        cs_id = int(cs_id)
        if cs_id not in page['stacks']:
            page['stacks'].append(cs_id)

    def remove_from_page(self, n, cs_id):
        page = self.get_page(n)
        cs_id = int(cs_id)
        if cs_id in page['stacks']:
            page['stacks'].remove(cs_id)

    def delete_page(self, n):
        self.pages.pop(int(n), None)

    def all_pages(self):
        return sorted(self.pages.keys())


# ============================================================
# FXpreset + FXPool
# A preset is a snapshot of one or more FX layer definitions.
# Targets are NOT stored — resolved at fire time from patch/group.
# ============================================================

class FXPreset:
    """One named FX state: a list of layer defs that fire together."""

    name = LowercaseName()

    def __init__(self, preset_id, name=""):
        self.preset_id = int(preset_id)
        self.name      = name or f"fx {preset_id}"
        self.layers    = []   # list of dicts: {waveform, channel, rate_bpm, size, spread}

    def add_layer(self, waveform, channel, rate_bpm=60.0, size=100.0, spread=0.0,
                  form_id=None, rate_id=None, size_id=None, spread_id=None, bpm=None,
                  dim_id=None, color_id=None, group_id=None, speed_id=None,
                  phase_offset=0.0, block_size=1, order='linear', direction='forward',
                  mirror=False, cluster=False, low=0.0, target_scope=None,
                  infade=0.0, outfade=0.0):
        self.layers.append({
            'waveform':      waveform.lower(),
            'channel':       channel.lower(),
            'bpm':           float(bpm if bpm is not None else rate_bpm),
            'size':          float(size),
            'low':           float(low),
            'spread':        float(spread),
            'phase_offset':  float(phase_offset),
            'infade':        float(infade),
            'outfade':       float(outfade),
            'form_id':       form_id,
            'rate_id':       rate_id,
            'size_id':       size_id,
            'spread_id':     spread_id,
            'dim_id':        dim_id,
            'color_id':      color_id,
            'group_id':      group_id,
            'speed_id':      speed_id,
            'block_size':    block_size,
            'order':         order,
            'direction':     direction,
            'mirror':        bool(mirror),
            'cluster':       bool(cluster),
            'target_scope':  target_scope,
        })

    def __repr__(self):
        parts = [f"{ld['waveform']} {ld['channel']}" for ld in self.layers]
        return f"[FX {self.preset_id}] {self.name}  ({', '.join(parts)})"


class FXPool:
    """Numbered library of FXpreset objects (1-based slots)."""

    def __init__(self):
        self.presets = {}   # {int: FXPreset}

    def get(self, n):
        return self.presets.get(int(n))

    def store(self, n, preset):
        self.presets[int(n)] = preset

    def delete(self, n):
        self.presets.pop(int(n), None)

    def all_slots(self):
        return sorted(self.presets.keys())


# ------------------------------------------------------------
# Fade
# ------------------------------------------------------------

class Fade:
    """
    One active crossfade between two states.
    Interpolates linearly from data_from → data_to
    over fade_time seconds, after an optional delay_time.
    Writes into fader.layer via fader.set_value().
    """

    # Map channel names to attribute groups for per-group timing
    _CHANNEL_GROUP = {
        'red': 'colour', 'green': 'colour', 'blue': 'colour',
        'white': 'colour', 'amber': 'colour',
        'dim': 'dim', 'dimmer': 'dim',
        'pan': 'position', 'tilt': 'position',
        'pan_fine': 'position', 'tilt_fine': 'position',
        'gobo': 'beam', 'gobo_rot': 'beam', 'gobo2': 'beam', 'gobo2_rot': 'beam',
        'zoom': 'beam', 'focus': 'beam', 'iris': 'beam',
        'shutter1': 'beam', 'strobe': 'beam',
        'color': 'beam', 'prism': 'beam', 'frost': 'beam',
        'control': 'control', 'macro': 'control', 'animation': 'control',
    }

    def __init__(self, data_from, data_to, fade_time, delay_time, fader,
                 fade_times=None, delay_times=None, done_callback=None):
        self.data_from    = data_from
        self.data_to      = data_to
        self._default_ft  = float(fade_time)
        self._default_dt  = float(delay_time)
        self.fader     = fader
        self.done         = False
        self._done_callback = done_callback

        now = time.monotonic()
        _ft  = fade_times  or {}
        _dt  = delay_times or {}

        # Pre-compute start_time and fade_time per group so tick() does no dict creation
        all_groups = set(_ft) | set(_dt)
        self._group_ft    = {g: float(_ft.get(g, self._default_ft)) for g in all_groups}
        self._group_start = {g: now + float(_dt.get(g, self._default_dt)) for g in all_groups}
        self._default_start = now + self._default_dt

    def tick(self, now):
        all_done = True

        for fid in set(self.data_from) | set(self.data_to):
            from_vals = self.data_from.get(fid, {})
            to_vals   = self.data_to.get(fid, {})
            for ch in set(from_vals) | set(to_vals):
                v_from = from_vals.get(ch, 0)
                # Flag channels (fx_kill etc.) reset to 0 when absent from the new
                # cue rather than persisting via LTP — the flag should only be active
                # when explicitly stored in the current cue's data.
                _flag = ch in ('fx_kill',)
                v_to   = to_vals.get(ch, 0 if _flag else v_from)
                if not isinstance(v_from, (int, float)) or not isinstance(v_to, (int, float)):
                    continue  # skip non-DMX keys (fx defs, refs, etc.)

                group   = Fade._CHANNEL_GROUP.get(ch, 'other')
                start   = self._group_start.get(group, self._default_start)
                ft      = self._group_ft.get(group,    self._default_ft)

                elapsed = now - start
                if elapsed < 0:
                    all_done = False
                    continue  # still in delay for this attribute group

                t = 1.0 if ft == 0 else min(1.0, elapsed / ft)
                if t < 1.0:
                    all_done = False

                self.fader.set_value(fid, ch, v_from + (v_to - v_from) * t)

        self.done = all_done
        if self.done and self._done_callback:
            try:
                self._done_callback()
            except Exception:
                pass
            self._done_callback = None

__all__ = ["ColorPreset", "ColorPool", "DimmerPreset", "DimmerPool",
           "AttributePreset", "AttributePool", "Group", "GroupPool",
           "Cue", "Stack", "CuePool", "StackPool", "Fader", "FaderPool",
           "FXPreset", "FXPool", "Fade"]
