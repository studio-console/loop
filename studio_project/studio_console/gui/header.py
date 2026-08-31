"""GUIEngine's header bar (title, current cue status).

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403


class GUIEngineHeader:
    def _build_header(self):
        # ── Top row: info + 4 grouped button clusters ──────────
        with dpg.group(horizontal=True):
            dpg.add_text("STUDIO", color=_C_ACCENT)
            dpg.add_text("v0.21", color=_C_DIM)
            dpg.add_spacer(width=8)
            dpg.add_text("▶", tag="hdr_cue", color=_C_TEXT)
            dpg.add_spacer(width=6)
            dpg.add_text("fx: off", tag="hdr_fx", color=_C_DIM)
            dpg.add_spacer(width=6)
            dpg.add_text("", tag="hdr_clock", color=_C_DIM)
            dpg.add_text("dim: --", tag="hdr_dim", color=_C_TEXT)
            dpg.add_spacer(width=10)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            # cluster: hardware — patch / osc / midi
            dpg.add_text("hw", color=_C_DIM)
            dpg.add_spacer(width=4)
            dpg.add_button(label="patch", width=60, height=24,
                           callback=self._on_patch_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="osc", width=50, height=24,
                           callback=self._on_osc_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="midi", width=60, height=24,
                           callback=self._on_midi_toggle)
            dpg.add_spacer(width=8)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            # cluster: views — pages / attr / fdrs / mon
            dpg.add_text("view", color=_C_DIM)
            dpg.add_spacer(width=4)
            dpg.add_button(label="pages", width=55, height=24,
                           callback=self._on_pages_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="attr", width=50, height=24,
                           callback=self._on_attr_popup_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="fdrs", width=50, height=24,
                           callback=self._on_fader_page_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="mon", width=50, height=24,
                           callback=self._on_monitors_toggle)
            dpg.add_spacer(width=8)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            # cluster: tools — fx ed / color / spd / ai
            dpg.add_text("tools", color=_C_DIM)
            dpg.add_spacer(width=4)
            dpg.add_button(label="fx ed", width=60, height=24,
                           callback=self._on_fx_editor_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="color", width=52, height=24,
                           callback=self._on_color_picker_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="spd", width=46, height=24,
                           callback=self._on_speed_master_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="ai", width=36, height=24,
                           callback=self._on_ai_bar_toggle)
            dpg.add_spacer(width=8)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            # cluster: system — log / ? / audio / save show
            dpg.add_text("sys", color=_C_DIM)
            dpg.add_spacer(width=4)
            dpg.add_button(label="log", width=50, height=24,
                           callback=self._on_changelog_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="?", width=30, height=24,
                           callback=self._on_keys_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="audio", width=50, height=24,
                           callback=self._on_audio_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="save show", width=90, height=24,
                           callback=self._on_save)
            dpg.add_spacer(width=6)
            dpg.add_text("", tag="hdr_save_status", color=_C_DIM)
            dpg.add_spacer(width=8)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            # cluster: window — min / close. The app starts fullscreen
            # (no OS title bar), so these are the only way to minimize or
            # quit without a keyboard shortcut. "close" runs the same
            # dpg.stop_dearpygui() the OS window-close button would have
            # triggered, which flows into run()'s normal shutdown path
            # (popup layout + show autosave) — not a hard process kill.
            dpg.add_text("win", color=_C_DIM)
            dpg.add_spacer(width=4)
            dpg.add_button(label="min", tag="hdr_minimize_btn", width=46, height=24,
                           callback=lambda: dpg.minimize_viewport())
            dpg.add_spacer(width=2)
            dpg.add_button(label="close", tag="hdr_close_btn", width=56, height=24,
                           callback=lambda: dpg.stop_dearpygui())

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
            dpg.add_spacer(width=16)
            dpg.add_text("sel", color=_C_DIM)
            dpg.add_spacer(width=4)
            # one clickable chip per patched fixture
            if self._patch:
                for master in self._patch.all_fixtures():
                    fid = master.fixture_id
                    dpg.add_button(label=f"[{fid}]", tag=f"sb_sel_{fid}",
                                   width=34, height=20,
                                   callback=self._on_fixture_chip_click,
                                   user_data=fid)
                    dpg.add_spacer(width=2)
        dpg.add_separator()
