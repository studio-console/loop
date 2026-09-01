"""Studio Console startup wiring — extracted from studio_project.py's
"Live Session" section. Instantiates every singleton (patch, prog, pools,
engines, drivers), loads the show from disk, sets up MIDI/OSC mappings and
the MIDI target registry, and defines the cue-navigation/save-show/
OSC-callback helper functions that sit close to that wiring rather than
belonging to any single engine module. Not a clean "just assignments" file
— it's genuinely 1200+ lines of real startup logic, including several
top-level side-effecting calls (network.start(), midi.start(), osc.start())
and a large first-run-factory-defaults block. Pure move, zero behavior
change, with two categories of fix applied (found by a careful pre-check,
not after the fact):

1. `GUIEngine.target_registry = {...}` (and later mutations to it) — safe
   as a plain module-level `from __main__ import GUIEngine`. GUIEngine
   hasn't been extracted yet (a later phase), but it's defined *earlier*
   in studio_project.py than this module's own import point (Phase 2's
   extraction left GUIEngine sitting right after the theme import, well
   before where this wiring section lived), so by the time studio_project.py
   reaches the line that imports this module, GUIEngine already exists in
   __main__'s namespace.

2. Six call sites reference `run_command`, defined *after* this section in
   studio_project.py (not extracted until a later phase) — the opposite
   timing situation from GUIEngine. Each needs a deferred (function-local)
   `from __main__ import run_command`, same category as drivers/ai.py's
   Fader import. Two of the six were bare lambdas inside dynamically
   generated MIDI-target closures (`_make_go`/`_make_flash` in the MIDI
   restore block) — lambdas can't contain an import statement, so those
   were converted to small named wrapper functions that do the deferred
   import inside themselves, preserving the original "resolve run_command
   at call time, not definition time" behavior exactly, just made explicit
   since it now crosses a module boundary.
"""

import os
import json
import time

from studio_console.paths import DATA_DIR, SAVES_DIR
from studio_console.show import ShowFile, _write_file, _read_file
from studio_console.models.fixtures import FixtureLibrary, Patch, programmer
from studio_console.models.presets import (
    GroupPool, ColorPool, DimmerPool, FaderPool, CuePool, StackPool,
    FXPool, AttributePool, Stack, FXPreset,
)
from studio_console.engine.playback import OutputState, FadeEngine
from studio_console.engine.fx import (
    FormPool, RatePool, SizePool, SpreadPool, SpeedMasterPool, FXEngine,
    FormPreset, RatePreset, SizePreset, SpreadPreset, SpeedMaster,
    _fx_grouping_compat,
)
from studio_console.drivers.network import NetworkEngine
from studio_console.drivers.midi import MIDIEngine
from studio_console.drivers.osc import OSCEngine
from studio_console.drivers.audio import AudioEngine, AudioMapper
from studio_console.drivers.ai import AIEngine

# GUIEngine hasn't been extracted yet (a later phase) — see module docstring
# category 1 above for why a module-level reach-back is safe here.
from __main__ import GUIEngine


# STUDIO CONSOLE — Live Session
# stack 1 / Axiom 25 MkII mapped
# ============================================================

# ----------------------------------------------------------
# Setup
# ----------------------------------------------------------

library = FixtureLibrary()

# Load JSON profiles from profiles/ folder (custom fixtures without touching code)
library.load_from_folder(os.path.join(DATA_DIR, "profiles"))

# Load GDTF fixtures — drop .gdtf files into studio_data/gdtf/ to auto-import
os.makedirs(ShowFile.GDTF_DIR, exist_ok=True)
library.load_gdtf_folder(ShowFile.GDTF_DIR)

patch   = Patch(library)

if not ShowFile.load_patch(patch):
    # First-run defaults — 6 SGM RGB 54-pixel tubes across two universes
    patch.patch_fixture(1, "Tube 1", "SGM_RGB_54", universe=1, start_address=1)
    patch.patch_fixture(2, "Tube 2", "SGM_RGB_54", universe=1, start_address=163)
    patch.patch_fixture(3, "Tube 3", "SGM_RGB_54", universe=1, start_address=325)
    patch.patch_fixture(4, "Tube 4", "SGM_RGB_54", universe=2, start_address=1)
    patch.patch_fixture(5, "Tube 5", "SGM_RGB_54", universe=2, start_address=163)
    patch.patch_fixture(6, "Tube 6", "SGM_RGB_54", universe=2, start_address=325)
    ShowFile.save_patch(patch)

prog         = programmer(patch)
_prog_snapshots = {}  # { int slot: {"name": str, "data": dict} } — session-only
group_pool   = GroupPool()
color_pool   = ColorPool()
dim_pool     = DimmerPool()
output_state = OutputState(patch)
output_state.link_programmer(prog)
_blackout_saved_level = [1.0]   # saved master level before BLACKOUT; shared mutable ref
fader_pool = FaderPool()
output_state.link_fader_pool(fader_pool)
fade_engine  = FadeEngine()
form_pool    = FormPool()   # built-ins pre-seeded; custom forms loaded below
rate_pool         = RatePool()
size_pool         = SizePool()
spread_pool       = SpreadPool()
speed_master_pool = SpeedMasterPool()
fx_engine    = FXEngine(output_state, form_pool=form_pool,
                        rate_pool=rate_pool, size_pool=size_pool,
                        spread_pool=spread_pool, dim_pool=dim_pool,
                        speed_master_pool=speed_master_pool,
                        group_pool=group_pool)
# Wire fx_engine + form_pool into fader_pool so new faders inherit them
fader_pool.default_fx_engine  = fx_engine
fader_pool.default_form_pool  = form_pool
fader_pool.default_color_pool = color_pool
fader_pool.default_dim_pool   = dim_pool
fader_pool.default_group_pool = group_pool
# STUDIO_DRY_RUN=1 disables real sACN output (no socket, nothing sent to the
# tubes) while still running the full FX/cue/output pipeline — used for
# unattended/automated testing. STUDIO_HEADLESS=1 additionally skips the
# blocking DearPyGui window (see the GUI launch block near the end of file).
STUDIO_DRY_RUN  = os.environ.get('STUDIO_DRY_RUN')  == '1'
STUDIO_HEADLESS = os.environ.get('STUDIO_HEADLESS') == '1'
if STUDIO_DRY_RUN:
    print("*** STUDIO_DRY_RUN active — sACN output disabled, no data sent to fixtures ***")

_net_bind, _net_univs = ShowFile.load_network()
_NET_BIND     = _net_bind  if _net_bind  is not None else "192.168.1.161"
_NET_UNIVERSES = _net_univs if _net_univs is not None else [1, 2]
network      = NetworkEngine(output_state, universes=_NET_UNIVERSES,
                             bind_address=_NET_BIND,
                             dry_run=STUDIO_DRY_RUN,
                             fx_engine=fx_engine)
network.start()

midi = MIDIEngine()
MIDIEngine.list_ports()
midi.start(port=1)  # Axiom 25 Axiom USB In

# OSC engine
# Port 8000 is grandMA3's OSC port — Studio Console uses 8001 so
# both can run at the same time during transition.
# When you fully replace MA3, stop app_gma3 and switch to port 8000.
osc = OSCEngine()
osc.start(port=8001)

# Lightform Creator — update IP to match your Lightform machine
# Leave commented if Lightform isn't running yet
# osc.add_target("lightform", "192.168.1.XXX", 9000)

osc.list_targets()

# audio engine (Block 9) — reactive audio→light mapping. Unlike MIDI (control
# surface hardware the console expects on every launch) or OSC (a passive
# network listener), microphone capture is opt-in: the engine and mapper
# construct safely with no input device present and sit idle until an
# operator runs AUDIO START / AUDIO ON.
audio_engine = AudioEngine()
audio_mapper = AudioMapper(audio_engine, output_state, patch)

all_subs = [sub for master in patch.all_fixtures() for sub in master.all_subs()]

# ----------------------------------------------------------
# State tracking (defined before show-file load so it can
# be updated from the file's saved fx_params)
# ----------------------------------------------------------

active_fx    = []    # programmer preview FX layer objects (while editing)
_prog_fx_ids = []    # FX engine layer IDs for programmer preview (cleared on CLEAR stage 2)
_fader_dim   = [0.0] # last dim value from fader (for flash restore)

def _stop_prog_fx_preview():
    """Stop programmer preview FX layers without wiping prog.data['fx'] entries."""
    for fxid in _prog_fx_ids:
        fx_engine.remove(fxid)
    _prog_fx_ids.clear()
    active_fx.clear()

_fx_params = {
    'rate_bpm': 60.0,
    'size':     100.0,   # 0-100 (100 = full DMX 255)
    'spread':   0.0,     # 0-100 (100 = full 1-cycle phase spread)
    'infade':   0.0,
    'outfade':  0.0,
}

# ----------------------------------------------------------
# Pools — Cues and Stacks (faders)
# ----------------------------------------------------------

cue_pool       = CuePool()
stack_pool  = StackPool()
fx_pool        = FXPool()
active_fader = [1]   # list so closures can rebind it
_tap_times: list = []   # monotonic timestamps for tap-tempo; shared between GUI and TAP command

# programmer time override — when on, overrides cue fade/delay for manually fired cues
_prog_time = {
    'on':    False,
    'fade':  0.0,
    'delay': 0.0,
}

# Attribute preset pools — extend this list as new fixture types are added
position_pool = AttributePool("position", ["pan", "tilt", "pan_fine", "tilt_fine"])
gobo_pool     = AttributePool("gobo",     ["gobo", "gobo_rot", "gobo2", "gobo2_rot"])
zoom_pool     = AttributePool("zoom",     ["zoom"])
focus_pool    = AttributePool("focus",    ["focus"])
beam_pool     = AttributePool("beam",     ["iris", "shutter1", "strobe"])
control_pool  = AttributePool("control",  ["control", "macro", "prism", "frost", "animation"])

# Wire attribute pools into fader_pool now that they exist
_attr_pools = {
    "position": position_pool,
    "gobo":     gobo_pool,
    "zoom":     zoom_pool,
    "focus":    focus_pool,
    "beam":     beam_pool,
    "control":  control_pool,
}
fader_pool.default_attr_pools = _attr_pools
fader_pool.default_fx_pool    = fx_pool

macro_pool       = {}    # {slot_int: {"name": str, "commands": [str, ...]}}
_macro_recording = {"slot": None, "cmds": []}
_macro_play_stack = []   # slot ints currently mid-playback, innermost last — guards against MACRO N containing MACRO N (direct or indirect cycle)

# ── Load all data files (migrate legacy file if present) ──
ShowFile.load_fx(_fx_params)
ShowFile.load_fx_pool(fx_pool)
ShowFile.load_forms(form_pool)
ShowFile.load_rate_pool(rate_pool)
ShowFile.load_size_pool(size_pool)
ShowFile.load_spread_pool(spread_pool)
ShowFile.load_speed_masters(speed_master_pool)
ShowFile.load_groups(group_pool)
ShowFile.load_colors(color_pool)
ShowFile.load_dims(dim_pool)
_cs_loaded = ShowFile.load_stacks(stack_pool, cue_pool)
ShowFile.load_position_pool(position_pool)
ShowFile.load_gobo_pool(gobo_pool)
ShowFile.load_zoom_pool(zoom_pool)
ShowFile.load_focus_pool(focus_pool)
ShowFile.load_beam_pool(beam_pool)
ShowFile.load_control_pool(control_pool)
ShowFile.load_fader_pages(fader_pool)
ShowFile.load_faders(fader_pool, stack_pool)
ShowFile.load_osc_targets(osc)
ShowFile.load_macros(macro_pool)
ShowFile.load_state(output_state, fader_pool, stack_pool, active_fader,
                    prog_time=_prog_time, fader_dim=_fader_dim)
# Restores prog.data/.disabled/.selection (unrecorded programmer edits,
# selection, and any live-preview FX defs) — data only here; the live FX
# *engine layers* themselves are rebuilt from this once the GUI exists
# (gui/core.py's _tick_first_sync — _prog_fx_rebuild isn't safely
# reachable from this module, see that method's comment).
ShowFile.load_programmer(prog, patch)

# ── Fixture defaults ────────────────────────────────────────────────────
# Loaded from defaults.json; applied to programmer_layer so every fixture
# starts at these values unless a cue overrides them.
# Keys: "dim" (0.0–1.0), "red"/"green"/"blue" (0–255), "kelvin" (CCT)
_fixture_defaults = ShowFile.load_defaults()

def _apply_fixture_defaults():
    """Write defaults into programmer_layer for all patched fixtures."""
    for master in patch.all_fixtures():
        fid = str(master.fixture_id)
        layer = output_state.programmer_layer.setdefault(fid, {})
        if 'dim' in _fixture_defaults:
            layer['dim'] = float(_fixture_defaults['dim'])
        if 'red' in _fixture_defaults:
            layer['red']   = int(_fixture_defaults['red'])
            layer['green'] = int(_fixture_defaults.get('green', 0))
            layer['blue']  = int(_fixture_defaults.get('blue', 0))

_apply_fixture_defaults()

# Migrate old single-file if new files don't exist yet
if not _cs_loaded:
    _migrated = ShowFile.migrate_legacy(
        stack_pool, cue_pool, group_pool, color_pool, dim_pool, _fx_params)
    if not _migrated:
        # ── First-run factory defaults ─────────────────────────────────
        # Helper to set all fixtures to a colour quickly
        def _set_all(r, g, b, dim=100):
            prog.execute(f"1 THRU 6 AT FULL")
            prog.execute(f"1 THRU 6 AT R {r}")
            prog.execute(f"1 THRU 6 AT G {g}")
            prog.execute(f"1 THRU 6 AT B {b}")
            if dim != 100:
                prog.execute(f"1 THRU 6 AT DIM {dim}")

        # ── Custom Forms (slots 5-8) ──────────────────────────────────
        form_pool.store(5, FormPreset(5, "Bounce",
            form_type='breakpoints',
            breakpoints=[[0.0,0.0],[0.1,1.0],[1.0,0.0]]))

        form_pool.store(6, FormPreset(6, "Heartbeat",
            form_type='breakpoints',
            breakpoints=[[0.0,0.0],[0.05,1.0],[0.12,0.0],
                         [0.22,0.8],[0.30,0.0],[1.0,0.0]]))

        form_pool.store(7, FormPreset(7, "Spike",
            form_type='breakpoints',
            breakpoints=[[0.0,0.0],[0.03,1.0],[0.06,0.0],[1.0,0.0]]))

        form_pool.store(8, FormPreset(8, "Trapezoid",
            form_type='breakpoints',
            breakpoints=[[0.0,0.0],[0.2,1.0],[0.65,1.0],[0.85,0.0],[1.0,0.0]]))

        ShowFile.save_forms(form_pool)

        # ── FX pool (slots 1-8) ───────────────────────────────────────
        def _fx(pid, name, layers):
            p = FXPreset(pid, name)
            for lyr in layers:
                p.add_layer(*lyr[0:2], rate_bpm=lyr[2], size=lyr[3], spread=lyr[4],
                            form_id=lyr[5] if len(lyr) > 5 else None)
            return p

        fx_pool.store(1, _fx(1, "Red Sine",    [("sine",  "red",   60,  220, 1.0)]))
        fx_pool.store(2, _fx(2, "Blue Sine",   [("sine",  "blue",  60,  220, 1.0)]))
        fx_pool.store(3, _fx(3, "Magenta Sine",[("sine",  "red",   60,  200, 1.0),
                                                ("sine",  "blue",  60,  200, 1.0)]))
        fx_pool.store(4, _fx(4, "White Pulse", [("pulse", "red",   90,  200, 0.0),
                                                ("pulse", "green", 90,  200, 0.0),
                                                ("pulse", "blue",  90,  200, 0.0)]))
        fx_pool.store(5, _fx(5, "RGB Chase",   [("sine",  "red",   50,  180, 0.33),
                                                ("sine",  "green", 50,  180, 0.33),
                                                ("sine",  "blue",  50,  180, 0.33)]))
        fx_pool.store(6, _fx(6, "Green Sine",  [("sine",  "green", 60,  220, 1.0)]))
        fx_pool.store(7, _fx(7, "Strobe",      [("pulse", "red",   240, 255, 0.0),
                                                ("pulse", "green", 240, 255, 0.0),
                                                ("pulse", "blue",  240, 255, 0.0)]))

        p8 = FXPreset(8, "Bounce Red+Blue")
        p8.add_layer("sine", "red",  50, 210, 1.0, form_id=5)
        p8.add_layer("sine", "blue", 50, 210, 1.0, form_id=5)
        fx_pool.store(8, p8)

        ShowFile.save_fx_pool(fx_pool)

        # ── stack 1: color show ────────────────────────────────────
        cs1 = Stack(1, "color Show")

        _set_all(255, 0, 0)
        cs1.record_cue(1, prog, name="Red", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 0, 255)
        cs1.record_cue(2, prog, name="Blue", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 200, 0)
        cs1.record_cue(3, prog, name="Green", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 200, 200)
        cs1.record_cue(4, prog, name="Cyan", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 0, 0, dim=0)
        cs1.record_cue(5, prog, name="Off", fade_time=2.0)
        prog.execute("CLEAR")

        # ── stack 2: Dynamic ───────────────────────────────────────
        cs2 = Stack(2, "Dynamic")

        _set_all(255, 255, 255)
        cs2.record_cue(1, prog, name="White Full", fade_time=1.5)
        prog.execute("CLEAR")

        _set_all(255, 80, 0)
        cs2.record_cue(2, prog, name="Amber", fade_time=1.5)
        prog.execute("CLEAR")

        _set_all(0, 0, 180)
        cs2.record_cue(3, prog, name="Deep Blue", fade_time=1.5)
        prog.execute("CLEAR")

        _set_all(200, 0, 200)
        cs2.record_cue(4, prog, name="Magenta", fade_time=1.5)
        prog.execute("CLEAR")

        _set_all(0, 0, 0, dim=0)
        cs2.record_cue(5, prog, name="Fade Out", fade_time=3.0)
        prog.execute("CLEAR")

        # ── stack 3: Warm Tones ────────────────────────────────────
        cs3 = Stack(3, "Warm")

        _set_all(255, 30, 0)
        cs3.record_cue(1, prog, name="Hot Red", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(255, 100, 0)
        cs3.record_cue(2, prog, name="Orange", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(255, 160, 60)
        cs3.record_cue(3, prog, name="Warm Amber", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(220, 60, 80)
        cs3.record_cue(4, prog, name="Soft Pink", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 0, 0, dim=0)
        cs3.record_cue(5, prog, name="Out", fade_time=3.0)
        prog.execute("CLEAR")

        # ── Store everything ─────────────────────────────────────────
        for _cs in (cs1, cs2, cs3):
            stack_pool.store(_cs.stack_id, _cs)
            for _cnum, _cue in _cs.cues.items():
                if _cnum == int(_cnum):
                    cue_pool.store(int(_cnum), _cue)
            _cs.print_stack()

        ShowFile.save_stacks(stack_pool)

cs1 = stack_pool.get(1) or Stack(1, "stack 1")
stack_pool.store(1, cs1)

# Wire every loaded stack into an fader slot (1:1 by default)
for _slot, _stack in stack_pool.stacks.items():
    fader_pool.assign(_slot, _stack)

# CLEAR rebinds prog.data — re-link so programmer_layer points
# to the fresh empty dict, not the old one with stale values.
output_state.link_programmer(prog)

def _active_stack():
    """Returns the stack for the current active fader."""
    return stack_pool.get(active_fader[0])

def _active_fader():
    """Returns the Fader object for the current active fader."""
    return fader_pool.get(active_fader[0])

# ----------------------------------------------------------
# FX helpers — called by cue fire and manual pads
# ----------------------------------------------------------

def _start_magenta_sine():
    fx_engine.clear()
    active_fx.clear()
    r = fx_engine.add(1, 'sine', 'red',  rate_bpm=_fx_params['rate_bpm'],
                      size=_fx_params['size'], targets=all_subs,
                      spread=_fx_params['spread'])
    b = fx_engine.add(2, 'sine', 'blue', rate_bpm=_fx_params['rate_bpm'],
                      size=_fx_params['size'], targets=all_subs,
                      spread=_fx_params['spread'])
    active_fx.extend([r, b])
    print(f"\n  FX: magenta sine  "
          f"{_fx_params['rate_bpm']:.0f}BPM  "
          f"size={_fx_params['size']:.0f}  "
          f"spread={_fx_params['spread']:.2f}")

def _stop_fx():
    # programmer-based kill: sets fx_kill in programmer so CLEAR can release it.
    # Equivalent to typing KILL FX at the command line.
    # run_command is defined later in studio_project.py (not extracted yet —
    # a later phase). Deferred import — see module docstring.
    from __main__ import run_command
    run_command("KILL FX")

# Lightform OSC map — what to send to Lightform when each cue fires.
# Edit the address/value to match your Lightform Creator OSC setup.
# These are sent automatically every time a cue fires.
LIGHTFORM_CUE_MAP = {
    1.0: ("/lightform/layer/show", 1),   # cue 1 Red   → Lightform layer 1
    2.0: ("/lightform/layer/show", 2),   # cue 2 Blue  → Lightform layer 2
    3.0: ("/lightform/layer/show", 3),   # cue 3 Sine  → Lightform layer 3
    4.0: ("/lightform/layer/show", 0),   # cue 4 Off   → Lightform layer 0 (hide)
}

# Called every time a cue fires — manages FX and sends OSC.
def _on_cue_fire(cue_num):
    # Send to Lightform if mapped AND target is configured
    if cue_num in LIGHTFORM_CUE_MAP and "lightform" in osc._clients:
        address, value = LIGHTFORM_CUE_MAP[cue_num]
        osc.send(address, value, target="lightform")

# ----------------------------------------------------------
# MA3-compatible OSC input handlers
# Any tool that was sending to grandMA3 can now send here.
# ----------------------------------------------------------

def _osc_cmd(_, *args):  # _ = OSC address, unused here
    """
    /gma3/cmd  "Go+ cue 1"
    Receives a grandMA3 command string and runs it through
    the programmer — same as typing it on the command line.
    """
    if not args:
        return
    cmd = str(args[0])
    print(f"\n  OSC cmd: {cmd}")
    # Translate a small set of MA3 shorthand → our command parser
    # Add more translations as you discover what Chataigne sends
    translations = {
        'go+':  'GO',
        'go-':  'BACK',
        'go':   'GO',
        'back': 'BACK',
    }
    lower = cmd.strip().lower()
    for ma3_word, our_word in translations.items():
        lower = lower.replace(ma3_word, our_word)
    try:
        # Use run_command so GO/BACK/fdr etc. work; prog.execute only handles
        # selection and AT commands. Deferred import — see module docstring.
        from __main__ import run_command
        result = run_command(lower.upper())
        if result:
            print(f"  OSC cmd result: {result}")
    except Exception as e:
        print(f"  OSC cmd error: {e}")

def _osc_fader(address, *args):
    """
    /gma3/fader/PAGE/fdr  float(0.0-1.0)
    fader on page PAGE, fader fdr.
    page 1 fdr 1 stays mapped to the grandmaster dim (legacy behavior,
    kept for existing OSC templates). Any other page/fdr routes straight
    to that fader's own level fader — same field the GUI fader
    sliders write via _on_exec_fader — so a surface like TouchOSC can
    drive every fader, not just the first one.
    """
    if not args:
        return
    val = float(args[0])
    # Parse page/fdr from address: /gma3/fader/1/1
    parts = address.strip('/').split('/')
    page = int(parts[2]) if len(parts) > 2 else 1
    fdr_num = int(parts[3]) if len(parts) > 3 else 1
    print(f"\n  OSC fader P{page}/E{fdr_num} → {val:.0%}")
    if page == 1 and fdr_num == 1:
        set_all_dim(val)
    else:
        fader_pool.get(fdr_num).level = max(0.0, min(1.0, val))

def _osc_key(address, *args):
    """
    /gma3/key/PAGE/fdr/TYPE  int(0/1)
    Key press on a fader.  1=press, 0=release.
    page 1 fader 1 Go/Back stay mapped to the active fader (legacy
    behavior, kept for existing OSC templates). Any other page/fader fires
    GO/BACK on that specific fader via the same "FADER <n> GO|BACK"
    command MIDI and the command line already use.

    TYPE "flash" is press-and-hold, same as a MIDI note's on/off pair or
    the GUI's FLASH button: unlike go/back it needs the release (0) event
    too, so that branch is handled before the go/back-only early return.
    """
    if not args:
        return
    pressed = int(args[0]) == 1
    parts = address.strip('/').split('/')
    page     = int(parts[2]) if len(parts) > 2 else 1
    fdr_num = int(parts[3]) if len(parts) > 3 else 1
    key_type = parts[4] if len(parts) > 4 else "go"
    print(f"\n  OSC key P{page}/E{fdr_num}/{key_type} {'▼' if pressed else '▲'}")
    # run_command is defined later in studio_project.py — deferred import.
    from __main__ import run_command
    if key_type.lower() == 'flash':
        run_command(f"FADER {fdr_num} FLASH {'ON' if pressed else 'OFF'}")
        return
    if not pressed:
        return
    is_go   = key_type.lower() in ('go', 'go+')
    is_back = key_type.lower() in ('back', 'go-')
    if not (is_go or is_back):
        return
    if page == 1 and fdr_num == 1:
        cue_go() if is_go else cue_back()
    else:
        run_command(f"FADER {fdr_num} {'GO' if is_go else 'BACK'}")

# Register MA3-style OSC handlers
osc.map("/gma3/cmd",         _osc_cmd)
osc.map("/gma3/fader/*/*",   _osc_fader)  # /gma3/fader/page/fdr
osc.map("/gma3/key/*/*/*",   _osc_key)    # /gma3/key/page/fdr/type
# Catch-all: print anything else (helps discover what Chataigne is sending)
osc.map("/*", lambda addr, *a: print(f"  OSC (unmapped): {addr}  {list(a)}"),
         default_handler=True)

# ----------------------------------------------------------
# Grandmaster dim — writes to programmer_layer (highest priority)
# ----------------------------------------------------------

def set_all_dim(val):
    _fader_dim[0] = val
    for master in patch.all_fixtures():
        output_state.programmer_layer.setdefault(str(master.fixture_id), {})['dim'] = val
    print(f"\r  dim → {val:.0%}      ", end='', flush=True)

# ----------------------------------------------------------
# Knob callbacks
# Each knob saves to _fx_params AND updates any running FX live.
# If no FX is active the value is remembered for when cue 3 fires.
# ----------------------------------------------------------

def set_fx_rate(val):
    bpm = 20 + val * 460   # 20 – 480 BPM
    _fx_params['rate_bpm'] = bpm
    now = time.monotonic()
    for fx in active_fx:
        fx.set_rate_smooth(bpm, now)
    suffix = f"  ({len(active_fx)} FX live)" if active_fx else "  (pending — fire cue 3)"
    print(f"\r  FX rate → {bpm:.0f} BPM{suffix}   ", end='', flush=True)

def set_fx_size(val):
    size = val * 100
    _fx_params['size'] = size
    for fx in active_fx:
        fx.size = size
    suffix = f"  ({len(active_fx)} FX live)" if active_fx else "  (pending)"
    print(f"\r  FX size → {size:.0f}{suffix}      ", end='', flush=True)

def set_fx_spread(val):
    spread = val * 100
    _fx_params['spread'] = spread
    for fx in active_fx:
        fx.spread = spread
    suffix = f"  ({len(active_fx)} FX live)" if active_fx else "  (pending)"
    print(f"\r  FX spread → {spread:.1f}{suffix}   ", end='', flush=True)

def _make_set_speed_master(slot_id):
    """Return a MIDI callback that sets speed_master_pool[slot_id].bpm from a 0-1 CC value."""
    def _set_speed(val):
        bpm = 20 + val * 460   # 20 – 480 BPM  (same range as global FX rate)
        speed_master_pool.set_bpm(slot_id, bpm)
        print(f"\r  speed master {slot_id} → {bpm:.0f} BPM   ", end='', flush=True)
    return _set_speed

# ----------------------------------------------------------
# cue navigation — GO/BACK auto-trigger _on_cue_fire
# ----------------------------------------------------------

def cue_go():
    _stop_prog_fx_preview()
    ex = _active_fader()
    fader_pool.bump_priority(ex.fdr_id)
    ex.go(patch, fade_engine)
    stk = ex.stack
    if stk:
        _on_cue_fire(stk.current)

def cue_back():
    _stop_prog_fx_preview()
    ex = _active_fader()
    fader_pool.bump_priority(ex.fdr_id)
    ex.back(patch, fade_engine)
    stk = ex.stack
    if stk:
        _on_cue_fire(stk.current)

def cue_reload():
    """Re-fire the current cue from scratch: resets FX, re-applies fade."""
    _stop_prog_fx_preview()
    ex = _active_fader()
    stk = ex.stack
    if not stk or stk.current is None:
        return "no active cue to reload"
    fader_pool.bump_priority(ex.fdr_id)
    result = ex.reload(patch, fade_engine)
    _on_cue_fire(stk.current)
    return result

def goto_cue(num):
    _stop_prog_fx_preview()
    ex = _active_fader()
    fader_pool.bump_priority(ex.fdr_id)
    result = ex.goto(num, patch, fade_engine)
    if result and 'not found' not in result:
        _on_cue_fire(float(num))
    return result

# ----------------------------------------------------------
# direct cue triggers (pads 1-4)
# ----------------------------------------------------------

def goto_1(): goto_cue(1)
def goto_2(): goto_cue(2)
def goto_3(): goto_cue(3)
def goto_4(): goto_cue(4)

# ----------------------------------------------------------
# Flash white — uses programmer_layer so it trumps cues
# ----------------------------------------------------------

def flash_on():
    for master in patch.all_fixtures():
        output_state.programmer_layer.setdefault(str(master.fixture_id), {})['dim'] = 1.0
    for sub in all_subs:
        pl = output_state.programmer_layer.setdefault(str(sub.fixture_id), {})
        pl['red'] = pl['green'] = pl['blue'] = 255

def flash_off():
    for sub in all_subs:
        pl = output_state.programmer_layer.get(str(sub.fixture_id), {})
        for ch in ('red', 'green', 'blue'):
            pl.pop(ch, None)
    set_all_dim(_fader_dim[0])   # restore fader position

# ----------------------------------------------------------
# Transport CC helpers (value 127=press, 0=release)
# ----------------------------------------------------------

def transport_go(val):
    if val > 0.5:
        cue_go()

def transport_back(val):
    if val > 0.5:
        cue_back()

def transport_rewind(val):
    if val > 0.5:
        goto_cue(1)

def tap_tempo():
    """MIDI-mappable tap-tempo trigger (safe to call from MIDI thread).
    Shares _tap_times with the TAP command and GUI button.
    Updates _fx_params['rate_bpm'] directly — FX engine reads it on next tick.
    """
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

# ----------------------------------------------------------
# MIDI mappings — Axiom 25 MkII
# ----------------------------------------------------------

# Vol slider / Knob 1 → grandmaster dim
# Names MUST match target_registry keys so show-file restore works
midi.map_cc(channel=1, cc=7,  callback=set_all_dim,   name="Grandmaster Dim",   soft_takeover=True)
midi.map_cc(channel=1, cc=74, callback=set_all_dim,   name="Grandmaster Dim",   soft_takeover=True)

# FX knobs — immediately live (no critical software state to protect)
midi.map_cc(channel=1, cc=71, callback=set_fx_rate,   name="FX Rate",    soft_takeover=False)
midi.map_cc(channel=1, cc=91, callback=set_fx_size,   name="FX Size",    soft_takeover=False)
midi.map_cc(channel=1, cc=93, callback=set_fx_spread, name="FX Spread",  soft_takeover=False)

# Pads (ch=10)
# Row 1 — direct cue jumps
midi.map_note(channel=10, note=36, on_callback=goto_1,   name="cue 1 Red")
midi.map_note(channel=10, note=38, on_callback=goto_2,   name="cue 2 Blue")
midi.map_note(channel=10, note=42, on_callback=goto_3,   name="cue 3 Magenta")
midi.map_note(channel=10, note=46, on_callback=goto_4,   name="cue 4 Off")
# Row 2 — navigation + flash
midi.map_note(channel=10, note=50, on_callback=cue_back, name="BACK")
midi.map_note(channel=10, note=45, on_callback=cue_go,   name="GO")
midi.map_note(channel=10, note=51, on_callback=flash_on, off_callback=flash_off,
              name="Flash White (hold)")
midi.map_note(channel=10, note=49, on_callback=_stop_fx, name="FX Kill")

# Transport (ch=16, CC toggles)
midi.map_cc(channel=16, cc=118, callback=transport_rewind, name="Transport Rewind",
            soft_takeover=False)
midi.map_cc(channel=16, cc=117, callback=transport_go,     name="Transport GO",
            soft_takeover=False)
midi.map_cc(channel=16, cc=116, callback=transport_back,   name="Transport BACK",
            soft_takeover=False)

midi.print_maps()

# ── AI Engine ─────────────────────────────────────────────
ai = AIEngine(
    patch         = patch,
    prog          = prog,
    output_state  = output_state,
    fx_engine     = fx_engine,
    fade_engine   = fade_engine,
    stack_pool = stack_pool,
    fader_pool = fader_pool,
    color_pool = color_pool,
    dim_pool   = dim_pool,
    group_pool = group_pool,
    fx_pool    = fx_pool,
    attr_pools = _attr_pools,
    rate_pool  = rate_pool,
    size_pool  = size_pool,
    spread_pool = spread_pool,
    form_pool  = form_pool,
    # cmd_fn and log_fn wired after run_command / GUIEngine are defined below
)

# ── MIDI target registry ───────────────────────────────────
# All parameters that can be assigned to a knob/fader/pad
# via the GUI's MIDI learn panel.
# Format: "Display Name": (callback, soft_takeover, is_note)
#   soft_takeover=True  → physical must reach software value first (faders)
#   is_note=True        → hints to GUI this suits Note mappings
GUIEngine.target_registry = {
    "Grandmaster Dim":  (set_all_dim,      True,  False),
    "FX Rate":          (set_fx_rate,      False, False),
    "FX Size":          (set_fx_size,      False, False),
    "FX Spread":        (set_fx_spread,    False, False),
    "Transport GO":     (transport_go,     False, False),
    "Transport BACK":   (transport_back,   False, False),
    "Transport Rewind": (transport_rewind, False, False),
    "cue 1 Red":        (goto_1,           False, True),
    "cue 2 Blue":       (goto_2,           False, True),
    "cue 3 Magenta":    (goto_3,           False, True),
    "cue 4 Off":        (goto_4,           False, True),
    "GO":               (cue_go,           False, True),
    "BACK":             (cue_back,         False, True),
    "FX Kill":          (_stop_fx,         False, True),
    "Tap Tempo":          (tap_tempo,        False, True),
    # 4-tuple: (on_cb, soft_takeover, is_note, off_cb)
    "Flash White (hold)": (flash_on,       False, True, flash_off),
    **{f"speed Master {i}": (_make_set_speed_master(i), False, False)
       for i in range(1, SpeedMasterPool._DEFAULT_SLOTS + 1)},
}

# ── Save helpers — one call per category ──────────────────
def save_show():
    ShowFile.save_patch(patch)
    ShowFile.save_stacks(stack_pool)
    ShowFile.save_groups(group_pool)
    ShowFile.save_colors(color_pool)
    ShowFile.save_dims(dim_pool)
    ShowFile.save_midi(midi)
    ShowFile.save_fx(_fx_params)
    ShowFile.save_fx_pool(fx_pool)
    ShowFile.save_forms(form_pool)
    ShowFile.save_rate_pool(rate_pool)
    ShowFile.save_size_pool(size_pool)
    ShowFile.save_spread_pool(spread_pool)
    ShowFile.save_speed_masters(speed_master_pool)
    ShowFile.save_position_pool(position_pool)
    ShowFile.save_gobo_pool(gobo_pool)
    ShowFile.save_zoom_pool(zoom_pool)
    ShowFile.save_focus_pool(focus_pool)
    ShowFile.save_beam_pool(beam_pool)
    ShowFile.save_control_pool(control_pool)
    ShowFile.save_fader_pages(fader_pool)
    ShowFile.save_faders(fader_pool)
    ShowFile.save_osc_targets(osc)
    ShowFile.save_state(output_state, fader_pool, active_fader,
                        prog_time=_prog_time, fader_dim=_fader_dim[0])
    ShowFile.save_programmer(prog)


def save_show_as(name):
    """Copy current show files into studio_saves/<name>/."""
    import shutil as _sh
    if not name or not name.strip():
        return "SAVE AS: provide a show name"
    safe = "".join(c for c in name.strip() if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe:
        return "SAVE AS: invalid name"
    save_show()  # flush current state first
    dest = os.path.join(SAVES_DIR, safe)
    os.makedirs(dest, exist_ok=True)
    for fname in os.listdir(DATA_DIR):
        if fname.endswith('.json') and not fname.endswith('.bak'):
            _sh.copy2(os.path.join(DATA_DIR, fname), os.path.join(dest, fname))
    return f"show saved as '{safe}'  →  studio_saves/{safe}/"


def load_show_from(name):
    """Copy saved show files back into studio_data/ and reload all pools."""
    import shutil as _sh
    if not name or not name.strip():
        return "LOAD SHOW: provide a show name"
    src = os.path.join(SAVES_DIR, name.strip())
    if not os.path.isdir(src):
        # fuzzy match
        try:
            all_saves = [d for d in os.listdir(SAVES_DIR)
                         if os.path.isdir(os.path.join(SAVES_DIR, d))]
        except OSError:
            return "LOAD SHOW: no saves directory found — use SAVE AS first"
        matches = [s for s in all_saves if name.strip().lower() in s.lower()]
        if len(matches) == 1:
            src = os.path.join(SAVES_DIR, matches[0])
            name = matches[0]
        elif matches:
            return f"LOAD SHOW: ambiguous — matches: {', '.join(matches)}"
        else:
            return f"LOAD SHOW: '{name}' not found — LIST SHOWS to see saves"
    for fname in os.listdir(src):
        if fname.endswith('.json'):
            _sh.copy2(os.path.join(src, fname), os.path.join(DATA_DIR, fname))
    # Reload pools from newly-copied files (each loader reads from DATA_DIR itself)
    stack_pool.stacks.clear()
    ShowFile.load_stacks(stack_pool, cue_pool)
    group_pool.groups.clear()
    ShowFile.load_groups(group_pool)
    color_pool.presets.clear()
    ShowFile.load_colors(color_pool)
    dim_pool.presets.clear()
    ShowFile.load_dims(dim_pool)
    fx_pool.presets.clear()
    ShowFile.load_fx_pool(fx_pool)
    # Clear only custom form slots (builtins 1-4 are never saved to file)
    for _fid in [k for k in form_pool.forms if k >= FormPool.FIRST_CUSTOM_SLOT]:
        del form_pool.forms[_fid]
    ShowFile.load_forms(form_pool)
    rate_pool.presets.clear()
    ShowFile.load_rate_pool(rate_pool)
    size_pool.presets.clear()
    ShowFile.load_size_pool(size_pool)
    spread_pool.presets.clear()
    ShowFile.load_spread_pool(spread_pool)
    speed_master_pool.masters.clear()
    for i in range(1, SpeedMasterPool._DEFAULT_SLOTS + 1):
        speed_master_pool.masters[i] = SpeedMaster(i)
    ShowFile.load_speed_masters(speed_master_pool)
    for _pool in (position_pool, gobo_pool, zoom_pool, focus_pool, beam_pool, control_pool):
        _pool.presets.clear()
    ShowFile.load_position_pool(position_pool)
    ShowFile.load_gobo_pool(gobo_pool)
    ShowFile.load_zoom_pool(zoom_pool)
    ShowFile.load_focus_pool(focus_pool)
    ShowFile.load_beam_pool(beam_pool)
    ShowFile.load_control_pool(control_pool)
    ShowFile.load_fader_pages(fader_pool)
    ShowFile.load_faders(fader_pool, stack_pool)
    ShowFile.load_state(output_state, fader_pool, stack_pool,
                        active_fader, prog_time=_prog_time, fader_dim=_fader_dim)
    # OSC targets and global FX rate/size/spread/fade defaults are saved every
    # SAVE (ShowFile.save_osc_targets / save_fx) and loaded at startup, but were
    # missing here — unlike patch/MIDI (which need a real restart to re-init
    # hardware/threads), neither has a reason to stay stale after a LOAD SHOW.
    osc._clients.clear()
    ShowFile.load_osc_targets(osc)
    ShowFile.load_fx(_fx_params)
    return f"show '{name}' loaded — restart may be needed for patch/midi changes"


def list_shows():
    """List all saved shows in studio_saves/."""
    try:
        saves = [d for d in sorted(os.listdir(SAVES_DIR))
                 if os.path.isdir(os.path.join(SAVES_DIR, d))]
    except OSError:
        return "no saves yet — use: save as <name>"
    if not saves:
        return "no saved shows — use: save as <name>"
    import datetime as _dt
    lines = ["Saved shows:"]
    for s in saves:
        mtime = os.path.getmtime(os.path.join(SAVES_DIR, s))
        ts = _dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"  {s}  [{ts}]")
    return "\n".join(lines)


def export_presets(what='all'):
    """
    Bundle presets into a single JSON file in studio_data/.
    what: 'all' | 'colors' | 'dims' | 'fx' | 'forms' | 'rates' | 'sizes' | 'spreads'
    Returns the output path on success.
    """
    import datetime as _dt
    bundle = {"version": ShowFile.VERSION,
              "exported": _dt.datetime.now().isoformat()}
    what_l = what.lower()

    if what_l in ('all', 'colors'):
        bundle['colors'] = {}
        for pid, p in color_pool.presets.items():
            bundle['colors'][str(pid)] = {'name': p.name, 'red': p.red,
                                           'green': p.green, 'blue': p.blue}
    if what_l in ('all', 'dims'):
        bundle['dims'] = {}
        for pid, p in dim_pool.presets.items():
            bundle['dims'][str(pid)] = {'name': p.name, 'level': p.level}
    if what_l in ('all', 'fx'):
        doc = _read_file(ShowFile.FX_POOL)
        if doc:
            bundle['fx_pool'] = doc.get('fx_presets', {})
    if what_l in ('all', 'forms'):
        doc = _read_file(ShowFile.FORMS)
        if doc:
            bundle['forms'] = doc.get('forms', {})
    if what_l in ('all', 'rates'):
        doc = _read_file(ShowFile.RATES)
        if doc:
            bundle['rate_pool'] = doc.get('rate_presets', {})
    if what_l in ('all', 'sizes'):
        doc = _read_file(ShowFile.SIZES)
        if doc:
            bundle['size_pool'] = doc.get('size_presets', {})
    if what_l in ('all', 'spreads'):
        doc = _read_file(ShowFile.SPREADS)
        if doc:
            bundle['spread_pool'] = doc.get('spread_presets', {})

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(DATA_DIR, f"preset_export_{ts}.json")
    with open(out_path, 'w') as f:
        json.dump(bundle, f, indent=2)
    cats = [k for k in ('colors','dims','fx_pool','forms','rate_pool','size_pool','spread_pool')
            if k in bundle]
    return f"exported {', '.join(cats)} → {os.path.basename(out_path)}"


def import_presets(path):
    """
    Merge a preset bundle JSON into the live pools.
    Existing presets are overwritten only where the bundle has data.
    """
    if not os.path.isabs(path):
        # try relative to DATA_DIR first, then cwd
        candidate = os.path.join(DATA_DIR, path)
        if os.path.exists(candidate):
            path = candidate
    if not os.path.exists(path):
        return f"IMPORT PRESETS: file not found — {path}"
    try:
        with open(path) as f:
            bundle = json.load(f)
    except Exception as e:
        return f"IMPORT PRESETS: bad JSON — {e}"

    imported = []
    if 'colors' in bundle:
        for pid_s, d in bundle['colors'].items():
            pid = int(pid_s)
            p = color_pool.presets.setdefault(pid, type('ColorPreset', (), {
                'preset_id': pid, 'name': '', 'red': 0, 'green': 0, 'blue': 0})())
            p.name = d.get('name', ''); p.red = d.get('red', 0)
            p.green = d.get('green', 0); p.blue = d.get('blue', 0)
        ShowFile.save_colors(color_pool)
        imported.append(f"{len(bundle['colors'])} colors")
    if 'dims' in bundle:
        for pid_s, d in bundle['dims'].items():
            pid = int(pid_s)
            p = dim_pool.presets.setdefault(pid, type('DimPreset', (), {
                'preset_id': pid, 'name': '', 'level': 1.0})())
            p.name = d.get('name', ''); p.level = d.get('level', 1.0)
        ShowFile.save_dims(dim_pool)
        imported.append(f"{len(bundle['dims'])} dims")
    if 'fx_pool' in bundle:
        count = 0
        for pid_s, pdata in bundle['fx_pool'].items():
            pid    = int(pid_s)
            preset = FXPreset(pid, pdata.get("name", f"FX {pid}"))
            for ld in pdata.get("layers", []):
                _mirror, _cluster, _order = _fx_grouping_compat(ld)
                preset.add_layer(
                    ld["waveform"], ld["channel"],
                    bpm=ld.get("bpm", ld.get("rate_bpm", 60.0)),
                    size=ld.get("size", 100.0), spread=ld.get("spread", 0.0),
                    phase_offset=ld.get("phase_offset", 0.0),
                    form_id=ld.get("form_id"), rate_id=ld.get("rate_id"),
                    size_id=ld.get("size_id"), spread_id=ld.get("spread_id"),
                    dim_id=ld.get("dim_id"), color_id=ld.get("color_id"),
                    group_id=ld.get("group_id"), speed_id=ld.get("speed_id"),
                    block_size=ld.get("block_size", 1),
                    order=_order, direction=ld.get("direction", "forward"),
                    mirror=_mirror, cluster=_cluster,
                    low=ld.get("low", 0.0),
                    target_scope=ld.get("target_scope"),
                )
            fx_pool.store(pid, preset)
            count += 1
        ShowFile.save_fx_pool(fx_pool)
        imported.append(f"{count} fx")
    if 'forms' in bundle:
        count = 0
        for fid_s, fdata in bundle['forms'].items():
            fid = int(fid_s)
            if fid < FormPool.FIRST_CUSTOM_SLOT:
                continue
            form = FormPreset(fid, fdata.get("name", f"form {fid}"),
                              fdata.get("form_type", "breakpoints"),
                              breakpoints=fdata.get("breakpoints", []))
            form_pool.store(fid, form)
            count += 1
        if count:
            ShowFile.save_forms(form_pool)
            imported.append(f"{count} forms")
    if 'rate_pool' in bundle:
        count = 0
        for pid_s, d in bundle['rate_pool'].items():
            pid = int(pid_s)
            rate_pool.store(pid, RatePreset(pid, d.get("name", f"rate {pid}"),
                                            d.get("bpm", 60.0)))
            count += 1
        ShowFile.save_rate_pool(rate_pool)
        imported.append(f"{count} rates")
    if 'size_pool' in bundle:
        count = 0
        for pid_s, d in bundle['size_pool'].items():
            pid = int(pid_s)
            size_pool.store(pid, SizePreset(pid, d.get("name", f"size {pid}"),
                                            d.get("size", 100.0)))
            count += 1
        ShowFile.save_size_pool(size_pool)
        imported.append(f"{count} sizes")
    if 'spread_pool' in bundle:
        count = 0
        for pid_s, d in bundle['spread_pool'].items():
            pid = int(pid_s)
            spread_pool.store(pid, SpreadPreset(pid, d.get("name", f"spread {pid}"),
                                                d.get("spread", 0.0)))
            count += 1
        ShowFile.save_spread_pool(spread_pool)
        imported.append(f"{count} spreads")
    if not imported:
        return "IMPORT PRESETS: nothing imported (bundle has no recognized preset categories)"
    return "imported: " + ", ".join(imported)

# ── MIDI restore (must happen after target_registry is built) ──
_midi_doc = _read_file(ShowFile.MIDI)
if _midi_doc:
    # Pre-generate callbacks for any dynamic "GO stk N CUE M" / "fdr N Flash"
    # targets saved in midi.json — these aren't in the static target_registry
    # dict (fader/stack numbers aren't known ahead of time), so they're
    # regenerated by name pattern on load, same as when they were first learned.
    import re as _re_midi
    for _entry in _midi_doc.get("midi_note", []):
        _name = _entry.get("target", "")
        if _name not in GUIEngine.target_registry:
            _m = _re_midi.match(r'^GO stk (\d+) CUE (\d+(?:\.\d+)?)$', _name)
            if _m:
                _cs, _cue = int(_m.group(1)), float(_m.group(2))
                # run_command is defined later in studio_project.py — these
                # wrapper functions defer the import to call time (when the
                # MIDI target actually fires), not lambda-definition time.
                def _make_go(c=f"GO stk {_cs} CUE {_cue}"):
                    def _go():
                        from __main__ import run_command
                        return run_command(c)
                    return _go
                GUIEngine.target_registry[_name] = (_make_go(), False, True)
                continue
            _mf = _re_midi.match(r'^fdr (\d+) Flash$', _name)
            if _mf:
                _ex_n = int(_mf.group(1))
                def _make_flash(on_c=f"FADER {_ex_n} flash on", off_c=f"FADER {_ex_n} flash off"):
                    def _on():
                        from __main__ import run_command
                        return run_command(on_c)
                    def _off():
                        from __main__ import run_command
                        return run_command(off_c)
                    return _on, _off
                _on_cb, _off_cb = _make_flash()
                GUIEngine.target_registry[_name] = (_on_cb, False, True, _off_cb)
    ShowFile.load_midi(_midi_doc, midi, GUIEngine.target_registry)
else:
    save_show()   # first run — write all files now

midi.print_maps()

# ── Command line router ────────────────────────────────────
# Handles both console-level commands and programmer commands.
# Returns a result string that the GUI logs below the input.
#
# Console commands:
#   GO / BACK / GOTO <n>
#   RECORD CUE <n> ["<name>"] [FADE <t>]
#   SAVE
#   CUES  — list current stack
#
# Everything else is forwarded to prog.execute() (programmer).
# programmer syntax:  <fixtures> AT <value>  |  CLEAR  |  etc.

import re as _re

def _name_after(raw_cmd, skip_token_count):
    """
    Extract a name from a command string after skipping skip_token_count words.
    Quoted string takes priority: RECORD GROUP 1 "All Tubes" → "All Tubes"
    Without quotes: RECORD GROUP 1 All Tubes → "All Tubes"
    Returns "" if nothing left after skipping.
    """
    m = _re.search(r'"([^"]*)"', raw_cmd)
    if m:
        return m.group(1).strip()
    parts = raw_cmd.split(None, skip_token_count)
    if len(parts) > skip_token_count:
        return parts[skip_token_count].strip()
    return ""

def _apply_timing_edit(cue, raw_str):
    """Write timing keywords from raw_str onto cue in-place. No programmer needed.

    Supported keywords (all case-insensitive):
      FADE / INFADE / OUTFADE   — cue crossfade time (all three are synonyms here)
      DELAY                     — global pre-wait before fade starts
      CFADE / CINFADE           — colour-group fade override
      DFADE / DINFADE           — dim-group fade override
      CDELAY / CDDELAY          — colour-group delay override
      DDELAY / DDDELAY          — dim-group delay override
      FXOUTFADE                 — FX layer outfade when this cue fires (overrides auto)
    """
    up = raw_str.upper()
    def _get(*kws):
        """Return first match across multiple keyword aliases."""
        import re as _r
        for kw in kws:
            m = _r.search(rf'\b{kw}\s+([\d.]+)', up)
            if m:
                return float(m.group(1))
        return None

    # Global fade: FADE / INFADE / OUTFADE are all synonyms for crossfade time
    v = _get('FADE', 'INFADE', 'OUTFADE')
    if v is not None:
        cue.fade_time = v

    v = _get('DELAY')
    if v is not None:
        cue.delay_time = v

    v = _get('FOLLOW')
    if v is not None:
        cue.follow_time = v

    # FX outfade override: how long old FX layers take to fade out when this cue fires
    v = _get('FXOUTFADE')
    if v is not None:
        cue.fx_outfade = None if v == 0.0 else v  # 0 resets to auto

    for grp, kw_f, kw_d in [
        ('colour', ('CFADE', 'CINFADE'), ('CDELAY',)),
        ('dim',    ('DFADE', 'DINFADE'), ('DDELAY',)),
    ]:
        vf = _get(*kw_f)
        vd = _get(*kw_d)
        if vf is not None: cue.fade_times[grp]  = vf
        if vd is not None: cue.delay_times[grp] = vd


def _preset_live_push(preset_type, preset_id):
    """
    After updating a preset, push the new values into any fader currently
    playing a cue that references that preset.
    preset_type: 'color', 'dim', 'fx', or an attr name ('position', 'gobo', etc.)
    preset_id:   int preset slot number
    """
    for ex in fader_pool.faders.values():
        if not ex.is_active or not ex.stack:
            continue
        cue_num = ex.stack.current
        if cue_num is None:
            continue
        cue = ex.stack.cues.get(cue_num)
        if not cue:
            continue

        if preset_type == 'color':
            p = color_pool.get(preset_id)
            if not p:
                continue
            for fid, vals in cue.data.items():
                if '.' in fid or vals.get('color_ref') != preset_id:
                    continue
                master = patch.get(int(fid)) if fid.isdigit() else None
                if not master:
                    continue
                for sub in master.all_subs():
                    sfid = str(sub.fixture_id)
                    ex.layer.setdefault(sfid, {}).update(
                        {'red': p.red, 'green': p.green, 'blue': p.blue}
                    )

        elif preset_type == 'dim':
            p = dim_pool.get(preset_id)
            if not p:
                continue
            for fid, vals in cue.data.items():
                if '.' in fid or vals.get('dim_ref') != preset_id:
                    continue
                ex.layer.setdefault(fid, {})['dim'] = p.level

        elif preset_type == 'fx':
            affected = any(
                any(_ld.get('fx_preset_ref') == preset_id
                    for _ld in vals.get('fx', []))
                for fid, vals in cue.data.items()
                if '.' not in fid
            )
            if affected:
                ex._start_cue_fx(cue, patch, default_infade=0.0, default_outfade=0.0)

        else:
            # generic attribute pool
            ref_key = f"{preset_type}_ref"
            ap = _attr_pools.get(preset_type)
            if not ap:
                continue
            p = ap.get(preset_id)
            if not p:
                continue
            for fid, vals in cue.data.items():
                if '.' in fid or vals.get(ref_key) != preset_id:
                    continue
                src = p.data.get(fid, {})
                if src:
                    ex.layer.setdefault(fid, {}).update(src)




__all__ = [
    "LIGHTFORM_CUE_MAP", "STUDIO_DRY_RUN", "STUDIO_HEADLESS", "_NET_BIND", "_NET_UNIVERSES", "_active_fader",
    "_active_stack", "_apply_fixture_defaults", "_apply_timing_edit", "_attr_pools", "_blackout_saved_level", "_cs_loaded",
    "_fader_dim", "_fixture_defaults", "_fx_params", "_macro_play_stack", "_macro_recording", "_make_set_speed_master",
    "_midi_doc", "_name_after", "_on_cue_fire", "_osc_cmd", "_osc_fader", "_osc_key",
    "_preset_live_push", "_prog_fx_ids", "_prog_snapshots", "_prog_time", "_start_magenta_sine", "_stop_fx",
    "_stop_prog_fx_preview", "_tap_times", "active_fader", "active_fx", "ai", "all_subs",
    "audio_engine", "audio_mapper", "beam_pool", "color_pool", "control_pool", "cs1",
    "cue_back", "cue_go", "cue_pool", "cue_reload", "dim_pool", "export_presets",
    "fade_engine", "fader_pool", "flash_off", "flash_on", "focus_pool", "form_pool",
    "fx_engine", "fx_pool", "gobo_pool", "goto_1", "goto_2", "goto_3",
    "goto_4", "goto_cue", "group_pool", "import_presets", "library", "list_shows",
    "load_show_from", "macro_pool", "midi", "network", "osc", "output_state",
    "patch", "position_pool", "prog", "rate_pool", "save_show", "save_show_as",
    "set_all_dim", "set_fx_rate", "set_fx_size", "set_fx_spread", "size_pool", "speed_master_pool",
    "spread_pool", "stack_pool", "tap_tempo", "transport_back", "transport_go", "transport_rewind",
    "zoom_pool",
]
