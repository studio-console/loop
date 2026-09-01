"""GUIEngine's FX preset editor popup — the _fxed_* method cluster.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.models.presets import FXPreset
from studio_console.engine.fx import SpeedMasterPool
from studio_console.show import ShowFile


class GUIEngineFXEditor:
    def _build_fx_editor_popup(self):
        """Floating FX preset editor — hidden by default, opened via FX ED button."""
        self._fx_ed_slot   = None   # currently selected preset slot (int)
        self._fx_ed_layers = []     # working copy: list of layer dicts
        # Which _fx_ed_layers row (int, or None if no layers) the live
        # rate/size/spread sliders below are bidirectionally linked to —
        # dragging a slider updates this row's bpm/size/spread, and
        # editing the row's own bpm/size/spread fields updates the
        # slider. Clamped/defaulted by _fxed_rebuild_rows on every call
        # rather than by each individual caller, so there's one place
        # that can't drift out of sync with the actual layer list.
        self._fx_ed_selected_row = None

        _FXED_COLS   = 8
        _FXED_BTN_W  = 108   # 8 × 108 + 7 × 6 spacing ≈ 906, fits in 940px window
        _FXED_BTN_H  = 28
        with dpg.window(tag="fx_editor_window", label="fx editor",
                        width=1320, height=580, show=False,
                        pos=(120, 100), no_collapse=False):

            # ── preset selector row ───────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("preset", color=_C_ACCENT)
                dpg.add_spacer(width=6)
            # pool slots: _POOL_SLOTS in rows of _FXED_COLS
            for _fxed_row in range(self._POOL_SLOTS // _FXED_COLS):
                with dpg.group(horizontal=True):
                    for _fxed_col in range(_FXED_COLS):
                        n = _fxed_row * _FXED_COLS + _fxed_col + 1
                        dpg.add_button(tag=f"fxed_slot_{n}", label=str(n),
                                       width=_FXED_BTN_W, height=_FXED_BTN_H,
                                       callback=self._fxed_select_slot,
                                       user_data=n)
            with dpg.group(horizontal=True):
                dpg.add_button(label="new preset", width=120, height=_FXED_BTN_H,
                               callback=self._fxed_new_preset)
                dpg.add_button(label="delete", width=80, height=_FXED_BTN_H,
                               callback=self._fxed_delete_preset)

            dpg.add_separator()

            # ── Name + actions row ────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("name:", color=_C_DIM)
                dpg.add_input_text(tag="fxed_name", label="", width=200,
                                   default_value="")
                dpg.add_spacer(width=8)
                dpg.add_button(label="rainbow", width=90, height=22,
                               callback=self._fxed_rainbow)
                dpg.add_button(label="chase rgb", width=90, height=22,
                               callback=self._fxed_chase_rgb)
                dpg.add_spacer(width=8)
                dpg.add_button(label="save preset", width=110, height=22,
                               callback=self._fxed_save)
                dpg.add_button(label="fire", width=70, height=22,
                               callback=self._fxed_fire)

            # ── Target selector ───────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("target:", color=_C_DIM)
                dpg.add_combo(tag="fxed_target", label="", width=240,
                              items=["selection", "all fixtures"],
                              default_value="selection")
                dpg.add_spacer(width=6)
                dpg.add_button(label="↻ groups", width=90, height=22,
                               callback=self._fxed_refresh_target)

            dpg.add_separator()

            # ── Live controls — moved here from the main window to
            # declutter it (was the "› fx" section in left_column.py).
            # Same tags/callbacks as before: these act on every currently
            # RUNNING programmer FX layer at once, independent of whatever
            # preset slot is loaded above for editing — not a per-preset
            # setting, so they live in their own row rather than inside
            # the add-layer form.
            with dpg.group(horizontal=True):
                dpg.add_text("› live", color=_C_ACCENT)
                dpg.add_spacer(width=4)
                dpg.add_button(label="tap", tag="fx_tap_btn", width=42, height=24,
                               callback=self._on_tap_tempo)
                dpg.add_text("", tag="fx_tap_label", color=_C_DIM)
                dpg.add_spacer(width=12)
                dpg.add_button(label="kill fx", tag="kill_fx_btn", width=90,
                               callback=lambda: self._cmd("KILL FX") if self._cmd else None)
                dpg.add_button(label="rsp pool", width=80,
                               callback=self._on_fx_params_toggle)
            with dpg.group(horizontal=True):
                dpg.add_slider_float(label="rate bpm", tag="fx_rate",
                                     default_value=60.0, min_value=10.0,
                                     max_value=480.0, width=240,
                                     callback=self._on_fx_rate)
                dpg.add_slider_float(label="size", tag="fx_size",
                                     default_value=100.0, min_value=0.0,
                                     max_value=100.0, width=240,
                                     callback=self._on_fx_size)
                dpg.add_slider_float(label="spread", tag="fx_spread",
                                     default_value=0.0, min_value=0.0,
                                     max_value=100.0, width=240,
                                     callback=self._on_fx_spread)
                dpg.add_text("", tag="fxed_linked_lbl", color=_C_DIM)

            # Distribution controls for the ●-linked row (same row the
            # sliders above edit) — big, always-visible, not buried in the
            # scrolling layer table. Editor-only: unlike rate/size/spread
            # above, there's no live "adjust every running FX's low/dist"
            # command to also drive, so these only ever touch the selected
            # preset-editor row (and, bidirectionally, that row's own cells
            # in the table below).
            #
            # mirror/cluster/random are independent, combinable toggles
            # (not a single mutually-exclusive mode) — check any subset of
            # them together with a block size and a direction to build a
            # chase pattern, the same way MA's own effect-grouping knobs
            # compose. See FXLayer's distribution comment in engine/fx.py.
            with dpg.group(horizontal=True):
                dpg.add_slider_float(label="low", tag="fxed_sel_low",
                                     default_value=0.0, min_value=0.0,
                                     max_value=100.0, width=180,
                                     callback=self._on_fxed_sel_low)
                dpg.add_checkbox(label="mirror", tag="fxed_sel_mirror",
                                 default_value=False,
                                 callback=self._on_fxed_sel_mirror)
                dpg.add_checkbox(label="cluster", tag="fxed_sel_cluster",
                                 default_value=False,
                                 callback=self._on_fxed_sel_cluster)
                dpg.add_checkbox(label="random", tag="fxed_sel_random",
                                 default_value=False,
                                 callback=self._on_fxed_sel_random)
                dpg.add_text("block", color=_C_DIM)
                dpg.add_input_int(tag="fxed_sel_block", label="", width=60,
                                  default_value=1, min_value=1, max_value=999,
                                  step=0, callback=self._on_fxed_sel_block)
                dpg.add_text("dir", color=_C_DIM)
                dpg.add_combo(tag="fxed_sel_dir", label="", width=70,
                              items=self._FX_DIRECTIONS, default_value='fwd',
                              callback=self._on_fxed_sel_dir)

            dpg.add_separator()

            # ── Layer list ────────────────────────────────────
            dpg.add_text("layers:", color=_C_DIM)
            # horizontal_scrollbar: the table is wider than the window fits
            # comfortably (23 columns once the pool refs/scope/fade columns
            # below are included) — the common fields (waveform..dir) stay
            # in the first ~700px so no scrolling is needed for everyday
            # editing; the less-common pool-reference/fade columns are a
            # scroll away instead of forcing the window itself wider.
            with dpg.child_window(tag="fxed_layers_win",
                                  width=-1, height=270, border=True,
                                  horizontal_scrollbar=True):
                with dpg.table(tag="fxed_layer_table", header_row=True,
                               borders_innerV=False, borders_outerV=False,
                               borders_innerH=False, borders_outerH=False,
                               policy=dpg.mvTable_SizingFixedFit):
                    dpg.add_table_column(label="live",     width_fixed=True, init_width_or_weight=32)
                    dpg.add_table_column(label="waveform", width_fixed=True, init_width_or_weight=94)
                    dpg.add_table_column(label="channel",  width_fixed=True, init_width_or_weight=74)
                    dpg.add_table_column(label="bpm",      width_fixed=True, init_width_or_weight=64)
                    dpg.add_table_column(label="size",     width_fixed=True, init_width_or_weight=64)
                    dpg.add_table_column(label="spread",   width_fixed=True, init_width_or_weight=59)
                    dpg.add_table_column(label="phase",    width_fixed=True, init_width_or_weight=59)
                    dpg.add_table_column(label="low",      width_fixed=True, init_width_or_weight=55)
                    dpg.add_table_column(label="mirror",   width_fixed=True, init_width_or_weight=54)
                    dpg.add_table_column(label="cluster",  width_fixed=True, init_width_or_weight=54)
                    dpg.add_table_column(label="random",   width_fixed=True, init_width_or_weight=54)
                    dpg.add_table_column(label="block",    width_fixed=True, init_width_or_weight=48)
                    dpg.add_table_column(label="dir",      width_fixed=True, init_width_or_weight=64)
                    dpg.add_table_column(label="group",    width_fixed=True, init_width_or_weight=96)
                    dpg.add_table_column(label="color",    width_fixed=True, init_width_or_weight=96)
                    dpg.add_table_column(label="dim",      width_fixed=True, init_width_or_weight=96)
                    dpg.add_table_column(label="spd",      width_fixed=True, init_width_or_weight=50)
                    dpg.add_table_column(label="form",     width_fixed=True, init_width_or_weight=90)
                    dpg.add_table_column(label="rateP",    width_fixed=True, init_width_or_weight=70)
                    dpg.add_table_column(label="sizeP",    width_fixed=True, init_width_or_weight=70)
                    dpg.add_table_column(label="sprP",     width_fixed=True, init_width_or_weight=70)
                    dpg.add_table_column(label="scope",    width_fixed=True, init_width_or_weight=68)
                    dpg.add_table_column(label="infade",   width_fixed=True, init_width_or_weight=55)
                    dpg.add_table_column(label="outfade",  width_fixed=True, init_width_or_weight=55)
                    dpg.add_table_column(label="",         width_fixed=True, init_width_or_weight=30)

            dpg.add_separator()

            # ── Add layer form ────────────────────────────────
            dpg.add_text("add layer:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_combo(tag="fxed_add_wave",    label="", width=90,
                              items=self._FX_WAVEFORMS,
                              default_value=self._FX_WAVEFORMS[0])
                dpg.add_combo(tag="fxed_add_ch",      label="", width=70,
                              items=self._FX_CHANNELS,
                              default_value=self._FX_CHANNELS[0])
                dpg.add_text("bpm", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_bpm",    label="", width=60,
                                    default_value=60.0, min_value=1.0, max_value=999.0,
                                    step=0, format="%.1f")
                dpg.add_text("size", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_size",   label="", width=60,
                                    default_value=100.0, min_value=0.0, max_value=100.0,
                                    step=0, format="%.0f")
                dpg.add_text("spread", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_spread", label="", width=55,
                                    default_value=0.0, min_value=0.0, max_value=100.0,
                                    step=0, format="%.1f")
                dpg.add_text("phase", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_phase",  label="", width=55,
                                    default_value=0.0, min_value=0.0, max_value=1.0,
                                    step=0, format="%.3f")
                dpg.add_button(label="add layer", width=90, height=22,
                               callback=self._fxed_add_layer)
            with dpg.group(horizontal=True):
                dpg.add_text("low", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_low", label="", width=55,
                                    default_value=0.0, min_value=0.0, max_value=100.0,
                                    step=0, format="%.0f")
                dpg.add_checkbox(label="mirror", tag="fxed_add_mirror", default_value=False)
                dpg.add_checkbox(label="cluster", tag="fxed_add_cluster", default_value=False)
                dpg.add_checkbox(label="random", tag="fxed_add_random", default_value=False)
                dpg.add_text("block", color=_C_DIM)
                dpg.add_input_int(tag="fxed_add_block", label="", width=48,
                                  default_value=1, min_value=1, max_value=999, step=0)
                dpg.add_text("dir", color=_C_DIM)
                dpg.add_combo(tag="fxed_add_dir", label="", width=64,
                              items=self._FX_DIRECTIONS, default_value='fwd')
                dpg.add_text("scope", color=_C_DIM)
                dpg.add_combo(tag="fxed_add_scope", label="", width=68,
                              items=["default", "pixel", "fixture"],
                              default_value='default')
                dpg.add_text("infade", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_infade", label="", width=50,
                                    default_value=0.0, min_value=0.0, max_value=60.0,
                                    step=0, format="%.1f")
                dpg.add_text("outfade", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_outfade", label="", width=50,
                                    default_value=0.0, min_value=0.0, max_value=60.0,
                                    step=0, format="%.1f")

        self._fxed_refresh_slot_labels()
    def _refresh_fx_pool_buttons(self):
        for n in range(1, self._POOL_SLOTS + 1):
            p = self._fx_pool.get(n) if self._fx_pool else None
            lbl = f"{n}:{p.name[:6]}" if p else f"fx{n}"
            try:
                dpg.set_item_label(f"fx_btn_{n}", lbl)
            except Exception:
                pass
    def _fxed_refresh_slot_labels(self):
        for n in range(1, self._POOL_SLOTS + 1):
            p = self._fx_pool.get(n) if self._fx_pool else None
            label = p.name[:10] if p else str(n)
            is_selected = (n == self._fx_ed_slot)
            try:
                dpg.set_item_label(f"fxed_slot_{n}", label)
                color = _C_BTN_A if is_selected else (_C_ACCENT if p else _C_BTN)
                dpg.configure_item(f"fxed_slot_{n}", enabled=True)
                _ = color
            except Exception:
                pass
    def _fxed_select_slot(self, _s, _a, user_data):
        self._fx_ed_slot = user_data
        preset = self._fx_pool.get(user_data) if self._fx_pool else None
        self._fx_ed_selected_row = None   # a different preset — don't carry over a stale row index
        if preset:
            dpg.set_value("fxed_name", preset.name)
            self._fx_ed_layers = [dict(ld) for ld in preset.layers]
        else:
            dpg.set_value("fxed_name", f"fx {user_data}")
            self._fx_ed_layers = []
        self._fxed_rebuild_rows()
    def _fxed_new_preset(self, *_):
        for n in range(1, self._POOL_SLOTS + 1):
            if not (self._fx_pool and self._fx_pool.get(n)):
                self._fx_ed_slot = n
                dpg.set_value("fxed_name", f"fx {n}")
                self._fx_ed_layers = []
                self._fx_ed_selected_row = None
                self._fxed_rebuild_rows()
                return
        self._log(f"all {self._POOL_SLOTS} fx slots are full — delete one first")
    def _fxed_delete_preset(self, *_):
        if self._fx_ed_slot and self._fx_pool:
            self._fx_pool.delete(self._fx_ed_slot)
            self._fx_ed_layers = []
            self._fx_ed_selected_row = None
            dpg.set_value("fxed_name", "")
            self._fxed_rebuild_rows()
            ShowFile.save_fx_pool(self._fx_pool)
            self._fxed_refresh_slot_labels()
            self._refresh_fx_pool_buttons()
            self._log(f"> FX {self._fx_ed_slot} deleted")
    def _fxed_rainbow(self, *_):
        """Load RGB rainbow template into editor (doesn't save until SAVE is clicked)."""
        self._fx_ed_layers = [
            {'waveform': 'sine', 'channel': 'red',   'bpm': 30.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.0},
            {'waveform': 'sine', 'channel': 'green', 'bpm': 30.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.333},
            {'waveform': 'sine', 'channel': 'blue',  'bpm': 30.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.667},
        ]
        self._fx_ed_selected_row = None
        if not dpg.get_value("fxed_name"):
            dpg.set_value("fxed_name", "rainbow")
        self._fxed_rebuild_rows()
    def _fxed_chase_rgb(self, *_):
        """Pixel chase — white pulse travelling through R then G then B."""
        self._fx_ed_layers = [
            {'waveform': 'pulse', 'channel': 'red',   'bpm': 60.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.0},
            {'waveform': 'pulse', 'channel': 'green', 'bpm': 60.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.333},
            {'waveform': 'pulse', 'channel': 'blue',  'bpm': 60.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.667},
        ]
        self._fx_ed_selected_row = None
        if not dpg.get_value("fxed_name"):
            dpg.set_value("fxed_name", "chase rgb")
        self._fxed_rebuild_rows()
    def _fxed_named_items(self, pool, id_attr='groups', name_attr='name', trunc=8):
        """Build ["—", "1: name", ...] items from a pool dict; only existing entries."""
        items = ["—"]
        pool_dict = getattr(pool, id_attr, {}) if pool else {}
        for pid in sorted(pool_dict):
            entry = pool_dict[pid]
            label = getattr(entry, name_attr, str(pid))[:trunc]
            items.append(f"{pid}: {label}")
        return items
    def _fxed_id_to_label(self, pid, pool, id_attr='groups', name_attr='name', trunc=8):
        """Return "n: name" for a given pool ID, or bare "n" if not found."""
        if pid is None:
            return "—"
        pool_dict = getattr(pool, id_attr, {}) if pool else {}
        entry = pool_dict.get(int(pid))
        if entry:
            label = getattr(entry, name_attr, str(pid))[:trunc]
            return f"{pid}: {label}"
        return str(pid)
    def _fxed_rebuild_rows(self):
        for row_id in getattr(self, '_fxed_row_ids', []):
            try:
                dpg.delete_item(row_id)
            except Exception:
                pass
        self._fxed_row_ids = []

        # Clamp/default the slider-linked row here, once, rather than in
        # every caller that can change _fx_ed_layers (select slot, new
        # preset, add/remove layer, rainbow/chase templates, ...) — one
        # place that can't drift out of sync with the actual layer list.
        n_layers = len(self._fx_ed_layers)
        if n_layers == 0:
            self._fx_ed_selected_row = None
        elif (self._fx_ed_selected_row is None
              or not (0 <= self._fx_ed_selected_row < n_layers)):
            self._fx_ed_selected_row = 0

        _spd_items = ["—"] + [str(n) for n in range(1, SpeedMasterPool._DEFAULT_SLOTS + 1)]
        _grp_items  = self._fxed_named_items(self._groups,     'groups',  'name')
        _col_items  = self._fxed_named_items(self._colors,     'presets', 'name')
        _dim_items  = self._fxed_named_items(self._dims,       'presets', 'name')
        _form_items = self._fxed_named_items(self._form_pool,   'forms',   'name')
        _rate_items = self._fxed_named_items(self._rate_pool,   'presets', 'name')
        _szp_items  = self._fxed_named_items(self._size_pool,   'presets', 'name')
        _sprp_items = self._fxed_named_items(self._spread_pool, 'presets', 'name')
        _scope_items = ["default", "pixel", "fixture"]

        for i, ld in enumerate(self._fx_ed_layers):
            _gid = ld.get('group_id')
            _cid = ld.get('color_id')
            _did = ld.get('dim_id')
            _sid = ld.get('speed_id')
            _fid = ld.get('form_id')
            _rid = ld.get('rate_id')
            _szid = ld.get('size_id')
            _sprid = ld.get('spread_id')

            # DPG quirk: set_value() is called right after each widget so that
            # _fxed_sync_rows() reads the correct value even if the user never
            # touched the widget (default_value alone isn't returned by get_value).
            with dpg.table_row(parent="fxed_layer_table") as row_id:
                # "live" column — which row the rate/size/spread sliders
                # above are bidirectionally linked to. ● marks the linked
                # row; click any row's mark to re-link it.
                _is_sel = (i == self._fx_ed_selected_row)
                dpg.add_selectable(label="●" if _is_sel else "○",
                                   tag=f"fxed_r{i}_sel", width=20,
                                   callback=self._fxed_select_row, user_data=i)

                dpg.add_combo(tag=f"fxed_r{i}_wave", label="", width=90,
                              items=self._FX_WAVEFORMS,
                              default_value=ld.get('waveform', 'sine'))
                dpg.set_value(f"fxed_r{i}_wave", ld.get('waveform', 'sine'))

                dpg.add_combo(tag=f"fxed_r{i}_ch", label="", width=70,
                              items=self._FX_CHANNELS,
                              default_value=ld.get('channel', 'red'))
                dpg.set_value(f"fxed_r{i}_ch", ld.get('channel', 'red'))

                dpg.add_input_float(tag=f"fxed_r{i}_bpm", label="", width=60,
                                    default_value=ld.get('bpm', 60.0),
                                    min_value=1.0, max_value=999.0,
                                    step=0, format="%.1f",
                                    callback=self._fxed_on_row_val_change,
                                    user_data=(i, 'bpm'))
                dpg.set_value(f"fxed_r{i}_bpm", ld.get('bpm', 60.0))

                dpg.add_input_float(tag=f"fxed_r{i}_size", label="", width=60,
                                    default_value=ld.get('size', 100.0),
                                    min_value=0.0, max_value=100.0,
                                    step=0, format="%.0f",
                                    callback=self._fxed_on_row_val_change,
                                    user_data=(i, 'size'))
                dpg.set_value(f"fxed_r{i}_size", ld.get('size', 100.0))

                dpg.add_input_float(tag=f"fxed_r{i}_spread", label="", width=55,
                                    default_value=ld.get('spread', 0.0),
                                    min_value=0.0, max_value=100.0,
                                    step=0, format="%.1f",
                                    callback=self._fxed_on_row_val_change,
                                    user_data=(i, 'spread'))
                dpg.set_value(f"fxed_r{i}_spread", ld.get('spread', 0.0))

                dpg.add_input_float(tag=f"fxed_r{i}_phase", label="", width=55,
                                    default_value=ld.get('phase_offset', 0.0),
                                    min_value=0.0, max_value=1.0,
                                    step=0, format="%.3f")
                dpg.set_value(f"fxed_r{i}_phase", ld.get('phase_offset', 0.0))

                # Floor for the oscillation range — waveform swings between
                # low and size instead of 0 and size (e.g. low=40 size=70
                # keeps a dim/strobe sync between 40% and 70%). Callbacks
                # below mirror edits into the big fxed_sel_* controls above
                # when this is the ●-linked row — same link direction as
                # bpm/size/spread's _fxed_on_row_val_change.
                dpg.add_input_float(tag=f"fxed_r{i}_low", label="", width=50,
                                    default_value=ld.get('low', 0.0),
                                    min_value=0.0, max_value=100.0,
                                    step=0, format="%.0f",
                                    callback=self._fxed_on_row_dist_change,
                                    user_data=(i, 'low'))
                dpg.set_value(f"fxed_r{i}_low", ld.get('low', 0.0))

                # Distribution toggles — independent and combinable (see
                # FXLayer's distribution comment in engine/fx.py): any
                # subset of mirror/cluster/random can be checked together.
                # 'cluster' buckets by the "group" ref column to the right.
                dpg.add_checkbox(tag=f"fxed_r{i}_mirror",
                                 default_value=bool(ld.get('mirror')),
                                 callback=self._fxed_on_row_dist_change,
                                 user_data=(i, 'mirror'))
                dpg.set_value(f"fxed_r{i}_mirror", bool(ld.get('mirror')))
                dpg.add_checkbox(tag=f"fxed_r{i}_cluster",
                                 default_value=bool(ld.get('cluster')),
                                 callback=self._fxed_on_row_dist_change,
                                 user_data=(i, 'cluster'))
                dpg.set_value(f"fxed_r{i}_cluster", bool(ld.get('cluster')))
                dpg.add_checkbox(tag=f"fxed_r{i}_random",
                                 default_value=(ld.get('order') == 'random'),
                                 callback=self._fxed_on_row_dist_change,
                                 user_data=(i, 'random'))
                dpg.set_value(f"fxed_r{i}_random", ld.get('order') == 'random')

                dpg.add_input_int(tag=f"fxed_r{i}_block", label="", width=44,
                                  default_value=ld.get('block_size', 1),
                                  min_value=1, max_value=999, step=0,
                                  callback=self._fxed_on_row_dist_change,
                                  user_data=(i, 'block'))
                dpg.set_value(f"fxed_r{i}_block", ld.get('block_size', 1))

                _dir_val = self._FX_DIR_FROM_INTERNAL.get(ld.get('direction', 'forward'), 'fwd')
                dpg.add_combo(tag=f"fxed_r{i}_dir", label="", width=58,
                              items=self._FX_DIRECTIONS, default_value=_dir_val,
                              callback=self._fxed_on_row_dist_change,
                              user_data=(i, 'dir'))
                dpg.set_value(f"fxed_r{i}_dir", _dir_val)

                _gval = self._fxed_id_to_label(_gid, self._groups,  'groups',  'name')
                dpg.add_combo(tag=f"fxed_r{i}_grp", label="", width=90,
                              items=_grp_items, default_value=_gval)
                dpg.set_value(f"fxed_r{i}_grp", _gval)
                _cval = self._fxed_id_to_label(_cid, self._colors,  'presets', 'name')
                dpg.add_combo(tag=f"fxed_r{i}_col", label="", width=90,
                              items=_col_items, default_value=_cval)
                dpg.set_value(f"fxed_r{i}_col", _cval)
                _dval = self._fxed_id_to_label(_did, self._dims,    'presets', 'name')
                dpg.add_combo(tag=f"fxed_r{i}_dim", label="", width=90,
                              items=_dim_items, default_value=_dval)
                dpg.set_value(f"fxed_r{i}_dim", _dval)

                dpg.add_combo(tag=f"fxed_r{i}_spd", label="", width=46,
                              items=_spd_items,
                              default_value="—" if _sid is None else str(_sid))
                dpg.set_value(f"fxed_r{i}_spd", "—" if _sid is None else str(_sid))

                # Pool references — override the inline bpm/size/spread
                # above (live-tracked: editing the referenced pool preset
                # updates every layer pointing at it, same as color/dim/spd).
                _fval = self._fxed_id_to_label(_fid, self._form_pool, 'forms', 'name')
                dpg.add_combo(tag=f"fxed_r{i}_form", label="", width=84,
                              items=_form_items, default_value=_fval)
                dpg.set_value(f"fxed_r{i}_form", _fval)
                _rval = self._fxed_id_to_label(_rid, self._rate_pool, 'presets', 'name')
                dpg.add_combo(tag=f"fxed_r{i}_rate", label="", width=64,
                              items=_rate_items, default_value=_rval)
                dpg.set_value(f"fxed_r{i}_rate", _rval)
                _szval = self._fxed_id_to_label(_szid, self._size_pool, 'presets', 'name')
                dpg.add_combo(tag=f"fxed_r{i}_szp", label="", width=64,
                              items=_szp_items, default_value=_szval)
                dpg.set_value(f"fxed_r{i}_szp", _szval)
                _sprval = self._fxed_id_to_label(_sprid, self._spread_pool, 'presets', 'name')
                dpg.add_combo(tag=f"fxed_r{i}_sprp", label="", width=64,
                              items=_sprp_items, default_value=_sprval)
                dpg.set_value(f"fxed_r{i}_sprp", _sprval)

                # target scope — PIXEL (per sub-fixture) vs FIXTURE (whole
                # master) vs "default" (channel-dependent: colour defaults
                # to pixel, dim defaults to fixture — see _bucket_fx_defs).
                _scope_val = ld.get('target_scope') or 'default'
                dpg.add_combo(tag=f"fxed_r{i}_scope", label="", width=62,
                              items=_scope_items, default_value=_scope_val)
                dpg.set_value(f"fxed_r{i}_scope", _scope_val)

                dpg.add_input_float(tag=f"fxed_r{i}_infade", label="", width=50,
                                    default_value=ld.get('infade', 0.0),
                                    min_value=0.0, max_value=60.0,
                                    step=0, format="%.1f")
                dpg.set_value(f"fxed_r{i}_infade", ld.get('infade', 0.0))
                dpg.add_input_float(tag=f"fxed_r{i}_outfade", label="", width=50,
                                    default_value=ld.get('outfade', 0.0),
                                    min_value=0.0, max_value=60.0,
                                    step=0, format="%.1f")
                dpg.set_value(f"fxed_r{i}_outfade", ld.get('outfade', 0.0))

                dpg.add_button(label="x", width=24, height=20,
                               callback=self._fxed_remove_layer,
                               user_data=i)
            self._fxed_row_ids.append(row_id)
        self._fxed_sync_sliders_to_selected_row()
    def _fxed_select_row(self, _s, _a, user_data):
        """Re-link the rate/size/spread sliders to a different layer row."""
        self._fx_ed_selected_row = int(user_data)
        for i in range(len(self._fx_ed_layers)):
            try:
                dpg.configure_item(f"fxed_r{i}_sel",
                                   label="●" if i == self._fx_ed_selected_row else "○")
            except Exception:
                pass
        self._fxed_sync_sliders_to_selected_row()
    def _fxed_sync_sliders_to_selected_row(self):
        """Push the linked row's bpm/size/spread into the live sliders
        (display only — does not touch running FX) and update the label
        showing which row is linked."""
        idx = self._fx_ed_selected_row
        try:
            if idx is None or not (0 <= idx < len(self._fx_ed_layers)):
                dpg.set_value("fxed_linked_lbl", "no layer linked")
                return
            ld = self._fx_ed_layers[idx]
            dpg.set_value("fx_rate",   ld.get('bpm',    60.0))
            dpg.set_value("fx_size",   ld.get('size',  100.0))
            dpg.set_value("fx_spread", ld.get('spread',  0.0))
            dpg.set_value("fxed_sel_low",     ld.get('low', 0.0))
            dpg.set_value("fxed_sel_mirror",  bool(ld.get('mirror')))
            dpg.set_value("fxed_sel_cluster", bool(ld.get('cluster')))
            dpg.set_value("fxed_sel_random",  ld.get('order') == 'random')
            dpg.set_value("fxed_sel_block", ld.get('block_size', 1))
            dpg.set_value("fxed_sel_dir",
                          self._FX_DIR_FROM_INTERNAL.get(ld.get('direction', 'forward'), 'fwd'))
            dpg.set_value("fxed_linked_lbl", f"↔ linked to row {idx + 1}")
        except Exception:
            pass
    def _fxed_on_row_val_change(self, _sender, app_data, user_data):
        """A layer row's own bpm/size/spread field was edited directly.
        Updates _fx_ed_layers immediately (not just on the next
        _fxed_sync_rows() pass) and, if this is the slider-linked row,
        pushes the same value out through the normal live-FX slider
        callback — editing the linked row's field is equivalent to
        dragging its slider, not a separate/silent path."""
        i, field = user_data
        if 0 <= i < len(self._fx_ed_layers):
            self._fx_ed_layers[i][field] = app_data
        if i == self._fx_ed_selected_row:
            # A real slider drag has DPG update the slider's own displayed
            # value natively as part of the drag — calling its callback
            # out-of-band like this doesn't, so it has to be done here
            # explicitly or the slider would silently stay stale even
            # though everything it *controls* did update.
            _slider_tag = {'bpm': 'fx_rate', 'size': 'fx_size',
                           'spread': 'fx_spread'}[field]
            try:
                dpg.set_value(_slider_tag, app_data)
            except Exception:
                pass
            {'bpm': self._on_fx_rate,
             'size': self._on_fx_size,
             'spread': self._on_fx_spread}[field](None, app_data)
    def _fxed_push_to_selected_row(self, field, value):
        """Called from _on_fx_rate/_on_fx_size/_on_fx_spread (pools_panel.py)
        on every live slider drag — the other half of the bidirectional
        link: mirrors the drag into the slider-linked row's stored value
        and displayed table cell, if one is linked. A no-op if the FX
        editor hasn't been opened/built yet or no row is linked."""
        idx = getattr(self, '_fx_ed_selected_row', None)
        layers = getattr(self, '_fx_ed_layers', None)
        if idx is None or not layers or not (0 <= idx < len(layers)):
            return
        layers[idx][field] = value
        try:
            dpg.set_value(f"fxed_r{idx}_{field}", value)
        except Exception:
            pass
    def _fxed_on_row_dist_change(self, _sender, app_data, user_data):
        """A layer row's own low/mirror/cluster/random/block/dir field was
        edited directly in the table. Same idea as _fxed_on_row_val_change
        (bpm/size/spread) but for the distribution controls, which have no
        live-running-FX command to also drive — so this only ever mirrors
        into the big fxed_sel_* controls above when this is the ●-linked
        row, never into anything else."""
        i, kind = user_data
        if not (0 <= i < len(self._fx_ed_layers)):
            return
        if kind == 'low':
            self._fx_ed_layers[i]['low'] = app_data
        elif kind == 'mirror':
            self._fx_ed_layers[i]['mirror'] = app_data
        elif kind == 'cluster':
            self._fx_ed_layers[i]['cluster'] = app_data
        elif kind == 'random':
            self._fx_ed_layers[i]['order'] = 'random' if app_data else 'linear'
        elif kind == 'block':
            self._fx_ed_layers[i]['block_size'] = app_data
        elif kind == 'dir':
            self._fx_ed_layers[i]['direction'] = self._FX_DIR_TO_INTERNAL.get(app_data, 'forward')
        if i == self._fx_ed_selected_row:
            _sel_tag = {'low': 'fxed_sel_low', 'mirror': 'fxed_sel_mirror',
                        'cluster': 'fxed_sel_cluster', 'random': 'fxed_sel_random',
                        'block': 'fxed_sel_block', 'dir': 'fxed_sel_dir'}[kind]
            try:
                dpg.set_value(_sel_tag, app_data)
            except Exception:
                pass
    def _on_fxed_sel_low(self, _sender, app_data, _user_data=None):
        """Big 'low' slider (selected row) — the other half of the link
        with _fxed_on_row_dist_change."""
        idx = self._fx_ed_selected_row
        if idx is None or not (0 <= idx < len(self._fx_ed_layers)):
            return
        self._fx_ed_layers[idx]['low'] = app_data
        try:
            dpg.set_value(f"fxed_r{idx}_low", app_data)
        except Exception:
            pass
    def _on_fxed_sel_mirror(self, _sender, app_data, _user_data=None):
        idx = self._fx_ed_selected_row
        if idx is None or not (0 <= idx < len(self._fx_ed_layers)):
            return
        self._fx_ed_layers[idx]['mirror'] = app_data
        try:
            dpg.set_value(f"fxed_r{idx}_mirror", app_data)
        except Exception:
            pass
    def _on_fxed_sel_cluster(self, _sender, app_data, _user_data=None):
        idx = self._fx_ed_selected_row
        if idx is None or not (0 <= idx < len(self._fx_ed_layers)):
            return
        self._fx_ed_layers[idx]['cluster'] = app_data
        try:
            dpg.set_value(f"fxed_r{idx}_cluster", app_data)
        except Exception:
            pass
    def _on_fxed_sel_random(self, _sender, app_data, _user_data=None):
        idx = self._fx_ed_selected_row
        if idx is None or not (0 <= idx < len(self._fx_ed_layers)):
            return
        self._fx_ed_layers[idx]['order'] = 'random' if app_data else 'linear'
        try:
            dpg.set_value(f"fxed_r{idx}_random", app_data)
        except Exception:
            pass
    def _on_fxed_sel_block(self, _sender, app_data, _user_data=None):
        idx = self._fx_ed_selected_row
        if idx is None or not (0 <= idx < len(self._fx_ed_layers)):
            return
        self._fx_ed_layers[idx]['block_size'] = app_data
        try:
            dpg.set_value(f"fxed_r{idx}_block", app_data)
        except Exception:
            pass
    def _on_fxed_sel_dir(self, _sender, app_data, _user_data=None):
        idx = self._fx_ed_selected_row
        if idx is None or not (0 <= idx < len(self._fx_ed_layers)):
            return
        self._fx_ed_layers[idx]['direction'] = self._FX_DIR_TO_INTERNAL.get(app_data, 'forward')
        try:
            dpg.set_value(f"fxed_r{idx}_dir", app_data)
        except Exception:
            pass
    def _fxed_add_layer(self, *_):
        self._fxed_sync_rows()   # save any edits in existing rows first
        _add_scope = dpg.get_value("fxed_add_scope")
        self._fx_ed_layers.append({
            'waveform':     dpg.get_value("fxed_add_wave"),
            'channel':      dpg.get_value("fxed_add_ch"),
            'bpm':          dpg.get_value("fxed_add_bpm"),
            'size':         dpg.get_value("fxed_add_size"),
            'spread':       dpg.get_value("fxed_add_spread"),
            'phase_offset': dpg.get_value("fxed_add_phase"),
            'low':          dpg.get_value("fxed_add_low"),
            'mirror':       dpg.get_value("fxed_add_mirror"),
            'cluster':      dpg.get_value("fxed_add_cluster"),
            'order':        'random' if dpg.get_value("fxed_add_random") else 'linear',
            'block_size':   dpg.get_value("fxed_add_block"),
            'direction':    self._FX_DIR_TO_INTERNAL.get(dpg.get_value("fxed_add_dir"), 'forward'),
            'target_scope': None if _add_scope == 'default' else _add_scope,
            'infade':       dpg.get_value("fxed_add_infade"),
            'outfade':      dpg.get_value("fxed_add_outfade"),
        })
        self._fxed_rebuild_rows()
    def _fxed_remove_layer(self, _s, _a, user_data):
        self._fxed_sync_rows()
        idx = int(user_data)
        if 0 <= idx < len(self._fx_ed_layers):
            self._fx_ed_layers.pop(idx)
        self._fxed_rebuild_rows()
    def _fxed_sync_rows(self):
        """Read current widget values back into _fx_ed_layers."""
        def _ref(v):
            if not v or v == "—":
                return None
            # values may be "n" or "n: name" (from named dropdowns)
            try:
                return int(v.split(":")[0].strip())
            except (ValueError, IndexError):
                return None
        for i in range(len(self._fx_ed_layers)):
            try:
                self._fx_ed_layers[i]['waveform']     = dpg.get_value(f"fxed_r{i}_wave")
                self._fx_ed_layers[i]['channel']       = dpg.get_value(f"fxed_r{i}_ch")
                self._fx_ed_layers[i]['bpm']           = dpg.get_value(f"fxed_r{i}_bpm")
                self._fx_ed_layers[i]['size']          = dpg.get_value(f"fxed_r{i}_size")
                self._fx_ed_layers[i]['spread']        = dpg.get_value(f"fxed_r{i}_spread")
                self._fx_ed_layers[i]['phase_offset']  = dpg.get_value(f"fxed_r{i}_phase")
                self._fx_ed_layers[i]['low']           = dpg.get_value(f"fxed_r{i}_low")
                self._fx_ed_layers[i]['mirror']        = dpg.get_value(f"fxed_r{i}_mirror")
                self._fx_ed_layers[i]['cluster']       = dpg.get_value(f"fxed_r{i}_cluster")
                self._fx_ed_layers[i]['order']         = (
                    'random' if dpg.get_value(f"fxed_r{i}_random") else 'linear')
                self._fx_ed_layers[i]['block_size']    = dpg.get_value(f"fxed_r{i}_block")
                self._fx_ed_layers[i]['direction']     = self._FX_DIR_TO_INTERNAL.get(
                    dpg.get_value(f"fxed_r{i}_dir"), 'forward')
                self._fx_ed_layers[i]['group_id']      = _ref(dpg.get_value(f"fxed_r{i}_grp"))
                self._fx_ed_layers[i]['color_id']      = _ref(dpg.get_value(f"fxed_r{i}_col"))
                self._fx_ed_layers[i]['dim_id']        = _ref(dpg.get_value(f"fxed_r{i}_dim"))
                self._fx_ed_layers[i]['speed_id']      = _ref(dpg.get_value(f"fxed_r{i}_spd"))
                self._fx_ed_layers[i]['form_id']       = _ref(dpg.get_value(f"fxed_r{i}_form"))
                self._fx_ed_layers[i]['rate_id']       = _ref(dpg.get_value(f"fxed_r{i}_rate"))
                self._fx_ed_layers[i]['size_id']       = _ref(dpg.get_value(f"fxed_r{i}_szp"))
                self._fx_ed_layers[i]['spread_id']     = _ref(dpg.get_value(f"fxed_r{i}_sprp"))
                _scope = dpg.get_value(f"fxed_r{i}_scope")
                self._fx_ed_layers[i]['target_scope']  = None if _scope == 'default' else _scope
                self._fx_ed_layers[i]['infade']        = dpg.get_value(f"fxed_r{i}_infade")
                self._fx_ed_layers[i]['outfade']       = dpg.get_value(f"fxed_r{i}_outfade")
            except Exception:
                pass
    def _fxed_save(self, *_):
        if self._fx_ed_slot is None:
            self._log("> select a slot first")
            return
        self._fxed_sync_rows()
        name   = dpg.get_value("fxed_name").strip() or f"fx {self._fx_ed_slot}"
        preset = FXPreset(self._fx_ed_slot, name)
        for ld in self._fx_ed_layers:
            preset.add_layer(
                ld.get('waveform', 'sine'),
                ld.get('channel',  'red'),
                bpm          = ld.get('bpm',          60.0),
                size         = ld.get('size',         200.0),
                spread       = ld.get('spread',         1.0),
                phase_offset = ld.get('phase_offset',   0.0),
                low          = ld.get('low',             0.0),
                mirror       = ld.get('mirror',       False),
                cluster      = ld.get('cluster',      False),
                order        = ld.get('order',    'linear'),
                block_size   = ld.get('block_size',       1),
                direction    = ld.get('direction', 'forward'),
                infade       = ld.get('infade',          0.0),
                outfade      = ld.get('outfade',         0.0),
                target_scope = ld.get('target_scope'),
                group_id     = ld.get('group_id'),
                color_id     = ld.get('color_id'),
                dim_id       = ld.get('dim_id'),
                speed_id     = ld.get('speed_id'),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
            )
        self._fx_pool.store(self._fx_ed_slot, preset)
        ShowFile.save_fx_pool(self._fx_pool)
        self._fxed_refresh_slot_labels()
        self._refresh_fx_pool_buttons()
        self._log(f"> Saved FX {self._fx_ed_slot}: {name}  ({len(preset.layers)} layers)")
    def _fxed_refresh_target(self, *_):
        """Rebuild the target combo with current group list."""
        items = ["selection", "all fixtures"]
        if self._groups:
            for gid in sorted(self._groups.groups):
                g = self._groups.groups[gid]
                if g.members:
                    items.append(f"group {gid}: {g.name}")
        try:
            dpg.configure_item("fxed_target", items=items)
        except Exception:
            pass
    def _fxed_fire(self, *_):
        if self._fx_ed_slot is None:
            self._log("> select a slot first")
            return
        self._fxed_save()

        try:
            target = dpg.get_value("fxed_target")
        except Exception:
            target = "selection"

        saved_sel = list(self._prog.selection)

        if target == "all fixtures":
            self._prog.clear_selection()
        elif target.startswith("group "):
            try:
                gid = int(target.split(":")[0].split()[-1])
                self._groups.recall(gid, self._prog)
            except (ValueError, IndexError, AttributeError):
                pass

        result = self._cmd(f"FIRE FX {self._fx_ed_slot}") if self._cmd else ""

        # Restore selection unless it was already empty
        if saved_sel:
            self._prog.select(saved_sel)

        if result:
            self._log(f"  {result}")
    def _on_fx_editor_toggle(self, *_):
        vis = dpg.get_item_configuration("fx_editor_window").get("show", False)
        if vis:
            self._save_popup_layout()
        dpg.configure_item("fx_editor_window", show=not vis)
        if not vis:
            self._fxed_refresh_target()
            self._fxed_refresh_slot_labels()
