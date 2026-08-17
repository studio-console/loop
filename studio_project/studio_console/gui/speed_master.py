"""GUIEngine's speed master (live BPM slot) popup.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.show import ShowFile


class GUIEngineSpeedMaster:
    def _build_speed_master_popup(self):
        """Floating 16-slot speed master panel — drag a fader to set BPM live."""
        with dpg.window(tag="speed_master_window", label="speed masters",
                        width=560, height=340, show=False,
                        pos=(600, 300), no_collapse=False,
                        on_close=self._on_speed_master_close):
            dpg.add_text("speed masters  (20–480 bpm)", color=_C_ACCENT)
            dpg.add_separator()
            # 4 columns × 4 rows of 16 slots
            for row in range(4):
                with dpg.group(horizontal=True):
                    for col in range(4):
                        sid = row * 4 + col + 1
                        m   = self._speed_pool.get(sid) if self._speed_pool else None
                        bpm = m.bpm if m else 120.0
                        lbl = m.name if m else f"spd{sid}"
                        with dpg.group(horizontal=False):
                            dpg.add_text(f"{sid:2d}: {lbl[:6]}", tag=f"spd_lbl_{sid}",
                                         color=_C_DIM)
                            dpg.add_slider_float(
                                tag=f"spd_fader_{sid}", label="",
                                width=120, height=18,
                                default_value=bpm,
                                min_value=20.0, max_value=480.0,
                                format="%.0f",
                                callback=self._on_spd_fader,
                                user_data=sid,
                            )
                dpg.add_spacer(height=4)
            dpg.add_separator()
            dpg.add_text("rename: SPEED <n> NAME <name>  |  set via command: SPEED <n> <bpm>",
                         color=_C_DIM)
    def _on_spd_fader(self, sender, value, user_data):
        sid = user_data
        if self._speed_pool:
            self._speed_pool.set_bpm(sid, value)
    def _on_speed_master_close(self, *_):
        """Persist BPM values when the panel is dismissed via X."""
        self._save_popup_layout()
        if self._speed_pool:
            try:
                ShowFile.save_speed_masters(self._speed_pool)
            except Exception:
                pass
    def _on_speed_master_toggle(self, *_):
        try:
            self._refresh_speed_master_panel()
            vis = dpg.is_item_shown("speed_master_window")
            if vis:
                dpg.hide_item("speed_master_window")
                if self._speed_pool:
                    ShowFile.save_speed_masters(self._speed_pool)
            else:
                dpg.show_item("speed_master_window")
            self._save_popup_layout()
        except Exception:
            pass
    def _refresh_speed_master_panel(self):
        """Sync fader positions and labels from pool (called on open)."""
        if not self._speed_pool:
            return
        for sid in self._speed_pool.all_slots():
            m = self._speed_pool.get(sid)
            if not m:
                continue
            try:
                dpg.set_value(f"spd_fader_{sid}", m.bpm)
                dpg.set_item_label(f"spd_lbl_{sid}", f"{sid:2d}: {m.name[:6]}")
            except Exception:
                pass
