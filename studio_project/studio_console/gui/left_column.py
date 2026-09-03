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
        self._last_prog_fx_hash   = None
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
            # Running stacks now gets the room live fx (programmer) used to
            # share this space with — that list moved into the monitors
            # popup (see _build_monitors_popup in audio_monitors.py, "kill"
            # button and all) since it needed a "check on it occasionally"
            # popup a lot less than running stacks needed the room to show
            # more than one or two faders at a time. 128+50(old prog_fx_list)
            # plus its header/separator overhead reclaimed, so the left
            # column's total height budget doesn't grow (no scrollbar
            # anywhere is the whole point — see build()'s own comment).
            with dpg.child_window(tag="playbacks_list", width=-1, height=220,
                                  border=False, no_scrollbar=False, no_scroll_with_mouse=False):
                dpg.add_text("— none running", tag="playbacks_empty", color=_C_DIM)

            # FX live controls (tap/rate/size/spread/kill fx/rsp pool) moved
            # into the fx editor window — see _build_fx_editor_popup in
            # fx_editor.py. Kept out of the main window to declutter it;
            # same tags (fx_rate/fx_size/fx_spread/etc.), same callbacks,
            # so _tick_fx_header's live sync is unaffected by the move —
            # DPG widgets are addressed by tag regardless of which window
            # currently contains them.
    def _prog_fx_state_hash(self):
        """Compact snapshot of live programmer FX — used to detect changes."""
        if not self._prog_fx_ids or not self._fx:
            return ()
        out = []
        for fxid in self._prog_fx_ids:
            layer = self._fx._layers.get(fxid)
            if not layer:
                continue
            out.append((fxid, layer.waveform, layer.channel, round(layer.rate_bpm, 1),
                        round(layer.size, 1), round(layer.spread, 1), round(layer.low, 1),
                        layer.mirror, layer.cluster, layer.block_size, len(layer.targets)))
        return tuple(out)
    def _rebuild_prog_fx_list(self):
        """Rebuild the live-programmer-FX list (left column). Detail view for
        what's actually running, now that the header only shows a short,
        fixed-width summary — see _build_header's comment on why."""
        try:
            dpg.delete_item("prog_fx_list", children_only=True)
        except Exception:
            return
        layers = []
        if self._fx:
            for fxid in self._prog_fx_ids:
                layer = self._fx._layers.get(fxid)
                if layer:
                    layers.append(layer)
        if not layers:
            dpg.add_text("— none live", tag="prog_fx_empty",
                         color=_C_DIM, parent="prog_fx_list")
            return
        for i, layer in enumerate(layers):
            if i > 0:
                dpg.add_separator(parent="prog_fx_list")
            extras = []
            if layer.low:
                extras.append(f"low {layer.low:.0f}")
            if layer.cluster:
                extras.append("cluster")
            if layer.mirror:
                extras.append("mirror")
            if layer.block_size != 1:
                extras.append(f"block {layer.block_size}")
            extra_s = f"  [{' '.join(extras)}]" if extras else ""
            line = (f"{layer.waveform} {layer.channel}  {layer.rate_bpm:.0f}bpm  "
                    f"sz{layer.size:.0f}  spr{layer.spread:.0f}  "
                    f"{len(layer.targets)} tgt{extra_s}")
            dpg.add_text(line, color=_C_ACCENT, parent="prog_fx_list")
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
        """On-screen backspace button — same empty-input-triggers-UNDO
        behavior as the physical Backspace key (_on_global_backspace),
        for touch use with no keyboard."""
        try:
            v = dpg.get_value("cmd_input")
            if v:
                dpg.set_value("cmd_input", v[:-1])
            elif self._cmd:
                result = self._cmd("UNDO")
                if result:
                    self._log(f"> {result}")
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
    def _other_field_has_focus(self):
        """True when a text/number widget OTHER than cmd_input has real
        keyboard focus (e.g. editing a cue name or a numeric popup field).

        Unlike _cmd_input_needs_focus(), this deliberately excludes cmd_input
        itself: dpg.focus_item("cmd_input") is called after every command
        execution, so cmd_input legitimately holds real focus most of the
        time, and that alone shouldn't count as "hands off cmd_input"."""
        try:
            focused = dpg.get_focused_item()
            if focused == 0:
                return False
            if dpg.get_item_alias(focused) == "cmd_input":
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
    def _on_arrow_select(self, _sender, _app_data, user_data):
        """Left/Right arrow — PREV/NEXT fixture (or sub-fixture, when
        exactly one is selected — see NEXT/PREV's own extended stepping in
        programmer._parse_selection) stepping, mirroring the numpad prev/
        next buttons exactly. Gated like the ↑/↓ history handlers above:
        only fires when no input-type widget has focus at all — Left/Right
        are standard text-cursor-movement keys and must not be hijacked
        while actually editing cmd_input or any other field."""
        if self._cmd_input_needs_focus():
            return
        cmd = user_data
        self._log(f"> {cmd}")
        if self._cmd:
            result = self._cmd(cmd)
            if result:
                for line in str(result).splitlines():
                    self._log(f"  {line}")
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
    def _on_global_right_click(self, sender, app_data):
        """Right-click anywhere — currently only meaningful over either
        undo button, where it opens the hold-undo history popup (see
        _build_undo_history_popup/_open_undo_history in right_column.py)."""
        if app_data != 1:   # 1 = right mouse button
            return
        for tag in ("qbtn_undo", "numpad_undo_btn"):
            try:
                if dpg.does_item_exist(tag) and dpg.is_item_hovered(tag):
                    self._open_undo_history()
                    return
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
    def _on_global_numpad_op(self, _sender, _app_data, user_data):
        """Physical NumPad +/-// — appends the SAME padded " + "/" - "/
        " THRU " string the GUI numpad's own buttons do (_numpad_append in
        right_column.py), so the two behave identically.

        Gated on _other_field_has_focus() (excludes cmd_input), not
        _cmd_input_needs_focus() (which doesn't) — same fix already applied
        to _on_global_backspace and for the same reason: dpg.focus_item(
        "cmd_input") runs after every command, so cmd_input holds real
        native DPG focus most of the time, and gating on "cmd_input
        doesn't have focus" made this handler nearly unreachable in
        practice (reported: physical +/- silently stopped padding).

        But cmd_input HAVING native focus is exactly the case that needs
        the most care here: DPG's own input_text widget handles a raw
        keypress itself before this handler ever runs, inserting the bare,
        unpadded character (a literal "+"/"-"/"/") — key handlers in DPG
        are notification-only, there's no way to cancel that native
        insertion. So instead of preventing it, detect it (the value now
        ends with the bare native character) and swap it for the padded
        version after the fact — matches what the GUI button produces
        exactly, regardless of whether cmd_input was focused or not."""
        if self._other_field_has_focus():
            return
        is_ctrl = (dpg.is_key_down(dpg.mvKey_LControl) or
                   dpg.is_key_down(dpg.mvKey_RControl) or
                   dpg.is_key_down(dpg.mvKey_ModSuper))
        if is_ctrl:
            return
        native_char, padded = user_data
        try:
            val = dpg.get_value("cmd_input")
            if val.endswith(native_char):
                val = val[:-len(native_char)]
            dpg.set_value("cmd_input", val + padded)
        except Exception:
            pass
    def _on_global_backspace(self, *_):
        """Route Backspace to cmd_input when no other text widget is active.
        Once the command line is already empty, Backspace instead triggers
        UNDO (same as Ctrl+Z) — a quick, single-key way to reverse the
        last programmer change with no modifier needed, but only once
        there's nothing left to delete, so it can never fire mid-typo-fix
        while actually typing a command.

        The empty-triggers-UNDO branch uses _other_field_has_focus() rather
        than _cmd_input_needs_focus(): dpg.focus_item("cmd_input") runs after
        every command, so cmd_input holds real DPG focus most of the time —
        gating UNDO on "cmd_input doesn't have focus" made it nearly
        unreachable in practice. The delete branch still checks whether
        cmd_input itself has native focus, since DPG's own widget already
        deletes a character natively in that case and a manual set_value
        here would double-delete."""
        if self._other_field_has_focus():
            return
        v = dpg.get_value("cmd_input")
        if v:
            focused = dpg.get_focused_item()
            if focused != 0 and dpg.get_item_alias(focused) == "cmd_input":
                return
            dpg.set_value("cmd_input", v[:-1])
        elif self._cmd:
            result = self._cmd("UNDO")
            if result:
                self._log(f"> {result}")
    def _on_global_enter(self, *_):
        """Execute cmd_input command when Enter pressed outside the input field."""
        if self._cmd_input_needs_focus():
            return
        self._on_cmd_execute()
