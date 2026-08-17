"""GUIEngine's right column: transport controls, BLIND/HIGHLIGHT/programmer-time toggles.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.models.fixtures import MasterFixture


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

            # ── Log — larger to show more feedback lines ─────────
            with dpg.child_window(tag="cmd_log_win", width=-1, height=140,
                                  border=True, horizontal_scrollbar=False,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_text("", tag="cmd_log", wrap=0)

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

                # Right: keywords — 4 rows × (wide + narrow + narrow)
                _kw_rows = [
                    [("thru", _KW, self._numpad_append, " THRU "),
                     (" +",   _NW, self._numpad_append, " + "),
                     ("at",   _NW, self._numpad_append, " AT ")],
                    [("full", _KW, self._numpad_exec,   "FULL"),
                     ("out",  _NW, self._numpad_exec,   "OUT"),
                     (" R ",  _NW, self._numpad_append, " R ")],
                    [("dim",  _KW, self._numpad_append, " DIM "),
                     (" G ",  _NW, self._numpad_append, " G "),
                     (" B ",  _NW, self._numpad_append, " B ")],
                    [("clr", _KW, self._numpad_clear_input, None),
                     ("grp",  _NW, self._numpad_append, "GROUP "),
                     ("col",  _NW, self._numpad_append, "COLOR ")],
                ]
                with dpg.group():
                    for row in _kw_rows:
                        with dpg.group(horizontal=True):
                            for label, w, cb, ud in row:
                                if ud is not None:
                                    dpg.add_button(label=label, width=w, height=_NH,
                                                   callback=cb, user_data=ud)
                                else:
                                    dpg.add_button(label=label, width=w, height=_NH,
                                                   callback=cb)
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
        """Push the current programmer selection into the output engine's highlight set."""
        if not self._out or not self._prog:
            return
        self._out.highlight_fids = {
            f.fixture_id for f in self._prog.selection
            if isinstance(f, MasterFixture)
        }
