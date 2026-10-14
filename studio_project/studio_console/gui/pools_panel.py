"""GUIEngine's preset pools: groups, colors, dims, stacks, cues, FX pool, attribute pools, forms, codes, plus the global FX rate/size/spread knobs.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

import time

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.engine.fx import FormPool


class GUIEnginePoolsPanel:
    def _on_attr_popup_toggle(self):
        try:
            if dpg.is_item_shown("attr_window"):
                dpg.hide_item("attr_window")
            else:
                dpg.show_item("attr_window")
            self._save_popup_layout()
        except Exception:
            pass
    def _build_pools_row(self):
        # Panels touch each other — no spacers, borders serve as dividers.
        dpg.add_separator()
        # Row 1: Groups | Colors | Dims
        with dpg.group(horizontal=True):
            self._build_group_panel()
            self._build_color_panel()
            self._build_dim_panel()
        # Row 2: Stacks | Cues | FX Pool
        with dpg.group(horizontal=True):
            self._build_stack_panel()
            self._build_cue_panel()
            self._build_fx_pool_panel()
        # Row 3: Forms (full width)
        self._build_forms_panel()
    def _build_group_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_groups", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text("› groups", color=_C_P_GROUPS)
                dpg.add_spacer(width=10)
                self._build_page_ctrl("groups", self._POOL_SLOTS, _C_P_GROUPS)
                dpg.add_spacer(width=16)
                # Global link/unlink toggle lives here (not its own row) —
                # this main window already runs a tight, no-scrollbar
                # vertical budget (see _build_forms_panel's own comment on
                # that), and there's clean horizontal room left in this
                # specific header line. Second copy in the attribute pools
                # popup, since attribute pools live in a different window —
                # both drive the same state (_on_pool_pages_link_toggle).
                self._build_pages_link_ctrl("pool_pages_link_main")
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"grp_btn_{n}", label=f"g{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_group_click, user_data=n)
                        with dpg.tooltip(f"grp_btn_{n}"):
                            dpg.add_text(f"group {n}", tag=f"grp_tip_{n}")
                        with dpg.popup(f"grp_btn_{n}", mousebutton=1):
                            dpg.add_text("group", tag=f"grp_ctxlbl_{n}", color=_C_P_GROUPS)
                            dpg.add_separator()
                            dpg.add_menu_item(label="record group here",
                                callback=self._ctx_prefill_paged,
                                user_data=("groups", self._POOL_SLOTS, n, "RECORD GROUP {n} "))
                            dpg.add_menu_item(label="recall group",
                                callback=self._ctx_exec_paged,
                                user_data=("groups", self._POOL_SLOTS, n, "GROUP {n}"))
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill_paged,
                                user_data=("groups", self._POOL_SLOTS, n, "RENAME GROUP {n} "))
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill_paged,
                                user_data=("groups", self._POOL_SLOTS, n, "COPY GROUP {n} TO "))
                            dpg.add_separator()
                            dpg.add_menu_item(label="clear group",
                                callback=self._ctx_exec_paged,
                                user_data=("groups", self._POOL_SLOTS, n, "CLEAR GROUP {n}"))
    def _build_color_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_colors", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text("› color presets", color=_C_P_COLORS)
                dpg.add_spacer(width=10)
                self._build_page_ctrl("colors", self._POOL_SLOTS, _C_P_COLORS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"col_btn_{n}", label=f"c{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_color_click, user_data=n)
                        with dpg.tooltip(f"col_btn_{n}"):
                            dpg.add_text(f"color {n}", tag=f"col_tip_{n}")
                        with dpg.popup(f"col_btn_{n}", mousebutton=1):
                            dpg.add_text("color", tag=f"col_ctxlbl_{n}", color=_C_P_COLORS)
                            dpg.add_separator()
                            dpg.add_menu_item(label="record color here",
                                callback=self._ctx_prefill_paged,
                                user_data=("colors", self._POOL_SLOTS, n, "RECORD COLOR {n} "))
                            dpg.add_menu_item(label="apply color",
                                callback=self._ctx_exec_paged,
                                user_data=("colors", self._POOL_SLOTS, n, "COLOR {n}"))
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill_paged,
                                user_data=("colors", self._POOL_SLOTS, n, "RENAME COLOR {n} "))
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill_paged,
                                user_data=("colors", self._POOL_SLOTS, n, "COPY COLOR {n} TO "))
                            dpg.add_separator()
                            dpg.add_menu_item(label="clear color",
                                callback=self._ctx_exec_paged,
                                user_data=("colors", self._POOL_SLOTS, n, "CLEAR COLOR {n}"))
    def _build_dim_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_dims", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text("› dim presets", color=_C_P_DIMS)
                dpg.add_spacer(width=10)
                self._build_page_ctrl("dims", self._POOL_SLOTS, _C_P_DIMS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"dim_btn_{n}", label=f"d{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_dim_click, user_data=n)
                        with dpg.tooltip(f"dim_btn_{n}"):
                            dpg.add_text(f"dim {n}", tag=f"dim_tip_{n}")
                        with dpg.popup(f"dim_btn_{n}", mousebutton=1):
                            dpg.add_text("dim", tag=f"dim_ctxlbl_{n}", color=_C_P_DIMS)
                            dpg.add_separator()
                            dpg.add_menu_item(label="record dim here",
                                callback=self._ctx_prefill_paged,
                                user_data=("dims", self._POOL_SLOTS, n, "RECORD DIM {n} "))
                            dpg.add_menu_item(label="apply dim",
                                callback=self._ctx_exec_paged,
                                user_data=("dims", self._POOL_SLOTS, n, "DIM {n}"))
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill_paged,
                                user_data=("dims", self._POOL_SLOTS, n, "RENAME DIM {n} "))
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill_paged,
                                user_data=("dims", self._POOL_SLOTS, n, "COPY DIM {n} TO "))
                            dpg.add_separator()
                            dpg.add_menu_item(label="clear dim",
                                callback=self._ctx_exec_paged,
                                user_data=("dims", self._POOL_SLOTS, n, "CLEAR DIM {n}"))
    def _focus_cmd(self):
        pass  # key routing via global handlers; no focus transfer needed
    def _ctx_exec(self, _s, _a, cmd):
        """Execute cmd immediately and log result."""
        if not self._cmd:
            return
        result = self._cmd(cmd)
        self._log(f"> {cmd}")
        if result:
            for line in str(result).splitlines():
                self._log(f"  {line}")
    def _ctx_prefill(self, _s, _a, text):
        """Pre-fill command line and focus it."""
        try:
            dpg.set_value("cmd_input", text)
        except Exception:
            pass

    # ── Pool pagination ──────────────────────────────────────────
    # See GUIEngineCore.__init__'s comment for the linked/unlinked design.
    # Every paginated panel (groups/colors/dims/stacks/cues/fx pool/forms/
    # codes/6 attribute pools) is built with a small, fixed grid of
    # buttons (its "page size" — e.g. 24 for groups, 12 for an attribute
    # pool) whose TAGS stay tied to grid position 1..page_size forever.
    # Paging never rebuilds or retags anything: it only changes what
    # ACTUAL pool slot number each grid position maps to, and the existing
    # per-tick label/tooltip refresh (_tick_pools) already re-reads that
    # mapping every ~50ms, so a page change is visible within one tick.
    # Click handlers and context-menu commands route through
    # _pool_page_offset()/the _paged wrappers below so they always act on
    # the REAL slot number, not the 1..page_size grid position.
    def _pool_pages_linked(self):
        try:
            return bool(dpg.get_value("pool_pages_link_main"))
        except Exception:
            return True
    def _pool_page_start(self, key):
        if self._pool_pages_linked():
            return self._linked_page_start
        return self._pool_page_starts.get(key, 1)
    def _pool_page_set_start(self, key, start):
        start = max(1, int(start))
        if self._pool_pages_linked():
            self._linked_page_start = start
        else:
            self._pool_page_starts[key] = start
    def _pool_page_offset(self, key):
        """0-based offset to add to a 1..page_size grid position to get
        the real pool slot number."""
        return self._pool_page_start(key) - 1
    def _on_pool_page_prev(self, _sender, _app_data, user_data):
        key, page_size = user_data
        self._pool_page_set_start(key, self._pool_page_start(key) - page_size)
    def _on_pool_page_next(self, _sender, _app_data, user_data):
        key, page_size = user_data
        self._pool_page_set_start(key, self._pool_page_start(key) + page_size)
    def _on_pool_pages_link_toggle(self, sender, value):
        # Two checkboxes (main window + attribute pools window) drive one
        # shared concept — keep whichever one the operator DIDN'T click in
        # sync immediately rather than waiting for a tick.
        other = "pool_pages_link_attr" if sender == "pool_pages_link_main" else "pool_pages_link_main"
        try:
            dpg.set_value(other, value)
        except Exception:
            pass
        if value:
            # Turning linking back ON: adopt whichever panel's own start
            # was furthest from 1 as the new shared start, so re-linking
            # doesn't silently snap everything back to page 1 and lose
            # whichever slot range the operator was actually looking at.
            self._linked_page_start = max(self._pool_page_starts.values(), default=1)
        else:
            # Turning linking OFF: seed every pool's own independent start
            # with whatever the shared start currently is, so unlinking
            # doesn't visually snap every panel but one back to page 1 —
            # each just keeps showing what it already was, free to move
            # independently from here on.
            for _key, _ in self._PAGED_POOLS:
                self._pool_page_starts[_key] = self._linked_page_start
    def _build_page_ctrl(self, key, page_size, color):
        """Small ◀ range ▶ control — placed beside a pool panel's title.
        Shows the real slot range currently visible (e.g. "25-48"), not a
        page number: once panels page independently (unlinked) or by
        different step sizes while linked, "page 3" stops meaning the same
        thing across every pool, but the actual slot range is always
        unambiguous."""
        with dpg.group(horizontal=True):
            dpg.add_button(label="<", width=18, height=18,
                callback=self._on_pool_page_prev, user_data=(key, page_size))
            dpg.add_text(f"1-{page_size}", tag=f"pg_{key}_lbl", color=color)
            dpg.add_button(label=">", width=18, height=18,
                callback=self._on_pool_page_next, user_data=(key, page_size))
    def _build_pages_link_ctrl(self, tag):
        """Global link/unlink toggle — one instance in the main pools row,
        one in the attribute pools popup (they live in different windows),
        both driving the same underlying state (see
        _on_pool_pages_link_toggle)."""
        with dpg.group(horizontal=True):
            dpg.add_text("pool pages:", color=_C_DIM)
            dpg.add_checkbox(label="linked", tag=tag, default_value=True,
                callback=self._on_pool_pages_link_toggle)
    def _ctx_exec_paged(self, _s, _a, user_data):
        """Like _ctx_exec, but user_data is (pool_key, page_size, grid_n,
        template) — the command template's "{n}" is filled in with the
        REAL slot number at click time, not baked in at build time, so it
        stays correct no matter what page the panel is currently on."""
        key, page_size, grid_n, template = user_data
        actual_n = self._pool_page_offset(key) + grid_n
        self._ctx_exec(_s, _a, template.format(n=actual_n))
    def _ctx_prefill_paged(self, _s, _a, user_data):
        """Prefill counterpart of _ctx_exec_paged — same (pool_key,
        page_size, grid_n, template) user_data shape."""
        key, page_size, grid_n, template = user_data
        actual_n = self._pool_page_offset(key) + grid_n
        self._ctx_prefill(_s, _a, template.format(n=actual_n))
    def _tick_pool_page_labels(self):
        """Refresh every page-range label + prev/next enabled state — one
        line per pool key, called once per tick from _tick_pools()."""
        for key, page_size in self._PAGED_POOLS:
            start = self._pool_page_start(key)
            try:
                dpg.set_value(f"pg_{key}_lbl", f"{start}-{start + page_size - 1}")
            except Exception:
                pass
        try:
            linked = self._pool_pages_linked()
            dpg.set_value("pool_pages_link_main", linked)
            dpg.set_value("pool_pages_link_attr", linked)
        except Exception:
            pass
    def _on_group_click(self, _sender, _app_data, user_data):
        n = self._pool_page_offset("groups") + user_data
        if self._groups and self._groups.get(n):
            # This button bypasses run_command()/commands/presets.py entirely
            # (calls GroupPool.recall() directly) — the undo push added there
            # for typed "GROUP n" never covered this, the actual click path.
            if self._prog:
                self._prog._push_undo()
            self._groups.recall(n, self._prog)
            self._log(f"> GROUP {n}  recalled — {self._groups.get(n).name}")
        else:
            self._log(f"> GROUP {n} is empty — select fixtures, then name the group:")
            try:
                dpg.set_value("cmd_input", f"RECORD GROUP {n} ")
            except Exception:
                pass
        self._focus_cmd()
    def _on_color_click(self, _sender, _app_data, user_data):
        n = self._pool_page_offset("colors") + user_data
        if self._colors and self._colors.get(n):
            p = self._colors.get(n)
            # Same bypass as _on_group_click — direct ColorPreset.apply()
            # call, not routed through run_command()'s "COLOR n" branch.
            if self._prog:
                self._prog._push_undo()
            p.apply(self._prog)
            self._log(f"> COLOR {n}  applied — {p.name}")
        else:
            self._log(f"> COLOR {n} is empty — set colour in programmer, then name it:")
            try:
                dpg.set_value("cmd_input", f"RECORD COLOR {n} ")
            except Exception:
                pass
        self._focus_cmd()
    def _on_dim_click(self, _sender, _app_data, user_data):
        n = self._pool_page_offset("dims") + user_data
        if self._dims and self._dims.get(n):
            p = self._dims.get(n)
            # Same bypass as _on_group_click — direct DimmerPreset.apply()
            # call, not routed through run_command()'s "DIM PRESET n" branch.
            if self._prog:
                self._prog._push_undo()
            p.apply(self._prog)
            self._log(f"> DIM PRESET {n}  applied — {p.name}")
        else:
            self._log(f"> DIM PRESET {n} is empty — set dim in programmer, then name it:")
            try:
                dpg.set_value("cmd_input", f"RECORD DIM {n} ")
            except Exception:
                pass
        self._focus_cmd()
    def _build_stack_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_stacks", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text("› stacks", color=_C_P_CS)
                dpg.add_spacer(width=10)
                self._build_page_ctrl("stacks", self._POOL_SLOTS, _C_P_CS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"cs_btn_{n}", label=f"stk{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_stack_click, user_data=n)
                        with dpg.tooltip(f"cs_btn_{n}"):
                            dpg.add_text(f"stack {n}", tag=f"cs_tip_{n}")
                        with dpg.popup(f"cs_btn_{n}", mousebutton=1):
                            dpg.add_text("stack", tag=f"cs_ctxlbl_{n}", color=_C_P_CS)
                            dpg.add_separator()
                            dpg.add_menu_item(label="select / activate",
                                callback=self._on_stack_click,
                                user_data=n)
                            dpg.add_menu_item(label="create / rename...",
                                callback=self._ctx_prefill_paged,
                                user_data=("stacks", self._POOL_SLOTS, n, "RECORD STACK {n} "))
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill_paged,
                                user_data=("stacks", self._POOL_SLOTS, n, "RENAME STACK {n} "))
                            dpg.add_menu_item(label="assign to fader...",
                                callback=self._ctx_prefill_paged,
                                user_data=("stacks", self._POOL_SLOTS, n, "ASSIGN stk {n} TO FADER "))
                            dpg.add_separator()
                            dpg.add_menu_item(label="delete stack",
                                callback=self._ctx_exec_paged,
                                user_data=("stacks", self._POOL_SLOTS, n, "delete stack {n}"))
    def _build_cue_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_cues", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text("› cues", color=_C_P_CUES)
                dpg.add_spacer(width=10)
                self._build_page_ctrl("cues", self._POOL_SLOTS, _C_P_CUES)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"cue_btn_{n}", label=f"{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_cue_click, user_data=n)
                        with dpg.tooltip(f"cue_btn_{n}"):
                            dpg.add_text(f"cue {n}", tag=f"cue_tip_{n}")
                        with dpg.popup(f"cue_btn_{n}", mousebutton=1):
                            dpg.add_text("cue", tag=f"cue_ctxlbl_{n}", color=_C_P_CUES)
                            dpg.add_separator()
                            dpg.add_menu_item(label="go to cue",
                                callback=self._on_cue_click,
                                user_data=n)
                            dpg.add_menu_item(label="record cue here",
                                callback=self._ctx_prefill_paged,
                                user_data=("cues", self._POOL_SLOTS, n, "RECORD CUE {n} "))
                            dpg.add_menu_item(label="update cue",
                                callback=self._ctx_exec_paged,
                                user_data=("cues", self._POOL_SLOTS, n, "UPDATE CUE {n}"))
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill_paged,
                                user_data=("cues", self._POOL_SLOTS, n, "RENAME CUE {n} "))
                            dpg.add_separator()
                            dpg.add_menu_item(label="delete cue",
                                callback=self._ctx_exec_paged,
                                user_data=("cues", self._POOL_SLOTS, n, "delete cue {n}"))
    def _on_stack_click(self, _sender, _app_data, user_data):
        n = self._pool_page_offset("stacks") + user_data
        if self._stack_pool and self._stack_pool.get(n):
            if self._active_fader is not None:
                self._active_fader[0] = n
            stk = self._stack_pool.get(n)
            self._log(f"> STACK {n}  selected — {stk.name}")
        else:
            self._log(f"> STACK {n} is empty — name it to create:")
            try:
                dpg.set_value("cmd_input", f"RECORD STACK {n} ")
            except Exception:
                pass
        self._focus_cmd()
    def _on_cue_click(self, _sender, _app_data, user_data):
        n = self._pool_page_offset("cues") + user_data
        if self._cue_pool and self._cue_pool.get(n):
            cue = self._cue_pool.get(n)
            if self._goto:
                self._goto(float(n))
            self._log(f"> CUE {n} — {cue.name}")
        else:
            self._log(f"> CUE {n} is empty")
        self._focus_cmd()
    def _build_fx_pool_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_fx", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            # Header: title + live summary + CLEAR FX all on one line
            with dpg.group(horizontal=True):
                dpg.add_text("› fx pool", color=_C_P_FX)
                dpg.add_spacer(width=10)
                self._build_page_ctrl("fx", self._POOL_SLOTS, _C_P_FX)
                dpg.add_spacer(width=6)
                dpg.add_text("—", tag="fx_prog_summary", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_text("", tag="fx_prog_other", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_button(label="clr fx", width=60, height=18,
                               callback=self._on_clear_fx)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"fx_btn_{n}", label=f"fx{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_fx_click, user_data=n)
                        with dpg.tooltip(f"fx_btn_{n}"):
                            dpg.add_text(f"fx {n}", tag=f"fx_tip_{n}")
                        with dpg.popup(f"fx_btn_{n}", mousebutton=1):
                            dpg.add_text("fx preset", tag=f"fx_ctxlbl_{n}", color=_C_P_FX)
                            dpg.add_separator()
                            dpg.add_menu_item(label="fire fx",
                                callback=self._ctx_exec_paged,
                                user_data=("fx", self._POOL_SLOTS, n, "FIRE FX {n}"))
                            dpg.add_menu_item(label="record fx here",
                                callback=self._ctx_prefill_paged,
                                user_data=("fx", self._POOL_SLOTS, n, "RECORD FX {n} "))
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill_paged,
                                user_data=("fx", self._POOL_SLOTS, n, "RENAME FX {n} "))
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill_paged,
                                user_data=("fx", self._POOL_SLOTS, n, "COPY FX {n} TO "))
                            dpg.add_separator()
                            dpg.add_menu_item(label="clear fx preset",
                                callback=self._ctx_exec_paged,
                                user_data=("fx", self._POOL_SLOTS, n, "CLEAR FX {n}"))
    def _build_attr_pool_panel(self, attr_name, color, tag_prefix, slot_count=12):
        """Compact 2-row attribute pool panel (12 slots = 2 rows × 6 cols)."""
        _COLS = self._POOL_COLS
        _ROWS = slot_count // _COLS
        # Header allowance bumped from 26 to 40: the plain single-line
        # title text this was originally sized for (a pixel-exact fit,
        # zero slack) became a title + ‹prev/range/next› page control
        # sharing one horizontal group once paging was added, which
        # measures a few px taller — with the old allowance that clipped
        # the panel's own second button row against its bottom border
        # (reported, with a screenshot: p7-p12/g7-g12/etc rendering but
        # cut off mid-button).
        _H    = 40 + _ROWS * (self._BTN_H + 4)   # header + rows
        with dpg.child_window(tag=f"pool_{tag_prefix}", width=self._PANEL_W,
                              height=_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text(attr_name, color=color)
                dpg.add_spacer(width=10)
                self._build_page_ctrl(attr_name, slot_count, color)
            dpg.add_separator()
            for row in range(_ROWS):
                with dpg.group(horizontal=True):
                    for col in range(_COLS):
                        n = row * _COLS + col + 1
                        dpg.add_button(
                            tag=f"{tag_prefix}_btn_{n}",
                            label=f"{attr_name[0]}{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_attr_click,
                            user_data=(attr_name, n))
                        with dpg.tooltip(f"{tag_prefix}_btn_{n}"):
                            dpg.add_text(f"{attr_name} {n}",
                                         tag=f"{tag_prefix}_tip_{n}")
                        with dpg.popup(f"{tag_prefix}_btn_{n}", mousebutton=1):
                            dpg.add_text(attr_name, tag=f"{tag_prefix}_ctxlbl_{n}", color=color)
                            dpg.add_separator()
                            dpg.add_menu_item(label=f"record {attr_name} here",
                                callback=self._ctx_prefill_paged,
                                user_data=(attr_name, slot_count, n,
                                           f"RECORD {attr_name.upper()} " + "{n} "))
                            dpg.add_menu_item(label=f"apply {attr_name}",
                                callback=self._ctx_exec_paged,
                                user_data=(attr_name, slot_count, n,
                                           f"{attr_name.upper()} " + "{n}"))
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill_paged,
                                user_data=(attr_name, slot_count, n,
                                           f"RENAME {attr_name.upper()} " + "{n} "))
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill_paged,
                                user_data=(attr_name, slot_count, n,
                                           f"COPY {attr_name.upper()} " + "{n} TO "))
                            dpg.add_separator()
                            dpg.add_menu_item(label=f"clear {attr_name}",
                                callback=self._ctx_exec_paged,
                                user_data=(attr_name, slot_count, n,
                                           f"CLEAR {attr_name.upper()} " + "{n}"))
    def _build_code_pool_panel(self):
        """Code pool — recorded command sequences (CODE RECORD/STOP/ABORT),
        played back by number. Bespoke rather than routed through
        _build_attr_pool_panel: code command syntax puts the verb before
        the slot number for record/rename (CODE RECORD n / CODE RENAME n)
        instead of after (RECORD POSITION n), and there's no COPY/CLEAR
        equivalent — a code is either recorded or DELETEd, not applied
        as a value and re-recorded over.

        Called "codes" rather than the more common "macros" specifically
        to avoid colliding with the real DMX "macro" channel some
        moving-light profiles carry (control_pool's channel list in
        state.py, AT MACRO <n> in models/fixtures.py) — same word, two
        completely unrelated things, which was confusing.

        24 slots at full attr_window width — code numbering isn't tied to
        a fixed per-attribute slot count the way position/gobo/etc are.
        """
        _COLS  = self._POOL_COLS
        _ROWS  = self._POOL_SLOTS // _COLS
        _PANEL_TOTAL = 3 * self._PANEL_W + 2 * 6   # matches attr_window's 1902 width
        _BTN_W_FULL  = (_PANEL_TOTAL - 2 - 16 - (_COLS - 1) * 6) // _COLS
        # 30 -> 44: same pixel-exact-fit problem _build_attr_pool_panel's
        # _H had — this header line grew from plain text to title + page
        # control + rec status + stop/abort buttons, and the old, exact
        # allowance clipped the panel's own last button row (m19-m24,
        # reported with a screenshot) against its bottom border.
        _H = 44 + _ROWS * (self._BTN_H + 4)
        with dpg.child_window(tag="pool_codes", width=_PANEL_TOTAL,
                              height=_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text("codes", color=_C_P_CODES)
                dpg.add_spacer(width=10)
                self._build_page_ctrl("codes", self._POOL_SLOTS, _C_P_CODES)
                dpg.add_spacer(width=12)
                dpg.add_text("not recording", tag="code_rec_status", color=_C_DIM)
                dpg.add_spacer(width=12)
                dpg.add_button(label="stop", width=50, height=20,
                    callback=lambda: self._ctx_exec(None, None, "CODE STOP"))
                dpg.add_button(label="abort", width=50, height=20,
                    callback=lambda: self._ctx_exec(None, None, "CODE ABORT"))
            dpg.add_separator()
            for row in range(_ROWS):
                with dpg.group(horizontal=True):
                    for col in range(_COLS):
                        n = row * _COLS + col + 1
                        dpg.add_button(
                            tag=f"code_btn_{n}", label=f"c{n}",
                            width=_BTN_W_FULL, height=self._BTN_H,
                            callback=self._on_code_click, user_data=n)
                        with dpg.tooltip(f"code_btn_{n}"):
                            dpg.add_text(f"code {n}", tag=f"code_tip_{n}")
                        with dpg.popup(f"code_btn_{n}", mousebutton=1):
                            dpg.add_text("code", tag=f"code_ctxlbl_{n}", color=_C_P_CODES)
                            dpg.add_separator()
                            dpg.add_menu_item(label="play code",
                                callback=self._ctx_exec_paged,
                                user_data=("codes", self._POOL_SLOTS, n, "CODE {n}"))
                            dpg.add_menu_item(label="record here",
                                callback=self._ctx_prefill_paged,
                                user_data=("codes", self._POOL_SLOTS, n, "CODE RECORD {n} "))
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill_paged,
                                user_data=("codes", self._POOL_SLOTS, n, "CODE RENAME {n} "))
                            dpg.add_menu_item(label="edit code...",
                                callback=self._on_code_editor_open,
                                user_data=("codes", self._POOL_SLOTS, n))
                            dpg.add_separator()
                            dpg.add_menu_item(label="delete code",
                                callback=self._ctx_exec_paged,
                                user_data=("codes", self._POOL_SLOTS, n, "CODE DELETE {n}"))
    def _on_code_click(self, _sender, _app_data, user_data):
        n = self._pool_page_offset("codes") + user_data
        m = self._codes.get(n) if self._codes else None
        if m:
            if self._cmd:
                result = self._cmd(f"CODE {n}")
                if result:
                    for line in str(result).splitlines():
                        self._log(f"  {line}")
            self._log(f"> CODE {n} — {m['name']}")
        else:
            self._log(f"> CODE {n} is empty")
            self._log(f"  To record: run commands, then CODE STOP to save")
            try:
                dpg.set_value("cmd_input", f"CODE RECORD {n} ")
            except Exception:
                pass
        self._focus_cmd()

    # ── Code editor popup ────────────────────────────────────────
    # Live CODE RECORD/STOP captures commands as you actually run them,
    # one at a time — there was no way to add a DELAY step (or fix a typo,
    # or reorder a line) without discarding the whole recording and
    # starting over. This is a direct multi-line editor over a code's
    # command list instead: one command per line, blank lines ignored,
    # a "DELAY <ms>" line pauses playback for that long before the next
    # line WITHOUT blocking the console (see commands/code.py's
    # _run_code_from) — millisecond-precision timed steps, not a redo of
    # the live-record workflow.
    def _build_code_editor_popup(self):
        with dpg.window(tag="code_editor_window", label="code editor",
                        width=640, height=520, show=False, pos=(300, 140),
                        no_collapse=False):
            with dpg.group(horizontal=True):
                dpg.add_text("code", color=_C_P_CODES)
                dpg.add_text("", tag="code_ed_slot_lbl", color=_C_DIM)
            dpg.add_input_text(tag="code_ed_name", label="name", width=360)
            dpg.add_separator()
            dpg.add_text("one command per line, in play order. add a line "
                         "\"DELAY <ms>\" to pause that long before the next "
                         "line — e.g. DELAY 250 waits a quarter second. "
                         "playback never blocks the console, delayed or not.",
                         color=_C_DIM, wrap=610)
            dpg.add_input_text(tag="code_ed_body", multiline=True, width=-1, height=340,
                               tab_input=True)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="save", width=80, callback=self._on_code_editor_save)
                dpg.add_button(label="save + play", width=100, callback=self._on_code_editor_save_play)
                dpg.add_button(label="close", width=80,
                               callback=lambda: dpg.hide_item("code_editor_window"))
                dpg.add_text("", tag="code_ed_status", color=_C_ACCENT)
    def _on_code_editor_open(self, _sender, _app_data, user_data):
        key, page_size, grid_n = user_data
        slot = self._pool_page_offset(key) + grid_n
        self._code_editor_slot = slot
        m = self._codes.get(slot) if self._codes else None
        try:
            dpg.set_value("code_ed_slot_lbl", f"slot {slot}")
            dpg.set_value("code_ed_name", m['name'] if m else f"code {slot}")
            dpg.set_value("code_ed_body", "\n".join(m['commands']) if m else "")
            dpg.set_value("code_ed_status", "")
            dpg.configure_item("code_editor_window", label=f"code editor — slot {slot}")
            dpg.show_item("code_editor_window")
        except Exception:
            pass
    def _code_editor_commit(self):
        """Write the editor's current text into self._codes and persist —
        shared by both Save and Save+Play. Returns the (slot, line count)
        on success, None if the editor isn't actually open on a slot."""
        slot = self._code_editor_slot
        if slot is None:
            return None
        name = (dpg.get_value("code_ed_name") or f"code {slot}").strip().lower()
        body = dpg.get_value("code_ed_body") or ""
        cmds = [ln.strip() for ln in body.splitlines() if ln.strip()]
        self._codes[slot] = {"name": name, "commands": cmds}
        try:
            from studio_console.show import ShowFile
            ShowFile.save_codes(self._codes)
        except Exception:
            pass
        return slot, len(cmds)
    def _on_code_editor_save(self):
        result = self._code_editor_commit()
        if result:
            slot, n_cmds = result
            try:
                dpg.set_value("code_ed_status", f"saved — {n_cmds} line(s)")
            except Exception:
                pass
            self._log(f"> CODE {slot} edited — {n_cmds} line(s) saved")
    def _on_code_editor_save_play(self):
        result = self._code_editor_commit()
        if not result:
            return
        slot, n_cmds = result
        try:
            dpg.set_value("code_ed_status", f"saved — {n_cmds} line(s), playing")
        except Exception:
            pass
        if self._cmd:
            r = self._cmd(f"CODE {slot}")
            self._log(f"> CODE {slot} edited + played")
            if r:
                for line in str(r).splitlines():
                    self._log(f"  {line}")
    def _build_attr_popup(self):
        """Floating attribute pool panel — hidden by default, opened via header button."""
        with dpg.window(tag="attr_window", label="attribute pools",
                        width=1902, height=580, show=False,
                        pos=(10, 80), no_collapse=False):
            with dpg.group(horizontal=True):
                dpg.add_text("position / gobo / zoom / focus / beam / control", color=_C_ACCENT)
                dpg.add_spacer(width=16)
                # Same shared link/unlink state as the main window's copy —
                # a separate instance since attribute pools live in this
                # popup, not the main window (see _on_pool_pages_link_toggle).
                self._build_pages_link_ctrl("pool_pages_link_attr")
            dpg.add_text("moving-light attributes — not used by the 6 lt-200 pixel tubes "
                         "in this rig, but recalled the same way as color/dim presets "
                         "for any fixture patched with these channels.", color=_C_DIM, wrap=1860)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                self._build_attr_pool_panel("position", _C_P_POSITION, "pos")
                self._build_attr_pool_panel("gobo",     _C_P_GOBO,  "gobo")
                self._build_attr_pool_panel("zoom",     _C_P_ZOOM,  "zoom")
            with dpg.group(horizontal=True):
                self._build_attr_pool_panel("focus",    _C_P_FOCUS,    "focus")
                self._build_attr_pool_panel("beam",     _C_P_BEAM,     "beam")
                self._build_attr_pool_panel("control",  _C_P_CONTROL,  "ctrl")
            dpg.add_separator()
            dpg.add_text("codes — recorded command sequences, played back by number; "
                         "mappable to a MIDI note or OSC /gma3/cmd trigger the same way "
                         "GO/BACK/cue jumps are (hardware popup's MIDI learn panel).",
                         color=_C_DIM, wrap=1860)
            self._build_code_pool_panel()
    def _build_fx_params_popup(self):
        """Floating Rate/Size/spread pool panel — hidden by default, opened via
        the 'rsp pool' button next to the inline FX sliders. Moved out of the
        left column (was pushing left_col 224px past its 480px budget, the
        largest single contributor) — the sliders themselves (live values)
        and kill fx stay inline since those are used every cue; recall/record/
        rename of the 4-slot pools is used far less often and fits the same
        popup-for-pool pattern already used for attribute pools and speed
        masters."""
        _POOL_BTN = 90
        with dpg.window(tag="fx_params_window", label="rate / size / spread pools",
                        width=420, height=190, show=False,
                        pos=(600, 80), no_collapse=False):
            dpg.add_text("rate", color=_C_DIM)
            with dpg.group(horizontal=True):
                for n in range(1, 5):
                    dpg.add_button(tag=f"rate_btn_{n}", label=f"r{n}",
                                   width=_POOL_BTN, height=22,
                                   callback=self._on_rate_click, user_data=n)
                    with dpg.tooltip(f"rate_btn_{n}"):
                        dpg.add_text(f"rate {n}", tag=f"rate_tip_{n}")
                    with dpg.popup(f"rate_btn_{n}", mousebutton=1):
                        dpg.add_text(f"rate {n}", color=_C_DIM)
                        dpg.add_separator()
                        dpg.add_menu_item(label="recall rate",
                            callback=self._ctx_exec, user_data=f"RATE {n}")
                        dpg.add_menu_item(label="record rate here...",
                            callback=self._ctx_prefill,
                            user_data=f"RECORD RATE {n} ")
                        dpg.add_menu_item(label="rename...",
                            callback=self._ctx_prefill,
                            user_data=f"RENAME RATE {n} ")
                        dpg.add_menu_item(label="copy to slot...",
                            callback=self._ctx_prefill,
                            user_data=f"COPY RATE {n} TO ")
                        dpg.add_separator()
                        dpg.add_menu_item(label="delete rate",
                            callback=self._ctx_exec, user_data=f"DELETE RATE {n}")
            dpg.add_text("size", color=_C_DIM)
            with dpg.group(horizontal=True):
                for n in range(1, 5):
                    dpg.add_button(tag=f"size_btn_{n}", label=f"s{n}",
                                   width=_POOL_BTN, height=22,
                                   callback=self._on_size_click, user_data=n)
                    with dpg.tooltip(f"size_btn_{n}"):
                        dpg.add_text(f"size {n}", tag=f"size_tip_{n}")
                    with dpg.popup(f"size_btn_{n}", mousebutton=1):
                        dpg.add_text(f"size {n}", color=_C_DIM)
                        dpg.add_separator()
                        dpg.add_menu_item(label="recall size",
                            callback=self._ctx_exec, user_data=f"SIZEP {n}")
                        dpg.add_menu_item(label="record size here...",
                            callback=self._ctx_prefill,
                            user_data=f"RECORD SIZEP {n} ")
                        dpg.add_menu_item(label="rename...",
                            callback=self._ctx_prefill,
                            user_data=f"RENAME SIZEP {n} ")
                        dpg.add_menu_item(label="copy to slot...",
                            callback=self._ctx_prefill,
                            user_data=f"COPY SIZEP {n} TO ")
                        dpg.add_separator()
                        dpg.add_menu_item(label="delete size",
                            callback=self._ctx_exec, user_data=f"DELETE SIZEP {n}")
            dpg.add_text("spread", color=_C_DIM)
            with dpg.group(horizontal=True):
                for n in range(1, 5):
                    dpg.add_button(tag=f"spread_btn_{n}", label=f"sp{n}",
                                   width=_POOL_BTN, height=22,
                                   callback=self._on_spread_click, user_data=n)
                    with dpg.tooltip(f"spread_btn_{n}"):
                        dpg.add_text(f"spread {n}", tag=f"spread_tip_{n}")
                    with dpg.popup(f"spread_btn_{n}", mousebutton=1):
                        dpg.add_text(f"spread {n}", color=_C_DIM)
                        dpg.add_separator()
                        dpg.add_menu_item(label="recall spread",
                            callback=self._ctx_exec, user_data=f"SPREADP {n}")
                        dpg.add_menu_item(label="record spread here...",
                            callback=self._ctx_prefill,
                            user_data=f"RECORD SPREADP {n} ")
                        dpg.add_menu_item(label="rename...",
                            callback=self._ctx_prefill,
                            user_data=f"RENAME SPREADP {n} ")
                        dpg.add_menu_item(label="copy to slot...",
                            callback=self._ctx_prefill,
                            user_data=f"COPY SPREADP {n} TO ")
                        dpg.add_separator()
                        dpg.add_menu_item(label="delete spread",
                            callback=self._ctx_exec, user_data=f"DELETE SPREADP {n}")
    def _on_fx_params_toggle(self, *_):
        try:
            if dpg.is_item_shown("fx_params_window"):
                dpg.hide_item("fx_params_window")
            else:
                dpg.show_item("fx_params_window")
            self._save_popup_layout()
        except Exception:
            pass
    def _build_forms_panel(self):
        # Spans the same width as the 3 pool panels above INCLUDING the
        # inter-panel ItemSpacing gaps, so its right edge lines up with theirs:
        #   3×_PANEL_W  (panels)  +  2×ItemSpacing.X  (gaps)
        # Single row of 16 (was 2 rows of 12 = 24 slots) — halving the row
        # count is what actually buys back the vertical space; the 2-row
        # layout was the reason "main" needed a scrollbar fallback at all,
        # and no scrollbar (of any kind, anywhere) is the point here, not
        # just a smaller one.
        _FORMS_COLS  = self._FORMS_SLOTS
        _PANEL_TOTAL = 3 * self._PANEL_W + 2 * 6           # 1890 + 12 = 1902
        _FORMS_BTN_W = (_PANEL_TOTAL - 2 - 16 - (_FORMS_COLS - 1) * 6) // _FORMS_COLS
        # header text (~20) + separator (~6) + 1 button row (_BTN_H) + 2
        # ItemSpacing.y(5) gaps between the 3 top-level rows (header, sep,
        # buttons) + the child_window's own top+bottom WindowPadding.y(6
        # each) — same accounting as the old 2-row formula, just one less
        # button row and one less gap.
        _FORMS_H     = 20 + 6 + self._BTN_H + 2 * 5 + 2 * 6
        with dpg.child_window(tag="pool_forms", width=_PANEL_TOTAL,
                              height=_FORMS_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text("› forms", color=_C_P_FORMS)
                dpg.add_spacer(width=10)
                self._build_page_ctrl("forms", self._FORMS_SLOTS, _C_P_FORMS)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                for col in range(_FORMS_COLS):
                    n = col + 1
                    dpg.add_button(
                        tag=f"form_btn_{n}", label=f"f{n}",
                        width=_FORMS_BTN_W, height=self._BTN_H,
                        callback=self._on_form_click, user_data=n)
                    with dpg.tooltip(f"form_btn_{n}"):
                        dpg.add_text(f"form {n}", tag=f"form_tip_{n}")
                    # Built unconditionally for every grid position, not
                    # just n >= FIRST_CUSTOM_SLOT: paging can put a regular
                    # custom form at ANY grid position (e.g. slot 17 lands
                    # on grid position 1 on forms' second page), and that
                    # position still needs a working context menu. The
                    # underlying RENAME/DELETE FORM commands already reject
                    # built-in slots 1-4 on their own ("built-ins 1-4
                    # protected" — see command_reference.py), so there's no
                    # need to duplicate that guard in the UI here.
                    with dpg.popup(f"form_btn_{n}", mousebutton=1):
                        dpg.add_text("form", tag=f"form_ctxlbl_{n}", color=_C_P_FORMS)
                        dpg.add_separator()
                        dpg.add_menu_item(label="use form",
                            callback=self._ctx_exec_paged,
                            user_data=("forms", self._FORMS_SLOTS, n, "FX FORM {n}"))
                        dpg.add_menu_item(label="rename...",
                            callback=self._ctx_prefill_paged,
                            user_data=("forms", self._FORMS_SLOTS, n, "RENAME FORM {n} "))
                        dpg.add_separator()
                        dpg.add_menu_item(label="delete form",
                            callback=self._ctx_exec_paged,
                            user_data=("forms", self._FORMS_SLOTS, n, "DELETE FORM {n}"))
    def _on_fx_click(self, _sender, _app_data, user_data):
        n = self._pool_page_offset("fx") + user_data
        if self._fx_pool and self._fx_pool.get(n):
            result = self._cmd(f"FIRE FX {n}") if self._cmd else None
            preset = self._fx_pool.get(n)
            self._log(f"> fx {n} — {preset.name}")
            if result:
                self._log(f"  {result}")
            # If the FX editor is open, sync it to this slot
            try:
                if dpg.get_item_configuration("fx_editor_window").get("show", False):
                    self._fxed_select_slot(None, None, n)
            except Exception:
                pass
        else:
            self._log(f"> fx {n} is empty — open fx ed to build a preset")
        self._focus_cmd()
    def _on_clear_fx(self, *_):
        result = self._cmd("CLEAR FX") if self._cmd else None
        self._log("> clear fx")
        if result:
            self._log(f"  {result}")
        self._focus_cmd()
    def _on_attr_click(self, _sender, _app_data, user_data):
        attr_name, grid_n = user_data
        n = self._pool_page_offset(attr_name) + grid_n
        pool = self._attr_pools.get(attr_name) if self._attr_pools else None
        if pool and pool.get(n):
            if self._cmd:
                result = self._cmd(f"{attr_name.upper()} {n}")
                if result:
                    self._log(f"  {result}")
            self._log(f"> {attr_name.upper()} {n} — {pool.get(n).name}")
        else:
            self._log(f"> {attr_name.upper()} {n} is empty")
            self._log(f"  To record: set value in programmer, then  RECORD {attr_name.upper()} {n} Name")
        self._focus_cmd()
    def _on_form_click(self, _sender, _app_data, user_data):
        n = self._pool_page_offset("forms") + user_data
        if self._form_pool and self._form_pool.get(n):
            form = self._form_pool.get(n)
            self._log(f"> FORM {n} — {form.name}  ({form.form_type})")
            if self._cmd:
                result = self._cmd(f"FX FORM {n}")
                if result:
                    self._log(f"  {result}")
        else:
            self._log(f"> FORM {n} is empty")
            if n < FormPool.FIRST_CUSTOM_SLOT:
                self._log(f"  slots 1-4 are built-ins (sine/ramp/pulse/square)")
            else:
                self._log(f"  to record: record form {n} name 0.0,0.0 0.5,1.0 1.0,0.0")
        self._focus_cmd()
    def _on_rate_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._cmd:
            result = self._cmd(f"RATE {n}")
            if result:
                self._log(f"> RATE {n}")
                self._log(f"  {result}")
    def _on_size_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._cmd:
            result = self._cmd(f"SIZEP {n}")
            if result:
                self._log(f"> SIZEP {n}")
                self._log(f"  {result}")
    def _on_spread_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._cmd:
            result = self._cmd(f"SPREADP {n}")
            if result:
                self._log(f"> SPREADP {n}")
                self._log(f"  {result}")
    def _tick_pools(self):
        """Update pool button labels to show occupied/empty state."""
        self._tick_pool_page_labels()
        _grp_off = self._pool_page_offset("groups")
        _col_off = self._pool_page_offset("colors")
        _dim_off = self._pool_page_offset("dims")
        for n in range(1, self._POOL_SLOTS + 1):
            # Groups — n is the fixed grid position (also the widget tag
            # suffix and theme-cache key); gn is the real pool slot that
            # position currently shows, per the panel's page offset.
            gn = _grp_off + n
            g = self._groups.get(gn) if self._groups else None
            lbl = f"{gn}:{g.name[:7]}" if g else f"g{gn}"
            try:
                dpg.set_item_label(f"grp_btn_{n}", lbl)
                _gt = self._pool_live_theme if g else self._pool_empty_theme
                if _gt:
                    dpg.bind_item_theme(f"grp_btn_{n}", _gt)
            except Exception:
                pass
            try:
                if g:
                    ids = [str(fid) for _, fid in g.members]
                    id_str = ", ".join(ids[:8]) + ("…" if len(ids) > 8 else "")
                    tip = f"group {gn}: {g.name}\n{len(ids)} fixture(s): [{id_str}]"
                else:
                    tip = f"group {gn} — empty"
                dpg.set_value(f"grp_tip_{n}", tip)
                dpg.set_value(f"grp_ctxlbl_{n}", f"group {gn}")
            except Exception:
                pass
            # Colors
            cn = _col_off + n
            c = self._colors.get(cn) if self._colors else None
            lbl = f"{cn}:{c.name[:7]}" if c else f"c{cn}"
            try:
                dpg.set_item_label(f"col_btn_{n}", lbl)
            except Exception:
                pass
            try:
                if c:
                    ch_tip = "  ".join(f"{k.title()} {int(v)}" for k, v in c.channels.items()) or "(empty)"
                    col_tip = f"color {cn}: {c.name}\n{ch_tip}"
                else:
                    col_tip = f"color {cn} — empty"
                dpg.set_value(f"col_tip_{n}", col_tip)
                dpg.set_value(f"col_ctxlbl_{n}", f"color {cn}")
            except Exception:
                pass
            # Tint the color button with the preset's actual color
            if c:
                # Swatch tint is an RGB approximation regardless of how many
                # channels the preset actually carries — a preset that's
                # amber/white/lime/uv-only (no red/green/blue at all) still
                # needs *some* button color, so missing RGB channels default
                # to 0 here rather than erroring.
                r, g, b = int(c.channels.get('red', 0)), int(c.channels.get('green', 0)), int(c.channels.get('blue', 0))
                cached = self._col_btn_themes.get(n)
                if cached is None or cached[0] != (r, g, b):
                    if cached:
                        try:
                            dpg.delete_item(cached[1])
                        except Exception:
                            pass
                    try:
                        with dpg.theme() as _cth:
                            with dpg.theme_component(dpg.mvButton):
                                dpg.add_theme_color(dpg.mvThemeCol_Button,
                                                    (max(20, r//3), max(20, g//3), max(20, b//3), 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,
                                                    (min(255, r*2//3+20), min(255, g*2//3+20), min(255, b*2//3+20), 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,
                                                    (r, g, b, 255))
                        dpg.bind_item_theme(f"col_btn_{n}", _cth)
                        self._col_btn_themes[n] = ((r, g, b), _cth)
                    except Exception:
                        pass
            else:
                if n in self._col_btn_themes:
                    # preset deleted — remove custom theme
                    try:
                        dpg.delete_item(self._col_btn_themes[n][1])
                    except Exception:
                        pass
                    del self._col_btn_themes[n]
                # Apply empty theme (consistent with other pools)
                try:
                    if self._pool_empty_theme:
                        dpg.bind_item_theme(f"col_btn_{n}", self._pool_empty_theme)
                except Exception:
                    pass
            # Dims
            dn = _dim_off + n
            d = self._dims.get(dn) if self._dims else None
            lbl = f"{dn}:{d.name[:7]}" if d else f"d{dn}"
            try:
                dpg.set_item_label(f"dim_btn_{n}", lbl)
            except Exception:
                pass
            try:
                tip = (f"dim {dn}: {d.name}  {d.level*100:.0f}%") if d else f"dim {dn} — empty"
                dpg.set_value(f"dim_tip_{n}", tip)
                dpg.set_value(f"dim_ctxlbl_{n}", f"dim {dn}")
            except Exception:
                pass
            # Tint the dim button with a brightness-scaled grey
            if d:
                lv = max(0.05, float(d.level))
                cached = self._dim_btn_themes.get(n)
                if cached is None or abs(cached[0] - lv) > 0.01:
                    if cached:
                        try:
                            dpg.delete_item(cached[1])
                        except Exception:
                            pass
                    try:
                        br   = int(lv * 180)
                        brH  = min(255, int(lv * 255))
                        with dpg.theme() as _dth:
                            with dpg.theme_component(dpg.mvButton):
                                # violet-tinted brightness scale: dark resting → vivid violet active
                                dpg.add_theme_color(dpg.mvThemeCol_Button,
                                                    (br//5, br//6, br//2, 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,
                                                    (brH//3, brH//5, brH, 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,
                                                    (min(220, int(brH*0.85)), min(180, int(brH*0.55)), 255, 255))
                        dpg.bind_item_theme(f"dim_btn_{n}", _dth)
                        self._dim_btn_themes[n] = (lv, _dth)
                    except Exception:
                        pass
            else:
                if n in self._dim_btn_themes:
                    try:
                        dpg.delete_item(self._dim_btn_themes[n][1])
                    except Exception:
                        pass
                    del self._dim_btn_themes[n]
                try:
                    if self._pool_empty_theme:
                        dpg.bind_item_theme(f"dim_btn_{n}", self._pool_empty_theme)
                except Exception:
                    pass

        # Stacks — highlight the active one
        active = self._active_fader[0] if self._active_fader else None
        _stk_off = self._pool_page_offset("stacks")
        for n in range(1, self._POOL_SLOTS + 1):
            sn = _stk_off + n
            stk = self._stack_pool.get(sn) if self._stack_pool else None
            lbl = f"{sn}:{stk.name[:5]}" if stk else f"stk{sn}"
            try:
                dpg.set_item_label(f"cs_btn_{n}", lbl)
            except Exception:
                pass
            try:
                is_active = (sn == active and stk is not None)
                if is_active:
                    theme = self._go_theme
                elif stk:
                    theme = self._pool_live_theme
                else:
                    theme = self._pool_empty_theme
                dpg.bind_item_theme(f"cs_btn_{n}", theme if theme else 0)
            except Exception:
                pass
            try:
                if stk:
                    ncues = len(stk.cues)
                    cur   = stk.current
                    cs_tip = f"stack {sn}: {stk.name}\n{ncues} cue(s)"
                    if cur is not None:
                        cs_tip += f"\n▶ cue {cur:.0f}"
                else:
                    cs_tip = f"stack {sn} — empty"
                dpg.set_value(f"cs_tip_{n}", cs_tip)
                dpg.set_value(f"cs_ctxlbl_{n}", f"stack {sn}")
            except Exception:
                pass

        # Cues, from the active stack
        active_cs = None
        if self._stack_pool and self._active_fader:
            active_cs = self._stack_pool.get(self._active_fader[0])
        current_cue = active_cs.current if active_cs else None
        _cue_off = self._pool_page_offset("cues")
        for n in range(1, self._POOL_SLOTS + 1):
            qn = _cue_off + n
            cue = active_cs.cues.get(float(qn)) if active_cs else None
            if cue:
                lbl = f"{qn}:{cue.name[:5]}" + (" ◀" if qn == current_cue else "")
                ft_s  = f"  fade {cue.fade_time}s" if cue.fade_time  else ""
                dt_s  = f"  delay {cue.delay_time}s" if cue.delay_time else ""
                fw    = getattr(cue, 'follow_time', 0.0)
                fw_s  = f"  →{fw:.0f}s" if fw > 0 else ""
                fxo   = getattr(cue, 'fx_outfade', None)
                fxo_s = f"  FXOut:{fxo}s" if fxo is not None else ""
                nfix  = sum(1 for k in getattr(cue, 'data', {}) if not k.startswith('__') and '.' not in k) if hasattr(cue, 'data') else 0
                fix_s = f"\n{nfix} fixture(s)" if nfix else ""
                nfx   = 0
                if hasattr(cue, 'data') and isinstance(cue.data, dict):
                    for k, v in cue.data.items():
                        if not k.startswith('__') and isinstance(v, dict):
                            nfx += len(v.get('fx', []) or [])
                fx_s  = f"\n{nfx} FX layer(s)" if nfx else ""
                note  = getattr(cue, 'note', '')
                note_s = f"\nnote: {note}" if note else ""
                tip   = f"cue {qn}: {cue.name}{ft_s}{dt_s}{fw_s}{fxo_s}{fix_s}{fx_s}{note_s}"
            else:
                lbl = f"{qn}"
                tip = f"cue {qn} — empty"
            try:
                dpg.set_item_label(f"cue_btn_{n}", lbl)
                dpg.configure_item(f"cue_tip_{n}", default_value=tip)
                dpg.set_value(f"cue_ctxlbl_{n}", f"cue {qn}")
            except Exception:
                pass
            # Highlight active cue green, dim empty slots, default for occupied-inactive
            try:
                if qn == current_cue and cue:
                    dpg.bind_item_theme(f"cue_btn_{n}", self._go_theme if self._go_theme else 0)
                elif cue:
                    dpg.bind_item_theme(f"cue_btn_{n}", self._pool_live_theme if self._pool_live_theme else 0)
                else:
                    dpg.bind_item_theme(f"cue_btn_{n}", self._pool_empty_theme if self._pool_empty_theme else 0)
            except Exception:
                pass

        # FX pool
        _fx_off = self._pool_page_offset("fx")
        for n in range(1, self._POOL_SLOTS + 1):
            xn = _fx_off + n
            p = self._fx_pool.get(xn) if self._fx_pool else None
            lbl = f"{xn}:{p.name[:6]}" if p else f"fx{xn}"
            try:
                dpg.set_item_label(f"fx_btn_{n}", lbl)
                _ft = self._pool_live_theme if p else self._pool_empty_theme
                if _ft:
                    dpg.bind_item_theme(f"fx_btn_{n}", _ft)
            except Exception:
                pass
            try:
                if p and p.layers:
                    layer_strs = [f"{ld['waveform']} {ld['channel']} {ld.get('bpm', 60):.0f} bpm"
                                  for ld in p.layers[:3]]
                    fx_tip = f"fx {xn}: {p.name}\n" + "\n".join(layer_strs)
                    if len(p.layers) > 3:
                        fx_tip += f"\n+ {len(p.layers)-3} more layer(s)"
                elif p:
                    fx_tip = f"fx {xn}: {p.name} (empty)"
                else:
                    fx_tip = f"fx {xn} — empty"
                dpg.set_value(f"fx_tip_{n}", fx_tip)
                dpg.set_value(f"fx_ctxlbl_{n}", f"fx preset {xn}")
            except Exception:
                pass

        # Attribute pools (12 slots each)
        _ATTR_SLOTS = 12
        _ATTR_MAP = [
            ("position", "pos"), ("gobo", "gobo"), ("zoom", "zoom"),
            ("focus", "focus"), ("beam", "beam"), ("control", "ctrl"),
        ]
        for attr_name, pfx in _ATTR_MAP:
            pool = self._attr_pools.get(attr_name) if self._attr_pools else None
            _attr_off = self._pool_page_offset(attr_name)
            for n in range(1, _ATTR_SLOTS + 1):
                an = _attr_off + n
                p = pool.get(an) if pool else None
                lbl = f"{an}:{p.name[:6]}" if p else f"{pfx[0]}{an}"
                try:
                    dpg.set_item_label(f"{pfx}_btn_{n}", lbl)
                    tip = f"{attr_name} {an}: {p.name}" if p else f"{attr_name} {an} — empty"
                    dpg.set_value(f"{pfx}_tip_{n}", tip)
                    dpg.set_value(f"{pfx}_ctxlbl_{n}", f"{attr_name} {an}")
                    _at = self._pool_live_theme if p else self._pool_empty_theme
                    if _at:
                        dpg.bind_item_theme(f"{pfx}_btn_{n}", _at)
                except Exception:
                    pass

        # Codes (24 slots, full attr_window width)
        _rec_slot = self._code_rec.get("slot") if self._code_rec else None
        try:
            if _rec_slot is not None:
                n_cmds = len(self._code_rec.get("cmds", []))
                dpg.set_value("code_rec_status",
                    f"recording code {_rec_slot} ({n_cmds} cmd{'s' if n_cmds != 1 else ''})")
                dpg.configure_item("code_rec_status", color=_C_HOT)
            else:
                dpg.set_value("code_rec_status", "not recording")
                dpg.configure_item("code_rec_status", color=_C_DIM)
        except Exception:
            pass
        _code_off = self._pool_page_offset("codes")
        for n in range(1, self._POOL_SLOTS + 1):
            mn = _code_off + n
            m = self._codes.get(mn) if self._codes else None
            lbl = f"{mn}:{m['name'][:6]}" if m else f"c{mn}"
            try:
                dpg.set_item_label(f"code_btn_{n}", lbl)
                tip = (f"code {mn}: {m['name']} — {len(m['commands'])} cmd(s)"
                       if m else f"code {mn} — empty")
                dpg.set_value(f"code_tip_{n}", tip)
                dpg.set_value(f"code_ctxlbl_{n}", f"code {mn}")
                _mt = self._pool_live_theme if m else self._pool_empty_theme
                if _mt:
                    dpg.bind_item_theme(f"code_btn_{n}", _mt)
            except Exception:
                pass

        # Forms — matches the panel's single row of _FORMS_SLOTS
        _form_off = self._pool_page_offset("forms")
        for n in range(1, self._FORMS_SLOTS + 1):
            fn = _form_off + n
            f = self._form_pool.get(fn) if self._form_pool else None
            lbl = f"{fn}:{f.name[:6]}" if f else f"f{fn}"
            try:
                dpg.set_item_label(f"form_btn_{n}", lbl)
                _ft = self._pool_live_theme if f else self._pool_empty_theme
                if _ft:
                    dpg.bind_item_theme(f"form_btn_{n}", _ft)
            except Exception:
                pass
            try:
                if f:
                    ft = getattr(f, 'form_type', 'custom')
                    form_tip = f"form {fn}: {f.name}  ({ft})"
                    if hasattr(f, 'points') and f.points:
                        form_tip += f"\n{len(f.points)} points"
                elif fn < FormPool.FIRST_CUSTOM_SLOT:
                    _BUILTIN = {1: "sine", 2: "ramp", 3: "pulse", 4: "square"}
                    form_tip = f"form {fn}: {_BUILTIN.get(fn, '?')} (built-in)"
                else:
                    form_tip = f"form {fn} — empty  (record form {fn} ...)"
                dpg.set_value(f"form_tip_{n}", form_tip)
                dpg.set_value(f"form_ctxlbl_{n}", f"form {fn}")
            except Exception:
                pass

        # FX pool programmer summary
        self._tick_fx_prog_summary()
        # Keep FX editor slot labels current when the editor is open
        try:
            if dpg.is_item_shown("fx_editor_window"):
                self._fxed_refresh_slot_labels()
        except Exception:
            pass
        # Live-sync speed master faders when the panel is open
        try:
            if dpg.is_item_shown("speed_master_window") and self._speed_pool:
                for sid in self._speed_pool.all_slots():
                    m = self._speed_pool.get(sid)
                    if m:
                        dpg.set_value(f"spd_fader_{sid}", m.bpm)
        except Exception:
            pass
    def _tick_fx_prog_summary(self):
        """Update the programmer FX summary text in the FX pool panel."""
        if not self._prog:
            return

        fx_parts   = []
        color_seen = {}  # ref_id → name (deduplicated across fixtures)
        dim_seen   = {}

        for master in self._patch.all_fixtures():
            fid    = str(master.fixture_id)
            m_data = self._prog.data.get(fid, {})

            for ld in m_data.get('fx', []):
                if ld.get('form_id') and self._form_pool:
                    frm  = self._form_pool.get(ld['form_id'])
                    wave = f"F{ld['form_id']}:{frm.name[:5]}" if frm else f"F{ld['form_id']}"
                else:
                    wave = ld.get('waveform', '?')[:4]
                ch = ld.get('channel', '?')[:1].upper()

                if ld.get('rate_id') and self._rate_pool:
                    rp    = self._rate_pool.get(ld['rate_id'])
                    bpm_s = f"R{ld['rate_id']}:{rp.bpm:.0f}" if rp else f"R{ld['rate_id']}"
                else:
                    bpm_s = f"{ld.get('bpm', 60):.0f}♩"

                if ld.get('size_id') and self._size_pool:
                    sp   = self._size_pool.get(ld['size_id'])
                    sz_s = f"S{ld['size_id']}:{sp.size:.0f}" if sp else f"S{ld['size_id']}"
                else:
                    sz_s = f"sz{ld.get('size', 200):.0f}"

                fx_parts.append(f"{wave}/{ch} {bpm_s} {sz_s}")

            c_ref = m_data.get('color_ref')
            if c_ref and self._colors:
                p = self._colors.get(c_ref)
                color_seen[c_ref] = p.name if p else f"C{c_ref}"

            d_ref = m_data.get('dim_ref')
            if d_ref and self._dims:
                p = self._dims.get(d_ref)
                dim_seen[d_ref] = p.name if p else f"D{d_ref}"

        # FX line — deduplicate identical layers
        seen_fx = []
        for part in fx_parts:
            if part not in seen_fx:
                seen_fx.append(part)
        fx_summary = "  |  ".join(seen_fx) if seen_fx else "— no FX in programmer"

        # color / dim line
        color_str = "  ".join(f"C{rid}:{name}" for rid, name in color_seen.items())
        dim_str   = "  ".join(f"D{rid}:{name}" for rid, name in dim_seen.items())
        other_str = "  ".join(filter(None, [color_str, dim_str]))

        try:
            dpg.set_value("fx_prog_summary", fx_summary)
            dpg.configure_item("fx_prog_summary",
                               color=_C_ACCENT if seen_fx else _C_DIM)
            dpg.set_value("fx_prog_other", other_str)
            dpg.configure_item("fx_prog_other",
                               color=_C_DIM if not other_str else (180, 180, 140, 255))
        except Exception:
            pass
    def _on_fx_rate(self, sender, value):
        now = time.monotonic()
        for layer in self._fx._layers.values():
            if layer.fx_id >= 10000:  # skip fader (cue) FX — programmer sliders don't own them
                continue
            layer.set_rate_smooth(value, now)
        self._fx_sliders_to_prog('bpm', value)
        if self._fx_params is not None:
            self._fx_params['rate_bpm'] = value
        self._fxed_push_to_selected_row('bpm', value)
    def _on_fx_size(self, sender, value):
        for layer in self._fx._layers.values():
            if layer.fx_id >= 10000:
                continue
            layer.size = value
        self._fx_sliders_to_prog('size', value)
        if self._fx_params is not None:
            self._fx_params['size'] = value
        self._fxed_push_to_selected_row('size', value)
    def _on_fx_spread(self, sender, value):
        for layer in self._fx._layers.values():
            if layer.fx_id >= 10000:
                continue
            layer.spread = value
        self._fx_sliders_to_prog('spread', value)
        if self._fx_params is not None:
            self._fx_params['spread'] = value
        self._fxed_push_to_selected_row('spread', value)
    def _on_tap_tempo(self, *_):
        """Record a tap — delegates to the TAP command so GUI and text share state."""
        if self._cmd:
            result = self._cmd("TAP")
            try:
                if result and result.startswith("BPM"):
                    dpg.set_value("fx_tap_label", result.replace("BPM → ", "") + " bpm")
                else:
                    dpg.set_value("fx_tap_label", "tap…")
            except Exception:
                pass
    def _fx_sliders_to_prog(self, key, value):
        """Propagate FX slider change into programmer so it can be recorded."""
        if not self._prog:
            return
        for vals in self._prog.data.values():
            layers = vals.get('fx')
            if isinstance(layers, list):
                for ld in layers:
                    ld[key] = value
