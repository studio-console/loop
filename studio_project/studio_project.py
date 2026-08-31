# ============================================================
# STUDIO CONSOLE - Core Object Model
# Block 1: Fixture Profile System + SubFixture + MasterFixture
# ============================================================

import os
import json
import copy
import re as _re

# Load studio_data/.env (gitignored — never committed) into the environment
# before anything else runs. Must happen before any studio_console import:
# state.py constructs AIEngine at import time, which reads ANTHROPIC_API_KEY
# from os.environ in its own __init__ — by the time that happens, whatever
# .env would have set needs to already be there. os.environ.setdefault()
# means a real shell-exported value always wins over the file, same as
# every dotenv-style loader.
def _load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)

_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'studio_data', '.env'))

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
from studio_console.commands._shared import (
    _record_cue_into, _prog_fx_stop, _prog_fx_start, _prog_fx_rebuild,
)

from studio_console.commands import run_command


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

if os.environ.get('STUDIO_PYTEST_COLLECT'):
    # Used by studio_console/tests/test_smoke_pytest.py, via
    # runpy.run_path(..., run_name="__main__"), to harvest this
    # module's fully-wired globals (gui, run_command, every engine
    # singleton) with zero duplicated construction logic — same `gui`
    # a real launch would build, minus the smoke test / GUI event loop
    # / shutdown calls below, so the pytest fixture controls those
    # itself. Doesn't affect STUDIO_HEADLESS or normal launches — this
    # branch is unreachable unless something explicitly opts in.
    pass
elif STUDIO_HEADLESS:
    # tests_smoke.py is imported lazily, only when actually running
    # headless — normal GUI launches never need it. GUIEngine is
    # already fully defined and `gui` already constructed by this
    # point, so tests_smoke.py's own `from __main__ import GUIEngine`
    # resolves safely.
    from studio_console.tests_smoke import run_smoke_test
    run_smoke_test(gui)
else:
    gui.build()   # build all widgets (main thread)
    gui.run()     # hand control to DearPyGui — blocks until window closed

    # gui.run() has already saved the popup layout + show (see its own
    # tail) before returning here, so by this point the operator's work
    # is safe regardless of what happens below — only driver cleanup is
    # left. A hardware driver's stop() (sACN sender, MIDI port close,
    # audio stream teardown) occasionally not returning promptly on a
    # real machine (network/OS/hardware specifics this dev environment
    # can't reproduce — no display, limited networking) shouldn't leave
    # the whole process hanging after the operator has already closed
    # the window. Force-exit after a grace period generous enough for
    # normal cleanup if the shutdown below hasn't finished by then.
    def _force_exit_if_stuck():
        time.sleep(4.0)
        os._exit(0)
    threading.Thread(target=_force_exit_if_stuck, daemon=True).start()

    midi.stop()
    network.stop()
    fade_engine.stop()
    fx_engine.stop()
    audio_mapper.stop()
    audio_engine.stop()

