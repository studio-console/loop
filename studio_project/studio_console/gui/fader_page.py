"""GUIEngine's MA-style fader page grid — the _fpg_* method cluster, plus the fader-slot playback controls (_on_exec_*, _rebuild_playbacks, etc.).

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.models.presets import Fader
from studio_console.engine.playback import _exec_fader_mode_hook


class GUIEngineFaderPage:
    @staticmethod
    def _fpg_exec_for_slot(page, slot):
        """Map a fader-page slot (1.._FPG_SLOTS) on the given page to its
        underlying fader id, MA-style: page 2 slot 1 = fader 16."""
        # GUIEngine (the final composed class) isn't importable at module
        # level here — deferred import, same pattern used throughout this
        # split.
        from __main__ import GUIEngine
        return (int(page) - 1) * GUIEngine._FPG_SLOTS + int(slot)
    @staticmethod
    def _fpg_slot_for_exec(page, fdr_id):
        """Inverse of _fpg_exec_for_slot — the slot (1.._FPG_SLOTS) that
        would display fdr_id on the given page, or None if it's off-page."""
        # Deferred import — see _fpg_exec_for_slot above for rationale.
        from __main__ import GUIEngine
        slot = int(fdr_id) - (int(page) - 1) * GUIEngine._FPG_SLOTS
        return slot if 1 <= slot <= GUIEngine._FPG_SLOTS else None
    def _build_fader_page_popup(self):
        """10-slot MA-style fader page — floating, hidden by default."""
        _win_w = self._FPG_SLOTS * (self._FPG_SLOT_W + 4) + 22
        _win_h = self._FPG_SLOT_H + 80

        with dpg.window(tag="fader_page_window",
                        label=f"fader page  [page {self._fpg_page}]",
                        width=_win_w, height=_win_h, show=False,
                        pos=(100, 100), no_collapse=False):
            with dpg.group(horizontal=True):
                dpg.add_text("page:", color=_C_DIM)
                dpg.add_button(label="◀", width=26, callback=self._on_fpg_page_prev)
                dpg.add_text(f"{self._fpg_page}", tag="fpg_page_lbl", color=_C_ACCENT)
                dpg.add_button(label="▶", width=26, callback=self._on_fpg_page_next)
                dpg.add_spacer(width=8)
                dpg.add_text(f"execs {self._fpg_exec_for_slot(self._fpg_page, 1)}"
                            f"-{self._fpg_exec_for_slot(self._fpg_page, self._FPG_SLOTS)}",
                            tag="fpg_range_lbl", color=_C_DIM)
            dpg.add_separator()
            fader_h = self._FPG_FADER_H
            fader_w = self._FPG_SLOT_W - 16
            cuelist_w = self._FPG_SLOT_W - 16
            with dpg.group(horizontal=True):
                for n in range(1, self._FPG_SLOTS + 1):
                    with dpg.child_window(
                            tag=f"fpg_slot_{n}",
                            width=self._FPG_SLOT_W, height=self._FPG_SLOT_H,
                            border=True, no_scrollbar=True, no_scroll_with_mouse=True):

                        # row 1 — fdr id (click to set stack focus) +
                        # priority badge + output mode badge
                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                tag=f"fpg_id_{n}", label=f"{n}",
                                width=22, height=self._FPG_BADGE_H,
                                callback=self._on_fpg_id_click, user_data=n)
                            dpg.bind_item_theme(f"fpg_id_{n}", self._fpg_id_theme)
                            dpg.add_button(
                                tag=f"fpg_pri_{n}", label="nrm",
                                width=30, height=self._FPG_BADGE_H,
                                callback=self._on_fpg_pri_cycle, user_data=n)
                            dpg.add_button(
                                tag=f"fpg_out_{n}", label="nrm",
                                width=30, height=self._FPG_BADGE_H,
                                callback=self._on_fpg_out_cycle, user_data=n)

                        # row 2 — stack name, single line, truncated (was
                        # wrap= — a wrapped 2nd line silently blew the fixed
                        # per-slot height budget every row below is sized
                        # against; see _FPG_FIXED_ROWS_H in core.py)
                        dpg.add_text("—", tag=f"fpg_name_{n}", color=_C_ACCENT)

                        # row 3 — full-width cue list: every cue in the
                        # stack, running one marked with ▶ and highlighted
                        # via highlight_table_row (a per-row bg color the
                        # renderer always draws, unlike add_listbox's
                        # built-in "selected" color, which is ImGui's
                        # Header/HeaderHovered pair — HeaderHovered fires
                        # for whatever row the mouse happens to be over,
                        # selected or not, so a themed listbox meant any
                        # cue lit up on hover, not just the running one.
                        # highlight_table_row is exactly the mechanism the
                        # left-column cue list already uses for this same
                        # "mark the running cue" job (see core.py's
                        # _tick()) — reused here instead of a second,
                        # different approach. Click jumps straight to that
                        # cue via GOTO.
                        with dpg.child_window(
                                tag=f"fpg_cuelist_{n}",
                                width=cuelist_w,
                                height=self._FPG_CUELIST_ITEMS * self._FPG_CUELIST_ROW_H + 8,
                                border=True, no_scrollbar=False,
                                no_scroll_with_mouse=False):
                            with dpg.table(tag=f"fpg_cuelist_tbl_{n}",
                                           header_row=False,
                                           borders_innerH=False, borders_outerH=False,
                                           borders_innerV=False, borders_outerV=False,
                                           policy=dpg.mvTable_SizingFixedFit,
                                           resizable=False):
                                dpg.add_table_column(width_stretch=True, init_width_or_weight=1.0)

                        # row 4 — full-width fader, MA-style. Deliberately a
                        # plain, unmodified add_slider_int — no pos= overlay,
                        # no drawn fill underneath it. An earlier version
                        # tried a drawlist-fill-plus-transparent-slider
                        # overlay for a true bottom-up fill look; on a real
                        # run the drag stopped working entirely. This is the
                        # same interactive mechanism the original (never
                        # reported broken) narrow fader used, just resized
                        # and themed — colored track + a big bright grab via
                        # _make_fpg_fader_theme, guaranteed to actually drag.
                        dpg.add_slider_int(
                            tag=f"fpg_fader_{n}",
                            vertical=True,
                            width=fader_w, height=fader_h,
                            min_value=0, max_value=255,
                            default_value=255, format="",
                            no_input=True,
                            callback=self._on_fpg_fader, user_data=n)
                        dpg.bind_item_theme(f"fpg_fader_{n}", self._fpg_fader_theme)

                        # row 5 — level %
                        dpg.add_text("100%", tag=f"fpg_level_{n}", color=_C_DIM)

                        # rows 6-8 — A/B/C buttons with right-click reassign popups
                        for _s, _default_lbl in (('a', 'go'), ('b', 'back'), ('c', 'stop')):
                            _btag = f"fpg_btn{_s}_{n}"
                            dpg.add_button(
                                tag=_btag, label=_default_lbl,
                                width=self._FPG_BTN_W, height=self._FPG_BTN_H,
                                callback=self._on_fpg_btn, user_data=(n, _s))
                            with dpg.popup(_btag, mousebutton=1):
                                dpg.add_text(f"assign button {_s.upper()}", color=_C_ACCENT)
                                dpg.add_separator()
                                for _fn in ('GO', 'BACK', 'STOP', 'FLASH', 'RATE+', 'RATE-', 'SIZE+', 'SIZE-'):
                                    dpg.add_menu_item(
                                        label=_fn.lower(),
                                        callback=self._on_fpg_btn_assign,
                                        user_data=(n, _s, _fn))

                        # row 9 — separator
                        dpg.add_separator()

                        # row 10 — trigger mode badge (full-width, cycles on click)
                        dpg.add_button(
                            tag=f"fpg_trig_{n}", label="tgl",
                            width=self._FPG_BTN_W, height=self._FPG_BTN_H,
                            callback=self._on_fpg_trig_cycle, user_data=n)
    def _on_fader_page_toggle(self, *_):
        try:
            vis = dpg.is_item_shown("fader_page_window")
            if vis:
                dpg.hide_item("fader_page_window")
            else:
                self._fpg_refresh_all()
                dpg.show_item("fader_page_window")
            self._save_popup_layout()
        except Exception:
            pass
    def _fpg_step_page(self, delta):
        """Pure page-number update (no dpg calls) — clamped to >= 1. Split out
        from the prev/next callbacks so it's exercisable without a live dpg
        context (e.g. from the headless smoke test)."""
        self._fpg_page = max(1, self._fpg_page + int(delta))
        return self._fpg_page
    def _on_fpg_page_prev(self, *_):
        self._fpg_step_page(-1)
        self._fpg_page_changed()
    def _on_fpg_page_next(self, *_):
        self._fpg_step_page(1)
        self._fpg_page_changed()
    def _fpg_page_changed(self):
        """Update the page label/title/range display and re-sync all slots
        after the page number changes — otherwise slots would keep showing
        stale data from the previously-displayed bank of faders."""
        try:
            dpg.set_value("fpg_page_lbl", f"{self._fpg_page}")
            dpg.configure_item("fader_page_window",
                               label=f"fader page  [page {self._fpg_page}]")
            dpg.set_value("fpg_range_lbl",
                          f"execs {self._fpg_exec_for_slot(self._fpg_page, 1)}"
                          f"-{self._fpg_exec_for_slot(self._fpg_page, self._FPG_SLOTS)}")
        except Exception:
            pass
        self._fpg_refresh_all()
    def _fpg_reflow(self, win_w, win_h):
        """Resize all fader slot child-windows to fill the current window
        dimensions. Uses the exact same _FPG_FIXED_ROWS_H budget the
        initial build used (core.py) — the two can't drift apart from
        each other since they share the one constant, which is the whole
        point: the old version hand-tuned this math separately in two
        places and they quietly disagreed, clipping the bottom buttons."""
        _H_HDR   = 80   # title bar + page-controls row + separator + window padding
        _W_EDGE  = 22   # left + right outer window padding
        _W_GAP   = 4    # gap between adjacent child-window slots

        slot_h      = max(260, win_h - _H_HDR)
        slot_w      = max(90,  (win_w - _W_EDGE) // self._FPG_SLOTS - _W_GAP)
        # _FPG_FIXED_ROWS_H's per-row heights (badge/name/level-text/
        # separator rows) are close estimates, not exact widget heights —
        # a small safety margin here is what keeps the last row (trigger
        # badge) from landing a few px past the bottom of the fixed
        # slot_h and getting silently clipped by no_scrollbar=True.
        fader_h     = max(80,  slot_h - self._FPG_FIXED_ROWS_H - self._FPG_ROW_SAFETY)
        fader_w     = max(60,  slot_w - 16)   # full-width fader, not a sliver
        cuelist_w   = max(60,  slot_w - 16)
        # Full-width single-child rows only need the child_window's own
        # left+right WindowPadding (8px each, theme.py) subtracted once.
        btn_w       = max(36,  slot_w - 16)
        # Row 1 (fdr# text + pri badge + out badge, horizontal) instead has
        # THREE children sharing the row: WindowPadding (16 total) + the
        # "{n}" slot-number text (~20px, generous for 2 digits) + two
        # ItemSpacing.x gaps (6px each, theme.py) between the three items,
        # before what's left splits between the two badges. The previous
        # formula didn't account for the text or the spacing at all, so
        # the row quietly ran ~20-25px wider than the slot — exactly what
        # clipped the (rightmost) output-mode badge off the visible edge.
        badge_w     = max(24,  (slot_w - 16 - 20 - 12) // 2)

        for n in range(1, self._FPG_SLOTS + 1):
            try:
                dpg.configure_item(f"fpg_slot_{n}",    width=slot_w,  height=slot_h)
                dpg.configure_item(f"fpg_cuelist_{n}", width=cuelist_w)
                dpg.configure_item(f"fpg_fader_{n}",   width=fader_w, height=fader_h)
                dpg.configure_item(f"fpg_pri_{n}",     width=badge_w)
                dpg.configure_item(f"fpg_out_{n}",     width=badge_w)
                for _s in ('a', 'b', 'c'):
                    dpg.configure_item(f"fpg_btn{_s}_{n}", width=btn_w)
                dpg.configure_item(f"fpg_trig_{n}", width=btn_w)
            except Exception:
                pass
    def _fpg_refresh_all(self):
        """Sync all fader page slot labels and fader positions from fader pool."""
        if not self._fader_pool:
            return
        _name_w = self._FPG_SLOT_W - 10
        for n in range(1, self._FPG_SLOTS + 1):
            eid = self._fpg_exec_for_slot(self._fpg_page, n)
            ex = self._fader_pool.faders.get(eid)
            try:
                if ex and ex.stack:
                    dpg.set_value(f"fpg_name_{n}", self._fit_text(ex.stack.name, _name_w))
                else:
                    dpg.set_value(f"fpg_name_{n}", "—")
                lvl = ex.level if ex else 1.0
                dpg.set_value(f"fpg_fader_{n}", round(lvl * 255))
            except Exception:
                pass
    def _on_fpg_fader(self, _sender, value, user_data):
        n = int(user_data)
        if self._fader_pool:
            eid = self._fpg_exec_for_slot(self._fpg_page, n)
            ex = self._fader_pool.faders.get(eid)
            if ex:
                ex.level = max(0.0, min(1.0, float(value) / 255.0))
                _exec_fader_mode_hook(ex)
    def _on_fpg_btn(self, _sender, _app_data, user_data):
        n, slot = user_data
        eid = self._fpg_exec_for_slot(self._fpg_page, n)
        ex = self._fader_pool.faders.get(eid) if self._fader_pool else None
        if not ex or not self._cmd:
            return
        fn = getattr(ex, f'btn_{slot}', 'GO')
        if fn == 'FLASH':
            return  # hold polling handled by tick loop
        self._cmd(f"FADER {eid} {fn}")
    def _set_fader_focus(self, eid):
        """Give fader `eid` stack focus (active_fader) and log it — the
        same state _on_stack_click sets from the left-column stack list.
        "Focus" = which stack left-column commands like RECORD CUE/
        UPDATE CUE currently target; independent of which fader(s) are
        actually running. Shared by every "click an id badge to focus
        this fader" spot — the fader-page grid and the main-page running-
        stacks panel both call this rather than duplicating the logic."""
        if self._active_fader is not None:
            self._active_fader[0] = eid
        ex = self._fader_pool.faders.get(eid) if self._fader_pool else None
        name = ex.stack.name if (ex and ex.stack) else "—"
        if self._log:
            self._log(f"> focus → fader {eid}  ({name})")
    def _on_fpg_id_click(self, _sender, _app_data, user_data):
        """Click a fader-page slot's id badge to give that fader focus."""
        n = int(user_data)
        eid = self._fpg_exec_for_slot(self._fpg_page, n)
        self._set_fader_focus(eid)
    def _on_playback_id_click(self, _sender, _app_data, user_data):
        """Click a running-stacks row's id badge (main page) to give that
        fader focus — same action as the fader-page grid's id badge."""
        self._set_fader_focus(int(user_data))
    def _on_fpg_pri_cycle(self, _sender, _app_data, user_data):
        """Cycle priority for the fader in fader page slot user_data (nrm→hi→lo→nrm)."""
        n = int(user_data)
        eid = self._fpg_exec_for_slot(self._fpg_page, n)
        ex = self._fader_pool.faders.get(eid) if self._fader_pool else None
        if not ex or not self._cmd:
            return
        _cycle  = {0: 1, 1: -1, -1: 0}
        _labels = {-1: 'LOW', 0: 'NORMAL', 1: 'HIGH'}
        nxt = _cycle.get(getattr(ex, 'priority', 0), 0)
        self._cmd(f"PRIORITY {eid} {_labels[nxt]}")
    def _on_fpg_out_cycle(self, _sender, _app_data, user_data):
        """Cycle output_mode for the fader in fader page slot user_data."""
        n = int(user_data)
        eid = self._fpg_exec_for_slot(self._fpg_page, n)
        ex = self._fader_pool.faders.get(eid) if self._fader_pool else None
        if not ex or not self._cmd:
            return
        _cycle = {'normal': 'moment', 'moment': 'vfade', 'vfade': 'normal'}
        nxt = _cycle.get(getattr(ex, 'output_mode', 'normal'), 'normal')
        self._cmd(f"FADER {eid} OUTPUT {nxt.upper()}")
    def _on_fpg_trig_cycle(self, _sender, _app_data, user_data):
        """Cycle trigger_mode for the fader in fader page slot user_data."""
        n = int(user_data)
        eid = self._fpg_exec_for_slot(self._fpg_page, n)
        ex = self._fader_pool.faders.get(eid) if self._fader_pool else None
        if not ex or not self._cmd:
            return
        _cycle = {'toggle': 'flash', 'flash': 'moment', 'moment': 'toggle'}
        nxt = _cycle.get(getattr(ex, 'trigger_mode', 'toggle'), 'toggle')
        self._cmd(f"FADER {eid} MODE {nxt.upper()}")
    def _on_fpg_btn_assign(self, _sender, _app_data, user_data):
        """Assign a new function to fader page button slot (right-click popup)."""
        n, btn_slot, fn = user_data
        eid = self._fpg_exec_for_slot(self._fpg_page, n)
        if self._cmd:
            self._cmd(f"FADER {eid} BTN {btn_slot.upper()} {fn}")
    def _on_fpg_cuelist_click(self, _sender, _app_data, user_data):
        """GOTO the cue the user clicked in the fader page cue list."""
        n, cue_num = user_data
        eid = self._fpg_exec_for_slot(self._fpg_page, n)
        if self._cmd:
            self._cmd(f"GOTO {eid} {cue_num}")
    def _fpg_rebuild_cuelist(self, n, stack):
        """(Re)build the row widgets for fader-page slot n's cue list.
        Only called when the stack assigned to this slot, or its set of
        cue numbers, actually changes — not every tick — since it deletes
        and recreates every row. Per-tick updates (the ▶ marker and the
        running-row highlight) are cheap set_item_label/highlight_table_row
        calls handled separately in _tick_fader_page."""
        tbl_tag = f"fpg_cuelist_tbl_{n}"
        try:
            dpg.delete_item(tbl_tag, children_only=True)
        except Exception:
            return
        dpg.add_table_column(parent=tbl_tag, width_stretch=True, init_width_or_weight=1.0)
        nums = stack._sorted_cue_numbers() if stack else []
        if not nums:
            with dpg.table_row(parent=tbl_tag):
                dpg.add_text("—", color=_C_DIM)
            return
        for idx, cn in enumerate(nums):
            cue = stack.cues[cn]
            with dpg.table_row(parent=tbl_tag):
                dpg.add_selectable(
                    label=f"  {cn:.0f} {cue.name}",
                    tag=f"fpg_cue_row_{n}_{idx}",
                    span_columns=True,
                    callback=self._on_fpg_cuelist_click,
                    user_data=(n, cn))
    def _tick_fader_page(self):
        """Update fader page slot labels + mode badges (called from _tick)."""
        if not dpg.is_item_shown("fader_page_window"):
            return
        if not self._fader_pool:
            return
        for n in range(1, self._FPG_SLOTS + 1):
            eid = self._fpg_exec_for_slot(self._fpg_page, n)
            ex  = self._fader_pool.faders.get(eid)
            try:
                # ── name ─────────────────────────────────────
                _nm = ex.stack.name if (ex and ex.stack) else "—"
                dpg.set_value(f"fpg_name_{n}",
                              self._fit_text(_nm, self._FPG_SLOT_W - 10))

                # ── cue list: every cue, running one marked + highlighted ──
                _cs  = ex.stack if ex else None
                _nums = _cs._sorted_cue_numbers() if _cs else []
                _sig = (_cs.stack_id, tuple(_nums)) if _cs else (None, ())
                if self._fpg_cuelist_sig.get(n) != _sig:
                    self._fpg_rebuild_cuelist(n, _cs)
                    self._fpg_cuelist_sig[n] = _sig
                if _cs and _nums:
                    _cur = _cs.current
                    _tbl = f"fpg_cuelist_tbl_{n}"
                    _sel_idx = None
                    for idx, _cn in enumerate(_nums):
                        _cue = _cs.cues[_cn]
                        _row_tag = f"fpg_cue_row_{n}_{idx}"
                        _is_cur = (_cn == _cur)
                        try:
                            dpg.set_item_label(
                                _row_tag,
                                f"{'▶' if _is_cur else ' '} {_cn:.0f} {_cue.name}")
                            if _is_cur:
                                dpg.highlight_table_row(_tbl, idx, _C_FPG_ACCENT_DIM)
                                _sel_idx = idx
                            else:
                                dpg.unhighlight_table_row(_tbl, idx)
                        except Exception:
                            pass
                    # Manual scroll-to-current-row, same reasoning as the
                    # left-column cue list (core.py _tick()) and this
                    # widget's own previous listbox-based version: one row
                    # of headroom above the current cue so the next
                    # upcoming one stays visible too, clamped to the real
                    # scroll max since the row-height estimate only has to
                    # be close for cues mid-list — a cue near the end
                    # always reaches the true bottom regardless.
                    if _sel_idx is not None:
                        try:
                            _row_h = self._FPG_CUELIST_ROW_H
                            _target = max(0, (_sel_idx - 1) * _row_h)
                            _smax = dpg.get_y_scroll_max(f"fpg_cuelist_{n}")
                            if _smax:
                                _target = min(_target, _smax)
                            dpg.set_y_scroll(f"fpg_cuelist_{n}", _target)
                        except Exception:
                            pass

                # ── fader (sync when not dragging) ───────────
                _lvl01 = ex.level if ex else 1.0
                if not dpg.is_item_active(f"fpg_fader_{n}"):
                    dpg.set_value(f"fpg_fader_{n}", round(_lvl01 * 255))
                lv = _lvl01 * 100
                dpg.set_value(f"fpg_level_{n}", f"{lv:.0f}%")

                # ── button labels + color themes ──────────────
                _btn_defaults = {'a': 'GO', 'b': 'BACK', 'c': 'STOP'}
                _btn_themes   = {
                    'GO':    self._go_btn_theme,
                    'FLASH': self._go_btn_theme,
                    'STOP':  self._stop_btn_theme,
                }
                for _s in ('a', 'b', 'c'):
                    fn = getattr(ex, f'btn_{_s}', _btn_defaults[_s]) if ex else _btn_defaults[_s]
                    dpg.set_item_label(f"fpg_btn{_s}_{n}", fn.lower())
                    _bt = _btn_themes.get(fn, self._dim_btn_theme)
                    if _bt:
                        dpg.bind_item_theme(f"fpg_btn{_s}_{n}", _bt)

                # ── output mode badge ─────────────────────────
                out_mode = getattr(ex, 'output_mode', 'normal') if ex else 'normal'
                _out_labels = {'normal': 'nrm', 'moment': 'mom', 'vfade': 'vfd'}
                dpg.set_item_label(f"fpg_out_{n}", _out_labels.get(out_mode, 'nrm'))
                _out_themes = {
                    'normal': self._dim_btn_theme,
                    'moment': self._out_moment_theme,
                    'vfade':  self._out_vfade_theme,
                }
                _ot = _out_themes.get(out_mode, self._dim_btn_theme)
                if _ot:
                    dpg.bind_item_theme(f"fpg_out_{n}", _ot)

                # ── priority badge ────────────────────────────
                pri = getattr(ex, 'priority', 0) if ex else 0
                _pri_labels = {-1: 'lo', 0: 'nrm', 1: 'hi'}
                dpg.set_item_label(f"fpg_pri_{n}", _pri_labels.get(pri, 'nrm'))
                _pri_themes = {
                    -1: self._pri_lo_theme,
                     0: self._dim_btn_theme,
                     1: self._pri_hi_theme,
                }
                _pt = _pri_themes.get(pri, self._dim_btn_theme)
                if _pt:
                    dpg.bind_item_theme(f"fpg_pri_{n}", _pt)

                # ── trigger mode badge ────────────────────────
                trig_mode = getattr(ex, 'trigger_mode', 'toggle') if ex else 'toggle'
                _trig_labels = {'toggle': 'tgl', 'flash': 'fls', 'moment': 'mom'}
                dpg.set_item_label(f"fpg_trig_{n}", _trig_labels.get(trig_mode, 'tgl'))
                _trig_themes = {
                    'toggle': self._dim_btn_theme,
                    'flash':  self._trig_flash_theme,
                    'moment': self._trig_moment_theme,
                }
                _tt = _trig_themes.get(trig_mode, self._dim_btn_theme)
                if _tt:
                    dpg.bind_item_theme(f"fpg_trig_{n}", _tt)

                # ── focused slot outline ──────────────────────
                # "Focus" = active_fader, what left-column commands like
                # RECORD CUE currently target. Only the focused fader gets
                # an outline; exactly one slot at a time. A running cue is
                # signalled separately, per-cue, by highlight_table_row on
                # its row in this slot's own cue list above (blue) — not
                # by outlining the whole fader slot, since multiple
                # faders can be running at once but only one ever has
                # focus. This one is a plain white border only — no
                # fill/background change, every other slot's own panel
                # background stays exactly as it already is. The id
                # badge (now clickable — see _on_fpg_id_click) doubles
                # as the focus indicator: white text + brackets when
                # this fader has focus, dim otherwise.
                focused_eid = self._active_fader[0] if self._active_fader else None
                is_focused = bool(ex and eid == focused_eid)
                if is_focused and self._selected_slot_theme:
                    dpg.bind_item_theme(f"fpg_slot_{n}", self._selected_slot_theme)
                else:
                    dpg.bind_item_theme(f"fpg_slot_{n}", 0)
                dpg.set_item_label(f"fpg_id_{n}", f"[{n}]" if is_focused else f"{n}")
                dpg.bind_item_theme(f"fpg_id_{n}",
                                    self._fpg_id_focused_theme if is_focused
                                    else self._fpg_id_theme)

            except Exception:
                pass

        # ── reflow on window resize ───────────────────────────
        try:
            _sz  = dpg.get_item_rect_size("fader_page_window")
            _wsz = (int(_sz[0]), int(_sz[1]))
            if _wsz[0] > 10 and _wsz != self._fpg_last_win_size:
                self._fpg_last_win_size = _wsz
                self._fpg_reflow(_wsz[0], _wsz[1])
        except Exception:
            pass
    def _rebuild_cue_list(self, stack):
        """Clear and repopulate the left-column cue list for the given stack."""
        dpg.delete_item("cue_list_group", children_only=True)
        if not stack:
            return
        sid = stack.stack_id
        with dpg.table(parent="cue_list_group", tag=f"cl_tbl_{sid}",
                       header_row=False, resizable=False,
                       borders_innerH=True, borders_innerV=False,
                       borders_outerH=False, borders_outerV=False,
                       row_background=True,
                       scrollX=False, scrollY=False,
                       policy=dpg.mvTable_SizingFixedFit):
            dpg.add_table_column(label="#", width_fixed=True, init_width_or_weight=42)
            dpg.add_table_column(label="name", width_stretch=True, init_width_or_weight=1.0)
            dpg.add_table_column(label="t", width_fixed=True, init_width_or_weight=50)
            numbers = stack._sorted_cue_numbers()
            for num in numbers:
                cue  = stack.cues[num]
                tag  = f"cue_row_{sid}_{num}"
                ft   = f"{cue.fade_time:.1f}s" if cue.fade_time else ""
                fw   = getattr(cue, 'follow_time', 0.0)
                if fw > 0:
                    ft = (ft + f" →{fw:.0f}s") if ft else f"→{fw:.0f}s"
                note = getattr(cue, 'note', '')
                with dpg.table_row():
                    dpg.add_text(f"{num:.0f}", color=_C_ACCENT)
                    dpg.add_selectable(label=cue.name, tag=tag,
                                       span_columns=False,
                                       callback=lambda *_, u=num: self._goto(u),
                                       user_data=num)
                    if note:
                        with dpg.tooltip(tag):
                            dpg.add_text(note, color=(200, 200, 160, 255))
            # Wrap-to-1 warning row — sitting right on the current cue at the
            # end of the stack, "next GO wraps back to the start" is easy to
            # miss since the real cue 1 row is scrolled off the top of a long
            # list. Duplicating a preview of it directly under the last cue
            # puts the warning where the operator is actually looking.
            # Built once here (hidden by default) and toggled/highlighted red
            # per-tick in core.py's autoscroll block, exactly when the
            # current cue is genuinely the last one (bounce mode never
            # wraps, so it's skipped there). Number column repeats "1" (that
            # IS which cue this is — see the red colour + separator for what
            # marks it as the wrap preview, not a duplicate real cue).
            if len(numbers) > 1 and not getattr(stack, 'bounce', False):
                first_num = numbers[0]
                first_cue = stack.cues[first_num]
                with dpg.table_row(tag=f"cue_wrap_row_{sid}", show=False):
                    dpg.add_text("1", tag=f"cue_wrap_num_{sid}", color=_C_CUE_WRAP)
                    dpg.add_selectable(label=f"↻ {first_cue.name}",
                                       tag=f"cue_wrap_sel_{sid}",
                                       span_columns=False,
                                       callback=lambda *_, u=first_num: self._goto(u),
                                       user_data=first_num)
                    dpg.add_text("wrap", color=_C_CUE_WRAP)
                    dpg.add_text(ft, color=_C_DIM)
    def _playbacks_state_hash(self):
        """Compact snapshot of running fader state — used to detect changes.
        Includes the active fader id: the list is ordered selected-fader-
        first (see _rebuild_playbacks), so switching selection changes the
        row order even when no fader's own state changed at all."""
        if not self._fader_pool:
            return ()
        active_id = self._active_fader[0] if self._active_fader else None
        return (active_id,) + tuple(
            (eid, ex.priority, ex.stack.current if ex.stack else None,
             ex.time_override_on, ex.time_override_fade, ex.is_active,
             getattr(ex, 'output_mode', 'normal'), getattr(ex, 'trigger_mode', 'toggle'))
            for eid, ex in sorted(self._fader_pool.faders.items())
            if ex.is_active and ex.stack
        )
    @staticmethod
    def _fit_text(text, max_w):
        """Truncate text with an ellipsis so its rendered width stays <= max_w px.
        Used to keep the active-playbacks row's trailing action buttons from
        being pushed off the edge of the (fixed-width) left column by a long
        stack/cue name."""
        try:
            if dpg.get_text_size(text)[0] <= max_w:
                return text
            while text and dpg.get_text_size(text + "…")[0] > max_w:
                text = text[:-1]
            return (text + "…") if text else "…"
        except Exception:
            return text
    def _rebuild_playbacks(self):
        """Rebuild the running-stacks list — only shows actively playing faders."""
        try:
            dpg.delete_item("playbacks_list", children_only=True)
        except Exception:
            return

        # Order: the currently active/selected fader's row first (whatever
        # the left column's "stack" combo is showing), then every other
        # running fader by its stack's pool number — was most-recently-
        # fired first, which meant the row you're actually looking at (the
        # one you have selected) could land anywhere in the list.
        active = []
        if self._fader_pool:
            running_eids = [eid for eid, ex in self._fader_pool.faders.items()
                            if ex.is_active and ex.stack]
            selected_eid = self._active_fader[0] if self._active_fader else None
            rest = [eid for eid in running_eids if eid != selected_eid]
            rest.sort(key=lambda eid: self._fader_pool.faders[eid].stack.stack_id)
            ordered = ([selected_eid] if selected_eid in running_eids else []) + rest
            for eid in ordered:
                active.append(self._fader_pool.faders[eid])

        if not active:
            dpg.add_text("— none running", tag="playbacks_empty",
                         color=_C_DIM, parent="playbacks_list")
            return

        # Name/cue get their own row, entirely separate from the action
        # buttons below (see the width-aware button row further down) —
        # they used to share one row, squeezing the name down to just
        # "[3]..." with nothing of the actual stack name visible (reported:
        # buttons hiding the name, and the surviving "[3]" reading as a
        # redundant number next to the cue label's own leading number, e.g.
        # "[3]... ▶ 3: warm…").
        try:
            _row_w = dpg.get_item_rect_size("playbacks_list")[0] or 349
        except Exception:
            _row_w = 349
        _label_budget = max(60, _row_w - 12)
        _name_w = _label_budget * 2 // 5
        _cue_w  = _label_budget - _name_w

        for i, ex in enumerate(active):
            stk  = ex.stack
            cur = stk.current
            if cur is not None:
                cue = stk.cues.get(cur)
                cue_label = f"▶ {cur:.0f}: {cue.name}" if cue else f"▶ {cur:.0f}"
            else:
                cue_label = "▶ —"
            pri_label = Fader.PRIORITY_LABELS.get(ex.priority, 'nrm')
            _mode_tag = {'moment': ' ◉', 'vfade': ' ⇕'}.get(
                getattr(ex, 'output_mode', 'normal'), '')
            _trig_tag = {'flash': ' ⚡', 'moment': ' ◌'}.get(
                getattr(ex, 'trigger_mode', 'toggle'), '')
            # Id badge is its own clickable button now (click it to give
            # this fader stack focus — same action, same visual language
            # as the fader-page grid's id badge), split out of what used
            # to be one plain "[id] name" text — _rebuild_playbacks only
            # runs when _playbacks_state_hash() changes, and that hash
            # already includes active_fader, so the focused/not-focused
            # look here only needs to be correct at build time, no
            # separate per-tick update pass like the grid needs.
            _cur_focus  = self._active_fader[0] if self._active_fader else None
            is_focused  = (ex.fdr_id == _cur_focus)
            _stack_label = f"{stk.name}{_mode_tag}{_trig_tag}"
            _id_w      = 30
            _fit_stack = self._fit_text(_stack_label, max(20, _name_w - _id_w - 6))
            _fit_cue   = self._fit_text(cue_label, _cue_w)
            if i > 0:
                dpg.add_separator(parent="playbacks_list")
            with dpg.group(horizontal=True, parent="playbacks_list"):
                _id_tag   = f"pb_id_{ex.fdr_id}"
                _name_tag = f"pb_name_{ex.fdr_id}"
                _cue_tag  = f"pb_cue_{ex.fdr_id}"
                dpg.add_button(label=f"[{ex.fdr_id}]" if is_focused else f"{ex.fdr_id}",
                               tag=_id_tag, width=_id_w, height=20,
                               callback=self._on_playback_id_click, user_data=ex.fdr_id)
                dpg.bind_item_theme(_id_tag,
                                    self._fpg_id_focused_theme if is_focused
                                    else self._fpg_id_theme)
                with dpg.tooltip(_id_tag):
                    dpg.add_text(f"fader {ex.fdr_id} — click to give it focus")
                dpg.add_text(_fit_stack, tag=_name_tag, color=_C_TEXT)
                if _fit_stack != _stack_label:
                    with dpg.tooltip(_name_tag):
                        dpg.add_text(_stack_label)
                dpg.add_text(_fit_cue, tag=_cue_tag, color=_C_ACCENT)
                if _fit_cue != cue_label:
                    with dpg.tooltip(_cue_tag):
                        dpg.add_text(cue_label)
            # Back to one row for all 5 action buttons (time/priority/a/b/c)
            # — a two-row split fixed the earlier clipping but ate an extra
            # row per running fader for no real reason, and the whole point
            # of giving this panel more height was to fit more stacks, not
            # more rows per stack. Fits for real this time by measuring the
            # row's actual width (same _row_w as the name/cue split above)
            # and dividing it between the 5 slots, then pre-fitting each
            # button's own label text into its slot with the same
            # _fit_text() ellipsis logic the name/cue labels already use —
            # a real per-frame text measurement against the live font, not
            # another hand-guessed width, so a slot that's genuinely too
            # narrow for "back"/"stop" shrinks the text instead of
            # overflowing past the button (and still shows the full label
            # in a hover tooltip).
            _btn_gap  = 6   # theme ItemSpacing.x
            _btn_avail = max(200, _row_w - 4 * _btn_gap)
            _time_w = max(40, int(_btn_avail * 0.22))
            _act_w  = max(32, (_btn_avail - _time_w) // 4)
            with dpg.group(horizontal=True, parent="playbacks_list"):
                # Time override badge
                if ex.time_override_on and ex.time_override_fade is not None:
                    t_label  = f"t{ex.time_override_fade:.1f}s"
                    dpg.add_button(label=self._fit_text(t_label, _time_w - 16),
                                   width=_time_w, height=20,
                                   callback=self._on_exec_time_toggle,
                                   user_data=ex.fdr_id)
                    dpg.configure_item(dpg.last_item(), enabled=stk.allow_exec_time)
                    if not stk.allow_exec_time:
                        dpg.add_text("×", color=_C_DIM)
                else:
                    dpg.add_button(label=self._fit_text("time", _time_w - 16),
                                   width=_time_w, height=20,
                                   callback=self._on_exec_time_toggle,
                                   user_data=ex.fdr_id)
                dpg.add_button(label=self._fit_text(pri_label, _act_w - 16),
                               width=_act_w, height=20,
                               callback=self._on_priority_cycle,
                               user_data=ex.fdr_id)
                for _slot, _fn in (('a', ex.btn_a), ('b', ex.btn_b), ('c', ex.btn_c)):
                    _tag = f"ebtn_{_slot}_{ex.fdr_id}"
                    _lbl = _fn.lower()
                    dpg.add_button(label=self._fit_text(_lbl, _act_w - 16), tag=_tag,
                                   width=_act_w, height=20,
                                   callback=self._on_exec_slot_btn,
                                   user_data=(ex.fdr_id, _slot))
                    if self._fit_text(_lbl, _act_w - 16) != _lbl:
                        with dpg.tooltip(_tag):
                            dpg.add_text(_lbl)
            # fader level row — 0-100 (%), matching the fader page's own
            # faders (shown as a separate "N%" text there rather than the
            # slider's own number, but the same 0-100 scale) instead of
            # this one baring the raw 0-255 DMX-style value.
            dpg.add_slider_int(
                tag=f"exec_fader_{ex.fdr_id}",
                default_value=int(ex.level * 100),
                min_value=0, max_value=100,
                width=-1, height=16,
                format="%d%%",
                callback=self._on_exec_fader,
                user_data=ex.fdr_id,
                parent="playbacks_list")
            # Fade progress bar (thin, amber) — shows crossfade progress live
            dpg.add_progress_bar(
                tag=f"exec_fade_{ex.fdr_id}",
                default_value=0.0,
                width=-1, height=5,
                overlay="",
                parent="playbacks_list")
            try:
                dpg.bind_item_theme(f"exec_fade_{ex.fdr_id}",
                                    self._fade_bar_theme)
            except Exception:
                pass
    def _on_exec_time_toggle(self, sender, app_data, user_data):  # noqa: ARG002
        """Toggle fader time override on/off from playbacks panel."""
        if self._fader_pool:
            ex = self._fader_pool.faders.get(int(user_data))
            if ex:
                ex.time_override_on = not ex.time_override_on
        self._last_playbacks_hash = None
    def _on_priority_cycle(self, sender, app_data, user_data):
        if self._fader_pool:
            ex = self._fader_pool.faders.get(int(user_data))
            if ex:
                # NRM → HI → LO → NRM
                cycle = {0: 1, 1: -1, -1: 0}
                ex.priority = cycle.get(ex.priority, 0)
        self._last_playbacks_hash = None
    def _on_exec_flash_btn(self, sender, app_data, user_data):
        # flash on/OFF is handled by the tick loop via is_item_active() polling.
        pass
    def _on_exec_slot_btn(self, sender, app_data, user_data):
        eid, slot = user_data
        ex = self._fader_pool.faders.get(eid) if self._fader_pool else None
        if not ex or not self._cmd:
            return
        fn = getattr(ex, f'btn_{slot}', 'GO')
        if fn == 'FLASH':
            return  # hold behavior — tick loop handles via is_item_active()
        self._cmd(f"FADER {eid} {fn}")
    def _on_stop_fader(self, sender, app_data, user_data):
        fdr_id = int(user_data)
        if self._fader_pool:
            ex = self._fader_pool.faders.get(fdr_id)
            if ex:
                ex.stop()
        self._last_playbacks_hash = None
    def _on_stop_all_faders(self):
        if self._fader_pool:
            for ex in list(self._fader_pool.faders.values()):
                if ex.is_active:
                    ex.stop()
        self._last_playbacks_hash = None   # force rebuild next tick
    def _on_cs_combo_select(self, _sender, value, _user_data):
        """Switch active stack from the left-column combo."""
        if not value or value == "—":
            return
        try:
            n = int(value.split(":")[0])
        except (ValueError, IndexError):
            return
        if self._cmd:
            self._cmd(f"STACK {n}")
    def _on_exec_fader(self, _sender, value, user_data):
        if self._fader_pool:
            ex = self._fader_pool.faders.get(int(user_data))
            if ex:
                ex.level = max(0.0, min(1.0, float(value) / 100.0))
                _exec_fader_mode_hook(ex)
