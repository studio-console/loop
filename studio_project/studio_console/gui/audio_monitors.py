"""GUIEngine's audio reactive-mapping controls, output monitors popup, AI chat bar popup, and audio config popup.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.drivers.audio import _AUDIO_AVAILABLE, sd


class GUIEngineAudioMonitors:
    def _on_monitors_toggle(self):
        try:
            if dpg.is_item_shown("monitors_window"):
                self._save_popup_layout()
                dpg.hide_item("monitors_window")
            else:
                dpg.show_item("monitors_window")
        except Exception:
            pass
    def _on_audio_toggle(self):
        try:
            if dpg.is_item_shown("audio_window"):
                self._save_popup_layout()
                dpg.hide_item("audio_window")
            else:
                dpg.show_item("audio_window")
        except Exception:
            pass
    def _on_audio_start(self):
        """Start capture on the device picked in the combo (blank = system default)."""
        if not self._audio_engine:
            return
        device = None
        try:
            name = dpg.get_value("audio_device_combo")
            if name and _AUDIO_AVAILABLE:
                for i, d in enumerate(sd.query_devices()):
                    if d['name'] == name and d['max_input_channels'] > 0:
                        device = i
                        break
        except Exception:
            pass
        try:
            self._audio_engine.start(device=device)
            dpg.set_value("audio_capture_status", "capturing")
            dpg.configure_item("audio_capture_status", color=_C_ACCENT)
        except Exception as e:
            dpg.set_value("audio_capture_status", f"error: {e}")
            dpg.configure_item("audio_capture_status", color=[255, 80, 80, 220])
    def _on_audio_stop(self):
        if not self._audio_engine:
            return
        self._audio_engine.stop()
        try:
            dpg.set_value("audio_capture_status", "stopped")
            dpg.configure_item("audio_capture_status", color=_C_DIM)
        except Exception:
            pass
    def _on_audio_map_toggle(self):
        if not self._audio_mapper:
            return
        if self._audio_mapper.enabled:
            self._audio_mapper.disable()
        else:
            self._audio_mapper.enable()
        try:
            on = self._audio_mapper.enabled
            dpg.set_item_label("audio_map_btn", "mapping: on" if on else "mapping: off")
        except Exception:
            pass
    def _on_audio_gain(self, sender, value):
        if self._audio_engine:
            self._audio_engine.gain = value
    def _tick_audio(self):
        """Update live level meters + capture/mapping status (called from _tick)."""
        if not self._audio_engine or not dpg.is_item_shown("audio_window"):
            return
        try:
            dpg.set_value("audio_bar_level", self._audio_engine.level)
            dpg.set_value("audio_bar_low",   self._audio_engine.low)
            dpg.set_value("audio_bar_mid",   self._audio_engine.mid)
            dpg.set_value("audio_bar_high",  self._audio_engine.high)
            if self._audio_mapper:
                on = self._audio_mapper.enabled
                dpg.set_item_label("audio_map_btn", "mapping: on" if on else "mapping: off")
            state = "capturing" if self._audio_engine._running else "stopped"
            dpg.set_value("audio_capture_status", state)
        except Exception:
            pass
    def _build_monitors_popup(self):
        """Floating programmer/output monitor popup — no inner boxes, just tables."""
        # 1600 was sized for just the two tables (programmer + output).
        # Adding the live-fx panel as a third column (see below) pushed the
        # real content past that width with nothing to scroll it back into
        # view with — it was rendering, just entirely off the right edge
        # of the window (reported: "not seeing live fx in monitor window").
        # Widened to fit all three with real margin, using explicit widths
        # everywhere (out_table's width was previously implicit/auto) so
        # this total is verifiable instead of another guess.
        with dpg.window(tag="monitors_window", label="monitors",
                        width=1900, height=360, show=False,
                        pos=(10, 360), no_collapse=False):
            with dpg.group(horizontal=True):
                # ── programmer ──────────────────────────────────────
                with dpg.group(tag="prog_panel"):
                    dpg.add_text("programmer", tag="prog_mon_title", color=_C_DIM)
                    dpg.add_separator()
                    with dpg.table(tag="prog_table", header_row=True,
                                   borders_innerV=True, borders_outerV=True,
                                   borders_outerH=True, row_background=True,
                                   width=768, scrollY=False):
                        dpg.add_table_column(label="fixture", width_fixed=True, init_width_or_weight=110)
                        dpg.add_table_column(label="r",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="g",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="b",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="dim", width_fixed=True, init_width_or_weight=56)
                        dpg.add_table_column(label="fx / refs / attrs", width_stretch=True)
                        dpg.add_table_column(label="bar", width_fixed=True, init_width_or_weight=130)

                        for master in self._patch.all_fixtures():
                            fid = str(master.fixture_id)
                            with dpg.table_row(tag=f"prog_row_{fid}"):
                                dpg.add_text(master.name, tag=f"prog_name_{fid}", color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_r_{fid}",   color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_g_{fid}",   color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_b_{fid}",   color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_dim_{fid}", color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_fx_{fid}",  color=_C_DIM)
                                dpg.add_progress_bar(default_value=0.0,
                                                     tag=f"prog_bar_{fid}", width=-1)

                dpg.add_spacer(width=24)

                # ── Output Monitor ──────────────────────────────────
                with dpg.group(tag="out_panel"):
                    dpg.add_text("output monitor", color=_C_ACCENT)
                    dpg.add_separator()
                    with dpg.table(tag="out_table", header_row=True,
                                   borders_innerV=True, borders_outerV=True,
                                   borders_outerH=True, row_background=True,
                                   width=650, scrollY=False):
                        dpg.add_table_column(label="fixture", width_fixed=True, init_width_or_weight=110)
                        dpg.add_table_column(label="r",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="g",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="b",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="dim", width_fixed=True, init_width_or_weight=56)
                        dpg.add_table_column(label="bar", width_stretch=True)

                        for master in self._patch.all_fixtures():
                            fid = str(master.fixture_id)
                            with dpg.table_row(tag=f"out_row_{fid}"):
                                dpg.add_text(master.name, tag=f"out_name_{fid}")
                                dpg.add_text("0",  tag=f"out_r_{fid}",   color=(200, 80,  80,  255))
                                dpg.add_text("0",  tag=f"out_g_{fid}",   color=(80,  200, 80,  255))
                                dpg.add_text("0",  tag=f"out_b_{fid}",   color=(80,  130, 220, 255))
                                dpg.add_text("--", tag=f"out_dim_{fid}", color=_C_DIM)
                                dpg.add_progress_bar(default_value=0.0,
                                                     tag=f"out_bar_{fid}", width=-1)

                dpg.add_spacer(width=24)

                # ── Live FX (programmer) — moved here from the left column,
                # which needed the room for more running-stacks rows. Same
                # tags (prog_fx_list/prog_fx_empty) and the same
                # _rebuild_prog_fx_list()/kill-fx callback as before, just a
                # different window to live in — that rebuild function needed
                # no changes at all.
                with dpg.group(tag="fx_mon_panel"):
                    with dpg.group(horizontal=True):
                        dpg.add_text("live fx (programmer)", color=_C_ACCENT)
                        dpg.add_spacer(width=8)
                        dpg.add_button(label="kill", width=50, height=22,
                                       callback=lambda: self._cmd("FX CLEAR") if self._cmd else None)
                    dpg.add_separator()
                    with dpg.child_window(tag="prog_fx_list", width=380, height=280,
                                          border=True, no_scrollbar=False,
                                          no_scroll_with_mouse=False):
                        dpg.add_text("— none live", tag="prog_fx_empty", color=_C_DIM)
    def _build_ai_bar_popup(self):
        """Floating AI prompt bar — moved out of the main window (was inline,
        ~70px, and only counted against the 1920x1080 layout budget when
        ANTHROPIC_API_KEY was unset; with a key set it silently busted the
        no-scrollbar budget). Always built now, like the attr/monitors popups,
        so the main window's layout is deterministic regardless of AI config.
        """
        with dpg.window(tag="ai_bar_window", label="ai prompt",
                        width=760, height=230, show=False, pos=(240, 100),
                        on_close=self._on_ai_bar_close):
            with dpg.group(horizontal=True):
                dpg.add_text("ai prompt", color=_C_ACCENT)
                dpg.add_spacer(width=8)
                dpg.add_text("", tag="ai_status", color=_C_DIM)
                dpg.add_spacer(width=8)
                dpg.add_text("", tag="ai_tokens", color=_C_DIM)
                dpg.add_spacer(width=8)
                dpg.add_button(label="history", width=70,
                               callback=lambda: dpg.configure_item(
                                   "ai_history_window",
                                   show=not dpg.is_item_shown("ai_history_window")))
                dpg.add_spacer(width=4)
                dpg.add_button(label="prompts", width=70,
                               callback=self._on_ai_prompts_toggle)
            if not (self._ai and self._ai._enabled):
                dpg.add_text("anthropic_api_key not set — requests will no-op",
                             color=_C_DIM)
            dpg.add_separator()
            with dpg.group():
                for row_start in range(0, len(self._AI_CHIPS), 5):
                    with dpg.group(horizontal=True):
                        for label, prompt in self._AI_CHIPS[row_start:row_start + 5]:
                            dpg.add_button(label=label, width=140,
                                           callback=self._on_ai_chip,
                                           user_data=prompt)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="ai_input", hint="describe the look...",
                                   width=-120, on_enter=True,
                                   callback=self._on_ai_send)
                dpg.add_button(label="send", width=110,
                               callback=self._on_ai_send)
    def _build_audio_popup(self):
        """Floating audio-reactive panel — front-end for Block 9's AudioEngine/
        AudioMapper, which previously had a full AUDIO ON/OFF/START/STOP/GAIN
        command surface but zero GUI (see changelog / KNOWN ISSUES): device
        pick, capture, and mapping toggle all required typing commands. Mirrors
        the ai/midi popup pattern — built hidden, opened via a header button.
        """
        with dpg.window(tag="audio_window", label="audio reactive",
                        width=420, height=300, show=False, pos=(260, 120)):
            dpg.add_text("audio reactive", color=_C_ACCENT)
            dpg.add_separator()
            if not (self._audio_engine and _AUDIO_AVAILABLE):
                dpg.add_text("audio backend unavailable — sounddevice/Portaudio "
                             "not installed or no input device.", color=_C_DIM,
                             wrap=380)
            with dpg.group(horizontal=True):
                dpg.add_text("device:", color=_C_DIM)
                _dev_names = []
                if self._audio_engine and _AUDIO_AVAILABLE:
                    try:
                        _dev_names = [d['name'] for d in sd.query_devices()
                                     if d['max_input_channels'] > 0]
                    except Exception:
                        _dev_names = []
                dpg.add_combo(tag="audio_device_combo", items=_dev_names,
                              default_value=_dev_names[0] if _dev_names else "",
                              width=220)
            with dpg.group(horizontal=True):
                dpg.add_button(label="start capture", width=110,
                               callback=self._on_audio_start)
                dpg.add_button(label="stop", width=60,
                               callback=self._on_audio_stop)
                dpg.add_text("", tag="audio_capture_status", color=_C_DIM)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="mapping: off", tag="audio_map_btn", width=130,
                               callback=self._on_audio_map_toggle)
                dpg.add_text("bass=red mid=green high=blue level=dim", color=_C_DIM,
                             wrap=180)
            dpg.add_drag_float(tag="audio_gain", label="gain",
                               default_value=(self._audio_engine.gain
                                              if self._audio_engine else 3.0),
                               min_value=0.1, max_value=20.0, speed=0.1,
                               format="%.1f", width=200,
                               callback=self._on_audio_gain)
            dpg.add_separator()
            dpg.add_text("live levels", color=_C_DIM)
            for _lbl, _tag in (("level", "audio_bar_level"), ("low", "audio_bar_low"),
                              ("mid", "audio_bar_mid"), ("high", "audio_bar_high")):
                with dpg.group(horizontal=True):
                    dpg.add_text(f"{_lbl:5s}", color=_C_DIM)
                    dpg.add_progress_bar(tag=_tag, default_value=0.0, width=280)
