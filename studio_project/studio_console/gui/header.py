"""GUIEngine's header bar (title, current cue status).

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403


class GUIEngineHeader:
    def _build_header(self):
        # ── Top bar: compact menu bar — clusters become click-to-open menus ──
        with dpg.menu_bar():
            dpg.add_text("STUDIO", color=_C_ACCENT)
            dpg.add_text("v0.22", color=_C_DIM)
            dpg.add_spacer(width=8)

            dpg.add_button(label="min", tag="hdr_minimize_btn", width=46, height=24,
                           callback=lambda: dpg.minimize_viewport())
            dpg.add_spacer(width=2)
            dpg.add_button(label="close", tag="hdr_close_btn", width=56, height=24,
                           callback=lambda: dpg.stop_dearpygui())
            dpg.add_spacer(width=8)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            with dpg.child_window(width=210, height=24, border=False,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_text("▶", tag="hdr_cue", color=_C_TEXT)
            dpg.add_spacer(width=6)
            with dpg.child_window(width=90, height=24, border=False,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_text("fx: off", tag="hdr_fx", color=_C_DIM)
            dpg.add_spacer(width=6)
            with dpg.child_window(width=55, height=24, border=False,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_text("", tag="hdr_clock", color=_C_DIM)
            with dpg.child_window(width=70, height=24, border=False,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_text("dim: --", tag="hdr_dim", color=_C_TEXT)
            dpg.add_spacer(width=10)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            with dpg.menu(label="hw"):
                dpg.add_menu_item(label="patch", callback=self._on_patch_toggle)
                dpg.add_menu_item(label="osc", callback=self._on_osc_toggle)
                dpg.add_menu_item(label="midi", callback=self._on_midi_toggle)

            with dpg.menu(label="view"):
                dpg.add_menu_item(label="pages", callback=self._on_pages_toggle)
                dpg.add_menu_item(label="attr", callback=self._on_attr_popup_toggle)
                dpg.add_menu_item(label="enc bar", callback=self._on_encoder_bar_toggle)
                dpg.add_menu_item(label="fdrs", callback=self._on_fader_page_toggle)
                dpg.add_menu_item(label="mon", callback=self._on_monitors_toggle)
                dpg.add_menu_item(label="3d viz", callback=self._on_viz3d_toggle)

            with dpg.menu(label="tools"):
                dpg.add_menu_item(label="fx ed", callback=self._on_fx_editor_toggle)
                dpg.add_menu_item(label="color", callback=self._on_color_picker_toggle)
                dpg.add_menu_item(label="spd", callback=self._on_speed_master_toggle)
                dpg.add_menu_item(label="ai", callback=self._on_ai_bar_toggle)

            with dpg.menu(label="sys"):
                dpg.add_menu_item(label="log", callback=self._on_changelog_toggle)
                dpg.add_menu_item(label="?", callback=self._on_keys_toggle)
                dpg.add_menu_item(label="audio", callback=self._on_audio_toggle)
                dpg.add_menu_item(label="route", callback=self._on_audio_routing_toggle)
                dpg.add_menu_item(label="save show", callback=self._on_save)

            dpg.add_spacer(width=6)
            dpg.add_text("", tag="hdr_save_status", color=_C_DIM)

        dpg.add_separator()
        # ── Status bar: programmer state + mode pills + selection ─
        with dpg.group(horizontal=True):
            dpg.add_text("●", tag="sb_prog_dot",   color=_C_DIM)
            dpg.add_text("programmer", tag="sb_prog_lbl", color=_C_DIM)
            dpg.add_spacer(width=16)
            dpg.add_button(label="○ blind", tag="sb_blind_lbl",
                           width=70, height=24,
                           callback=self._on_blind_toggle)
            dpg.add_spacer(width=6)
            dpg.add_button(label="○ blackout", tag="sb_bbo_lbl",
                           width=94, height=24,
                           callback=lambda: self._cmd("BLACKOUT") if self._cmd else None)
            dpg.add_spacer(width=6)
            dpg.add_button(label="○ highlight", tag="sb_hl_lbl",
                           width=90, height=24,
                           callback=self._on_highlight_toggle)
            dpg.add_spacer(width=6)
            dpg.add_button(label="○ pan·tilt", tag="sb_pt_lbl",
                           width=84, height=24,
                           callback=self._on_pt_toggle)
            dpg.add_spacer(width=6)
            dpg.add_button(label="○ fade", tag="sb_pf_lbl",
                           width=74, height=24,
                           callback=self._on_pf_toggle)
            dpg.add_spacer(width=16)
            dpg.add_text("sel", color=_C_DIM)
            dpg.add_spacer(width=4)
            if self._patch:
                for master in self._patch.all_fixtures():
                    fid = master.fixture_id
                    dpg.add_button(label=f"[{fid}]", tag=f"sb_sel_{fid}",
                                   width=34, height=20,
                                   callback=self._on_fixture_chip_click,
                                   user_data=fid)
                    dpg.add_spacer(width=2)
        dpg.add_separator()
