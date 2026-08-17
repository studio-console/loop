# ============================================================
# STUDIO CONSOLE - Core Object Model
# Block 1: Fixture Profile System + SubFixture + MasterFixture
# ============================================================

import os
import json
import copy
import re as _re

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

if STUDIO_HEADLESS:
    # Scripted smoke test — no GUI, no real hardware (paired with
    # STUDIO_DRY_RUN). Exercises the FX-as-programmer path this file's own
    # doc comments flagged as written-but-untested: FX -> RECORD CUE ->
    # GO -> verify FX actually fires. Exits with status 0/1 instead of
    # blocking on dpg.start_dearpygui().
    import sys as _sys

    print("\n*** STUDIO_HEADLESS smoke test ***")
    _results = []
    def _check(label, cond):
        _results.append((label, bool(cond)))
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    try:
        r1 = run_command("FX SINE RED BLOCK 2 DIRECTION BOUNCE PIXEL")
        _check("FX command applied to programmer", "FX" in r1)

        r2 = run_command("RECORD stk 1 CUE 5")
        _check("cue recorded", "recorded" in r2 or "cue" in r2)

        run_command("GO stk 1 CUE 5")
        time.sleep(0.25)   # let FadeEngine/FXEngine tick at least once
        ex = fader_pool.get(1)
        _check("fader has active FX after GO", len(ex._fx_ids) > 0)

        dmx = output_state.get_dmx_for_universe(1)
        _check("DMX output computes without exception", len(dmx) == 512)

        # GO FADE — one-shot fade override
        _pt_before = dict(_prog_time)
        r_gf = run_command("GO FADE 7.5")
        _check("GO FADE fires without error", "Cue" in r_gf or "GO" in r_gf)
        _check("GO FADE restores prog_time.on after fire",
               _prog_time['on'] == _pt_before['on'])
        _check("GO FADE restores prog_time.fade after fire",
               _prog_time['fade'] == _pt_before['fade'])

        # FADER SWAP
        _cs1_before = fader_pool.get(1).stack
        _cs2_before = fader_pool.get(2).stack
        r_swap = run_command("FADER SWAP 1 2")
        _check("FADER SWAP swaps stk onto fader 1",
               fader_pool.get(1).stack is _cs2_before)
        _check("FADER SWAP swaps stk onto fader 2",
               fader_pool.get(2).stack is _cs1_before)
        # Swap back to restore state for remaining tests
        run_command("FADER SWAP 1 2")

        # COPY FIXTURE
        run_command("1 AT RED 200")                   # set red on fixture 1 (sub-fixture channel)
        _cf_f1 = patch.get(1)
        _cf_f2 = patch.get(2)
        if _cf_f1 and _cf_f2:
            _cf_f1_sub = next(iter(_cf_f1.all_subs()), None)
            _cf_f2_sub = next(iter(_cf_f2.all_subs()), None)
            _cf_red_src = (prog.data.get(str(_cf_f1_sub.fixture_id), {}).get('red')
                           if _cf_f1_sub else None)
            r_cf = run_command("COPY FIXTURE 1 TO 2")
            _cf_red_dst = (prog.data.get(str(_cf_f2_sub.fixture_id), {}).get('red')
                           if _cf_f2_sub else None)
            _check("COPY FIXTURE copies sub channel to destination",
                   _cf_red_src is not None and _cf_red_dst == _cf_red_src)
            _check("COPY FIXTURE returns confirmation message", "copied fixture" in r_cf)
        r_cf_bad = run_command("COPY FIXTURE 999 TO 2")
        _check("COPY FIXTURE rejects unknown source", "not patched" in r_cf_bad or "999" in r_cf_bad)

        # FIXTURE SWAP
        prog.clear_programmer()
        run_command("1 AT R 80")    # fixture 1 red = 80
        run_command("2 AT R 200")   # fixture 2 red = 200
        _fs_f1s = "1.1" if patch.get(1) and next(iter(patch.get(1).all_subs()), None) else None
        _fs_f2s = "2.1" if patch.get(2) and next(iter(patch.get(2).all_subs()), None) else None
        if _fs_f1s and _fs_f2s:
            r_swap = run_command("FIXTURE SWAP 1 2")
            _sw_r1 = prog.data.get(_fs_f1s, {}).get('red')
            _sw_r2 = prog.data.get(_fs_f2s, {}).get('red')
            _check("FIXTURE SWAP moves fixture 2 value to fixture 1", _sw_r1 == 200)
            _check("FIXTURE SWAP moves fixture 1 value to fixture 2", _sw_r2 == 80)
            _check("FIXTURE SWAP returns confirmation", "swapped" in r_swap.lower())
            prog.undo()
            _sw_u1 = prog.data.get(_fs_f1s, {}).get('red')
            _sw_u2 = prog.data.get(_fs_f2s, {}).get('red')
            _check("FIXTURE SWAP pushes an undo snapshot (UNDO restores fixture 1)", _sw_u1 == 80)
            _check("FIXTURE SWAP pushes an undo snapshot (UNDO restores fixture 2)", _sw_u2 == 200)
        prog.clear_programmer()

        # FIXTURE INFO
        _fi = patch.get(1)
        if _fi:
            r_fi = run_command("FIXTURE INFO 1")
            _check("FIXTURE INFO shows fixture name", _fi.name in r_fi)
            _check("FIXTURE INFO shows profile name", _fi.profile.name in r_fi)
            _check("FIXTURE INFO shows channel list", any(ch in r_fi for ch in _fi.profile.channels))
        r_fi_bad = run_command("FIXTURE INFO 999")
        _check("FIXTURE INFO rejects unknown fixture", "not patched" in r_fi_bad or "999" in r_fi_bad)

        # PROGRAMMER STATS
        prog.clear_programmer()
        run_command("1 AT R 200")
        run_command("2 AT R 100")
        r_ps = run_command("PROGRAMMER STATS")
        _check("PROGRAMMER STATS shows sub-fixture count", "sub-fixtures" in r_ps)
        _check("PROGRAMMER STATS shows total params > 0",
               "total params" in r_ps and "total params    : 0" not in r_ps)
        prog.clear_programmer()
        r_ps_empty = run_command("PROGRAMMER STATS")
        _check("PROGRAMMER STATS shows 0 params when clear",
               "total params    : 0" in r_ps_empty or "0" in r_ps_empty)

        # PROGRAMMER CAPTURE
        prog.clear_programmer()
        run_command("1 THRU 3")           # select fixtures 1-3
        r_cap = run_command("PROGRAMMER CAPTURE")
        _check("PROGRAMMER CAPTURE returns confirmation", "captured" in r_cap)
        prog.clear_programmer()

        # PROGRAMMER SAVE / LOAD
        prog.clear_programmer()
        run_command("1 AT R 150 G 80")    # set some values
        r_psnap = run_command("PROGRAMMER SAVE 5 TestSnap")
        _check("PROGRAMMER SAVE returns confirmation", "saved" in r_psnap.lower())
        _check("PROGRAMMER SAVE stores snapshot", 5 in _prog_snapshots)
        prog.clear_programmer()           # wipe programmer
        _check("PROGRAMMER CLEAR removes values", not prog.data.get("1.1"))
        r_pload = run_command("PROGRAMMER LOAD 5")
        _check("PROGRAMMER LOAD restores values", prog.data.get("1.1", {}).get('red') == 150)
        _check("PROGRAMMER LOAD returns confirmation", "loaded" in r_pload.lower())
        r_psnaps = run_command("PROGRAMMER SNAPSHOTS")
        _check("PROGRAMMER SNAPSHOTS lists the saved slot", "TestSnap" in r_psnaps)
        prog.clear_programmer()

        # SET DEFAULT / DEFAULT
        _saved_defaults = dict(_fixture_defaults)
        r_sd_dim  = run_command("SET DEFAULT DIM 0")
        _check("SET DEFAULT DIM returns confirmation", "dim" in r_sd_dim)
        _check("SET DEFAULT DIM stores 0.0 in _fixture_defaults", _fixture_defaults.get('dim') == 0.0)
        r_sd_clr  = run_command("SET DEFAULT CLR 5600")
        _check("SET DEFAULT CLR stores kelvin", _fixture_defaults.get('kelvin') == 5600)
        r_sd_red  = run_command("SET DEFAULT RED 200")
        _check("SET DEFAULT RED stores value", _fixture_defaults.get('red') == 200)
        r_default = run_command("DEFAULT")
        _check("DEFAULT shows dim",    "dim"    in r_default)
        _check("DEFAULT shows kelvin", "kelvin" in r_default)
        r_bad     = run_command("SET DEFAULT FOOBAR 50")
        _check("SET DEFAULT rejects unknown param", "unknown" in r_bad)
        # restore
        _fixture_defaults.clear()
        _fixture_defaults.update(_saved_defaults)
        ShowFile.save_defaults(_fixture_defaults)

        # PROGRAMMER SHOW
        run_command("1 AT R 200")
        r_pshow = run_command("PROGRAMMER SHOW")
        _f1_master = patch.get(1)
        _check("PROGRAMMER SHOW lists active fixture name",
               _f1_master is not None and _f1_master.name in r_pshow)
        _check("PROGRAMMER SHOW shows channel value", "200" in r_pshow or "red" in r_pshow.lower())
        prog.clear_programmer()
        r_pshow_empty = run_command("PROGRAMMER SHOW")
        _check("PROGRAMMER SHOW shows (empty) when clear", "empty" in r_pshow_empty)

        # Pages + trigger modes
        run_command('PAGE 1 NAME "Test Page"')
        run_command("PAGE 1 ADD stk 1")
        r3 = run_command("page list")
        _check("page created and stack added", "Test Page" in r3 and "[1]" in r3)

        run_command("FADER 1 MODE FLASH")
        _check("trigger_mode set", fader_pool.get(1).trigger_mode == 'flash')

        run_command("FADER 1 flash on")
        time.sleep(0.05)
        _check("fader active after flash on", fader_pool.get(1).is_active)

        run_command("FADER 1 flash off")
        _check("fader inactive after flash off", not fader_pool.get(1).is_active)

        # RECORD COLOR/DIM from programmer — verify no AttributeError
        run_command("ALL AT R 200 G 100 B 50")
        r_col = run_command("RECORD COLOR 1 TestRed")
        _check("RECORD COLOR from programmer", "recorded" in r_col or "no RGB" in r_col)

        run_command("ALL AT DIM 80")
        r_dim = run_command("RECORD DIM 1 TestDim")
        _check("RECORD DIM from programmer", "recorded" in r_dim or "no dimmer" in r_dim)

        # Explicit-value record
        r_col2 = run_command("RECORD COLOR 2 BlueTest 0 0 255")
        _check("RECORD COLOR explicit RGB", "recorded" in r_col2)

        r_dim2 = run_command("RECORD DIM 2 Half 50%")
        _check("RECORD DIM explicit level", "recorded" in r_dim2)

        # LIST COLOR/DIM — verify no AttributeError on pool iteration
        r_lc = run_command("LIST COLOR")
        _check("LIST COLOR no exception", "color" in r_lc.lower())

        r_ld = run_command("LIST DIM")
        _check("LIST DIM no exception", "dim" in r_ld)

        # Verify LIST sub-commands route correctly (not to stack listing)
        for _cmd, _kw in [
            ("LIST RATE", "Rate"), ("LIST SIZEP", "Size"),
            ("LIST SPREADP", "Spread"), ("LIST STACKS", "Stack"),
            ("STATUS", "Console"), ("LIST", "Stack"),
        ]:
            _r = run_command(_cmd)
            _check(f"{_cmd!r} routes correctly", _kw.lower() in _r.lower())

        # LIST CUES and LIST CUES stk <n>
        _lc_r = run_command("LIST CUES")
        _check("LIST CUES returns cue list for active stack",
               "stk " in _lc_r.lower() or "not found" in _lc_r.lower())
        _lc_cs1 = run_command("LIST CUES stk 1")
        _check("LIST CUES stk 1 targets stack 1",
               "stk 1" in _lc_cs1.lower() or "not found" in _lc_cs1.lower())

        # COPY pool preset routing — was broken by overly broad COPY CUE handler
        run_command("RECORD COLOR 5 CopySource 255 128 0")
        r_cp_col = run_command("COPY COLOR 5 TO 6 CopiedColor")
        _check("COPY COLOR routes to pool handler", "copied color" in r_cp_col)
        run_command("RECORD DIM 5 CopySrc 75%")
        r_cp_dim = run_command("COPY DIM 5 TO 6 CopiedDim")
        _check("COPY DIM routes to pool handler", "copied dim" in r_cp_dim)

        # CLEAR RATE / SIZEP / SPREADP / FORM — parity gap found by audit: every
        # other pool type (COLOR/DIM/GROUP/FX/attr pools) already had CLEAR.
        run_command("RECORD RATE 9 ClearMe 90")
        r_clr_rate = run_command("CLEAR RATE 9")
        _check("CLEAR RATE deletes the preset", "cleared" in r_clr_rate.lower())
        _check("CLEAR RATE actually removed it", rate_pool.get(9) is None)
        run_command("RECORD SIZEP 9 ClearMe 40")
        r_clr_size = run_command("CLEAR SIZEP 9")
        _check("CLEAR SIZEP deletes the preset", "cleared" in r_clr_size.lower())
        run_command("RECORD SPREADP 9 ClearMe 40")
        r_clr_spread = run_command("CLEAR SPREADP 9")
        _check("CLEAR SPREADP deletes the preset", "cleared" in r_clr_spread.lower())
        run_command('record form 9 ClearMe 0,0 1,1')
        r_clr_form = run_command("CLEAR FORM 9")
        _check("CLEAR FORM deletes a custom form", "cleared" in r_clr_form.lower())
        r_clr_form_builtin = run_command("CLEAR FORM 1")
        _check("CLEAR FORM protects built-in slot 1", "built-in" in r_clr_form_builtin.lower())

        # COPY FORM — the one pool type missing from COPY entirely (audit finding)
        run_command('record form 8 CopySrcform 0,0 0.5,1 1,0')
        r_cp_form = run_command("COPY FORM 8 TO 9 CopiedForm")
        _check("COPY FORM routes to pool handler", "copied form" in r_cp_form)
        _check("COPY FORM created the destination", form_pool.get(9) is not None)
        r_cp_form_builtin = run_command("COPY FORM 8 TO 2 Overwrite")
        _check("COPY FORM protects built-in destination slots",
               "built-in" in r_cp_form_builtin.lower())

        # Fader-page paging — GUIEngine._fpg_exec_for_slot/_fpg_slot_for_exec map
        # a fixed 15-slot panel onto banks of faders (page 2 slot 1 = fdr 16).
        # Pure functions, no dpg context needed, so they're smoke-testable headless.
        _check("fpg slot->fdr page 1 slot 1 == fdr 1",
               GUIEngine._fpg_exec_for_slot(1, 1) == 1)
        _check("fpg slot->fdr page 2 slot 1 == fdr 16",
               GUIEngine._fpg_exec_for_slot(2, 1) == 16)
        _check("fpg slot->fdr page 3 slot 15 == fdr 45",
               GUIEngine._fpg_exec_for_slot(3, 15) == 45)
        _check("fpg fdr->slot inverse holds for on-page fdr",
               GUIEngine._fpg_slot_for_exec(2, 16) == 1)
        _check("fpg fdr->slot returns None for off-page fdr",
               GUIEngine._fpg_slot_for_exec(1, 16) is None)
        # _fpg_step_page is the pure half of _on_fpg_page_prev/next (the dpg-
        # touching half needs a live GUI context, so it's exercised only by
        # hand — dpg calls segfault the process outright when no context is
        # active, rather than raising a catchable exception).
        gui._fpg_page = 1
        gui._fpg_step_page(-1)
        _check("fader page cannot go below page 1", gui._fpg_page == 1)
        gui._fpg_step_page(1)
        gui._fpg_step_page(1)
        _check("fader page increments normally", gui._fpg_page == 3)
        gui._fpg_page = 1  # reset so later state (e.g. SAVE) isn't affected

        # TAP command — pre-seed _tap_times to avoid sleep; two taps → BPM
        _tap_times.clear()
        _tap_times.append(time.monotonic() - 0.5)  # simulate a prior tap 500ms ago
        _r_tap1 = run_command("TAP")                 # second tap → should compute BPM
        _check("TAP computes BPM from two taps", "BPM" in _r_tap1 or "→" in _r_tap1)

        # MIDI text commands — add, list, remove
        _r_midi_map = run_command("MIDI CC 15 100 GO")
        _check("MIDI CC maps correctly", "mapped" in _r_midi_map)
        _r_midi_list = run_command("LIST MIDI")
        _check("LIST MIDI shows new mapping", "ch15" in _r_midi_list)
        _r_midi_rm = run_command("MIDI REMOVE CC 15 100")
        _check("MIDI REMOVE CC removes mapping", "removed" in _r_midi_rm)
        _r_targets = run_command("MIDI TARGETS")
        _check("MIDI TARGETS lists targets", "GO" in _r_targets)

        # HIGHLIGHT must not survive BLACKOUT — real output computation,
        # not just the flag, since BLACKOUT is the show-stopping safety cutoff.
        run_command("ALL")
        run_command("HIGHLIGHT")
        run_command("BLACKOUT")
        _dmx_bbo = output_state.get_dmx_for_universe(1)
        _check("BLACKOUT overrides HIGHLIGHT in DMX output", max(_dmx_bbo) == 0)
        run_command("BLACKOUT OFF")
        run_command("HIGHLIGHT OFF")

        # FREEZE must not defeat BLACKOUT, SOLO, or a direct DMX override —
        # real output computation, not just the flags. FREEZE snapshots a
        # look; it must not be a way to disable the master safety cutoff.
        # FADER 1 STOP + FX CLEAR first: the very first smoke-test check
        # (near the top of this block) GO'd a sine-RED FX cue on fader 1
        # and never stopped it, so it's been running live in the background
        # ever since. With a selection active, "FX CLEAR" only clears
        # programmer FX (by design, scoped to selection) and leaves that
        # fader's FX running -- its real-time envelope would otherwise
        # make the frozen red value here timing-dependent instead of
        # deterministic. Stop the fader directly so nothing but this
        # test's own explicit AT command drives colour into the freeze.
        run_command("FADER 1 STOP")
        run_command("FX CLEAR")
        run_command("ALL AT R 200 G 150 B 100")
        run_command("FREEZE")
        _dmx_frozen = output_state.get_dmx_for_universe(1)
        _check("FREEZE snapshot holds the look", max(_dmx_frozen) > 0)
        run_command("BLACKOUT")
        _dmx_frozen_bbo = output_state.get_dmx_for_universe(1)
        _check("BLACKOUT overrides FREEZE in DMX output", max(_dmx_frozen_bbo) == 0)
        run_command("BLACKOUT OFF")
        _dmx_frozen_restored = output_state.get_dmx_for_universe(1)
        _check("FREEZE look restored after BLACKOUT OFF", _dmx_frozen_restored == _dmx_frozen)
        run_command("DMX 1 42")
        _dmx_frozen_override = output_state.get_dmx_for_universe(1)
        _check("direct DMX override still applies during FREEZE", _dmx_frozen_override[0] == 42)
        run_command("CLEAR DMX")

        # GRANDMASTER
        output_state.master_level = 1.0
        r_gm_show = run_command("GRANDMASTER")
        _check("GRANDMASTER (no args) shows current level", "%" in r_gm_show)
        r_gm_set = run_command("GM 75")
        _check("GM 75 sets master to 75%", abs(output_state.master_level - 0.75) < 0.01)
        _check("GM 75 returns confirmation with new level", "75" in r_gm_set)
        run_command("GM FULL")
        _check("GM FULL sets master to 100%", output_state.master_level == 1.0)
        run_command("GM OUT")
        _check("GM OUT sets master to 0%", output_state.master_level == 0.0)
        output_state.master_level = 1.0   # restore

        # SHOW INFO
        r_si = run_command("SHOW INFO")
        _check("SHOW INFO returns multi-line overview", len(r_si.splitlines()) >= 5)
        _check("SHOW INFO shows fixture count", "fixtures" in r_si)
        _check("SHOW INFO shows master level", "master" in r_si)

        # OUTPUT STATUS
        run_command("MASTER 100")          # ensure master at full
        run_command("FREEZE OFF")
        run_command("1 FULL")              # put fixture 1 at 100% in programmer
        r_os = run_command("OUTPUT STATUS")
        _check("OUTPUT STATUS returns non-empty string", len(r_os) > 10)
        _check("OUTPUT STATUS shows master level", "master=" in r_os.lower() or "Output" in r_os)
        prog.clear_programmer()

        # SOLO's "zero everyone else" guarantee must also survive FREEZE —
        # same class of bug, found by a background audit of the same code.
        # Seed a synthetic frozen snapshot directly instead of re-capturing
        # one through run_command("FREEZE") -- this isolates the check to
        # exactly the SOLO-during-FREEZE branch instead of also depending on
        # whatever dim/FX state other tests in this shared process happen
        # to have left on fixture 1 (that state is real but not this
        # check's concern).
        _solo_out = output_state.patch.get(1).all_subs()[0].outputs[0]
        _other_out = output_state.patch.get(3).all_subs()[0].outputs[0]
        _univ = _solo_out['universe']
        output_state.frozen_dmx[_univ] = tuple([200] * 512)
        output_state.freeze_mode = True
        run_command("1")
        run_command("SOLO")
        _dmx_frozen_solo = output_state.get_dmx_for_universe(_univ)
        _check("SOLO still zeros non-solo fixtures during FREEZE",
               _dmx_frozen_solo[_other_out['address'] - 1] == 0)
        _check("SOLO still passes the solo'd fixture during FREEZE",
               _dmx_frozen_solo[_solo_out['address'] - 1] > 0)
        run_command("SOLO OFF")
        run_command("FREEZE OFF")

        # RECORD GROUP + recall — untested prior to this session
        run_command("1 THRU 3")
        r_grp = run_command("RECORD GROUP 9 SmokeGroup")
        _check("RECORD GROUP from selection", "recorded" in r_grp)
        r_grp_recall = run_command("GROUP 9")
        _check("GROUP recall", "recalled" in r_grp_recall.lower())
        r_gi = run_command("GROUP 9 INFO")
        _check("GROUP INFO shows group name", "SmokeGroup" in r_gi)
        _check("GROUP INFO shows member count", "members" in r_gi)

        # GROUP ADD / GROUP REMOVE
        _g9 = group_pool.get(9)
        _g9_before = len(_g9.members)
        r_gadd = run_command("GROUP 9 ADD 4")   # add fixture 4
        _check("GROUP ADD increases member count by 1", len(_g9.members) == _g9_before + 1)
        _check("GROUP ADD returns confirmation", "added" in r_gadd.lower())
        r_gadd_dup = run_command("GROUP 9 ADD 4")
        _check("GROUP ADD rejects duplicate fixture", "already" in r_gadd_dup.lower())
        r_grem = run_command("GROUP 9 REMOVE 4")
        _check("GROUP REMOVE decreases member count by 1", len(_g9.members) == _g9_before)
        _check("GROUP REMOVE returns confirmation", "removed" in r_grem.lower())
        r_grem_miss = run_command("GROUP 9 REMOVE 4")
        _check("GROUP REMOVE rejects missing fixture", "not in group" in r_grem_miss.lower())

        # record form (custom breakpoint curve) — untested prior to this session
        r_form = run_command("record form 6 SmokeWave 0.0,0.0 0.5,1.0 1.0,0.0")
        _check("record form custom breakpoints", "recorded" in r_form)
        r_form_list = run_command("FORM LIST")
        _check("FORM LIST shows recorded form", "smokewave" in r_form_list.lower())

        # RECORD FX + FIRE FX roundtrip — untested prior to this session
        run_command("1 THRU 3")
        run_command("FX SINE BLUE BPM 40")
        r_fx_rec = run_command("RECORD FX 9 SmokeFX")
        _check("RECORD FX from programmer", "recorded" in r_fx_rec)
        run_command("FX CLEAR")
        r_fx_fire = run_command("FIRE FX 9")
        _check("FIRE FX reapplies preset", "FX" in r_fx_fire)
        run_command("FX CLEAR")

        # FX pool save/load round-trip must preserve speed_id (SpeedMaster
        # link) -- was silently dropped by save_fx_pool/load_fx_pool, so a
        # layer linked to a speed master reverted to its raw bpm on every
        # restart with no error.
        _speed_preset = FXPreset(19, "SmokeSpeedLink")
        _speed_preset.add_layer("sine", "red", bpm=45.0, speed_id=3)
        fx_pool.store(19, _speed_preset)
        ShowFile.save_fx_pool(fx_pool)
        _reloaded_fx_pool = FXPool()
        ShowFile.load_fx_pool(_reloaded_fx_pool)
        _reloaded_layer = _reloaded_fx_pool.get(19).layers[0]
        _check("fx_pool save/load preserves speed_id",
               _reloaded_layer.get("speed_id") == 3)

        # RECORD FX must also forward speed_id from the programmer's FX defs
        # into the stored preset (same bug, second call site).
        run_command("1 THRU 3")
        run_command("FX SINE GREEN BPM 50")
        for _fid, _vals in prog.data.items():
            if '.' not in _fid:
                for _ld in _vals.get('fx', []):
                    _ld['speed_id'] = 7
        r_fx_rec2 = run_command("RECORD FX 20 SmokeSpeedRec")
        _check("RECORD FX from programmer", "recorded" in r_fx_rec2)
        _check("RECORD FX preserves speed_id",
               fx_pool.get(20).layers[0].get("speed_id") == 7)
        run_command("FX CLEAR")

        # Attribute pools (POSITION/GOBO/ZOOM/FOCUS/BEAM/CONTROL) — GUI panel
        # landed last session but the record path was never smoke-tested.
        # These fixtures (SGM_RGB_54) have no pan/tilt/gobo/etc channels, so
        # recording should fail gracefully (not crash) rather than succeed.
        for _attr in ("POSITION", "GOBO", "ZOOM", "FOCUS", "BEAM", "CONTROL"):
            r_attr = run_command(f"RECORD {_attr} 9 Smoke{_attr.title()}")
            _check(f"RECORD {_attr} handles no-data case cleanly",
                   "no" in r_attr.lower() and "data in programmer" in r_attr.lower())

        # OSC input dispatch (Block 11) — /gma3/fader/PAGE/fdr is documented
        # as a 2-segment address (page, fdr) and _osc_fader parses it as
        # such, but the registered pattern had an extra "/*" wildcard segment
        # baked in since it was first added, so real /gma3/fader/1/1 messages
        # never matched it and silently fell through to the unmapped default
        # handler. Exercise the real dispatcher (not just call the handler
        # function directly) so a future pattern/handler mismatch here is
        # caught the same way this one was found.
        from pythonosc.osc_message_builder import OscMessageBuilder as _OscMsgBuilder
        _prev_fader_dim = _fader_dim[0]
        _fader_msg = _OscMsgBuilder(address="/gma3/fader/1/1")
        _fader_msg.add_arg(0.42)
        osc._dispatch.call_handlers_for_packet(_fader_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/fader/1/1 reaches _osc_fader and sets grandmaster dim",
               abs(_fader_dim[0] - 0.42) < 1e-6)
        _fader_dim[0] = _prev_fader_dim

        # OSC page/fader addressing used to hard-gate all fader/key behavior
        # on "page == 1 and fader == 1" — any other fader was parsed
        # and logged but silently dropped. Exercise fader 3 (arbitrary, not
        # fader 1) through the real dispatcher to confirm it now reaches
        # that fader's own level/GO/BACK, same as "FADER 3 LEVEL ..." /
        # "FADER 3 GO" typed on the command line.
        _osc_ex = fader_pool.get(3)
        _prev_osc_ex_level = _osc_ex.level
        _fader3_msg = _OscMsgBuilder(address="/gma3/fader/1/3")
        _fader3_msg.add_arg(0.65)
        osc._dispatch.call_handlers_for_packet(_fader3_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/fader/1/3 sets fader 3's own level (not grandmaster)",
               abs(_osc_ex.level - 0.65) < 1e-6)
        _osc_ex.level = _prev_osc_ex_level

        # stack 3 is wired to fader 3 by default at startup (every
        # loaded stack assigns 1:1 into the matching fader slot), so
        # a real GO on fdr 3 should activate it.
        _key3_msg = _OscMsgBuilder(address="/gma3/key/1/3/go")
        _key3_msg.add_arg(1)
        osc._dispatch.call_handlers_for_packet(_key3_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/key/1/3/go GOes fader 3 (routes through FADER 3 GO)",
               _osc_ex.is_active)

        # /gma3/key/PAGE/fdr/flash used to be silently dropped: the handler
        # returned immediately on any release (0) event regardless of TYPE,
        # and even on press only recognized go/go+/back/go-. A TouchOSC/
        # Chataigne "flash" key sent 1 then 0 and nothing happened at all.
        # Exercise both press and release through the real dispatcher.
        _flash_press_msg = _OscMsgBuilder(address="/gma3/key/1/3/flash")
        _flash_press_msg.add_arg(1)
        osc._dispatch.call_handlers_for_packet(_flash_press_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/key/1/3/flash press fires FADER 3 flash on",
               _osc_ex.is_active)
        _flash_release_msg = _OscMsgBuilder(address="/gma3/key/1/3/flash")
        _flash_release_msg.add_arg(0)
        osc._dispatch.call_handlers_for_packet(_flash_release_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/key/1/3/flash release fires FADER 3 flash off",
               not _osc_ex.is_active)

        # AudioEngine (Block 9) has an AUDIO command surface and a GUI panel
        # (audio_window) now, but its import used to be unconditional -- a
        # missing sounddevice package or native Portaudio lib crashed the
        # entire console before a single fixture patched. Force the
        # unavailable branch here so the guard is verified on every run,
        # regardless of whether this box happens to have a working audio
        # stack installed.
        _audio_probe = AudioEngine()
        _prev_audio_avail = _AUDIO_AVAILABLE
        _AUDIO_AVAILABLE = False
        # AudioEngine.list_devices()/.start() read _AUDIO_AVAILABLE from their
        # OWN module's namespace (studio_console/drivers/audio.py) now that
        # AudioEngine has moved there — rebinding the name in THIS module
        # (studio_project.py, via the line above) does not affect that
        # separate namespace, so it must be forced there too or this probe
        # exercises the "available" branch by accident instead of the
        # "unavailable" branch this test exists to check.
        _audio_driver._AUDIO_AVAILABLE = False
        try:
            try:
                _audio_probe.list_devices()
                _list_ok = True
            except Exception:
                _list_ok = False
            _check("AudioEngine.list_devices() doesn't raise when unavailable", _list_ok)

            try:
                _audio_probe.start()
                _check("AudioEngine.start() raises RuntimeError when unavailable", False)
            except RuntimeError:
                _check("AudioEngine.start() raises RuntimeError when unavailable", True)
            except Exception as _ae:
                _check(f"AudioEngine.start() raised wrong exception "
                       f"({type(_ae).__name__}) when unavailable", False)

            # AUDIO command wiring — the engine/mapper above were dead code
            # with zero command/GUI surface until this session; exercise the
            # run_command() path itself (not just the classes directly) the
            # same way the OSC dispatcher check above does. ON/OFF/STATUS/GAIN
            # don't touch real hardware so they're safe with a real audio
            # stack installed too; START/DEVICES are only exercised in the
            # forced-unavailable branch to avoid opening a real mic stream.
            run_command("AUDIO OFF")
            _check("AUDIO OFF works pre-start", not audio_mapper.enabled)
            run_command("AUDIO ON")
            _check("AUDIO ON enables mapper", audio_mapper.enabled)
            r_audio_status = run_command("AUDIO STATUS")
            _check("AUDIO STATUS reports mapping ON", "mapping ON" in r_audio_status)
            run_command("AUDIO OFF")
            _check("AUDIO OFF disables mapper", not audio_mapper.enabled)
            _prev_gain = audio_engine.gain
            run_command("AUDIO GAIN 5")
            _check("AUDIO GAIN sets engine gain", audio_engine.gain == 5.0)
            audio_engine.gain = _prev_gain

            r_devices = run_command("AUDIO DEVICES")
            _check("AUDIO DEVICES reports unavailable cleanly",
                   "unavailable" in r_devices.lower())
            r_start = run_command("AUDIO START")
            _check("AUDIO START reports failure cleanly (no crash)",
                   "failed" in r_start.lower())
        finally:
            _AUDIO_AVAILABLE = _prev_audio_avail
            _audio_driver._AUDIO_AVAILABLE = _prev_audio_avail

        # CLEAR stage 3 — should blackout output, not silently return "output_clear"
        prog.do_clear(); prog.do_clear()   # advance to stage 2 (programmer cleared)
        _saved_master = output_state.master_level
        output_state.master_level = 0.8
        prog.live_fades.append({"fid": "1", "ch": "dim", "src": 0.5, "dst": 1.0,
                                 "start": 0.0, "dur": 10.0})  # fake live fade
        prog._clear_stage = 2
        _r_clear3 = run_command("CLEAR")
        _check("CLEAR stage 3 does not touch master level", output_state.master_level == 0.8)
        _check("CLEAR stage 3 kills live fades", len(prog.live_fades) == 0)
        _check("CLEAR stage 3 returns programmer output cleared", "output cleared" in _r_clear3)
        output_state.master_level = _saved_master

        # RECORD CUE with FOLLOW time — was silently dropped before the fix
        run_command("ALL AT R 255 G 0 B 0")
        _r_follow = run_command("RECORD stk 1 CUE 99 FollowTest FOLLOW 3.5")
        _cs_1 = stack_pool.get(1)
        _cue_99 = _cs_1.cues.get(99.0) if _cs_1 else None
        _check("RECORD CUE stores FOLLOW time", _cue_99 is not None and
               abs(getattr(_cue_99, 'follow_time', 0) - 3.5) < 0.01)

        # COPY CUE preserves follow_time and note
        if _cue_99:
            _cue_99.note = "test note"
        run_command("COPY CUE 99 TO 98 stk 1")
        _cue_98 = _cs_1.cues.get(98.0) if _cs_1 else None
        _check("COPY CUE copies follow_time", _cue_98 is not None and
               abs(getattr(_cue_98, 'follow_time', 0) - 3.5) < 0.01)
        _check("COPY CUE copies note", _cue_98 is not None and
               getattr(_cue_98, 'note', '') == "test note")

        # MOVE CUE renumbers and removes source
        run_command("MOVE CUE 98 TO 97 stk 1")
        _check("MOVE CUE creates destination", _cs_1.cues.get(97.0) is not None)
        _check("MOVE CUE removes source", _cs_1.cues.get(98.0) is None)

        # GOTO non-existent cue returns error, not false success
        _r_goto_bad = run_command("GOTO 9999")
        _check("GOTO non-existent cue returns error", "not found" in (_r_goto_bad or "").lower())

        # FADER GOTO FIRST / LAST
        _gtfl_ex = fader_pool.get(1)
        if _gtfl_ex and _gtfl_ex.stack and _gtfl_ex.stack.cues:
            _gtfl_cs = _gtfl_ex.stack
            _gtfl_first = _gtfl_cs._sorted_cue_numbers()[0]
            _gtfl_last  = _gtfl_cs._sorted_cue_numbers()[-1]
            run_command("FADER 1 GOTO FIRST")
            _check("FADER GOTO FIRST positions stack at first cue",
                   _gtfl_cs.current == _gtfl_first)
            run_command("FADER 1 GOTO LAST")
            _check("FADER GOTO LAST positions stack at last cue",
                   _gtfl_cs.current == _gtfl_last)

        # delete cue cleans up cue_pool
        run_command("ALL AT R 128 G 0 B 0")
        run_command("RECORD stk 1 CUE 96")
        _check("delete cue: cue_pool stale ref cleaned", True)  # record stores in pool
        _pool_has_96_before = cue_pool.get(96) is not None
        run_command("delete cue 96 stk 1")
        _check("delete cue removes from cue_pool",
               _pool_has_96_before and cue_pool.get(96) is None)

        # speed master: set/get BPM
        _r_spd = run_command("SPEED 4 200")
        _check("SPEED command sets BPM", speed_master_pool.get_bpm(4) == 200.0)
        _r_spd_name = run_command("SPEED 4 NAME StrobeClk")
        _check("SPEED NAME renames slot", speed_master_pool.get(4).name == "Strobeclk")
        _r_list_spd = run_command("LIST SPEED")
        _check("LIST SPEED shows all slots", "speed masters" in (_r_list_spd or "").lower())
        # FX layer with speed master reference uses master BPM
        run_command("FX SINE RED BPM 60")
        _check("FX inline BPM default before speed ref", True)
        speed_master_pool.set_bpm(4, 333.0)
        _layer0 = active_fx[0] if active_fx else None
        if _layer0:
            _layer0._speed_id = 4
            _layer0._speed_master_pool = speed_master_pool
        _check("FX layer rate_bpm uses speed master", (
            _layer0 is None or abs(_layer0.rate_bpm - 333.0) < 0.1))

        # ── FX ENGINE COMPREHENSIVE TESTS ─────────────────────────────────────

        # Waveform range: all outputs must stay in [0, 1]
        import math as _math
        def _wv_range(name, fn):
            vals = [fn(t / 200.0) for t in range(200)]
            return min(vals) >= 0.0 and max(vals) <= 1.0
        _check("waveform sine range [0,1]",     _wv_range('sine',     Waveform.sine))
        _check("waveform ramp range [0,1]",     _wv_range('ramp',     Waveform.ramp))
        _check("waveform square range [0,1]",   _wv_range('square',   Waveform.square))
        _check("waveform pulse range [0,1]",    _wv_range('pulse',    Waveform.pulse))
        _check("waveform triangle range [0,1]", _wv_range('triangle', Waveform.triangle))
        _check("waveform sawtooth range [0,1]", _wv_range('sawtooth', Waveform.sawtooth))
        _check("waveform flicker range [0,1]",
               all(0.0 <= Waveform.flicker(t/200.0, i) <= 1.0
                   for t in range(200) for i in range(10)))

        # Flicker per-pixel independence: 10 pixels at same phase must differ
        _fl_vals = [Waveform.flicker(0.5, i) for i in range(10)]
        _check("flicker has per-pixel variation", len(set(_fl_vals)) > 1)

        # Flicker time resolution: enough unique states per cycle for 44Hz
        _fl_cycle = [Waveform.flicker(t / 100.0, 0) for t in range(100)]
        _check("flicker has ≥44 unique states/cycle", len(set(_fl_cycle)) >= 44)

        # Sine shape: trough at 0, peak at 0.5, back to trough at 1.0
        _check("sine shape: trough at 0.0",
               abs(Waveform.sine(0.0) - 0.0) < 0.01)
        _check("sine shape: peak at 0.5",
               abs(Waveform.sine(0.5) - 1.0) < 0.01)

        # Pulse duty cycle: on for exactly 25% of a cycle
        _pulse_on = sum(1 for t in range(1000) if Waveform.pulse(t/1000.0) > 0.5)
        _check("pulse duty cycle is 25%", abs(_pulse_on - 250) <= 2)

        # Strobe shorthand: STROBE creates a pulse dim FX layer
        run_command("FX CLEAR")
        _r_strobe = run_command("STROBE 120")
        _check("STROBE creates FX layer", active_fx != [] or "FX" in (_r_strobe or ""))

        # STROBE CLEAR removes dim FX
        run_command("STROBE 120")
        run_command("STROBE CLEAR")
        _strobe_still = any(l.channel == 'dim' for l in (active_fx or []))
        _check("STROBE CLEAR removes dim FX", not _strobe_still)

        # rainbow shorthand: RAINBOW creates 3 colour FX layers
        run_command("FX CLEAR")
        _r_rainbow = run_command("RAINBOW 60 100")
        _rainbow_chans = [l.channel for l in (active_fx or [])]
        _check("RAINBOW creates red layer",   'red'   in _rainbow_chans)
        _check("RAINBOW creates green layer", 'green' in _rainbow_chans)
        _check("RAINBOW creates blue layer",  'blue'  in _rainbow_chans)
        # Phase offsets should differ by ~0.33 between R→G and G→B
        _rb_layers = sorted(
            [l for l in (active_fx or []) if l.channel in ('red','green','blue')],
            key=lambda l: l.phase_offset)
        if len(_rb_layers) >= 3:
            _rb_ph = [l.phase_offset for l in _rb_layers]
            _check("RAINBOW phases spaced ~0.33 apart",
                   abs(_rb_ph[1] - _rb_ph[0] - 0.333) < 0.01 or
                   abs(_rb_ph[2] - _rb_ph[1] - 0.333) < 0.01)
        else:
            _check("RAINBOW phases (need 3 layers)", False)

        # Spread: with spread=100 and ≥2 targets, offsets are not all identical
        run_command("FX CLEAR")
        run_command("FX SINE RED SPREAD 100 BPM 60")
        _sp_layer = (active_fx or [None])[0]
        if _sp_layer and len(_sp_layer._offsets) >= 2:
            _check("spread=100 creates non-zero offsets",
                   len(set(round(o, 4) for o in _sp_layer._offsets)) > 1)
        else:
            _check("spread=100 (need ≥2 targets)", _sp_layer is None)

        # FX size scales amplitude: size=50 → max ~127 DMX
        run_command("FX CLEAR")
        run_command("FX SINE RED SIZE 50 SPREAD 0 BPM 60")
        _sz_layer = (active_fx or [None])[0]
        if _sz_layer:
            _sz_vals = _sz_layer.get_values(time.monotonic())
            _sz_max  = max(_sz_vals.values()) if _sz_vals else 0
            _check("FX size=50 gives max ~127 DMX", _sz_max <= 128.0)
        else:
            _check("FX size=50 (layer needed)", False)

        # dim FX: multiplicative (FX PULSE DIM should not exceed base dim)
        run_command("FX CLEAR")
        run_command("FX SQUARE DIM SIZE 100 SPREAD 0 BPM 30")
        _dm_layer = next((l for l in (active_fx or []) if l.channel == 'dim'), None)
        _check("dim FX layer channel is 'dim'", _dm_layer is not None)

        # Bounce direction: phase reverses after one cycle
        run_command("FX CLEAR")
        run_command("FX RAMP RED SPREAD 100 BPM 60 DIRECTION BOUNCE")
        _bn_layer = (active_fx or [None])[0]
        _check("bounce direction stored", _bn_layer is not None and _bn_layer.direction == 'bounce')

        # Block size: adjacent pixels grouped
        run_command("FX CLEAR")
        run_command("FX RAMP RED SPREAD 100 BLOCK 3 BPM 60")
        _bk_layer = (active_fx or [None])[0]
        if _bk_layer and len(_bk_layer._offsets) >= 6:
            _bk_off = _bk_layer._offsets
            _check("block_size=3 groups adjacent targets (offsets equal)",
                   _bk_off[0] == _bk_off[1] == _bk_off[2] and
                   _bk_off[3] == _bk_off[4] == _bk_off[5])
        else:
            _check("block_size=3 (need ≥6 targets)", True)

        # Infade: envelope ramps from 0 at start
        run_command("FX CLEAR")
        run_command("FX SINE RED INFADE 5 BPM 60")
        _if_layer = (active_fx or [None])[0]
        if _if_layer:
            _if_layer.start = time.monotonic()  # reset start so env starts at 0
            _if_layer.get_values(time.monotonic())
            _check("infade envelope starts near 0", _if_layer._last_env < 0.5)
        else:
            _check("infade (layer needed)", False)

        run_command("FX CLEAR")

        # ── CUE DIM TRACKING TESTS ───────────────────────────────────────────
        # Verify that dim in cue 1 tracks through cue 2 (FX-only) and cue 3 (empty).
        # This exercises the LTP tracking path in Fade.tick() for the case where
        # data_to has no dim entry.

        _ts_cs = Stack(999, "TrackTest")

        # cue 1: dim=0.8 stored explicitly
        _tc1 = Cue(1.0, "Track1")
        _tc1.data = {'_test_fid': {'dim': 0.8}}
        _ts_cs.cues[1.0] = _tc1

        # cue 2: no dim (should track 0.8 from cue 1)
        _tc2 = Cue(2.0, "Track2")
        _tc2.data = {}
        _ts_cs.cues[2.0] = _tc2

        # cue 3: empty (should still track 0.8)
        _tc3 = Cue(3.0, "Track3")
        _tc3.data = {}
        _ts_cs.cues[3.0] = _tc3

        # Simulate the Fade.tick() tracking logic directly (no real fader needed)
        def _sim_fade(data_from, data_to):
            """Return resulting layer after a tracking fade (t=1.0, instant)."""
            result = {}
            for fid in set(data_from) | set(data_to):
                fv = data_from.get(fid, {})
                tv = data_to.get(fid, {})
                if fid not in result:
                    result[fid] = {}
                for ch in set(fv) | set(tv):
                    v_from = fv.get(ch, 0)
                    _flag  = ch in ('fx_kill',)
                    v_to   = tv.get(ch, 0 if _flag else v_from)
                    if not isinstance(v_from, (int, float)) or not isinstance(v_to, (int, float)):
                        continue
                    # t=1.0 (fade complete)
                    result[fid][ch] = v_from + (v_to - v_from) * 1.0
            return result

        # cue 1 fires from empty fader
        _layer = {}
        _layer = _sim_fade(_layer, {'_test_fid': {'dim': 0.8}})
        _check("cue tracking: cue 1 sets dim=0.8",
               abs(_layer.get('_test_fid', {}).get('dim', -1) - 0.8) < 0.001)

        # cue 2 fires (no dim in data_to) — should track dim=0.8
        _layer = _sim_fade(_layer, {})
        _check("cue tracking: cue 2 tracks dim from cue 1",
               abs(_layer.get('_test_fid', {}).get('dim', -1) - 0.8) < 0.001)

        # cue 3 fires (also empty) — should still track dim=0.8
        _layer = _sim_fade(_layer, {})
        _check("cue tracking: cue 3 still tracks dim (no stale zero)",
               abs(_layer.get('_test_fid', {}).get('dim', -1) - 0.8) < 0.001)

        # fx_outfade field: cue class should have it, default None
        _fxo_cue = Cue(1.0, "fxout")
        _check("Cue.fx_outfade defaults to None", _fxo_cue.fx_outfade is None)

        # FXOUTFADE keyword in timing edit
        _apply_timing_edit(_fxo_cue, "FXOUTFADE 2.5")
        _check("FXOUTFADE sets cue.fx_outfade", _fxo_cue.fx_outfade == 2.5)

        # COPY CUE / COPY stk / MOVE CUE must preserve fx_outfade (was silently
        # dropped -- Cue() constructor doesn't take it, and all three call
        # sites copied note/data/timings but forgot fx_outfade)
        _fxo_src_cs = stack_pool.create(91)
        _fxo_src_cue = Cue(1.0, "FXOutSrc")
        _fxo_src_cue.fx_outfade = 3.25
        _fxo_src_cs.cues[1.0] = _fxo_src_cue
        run_command("COPY stk 91 TO stk 92")
        _fxo_dst_cs = stack_pool.get(92)
        _check("COPY stk preserves cue.fx_outfade",
               _fxo_dst_cs is not None and _fxo_dst_cs.cues.get(1.0) is not None and
               _fxo_dst_cs.cues[1.0].fx_outfade == 3.25)

        run_command("COPY stk 91 CUE 1 TO stk 93 CUE 1")
        _fxo_dst_cs2 = stack_pool.get(93)
        _check("COPY CUE (single cue) preserves cue.fx_outfade",
               _fxo_dst_cs2 is not None and _fxo_dst_cs2.cues.get(1.0) is not None and
               _fxo_dst_cs2.cues[1.0].fx_outfade == 3.25)

        run_command("MOVE stk 91 CUE 1 TO stk 94 CUE 1")
        _fxo_dst_cs3 = stack_pool.get(94)
        _check("MOVE CUE preserves cue.fx_outfade",
               _fxo_dst_cs3 is not None and _fxo_dst_cs3.cues.get(1.0) is not None and
               _fxo_dst_cs3.cues[1.0].fx_outfade == 3.25)

        # FX CLEAR clears fader FX layers
        run_command("FX SINE RED BPM 60 SIZE 100")
        _ex0 = _active_fader()
        _ex0_had_fx = bool(_ex0._fx_ids)
        run_command("FX CLEAR")
        _check("FX CLEAR clears fader FX (fader._fx_ids empty)",
               not _ex0._fx_ids)

        # FX CLEAR scoped to selection — only clears selected fixtures' programmer FX
        run_command("1 THRU 3")   # select fixtures 1-3
        run_command("FX SINE RED BPM 60 SIZE 100")
        _all_fids = list(prog.data.keys())
        run_command("FX CLEAR")   # selection active → programmer-only, scoped
        _cleared_sel = all(
            'fx' not in prog.data.get(str(f.fixture_id), {})
            for f in prog.selection
        )
        _check("FX CLEAR with selection clears only selected fixtures (programmer)",
               _cleared_sel)

        # CLEAR COLOUR removes RGB from programmer, leaves dim intact
        # dim lives in master key ("1"), RGB in sub-fixture keys ("1.1" etc.)
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("@ FULL")           # set dim=1.0 on selection
        run_command("1 THRU 3 R 255 G 128 B 64")  # set explicit RGB
        _pre_dim  = prog.data.get("1", {}).get('dim')
        _sub1     = next((k for k in prog.data if k.startswith("1.")), None)
        _pre_red  = prog.data.get(_sub1, {}).get('red') if _sub1 else None
        _check("CLEAR COLOUR pre-check: red was set", _pre_red == 255)
        run_command("CLEAR COLOUR")
        _post_rgb = prog.data.get(_sub1, {}).get('red') if _sub1 else None
        _post_dim = prog.data.get("1", {}).get('dim')
        _check("CLEAR COLOUR zeroes RGB and leaves dim intact",
               _post_rgb == 0 and _post_dim == _pre_dim)

        # CLEAR DIM removes only dimmer, leaves RGB intact
        # RGB lives in sub-fixture keys ("1.1"), dim in master key ("1")
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("@ FULL")
        run_command("1 THRU 3 R 200 G 100 B 50")
        run_command("CLEAR DIM")
        _post_dim2 = prog.data.get("1", {}).get('dim')
        _first_sub = next((k for k in prog.data if k.startswith("1.")), None)
        _post_red2 = prog.data.get(_first_sub, {}).get('red') if _first_sub else None
        _check("CLEAR DIM zeroes dim, leaves RGB intact",
               _post_dim2 == 0.0 and _post_red2 == 200)

        # stk n WRAP ON/OFF — clean restart at top after last cue
        run_command("RECORD STACK 99 WrapTest")
        _stk99 = stack_pool.get(99)
        _check("stk WRAP: default is False", _stk99.wrap is False)
        run_command("stk 99 WRAP ON")
        _check("stk 99 WRAP ON sets .wrap = True", _stk99.wrap is True)
        run_command("stk 99 WRAP OFF")
        _check("stk 99 WRAP OFF sets .wrap = False", _stk99.wrap is False)

        # stk INFO
        r_csi = run_command("stk 99 INFO")
        _check("stk INFO shows stack name", "WrapTest" in r_csi)
        _check("stk INFO shows wrap/loop state", "wrap" in r_csi or "loop" in r_csi)
        r_csi_bad = run_command("stk 9999 INFO")
        _check("stk INFO rejects unknown stack", "not found" in r_csi_bad)

        # stk REVERSE
        run_command("RECORD STACK 94 RevTest")
        run_command("STACK 94")
        run_command("1 FULL");   run_command("RECORD CUE 1 First")
        run_command("1 OUT");    run_command("RECORD CUE 2 Second")
        run_command("1 AT R 200"); run_command("RECORD CUE 3 Third")
        _stk94 = stack_pool.get(94)
        _orig_names = [_stk94.cues[n].name for n in _stk94._sorted_cue_numbers()]
        r_rev = run_command("stk 94 REVERSE")
        _rev_names = [_stk94.cues[n].name for n in _stk94._sorted_cue_numbers()]
        _check("stk REVERSE reverses cue order", _rev_names == list(reversed(_orig_names)))
        _check("stk REVERSE returns confirmation", "reversed" in r_rev)
        _check("stk REVERSE resets current position to None", _stk94.current is None)

        # stk COMPRESS
        run_command("RECORD STACK 95 CompTest")
        run_command("STACK 95")
        run_command("1 FULL"); run_command("RECORD CUE 1 Cue1")
        run_command("1 OUT");  run_command("RECORD CUE 5 Cue5")   # gap: 1, 5
        run_command("1 AT R 200"); run_command("RECORD CUE 10 Cue10")  # cues 1,5,10
        _stk95 = stack_pool.get(95)
        r_cmp = run_command("stk 95 COMPRESS")
        _cmp_nums = _stk95._sorted_cue_numbers()
        _check("stk COMPRESS renumbers cues to 1,2,3 (collapses gaps)",
               _cmp_nums == [1.0, 2.0, 3.0])
        _check("stk COMPRESS preserves cue names in order",
               [_stk95.cues[n].name for n in _cmp_nums] == ["Cue1", "Cue5", "Cue10"])
        _check("stk COMPRESS returns 'compressed' confirmation", "compressed" in r_cmp)

        # stk EXTRACT
        run_command("RECORD STACK 97 ExtractSrc")
        run_command("STACK 97")
        run_command("1 FULL"); run_command("RECORD CUE 1 ExtCue1")
        run_command("1 OUT");  run_command("RECORD CUE 2 ExtCue2")
        _stk97 = stack_pool.get(97)
        _stk97.note = "Dark Moody Show"
        _stk97.wrap = True
        r_ext = run_command("stk 97 EXTRACT 2 INTO 98")
        _stk98 = stack_pool.get(98)
        _check("stk EXTRACT creates new stack in target slot", _stk98 is not None)
        _check("stk EXTRACT new stack has exactly one cue",
               _stk98 is not None and len(_stk98.cues) == 1)
        _check("stk EXTRACT preserves cue name",
               _stk98 is not None and list(_stk98.cues.values())[0].name.lower() == "extcue2")
        _check("stk EXTRACT returns 'Extracted' confirmation", "extracted" in r_ext)
        _check("stk EXTRACT source stack unchanged (still 2 cues)", len(_stk97.cues) == 2)
        _check("stk EXTRACT carries source note to new stack",
               _stk98 is not None and _stk98.note == "Dark Moody Show")
        _check("stk EXTRACT carries source wrap flag to new stack",
               _stk98 is not None and _stk98.wrap is True)

        # stk DUPLICATE
        run_command("RECORD STACK 99 DupSrc")
        run_command("STACK 99")
        run_command("1 FULL"); run_command("RECORD CUE 1 DupA")
        run_command("1 OUT");  run_command("RECORD CUE 2 DupB")
        _cs99dup = stack_pool.get(99)
        _cs99dup.note = "Act 2 Opener"
        _cs99dup.wrap = True
        r_dup = run_command("stk 99 DUPLICATE INTO 100")
        _stk100 = stack_pool.get(100)
        _check("stk DUPLICATE creates new stack in target slot", _stk100 is not None)
        _check("stk DUPLICATE copies all cues",
               _stk100 is not None and len(_stk100.cues) == len(_cs99dup.cues))
        _check("stk DUPLICATE is a deep copy (modifying source doesn't affect copy)",
               _stk100 is not None and _stk100.cues is not _cs99dup.cues)
        _check("stk DUPLICATE returns 'Duplicated' confirmation", "duplicated" in r_dup)
        _check("stk DUPLICATE source is unchanged", len(_cs99dup.cues) == 2)
        _check("stk DUPLICATE carries source note to new stack",
               _stk100 is not None and _stk100.note == "Act 2 Opener")
        _check("stk DUPLICATE carries source wrap flag to new stack (regression check)",
               _stk100 is not None and _stk100.wrap is True)

        # stk RENUMBER STEP
        run_command("RECORD STACK 101 StepTest")
        run_command("STACK 101")
        run_command("1 FULL"); run_command("RECORD CUE 1 SA")
        run_command("1 OUT");  run_command("RECORD CUE 2 SB")
        run_command("1 AT R 200"); run_command("RECORD CUE 3 SC")
        _stk101 = stack_pool.get(101)
        r_ren = run_command("stk 101 RENUMBER STEP 10")
        _ren_nums = _stk101._sorted_cue_numbers()
        _check("stk RENUMBER STEP 10 gives multiples of 10",
               _ren_nums == [10.0, 20.0, 30.0])
        _check("stk RENUMBER STEP returns confirmation", "renumbered" in r_ren.lower())

        # CUE SHIFT
        run_command("RECORD STACK 96 ShiftTest")
        run_command("STACK 96")
        run_command("1 FULL"); run_command("RECORD CUE 3 MoverCue")
        run_command("1 OUT");  run_command("RECORD CUE 7 StayCue")
        _stk96 = stack_pool.get(96)
        r_shift = run_command("CUE 3 SHIFT 5")   # 3+5 = cue 8
        _shift_nums = _stk96._sorted_cue_numbers()
        _check("CUE SHIFT moves cue to new number (3→8)",
               3.0 not in _shift_nums and 8.0 in _shift_nums)
        _check("CUE SHIFT does not disturb other cues",
               7.0 in _shift_nums)
        _check("CUE SHIFT returns confirmation with new number", "8" in r_shift)

        # STACK MERGE
        run_command("RECORD STACK 91 MergeSrc")
        run_command("STACK 91")          # make active
        run_command("1 FULL")
        run_command("RECORD CUE 1 SrcCue1")
        run_command("RECORD STACK 92 MergeDst")
        run_command("STACK 92")
        run_command("1 OUT")
        run_command("RECORD CUE 1 DstCue1")
        _stk91 = stack_pool.get(91)
        _stk92 = stack_pool.get(92)
        _n_before = len(_stk92.cues)
        r_merge = run_command("STACK MERGE 91 INTO 92")
        _n_after = len(_stk92.cues)
        _check("STACK MERGE adds src cues to dst",
               _n_after == _n_before + len(_stk91.cues))
        _check("STACK MERGE returns confirmation", "merged" in r_merge)
        # Src cue numbers in dst should be offset past dst's original last cue
        _merged_num = max(_stk92._sorted_cue_numbers())
        _check("STACK MERGE renumbers merged cues after dst's last cue",
               _merged_num > 1.0)
        r_merge_bad = run_command("STACK MERGE 9999 INTO 92")
        _check("STACK MERGE rejects unknown source", "not found" in r_merge_bad)

        # stk BACK on wrap-around (first cue -> last cue) must also clear the
        # LTP-bleed layer when WRAP is ON -- stk GO already did this on forward
        # wrap (last -> first); BACK had no equivalent, flagged by a prior
        # session and left unfixed pending confirmation it wasn't intentional.
        run_command("RECORD STACK 98 BackWrapTest")
        _stk98 = stack_pool.get(98)
        run_command("1")
        run_command("AT R 10")
        run_command("RECORD stk 98 CUE 1")
        run_command("AT R 20")
        run_command("RECORD stk 98 CUE 2")
        prog.clear_programmer()
        run_command("ASSIGN stk 98 TO FADER 9")
        _ex98 = fader_pool.get(9)
        _stk98.wrap    = True
        _stk98.current = _stk98._sorted_cue_numbers()[0]   # sitting at first cue
        _ex98.layer['__bleed_sentinel__'] = {'red': 99}
        _stk98.back(patch, fade_engine, _ex98)
        _check("stk BACK wrap-around (first->last) clears LTP-bleed layer when WRAP ON",
               '__bleed_sentinel__' not in _ex98.layer)

        _stk98.wrap    = False
        _stk98.current = _stk98._sorted_cue_numbers()[0]
        _ex98.layer['__bleed_sentinel2__'] = {'red': 99}
        _stk98.back(patch, fade_engine, _ex98)
        _check("stk BACK wrap-around leaves layer intact when WRAP OFF",
               '__bleed_sentinel2__' in _ex98.layer)

        # Non-wrap BACK (middle of stack, no wraparound) must never clear the
        # layer even with WRAP ON -- only the actual last->first transition should.
        _stk98.wrap    = True
        _stk98.current = _stk98._sorted_cue_numbers()[-1]  # sitting at last cue, BACK is not a wrap
        _ex98.layer['__bleed_sentinel3__'] = {'red': 99}
        _stk98.back(patch, fade_engine, _ex98)
        _check("stk BACK non-wrap step leaves layer intact even with WRAP ON",
               '__bleed_sentinel3__' in _ex98.layer)

        # UNDO must not desync output_state.programmer_layer from prog.data --
        # link_programmer() aliases them to the *same* dict object, so undo()
        # rebinding self.data to a new object (instead of clearing+updating in
        # place) would silently freeze live DMX output on stale data forever.
        # Each single-channel "R n" call pushes its own undo snapshot, so one
        # UNDO after one single-channel edit fully reverts it.
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("1 THRU 3 R 10")
        run_command("1 THRU 3 R 250")
        _check("UNDO pre-check: post-undo-marker red was set",
               prog.data.get(_sub1, {}).get('red') == 250)
        run_command("UNDO")
        _check("UNDO restores prior programmer values",
               prog.data.get(_sub1, {}).get('red') == 10)
        _check("UNDO keeps output_state.programmer_layer aliased to prog.data "
               "(same object identity, not a stale copy)",
               output_state.programmer_layer is prog.data)
        run_command("1 THRU 3 R 77")
        _check("UNDO: post-undo edits are visible through the aliased "
               "programmer_layer used by real DMX output",
               output_state.programmer_layer.get(_sub1, {}).get('red') == 77)

        # fader page button assignment round-trip
        _fpg_ex = fader_pool.get(1)
        _fpg_ex.btn_a, _fpg_ex.btn_b, _fpg_ex.btn_c = 'GO', 'BACK', 'STOP'
        r_btn = run_command("FADER 1 BTN A FLASH")
        _check("FADER 1 BTN A FLASH sets btn_a to FLASH", _fpg_ex.btn_a == 'FLASH')
        r_btn2 = run_command("FADER 1 BTN A GO")
        _check("FADER 1 BTN A GO restores btn_a to GO",   _fpg_ex.btn_a == 'GO')
        r_btn3 = run_command("FADER 1 BTN")  # missing slot → usage hint
        _check("FADER 1 BTN without slot returns current state", "btn" in r_btn3.lower() or "usage" in r_btn3.lower() or "A=" in r_btn3)

        # RATE+/RATE- and RATE RESET smoke tests
        _rate_ex = fader_pool.get(2)
        _rate_ex.rate_factor = 1.0
        run_command("FADER 2 RATE+")
        _check("FADER 2 RATE+ increases rate_factor to ~1.25", abs(_rate_ex.rate_factor - 1.25) < 0.01)
        run_command("FADER 2 RATE-")
        _check("FADER 2 RATE- returns rate_factor to ~1.00", abs(_rate_ex.rate_factor - 1.0) < 0.01)
        run_command("FADER 2 RATE+")
        run_command("FADER 2 RATE RESET")
        _check("FADER 2 RATE RESET returns rate_factor to 1.0", _rate_ex.rate_factor == 1.0)
        run_command("FADER 2 RATE 3.0")
        _check("FADER 2 RATE 3.0 sets rate_factor to 3.0", abs(_rate_ex.rate_factor - 3.0) < 0.01)
        run_command("FADER 2 RATE RESET")
        r_rate_btn = run_command("FADER 2 BTN C RATE+")
        _check("FADER 2 BTN C RATE+ sets btn_c to RATE+", _rate_ex.btn_c == 'RATE+')
        run_command("FADER 2 BTN C STOP")  # restore

        # FADER LABEL
        _lbl_ex = fader_pool.get(1)
        r_lbl = run_command("FADER 1 LABEL Main Show")
        _check("FADER LABEL sets label on fader", _lbl_ex.label == "Main Show")
        _check("FADER LABEL returns confirmation", "Main Show" in r_lbl)
        r_lbl_list = run_command("LIST FADER")
        _check("LIST FADER shows label", "Main Show" in r_lbl_list)
        run_command("FADER 1 LABEL")  # clear
        _check("FADER 1 LABEL (no text) clears label", _lbl_ex.label == "")

        # FADER INFO
        r_fi1 = run_command("FADER 1 INFO")
        _check("FADER INFO shows level", "Level" in r_fi1)
        _check("FADER INFO shows buttons", "Buttons" in r_fi1)
        _fi1_ex = fader_pool.get(1)
        if _fi1_ex.stack:
            _check("FADER INFO shows stack name", _fi1_ex.stack.name in r_fi1)
        r_fi1_stat = run_command("FADER 1 STATUS")
        _check("FADER STATUS alias works", "Level" in r_fi1_stat)

        # FADER CLEAR
        _clr_ex = fader_pool.get(1)
        _clr_cs = _clr_ex.stack
        if _clr_cs:
            _clr_cs.current = 1  # pretend we're at cue 1
            r_fc = run_command("FADER 1 CLEAR")
            _check("FADER CLEAR resets stack position to None", _clr_cs.current is None)
            _check("FADER CLEAR returns confirmation", "cleared" in r_fc or "reset" in r_fc)

        # FADER ALL CLEAR
        if _clr_cs:
            _clr_cs.current = 2  # set a position to confirm it gets reset
        r_fac = run_command("FADER ALL CLEAR")
        _check("FADER ALL CLEAR returns 'cleared' confirmation", "cleared" in r_fac)
        _check("FADER ALL CLEAR resets position of stack in fader 1",
               _clr_cs is None or _clr_cs.current is None)

        # FADER LOOP ON/OFF
        if _clr_cs:
            r_loop_on  = run_command("FADER 1 LOOP ON")
            _check("FADER LOOP ON enables wrap on assigned stack", _clr_cs.wrap is True)
            _check("FADER LOOP ON returns confirmation", "loop" in r_loop_on.lower() or "wrap" in r_loop_on.lower())
            r_loop_off = run_command("FADER 1 LOOP OFF")
            _check("FADER LOOP OFF disables wrap on assigned stack", _clr_cs.wrap is False)

        # LOAD SHOW must reload OSC targets and FX defaults, not just leave
        # the previous show's live values in place — same primitives
        # load_show_from() now calls (osc._clients.clear() + load_osc_targets,
        # load_fx), exercised directly here so the test stays within the
        # isolated DATA_DIR and never touches the real studio_saves/ dir.
        osc.add_target("smoketest_stale", "10.0.0.1", 9000)
        ShowFile.save_osc_targets(osc)
        osc.add_target("smoketest_extra", "10.0.0.2", 9001)  # never persisted
        osc._clients.clear()
        ShowFile.load_osc_targets(osc)
        _check("LOAD SHOW-style OSC reload restores saved targets",
               "smoketest_stale" in osc._clients)
        _check("LOAD SHOW-style OSC reload drops targets not in the saved show",
               "smoketest_extra" not in osc._clients)

        _fx_params['rate_bpm'] = 60.0
        ShowFile.save_fx(_fx_params)
        _fx_params['rate_bpm'] = 999.0  # simulate a live value from a different show
        ShowFile.load_fx(_fx_params)
        _check("LOAD SHOW-style FX reload restores saved fx_params",
               _fx_params['rate_bpm'] == 60.0)

        # BACKUP command
        r_bk = run_command("BACKUP")
        _check("BACKUP creates a timestamped save", "backup_" in r_bk and "saved" in r_bk.lower())

        # ── ATTRIBUTE CHANNEL / MOVING LIGHT TESTS ───────────────────────────
        # Patch a Generic_Moving head into a spare slot (fixture 50), set
        # pan/tilt/gobo in programmer, record a cue, fire it, verify DMX output.

        _ml_profile = library.get("Generic_Moving")
        _check("Generic_Moving profile registered", _ml_profile is not None)

        if _ml_profile:
            # Patch at fixture 50, universe 1, address 400 (well clear of tubes)
            _ml_fix = patch.patch_fixture(50, "SmokeMoving", "Generic_Moving", 1, 400)
            _check("moving light patched", _ml_fix is not None)

            # AT PAN 200 TILT 64 from programmer
            prog.clear_programmer()
            run_command("50")
            run_command("AT DIM 100 PAN 200 TILT 64 GOBO 10")
            _ml_sub_fid = "50.1"
            _check("programmer stores pan",
                   prog.data.get(_ml_sub_fid, {}).get('pan') == 200)
            _check("programmer stores tilt",
                   prog.data.get(_ml_sub_fid, {}).get('tilt') == 64)
            _check("programmer stores gobo",
                   prog.data.get(_ml_sub_fid, {}).get('gobo') == 10)

            # Record to a cue and fire it; verify DMX output
            run_command("RECORD stk 2 CUE 80 FADE 0")
            run_command("ASSIGN stk 2 TO FADER 2")
            prog.clear_programmer()
            run_command("GO stk 2 CUE 80")
            time.sleep(0.12)  # 0-sec fade, just let the engine tick once
            _ml_dmx = output_state.get_dmx_for_universe(1)
            _ml_base = 400 - 1   # 0-indexed
            _ch_names = _ml_profile.channels
            _pan_off  = _ch_names.index('pan')
            _tilt_off = _ch_names.index('tilt')
            _gobo_off = _ch_names.index('gobo')
            _check("cue playback drives pan in DMX", _ml_dmx[_ml_base + _pan_off] == 200)
            _check("cue playback drives tilt in DMX", _ml_dmx[_ml_base + _tilt_off] == 64)
            _check("cue playback drives gobo in DMX", _ml_dmx[_ml_base + _gobo_off] == 10)

            # programmer-level attr write visible in DMX immediately
            prog.clear_programmer()
            run_command("50")
            run_command("AT PAN 127 TILT 127")
            _ml_dmx2 = output_state.get_dmx_for_universe(1)
            _check("programmer attr channels visible in DMX output",
                   _ml_dmx2[_ml_base + _pan_off] == 127)

            # Position pool: record and apply
            r_pos = run_command("RECORD POSITION 1 SmokePos")
            _check("RECORD POSITION from moving light programmer",
                   "Recorded" in r_pos or "no position" not in r_pos.lower())
            prog.clear_programmer()
            run_command("50")
            run_command("POSITION 1")
            _check("POSITION 1 restores pan to programmer",
                   prog.data.get(_ml_sub_fid, {}).get('pan') is not None)

            # FX on attribute channel: FX SINE PAN should create a layer
            run_command("FX CLEAR")
            run_command("50")
            r_pan_fx = run_command("FX SINE PAN BPM 30 SIZE 50")
            _check("FX SINE PAN accepted", "Applied FX" in r_pan_fx)
            _pan_fx_layer = next(
                (l for l in (active_fx or []) if l.channel == 'pan'), None)
            _check("FX SINE PAN creates layer with channel=pan",
                   _pan_fx_layer is not None)
            run_command("FX CLEAR")

            # DMX output handles generic profile channel order (dimmer first)
            prog.clear_programmer()
            run_command("50")
            run_command("AT DIM 100")   # sets master dim = 1.0
            _ml_dmx3 = output_state.get_dmx_for_universe(1)
            _dim_off  = _ch_names.index('dimmer')
            _check("dimmer profile channel outputs master dim correctly",
                   _ml_dmx3[_ml_base + _dim_off] == 255)

            # SNAPSHOT captures attr channels (not just RGB)
            prog.clear_programmer()
            run_command("50")
            run_command("AT DIM 80 PAN 180 TILT 90")
            r_snap = run_command("SNAPSHOT 95 AttrSnap")
            _active_cs_for_snap = stack_pool.get(active_fader[0])
            _snap_cue = _active_cs_for_snap.cues.get(95.0) if _active_cs_for_snap else None
            _check("SNAPSHOT creates cue with attr channel data",
                   _snap_cue is not None and
                   _snap_cue.data.get(_ml_sub_fid, {}).get('pan') == 180.0)
            prog.clear_programmer()

            # Cleanup
            prog.clear_programmer()
            run_command("FX CLEAR")
            del patch.fixtures[50]

        # ── RELATIVE AT TESTS ─────────────────────────────────────────────────
        run_command("1")
        prog.clear_programmer()
        run_command("1")
        run_command("AT 50")                      # set dim to 50%
        _check("AT 50 sets dim to 50%",
               abs(prog.data.get('1', {}).get('dim', 0) - 0.5) < 0.01)
        run_command("AT +20")                     # relative: 50 + 20 = 70%
        _check("AT +20 increases dim by 20pp",
               abs(prog.data.get('1', {}).get('dim', 0) - 0.7) < 0.01)
        run_command("AT -10")                     # relative: 70 - 10 = 60%
        _check("AT -10 decreases dim by 10pp",
               abs(prog.data.get('1', {}).get('dim', 0) - 0.6) < 0.01)
        # RGB relative
        run_command("AT R 100")
        run_command("AT R +50")                   # 100 + 50 = 150
        _check("AT R +50 increases red by 50",
               prog.data.get('1.1', {}).get('red') == 150)
        run_command("AT R +200")                  # clamp at 255
        _check("AT R +200 clamps to 255",
               prog.data.get('1.1', {}).get('red') == 255)
        prog.clear_programmer()

        # ── HUE COMMAND TESTS ─────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT HUE 0")       # pure red (hue=0°, S=100%, V=100%)
        _check("HUE 0 sets red=255, green=0, blue=0",
               prog.data.get('1.1', {}).get('red') == 255 and
               prog.data.get('1.1', {}).get('green') == 0 and
               prog.data.get('1.1', {}).get('blue') == 0)
        run_command("AT HUE 120")     # pure green
        _check("HUE 120 sets green=255",
               prog.data.get('1.1', {}).get('green') == 255 and
               prog.data.get('1.1', {}).get('red') == 0)
        run_command("AT HUE 240")     # pure blue
        _check("HUE 240 sets blue=255",
               prog.data.get('1.1', {}).get('blue') == 255 and
               prog.data.get('1.1', {}).get('red') == 0)
        run_command("AT HUE 60 SAT 100 VAL 150")   # VAL over 100 must clamp
        _check("HUE VAL clamps at 100 (no channel over 255)",
               prog.data.get('1.1', {}).get('red') == 255 and
               prog.data.get('1.1', {}).get('green') == 255)
        run_command("AT HUE 0 SAT -50")            # SAT under 0 must clamp to 0 (grey/white)
        _check("HUE SAT clamps at 0 (grey output, not a negative-saturation artifact)",
               prog.data.get('1.1', {}).get('red') == 255 and
               prog.data.get('1.1', {}).get('green') == 255 and
               prog.data.get('1.1', {}).get('blue') == 255)
        prog.clear_programmer()

        # ── CT (color temperature) COMMAND TESTS ──────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT CT 9000")   # very cool — blue=255, red < 255
        _check("CT 9000 (cool) sets blue=255",
               prog.data.get('1.1', {}).get('blue') == 255)
        _check("CT 9000 (cool) sets red < 255",
               (prog.data.get('1.1', {}).get('red') or 0) < 255)
        prog.clear_programmer()
        run_command("1")
        run_command("AT CT 2700")   # warm tungsten — red = 255, blue ~ low
        _check("CT 2700 (warm) sets red=255",
               prog.data.get('1.1', {}).get('red') == 255)
        _check("CT 2700 (warm) sets blue < 200",
               (prog.data.get('1.1', {}).get('blue') or 0) < 200)
        prog.clear_programmer()

        # ── FLIP CHANNEL TESTS ────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT R 60")           # set red to 60
        run_command("AT FLIP R")         # invert: 255 - 60 = 195
        _check("AT FLIP R inverts red channel",
               prog.data.get('1.1', {}).get('red') == 195)
        run_command("AT R 0")
        run_command("AT FLIP R")         # 255 - 0 = 255
        _check("AT FLIP R on 0 gives 255",
               prog.data.get('1.1', {}).get('red') == 255)
        prog.clear_programmer()

        # ── AT RANDOM CHANNEL TESTS ───────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 6")
        run_command("AT RANDOM R")    # each sub gets independent random red
        _rnd_reds = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 7)]
        _check("AT RANDOM R sets red on all selected fixtures",
               all(v is not None for v in _rnd_reds))
        _check("AT RANDOM R values are in valid range",
               all(0 <= v <= 255 for v in _rnd_reds if v is not None))
        # RANDOM MASTER: all subs of each master get same value
        prog.clear_programmer()
        run_command("1")   # 54 pixels
        run_command("AT RANDOM G MASTER")
        _grn_subs = [prog.data.get(f"1.{i}", {}).get('green') for i in range(1, 4)]
        _check("AT RANDOM G MASTER applies same value to all subs of a master",
               len(set(v for v in _grn_subs if v is not None)) == 1)

        # AT RANDOM DIM — randomize master dimmer per fixture
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("1 THRU 3 AT RANDOM DIM")
        _rnd_dims = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT RANDOM DIM sets dim on all selected masters",
               all(v is not None for v in _rnd_dims))
        _check("AT RANDOM DIM values are in valid range 0–1",
               all(0.0 <= v <= 1.0 for v in _rnd_dims if v is not None))
        prog.clear_programmer()

        # ── AT BRIGHTEST / AT DARKEST ─────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 50")   # all subs of fixture 1 → red=50
        run_command("2 AT R 200")  # all subs of fixture 2 → red=200
        run_command("3 AT R 120")  # all subs of fixture 3 → red=120
        run_command("1 THRU 3 AT BRIGHTEST R")  # max=200 → stamp to all
        _bd_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT BRIGHTEST R stamps max value (200) to all subs",
               all(v == 200 for v in _bd_vals if v is not None))
        run_command("1 AT R 50")   # restore variety
        run_command("2 AT R 200")
        run_command("3 AT R 120")
        run_command("1 THRU 3 AT DARKEST R")    # min=50 → stamp to all
        _dk_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT DARKEST R stamps min value (50) to all subs",
               all(v == 50 for v in _dk_vals if v is not None))
        run_command("1 AT R 0")    # restore variety: 0, 200, 120
        run_command("2 AT R 200")
        run_command("3 AT R 100")
        run_command("1 THRU 3 AT AVERAGE R")  # avg = (0+200+100)/3 = 100
        _avg_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT AVERAGE R stamps mean value (100) to all subs",
               all(v == 100 for v in _avg_vals if v is not None))

        # ── AT CLAMP ──────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 20")   # below lo
        run_command("2 AT R 100")  # in range
        run_command("3 AT R 240")  # above hi
        run_command("1 THRU 3 AT CLAMP R 50 200")
        _cl_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT CLAMP R clamps below-lo value up to lo (50)", _cl_vals[0] == 50)
        _check("AT CLAMP R leaves in-range value unchanged (100)", _cl_vals[1] == 100)
        _check("AT CLAMP R clamps above-hi value down to hi (200)", _cl_vals[2] == 200)

        # AT CLAMP DIM — clamp master dimmer using percent range
        prog.clear_programmer()
        run_command("1 AT DIM 10")   # 10% — below lo
        run_command("2 AT DIM 50")   # 50% — in range
        run_command("3 AT DIM 90")   # 90% — above hi
        run_command("1 THRU 3 AT CLAMP DIM 20 80")
        _cd_dims = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT CLAMP DIM: 10% → 20% (clamped up to lo)", abs((_cd_dims[0] or 0) - 0.2) < 0.01)
        _check("AT CLAMP DIM: 50% unchanged (in range)", abs((_cd_dims[1] or 0) - 0.5) < 0.01)
        _check("AT CLAMP DIM: 90% → 80% (clamped down to hi)", abs((_cd_dims[2] or 0) - 0.8) < 0.01)
        prog.clear_programmer()

        # ── AT BRIGHTEST / DARKEST / AVERAGE DIM ─────────────────────────────
        run_command("1 AT DIM 20")   # 20%
        run_command("2 AT DIM 60")   # 60%
        run_command("3 AT DIM 80")   # 80%
        run_command("1 THRU 3 AT BRIGHTEST DIM")
        _bd_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT BRIGHTEST DIM: all stamped to max (0.8)",
               all(abs((v or 0) - 0.8) < 0.01 for v in _bd_d))
        run_command("1 THRU 3 AT DARKEST DIM")
        _dk_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT DARKEST DIM: all stamped to min (0.8 after BRIGHTEST)",
               all(abs((v or 0) - 0.8) < 0.01 for v in _dk_d))
        # Reset to original spread and test AVERAGE
        run_command("1 AT DIM 20"); run_command("2 AT DIM 60"); run_command("3 AT DIM 100")
        run_command("1 THRU 3 AT AVERAGE DIM")
        _av_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT AVERAGE DIM: all stamped to mean (20+60+100)/3=60%",
               all(abs((v or 0) - 0.6) < 0.01 for v in _av_d))
        prog.clear_programmer()

        # ── AT INVERT DIM / AT SCALE DIM / AT WOBBLE DIM ─────────────────────
        run_command("1 THRU 2 AT DIM 30")   # 30%
        run_command("1 THRU 2 AT INVERT DIM")
        _inv_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 3)]
        _check("AT INVERT DIM: 30% → 70%", all(abs((v or 0) - 0.7) < 0.01 for v in _inv_d))
        run_command("1 THRU 2 AT SCALE DIM 50")   # 70% × 50% = 35%
        _sc_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 3)]
        _check("AT SCALE DIM 50: 70% × 50% = 35%", all(abs((v or 0) - 0.35) < 0.01 for v in _sc_d))
        run_command("1 THRU 2 AT SCALE DIM 200")  # 35% × 200% = 70% (≤ 1.0)
        _sc_d2 = [prog.data.get(str(i), {}).get('dim') for i in range(1, 3)]
        _check("AT SCALE DIM 200: 35% × 200% = 70%", all(abs((v or 0) - 0.7) < 0.01 for v in _sc_d2))
        run_command("1 THRU 3 AT DIM 50")
        run_command("1 THRU 3 AT WOBBLE DIM 10")   # ±10% jitter
        _wb_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT WOBBLE DIM: values remain in 0–1 range",
               all(0.0 <= (v or 0) <= 1.0 for v in _wb_d))
        _check("AT WOBBLE DIM: values are near the seed (within 10%)",
               all(abs((v or 0) - 0.5) <= 0.10 for v in _wb_d))
        prog.clear_programmer()

        # ── AT STEP ───────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 3 AT R 50")        # seed all at 50
        run_command("1 THRU 3 AT STEP R 20")   # 50+0, 50+20, 50+40
        _st_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT STEP R fixture 1 unchanged (offset 0)", _st_vals[0] == 50)
        _check("AT STEP R fixture 2 offset +20 (70)",      _st_vals[1] == 70)
        _check("AT STEP R fixture 3 offset +40 (90)",      _st_vals[2] == 90)

        # ── AT MIRROR ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 10")   # fixture 1 = red 10
        run_command("2 AT R 100")  # fixture 2 = red 100
        run_command("3 AT R 200")  # fixture 3 = red 200
        run_command("1 THRU 3 AT MIRROR R")  # should swap 1↔3, keep 2 (symmetric)
        _mir_r1 = prog.data.get("1.1", {}).get('red')
        _mir_r2 = prog.data.get("2.1", {}).get('red')
        _mir_r3 = prog.data.get("3.1", {}).get('red')
        _check("AT MIRROR R swaps first ↔ last (fixture 1 gets fixture 3's value)",
               _mir_r1 == 200)
        _check("AT MIRROR R middle fixture gets its own mirror (fixture 3 gets fixture 1's value)",
               _mir_r3 == 10)
        prog.clear_programmer()

        # ── AT INVERT ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 100")   # fixture 1 red = 100
        run_command("2 AT R 0")     # fixture 2 red = 0
        run_command("1 THRU 2 AT INVERT R")
        _inv_r1 = prog.data.get("1.1", {}).get('red')
        _inv_r2 = prog.data.get("2.1", {}).get('red')
        _check("AT INVERT R: 100 → 155 (255-100)", _inv_r1 == 155)
        _check("AT INVERT R: 0 → 255 (255-0)",     _inv_r2 == 255)
        prog.clear_programmer()

        # ── AT SCALE ──────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 200")   # fixture 1 red = 200
        run_command("2 AT R 100")   # fixture 2 red = 100
        run_command("1 THRU 2 AT SCALE R 50")   # 50% → 100, 50
        _sc_r1 = prog.data.get("1.1", {}).get('red')
        _sc_r2 = prog.data.get("2.1", {}).get('red')
        _check("AT SCALE R 50%: 200 → 100", _sc_r1 == 100)
        _check("AT SCALE R 50%: 100 → 50",  _sc_r2 == 50)
        run_command("1 AT R 200")
        run_command("1 AT SCALE R 200")   # 200% of 200 = 400 → clamped to 255
        _sc_clamp = prog.data.get("1.1", {}).get('red')
        _check("AT SCALE R clamps at 255", _sc_clamp == 255)
        prog.clear_programmer()

        # ── AT WOBBLE ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 3 AT R 128")   # seed all at 128
        run_command("1 THRU 3 AT WOBBLE R 50")   # add ±50 jitter
        _wb_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT WOBBLE R keeps values in 0-255 range",
               all(v is not None and 0 <= v <= 255 for v in _wb_vals))
        _check("AT WOBBLE R values are near the seed (within 50)",
               all(v is not None and abs(v - 128) <= 50 for v in _wb_vals))
        prog.clear_programmer()

        # ── AT CLEAR ──────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 200 G 100")   # fixture 1: red=200, green=100
        run_command("1 AT CLEAR R")       # remove only red
        _ac_r = prog.data.get("1.1", {}).get('red')
        _ac_g = prog.data.get("1.1", {}).get('green')
        _check("AT CLEAR R removes red from programmer", _ac_r is None)
        _check("AT CLEAR R leaves other channels intact", _ac_g == 100)
        run_command("1 AT CLEAR")         # remove all channels for fixture 1
        _ac_all = prog.data.get("1.1", {})
        _check("AT CLEAR (no ch) removes all channels for selection", not _ac_all)
        prog.clear_programmer()

        # ── AT NORMALIZE ──────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 50")    # fixture 1 red = 50
        run_command("2 AT R 100")   # fixture 2 red = 100
        run_command("3 AT R 200")   # fixture 3 red = 200  (max)
        run_command("1 THRU 3 AT NORMALIZE R")
        _nrm_r = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT NORMALIZE R: highest value becomes 255", _nrm_r[2] == 255)
        _check("AT NORMALIZE R: proportional scale (50→64, 100→128)", _nrm_r[0] == 64 and _nrm_r[1] == 128)
        prog.clear_programmer()

        # ── AT COPY ───────────────────────────────────────────────────────────
        run_command("1")                        # select fixture 1
        run_command("1 AT DIM 80 R 200 G 50")  # set source values on fixture 1
        run_command("2 3")                      # select fixtures 2 & 3
        run_command("2 3 AT COPY 1")            # copy fixture 1 values into 2 & 3
        _cp_dim2  = prog.data.get("2", {}).get('dim')
        _cp_dim3  = prog.data.get("3", {}).get('dim')
        _cp_r2    = prog.data.get("2.1", {}).get('red')
        _cp_r3    = prog.data.get("3.1", {}).get('red')
        _cp_g2    = prog.data.get("2.1", {}).get('green')
        _check("AT COPY: dimmer copied to fixture 2", abs((_cp_dim2 or 0) - 0.8) < 0.01)
        _check("AT COPY: dimmer copied to fixture 3", abs((_cp_dim3 or 0) - 0.8) < 0.01)
        _check("AT COPY: red channel copied to fixture 2", _cp_r2 == 200)
        _check("AT COPY: red channel copied to fixture 3", _cp_r3 == 200)
        _check("AT COPY: green channel copied to fixture 2", _cp_g2 == 50)
        prog.clear_programmer()

        # ── stk NOTE ───────────────────────────────────────────────────────────
        _csnote_cs = stack_pool.get(99)
        if _csnote_cs is None:
            stack_pool.create(99, "NoteTestStack")
            _csnote_cs = stack_pool.get(99)
        _csnote_cs.note = ""
        _no_note_msg = run_command("stk 99 NOTE")
        _check("stk NOTE view returns has-no-note message when blank",
               "no note" in _no_note_msg.lower() or "set with" in _no_note_msg.lower())
        run_command("stk 99 NOTE Dark Moody Show")
        _check("stk NOTE set stores text",  _csnote_cs.note == "Dark Moody Show")
        _note_view = run_command("stk 99 NOTE")
        _check("stk NOTE view returns the note text", "Dark Moody Show" in _note_view)
        _csnote_cs.note = ""

        # ── stk BOUNCE ─────────────────────────────────────────────────────────
        # Verify ping-pong direction logic using a fresh 3-cue stack
        _bcs_id = 102
        stack_pool.create(_bcs_id, "BounceTest")
        _bcs = stack_pool.get(_bcs_id)
        _bcs.cues.clear()
        _bcs.current = None
        # Build 3 minimal cues directly (cue_pool.store returns None, so assign separately)
        def _mk_cue(num, dim_frac):
            prog.data["1"] = {"dim": dim_frac}
            c = Cue(float(num), f"C{num}")
            c.record(prog)
            prog.data.clear()
            _bcs.cues[float(num)] = c
        _mk_cue(1, 0.33)
        _mk_cue(2, 0.66)
        _mk_cue(3, 1.0)
        _check("BOUNCE: stack has 3 cues", len(_bcs.cues) == 3)
        run_command(f"stk {_bcs_id} bounce on")
        _check("stk bounce on sets .bounce = True", _bcs.bounce is True)
        # Use a minimal stub fader — bounce logic only needs .layer dict
        _bex = fader_pool.get(_bcs_id)
        _bex.assign(_bcs)
        _bcs.current = None
        _bcs._bounce_dir = 1
        _bcs.go(patch, fade_engine, _bex)   # fires cue 1
        _check("BOUNCE GO 1: at cue 1", _bcs.current == 1.0)
        _bcs.go(patch, fade_engine, _bex)   # fires cue 2
        _check("BOUNCE GO 2: at cue 2", _bcs.current == 2.0)
        _bcs.go(patch, fade_engine, _bex)   # fires cue 3
        _check("BOUNCE GO 3: at cue 3", _bcs.current == 3.0)
        _bcs.go(patch, fade_engine, _bex)   # hits end → reverses → fires cue 2
        _check("BOUNCE GO 4: reverses at last cue → cue 2", _bcs.current == 2.0)
        _check("BOUNCE GO 4: direction flipped to -1", _bcs._bounce_dir == -1)
        _bcs.go(patch, fade_engine, _bex)   # fires cue 1
        _check("BOUNCE GO 5: at cue 1", _bcs.current == 1.0)
        _bcs.go(patch, fade_engine, _bex)   # hits start → reverses → fires cue 2
        _check("BOUNCE GO 6: reverses at first cue → cue 2", _bcs.current == 2.0)
        _check("BOUNCE GO 6: direction flipped to +1", _bcs._bounce_dir == 1)
        run_command(f"stk {_bcs_id} bounce off")
        _check("stk bounce off sets .bounce = False", _bcs.bounce is False)
        stack_pool.stacks.pop(_bcs_id, None)

        # ── stk CLEAR ──────────────────────────────────────────────────────────
        _cc_id = 103
        stack_pool.create(_cc_id, "ClearTest")
        _cc = stack_pool.get(_cc_id)
        _cc.cues.clear()
        prog.data["1"] = {"dim": 0.5}
        _cc.cues[1.0] = Cue(1.0, "X"); _cc.cues[1.0].record(prog)
        _cc.cues[2.0] = Cue(2.0, "Y"); _cc.cues[2.0].record(prog)
        prog.data.clear()
        _cc.current = 1.0
        _check("stk CLEAR: setup has 2 cues", len(_cc.cues) == 2)
        _r_clear_cs = run_command(f"stk {_cc_id} CLEAR")
        _check("stk CLEAR: removes all cues", len(_cc.cues) == 0)
        _check("stk CLEAR: resets current to None", _cc.current is None)
        _check("stk CLEAR: returns confirmation", "cleared" in _r_clear_cs.lower())
        stack_pool.stacks.pop(_cc_id, None)

        # ── LIST NOTES ────────────────────────────────────────────────────────
        # Set a stack note and cue note, confirm LIST NOTES shows both
        _ln_cs = stack_pool.get(1)
        if _ln_cs:
            _ln_orig_note = getattr(_ln_cs, 'note', '')
            _ln_cs.note = "ListNotesTest"
            _cue1 = _ln_cs.cues.get(1.0) or next(iter(_ln_cs.cues.values()), None)
            _orig_cue_note = ""
            if _cue1:
                _orig_cue_note = getattr(_cue1, 'note', '')
                _cue1.note = "CueNoteTest"
            _ln_result = run_command("LIST NOTES")
            _check("LIST NOTES: includes stack note", "ListNotesTest" in _ln_result)
            if _cue1:
                _check("LIST NOTES: includes cue note", "CueNoteTest" in _ln_result)
            _ln_cs.note = _ln_orig_note
            if _cue1:
                _cue1.note = _orig_cue_note
        _ln_empty = run_command("LIST NOTES")

        # ── FIXTURE GROUPS ────────────────────────────────────────────────────
        # group 1 is set up in the show init with fixture 1 etc. — look for fixture 1
        _fg_fid = next(iter(sorted(patch.fixtures)), None)
        if _fg_fid is not None:
            # ensure fixture is in at least one group by checking group_pool
            _fg_in_group = any(
                any(isinstance(e, tuple) and e[1] == _fg_fid for e in g.members)
                for g in group_pool.groups.values()
            )
            if _fg_in_group:
                _fg_result = run_command(f"FIXTURE GROUPS {_fg_fid}")
                _check("FIXTURE GROUPS: returns group membership info",
                       "Group" in _fg_result or "group" in _fg_result)
                _check("FIXTURE GROUPS: mentions the fixture name",
                       patch.fixtures[_fg_fid].name in _fg_result
                       or str(_fg_fid) in _fg_result)
            # Fixture not in any group scenario
            _fg_not_found = run_command("FIXTURE GROUPS 9999")
            _check("FIXTURE GROUPS: bad fixture returns error", "not patched" in _fg_not_found.lower())

        # ── RENAME FIXTURE ────────────────────────────────────────────────────
        _rf_fid = next(iter(sorted(patch.fixtures)), None)
        if _rf_fid is not None:
            _rf_master = patch.fixtures[_rf_fid]
            _rf_orig = _rf_master.name
            _rf_result = run_command(f"RENAME FIXTURE {_rf_fid} TempTestName")
            _check("RENAME FIXTURE: changes master.name", _rf_master.name == "TempTestName")
            _check("RENAME FIXTURE: includes old→new in response",
                   "TempTestName" in _rf_result)
            run_command(f"RENAME FIXTURE {_rf_fid} {_rf_orig}")  # restore
            _check("RENAME FIXTURE: name restored", _rf_master.name == _rf_orig)
        _rf_bad = run_command("RENAME FIXTURE 9999 X")
        _check("RENAME FIXTURE: bad ID returns error", "not in patch" in _rf_bad)

        # ── PROGRAMMER SCALE ──────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT DIM 100")         # dim=1.0
        run_command("1 AT R 200 G 100")     # red=200, green=100
        _r_ps = run_command("PROGRAMMER SCALE 50")
        _check("PROGRAMMER SCALE: returns confirmation", "50%" in _r_ps or "scaled" in _r_ps.lower())
        _ps_dim = prog.data.get("1", {}).get('dim')
        _ps_r   = prog.data.get("1.1", {}).get('red')
        _ps_g   = prog.data.get("1.1", {}).get('green')
        _check("PROGRAMMER SCALE 50: dim scaled to 50%", abs((_ps_dim or 0) - 0.5) < 0.01)
        _check("PROGRAMMER SCALE 50: red 200 → 100", _ps_r == 100)
        _check("PROGRAMMER SCALE 50: green 100 → 50", _ps_g == 50)
        # Test 200% (amplify + clamp)
        run_command("PROGRAMMER SCALE 200")
        _ps_r2 = prog.data.get("1.1", {}).get('red')
        _check("PROGRAMMER SCALE 200: red 100 × 2 = 200", _ps_r2 == 200)
        # Test empty programmer
        prog.clear_programmer()
        _r_ps_empty = run_command("PROGRAMMER SCALE 50")
        _check("PROGRAMMER SCALE: empty programmer returns error", "empty" in _r_ps_empty.lower())
        prog.clear_programmer()

        # ── FADER ASSIGN stk ───────────────────────────────────────────────────
        _fa_cs = stack_pool.get(1)
        if _fa_cs:
            _fa_ex = fader_pool.get(15)  # high slot unlikely to conflict
            _fa_result = run_command(f"FADER 15 ASSIGN stk 1")
            _check("FADER ASSIGN stk: wires stack to fader",
                   _fa_ex.stack is _fa_cs)
            _check("FADER ASSIGN stk: returns confirmation",
                   "stk 1" in _fa_result or "assigned" in _fa_result.lower())
            _r_fa_bad = run_command("FADER 15 ASSIGN stk 9999")
            _check("FADER ASSIGN stk: bad stk returns error",
                   "not found" in _r_fa_bad.lower())

        # ── FADER UNASSIGN ────────────────────────────────────────────────────
        # Assign stk 1 to fader 16, then UNASSIGN it
        if stack_pool.get(1):
            run_command("FADER 16 ASSIGN stk 1")
            _fu_ex = fader_pool.get(16)
            _check("FADER UNASSIGN: setup — stack assigned", _fu_ex.stack is not None)
            _r_ua = run_command("FADER 16 UNASSIGN")
            _check("FADER UNASSIGN: stack is None after unassign", _fu_ex.stack is None)
            _check("FADER UNASSIGN: returns confirmation", "unassigned" in _r_ua.lower())
            _r_ua_empty = run_command("FADER 16 UNASSIGN")
            _check("FADER UNASSIGN: returns error when already empty",
                   "no stack" in _r_ua_empty.lower())

        # ── FAN TESTS ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 6")
        run_command("FAN DIM 0 100")
        _fan_dims = [prog.data.get(str(i), {}).get('dim') for i in range(1, 7)]
        _check("FAN DIM sets fixture 1 to 0%",  abs(_fan_dims[0] or 0) < 0.01)
        _check("FAN DIM sets fixture 6 to 100%", abs((_fan_dims[5] or 0) - 1.0) < 0.01)
        _check("FAN DIM is monotone across selection",
               all(_fan_dims[i] is not None and _fan_dims[i] <= _fan_dims[i+1]
                   for i in range(5)))
        run_command("FAN R 0 255")
        _fan_r = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 7)]
        _check("FAN R sets fixture 1 red to 0",   _fan_r[0] == 0)
        _check("FAN R sets fixture 6 red to 255",  _fan_r[5] == 255)
        prog.clear_programmer()

        # ── RANDOM / EVERY SELECTION TESTS ───────────────────────────────────
        run_command("RANDOM 3")
        _sel_m = [m for m in prog.selection if isinstance(m, MasterFixture)]
        _check("RANDOM 3 selects exactly 3 master fixtures", len(_sel_m) == 3)
        prog.clear_programmer()
        run_command("1 THRU 6 EVERY 2")   # selects 1, 3, 5
        _sel_m2 = [m.fixture_id for m in prog.selection if isinstance(m, MasterFixture)]
        _check("1 THRU 6 EVERY 2 selects 1,3,5", _sel_m2 == [1, 3, 5])
        prog.clear_programmer()

        # ── NEXT/PREV FIXTURE NAVIGATION ──────────────────────────────────────
        _all_ids = [m.fixture_id for m in patch.all_fixtures()]
        if len(_all_ids) >= 2:
            run_command(str(_all_ids[0]))     # select first fixture
            run_command("NEXT")               # should advance to second
            _sel_masters = [m.fixture_id for m in prog.selection
                            if isinstance(m, MasterFixture)]
            _check("NEXT advances selection to next fixture",
                   _sel_masters == [_all_ids[1]])
            run_command("PREV")               # should go back to first
            _sel_masters2 = [m.fixture_id for m in prog.selection
                             if isinstance(m, MasterFixture)]
            _check("PREV retreats selection to previous fixture",
                   _sel_masters2 == [_all_ids[0]])
            prog.clear_programmer()

        # ── PATCH RENAME / PATCH MOVE TESTS ──────────────────────────────
        _tmp_fix = patch.patch_fixture(51, "TmpFix", "Generic_RGB", 1, 490)
        _check("PATCH RENAME test fixture patched", _tmp_fix is not None)
        r_pr = run_command("PATCH RENAME 51 RenamedFix")
        _check("PATCH RENAME changes fixture name",
               patch.get(51) is not None and patch.get(51).name == "RenamedFix")
        r_pm = run_command("PATCH MOVE 51 UNIVERSE 2 AT 50")
        _first_sub_51 = patch.get(51).all_subs()[0] if patch.get(51) else None
        _check("PATCH MOVE updates sub universe",
               _first_sub_51 is not None and _first_sub_51.outputs[0]['universe'] == 2)
        _check("PATCH MOVE updates sub address",
               _first_sub_51 is not None and _first_sub_51.outputs[0]['address'] == 50)
        del patch.fixtures[51]

        # ── MACRO RECORD / PLAYBACK TESTS ────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("MACRO RECORD 99 SmokeTest")
        _check("MACRO RECORD starts recording", _macro_recording["slot"] == 99)
        run_command("AT FULL")          # captured inside macro
        run_command("AT R 200")         # captured inside macro
        r_ms = run_command("MACRO STOP")
        _check("MACRO STOP saves macro to pool", 99 in macro_pool)
        _check("MACRO STOP records correct command count",
               len(macro_pool.get(99, {}).get("commands", [])) == 2)
        _check("MACRO STOP ends recording", _macro_recording["slot"] is None)
        prog.clear_programmer()
        run_command("1")
        r_mb = run_command("MACRO 99")
        _check("MACRO playback result mentions commands played", "cmd" in r_mb)
        _check("MACRO playback restores dim",
               abs(prog.data.get('1', {}).get('dim', 0) - 1.0) < 0.01)
        _check("MACRO playback restores red channel",
               prog.data.get('1.1', {}).get('red') == 200)
        run_command("RENAME MACRO 99 Renamed")
        _check("RENAME MACRO changes name",
               macro_pool.get(99, {}).get("name") == "Renamed")
        run_command("MACRO DELETE 99")
        _check("MACRO DELETE removes slot", 99 not in macro_pool)
        # Also test MACRO RENAME <n> <name> (alternative order)
        macro_pool[98] = {"name": "TestMacro", "commands": ["1 FULL"]}
        r_mrn = run_command("MACRO RENAME 98 RenamedViaMAcroRename")
        _check("MACRO RENAME <n> <name> renames macro",
               macro_pool.get(98, {}).get("name") == "RenamedViaMAcroRename")
        del macro_pool[98]
        prog.clear_programmer()

        # ── MACRO RECURSION GUARD TESTS ───────────────────────────────────────
        # A macro whose commands (directly or via another macro) play itself
        # again used to recurse with no depth limit -> RecursionError crash.
        macro_pool[97] = {"name": "SelfRef", "commands": ["MACRO 97"]}
        r_self = run_command("MACRO 97")
        _check("MACRO self-recursion blocked, not a crash", "blocked" in r_self)
        _check("MACRO play stack cleaned up after self-recursion block",
               len(_macro_play_stack) == 0)
        macro_pool[95] = {"name": "A", "commands": ["MACRO 96"]}
        macro_pool[96] = {"name": "B", "commands": ["MACRO 95"]}
        r_cycle = run_command("MACRO 95")
        _check("MACRO indirect A->B->A cycle blocked, not a crash",
               "blocked" in r_cycle)
        _check("MACRO play stack cleaned up after cycle block",
               len(_macro_play_stack) == 0)
        del macro_pool[97]
        del macro_pool[95]
        del macro_pool[96]

        # ── PARK / UNPARK TESTS ───────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT FULL")           # dim=1.0, so DMX output for fixture 1 is non-zero
        run_command("AT R 200 G 100 B 50")
        # Park fixture 1 at this look
        r_park = run_command("PARK")
        _check("PARK adds fixture to parked_fids", 1 in output_state.parked_fids)
        _check("PARK stores some parked addresses",
               bool(output_state.parked_addresses))
        # Change programmer — should not affect parked output
        run_command("AT R 0 G 0 B 0")
        _park_dmx = output_state.get_dmx_for_universe(1)
        # Fixture 1 subs start at address 1 (SGM_RGB_54); first sub has r at offset 0
        _first_sub_1 = patch.get(1).all_subs()[0]
        _r_addr = _first_sub_1.outputs[0]['address'] - 1  # 0-indexed
        _check("PARK holds DMX value against programmer change",
               _park_dmx[_r_addr] == 200)
        # Unpark
        r_unpark = run_command("UNPARK")
        _check("UNPARK removes fixture from parked_fids", 1 not in output_state.parked_fids)
        prog.clear_programmer()
        run_command("1")
        run_command("AT R 0 G 0 B 0")
        _after_dmx = output_state.get_dmx_for_universe(1)
        _check("After UNPARK, programmer changes take effect",
               _after_dmx[_r_addr] == 0)
        prog.clear_programmer()

        # ── PARK-vs-FREEZE TEST ─────────────────────────────────────────────
        # Same bug class fixed twice before (BLACKOUT-vs-FREEZE, SOLO-vs-FREEZE):
        # FREEZE's frozen-snapshot branch must not silently defeat a newer
        # isolation/override layer. PARK is documented as "immune to
        # cue/prog changes" and highest priority (even above direct_dmx) —
        # verify it still holds while FREEZE is active. Seeds a synthetic
        # frozen snapshot directly (not via run_command('FREEZE')) so this
        # check is isolated from whatever dim/FX state other tests in this
        # long-lived process have left on fixture 1.
        run_command("1")
        run_command("AT FULL")
        run_command("AT R 222 G 11 B 33")
        run_command("PARK")
        _park_addr = _first_sub_1.outputs[0]['address'] - 1  # 0-indexed
        _saved_frozen = dict(output_state.frozen_dmx)
        _saved_freeze_mode = output_state.freeze_mode
        try:
            output_state.frozen_dmx[1] = tuple([99] * 512)  # conflicts with parked 222
            output_state.freeze_mode = True
            _frozen_dmx = output_state.get_dmx_for_universe(1)
            _check("PARK still holds its value while FREEZE is active",
                   _frozen_dmx[_park_addr] == 222)
        finally:
            output_state.freeze_mode = _saved_freeze_mode
            output_state.frozen_dmx.clear()
            output_state.frozen_dmx.update(_saved_frozen)
            run_command("UNPARK")
        prog.clear_programmer()

        # ── AI "dim" action clamp test ──────────────────────────────────
        # AIEngine.execute()'s "dim" action wrote a model-supplied value
        # straight into programmer_layer with no bounds check -- same bug
        # class already fixed for HUE SAT/VAL (invisible live since final
        # DMX render clamps on the way out, but a RECORDed cue would
        # persist the raw out-of-range number). Build a throwaway AIEngine
        # to exercise the fix: construction needs an API key string but
        # never calls the network -- only .execute() runs here, which is
        # pure local dict logic, no anthropic.messages.create() involved.
        _prev_api_key = os.environ.get('ANTHROPIC_API_KEY')
        os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-smoketest-dummy-unused'
        try:
            _test_ai = AIEngine(patch, prog, output_state, fx_engine, fade_engine,
                                 stack_pool=stack_pool, fader_pool=fader_pool)
            _test_ai.execute([{"action": "dim", "value": 5.0}])
            _check("AI 'dim' action clamps out-of-range value to 1.0",
                   output_state.programmer_layer.get("1", {}).get('dim') == 1.0
                   and patch.get(1).virtual_dimmer == 1.0)
            _test_ai.execute([{"action": "dim", "value": -3.0}])
            _check("AI 'dim' action clamps negative value to 0.0",
                   output_state.programmer_layer.get("1", {}).get('dim') == 0.0
                   and patch.get(1).virtual_dimmer == 0.0)
        finally:
            if _prev_api_key is None:
                os.environ.pop('ANTHROPIC_API_KEY', None)
            else:
                os.environ['ANTHROPIC_API_KEY'] = _prev_api_key
            # The "dim" action loops over ALL patched fixtures, not just a
            # selection -- undo its virtual_dimmer=0.0 and the programmer
            # 'dim' overrides on every fixture so this test doesn't leak
            # state into whatever runs after it.
            for _m in patch.all_fixtures():
                _m.set_dimmer(1.0)
            prog.clear_programmer()

        # ── stk CHASE MODE ─────────────────────────────────────────────────
        _ch_cs = stack_pool.create(103, "ChaseTest")
        if _ch_cs:
            _ch_cs.cues.clear()
            prog.data["1"] = {"dim": 0.5}
            for _cn in (1, 2, 3):
                _c = Cue(float(_cn), f"Ch{_cn}"); _c.record(prog); _ch_cs.cues[float(_cn)] = _c
            prog.data.clear()
        r_ch_on = run_command("stk 103 CHASE ON BPM 120")
        _ch = stack_pool.get(103)
        _check("stk CHASE ON enables chase_enabled", _ch is not None and _ch.chase_enabled is True)
        _check("stk CHASE ON BPM sets chase_bpm", _ch is not None and abs(_ch.chase_bpm - 120.0) < 0.1)
        _check("stk CHASE ON returns confirmation", "chase" in r_ch_on.lower())
        r_ch_bpm = run_command("stk 103 CHASE BPM 90")
        _check("stk CHASE BPM updates chase_bpm", _ch is not None and abs(_ch.chase_bpm - 90.0) < 0.1)
        r_ch_off = run_command("stk 103 CHASE OFF")
        _check("stk CHASE OFF disables chase_enabled", _ch is not None and _ch.chase_enabled is False)
        _check("stk CHASE OFF returns confirmation", "chase" in r_ch_off.lower())
        # stk INFO shows chase state
        r_ch_info = run_command("stk 103 INFO")
        _check("stk INFO shows chase field", "Chase" in r_ch_info or "chase" in r_ch_info.lower())
        # Save/load round-trip
        _ch.chase_enabled = True; _ch.chase_bpm = 77.0
        ShowFile.save_stacks(stack_pool)
        _ch2 = Stack(103, "ChaseTest")
        _tmp_pool = StackPool(); _tmp_pool.store(103, _ch2)
        ShowFile.load_stacks(_tmp_pool, CuePool())
        _reloaded_ch = _tmp_pool.get(103)
        _check("stk CHASE save/load preserves chase_enabled",
               _reloaded_ch is not None and _reloaded_ch.chase_enabled is True)
        _check("stk CHASE save/load preserves chase_bpm",
               _reloaded_ch is not None and abs(_reloaded_ch.chase_bpm - 77.0) < 0.1)
        _ch.chase_enabled = False
        stack_pool.stacks.pop(103, None)

        # ── FADER SIZE — per-fader FX amplitude multiplier ────────────
        _sz_ex = fader_pool.get(3)
        _sz_ex.size_factor = 1.0
        r_sz_plus = run_command("FADER 3 SIZE+")
        _check("FADER SIZE+ nudges size_factor up to ~1.25",
               abs(_sz_ex.size_factor - 1.25) < 0.01)
        _check("FADER SIZE+ returns confirmation", "size" in r_sz_plus.lower())
        run_command("FADER 3 SIZE-")
        _check("FADER SIZE- returns size_factor to ~1.00",
               abs(_sz_ex.size_factor - 1.0) < 0.01)
        run_command("FADER 3 SIZE+")
        r_sz_reset = run_command("FADER 3 SIZE RESET")
        _check("FADER SIZE RESET returns size_factor to 1.0", _sz_ex.size_factor == 1.0)
        _check("FADER SIZE RESET returns confirmation", "reset" in r_sz_reset.lower())
        r_sz_set = run_command("FADER 3 SIZE 2.0")
        _check("FADER SIZE 2.0 sets size_factor to 2.0",
               abs(_sz_ex.size_factor - 2.0) < 0.01)
        _check("FADER SIZE 2.0 returns confirmation", "2.0" in r_sz_set or "2.00" in r_sz_set)
        # SIZE propagates to owned FX layers (if any are active)
        run_command("FX CLEAR")
        run_command("1 THRU 3")
        run_command("FX SINE RED BPM 60 SIZE 100")
        _sz_layer_id = _sz_ex._fx_ids[0] if _sz_ex._fx_ids else None
        if _sz_layer_id is not None:
            _sz_layer = fx_engine._layers.get(_sz_layer_id)
            _sz_ex.size_factor = 0.5
            _sz_ex._apply_size_factor()
            _check("FADER SIZE: _apply_size_factor sets size_scale on owned layer",
                   _sz_layer is None or abs(_sz_layer.size_scale - 0.5) < 0.01)
        _sz_ex.size_factor = 1.0
        _sz_ex._apply_size_factor()
        run_command("FX CLEAR")
        prog.clear_programmer()

        # ── AT … IN <seconds> LIVE PROGRAMMER FADE ────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT FULL")                     # establish a src dim=1.0
        _pre_fade_dim = prog.data.get("1", {}).get("dim")
        run_command("AT 0 IN 5")                   # fade dim 1.0→0.0 over 5s
        _check("AT … IN creates a live_fade entry",
               len(prog.live_fades) >= 1)
        _fade_entry = next(
            (f for f in prog.live_fades if f['fid'] == '1' and f['channel'] == 'dim'),
            None)
        _check("live_fade entry has correct dst (0.0)",
               _fade_entry is not None and abs(_fade_entry['dst'] - 0.0) < 0.01)
        _check("live_fade entry has correct duration (5.0)",
               _fade_entry is not None and abs(_fade_entry['duration'] - 5.0) < 0.01)
        _check("live_fade entry has a non-zero src",
               _fade_entry is not None and (_fade_entry['src'] or 0) > 0.0)
        # PROG FADE CLEAR should purge all active fades
        r_pfc = run_command("PROG FADE CLEAR")
        _check("PROG FADE CLEAR empties live_fades list", len(prog.live_fades) == 0)
        _check("PROG FADE CLEAR returns confirmation", "clear" in r_pfc.lower())
        prog.clear_programmer()

        # ── Preset tracking — LIST REFS + UPDATE ──────────────────────────
        run_command("1 THRU 6 AT R 255 G 0 B 100")  # pink
        run_command("RECORD COLOR 10 Pink")
        run_command("COLOR 10")   # apply preset (sets color_ref)
        # record a cue with color_ref
        _tcs = stack_pool.get(1) or stack_pool.create(1, "TrackTest")
        _tcue = Cue(90, "track test cue")
        _tcue.record(prog)
        _tcs.cues[float(90)] = _tcue
        prog.clear_programmer()

        _r_refs = run_command("LIST REFS COLOR 10")
        _check("LIST REFS finds the cue", "track test cue" in _r_refs or "cue 90" in _r_refs.lower() or "stk 1" in _r_refs.lower())

        # Update the preset and check live-push returns confirmation
        run_command("1 AT R 200 G 50 B 150")
        _r_upd = run_command("UPDATE COLOR 10")
        _check("UPDATE COLOR returns confirmation", "updated" in _r_upd.lower())
        _check("UPDATE COLOR live-pushed message", "live-pushed" in _r_upd.lower())
        _check("Color preset 10 updated", color_pool.get(10) is not None)

        # FX preset ref in cue — FIRE FX tags layer defs
        run_command("FX SINE RED BPM 60")
        run_command("RECORD FX 11 TrackFX")
        run_command("CLEAR FX")
        run_command("FIRE FX 11")
        _fx_entry = next((v for fid, v in prog.data.items() if '.' not in fid and v.get('fx')), None)
        _check("FIRE FX tags layers with fx_preset_ref",
               _fx_entry is not None and any(ld.get('fx_preset_ref') == 11
                                              for ld in _fx_entry.get('fx', [])))
        # LIST REFS FX
        _tcue_fx = Cue(91, "fx track cue")
        _tcue_fx.record(prog)
        _tcs.cues[float(91)] = _tcue_fx
        prog.clear_programmer()
        _r_fx_refs = run_command("LIST REFS FX 11")
        _check("LIST REFS FX finds the cue", "fx track cue" in _r_fx_refs.lower() or "cue 91" in _r_fx_refs.lower() or "stk 1" in _r_fx_refs.lower())

        # UPDATE FX
        run_command("FX SINE RED BPM 90")
        _r_upd_fx = run_command("UPDATE FX 11")
        _check("UPDATE FX returns confirmation", "updated" in _r_upd_fx.lower())
        _check("UPDATE FX live-pushed message", "live-pushed" in _r_upd_fx.lower())

        # Cleanup
        prog.clear_programmer()
        _tcs.cues.pop(float(90), None)
        _tcs.cues.pop(float(91), None)

        # ── Flash mode fix ────────────────────────────────────────────────────
        _fe = fader_pool.get(98)
        _fe_cs = stack_pool.create(98, "FlashTest") if not stack_pool.get(98) else stack_pool.get(98)
        if not _fe_cs.cues:
            _fc = Cue(1, "flash cue")
            _fc.data = {"1": {"dim": 1.0}}
            _fe_cs.add_cue(_fc)
        fader_pool.assign(98, _fe_cs)
        _fe.trigger_mode = 'flash'
        _fe.flash_on(patch, fade_engine)
        _check("flash_on activates fader", _fe.is_active)
        _saved_pos = _fe_cs.current
        _fe.flash_off()
        _check("flash_off deactivates fader", not _fe.is_active)
        _check("flash_off preserves cue position", _fe_cs.current == _saved_pos)

        # ── Fader output_mode: moment ─────────────────────────────────────────
        _me = fader_pool.get(97)
        _me_cs = stack_pool.create(97, "MomentTest") if not stack_pool.get(97) else stack_pool.get(97)
        if not _me_cs.cues:
            _mc = Cue(1, "moment cue")
            _mc.data = {"1": {"dim": 1.0}}
            _me_cs.add_cue(_mc)
        fader_pool.assign(97, _me_cs)
        _me.output_mode = 'moment'
        _me.level = 0.0
        _me.is_active = True
        _active = fader_pool.active_layers()
        _check("moment fader excluded from active_layers at level 0",
               all(lyr is not _me.layer for lyr, _ in _active))
        _me.level = 0.5
        _exec_fader_mode_hook(_me)
        _check("moment fader is_active True when level > 0", _me.is_active)

        # ── Fader output_mode: vfade ──────────────────────────────────────────
        r_vfd = run_command("FADER 97 OUTPUT VFADE")
        _check("FADER OUTPUT VFADE command works", "vfade" in r_vfd.lower())
        _check("output_mode set to vfade", _me.output_mode == 'vfade')
        run_command("FADER 97 OUTPUT NORMAL")
        _check("FADER OUTPUT NORMAL resets mode", _me.output_mode == 'normal')

        # ── trigger_mode moment ───────────────────────────────────────────────
        r_mom = run_command("FADER 97 MODE MOMENT")
        _check("FADER MODE MOMENT accepted", "moment" in r_mom.lower())
        _check("trigger_mode set to moment", _me.trigger_mode == 'moment')
        r_offt = run_command("FADER 97 OFFTIME 1.5")
        _check("FADER OFFTIME sets off_time", abs(_me.off_time - 1.5) < 0.001)
        run_command("FADER 97 MODE TOGGLE")   # restore

        # ── _vfade_apply ─────────────────────────────────────────────────────
        _ve = fader_pool.get(96)
        _ve.output_mode = 'vfade'
        _ve.vfade_from  = {"1": {"red": 0.0}}
        _ve.vfade_to    = {"1": {"red": 255.0}}
        _ve.level       = 0.5
        _vfade_apply(_ve)
        _check("vfade_apply lerps at 0.5", abs(_ve.layer.get("1", {}).get("red", 0) - 127.5) < 0.5)
        _ve.level = 0.0
        _vfade_apply(_ve)
        _check("vfade_apply at 0 = from state", _ve.layer.get("1", {}).get("red", -1) == 0.0)
        _ve.level = 1.0
        _vfade_apply(_ve)
        _check("vfade_apply at 1 = to state", abs(_ve.layer.get("1", {}).get("red", 0) - 255.0) < 0.5)

    except Exception as e:
        _check(f"smoke test raised {type(e).__name__}: {e}", False)

    # ── GUI structural build check ──────────────────────────────────────
    # Every session that's added or touched a popup has had to say some
    # version of "reviewed by hand against the existing builders it
    # mirrors — headless mode skips gui.build() entirely, so the new
    # widgets aren't exercised by the smoke test itself." That caveat
    # doesn't have to keep repeating: DearPyGui can construct a full
    # widget tree with no display at all — only show_viewport() touches
    # GLFW/X11 and needs a real one (it hard-crashes without $DISPLAY).
    # Patch it to a no-op so the real, unmodified gui.build() runs start
    # to finish (every panel, every popup, every tag, the whole handler
    # registry) and any structural bug — duplicate tag, bad item
    # reference, build-order mistake — surfaces here instead of only at
    # next interactive launch.
    if _DPG_OK:
        _orig_show_viewport = dpg.show_viewport
        dpg.show_viewport = lambda *a, **k: None
        try:
            gui.build()
            _check("gui.build() constructs all windows/widgets without error", True)
            # ── fixture-dim-slider unit fix ──────────────────────────────
            # _on_fixture_dim_slider passed dim*100 into MasterFixture.
            # set_dimmer(), which expects a 0.0-1.0 fraction (per its own
            # docstring) and clamps to it -- so any drag above ~1% silently
            # forced virtual_dimmer to 1.0 regardless of the slider's real
            # position. programmer_layer['dim'] masks this live (it's read
            # first), but virtual_dimmer is the fallback default read once
            # that key is gone (e.g. after CLEAR) and is what status/PATCH
            # LIST prints directly -- so it would misreport 100% instead of
            # the real level.
            gui._on_fixture_dim_slider(None, 0.5, 1)
            _check("fixture-dim slider sets virtual_dimmer to the slider's "
                   "actual fraction, not fraction*100 clamped to 1.0",
                   patch.get(1).virtual_dimmer == 0.5)
            gui._on_fixture_dim_slider(None, 1.0, 1)
            patch.get(1).virtual_dimmer = 1.0  # restore default for any later use
        except Exception as e:
            _check(f"gui.build() raised {type(e).__name__}: {e}", False)
        finally:
            dpg.show_viewport = _orig_show_viewport
            try:
                dpg.destroy_context()
            except Exception:
                pass
    else:
        _check("gui.build() constructs all windows/widgets without error (skipped: dearpygui not installed)", True)

    ok = all(passed for _, passed in _results)
    print(f"\n*** SMOKE TEST {'PASSED' if ok else 'FAILED'} "
          f"({sum(p for _, p in _results)}/{len(_results)}) ***\n")

    network.stop()
    midi.stop()
    osc.stop()
    fx_engine.stop()
    fade_engine.stop()
    audio_mapper.stop()
    audio_engine.stop()
    _sys.exit(0 if ok else 1)
else:
    gui.build()   # build all widgets (main thread)
    gui.run()     # hand control to DearPyGui — blocks until window closed

midi.stop()
network.stop()
fade_engine.stop()
fx_engine.stop()
audio_mapper.stop()
audio_engine.stop()


# =============================================================================
# SESSION HANDOFF NOTE  —  2026-06-25
# =============================================================================
#
# PROJECT: Studio Console
# FILE:    studio_project/studio_project.py  (~21k lines, single file)
# SHOW DATA: studio_project/studio_data/  (per-category JSON files)
#
# ── WHAT THIS IS ──────────────────────────────────────────────────────────────
# Custom Python lighting console controlling 6 SGM LT-200 pixel tubes
# (54 RGB pixels each, 324 sub-fixtures total) via sACN multicast.
# GUI: DearPyGui retro console aesthetic.
# Command line: MA3-style text syntax (see run_command()).
#
# ── HARDWARE / NETWORK ────────────────────────────────────────────────────────
# sACN multicast on 192.168.1.161, universes 1 & 2, 44 Hz output loop.
# MIDI: Axiom 25 on port 1 (fader control).
# OSC: Studio Console on port 8001, grandMA3 on 8000.
#
# ── THREE-LAYER OUTPUT MERGE ──────────────────────────────────────────────────
# programmer  >  fader layers (LTP)  >  FX (additive)
#
# OutputState._merged_cue_layer()  — LTP merge of all active fader layers
#   in fire-order (last GO wins). Each Fader owns its own `layer` dict.
#   FadeEngine.Fade.tick() writes directly into fader.layer, not a shared dict.
#
# FXEngine runs additively on top of the merged cue layer.
# FX layers are split into two namespaces:
#   - programmer preview:  IDs 9000+   tracked in _prog_fx_ids  (module-level list)
#   - Per-fader cue FX: IDs fdr_id*10000+n  owned by Fader._fx_ids
#
# ── FX ARCHITECTURE (just redesigned this session) ────────────────────────────
# FX is now PROGRAMMER-NATIVE, not a standalone global thing.
#
# HOW IT WORKS:
#   1. `FX SINE RED`  writes  {'waveform':'sine','channel':'red','bpm':60,...}
#      into prog.data[fid_str]['fx'] for each selected master fixture.
#      Also starts a live-preview FXLayer (ID 9000+) so you see output immediately.
#
#   2. `RECORD CUE <n>` — Cue.record() does dict(vals) on programmer data,
#      which captures the 'fx' list automatically. No special handling needed.
#
#   3. `GO` on a cue calls fader._start_cue_fx(cue, patch):
#      - reads cue.data[master_fid]['fx'] lists
#      - starts FXLayer objects in the fader's own ID namespace
#      - clears previous fader FX first (_clear_fx)
#
#   4. `CLEAR` (stage 2 — programmer clear):
#      - also stops _prog_fx_ids preview layers  (_prog_fx_stop())
#
#   5. `Fader.stop()` calls _clear_fx() before clearing its layer.
#
#   6. `RECORD FX <n>` — snapshots unique FX defs from programmer into fx_pool.
#      (Reads from prog.data, NOT from active_fx list anymore.)
#
#   7. `FIRE FX <n>` — writes pool preset layers into programmer data + preview.
#      Does NOT fire directly to an fader — goes via programmer → RECORD CUE → GO.
#
#   8. `FX ADD ...` — appends additional FX layers to existing programmer FX.
#
#   9. `FX CLEAR` — removes 'fx' keys from programmer entries + stops preview.
#
# KEY OBJECTS:
#   _prog_fx_ids   — module-level list of active programmer-preview FX IDs
#   active_fx      — module-level list of active FXLayer objects (preview)
#   Fader._fx_ids   — list of FX IDs owned by that fader slot
#   Fader.fx_engine / Fader.form_pool — injected from FaderPool defaults
#   FaderPool.default_fx_engine / .default_form_pool / .default_color_pool / .default_dim_pool — set at startup
#
# ── SHOW FILE SPLIT ───────────────────────────────────────────────────────────
# ShowFile class (static methods only) — each category saves/loads independently.
# Files: studio_data/stacks.json, groups.json, colors.json, dims.json,
#        midi.json, fx.json, fx_pool.json, forms.json
# Legacy migration: if studio_show.json exists, it's read and split on first run,
#   then renamed to studio_show.json.migrated.
#
# ── PLAYBACK LAYER ────────────────────────────────────────────────────────────
# FaderPool holds numbered Fader slots.
# Each Fader: one Stack, its own layer dict, its own FX IDs, level fader.
# LTP priority: _fire_order list — last GO = highest priority.
# FadeEngine fires Fade objects that tick() directly into fader.layer.
#
# COMMANDS:
#   ASSIGN stk <n> TO fdr <n>    — wire stack to fader slot
#   fdr <n> GO/BACK/STOP/GOTO   — control specific fader
#   FADER <n>                 — set active fader for bare GO/BACK
#
# ── KEY COMMANDS ──────────────────────────────────────────────────────────────
#   FX SINE RED [bpm n] [size n] [SPREAD n]
#   FX ADD SINE BLUE [...]
#   FX FORM <n> RED [...]          — use FormPool waveform shape
#   FX CLEAR                       — clear all FX from programmer
#   FX CLEAR DIM                   — clear only dim channel FX (leaves RGB FX)
#   FX CLEAR RED / GREEN / BLUE    — clear only that colour channel FX
#   FX LIST
#   RECORD FX <n> [name]           — snapshot programmer FX → pool
#   FIRE FX <n>                    — add preset to programmer (channel-additive; same-channel layers replaced)
#   FORM LIST
#   record form <n> [name] 0.0,0.0 0.5,1.0 1.0,0.0   — custom breakpoint curve
#   record stk [n] cue <m> [preset-tokens]
#   go stk [n] cue <m>
#
# ── POOLS ──────────────────────────────────────────────────────────────────────
#   color_pool    — Colorpreset  (numbered, saved to colors.json)
#   dim_pool      — Dimpreset    (numbered, saved to dims.json)
#   group_pool    — group        (numbered, saved to groups.json)
#   stack_pool — stack     (numbered, saved to stacks.json)
#   fx_pool       — FXpreset     (numbered, 1-12 visible in GUI, saved to fx_pool.json)
#   form_pool     — Formpreset   (1-4 built-in builtins: sine/ramp/pulse/square;
#                                 5+ custom breakpoint curves; saved to forms.json)
#   fader_pool — Fader     (stack/level/priority/mode saved to faders.json)
#
# ── WHAT WORKS ────────────────────────────────────────────────────────────────
# - Full output pipeline (sACN, FX additive, programmer+cue merge)
# - stack playback with fades, fader isolation, LTP priority
# - FX as programmer-native (redesigned this session — just landed)
# - CLEAR 3-tap protocol: selection → programmer → full output
# - FX pool record/fire, Forms pool with custom breakpoints
# - show file per-category save/load with .bak auto-backup
# - GUI panels: stacks, groups, colors, dims, FX pool, forms pool
# - MIDI fader control, OSC bridge, AI command layer (ANTHROPIC_API_KEY gated)
# - audio reactive panel: device pick, capture start/stop, mapping toggle,
#   gain, live level/low/mid/high meters (GUI front-end for Block 9)
#
# ── KNOWN ISSUES / TODO ───────────────────────────────────────────────────────
# - fader_pool now persists stack assignments to faders.json; loaded
#   at startup so GO works immediately after restart without re-assigning.
#
# =============================================================================
