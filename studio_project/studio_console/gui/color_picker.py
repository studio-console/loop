"""GUIEngine's color picker popup — the _cpick_* method cluster.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403


class GUIEngineColorPicker:
    def _on_color_picker_toggle(self):
        try:
            if dpg.is_item_shown("color_picker_window"):
                dpg.hide_item("color_picker_window")
            else:
                self._cpick_sync_from_programmer()
                dpg.show_item("color_picker_window")
        except Exception:
            pass
    def _build_color_picker_popup(self):
        """Floating RGB color picker — live mode fires to programmer on every drag."""
        with dpg.window(tag="color_picker_window", label="color picker",
                        width=370, height=480, show=False,
                        pos=(800, 200), no_collapse=False):
            with dpg.group(horizontal=True):
                dpg.add_text("color picker", color=_C_ACCENT)
                dpg.add_spacer(width=12)
                dpg.add_checkbox(tag="cpick_live", label="live",
                                 default_value=True)
            dpg.add_separator()
            dpg.add_color_picker(
                tag="cpick_wheel",
                default_value=(255, 0, 128, 255),
                no_alpha=True,
                no_small_preview=True,
                display_rgb=True,
                display_hex=True,
                picker_mode=dpg.mvColorPicker_wheel,
                width=290,
                callback=self._on_cpick_change,
            )
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="apply",  width=90, height=26,
                               callback=self._on_cpick_apply)
                dpg.add_spacer(width=6)
                dpg.add_button(label="white",  width=70, height=26,
                               callback=lambda: self._cpick_set(255, 255, 255))
                dpg.add_spacer(width=6)
                dpg.add_button(label="off",    width=60, height=26,
                               callback=lambda: self._cpick_set(0, 0, 0))
            # Quick color swatches
            _QUICK_COLS = [
                ("red",     (255,   0,   0)),
                ("green",   (  0, 255,   0)),
                ("blue",    (  0,   0, 255)),
                ("amber",   (255, 140,   0)),
                ("cyan",    (  0, 200, 200)),
                ("magenta", (255,   0, 200)),
                ("warm",    (255, 180,  60)),
                ("uv",      ( 80,   0, 200)),
            ]
            with dpg.group(horizontal=True):
                for name, (r, g, b) in _QUICK_COLS[:4]:
                    dpg.add_button(
                        label=name, width=68, height=20,
                        callback=lambda s, a, u: self._cpick_set(*u),
                        user_data=(r, g, b),
                    )
            with dpg.group(horizontal=True):
                for name, (r, g, b) in _QUICK_COLS[4:]:
                    dpg.add_button(
                        label=name, width=68, height=20,
                        callback=lambda s, a, u: self._cpick_set(*u),
                        user_data=(r, g, b),
                    )
            dpg.add_text("", tag="cpick_status", color=_C_DIM)
    def _on_cpick_change(self, sender, color_val):
        """Called realtime as the user drags the picker — fires if live is on."""
        if dpg.get_value("cpick_live"):
            self._cpick_fire(color_val, live=True)
    def _on_cpick_apply(self):
        """Apply button — push current picker color to programmer unconditionally."""
        col = dpg.get_value("cpick_wheel")
        self._cpick_fire(col)
    def _cpick_set(self, r, g, b):
        """Set picker to an explicit colour and apply immediately."""
        dpg.set_value("cpick_wheel", (r, g, b, 255))
        self._cpick_fire((r, g, b, 255))
    def _cpick_fire(self, color_val, live=False):
        """Send R G B values to the programmer for the current fixture selection.

        Uses set_rgb() directly for an atomic single-undo update instead of
        routing through run_command (which does 3 separate set_channel calls).
        During live drag (live=True), near-black values are skipped — they are
        almost always drag artifacts from the wheel's black corner, not intent.
        """
        r = max(0, min(255, int(color_val[0])))
        g = max(0, min(255, int(color_val[1])))
        b = max(0, min(255, int(color_val[2])))
        if live and r + g + b < 6:
            return  # skip transient black during drag; use Off button for intentional black
        if self._prog:
            self._prog.set_rgb(r, g, b)
        try:
            dpg.set_value("cpick_status", f"R {r}  G {g}  B {b}")
        except Exception:
            pass
    def _cpick_sync_from_programmer(self):
        """Seed the picker with the live output RGB of the first selected fixture.

        Priority: programmer data → cue output → bright white.
        Using a bright seed ensures the wheel's inner triangle cursor is never
        stuck at the black corner, which would cause every hue drag to fire (0,0,0).
        """
        if not self._prog:
            return
        sel = list(self._prog.selection)
        if not sel:
            return
        master = sel[0]
        fid_master  = str(getattr(master, 'fixture_id', master))
        first_sub_fid = f"{fid_master}.1"

        # 1. Try programmer (sub-fixture first, then master)
        sub_vals = self._prog.data.get(first_sub_fid) or self._prog.data.get(fid_master) or {}
        if 'red' in sub_vals or 'green' in sub_vals or 'blue' in sub_vals:
            r = max(0, min(255, int(sub_vals.get('red',   0))))
            g = max(0, min(255, int(sub_vals.get('green', 0))))
            b = max(0, min(255, int(sub_vals.get('blue',  0))))
        else:
            # 2. Fall back to the live cue-merge output so the wheel opens at the
            #    actual displayed colour, not at black.
            r = g = b = 255  # safe default: full white
            if self._out:
                try:
                    cue_layer = self._out._merged_cue_layer()
                    cue_sub   = cue_layer.get(first_sub_fid, {})
                    cr = max(0, min(255, int(cue_sub.get('red',   0))))
                    cg = max(0, min(255, int(cue_sub.get('green', 0))))
                    cb = max(0, min(255, int(cue_sub.get('blue',  0))))
                    if cr + cg + cb > 0:
                        r, g, b = cr, cg, cb
                except Exception:
                    pass

        try:
            dpg.set_value("cpick_wheel", (r, g, b, 255))
            dpg.set_value("cpick_status", f"R {r}  G {g}  B {b}")
        except Exception:
            pass
