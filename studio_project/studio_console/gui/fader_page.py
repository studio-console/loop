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
        """15-slot MA-style fader page — floating, hidden by default."""
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
            n_items = max(3, fader_h // 21)
            self._fpg_fader_dims = (self._FPG_FADER_W, fader_h)
            with dpg.group(horizontal=True):
                for n in range(1, self._FPG_SLOTS + 1):
                    with dpg.child_window(
                            tag=f"fpg_slot_{n}",
                            width=self._FPG_SLOT_W, height=self._FPG_SLOT_H,
                            border=True, no_scrollbar=True, no_scroll_with_mouse=True):

                        # row 1 — fdr id + priority badge + output mode badge
                        with dpg.group(horizontal=True):
                            dpg.add_text(f"{n}", color=_C_DIM)
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

                        # rows 3-4 — cue list + fill-bar fader side by side
                        cuelist_w = max(32, self._FPG_SLOT_W - 22
                                         - self._FPG_FADER_W - 6)
                        with dpg.group(horizontal=True):
                            dpg.add_listbox(
                                tag=f"fpg_cuelist_{n}",
                                items=["—"],
                                num_items=n_items,
                                width=cuelist_w,
                                callback=self._on_fpg_cuelist_click,
                                user_data=n)
                            # Fill-bar fader: a drawn track+fill
                            # (fpg_faderbg_/fpg_faderfill_) with the real
                            # interactive slider overlaid at the same
                            # position via pos=(0, 0) — the slider is a
                            # fully transparent hit target (see
                            # _make_fpg_fader_theme) so DPG's native "tap
                            # anywhere on the track, then drag" slider
                            # behavior still works on a touch monitor, it
                            # just doesn't paint its own frame over the
                            # drawn fill. Isolated in its own fixed-size
                            # child_window so this pos= overlay can't
                            # disturb the rest of the slot's normal
                            # top-to-bottom layout flow.
                            with dpg.child_window(
                                    tag=f"fpg_fadercell_{n}",
                                    width=self._FPG_FADER_W, height=fader_h,
                                    border=False, no_scrollbar=True,
                                    no_scroll_with_mouse=True):
                                with dpg.drawlist(tag=f"fpg_faderbg_{n}",
                                                  width=self._FPG_FADER_W,
                                                  height=fader_h):
                                    dpg.draw_rectangle(
                                        pmin=(0, 0),
                                        pmax=(self._FPG_FADER_W, fader_h),
                                        tag=f"fpg_fadertrack_{n}",
                                        fill=_C_PANEL, color=_C_BORDER,
                                        thickness=1, rounding=4)
                                    dpg.draw_rectangle(
                                        pmin=(0, 0),
                                        pmax=(self._FPG_FADER_W, fader_h),
                                        tag=f"fpg_faderfill_{n}",
                                        fill=_C_ACCENT, color=(0, 0, 0, 0),
                                        rounding=4)
                                dpg.add_slider_int(
                                    tag=f"fpg_fader_{n}",
                                    vertical=True,
                                    pos=(0, 0),
                                    width=self._FPG_FADER_W, height=fader_h,
                                    min_value=0, max_value=255,
                                    default_value=255, format="",
                                    no_input=True,
                                    callback=self._on_fpg_fader, user_data=n)
                                dpg.bind_item_theme(f"fpg_fader_{n}",
                                                    self._fpg_fader_theme)

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
                        self._fpg_set_fader_fill(n, 1.0,
                                                  self._FPG_FADER_W, fader_h)
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
        fader_h     = max(80,  slot_h - self._FPG_FIXED_ROWS_H)
        fader_w     = self._FPG_FADER_W   # touch-target width — not reflowed
        btn_w       = max(36,  slot_w - 12)
        badge_w     = max(24,  (slot_w - 20) // 2 - 2)
        cuelist_w   = max(32,  slot_w - 22 - fader_w - 6)
        n_items     = max(3,   fader_h // 21)
        self._fpg_fader_dims = (fader_w, fader_h)

        for n in range(1, self._FPG_SLOTS + 1):
            try:
                dpg.configure_item(f"fpg_slot_{n}",      width=slot_w,    height=slot_h)
                dpg.configure_item(f"fpg_fadercell_{n}", height=fader_h)
                dpg.configure_item(f"fpg_faderbg_{n}",   height=fader_h)
                dpg.configure_item(f"fpg_fadertrack_{n}", pmin=(0, 0),
                                   pmax=(fader_w, fader_h))
                dpg.configure_item(f"fpg_fader_{n}",     height=fader_h)
                dpg.configure_item(f"fpg_cuelist_{n}",   width=cuelist_w,
                                   num_items=n_items)
                dpg.configure_item(f"fpg_pri_{n}",       width=badge_w)
                dpg.configure_item(f"fpg_out_{n}",       width=badge_w)
                for _s in ('a', 'b', 'c'):
                    dpg.configure_item(f"fpg_btn{_s}_{n}", width=btn_w)
                dpg.configure_item(f"fpg_trig_{n}", width=btn_w)
                # Re-draw the fill at its current level for the new size —
                # width/height changed underneath it, so the old pmax is stale.
                _lvl = dpg.get_value(f"fpg_fader_{n}") / 255.0
                self._fpg_set_fader_fill(n, _lvl, fader_w, fader_h)
            except Exception:
                pass
    def _fpg_set_fader_fill(self, n, level, fader_w=None, fader_h=None):
        """Redraw fader-page slot n's fill rectangle to reflect level
        (0.0-1.0), bottom-anchored like a real mixer fader. Called on every
        level change (drag, tick sync, reflow) — see fpg_faderfill_* in
        _build_fader_page_popup for the drawn track/fill this updates.
        Defaults to self._fpg_fader_dims (kept current by _fpg_reflow)
        rather than querying dpg.get_item_rect_size — a rect-size query
        only reflects reality after an actual render frame, so it can
        read (0, 0) right after a drag if no frame has landed yet."""
        try:
            if fader_w is None or fader_h is None:
                fader_w, fader_h = self._fpg_fader_dims
            if fader_w <= 0 or fader_h <= 0:
                return
            level = max(0.0, min(1.0, float(level)))
            fill_top = fader_h * (1.0 - level)
            dpg.configure_item(f"fpg_faderfill_{n}",
                               pmin=(0, fill_top), pmax=(fader_w, fader_h))
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
                self._fpg_set_fader_fill(n, lvl)
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
                self._fpg_set_fader_fill(n, ex.level)
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
    def _on_fpg_cuelist_click(self, _sender, value, user_data):
        """GOTO the cue the user clicked in the fader page cue list."""
        if not value or value.strip() in ("—", ""):
            return
        n   = int(user_data)
        eid = self._fpg_exec_for_slot(self._fpg_page, n)
        try:
            cue_num = float(value.strip().lstrip("▶").strip().split()[0])
            if self._cmd:
                self._cmd(f"GOTO {eid} {cue_num}")
        except (ValueError, IndexError):
            pass
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

                # ── cue list ─────────────────────────────────
                if ex and ex.stack:
                    _cs   = ex.stack
                    _cur  = _cs.current
                    _items, _sel = [], None
                    for _cn in sorted(_cs.cues.keys()):
                        _c   = _cs.cues[_cn]
                        _lbl = f"{'▶' if _cn == _cur else ' '}{_cn:.0f} {_c.name}"
                        _items.append(_lbl)
                        if _cn == _cur:
                            _sel = _lbl
                    dpg.configure_item(f"fpg_cuelist_{n}",
                                       items=_items if _items else ["—"])
                    if _sel:
                        dpg.set_value(f"fpg_cuelist_{n}", _sel)
                else:
                    dpg.configure_item(f"fpg_cuelist_{n}", items=["—"])

                # ── fader (sync when not dragging) ───────────
                _lvl01 = ex.level if ex else 1.0
                if not dpg.is_item_active(f"fpg_fader_{n}"):
                    dpg.set_value(f"fpg_fader_{n}", round(_lvl01 * 255))
                    self._fpg_set_fader_fill(n, _lvl01)
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

                # ── active slot highlight ─────────────────────
                is_live = bool(ex and ex.is_active and ex.stack)
                if is_live and self._active_slot_theme:
                    dpg.bind_item_theme(f"fpg_slot_{n}", self._active_slot_theme)

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
            for num in stack._sorted_cue_numbers():
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
                    dpg.add_text(ft, color=_C_DIM)
    def _playbacks_state_hash(self):
        """Compact snapshot of running fader state — used to detect changes."""
        if not self._fader_pool:
            return ()
        return tuple(
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

        active = []
        if self._fader_pool:
            running_eids = {eid for eid, ex in self._fader_pool.faders.items()
                            if ex.is_active and ex.stack}
            ordered = [eid for eid in reversed(self._fader_pool._fire_order)
                       if eid in running_eids]
            ordered += sorted(running_eids - set(ordered))
            for eid in ordered:
                active.append(self._fader_pool.faders[eid])

        if not active:
            dpg.add_text("— none running", tag="playbacks_empty",
                         color=_C_DIM, parent="playbacks_list")
            return

        # Reserve room for the trailing fixed-width buttons (time/priority/a/b/c
        # + inter-item spacing) so the two variable-length labels below never
        # push them past the edge of the (fixed-width) left column — see
        # _fit_text. 260px measured empirically (pixel-verified via a headless
        # DearPyGui render against the widest real row) with margin to spare
        # for the rarer 52px time-override badge.
        try:
            _row_w = dpg.get_item_rect_size("playbacks_list")[0] or 349
        except Exception:
            _row_w = 349
        _label_budget = max(60, _row_w - 260)
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
            _full_name = f"[{ex.fdr_id}] {stk.name}{_mode_tag}{_trig_tag}"
            _fit_name  = self._fit_text(_full_name, _name_w)
            _fit_cue   = self._fit_text(cue_label, _cue_w)
            if i > 0:
                dpg.add_separator(parent="playbacks_list")
            with dpg.group(horizontal=True, parent="playbacks_list"):
                _name_tag = f"pb_name_{ex.fdr_id}"
                _cue_tag  = f"pb_cue_{ex.fdr_id}"
                dpg.add_text(_fit_name, tag=_name_tag, color=_C_TEXT)
                if _fit_name != _full_name:
                    with dpg.tooltip(_name_tag):
                        dpg.add_text(_full_name)
                dpg.add_text(_fit_cue, tag=_cue_tag, color=_C_ACCENT)
                if _fit_cue != cue_label:
                    with dpg.tooltip(_cue_tag):
                        dpg.add_text(cue_label)
                # Time override badge
                if ex.time_override_on and ex.time_override_fade is not None:
                    t_label  = f"t{ex.time_override_fade:.1f}s"
                    dpg.add_button(label=t_label, width=52, height=20,
                                   callback=self._on_exec_time_toggle,
                                   user_data=ex.fdr_id)
                    dpg.configure_item(dpg.last_item(), enabled=stk.allow_exec_time)
                    if not stk.allow_exec_time:
                        dpg.add_text("🔒", color=_C_DIM)
                else:
                    dpg.add_button(label="time", width=44, height=20,
                                   callback=self._on_exec_time_toggle,
                                   user_data=ex.fdr_id)
                dpg.add_button(label=pri_label, width=40, height=20,
                               callback=self._on_priority_cycle,
                               user_data=ex.fdr_id)
                for _slot, _fn in (('a', ex.btn_a), ('b', ex.btn_b), ('c', ex.btn_c)):
                    _tag = f"ebtn_{_slot}_{ex.fdr_id}"
                    dpg.add_button(label=_fn.lower(), tag=_tag,
                                   width=40, height=20,
                                   callback=self._on_exec_slot_btn,
                                   user_data=(ex.fdr_id, _slot))
            # fader level row
            dpg.add_slider_int(
                tag=f"exec_fader_{ex.fdr_id}",
                default_value=int(ex.level * 255),
                min_value=0, max_value=255,
                width=-1, height=16,
                format="%d",
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
                ex.level = max(0.0, min(1.0, float(value) / 255.0))
                _exec_fader_mode_hook(ex)
