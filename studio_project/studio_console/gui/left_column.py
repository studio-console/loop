"""GUIEngine's left column: command input, numpad, command history, global keyboard shortcuts.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.models.fixtures import MasterFixture


class GUIEngineLeftColumn:
    def _build_left_column(self):
        self._displayed_fader  = None
        self._displayed_cs_name   = None
        self._last_playbacks_hash = None
        _W = self._W_LEFT
        with dpg.child_window(tag="left_col", width=_W, height=self._H_MAIN,
                              border=True, no_scrollbar=True, no_scroll_with_mouse=True):
            # ── cue list ─────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("› stack", color=_C_ACCENT)
                dpg.add_combo(tag="left_cs_combo", items=["—"], default_value="—",
                              width=-120, height_mode=dpg.mvComboHeight_Small,
                              callback=self._on_cs_combo_select)
                dpg.add_text("", tag="hdr_wrap", color=_C_ACCENT)
            dpg.add_separator()
            # Fixed-height scroll area for the cue list
            with dpg.child_window(tag="cue_list_scroll", width=-1, height=118,
                                  border=True, no_scrollbar=True,
                                  no_scroll_with_mouse=False):
                dpg.add_group(tag="cue_list_group")
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label=" ◀ back ", tag="back_btn", width=88, height=24,
                               callback=lambda: self._back())
                dpg.add_button(label=" ↺ reload ", width=100, height=24,
                               callback=lambda: self._reload() if self._reload else None)
                dpg.add_button(label="timing", width=70, height=24,
                               callback=self._on_cue_timing_toggle)
                dpg.add_button(label="  go ▶  ", tag="go_btn", width=88, height=24,
                               callback=lambda: self._go())

            # ── Active playbacks ─────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("› running stacks", color=_C_ACCENT)
                dpg.add_spacer(width=4)
                dpg.add_button(label="stop all", width=78, height=24,
                               callback=self._on_stop_all_faders)
            dpg.add_separator()
            with dpg.child_window(tag="playbacks_list", width=-1, height=108,
                                  border=False, no_scrollbar=False, no_scroll_with_mouse=False):
                dpg.add_text("— none running", tag="playbacks_empty", color=_C_DIM)

            # ── FX controls ─────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("› fx", color=_C_ACCENT)
                dpg.add_spacer(width=4)
                dpg.add_button(label="tap", tag="fx_tap_btn", width=42, height=24,
                               callback=self._on_tap_tempo)
                dpg.add_text("", tag="fx_tap_label", color=_C_DIM)
            dpg.add_separator()
            _sw = _W - 120
            dpg.add_slider_float(label="rate bpm", tag="fx_rate",
                                 default_value=60.0, min_value=10.0,
                                 max_value=480.0, width=_sw,
                                 callback=self._on_fx_rate)
            dpg.add_slider_float(label="size    ", tag="fx_size",
                                 default_value=100.0, min_value=0.0,
                                 max_value=100.0, width=_sw,
                                 callback=self._on_fx_size)
            dpg.add_slider_float(label="spread  ", tag="fx_spread",
                                 default_value=0.0, min_value=0.0,
                                 max_value=100.0, width=_sw,
                                 callback=self._on_fx_spread)
            with dpg.group(horizontal=True):
                dpg.add_button(label="kill fx", tag="kill_fx_btn",
                               width=_W - 20 - 80 - 4,
                               callback=lambda: self._cmd("KILL FX") if self._cmd else None)
                dpg.add_button(label="rsp pool", width=80,
                               callback=self._on_fx_params_toggle)
    def _numpad_append(self, sender, app_data, user_data):
        """Append a string to the command input field."""
        try:
            dpg.set_value("cmd_input",
                          dpg.get_value("cmd_input") + user_data)
        except Exception:
            pass
    def _numpad_exec(self, sender, app_data, user_data):
        """Execute a command immediately (used by CLEAR, GO, BACK buttons)."""
        cmd = user_data
        self._log(f"> {cmd}")
        if self._cmd:
            result = self._cmd(cmd)
            if result:
                for line in str(result).splitlines():
                    self._log(f"  {line}")
    def _numpad_backspace(self, s=None, a=None, u=None):
        try:
            v = dpg.get_value("cmd_input")
            if v:
                dpg.set_value("cmd_input", v[:-1])
        except Exception:
            pass
    def _numpad_clear_input(self, s=None, a=None, u=None):
        try:
            dpg.set_value("cmd_input", "")
        except Exception:
            pass
    def _cmd_input_needs_focus(self):
        """True when a text/number widget other than cmd_input has keyboard focus."""
        try:
            focused = dpg.get_focused_item()
            if focused == 0:
                return False
            t = dpg.get_item_info(focused).get('type', '')
            return ('Input' in t or 'Combo' in t)
        except Exception:
            return False
    def _on_hist_up(self, *_):
        """↑ arrow: scroll backward through command history."""
        if self._cmd_input_needs_focus():
            return
        if not self._cmd_history:
            return
        self._cmd_hist_i = min(len(self._cmd_history) - 1, self._cmd_hist_i + 1)
        try:
            dpg.set_value("cmd_input",
                          self._cmd_history[-(self._cmd_hist_i + 1)])
        except Exception:
            pass
    def _on_hist_down(self, *_):
        """↓ arrow: scroll forward through command history (toward blank)."""
        if self._cmd_input_needs_focus():
            return
        self._cmd_hist_i -= 1
        if self._cmd_hist_i < 0:
            self._cmd_hist_i = -1
            try:
                dpg.set_value("cmd_input", "")
            except Exception:
                pass
        else:
            try:
                dpg.set_value("cmd_input",
                              self._cmd_history[-(self._cmd_hist_i + 1)])
            except Exception:
                pass
    def _on_ctrl_s(self, *_):
        """Ctrl+S: save show."""
        is_ctrl = (dpg.is_key_down(dpg.mvKey_LControl) or
                   dpg.is_key_down(dpg.mvKey_RControl) or
                   dpg.is_key_down(dpg.mvKey_ModSuper))   # Cmd on macOS
        if is_ctrl:
            self._on_save()
    def _on_ctrl_z(self, *_):
        """Ctrl+Z: undo last programmer change."""
        is_ctrl = (dpg.is_key_down(dpg.mvKey_LControl) or
                   dpg.is_key_down(dpg.mvKey_RControl) or
                   dpg.is_key_down(dpg.mvKey_ModSuper))
        if is_ctrl and self._cmd:
            result = self._cmd("UNDO")
            if result:
                self._log(f"> {result}")
    def _on_global_mouse_click(self, sender, app_data):
        """Handle left-click on the stage canvas to select/deselect fixtures."""
        if app_data != 0:   # 0 = left button
            return
        try:
            if not dpg.is_item_hovered("stage_canvas"):
                return
        except Exception:
            return
        try:
            canvas_min = dpg.get_item_rect_min("stage_canvas")
            canvas_sz  = dpg.get_item_rect_size("stage_canvas")
            mouse      = dpg.get_mouse_pos(local=False)
            rel_x = mouse[0] - canvas_min[0]
            w     = canvas_sz[0]
            if w < 1:
                return
            fixtures = list(self._patch.all_fixtures())
            n = len(fixtures)
            if not n:
                return
            gap = 10
            tw  = (w - gap * (n + 1)) / n
            # Which fixture column was clicked?
            clicked_idx = None
            for i in range(n):
                x0 = gap + i * (tw + gap)
                x1 = x0 + tw
                if x0 <= rel_x <= x1:
                    clicked_idx = i
                    break
            if clicked_idx is None:
                return
            master = fixtures[clicked_idx]
            # Shift-click: toggle fixture in/out of selection
            shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)
            if shift:
                cur_masters = [f for f in self._prog.selection if isinstance(f, MasterFixture)]
                if master in cur_masters:
                    cur_masters.remove(master)
                else:
                    cur_masters.append(master)
                self._prog.select(cur_masters)
                sel_str = " ".join(str(m.fixture_id) for m in cur_masters) or "none"
                self._log(f"> SELECT {sel_str}")
            else:
                self._prog.select([master])
                self._log(f"> SELECT {master.fixture_id}")
        except Exception:
            pass
    def _on_global_char(self, sender, app_data, user_data):
        """Route printable keys to cmd_input when no other text widget is active."""
        if self._cmd_input_needs_focus():
            return
        lo, hi = user_data
        is_shift = (dpg.is_key_down(dpg.mvKey_LShift) or
                    dpg.is_key_down(dpg.mvKey_RShift))
        # Suppress Ctrl+key combos (they're shortcuts, not text input)
        is_ctrl = (dpg.is_key_down(dpg.mvKey_LControl) or
                   dpg.is_key_down(dpg.mvKey_RControl) or
                   dpg.is_key_down(dpg.mvKey_ModSuper))   # Cmd on macOS
        if is_ctrl:
            return
        dpg.set_value("cmd_input",
                      dpg.get_value("cmd_input") + lo)
    def _on_global_backspace(self, *_):
        """Route Backspace to cmd_input when no other text widget is active."""
        if self._cmd_input_needs_focus():
            return
        v = dpg.get_value("cmd_input")
        if v:
            dpg.set_value("cmd_input", v[:-1])
    def _on_global_enter(self, *_):
        """Execute cmd_input command when Enter pressed outside the input field."""
        if self._cmd_input_needs_focus():
            return
        self._on_cmd_execute()
