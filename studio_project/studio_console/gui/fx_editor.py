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

        _FXED_COLS   = 8
        _FXED_BTN_W  = 108   # 8 × 108 + 7 × 6 spacing ≈ 906, fits in 940px window
        _FXED_BTN_H  = 28
        with dpg.window(tag="fx_editor_window", label="fx editor",
                        width=1100, height=580, show=False,
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

            # ── Layer list ────────────────────────────────────
            dpg.add_text("layers:", color=_C_DIM)
            with dpg.child_window(tag="fxed_layers_win",
                                  width=-1, height=270, border=True):
                with dpg.table(tag="fxed_layer_table", header_row=True,
                               borders_innerV=False, borders_outerV=False,
                               borders_innerH=False, borders_outerH=False,
                               policy=dpg.mvTable_SizingFixedFit):
                    dpg.add_table_column(label="waveform", width_fixed=True, init_width_or_weight=94)
                    dpg.add_table_column(label="channel",  width_fixed=True, init_width_or_weight=74)
                    dpg.add_table_column(label="bpm",      width_fixed=True, init_width_or_weight=64)
                    dpg.add_table_column(label="size",     width_fixed=True, init_width_or_weight=64)
                    dpg.add_table_column(label="spread",   width_fixed=True, init_width_or_weight=59)
                    dpg.add_table_column(label="phase",    width_fixed=True, init_width_or_weight=59)
                    dpg.add_table_column(label="group",    width_fixed=True, init_width_or_weight=96)
                    dpg.add_table_column(label="color",    width_fixed=True, init_width_or_weight=96)
                    dpg.add_table_column(label="dim",      width_fixed=True, init_width_or_weight=96)
                    dpg.add_table_column(label="spd",      width_fixed=True, init_width_or_weight=50)
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
                self._fxed_rebuild_rows()
                return
        self._log(f"all {self._POOL_SLOTS} fx slots are full — delete one first")
    def _fxed_delete_preset(self, *_):
        if self._fx_ed_slot and self._fx_pool:
            self._fx_pool.delete(self._fx_ed_slot)
            self._fx_ed_layers = []
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

        _spd_items = ["—"] + [str(n) for n in range(1, SpeedMasterPool._DEFAULT_SLOTS + 1)]
        _grp_items = self._fxed_named_items(self._groups,  'groups',  'name')
        _col_items = self._fxed_named_items(self._colors,  'presets', 'name')
        _dim_items = self._fxed_named_items(self._dims,    'presets', 'name')

        for i, ld in enumerate(self._fx_ed_layers):
            _gid = ld.get('group_id')
            _cid = ld.get('color_id')
            _did = ld.get('dim_id')
            _sid = ld.get('speed_id')

            # DPG quirk: set_value() is called right after each widget so that
            # _fxed_sync_rows() reads the correct value even if the user never
            # touched the widget (default_value alone isn't returned by get_value).
            with dpg.table_row(parent="fxed_layer_table") as row_id:
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
                                    step=0, format="%.1f")
                dpg.set_value(f"fxed_r{i}_bpm", ld.get('bpm', 60.0))

                dpg.add_input_float(tag=f"fxed_r{i}_size", label="", width=60,
                                    default_value=ld.get('size', 100.0),
                                    min_value=0.0, max_value=100.0,
                                    step=0, format="%.0f")
                dpg.set_value(f"fxed_r{i}_size", ld.get('size', 100.0))

                dpg.add_input_float(tag=f"fxed_r{i}_spread", label="", width=55,
                                    default_value=ld.get('spread', 0.0),
                                    min_value=0.0, max_value=100.0,
                                    step=0, format="%.1f")
                dpg.set_value(f"fxed_r{i}_spread", ld.get('spread', 0.0))

                dpg.add_input_float(tag=f"fxed_r{i}_phase", label="", width=55,
                                    default_value=ld.get('phase_offset', 0.0),
                                    min_value=0.0, max_value=1.0,
                                    step=0, format="%.3f")
                dpg.set_value(f"fxed_r{i}_phase", ld.get('phase_offset', 0.0))

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

                dpg.add_button(label="x", width=24, height=20,
                               callback=self._fxed_remove_layer,
                               user_data=i)
            self._fxed_row_ids.append(row_id)
    def _fxed_add_layer(self, *_):
        self._fxed_sync_rows()   # save any edits in existing rows first
        self._fx_ed_layers.append({
            'waveform':     dpg.get_value("fxed_add_wave"),
            'channel':      dpg.get_value("fxed_add_ch"),
            'bpm':          dpg.get_value("fxed_add_bpm"),
            'size':         dpg.get_value("fxed_add_size"),
            'spread':       dpg.get_value("fxed_add_spread"),
            'phase_offset': dpg.get_value("fxed_add_phase"),
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
                self._fx_ed_layers[i]['group_id']      = _ref(dpg.get_value(f"fxed_r{i}_grp"))
                self._fx_ed_layers[i]['color_id']      = _ref(dpg.get_value(f"fxed_r{i}_col"))
                self._fx_ed_layers[i]['dim_id']        = _ref(dpg.get_value(f"fxed_r{i}_dim"))
                self._fx_ed_layers[i]['speed_id']      = _ref(dpg.get_value(f"fxed_r{i}_spd"))
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
                group_id     = ld.get('group_id'),
                color_id     = ld.get('color_id'),
                dim_id       = ld.get('dim_id'),
                speed_id     = ld.get('speed_id'),
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
