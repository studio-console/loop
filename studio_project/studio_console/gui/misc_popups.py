"""GUIEngine's keys/cue-timing/changelog/fader-pages popups.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.show import ShowFile, _read_file
from studio_console.command_reference import COMMAND_REFERENCE


class GUIEngineMiscPopups:
    def _on_keys_toggle(self):
        try:
            if dpg.is_item_shown("keys_window"):
                self._save_popup_layout()
                dpg.hide_item("keys_window")
            else:
                dpg.show_item("keys_window")
        except Exception:
            pass
    def _on_changelog_toggle(self):
        try:
            if dpg.is_item_shown("changelog_window"):
                self._save_popup_layout()
                dpg.hide_item("changelog_window")
            else:
                self._refresh_changelog_popup()
                dpg.show_item("changelog_window")
        except Exception:
            pass
    def _on_cue_timing_toggle(self):
        try:
            if dpg.is_item_shown("cue_timing_window"):
                dpg.hide_item("cue_timing_window")
            else:
                dpg.show_item("cue_timing_window")
        except Exception:
            pass
    def _on_pages_toggle(self):
        try:
            if dpg.is_item_shown("pages_window"):
                self._save_popup_layout()
                dpg.hide_item("pages_window")
            else:
                self._refresh_pages_table()
                dpg.show_item("pages_window")
        except Exception:
            pass
    def _build_keys_popup(self):
        """Floating keyboard / command reference — hidden by default, opened via ? button."""

        _S = COMMAND_REFERENCE  # (section_title, [(command, description), ...]) — see command_reference.py

        with dpg.window(tag="keys_window", label="keyboard & command reference",
                        width=720, height=560, show=False,
                        pos=(240, 80), no_collapse=False):
            dpg.add_text("command reference", color=_C_ACCENT)
            dpg.add_separator()
            # Scrolling ON (was off) — this list grows as commands are added, and
            # with no_scrollbar the overflow was silently unreachable.
            with dpg.child_window(width=-1, height=-1, border=False):
                for section, rows in _S:
                    dpg.add_text(section, color=_C_ACCENT)
                    dpg.add_separator()
                    with dpg.table(header_row=False,
                                   borders_innerV=True,
                                   policy=dpg.mvTable_SizingStretchProp):
                        dpg.add_table_column(label="cmd",  init_width_or_weight=0.42)
                        dpg.add_table_column(label="desc", init_width_or_weight=0.58)
                        for cmd, desc in rows:
                            with dpg.table_row():
                                # wrap= so long command strings (e.g. the
                                # "1 AT YELLOW / ORANGE / ..." shorthand rows)
                                # break onto a second line instead of being
                                # silently cut off at the column edge with no
                                # way to read the rest.
                                dpg.add_text(cmd,  color=_C_TEXT, wrap=280)
                                dpg.add_text(desc, color=_C_DIM,  wrap=380)
                    dpg.add_spacer(height=6)
    def _build_cue_timing_popup(self):
        """Floating cue timing editor — fade/delay/follow/fxout + note for active cue."""
        _tw = 220
        with dpg.window(tag="cue_timing_window", label="cue timing",
                        width=320, height=190, show=False,
                        pos=(10, 140), no_collapse=False, no_resize=False):
            with dpg.group(horizontal=True):
                dpg.add_text("cue:", color=_C_DIM)
                dpg.add_text("—", tag="cue_timing_label", color=_C_ACCENT)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_drag_float(tag="cue_fade_input", label="fade s",
                                   default_value=0.0, min_value=0.0, max_value=30.0,
                                   speed=0.05, format="%.2f", width=100,
                                   callback=self._on_cue_fade_edit)
                dpg.add_drag_float(tag="cue_delay_input", label="dly  s",
                                   default_value=0.0, min_value=0.0, max_value=30.0,
                                   speed=0.05, format="%.2f", width=100,
                                   callback=self._on_cue_delay_edit)
            with dpg.group(horizontal=True):
                dpg.add_drag_float(tag="cue_follow_input", label="auto→s",
                                   default_value=0.0, min_value=0.0, max_value=300.0,
                                   speed=0.05, format="%.2f", width=100,
                                   callback=self._on_cue_follow_edit)
                dpg.add_drag_float(tag="cue_fxoutfade_input", label="fxout s",
                                   default_value=0.0, min_value=0.0, max_value=30.0,
                                   speed=0.05, format="%.2f", width=100,
                                   callback=self._on_cue_fxoutfade_edit)
            dpg.add_input_text(tag="cue_note_input", label="note",
                               hint="production note...", width=_tw,
                               callback=self._on_cue_note_edit)
    def _build_changelog_popup(self):
        """Floating changelog viewer — hidden by default, opened via 'log' button."""
        with dpg.window(tag="changelog_window", label="changelog",
                        width=760, height=560, show=False,
                        pos=(260, 90), no_collapse=False):
            dpg.add_text("what's changed", color=_C_ACCENT)
            dpg.add_separator()
            with dpg.child_window(tag="changelog_scroll", width=-1, height=-1, border=False):
                dpg.add_group(tag="changelog_group")
            self._refresh_changelog_popup()
    def _refresh_changelog_popup(self):
        """Reload changelog.json and rebuild the entry list — called each time the popup opens."""
        try:
            dpg.delete_item("changelog_group", children_only=True)
        except Exception:
            return   # popup not built yet

        doc = _read_file(ShowFile.CHANGELOG)
        entries = doc.get("entries", []) if doc else []
        if not entries:
            dpg.add_text("(no changelog entries yet)", color=_C_DIM, parent="changelog_group")
            return

        # Most recent first — entries are appended chronologically as written.
        for entry in reversed(entries):
            date    = entry.get("date", "")
            summary = entry.get("summary", "(no summary)")
            details = entry.get("details", [])
            with dpg.group(parent="changelog_group"):
                dpg.add_text(f"{date} — {summary}", color=_C_TEXT, wrap=700)
                for d in details:
                    dpg.add_text(f"    • {d}", color=_C_DIM, wrap=700)
                dpg.add_spacer(height=8)
    def _build_pages_popup(self):
        """Floating pages editor — assign stacks to named pages."""
        self._pages_current = 1   # currently viewed page number

        with dpg.window(tag="pages_window", label="pages",
                        width=520, height=460, show=False,
                        pos=(220, 130), no_collapse=False):
            # ── Header row ───────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("page", color=_C_DIM)
                dpg.add_input_int(tag="pg_sel_num", label="", width=48,
                                  default_value=1, min_value=1, max_value=99,
                                  step=0, callback=self._on_page_sel_change)
                dpg.add_spacer(width=6)
                dpg.add_input_text(tag="pg_name_input", label="", width=180,
                                   hint="page name", default_value="page 1")
                dpg.add_button(label="rename", width=70,
                               callback=self._on_page_rename)
                dpg.add_spacer(width=6)
                dpg.add_button(label="new page", width=80,
                               callback=self._on_page_new)
                dpg.add_spacer(width=4)
                dpg.add_button(label="del page", width=80,
                               callback=self._on_page_delete)

            dpg.add_separator()

            # ── stack list for selected page ──────────────────
            dpg.add_text("stacks on this page:", color=_C_DIM)
            with dpg.child_window(tag="pg_cs_list", width=-1, height=210,
                                  border=True, no_scrollbar=False):
                dpg.add_group(tag="pg_cs_rows")   # rows rebuilt by _refresh_pages_table

            dpg.add_separator()

            # ── Add stack row ─────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("add:", color=_C_DIM)
                cs_items = self._cs_combo_items()
                dpg.add_combo(items=cs_items, tag="pg_add_cs_combo",
                              default_value=cs_items[0] if cs_items else "",
                              width=290)
                dpg.add_button(label="add to page", width=110,
                               callback=self._on_page_add_cs)

        self._refresh_pages_table()
    def _cs_combo_items(self):
        """Return list of 'ID — Name' strings for all stacks in the pool."""
        if not self._stack_pool:
            return []
        items = []
        for sid in sorted(self._stack_pool.stacks.keys()):
            stk = self._stack_pool.stacks[sid]
            items.append(f"{sid} — {stk.name}")
        return items
    def _refresh_pages_table(self):
        """Rebuild the stack list for the currently selected page."""
        try:
            dpg.delete_item("pg_cs_rows", children_only=True)
        except Exception:
            return
        if not self._fader_pool:
            return

        n    = self._pages_current
        page = self._fader_pool.pages.get(n)
        if not page:
            dpg.add_text("(page not created yet — add a stack to create it)",
                         parent="pg_cs_rows", color=_C_DIM)
            return

        cs_ids = page.get('stacks', [])
        if not cs_ids:
            dpg.add_text("— no stacks on this page —",
                         parent="pg_cs_rows", color=_C_DIM)
            return

        for cs_id in cs_ids:
            stk   = self._stack_pool.get(cs_id) if self._stack_pool else None
            lbl  = f"{cs_id} — {stk.name}" if stk else f"{cs_id} — (not found)"
            with dpg.group(horizontal=True, parent="pg_cs_rows"):
                dpg.add_button(label="×", width=24,
                               callback=lambda s, a, u: self._on_page_remove_cs(u),
                               user_data=cs_id)
                dpg.add_text(lbl)

        # Refresh the page-name field to match loaded data
        try:
            dpg.set_value("pg_name_input", page.get('name', f"page {n}"))
        except Exception:
            pass
    def _on_page_sel_change(self):
        self._pages_current = int(dpg.get_value("pg_sel_num"))
        page = self._fader_pool.pages.get(self._pages_current) if self._fader_pool else None
        try:
            dpg.set_value("pg_name_input",
                          page['name'] if page else f"page {self._pages_current}")
        except Exception:
            pass
        self._refresh_pages_table()
    def _on_page_rename(self):
        n    = self._pages_current
        name = dpg.get_value("pg_name_input").strip()
        if not name:
            return
        if self._cmd:
            self._cmd(f"PAGE {n} NAME {name}")
        self._log(f"> page {n} renamed to '{name}'")
    def _on_page_new(self):
        # Find next unused page number
        existing = set(self._fader_pool.all_pages()) if self._fader_pool else set()
        n = 1
        while n in existing:
            n += 1
        if self._fader_pool:
            self._fader_pool.get_page(n)   # creates it
            ShowFile.save_fader_pages(self._fader_pool)
        self._pages_current = n
        try:
            dpg.set_value("pg_sel_num", n)
            dpg.set_value("pg_name_input", f"page {n}")
        except Exception:
            pass
        self._refresh_pages_table()
        self._log(f"> page {n} created")
    def _on_page_delete(self):
        n = self._pages_current
        if self._cmd:
            self._cmd(f"PAGE {n} DELETE")
        self._log(f"> page {n} deleted")
        self._refresh_pages_table()
    def _on_page_add_cs(self):
        raw = dpg.get_value("pg_add_cs_combo")
        if not raw:
            return
        try:
            cs_id = int(raw.split("—")[0].strip())
        except (ValueError, IndexError):
            return
        n = self._pages_current
        if self._cmd:
            result = self._cmd(f"PAGE {n} ADD stk {cs_id}")
            if result:
                self._log(f"  {result}")
        self._refresh_pages_table()
    def _on_page_remove_cs(self, cs_id):
        n = self._pages_current
        if self._cmd:
            result = self._cmd(f"PAGE {n} REMOVE stk {cs_id}")
            if result:
                self._log(f"  {result}")
        self._refresh_pages_table()
    def _cue_timing_target(self):
        """Return (Stack, Cue) for the currently active cue, or (None, None)."""
        active_n = self._active_fader[0] if self._active_fader else 1
        stk = self._stack_pool.get(active_n) if self._stack_pool else None
        if not stk or stk.current is None:
            return None, None
        cue = stk.cues.get(stk.current)
        return stk, cue
    def _on_cue_fade_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} FADE {value:.2f}")
    def _on_cue_delay_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} DELAY {value:.2f}")
    def _on_cue_follow_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} FOLLOW {value:.2f}")
    def _on_cue_note_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue:
            cue.note = value
            if self._save:
                self._save()
    def _on_cue_fxoutfade_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} FXOUTFADE {value:.2f}")
