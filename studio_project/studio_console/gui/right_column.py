"""GUIEngine's right column: transport controls, BLIND/HIGHLIGHT/programmer-time toggles.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403


class GUIEngineRightColumn:
    def _build_right_column(self):
        # Digit buttons fill 3 cols; keyword buttons fill 3 cols; all proportioned to right col width.
        # Total numpad width: 3×_NW + gap + _KW + 2×(_NW+gap) = fills ~440px of _W_RIGHT
        _NW = 70   # digit button width
        _NH = 40   # digit button height — 4 rows × 40 + 3 × 4-gap = 172px
        _KW = 108  # keyword button width (wider label)
        _BH = 24   # quick-action button height
        _W  = self._W_RIGHT

        with dpg.child_window(tag="right_col", width=_W, height=self._H_MAIN,
                              border=True, no_scrollbar=True, no_scroll_with_mouse=True):
            # ── Header ─────────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("› command line", color=_C_ACCENT)
                dpg.add_spacer(width=10)
                dpg.add_text("sel: —", tag="cmd_sel_count", color=_C_DIM)
                with dpg.tooltip("cmd_sel_count"):
                    dpg.add_text("", tag="cmd_sel_count_tip", wrap=400)

            # ── Log — larger to show more feedback lines ─────────
            # A read-only multiline input_text, not a plain add_text: DPG's
            # add_text can't be scrolled back through or selected/copied at
            # all (reported: can't scroll back through the AI conversation,
            # can't copy anything out of the log) — input_text is a real
            # (if read-only) text widget, so native OS text selection and
            # Cmd/Ctrl+C work on it.
            #
            # Wrapped in a scrollable child_window, not left to size/scroll
            # itself: multiline InputText has no native word-wrap at all —
            # no_horizontal_scroll (tried first) only suppresses the
            # cursor's own auto-scroll-into-view while typing, it doesn't
            # wrap the text layout, so long AI replies still ran off the
            # right edge with nothing to scroll them into view (reported
            # again after that first attempt). And get_y_scroll/_max are
            # proven reliable on a child_window elsewhere in this app
            # (cue_list_scroll, fader-page cue lists); relying on them
            # against the input_text's own tag directly (no separate
            # window) was the "autoscroll hangs" bug — those APIs don't
            # reliably apply to it. So: _log() (core.py) now measures this
            # window's real width and manually word-wraps each line before
            # storing it (same dpg.get_text_size() technique _fit_text
            # already uses elsewhere), and the input_text itself is sized
            # tall enough to always show everything without needing its
            # own internal scroll — all scrolling is this window's, which
            # is the part already known to work.
            #
            # cmd_log's own height is NOT fixed — _log() (core.py) resizes
            # it to match the real line count on every call. A flat, large
            # fixed height (tried first) meant cmd_log_win's scroll range
            # was always that same big constant regardless of how much
            # text actually exists, so "scroll to the max" landed near the
            # bottom of a mostly-blank widget past the real last line
            # instead of at the actual bottom of the text (reported:
            # autoscroll still not reaching the bottom after the wrap fix).
            # Starts at this window's own height as a sane pre-any-log-
            # lines default.
            with dpg.child_window(tag="cmd_log_win", width=-1, height=140,
                                  border=True, horizontal_scrollbar=False,
                                  no_scrollbar=False, no_scroll_with_mouse=False):
                dpg.add_input_text(tag="cmd_log", multiline=True, readonly=True,
                                   width=-1, height=140)

            # ── Error flash — shows last error in red; clears on next success ─
            dpg.add_text("", tag="cmd_error_flash", color=[255, 80, 80, 220], wrap=0)

            # ── Input row ──────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("cmd >", color=_C_ACCENT)
                dpg.add_input_text(
                    tag="cmd_input",
                    hint="1 thru 6  |  1 thru 6 r 255  |  fx sine red  |  go  |  save",
                    width=-220, on_enter=True,
                    callback=self._on_cmd_execute,
                )
                dpg.add_button(label="enter", width=80, height=24,
                               callback=self._on_cmd_execute)
                dpg.add_button(label="clr", width=50, height=24,
                               callback=self._numpad_clear_input)

            dpg.add_separator()

            # ── Quick action row 1: cue / record / FX ──────────
            with dpg.group(horizontal=True):
                for label, ud in [
                    ("rec cue", "RECORD CUE "), ("upd cue", "UPDATE CUE "),
                    ("cue",     "CUE "),         ("rec fx",  "RECORD FX "),
                    ("fx",      "FX "),           ("rec grp", "RECORD GROUP "),
                    ("group",   "GROUP "),        ("snap",    "SNAPSHOT "),
                ]:
                    dpg.add_button(label=label, width=82, height=_BH,
                                   callback=self._numpad_append, user_data=ud)

            # ── Quick action row 2: timing / CLEAR / transport ─
            with dpg.group(horizontal=True):
                for label, ud in [
                    ("fade",  " FADE "), ("cfade", " CFADE "),
                    ("dfade", " DFADE "), ("delay", " DELAY "),
                ]:
                    dpg.add_button(label=label, width=72, height=_BH,
                                   callback=self._numpad_append, user_data=ud)
                dpg.add_spacer(width=8)
                for label, ud in [
                    ("clear", "CLEAR"), ("reload", "RELOAD"),
                    ("go",    "GO"),    ("back",   "BACK"),
                    ("undo",  "UNDO"),
                ]:
                    _tag = f"qbtn_{ud.lower()}"
                    dpg.add_button(label=label, tag=_tag, width=72, height=_BH,
                                   callback=self._numpad_exec, user_data=ud)

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("› numpad", color=_C_ACCENT)
                dpg.add_spacer(width=8)
                dpg.add_text("digit", color=_C_DIM)
                dpg.add_spacer(width=80)
                dpg.add_text("keyword", color=_C_DIM)

            # ── Numpad + keyword keys ───────────────────────────
            # Digit pad (left) + keyword pad (right), each 4 rows × 3 cols.
            # Total width: 3×_NW + 12 + 3-col-kw, all within _W_RIGHT.
            with dpg.group(horizontal=True):

                # Left: digit pad [7][8][9] / [4][5][6] / [1][2][3] / [⌫][0][.]
                with dpg.group(tag="numpad_digit_group"):
                    for row_digits in ([7, 8, 9], [4, 5, 6], [1, 2, 3]):
                        with dpg.group(horizontal=True):
                            for d in row_digits:
                                dpg.add_button(
                                    label=str(d), width=_NW, height=_NH,
                                    callback=self._numpad_append,
                                    user_data=str(d))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="⌫",  width=_NW, height=_NH,
                                       callback=self._numpad_backspace)
                        dpg.add_button(label="0",   width=_NW, height=_NH,
                                       callback=self._numpad_append, user_data="0")
                        dpg.add_button(label=".",   width=_NW, height=_NH,
                                       callback=self._numpad_append, user_data=".")

                dpg.add_spacer(width=12)

                # Right: keywords — selection/structure keys only now; the
                # pool/parameter quick-set buttons (dim, R, G, B, col) were
                # removed as redundant with the color picker and pools
                # panel. "-" mirrors "+" — deselect the next fixture/range
                # instead of adding it (programmer._parse_selection),
                # e.g. "1 THRU 10 - 3" = 1-10 except 3. "/" is a second
                # shortcut for the same THRU append as the "thru" button —
                # mirrors the physical NumPad Divide key (core.py), which
                # real numpad layouts have and "T" doesn't. "undo" runs the
                # same UNDO command as Backspace-on-empty/Ctrl+Z — a direct,
                # always-visible button for it rather than only a keyboard
                # gesture. "all" is a one-tap "select every patched fixture"
                # (the ALL keyword) — safe/reversible, and common enough to
                # be worth a dedicated key rather than typing it out.
                # "prev"/"next" step the selection one fixture at a time
                # (the NEXT/PREV selection keywords) — steps one SUB-
                # fixture at a time instead, wrapping into the next/prev
                # fixture's first/last sub, when exactly one sub-fixture
                # (not a whole fixture) is currently selected.
                # "kill" is KILL FX again — already a button in the FX
                # editor, duplicated here so it's reachable without opening
                # that window. "hi"/"nrm"/"lo" set the CURRENTLY ACTIVE
                # fader's priority directly (PRIORITY <active fader>
                # HIGH/NORMAL/LOW) — the running-stacks priority button only
                # cycles hi→lo→nrm one step at a time and needs that fader's
                # row visible; these jump straight there for whichever
                # fader is active. "upd" is UPDATE CUE for whatever cue is
                # actively running on the active fader, without having to
                # know/type its number — the existing "upd cue" button
                # still needs one typed in, for updating a cue that ISN'T
                # the live one.
                #
                # Packed into exactly 4 rows, matching the digit pad's own
                # 4 rows — a 5th row here previously pushed the whole
                # keyword pad taller than the digit pad, and right_col has
                # no scrollbar to fall back on, so the last row was
                # clipped off entirely and invisible (reported: "cant see
                # bottom 3 button adds to keypad shortcuts at all").
                _kw_rows = [
                    [("thru", _KW, self._numpad_append, " THRU "),
                     (" +",   _NW, self._numpad_append, " + "),
                     (" - ",  _NW, self._numpad_append, " - "),
                     (" / ",  _NW, self._numpad_append, " THRU ")],
                    [("at",   _KW, self._numpad_append, " AT "),
                     ("full", _NW, self._numpad_exec,   "FULL"),
                     ("out",  _NW, self._numpad_exec,   "OUT"),
                     ("prev", _NW, self._numpad_exec,   "PREV"),
                     ("next", _NW, self._numpad_exec,   "NEXT")],
                    [("clr", _KW, self._numpad_clear_input, None),
                     ("grp",  _NW, self._numpad_append, "GROUP "),
                     ("undo", _NW, self._numpad_exec,   "UNDO"),
                     ("all",  _NW, self._numpad_exec,   "ALL")],
                    [("kill", _NW, self._numpad_exec,      "KILL FX"),
                     ("hi",   _NW, self._quick_priority,   "HIGH"),
                     ("nrm",  _NW, self._quick_priority,   "NORMAL"),
                     ("lo",   _NW, self._quick_priority,   "LOW"),
                     ("upd",  _KW, self._quick_update_active_cue, None)],
                ]
                with dpg.group():
                    for row in _kw_rows:
                        with dpg.group(horizontal=True):
                            for label, w, cb, ud in row:
                                # Tagged so the right-click undo-history
                                # popup (see _on_global_right_click in
                                # core.py) can detect a right-click on
                                # this specific button.
                                _kwargs = {'label': label, 'width': w, 'height': _NH,
                                           'callback': cb}
                                if ud is not None:
                                    _kwargs['user_data'] = ud
                                if label == "undo":
                                    _kwargs['tag'] = "numpad_undo_btn"
                                dpg.add_button(**_kwargs)
    def _quick_priority(self, _sender, _app_data, user_data):
        """hi/lo numpad buttons — set the currently active fader's priority
        directly (PRIORITY <n> HIGH/LOW), without needing that fader's row
        visible in the running-stacks panel."""
        if not self._active_fader:
            return
        cmd = f"PRIORITY {self._active_fader[0]} {user_data}"
        self._log(f"> {cmd}")
        if self._cmd:
            result = self._cmd(cmd)
            if result:
                for line in str(result).splitlines():
                    self._log(f"  {line}")
    def _quick_update_active_cue(self, *_):
        """upd numpad button — merge current programmer values into whatever
        cue is actively running on the active fader, without typing its
        number (unlike the "upd cue" quick-action button above, which still
        needs one)."""
        stk = self._stack_pool.get(self._active_fader[0]) if (
            self._stack_pool and self._active_fader) else None
        if not stk or stk.current is None:
            self._log("> upd — active fader has no cue running")
            return
        cmd = f"UPDATE CUE {stk.current}"
        self._log(f"> {cmd}")
        if self._cmd:
            result = self._cmd(cmd)
            if result:
                for line in str(result).splitlines():
                    self._log(f"  {line}")
    def _build_undo_history_popup(self):
        """Hold-undo history — the closest practical equivalent to an
        MA-style press-and-hold gesture DearPyGui can reliably support: a
        true press-and-hold would need per-frame hold-duration timing with
        no way to verify it works without a live display, whereas a
        right-click for "more options on this button" is already this
        app's own established pattern (see the pool buttons' own right-
        click context menus in pools_panel.py). Right-click either undo
        button (qbtn_undo or the numpad's undo) to open it — see
        _on_global_right_click in core.py."""
        with dpg.window(tag="undo_history_window", label="undo history",
                        width=380, height=340, show=False, pos=(700, 260),
                        no_collapse=True):
            dpg.add_text("click a step to undo everything back to it",
                         color=_C_DIM, wrap=340)
            dpg.add_separator()
            with dpg.child_window(tag="undo_history_list", width=-1, height=-1,
                                  border=False):
                dpg.add_text("— nothing to undo", tag="undo_history_empty", color=_C_DIM)
    def _open_undo_history(self):
        """Rebuild the undo-history list from the live undo stack and show
        the popup near the mouse. Called on right-click of either undo
        button (see _on_global_right_click, core.py)."""
        try:
            dpg.delete_item("undo_history_list", children_only=True)
        except Exception:
            return
        hist = self._prog.undo_history() if self._prog else []
        if not hist:
            dpg.add_text("— nothing to undo", color=_C_DIM, parent="undo_history_list")
        else:
            for step_n, (idx, desc) in enumerate(hist, 1):
                dpg.add_selectable(label=f"{step_n}.  {desc}",
                                   callback=self._on_undo_history_pick,
                                   user_data=idx,
                                   parent="undo_history_list")
        try:
            mx, my = dpg.get_mouse_pos(local=False)
            dpg.configure_item("undo_history_window", pos=(mx, my))
        except Exception:
            pass
        try:
            dpg.configure_item("undo_history_window", show=True)
            dpg.focus_item("undo_history_window")
        except Exception:
            pass
    def _on_undo_history_pick(self, _sender, _app_data, user_data):
        """A history entry was clicked — undo back to (and including) it in
        one go, then close the popup."""
        try:
            dpg.configure_item("undo_history_window", show=False)
        except Exception:
            pass
        cmd = f"UNDO TO {user_data}"
        self._log(f"> {cmd}")
        if self._cmd:
            result = self._cmd(cmd)
            if result:
                for line in str(result).splitlines():
                    self._log(f"  {line}")
    def _on_blind_toggle(self):
        """Toggle BLIND mode — suppress programmer from DMX output."""
        if self._cmd and self._out:
            self._cmd("LIVE" if self._out.blind else "BLIND")
    def _on_pt_toggle(self):
        """programmer time toggle: click to set 2s fade, click again to turn off."""
        if self._cmd:
            # Deferred import — see core.py's _tick for the same pattern
            # and full rationale (this module loads before state.py runs).
            from __main__ import _prog_time
            pt = _prog_time
            if pt.get('on'):
                self._cmd("PROG TIME OFF")
            else:
                self._cmd("PROG TIME 2")
    def _on_highlight_toggle(self):
        """Toggle HIGHLIGHT mode — selected fixtures go full-white at full dim."""
        if not self._out:
            return
        self._out.highlight_mode = not self._out.highlight_mode
        if self._out.highlight_mode:
            self._sync_highlight_selection()
            self._log("> highlight on")
        else:
            self._log("> highlight off")
    def _sync_highlight_selection(self):
        """Push the current programmer selection into the output engine's
        highlight set. Every selected object's own .fixture_id, master or
        sub — see commands/programmer.py's cmd_051_highlight for why the
        old MasterFixture-only filter left a sub-fixture-only selection
        (e.g. "1.1 THRU 1.10") highlighting nothing."""
        if not self._out or not self._prog:
            return
        self._out.highlight_fids = {f.fixture_id for f in self._prog.selection}
