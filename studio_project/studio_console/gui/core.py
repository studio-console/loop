"""GUIEngine's base: __init__, popup-layout persistence, build(), the main input/history/global-keyboard handlers, the command-log helpers (_log/_log_error — physically misplaced inside the original FX-editor method cluster, relocated here since every mixin uses them), the update loop, and the giant _tick() method. Also holds every class-level constant (layout dimensions, popup tag lists, etc.) and the class docstring — consolidated here from their original scattered positions throughout the class body, since Python class-body constants must live in one physical class definition to resolve each other correctly (e.g. _POOL_H = _H_P1), but are accessible from every other mixin via normal attribute inheritance once GUIEngine composes them all.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

import os
import json
import time
import signal

import threading

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.models.fixtures import MasterFixture
from studio_console.paths import _SCRIPT_DIR
from studio_console.show import ShowFile


class GUIEngineCore:
    """
    DearPyGui retro console.

    Usage:
        gui = GUIEngine(midi, fx_engine, fade_engine, output_state,
                        patch, stacks, prog, cue_go_fn, cue_back_fn,
                        goto_fn, ai=ai_instance)
        gui.build()    # set up all windows/widgets (main thread)
        gui.run()      # hand control to DearPyGui (blocks until closed)
    """
    target_registry = {}
    _POPUP_TAGS = [
        "patch_window", "osc_window", "midi_window", "fx_editor_window",
        "keys_window", "changelog_window", "pages_window", "monitors_window",
        "ai_history_window", "attr_window", "ai_prompts_window", "ai_bar_window",
        "color_picker_window", "speed_master_window", "fader_page_window",
        "audio_window", "fx_params_window",
    ]
    # Was os.path.dirname(os.path.abspath(__file__)) — that resolved
    # relative to studio_project.py itself when this class lived there
    # directly. Now that it's in gui/core.py, __file__ would resolve two
    # directories too deep. _SCRIPT_DIR (studio_console/paths.py) is the
    # same anchor, always the real studio_data/ dir regardless of
    # STUDIO_HEADLESS (unlike DATA_DIR, which paths.py redirects to a
    # scratch dir in headless mode) — preserves exact original behavior.
    _POPUP_LAYOUT_FILE = os.path.join(
        _SCRIPT_DIR, "studio_data", "popup_layout.json"
    )
    _POPUP_REFRESH = {
        "changelog_window": "_refresh_changelog_popup",
        "patch_window":     "_refresh_patch_table",
        "pages_window":     "_refresh_pages_table",
        "osc_window":       "_refresh_osc_table",
    }
    _W          = 1920
    _H          = 1080
    _H_MAIN     = 512   # main 3-col area — tall enough for all left-col FX controls
    _H_P1       = 182   # pool row 1: 4×30btn + 3×5gap + header + 12WP ≈ 170px content
    _H_P2       = 182   # pool row 2
    _H_FORMS    =  56   # forms single row (unused — _build_forms_panel computes own height)
    _H_MON      = 270   # monitor popup panel height (not in main layout)
    _W_LEFT     = 380
    _W_RIGHT    = 720
    _POOL_SLOTS = 24    # 4 rows × 6 cols per panel
    _POOL_COLS  = 6
    _PANEL_W    = 630   # 3 panels + 2 ItemSpacing gaps fit 1920 (3×630+12 = 1902)
    _BTN_W      =  97   # exactly fits 6 columns in a 630-wide panel (97×6+5×6 = 612)
    _BTN_H      =  30   # 4 rows × 30 + 3 × 5gap + header = ~155px content
    _POOL_H     = _H_P1
    _FX_WAVEFORMS = ['sine', 'ramp', 'pulse', 'square', 'triangle', 'sawtooth', 'flicker']
    _FX_CHANNELS  = [
        'dim', 'red', 'green', 'blue',
        'pan', 'tilt', 'pan_fine', 'tilt_fine',
        'gobo', 'gobo_rot', 'gobo2', 'gobo2_rot',
        'zoom', 'focus', 'iris', 'shutter1',
        'color', 'prism', 'frost', 'animation', 'control', 'macro', 'dimmer',
    ]
    # Display items for the FX editor's "dir" column — see FXLayer's
    # distribution/direction docstring in engine/fx.py for what each
    # actually does. mirror/cluster/random (elsewhere in the FX editor)
    # are independent checkboxes, not part of this list — they combine
    # freely rather than being one mutually-exclusive mode. Deliberately
    # renamed away from grandMA2/MA3's own terms for these concepts
    # (block/wings/group/random-style effect grouping), per explicit
    # instruction — this codebase's own names, not theirs.
    _FX_DIRECTIONS = ['fwd', 'rev', 'bounce']
    _FX_DIR_TO_INTERNAL = {'fwd': 'forward', 'rev': 'reverse', 'bounce': 'bounce'}
    _FX_DIR_FROM_INTERNAL = {'forward': 'fwd', 'reverse': 'rev', 'bounce': 'bounce'}
    _ERR_PREFIXES = ("Usage:", "Error:", "bad ", "not found", "unknown verb",
                     "Unknown", "invalid", "no stack", "no active", "not set",
                     "AI error")
    # Touch-target sizing: 40px buttons and 30px badges land close to the
    # ~44pt minimum tap target most touch UI guidelines recommend, given
    # the 17px UI font this app already uses. The cue list and fader are
    # both the slot's near-full width, stacked (not side by side) — every
    # cue is readable, and the fader is still a proper touch-width strip,
    # without the two competing for the same horizontal space.
    _FPG_SLOTS        = 15
    _FPG_SLOT_W       = 120    # initial slot width (reflow updates dynamically)
    _FPG_BTN_W        = 108    # initial button width
    _FPG_BTN_H        = 40     # button height — real touch target (was 24)
    _FPG_BADGE_H      = 30     # priority/output-mode badge height (was hardcoded 18)
    _FPG_CUELIST_ITEMS = 6     # visible cue rows before the listbox scrolls
    _FPG_CUELIST_ROW_H = 22    # px per listbox row (matches the left-column
                                # cue list's own row-height estimate, core.py)
    # Every fixed-height row in a fader-page slot, in build order, plus the
    # item-spacing gap before each (theme.py's ItemSpacing.y=5) and the
    # child_window's own top+bottom padding (WindowPadding.y=6 each side).
    # Whatever's left of the slot's total height after this goes to the
    # fader row — computed here, not hand-tuned, specifically because a
    # hand-tuned guess is what caused the fader page's own buttons to get
    # silently clipped before (no_scrollbar=True hides overflow instead of
    # erroring, so a wrong guess is invisible until someone's actually
    # looking at it). _fpg_reflow reuses this same constant so the two
    # can't drift apart from each other.
    _FPG_FIXED_ROWS_H = (_FPG_BADGE_H + 20                     # badges, name
                          + _FPG_CUELIST_ITEMS * _FPG_CUELIST_ROW_H + 8  # cue list
                          + 20                                  # level %
                          + _FPG_BTN_H * 3 + 6 + _FPG_BTN_H      # A/B/C, sep, trig
                          ) + 5 * 9 + 6 * 2
    _FPG_SLOT_H  = 600    # initial slot height (reflow updates dynamically)
    _FPG_FADER_H = max(80, _FPG_SLOT_H - _FPG_FIXED_ROWS_H)  # initial fader h
    _AI_CHIPS = [
        ("warm wash",    "warm amber golden wash on all fixtures, moderate brightness"),
        ("strobe",       "fast white strobe on all fixtures"),
        ("blackout",     "full blackout, all fixtures off immediately"),
        ("rgb chase",    "RGB color chase effect rippling through all fixtures"),
        ("cool wash",    "cool blue-white wash, clean and bright"),
        ("purple haze",  "deep violet-purple haze atmosphere"),
        ("sunrise",      "slow sunrise from deep red to orange to gold"),
        ("pulse",        "slow red breathing pulse on all fixtures"),
        ("thunderstorm", "chaotic random flicker simulating lightning"),
        ("disco",        "fast random colourful disco effect"),
    ]
    _tick_first           = True    # sync one-shot values on first tick
    _auto_save_t          = 0.0    # monotonic time of last auto-save
    _AUTO_SAVE_INT        = 300.0  # seconds between auto-saves (5 min)
    _save_status_clear_at = 0.0   # monotonic time to clear the save status label

    def __init__(self, midi, fx_engine, fade_engine, output_state, patch,
                 stacks, prog, go_fn, back_fn, goto_fn, reload_fn=None, ai=None,
                 save_fn=None, cmd_fn=None,
                 group_pool=None, color_pool=None, dim_pool=None,
                 cue_pool=None, stack_pool=None, active_fader=None,
                 fader_pool=None, fx_pool=None, form_pool=None,
                 rate_pool=None, size_pool=None, spread_pool=None,
                 speed_master_pool=None,
                 attr_pools=None, osc=None,
                 library=None, save_patch_fn=None, fx_params=None,
                 audio_engine=None, audio_mapper=None, prog_fx_ids=None):
        self._midi       = midi
        self._fx         = fx_engine
        self._fade       = fade_engine
        self._out        = output_state
        self._patch      = patch
        self._stacks     = stacks       # {stack_id: Stack}
        self._prog       = prog
        self._go         = go_fn
        self._back       = back_fn
        self._goto       = goto_fn         # goto_fn(cue_num)
        self._reload     = reload_fn       # reload_fn() — re-fire current cue
        self._ai         = ai
        self._osc        = osc
        self._groups     = group_pool
        self._colors     = color_pool
        self._dims       = dim_pool
        self._cue_pool        = cue_pool
        self._stack_pool   = stack_pool
        self._active_fader = active_fader  # list[int] so mutations are visible
        self._fader_pool   = fader_pool
        self._fx_pool    = fx_pool
        self._form_pool  = form_pool
        self._rate_pool   = rate_pool
        self._size_pool   = size_pool
        self._spread_pool = spread_pool
        self._speed_pool  = speed_master_pool
        self._attr_pools  = attr_pools or {}   # {name: AttributePool}
        self._library     = library
        self._fx_params   = fx_params
        self._save        = save_fn         # save_fn() → ShowFile.save()
        self._save_patch  = save_patch_fn   # save_patch_fn() → ShowFile.save_patch()
        self._cmd         = cmd_fn          # cmd_fn(str) → result str
        self._audio_engine = audio_engine   # AudioEngine — capture + level/band analysis
        self._audio_mapper = audio_mapper   # AudioMapper — level/band → output_state.audio_layer
        self._prog_fx_ids  = prog_fx_ids if prog_fx_ids is not None else []  # live-tracked list, shared by reference with state.py

        self._cmd_log     = []         # command history lines
        self._cmd_history = []         # entered commands for ↑↓ recall
        self._cmd_hist_i  = -1        # history cursor

        self._flash_held  = {}         # {fdr_id: bool} — tracks held state of FLASH buttons
        self._col_btn_themes  = {}     # {slot_n: ((r,g,b), theme_id)} — per-color-preset button themes
        self._dim_btn_themes  = {}     # {slot_n: (level, theme_id)} — per-dim-preset button themes
        self._out_bar_themes  = {}     # {fid: ((r,g,b), theme_id)} — output monitor bar tints
        self._prog_bar_themes = {}     # {fid: ((r,g,b), theme_id)} — programmer bar tints
        self._tap_times       = []     # monotonic timestamps of recent BPM taps
        self._error_flash_time = None  # monotonic time of last _log_error call

        self._learn_pending      = None    # (ch, number) captured by learn
        self._learn_target       = None    # display name chosen in dropdown
        self._learn_type         = 'cc'    # 'cc' or 'note'
        self._learn_armed_type   = 'cc'    # saved copy — survives MIDI thread clearing _learn_type
        self._learn_armed        = False
        self._pending_table_refresh = False  # set from MIDI thread; consumed by main thread _tick

        # Tags for dynamic MIDI table rows — key=(ch,num,type)
        self._map_rows = {}
        # Reassign flow: stores {'type','ch','num','label'} when user clicks ► on a row
        self._reassign_pending = None
        self._ai_history       = []   # list of {ts, prompt, summary, actions}
        self._ai_prompts       = []   # list of {name, prompt} — user-editable AI prompt presets
        self._fpg_page          = 1    # current fader-page bank (1-based); slot N shows fdr (page-1)*15+N
        self._fpg_last_win_size = (0, 0)
    # Widget values (not window pos/size) that need to survive a restart —
    # currently just the color picker's "live" checkbox, which was
    # silently resetting to its default_value=True on every launch with
    # no visible sign it had reset, reported as "changes the programmer
    # even when live is unchecked" (it wasn't still unchecked by the time
    # that was observed — it had reset back to checked since the last
    # restart). Add more (tag, "value_key") pairs here if another toggle
    # needs the same treatment.
    _PERSISTED_CHECKBOXES = [("cpick_live", "cpick_live")]
    def _save_popup_layout(self):
        layout = {}
        for tag in self._POPUP_TAGS:
            try:
                cfg = dpg.get_item_configuration(tag)
                # 'pos' is NOT a get_item_configuration key for a window
                # (confirmed: absent from its key set entirely) — using
                # cfg.get("pos", [100, 100]) always silently returned the
                # fallback, so every popup's real position was never once
                # actually saved, only ever overwritten back to (100, 100)
                # (or whatever a given popup's own hardcoded build-time
                # default was, on whichever save happened to run first)
                # on the next restore. dpg.get_item_pos() is the real
                # (and only) way to read a window's current position.
                layout[tag] = {
                    "pos":    list(dpg.get_item_pos(tag)),
                    "width":  int(cfg.get("width",   700)),
                    "height": int(cfg.get("height",  400)),
                    "show":   bool(dpg.is_item_shown(tag)),
                }
            except Exception:
                pass
        values = {}
        for tag, key in self._PERSISTED_CHECKBOXES:
            try:
                values[key] = bool(dpg.get_value(tag))
            except Exception:
                pass
        if values:
            layout["__values__"] = values
        try:
            os.makedirs(os.path.dirname(self._POPUP_LAYOUT_FILE), exist_ok=True)
            with open(self._POPUP_LAYOUT_FILE, "w") as f:
                json.dump(layout, f, indent=2)
        except Exception:
            pass
    def _load_popup_layout(self):
        try:
            with open(self._POPUP_LAYOUT_FILE) as f:
                layout = json.load(f)
            values = layout.pop("__values__", {})
            for tag, key in self._PERSISTED_CHECKBOXES:
                if key in values:
                    try:
                        dpg.set_value(tag, bool(values[key]))
                    except Exception:
                        pass
            # Clamp restored positions to stay on-screen — belt-and-
            # suspenders against whatever produces an off-screen saved
            # position (DPI/scale mismatch between the save and load
            # sessions, a different display arrangement, etc.): keep at
            # least a corner of the window inside the current viewport
            # rather than trusting the saved coordinates blindly.
            max_x = max(0, int(getattr(self, '_vp_w', 1920)) - 100)
            max_y = max(0, int(getattr(self, '_vp_h', 1040)) - 60)
            for tag, cfg in layout.items():
                try:
                    pos = [min(max(0, int(cfg["pos"][0])), max_x),
                           min(max(0, int(cfg["pos"][1])), max_y)]
                    dpg.configure_item(tag, pos=pos,
                                       width=cfg["width"], height=cfg["height"])
                    if cfg.get("show"):
                        refresh = self._POPUP_REFRESH.get(tag)
                        if refresh:
                            getattr(self, refresh)()
                        dpg.show_item(tag)
                except Exception:
                    pass
        except Exception:
            pass
    def build(self):
        if not _DPG_OK:
            print("  GUI: dearpygui not installed — pip install dearpygui")
            return

        dpg.create_context()
        _apply_theme()
        self._surface_font, self._mono_font = _setup_fonts()
        self._go_theme       = _make_go_theme()
        self._back_theme     = _make_back_theme()
        self._fade_bar_theme = _make_fade_bar_theme()
        self._alert_btn_theme     = _make_alert_btn_theme()
        self._transport_go_theme  = _make_transport_go_theme()
        self._dim_btn_theme       = _make_dim_btn_theme()
        self._numpad_digit_theme  = _make_numpad_digit_theme()
        self._pool_live_theme     = _make_pool_live_theme()
        self._pool_empty_theme    = _make_pool_empty_theme()
        self._out_moment_theme    = _make_out_moment_theme()
        self._out_vfade_theme     = _make_out_vfade_theme()
        self._trig_flash_theme    = _make_trig_flash_theme()
        self._trig_moment_theme   = _make_trig_moment_theme()
        self._pri_hi_theme        = _make_pri_hi_theme()
        self._pri_lo_theme        = _make_pri_lo_theme()
        self._go_btn_theme        = _make_go_btn_theme()
        self._stop_btn_theme      = _make_stop_btn_theme()
        self._active_slot_theme   = _make_active_slot_theme()
        self._fpg_fader_theme     = _make_fpg_fader_theme()

        W, H = 1920, 1040   # trimmed from 1080: macOS menu bar eats ~25-38px off a
                            # non-resizable full-height viewport, clipping the bottom
        self._vp_w, self._vp_h = W, H   # stash for overlay builder (viewport not yet created)

        with dpg.window(tag="main", no_close=True, no_collapse=True,
                        no_move=True, no_resize=True, no_title_bar=True):
            # Scrolling left ON (was off): stacked panels (header + 3-col row +
            # pools row + monitors row + AI bar) can exceed the visible viewport
            # height, and with no_scrollbar the overflow was silently clipped
            # with no way to reach it. Scrolling is a safe fallback regardless
            # of the exact overflow amount, which isn't verifiable without a
            # real display.
            self._build_header()
            with dpg.group(horizontal=True):
                self._build_left_column()
                self._build_right_column()
                self._build_stage_panel()
            self._build_pools_row()
        self._build_osc_popup()
        self._build_midi_popup()
        self._build_patch_popup()
        self._build_keys_popup()
        self._build_fx_editor_popup()
        self._build_cue_timing_popup()
        self._build_changelog_popup()
        self._build_pages_popup()
        self._build_attr_popup()
        self._build_fx_params_popup()
        self._build_monitors_popup()
        self._build_ai_bar_popup()
        self._build_ai_history_popup()
        self._build_ai_prompts_popup()
        self._build_color_picker_popup()
        self._build_speed_master_popup()
        self._build_fader_page_popup()
        self._build_audio_popup()

        with dpg.handler_registry():
            dpg.add_key_press_handler(dpg.mvKey_Delete,
                                      callback=self._on_delete_key)
            # Route printable keys to cmd_input when no text/number widget has focus.
            # This lets the user type commands immediately after clicking soft-buttons
            # without needing to click the input field first — and avoids the DPG
            # focus-transfer bug where the input text gets select-all'd on focus gain.
            _letter_keys = [
                (dpg.mvKey_A,'a','A'),(dpg.mvKey_B,'b','B'),(dpg.mvKey_C,'c','C'),
                (dpg.mvKey_D,'d','D'),(dpg.mvKey_E,'e','E'),(dpg.mvKey_F,'f','F'),
                (dpg.mvKey_G,'g','G'),(dpg.mvKey_H,'h','H'),(dpg.mvKey_I,'i','I'),
                (dpg.mvKey_J,'j','J'),(dpg.mvKey_K,'k','K'),(dpg.mvKey_L,'l','L'),
                (dpg.mvKey_M,'m','M'),(dpg.mvKey_N,'n','N'),(dpg.mvKey_O,'o','O'),
                (dpg.mvKey_P,'p','P'),(dpg.mvKey_Q,'q','Q'),(dpg.mvKey_R,'r','R'),
                (dpg.mvKey_S,'s','S'),(dpg.mvKey_T,'t','T'),(dpg.mvKey_U,'u','U'),
                (dpg.mvKey_V,'v','V'),(dpg.mvKey_W,'w','W'),(dpg.mvKey_X,'x','X'),
                (dpg.mvKey_Y,'y','Y'),(dpg.mvKey_Z,'z','Z'),
                (dpg.mvKey_0,'0',')'),(dpg.mvKey_1,'1','!'),(dpg.mvKey_2,'2','@'),
                (dpg.mvKey_3,'3','#'),(dpg.mvKey_4,'4','$'),(dpg.mvKey_5,'5','%'),
                (dpg.mvKey_6,'6','^'),(dpg.mvKey_7,'7','&'),(dpg.mvKey_8,'8','*'),
                (dpg.mvKey_9,'9','('),
                (dpg.mvKey_Spacebar,' ',' '),
                (dpg.mvKey_Period,'.','>'),(dpg.mvKey_Minus,'-','_'),
                (dpg.mvKey_Slash,'/','?'),
            ]
            for _k, _lo, _hi in _letter_keys:
                dpg.add_key_press_handler(_k, callback=self._on_global_char,
                                          user_data=(_lo, _hi))
            dpg.add_key_press_handler(dpg.mvKey_Back,
                                      callback=self._on_global_backspace)
            dpg.add_key_press_handler(dpg.mvKey_Return,
                                      callback=self._on_global_enter)
            dpg.add_key_press_handler(dpg.mvKey_NumPadEnter,
                                      callback=self._on_global_enter)
            dpg.add_key_press_handler(dpg.mvKey_F4,
                                      callback=lambda *_: self._back())
            dpg.add_key_press_handler(dpg.mvKey_F5,
                                      callback=lambda *_: self._go())
            dpg.add_key_press_handler(dpg.mvKey_S,
                                      callback=self._on_ctrl_s)
            dpg.add_key_press_handler(dpg.mvKey_Z,
                                      callback=self._on_ctrl_z)
            dpg.add_key_press_handler(dpg.mvKey_Up,
                                      callback=self._on_hist_up)
            dpg.add_key_press_handler(dpg.mvKey_Down,
                                      callback=self._on_hist_down)
            dpg.add_mouse_click_handler(callback=self._on_global_mouse_click)

        # Apply per-item themes after widgets are built
        try:
            dpg.bind_item_theme("go_btn",           self._transport_go_theme)
            dpg.bind_item_theme("back_btn",         self._back_theme)
            dpg.bind_item_theme("numpad_digit_group", self._numpad_digit_theme)
            dpg.bind_item_theme("hdr_close_btn",    self._alert_btn_theme)
        except Exception:
            pass

        dpg.create_viewport(title="Studio Console", width=W, height=H,
                            resizable=True, x_pos=0, y_pos=32)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        # Default to fullscreen on launch (was windowed) — DPG's own
        # fullscreen toggle, not a manual viewport resize, so exiting it
        # (OS-dependent shortcut, e.g. Ctrl+Cmd+F on macOS) still works
        # normally afterward.
        dpg.toggle_viewport_fullscreen()
        dpg.set_primary_window("main", True)
    def _on_cmd_execute(self):
        raw = dpg.get_value("cmd_input").strip()
        if not raw:
            return
        dpg.set_value("cmd_input", "")
        dpg.focus_item("cmd_input")

        # Save to history
        self._cmd_history.append(raw)
        self._cmd_hist_i = -1

        # Echo input
        self._log(f"> {raw}")

        # Route to cmd_fn; it returns a result string to display
        if self._cmd:
            result = self._cmd(raw)
            if result:
                is_err = any(str(result).startswith(p) for p in self._ERR_PREFIXES)
                for line in str(result).splitlines():
                    if is_err:
                        self._log_error(f"  {line}")
                    else:
                        self._log(f"  {line}")

        # Feed command into AI history for future context
        if self._ai:
            try:
                self._ai.push_cmd_history(raw)
            except Exception:
                pass
    def _on_delete_key(self):
        # Only fire CLEAR when cmd_input is empty (so Delete still edits text normally)
        if dpg.get_value("cmd_input"):
            return
        if self._cmd:
            result = self._cmd("CLEAR")
            self._log("> clear")
            if result:
                self._log(f"  {result}")
        dpg.focus_item("cmd_input")
    def _log(self, line):
        self._cmd_log.append(line)
        if len(self._cmd_log) > 200:
            self._cmd_log = self._cmd_log[-200:]
        try:
            dpg.set_value("cmd_log", "\n".join(self._cmd_log))
            dpg.set_y_scroll("cmd_log_win", 99999)
        except Exception:
            pass
        # Clear any pending error flash on the next non-error log line
        if self._error_flash_time is not None:
            self._error_flash_time = None
            try:
                dpg.set_value("cmd_error_flash", "")
            except Exception:
                pass
    def _log_error(self, line):
        import time as _time
        self._log(f"⚠ {line}")
        self._error_flash_time = _time.monotonic()
        try:
            dpg.set_value("cmd_error_flash", f"⚠  {line}")
        except Exception:
            pass
    def _on_save(self):
        # GUIEngine (the final composed class) isn't importable at module
        # level here — deferred import, same pattern used throughout this
        # split.
        from __main__ import GUIEngine
        if self._save:
            self._save()
            dpg.set_value("hdr_save_status", "  saved ✓")
            GUIEngine._save_status_clear_at = time.monotonic() + 3.0
        else:
            dpg.set_value("hdr_save_status", "  no save_fn")
    def start_update_loop(self):
        """Start background thread that refreshes live data at 20 Hz."""
        self._running = True
        t = threading.Thread(target=self._update_loop, daemon=True)
        t.start()
    def _update_loop(self):
        while self._running and dpg.is_dearpygui_running():
            try:
                self._tick()
            except Exception:
                pass
            time.sleep(0.05)
        self._running = False
    def _tick(self):
        self._tick_first_sync()
        self._tick_deferred_maintenance()
        self._tick_prog_live_fades()

        self._tick_pools()
        self._tick_stage()
        self._tick_fader_page()
        self._tick_audio()

        self._tick_status_bar()
        self._tick_playbacks_and_faders()
        self._tick_cue_list()
        self._tick_fx_header()
        self._tick_programmer_monitor()
        self._tick_output_monitor()
        self._tick_midi_osc()
        self._tick_autosave()

    def _tick_first_sync(self):
        # Deferred import — see _on_save above for rationale.
        from __main__ import GUIEngine
        # One-shot sync on first tick — apply loaded values to GUI widgets
        if GUIEngine._tick_first:
            GUIEngine._tick_first = False
            try:
                if self._out:
                    dpg.set_value("stage_master_fader",
                                  int(self._out.master_level * 100))
            except Exception:
                pass
            # _fader_dim is restored from state for MIDI soft-takeover,
            # but NOT applied to programmer_layer on boot — fixtures start
            # at whatever their cue/default says, not the last fader position.
            # Auto-reload all faders that have a saved cue position.
            # Fires with instant (0s) fade so output is live on first frame.
            try:
                if self._cmd:
                    reloaded = 0
                    for ex in self._fader_pool.faders.values():
                        stk = ex.stack
                        if stk and stk.current is not None:
                            prev = (ex.time_override_on,
                                    ex.time_override_fade,
                                    ex.time_override_delay)
                            ex.time_override_on    = True
                            ex.time_override_fade  = 0.0
                            ex.time_override_delay = 0.0
                            try:
                                ex.reload(self._patch, self._fade)
                                ex.is_active = True
                                # Without this, the fader's cue data is
                                # fully correct but invisible in real DMX
                                # output: OutputState.active_layers() only
                                # merges faders present in
                                # FaderPool._fire_order (LTP priority
                                # order), which starts empty every launch
                                # and is never restored from saved state —
                                # a fader only enters it via bump_priority.
                                # The manual RELOAD command's cue_reload()
                                # already calls this; auto-reload silently
                                # didn't, which is exactly why typing
                                # RELOAD by hand "fixed" it and restarting
                                # kept losing that fix again.
                                self._fader_pool.bump_priority(ex.fdr_id)
                                reloaded += 1
                            finally:
                                (ex.time_override_on,
                                 ex.time_override_fade,
                                 ex.time_override_delay) = prev
                    if reloaded:
                        self._log(f"↺  auto-reload — {reloaded} stack(s) live")
            except Exception as _e:
                self._log(f"auto-reload error: {_e}")

            # Restore any live-preview programmer FX. ShowFile.load_programmer()
            # (called during state.py's boot, before the GUI/run_command even
            # exist) already restored prog.data — including any per-fixture
            # 'fx' entries — but that's just the *definition*; nothing yet
            # told fx_engine to actually start the oscillating layer. Same
            # "data restored correctly but not actually running" shape as
            # the fader DMX-on-restart bug above, same fix idea: do the one
            # rebuild call once the whole app is wired.
            try:
                from __main__ import _prog_fx_rebuild
                if self._prog and any('fx' in v for v in self._prog.data.values()):
                    _prog_fx_rebuild()
                    self._log("↺  programmer fx restored")
            except Exception as _e:
                self._log(f"programmer fx restore error: {_e}")

    def _tick_deferred_maintenance(self):
        # Consume deferred MIDI table rebuild (must be on main thread)
        if self._pending_table_refresh:
            self._pending_table_refresh = False
            self._refresh_midi_table()

        # Auto-clear error flash after 8 s if operator doesn't run another command
        if self._error_flash_time is not None:
            import time as _time
            if _time.monotonic() - self._error_flash_time > 8.0:
                self._error_flash_time = None
                try:
                    dpg.set_value("cmd_error_flash", "")
                except Exception:
                    pass

    def _tick_prog_live_fades(self):
        # Advance live programmer fades (AT … IN <seconds>)
        if self._prog and self._prog.live_fades:
            import time as _t
            _now = _t.monotonic()
            _still_active = []
            for _fade in self._prog.live_fades:
                _elapsed = _now - _fade['start']
                _dur     = _fade['duration']
                _fid     = _fade['fid']
                _ch      = _fade['channel']
                _src     = _fade['src']
                _dst     = _fade['dst']
                if _elapsed >= _dur:
                    # Fade complete — write final value
                    self._prog.data.setdefault(_fid, {})[_ch] = _dst
                else:
                    # Interpolate
                    _frac = _elapsed / _dur
                    _val  = _src + (_dst - _src) * _frac
                    self._prog.data.setdefault(_fid, {})[_ch] = _val
                    _still_active.append(_fade)
            self._prog.live_fades = _still_active

    def _tick_status_bar(self):
        # ── Status bar: programmer + selection ──────────────────
        prog_data   = self._prog.data if self._prog else {}
        prog_active = any(v for v in prog_data.values() if v)
        try:
            if prog_active:
                # Compute average RGB across all sub-fixtures in programmer
                r_sum = g_sum = b_sum = n = 0
                for fid, vals in prog_data.items():
                    if '.' in fid and vals:
                        r_sum += vals.get('red',   0)
                        g_sum += vals.get('green', 0)
                        b_sum += vals.get('blue',  0)
                        n += 1
                if n > 0:
                    mix = (max(60, r_sum // n), max(60, g_sum // n),
                           max(60, b_sum // n), 255)
                    dot_col = mix
                else:
                    dot_col = _C_ACCENT
                dpg.configure_item("sb_prog_dot", color=dot_col)
                dpg.configure_item("sb_prog_lbl", color=_C_ACCENT)
                dpg.set_value("sb_prog_lbl", "programmer  dirty")
            else:
                dpg.configure_item("sb_prog_dot", color=_C_DIM)
                dpg.configure_item("sb_prog_lbl", color=_C_DIM)
                dpg.set_value("sb_prog_lbl", "programmer  clear")
        except Exception:
            pass

        # BLIND indicator (button — clickable toggle)
        try:
            blind = self._out.blind if self._out else False
            dpg.configure_item("sb_blind_lbl",
                               label="● blind" if blind else "○ blind")
            theme = self._alert_btn_theme if blind else self._dim_btn_theme
            if theme:
                dpg.bind_item_theme("sb_blind_lbl", theme)
        except Exception:
            pass

        # BLACKOUT indicator (button — clickable toggle)
        try:
            bbo = (self._out.master_level == 0.0) if self._out else False
            dpg.configure_item("sb_bbo_lbl",
                               label="● blackout" if bbo else "○ blackout")
            theme = self._alert_btn_theme if bbo else self._dim_btn_theme
            if theme:
                dpg.bind_item_theme("sb_bbo_lbl", theme)
            # Also sync master fader widget
            if bbo:
                try:
                    if not dpg.is_item_active("stage_master_fader"):
                        dpg.set_value("stage_master_fader", 0)
                except Exception:
                    pass
        except Exception:
            pass

        # HIGHLIGHT indicator (button — clickable toggle; syncs selection each tick)
        try:
            hl = self._out.highlight_mode if self._out else False
            dpg.configure_item("sb_hl_lbl", label="● highlight" if hl else "○ highlight")
            theme = self._go_theme if hl else self._dim_btn_theme
            if theme:
                dpg.bind_item_theme("sb_hl_lbl", theme)
            if hl:
                self._sync_highlight_selection()
        except Exception:
            pass

        try:
            sel = self._prog.selection if self._prog else []
            sel_ids = {f.fixture_id if isinstance(f, MasterFixture)
                       else getattr(f, 'master_id', None) for f in sel}
            sel_ids.discard(None)
            for master in self._patch.all_fixtures():
                fid    = master.fixture_id
                active = fid in sel_ids
                theme  = self._go_theme if active else self._dim_btn_theme
                if theme:
                    try:
                        dpg.bind_item_theme(f"sb_sel_{fid}", theme)
                    except Exception:
                        pass
        except Exception:
            pass

        # CLEAR button — lights up (go_theme) when programmer has data or selection active
        try:
            clear_active = bool(
                (self._prog and (self._prog.data or self._prog.selection or
                                 self._prog.live_fades)) or
                (self._prog and self._prog._clear_stage > 0)
            )
            theme = self._go_theme if clear_active else self._dim_btn_theme
            if theme:
                dpg.bind_item_theme("qbtn_clear", theme)
        except Exception:
            pass

        # Enforce lowercase in command input (catches direct keyboard typing)
        try:
            _cv = dpg.get_value("cmd_input")
            if _cv and _cv != _cv.lower():
                dpg.set_value("cmd_input", _cv.lower())
        except Exception:
            pass

        # Sync per-fixture dim quick-set sliders from programmer/cue output
        try:
            if self._patch and self._out:
                cue_m = self._out._merged_cue_layer()
                for master in self._patch.all_fixtures():
                    fid = master.fixture_id
                    tag = f"fq_dim_{fid}"
                    if not dpg.is_item_active(tag):
                        pl = self._out.programmer_layer.get(str(fid), {})
                        cl = cue_m.get(str(fid), {})
                        dim = pl.get('dim', cl.get('dim', master.virtual_dimmer))
                        dpg.set_value(tag, float(dim))
        except Exception:
            pass

        try:
            # _prog_time is defined in studio_console/state.py, not reachable
            # as a module-level import here (this module gets imported before
            # state.py runs) — deferred import, same pattern used throughout
            # this split. See module docstring.
            from __main__ import _prog_time
            pt = _prog_time
            if pt.get('on'):
                pt_label = f"● pan·tilt {pt['fade']:.1f}s"
                if pt.get('delay', 0.0):
                    pt_label += f" d{pt['delay']:.1f}"
                dpg.configure_item("sb_pt_lbl", label=pt_label)
                if self._go_theme:
                    dpg.bind_item_theme("sb_pt_lbl", self._go_theme)
            else:
                dpg.configure_item("sb_pt_lbl", label="○ pan·tilt")
                if self._dim_btn_theme:
                    dpg.bind_item_theme("sb_pt_lbl", self._dim_btn_theme)
        except Exception:
            pass

        # Selection counter in command bar (keep small label too)
        try:
            sel = self._prog.selection
            masters = sum(1 for f in sel if isinstance(f, MasterFixture))
            if masters:
                dpg.set_value("cmd_sel_count", f"sel: {masters} fixture(s)")
                dpg.configure_item("cmd_sel_count", color=_C_ACCENT)
            else:
                dpg.set_value("cmd_sel_count", "sel: —")
                dpg.configure_item("cmd_sel_count", color=_C_DIM)
        except Exception:
            pass

    def _tick_playbacks_and_faders(self):
        # Active playbacks — rebuild list when fader state changes
        ph = self._playbacks_state_hash()
        if ph != self._last_playbacks_hash:
            self._last_playbacks_hash = ph
            try:
                self._rebuild_playbacks()
            except Exception:
                pass

        # Live programmer FX list — rebuild when the set of running layers
        # (or their live-tracked params) changes.
        fxh = self._prog_fx_state_hash()
        if fxh != self._last_prog_fx_hash:
            self._last_prog_fx_hash = fxh
            try:
                self._rebuild_prog_fx_list()
            except Exception:
                pass

        # Sync fader fader sliders and fade progress bars
        if self._fader_pool:
            for eid, ex in self._fader_pool.faders.items():
                if not ex.is_active:
                    continue
                tag = f"exec_fader_{eid}"
                try:
                    if not dpg.is_item_active(tag):
                        dpg.set_value(tag, round(ex.level * 255))
                except Exception:
                    pass
                # Fade progress bar
                try:
                    fp = self._fade.fade_progress(ex) if self._fade else None
                    fade_tag = f"exec_fade_{eid}"
                    if fp is not None:
                        prog, secs = fp
                        dpg.set_value(fade_tag, prog)
                        dpg.configure_item(fade_tag,
                                           overlay=f"fade  {prog*100:.0f}%  ({secs:.1f}s)")
                    else:
                        dpg.set_value(fade_tag, 0.0)
                        dpg.configure_item(fade_tag, overlay="")
                except Exception:
                    pass

        # Auto-follow: fire GO on faders whose follow timer has elapsed
        if self._fader_pool and self._cmd:
            _now = time.monotonic()
            for ex in self._fader_pool.faders.values():
                fa = getattr(ex, '_follow_at', None)
                if fa and _now >= fa:
                    ex._follow_at = None
                    try:
                        self._cmd(f"FADER {ex.fdr_id} GO")
                    except Exception:
                        pass

        # Auto-chase: fire GO on faders whose stack is in chase mode
        if self._fader_pool and self._cmd:
            _now_ch = time.monotonic()
            for ex in self._fader_pool.faders.values():
                stk = ex.stack
                if not (stk and stk.chase_enabled and stk.cues):
                    ex._chase_next_at = None
                    continue
                # Resolve BPM: speed master > inline
                _sm = None
                if stk.chase_speed_id is not None and self._speed_pool:
                    _sm = self._speed_pool.get(stk.chase_speed_id)
                bpm = (_sm.bpm if _sm else None) or stk.chase_bpm or 120.0
                beat_s = 60.0 / bpm
                if ex._chase_next_at is None:
                    ex._chase_next_at = _now_ch + beat_s
                elif _now_ch >= ex._chase_next_at:
                    ex._chase_next_at = _now_ch + beat_s
                    try:
                        self._cmd(f"FADER {ex.fdr_id} GO")
                    except Exception:
                        pass

        # FLASH button hold detection — poll is_item_active on any ebtn_* slot
        # whose configured function is FLASH (any assigned fader).
        if self._fader_pool and self._cmd:
            active_eids = {
                eid for eid, ex in self._fader_pool.faders.items()
                if ex.stack
            }
            for eid in list(self._flash_held):
                if eid not in active_eids:
                    if self._flash_held.pop(eid, False):
                        try:
                            self._cmd(f"FADER {eid} flash off")
                        except Exception:
                            pass
            for eid in active_eids:
                ex = self._fader_pool.faders[eid]
                # Find which slots are configured as FLASH — check both playbacks panel and fader page
                flash_tags = []
                _fpg_slot = self._fpg_slot_for_exec(self._fpg_page, eid)
                for _s in ('a', 'b', 'c'):
                    if getattr(ex, f'btn_{_s}', '') == 'FLASH':
                        flash_tags.append(f"ebtn_{_s}_{eid}")
                        if _fpg_slot is not None:
                            flash_tags.append(f"fpg_btn{_s}_{_fpg_slot}")
                held = False
                for _ftag in flash_tags:
                    try:
                        if dpg.is_item_active(_ftag):
                            held = True
                            break
                    except Exception:
                        pass
                was_held = self._flash_held.get(eid, False)
                if held and not was_held:
                    try:
                        if ex.trigger_mode == 'moment':
                            self._cmd(f"FADER {eid} moment on")
                        else:
                            self._cmd(f"FADER {eid} flash on")
                    except Exception:
                        pass
                elif not held and was_held:
                    try:
                        if ex.trigger_mode == 'moment':
                            self._cmd(f"FADER {eid} moment off")
                        else:
                            self._cmd(f"FADER {eid} flash off")
                    except Exception:
                        pass
                self._flash_held[eid] = held
                # Update FLASH button visuals
                for _ftag in flash_tags:
                    try:
                        dpg.configure_item(_ftag, label="■ flash" if held else "flash")
                        theme = self._alert_btn_theme if held else self._dim_btn_theme
                        if theme:
                            dpg.bind_item_theme(_ftag, theme)
                    except Exception:
                        pass

    def _tick_cue_list(self):
        # Active stack — refresh left column when fader changes
        active_n = self._active_fader[0] if self._active_fader else 1
        active_cs   = self._stack_pool.get(active_n) if self._stack_pool else None
        current_name = active_cs.name if active_cs else f"stack {active_n}"
        # Build stack combo items from pool
        if self._stack_pool:
            cs_items = ["—"] + [
                f"{sid}: {self._stack_pool.stacks[sid].name}"
                for sid in sorted(self._stack_pool.stacks)
            ]
        else:
            cs_items = ["—"]
        active_item = f"{active_n}: {current_name}" if active_cs else "—"
        try:
            dpg.configure_item("left_cs_combo", items=cs_items)
            if not dpg.is_item_active("left_cs_combo"):
                dpg.set_value("left_cs_combo", active_item if active_item in cs_items else "—")
        except Exception:
            pass

        # Include cue count, notes hash, and wrap state so list rebuilds on changes
        notes_hash = tuple(
            (n, getattr(c, 'note', ''))
            for n, c in active_cs.cues.items()
        ) if active_cs else ()
        wrap_state = getattr(active_cs, 'wrap', False) if active_cs else False
        if (active_n != self._displayed_fader
                or current_name != self._displayed_cs_name
                or notes_hash != getattr(self, '_displayed_notes_hash', None)
                or wrap_state != getattr(self, '_displayed_wrap', None)):
            self._displayed_fader    = active_n
            self._displayed_cs_name     = current_name
            self._displayed_notes_hash  = notes_hash
            self._displayed_wrap        = wrap_state
            try:
                self._rebuild_cue_list(active_cs)
            except Exception:
                pass

        # Header: current cue + wrap badge
        cur = getattr(active_cs, 'current', None) if active_cs else None
        try:
            if cur is not None:
                cue  = active_cs.cues.get(cur)
                name = cue.name if cue else str(cur)
                dpg.set_value("hdr_cue", f"▶  cue {cur:.0f}: {name}")
            else:
                dpg.set_value("hdr_cue", "▶  (none)")
            dpg.set_value("hdr_wrap",
                          "  ↻wrap" if getattr(active_cs, 'wrap', False) else "")
        except Exception:
            pass

        # cue timing editor — sync drag floats to active cue's fade/delay
        try:
            _, cue_t = self._cue_timing_target()
            if cue_t:
                dpg.set_value("cue_timing_label", f"cue {cue_t.cue_number} — {cue_t.name[:14]}")
                if not dpg.is_item_active("cue_fade_input"):
                    dpg.set_value("cue_fade_input", cue_t.fade_time)
                if not dpg.is_item_active("cue_delay_input"):
                    dpg.set_value("cue_delay_input", cue_t.delay_time)
                if not dpg.is_item_active("cue_follow_input"):
                    dpg.set_value("cue_follow_input", getattr(cue_t, 'follow_time', 0.0))
                if not dpg.is_item_active("cue_note_input"):
                    dpg.set_value("cue_note_input", getattr(cue_t, 'note', ''))
                if not dpg.is_item_active("cue_fxoutfade_input"):
                    dpg.set_value("cue_fxoutfade_input",
                                  getattr(cue_t, 'fx_outfade', None) or 0.0)
            else:
                dpg.set_value("cue_timing_label", "—")
        except Exception:
            pass

        # Highlight active cue row and auto-scroll to it
        if active_cs:
            sid = active_cs.stack_id
            sorted_nums = active_cs._sorted_cue_numbers()
            tbl_tag = f"cl_tbl_{sid}"
            for idx, num in enumerate(sorted_nums):
                tag = f"cue_row_{sid}_{num}"
                is_cur = (num == cur)
                try:
                    dpg.set_value(tag, is_cur)
                except Exception:
                    pass
                try:
                    if is_cur:
                        dpg.highlight_table_row(tbl_tag, idx, _C_CUE_ACT)
                    else:
                        dpg.unhighlight_table_row(tbl_tag, idx)
                except Exception:
                    pass
            # Auto-scroll the cue list so the active cue stays visible
            if cur is not None:
                try:
                    cur_idx = list(sorted_nums).index(cur) if cur in sorted_nums else 0
                    row_h   = 22   # approximate table row height with padding
                    target  = max(0, cur_idx * row_h - 44)
                    dpg.set_y_scroll("cue_list_scroll", target)
                except Exception:
                    pass

    def _tick_fx_header(self):
        # Header: FX — kept short and bounded on purpose (see _build_header's
        # comment): a variable-length "fx: <waveform> <bpm>bpm" string used
        # to reflow the whole header row when it grew, pushing the win
        # (minimize/close) cluster off-screen. Full detail lives in the
        # "live fx (programmer)" list in the left column instead.
        layers = list(self._fx._layers.values())
        if layers:
            l = layers[0]
            n = len(layers)
            dpg.set_value("hdr_fx", f"fx: on ({n})" if n > 1 else "fx: on")
            dpg.configure_item("hdr_fx", color=_C_ACCENT)
            # Sync sliders to actual FX state
            dpg.set_value("fx_rate",   l.rate_bpm)
            dpg.set_value("fx_size",   l.size)
            dpg.set_value("fx_spread", l.spread)
            try:
                dpg.bind_item_theme("kill_fx_btn", self._alert_btn_theme)
            except Exception:
                pass
        else:
            dpg.set_value("hdr_fx", "fx: off")
            dpg.configure_item("hdr_fx", color=_C_DIM)
            try:
                dpg.bind_item_theme("kill_fx_btn", self._dim_btn_theme)
            except Exception:
                pass

        # Rate/Size/spread pool button labels + tooltips
        try:
            for n in range(1, 5):
                rp = self._rate_pool.get(n) if self._rate_pool else None
                sp = self._size_pool.get(n) if self._size_pool else None
                xp = self._spread_pool.get(n) if self._spread_pool else None
                try:
                    dpg.set_item_label(f"rate_btn_{n}",
                                       f"r{n}:{rp.bpm:.0f}" if rp else f"r{n}")
                    dpg.set_value(f"rate_tip_{n}",
                                  f"rate {n}: {rp.name}  {rp.bpm:.0f} bpm" if rp
                                  else f"rate {n} — empty  (RECORD RATE {n} Name bpm)")
                except Exception:
                    pass
                try:
                    dpg.set_item_label(f"size_btn_{n}",
                                       f"s{n}:{sp.size:.0f}" if sp else f"s{n}")
                    dpg.set_value(f"size_tip_{n}",
                                  f"size {n}: {sp.name}  {sp.size:.0f}%" if sp
                                  else f"size {n} — empty  (RECORD SIZEP {n} Name size)")
                except Exception:
                    pass
                try:
                    dpg.set_item_label(f"spread_btn_{n}",
                                       f"sp{n}:{xp.spread:.0f}" if xp else f"sp{n}")
                    dpg.set_value(f"spread_tip_{n}",
                                  f"spread {n}: {xp.name}  {xp.spread:.2f}" if xp
                                  else f"spread {n} — empty  (RECORD SPREADP {n} Name spread)")
                except Exception:
                    pass
        except Exception:
            pass

    def _tick_programmer_monitor(self):
        prog_data = self._prog.data if self._prog else {}
        prog_active = any(v for v in prog_data.values() if v)
        # Header: dim (from programmer layer)
        pl = self._out.programmer_layer
        any_dim = next(iter(pl.values()), {}).get('dim') if pl else None
        if any_dim is not None:
            dpg.set_value("hdr_dim", f"dim: {any_dim:.0%}")

        # programmer monitor title colour (mirrors status bar)
        try:
            dpg.configure_item("prog_mon_title",
                               color=_C_ACCENT if prog_active else _C_DIM)
        except Exception:
            pass

        for master in self._patch.all_fixtures():
            fid     = str(master.fixture_id)
            sub_fid = f"{master.fixture_id}.1"
            m_vals  = prog_data.get(fid, {})
            s_vals  = prog_data.get(sub_fid, {})

            has_data = bool(m_vals or s_vals)
            txt_col  = _C_TEXT if has_data else _C_DIM
            r_col    = (200, 80,  80,  255) if has_data else _C_DIM
            g_col    = (80,  200, 80,  255) if has_data else _C_DIM
            b_col    = (80,  130, 220, 255) if has_data else _C_DIM

            r   = int(s_vals.get('red',   0))
            g   = int(s_vals.get('green', 0))
            b   = int(s_vals.get('blue',  0))
            dim = m_vals.get('dim')

            fx_defs  = m_vals.get('fx', [])
            has_fx   = bool(fx_defs)
            if fx_defs:
                parts = []
                for ld in fx_defs:
                    # Waveform: prefer form slot label over raw name
                    if ld.get('form_id') and self._form_pool:
                        frm = self._form_pool.get(ld['form_id'])
                        wave = f"F{ld['form_id']}:{frm.name[:4]}" if frm else f"F{ld['form_id']}"
                    else:
                        wave = ld.get('waveform', '?')[:4]
                    ch = ld.get('channel', '?')[:1].upper()
                    # BPM: pool ref or inline
                    if ld.get('rate_id') and self._rate_pool:
                        rp = self._rate_pool.get(ld['rate_id'])
                        bpm_s = f"R{ld['rate_id']}:{rp.bpm:.0f}" if rp else f"R{ld['rate_id']}"
                    else:
                        bpm_s = f"{ld.get('bpm', 60):.0f}"
                    # Size: pool ref or inline
                    if ld.get('size_id') and self._size_pool:
                        sp = self._size_pool.get(ld['size_id'])
                        sz_s = f"S{ld['size_id']}" if sp else f"S?"
                    else:
                        sz_s = f"sz{ld.get('size', 200):.0f}"
                    parts.append(f"{wave}/{ch} {bpm_s}♩ {sz_s}")
                fx_lbl = "  |  ".join(parts)
            else:
                fx_lbl = "—"

            # Attribute channels present in programmer (for movers)
            _ATTR_ABBREV = [('pan','P'), ('tilt','T'), ('gobo','G'), ('zoom','Z'),
                            ('focus','Fc'), ('iris','Ir'), ('color','Co'), ('dimmer','D')]
            attr_parts = [f"{abbr}:{s_vals[ch]}" for ch, abbr in _ATTR_ABBREV if ch in s_vals]
            has_attr = bool(attr_parts)
            attr_str = ' '.join(attr_parts)

            try:
                dpg.configure_item(f"prog_name_{fid}", color=txt_col)
                dpg.set_value(f"prog_r_{fid}",   str(r)         if has_data else "—")
                dpg.configure_item(f"prog_r_{fid}", color=r_col)
                dpg.set_value(f"prog_g_{fid}",   str(g)         if has_data else "—")
                dpg.configure_item(f"prog_g_{fid}", color=g_col)
                dpg.set_value(f"prog_b_{fid}",   str(b)         if has_data else "—")
                dpg.configure_item(f"prog_b_{fid}", color=b_col)
                dpg.set_value(f"prog_dim_{fid}", f"{dim:.0%}"   if dim is not None else "—")
                dpg.configure_item(f"prog_dim_{fid}", color=txt_col)
                # Append attr summary to fx column when attribute channels are in programmer
                fx_display = fx_lbl
                if has_attr:
                    fx_display = f"{attr_str}  {fx_lbl}" if has_fx else attr_str
                dpg.set_value(f"prog_fx_{fid}",  fx_display)
                dpg.configure_item(f"prog_fx_{fid}",
                                   color=_C_ACCENT if (has_fx or has_attr) else _C_DIM)
                brightness = (r + g + b) / (3 * 255) * float(dim if dim is not None else 1.0)
                # When only FX or attr channels in programmer, show partial bar
                bar_val = max(brightness, 0.25) if ((has_fx or has_attr) and not (r or g or b)) else brightness
                dpg.set_value(f"prog_bar_{fid}", min(1.0, bar_val) if has_data else 0.0)
                fx_tag = "  ~FX" if has_fx else ""
                if has_attr and not (r or g or b):
                    bar_overlay = f"{attr_str}{fx_tag}" if has_data else ""
                else:
                    bar_overlay = f"R{r} G{g} B{b}{fx_tag}" if has_data else ""
                dpg.configure_item(f"prog_bar_{fid}", overlay=bar_overlay)
                # Tint programmer bar to match RGB color
                _pcached = self._prog_bar_themes.get(fid)
                if has_data and (r > 0 or g > 0 or b > 0):
                    if _pcached is None or _pcached[0] != (r, g, b):
                        if _pcached:
                            try: dpg.delete_item(_pcached[1])
                            except: pass
                        try:
                            with dpg.theme() as _pth:
                                with dpg.theme_component(dpg.mvProgressBar):
                                    dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram,
                                                        (r, g, b, 255))
                            dpg.bind_item_theme(f"prog_bar_{fid}", _pth)
                            self._prog_bar_themes[fid] = ((r, g, b), _pth)
                        except: pass
                else:
                    if _pcached:
                        try:
                            dpg.bind_item_theme(f"prog_bar_{fid}", 0)
                            dpg.delete_item(_pcached[1])
                        except: pass
                        del self._prog_bar_themes[fid]
            except Exception:
                pass

    def _tick_output_monitor(self):
        # Output monitor — sample first sub-fixture for RGB (pixel 1 of each tube),
        # master entry for dim. Keys are 'red'/'green'/'blue' throughout.
        for master in self._patch.all_fixtures():
            fid     = str(master.fixture_id)          # e.g. "1"
            sub_fid = f"{master.fixture_id}.1"        # e.g. "1.1" — first pixel

            # dim lives on the master entry
            pl_master  = self._out.programmer_layer.get(fid, {})
            cue_merged = self._out._merged_cue_layer()
            cue_master = cue_merged.get(fid, {})
            dim = pl_master.get('dim', cue_master.get('dim', 1.0))

            # RGB lives on sub-fixture entries; use pixel 1 as representative
            pl_sub  = self._out.programmer_layer.get(sub_fid, {})
            cue_sub = cue_merged.get(sub_fid, {})
            fx_sub  = self._out.fx_layer.get(sub_fid, {})

            # Mirror the actual merger: programmer wins; otherwise cue+FX additive
            if 'red' in pl_sub:
                r = int(pl_sub['red'])
                g = int(pl_sub.get('green', 0))
                b = int(pl_sub.get('blue',  0))
            else:
                r = min(255, int(cue_sub.get('red',   0)) + int(fx_sub.get('red',   0)))
                g = min(255, int(cue_sub.get('green', 0)) + int(fx_sub.get('green', 0)))
                b = min(255, int(cue_sub.get('blue',  0)) + int(fx_sub.get('blue',  0)))

            # Attribute channels (for movers with no RGB)
            _OUT_ATTR = [('pan','P'), ('tilt','T'), ('gobo','G'), ('zoom','Z'), ('focus','Fc')]
            _merged_sub = {**cue_sub, **pl_sub}
            out_attr_parts = [f"{abbr}:{_merged_sub[ch]}" for ch, abbr in _OUT_ATTR
                              if ch in _merged_sub]
            has_out_attr = bool(out_attr_parts) and not (r or g or b)

            dpg.set_value(f"out_r_{fid}",   str(r))
            dpg.set_value(f"out_g_{fid}",   str(g))
            dpg.set_value(f"out_b_{fid}",   str(b))
            dpg.set_value(f"out_dim_{fid}", f"{dim:.0%}")
            brightness = (r + g + b) / (3 * 255) * float(dim)
            out_bar_val = max(brightness, 0.3) if has_out_attr else brightness
            dpg.set_value(f"out_bar_{fid}", min(1.0, out_bar_val))
            out_overlay = ' '.join(out_attr_parts) if has_out_attr else f"R{r} G{g} B{b}"
            dpg.configure_item(f"out_bar_{fid}", overlay=out_overlay)
            # Tint output bar to match actual RGB color
            _ocached = self._out_bar_themes.get(fid)
            if r > 0 or g > 0 or b > 0:
                if _ocached is None or _ocached[0] != (r, g, b):
                    if _ocached:
                        try: dpg.delete_item(_ocached[1])
                        except: pass
                    try:
                        with dpg.theme() as _oth:
                            with dpg.theme_component(dpg.mvProgressBar):
                                dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram,
                                                    (r, g, b, 255))
                        dpg.bind_item_theme(f"out_bar_{fid}", _oth)
                        self._out_bar_themes[fid] = ((r, g, b), _oth)
                    except: pass
            else:
                if _ocached:
                    try:
                        dpg.bind_item_theme(f"out_bar_{fid}", 0)
                        dpg.delete_item(_ocached[1])
                    except: pass
                    del self._out_bar_themes[fid]

    def _tick_midi_osc(self):
        # MIDI status column (soft-takeover state)
        for (ch, cc), m in self._midi.cc_maps.items():
            tag = f"mr_st_cc_{ch}_{cc}"
            try:
                status = "live" if m.taken_over else "◐ takeover"
                col    = _C_TEXT if m.taken_over else _C_DIM
                dpg.set_value(tag, status)
                dpg.configure_item(tag, color=col)
            except Exception:
                pass

        # MIDI clock sync — when active, apply detected BPM to all programmer FX layers
        if self._midi and getattr(self._midi, 'clock_sync', False):
            clk_bpm = self._midi.clock_bpm
            try:
                if clk_bpm is not None:
                    if not dpg.is_item_active("fx_rate"):
                        dpg.set_value("fx_rate", clk_bpm)
                    try:
                        dpg.set_value("fx_tap_label", f"{clk_bpm:.0f} bpm")
                    except Exception:
                        pass
                    now = time.monotonic()
                    for layer in self._fx._layers.values():
                        if layer.fx_id < 10000:
                            layer.set_rate_smooth(clk_bpm, now)
                    dpg.set_value("hdr_clock", f"clk {clk_bpm:.0f}")
                    dpg.configure_item("hdr_clock", color=_C_ACCENT)
                else:
                    dpg.set_value("hdr_clock", "clk …")
                    dpg.configure_item("hdr_clock", color=_C_DIM)
            except Exception:
                pass
        else:
            try:
                dpg.set_value("hdr_clock", "")
            except Exception:
                pass

        # OSC state feedback — broadcast at ~1 Hz (every ~20 ticks at 20Hz)
        self._osc_fb_counter = getattr(self, '_osc_fb_counter', 0) + 1
        if self._osc_fb_counter >= 20:
            self._osc_fb_counter = 0
            if self._osc and self._out and self._patch:
                self._osc.broadcast_state(self._out, self._fader_pool, self._patch)

    def _tick_autosave(self):
        from __main__ import GUIEngine
        # Clear save status after delay
        _now_as = time.monotonic()
        if (GUIEngine._save_status_clear_at > 0.0 and
                _now_as >= GUIEngine._save_status_clear_at):
            GUIEngine._save_status_clear_at = 0.0
            try:
                dpg.set_value("hdr_save_status", "")
            except Exception:
                pass

        # Auto-save every _AUTO_SAVE_INT seconds (default 5 min)
        if (GUIEngine._auto_save_t > 0.0 and
                _now_as - GUIEngine._auto_save_t >= GUIEngine._AUTO_SAVE_INT):
            if self._save:
                try:
                    self._save()
                    GUIEngine._auto_save_t = _now_as
                    try:
                        dpg.set_value("hdr_save_status", "auto-saved")
                        dpg.configure_item("hdr_save_status", color=_C_DIM)
                        GUIEngine._save_status_clear_at = time.monotonic() + 3.0
                    except Exception:
                        pass
                except Exception:
                    pass
        elif GUIEngine._auto_save_t == 0.0:
            # First tick — arm the timer
            GUIEngine._auto_save_t = _now_as

    def run(self):
        if not _DPG_OK:
            # Fall back to the old sleep loop
            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                pass
            return
        self.start_update_loop()
        self._load_popup_layout()   # restore saved popup positions/sizes
        dpg.focus_item("cmd_input")
        # Ctrl+C (SIGINT) in the terminal used to raise KeyboardInterrupt
        # straight out of the blocking dpg.start_dearpygui() call below,
        # skipping every line after it — including the popup-layout and
        # save_show() calls a few lines down, which is the same shutdown
        # code the "close" header button and a normal window-close both
        # rely on. That meant a Ctrl+C exit silently lost whatever
        # changed since the last save, with no error or warning — the
        # console would come back up next launch showing stale state,
        # not "how it was when I last turned it off". Routing SIGINT
        # through dpg.stop_dearpygui() instead makes Ctrl+C take the
        # exact same graceful path as every other way of closing the
        # app, so it's covered by the same save logic (and the same
        # force-exit watchdog in studio_project.py, if driver shutdown
        # itself hangs afterward).
        try:
            signal.signal(signal.SIGINT, lambda *_: dpg.stop_dearpygui())
        except Exception:
            pass   # signal.signal only works from the main thread; run() always is, but stay defensive
        dpg.start_dearpygui()
        self._running = False   # signal update thread before destroying context
        time.sleep(0.1)         # give thread one tick to see the flag
        self._save_popup_layout()   # persist popup positions on clean exit
        try:
            # save_show is defined in studio_console/state.py, not reachable
            # as a module-level import here — deferred import, same pattern
            # used throughout this split.
            from __main__ import save_show
            save_show()
        except Exception:
            pass
        dpg.destroy_context()
