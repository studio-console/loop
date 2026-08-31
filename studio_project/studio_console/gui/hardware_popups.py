"""GUIEngine's OSC/MIDI/patch/network config popups, plus MIDI learn and the MIDI mapping table.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.show import ShowFile


class GUIEngineHardwarePopups:
    def _on_patch_toggle(self):
        try:
            if dpg.is_item_shown("patch_window"):
                self._save_popup_layout()
                dpg.hide_item("patch_window")
            else:
                self._refresh_patch_table()
                dpg.show_item("patch_window")
        except Exception:
            pass
    def _on_osc_toggle(self):
        try:
            if dpg.is_item_shown("osc_window"):
                self._save_popup_layout()
                dpg.hide_item("osc_window")
            else:
                self._refresh_osc_table()
                dpg.show_item("osc_window")
        except Exception:
            pass
    def _on_midi_toggle(self):
        try:
            if dpg.is_item_shown("midi_window"):
                self._save_popup_layout()
                dpg.hide_item("midi_window")
            else:
                dpg.show_item("midi_window")
        except Exception:
            pass
    def _build_osc_popup(self):
        """Floating OSC target manager — add/remove output destinations without typing commands."""
        with dpg.window(tag="osc_window", label="osc targets",
                        width=620, height=360, show=False,
                        pos=(200, 150), no_collapse=False):
            dpg.add_text("osc output targets", color=_C_ACCENT)
            dpg.add_separator()

            # ── Add target row ────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("add:", color=_C_DIM)
                dpg.add_input_text(tag="osc_add_name", label="", width=100,
                                   hint="name")
                dpg.add_input_text(tag="osc_add_host", label="", width=140,
                                   hint="host / IP")
                dpg.add_input_int(tag="osc_add_port", label="", width=70,
                                  default_value=8000, min_value=1, max_value=65535, step=0)
                dpg.add_button(label="add", width=52, callback=self._on_osc_add_target)
                dpg.add_text("", tag="osc_add_status", color=_C_ACCENT)

            dpg.add_separator()

            # ── Targets table (rebuilt on refresh) ────────────────
            with dpg.child_window(tag="osc_targets_scroll", width=-1, height=-1, border=False):
                dpg.add_group(tag="osc_targets_group")
    def _refresh_osc_table(self):
        """Rebuild the OSC targets list widget from the live osc engine state."""
        try:
            dpg.delete_item("osc_targets_group", children_only=True)
        except Exception:
            return
        if not self._osc:
            dpg.add_text("(no OSC engine)", color=_C_DIM, parent="osc_targets_group")
            return
        clients = self._osc._clients
        if not clients:
            dpg.add_text("(no targets — add one above)", color=_C_DIM,
                         parent="osc_targets_group")
            return
        with dpg.table(parent="osc_targets_group",
                       header_row=True,
                       borders_innerV=True,
                       policy=dpg.mvTable_SizingStretchProp):
            dpg.add_table_column(label="name",    init_width_or_weight=0.22)
            dpg.add_table_column(label="host",    init_width_or_weight=0.38)
            dpg.add_table_column(label="port",    init_width_or_weight=0.12)
            dpg.add_table_column(label="",        init_width_or_weight=0.28)
            for name, client in list(clients.items()):
                with dpg.table_row():
                    dpg.add_text(name,              color=_C_ACCENT)
                    dpg.add_text(client._address,   color=_C_TEXT)
                    dpg.add_text(str(client._port), color=_C_DIM)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="test", width=46,
                                       callback=self._on_osc_test,
                                       user_data=name)
                        dpg.add_spacer(width=4)
                        dpg.add_button(label="remove", width=58,
                                       callback=self._on_osc_remove,
                                       user_data=name)
    def _on_osc_add_target(self):
        name = dpg.get_value("osc_add_name").strip()
        host = dpg.get_value("osc_add_host").strip()
        port = int(dpg.get_value("osc_add_port"))
        if not name or not host:
            dpg.set_value("osc_add_status", "name+host required")
            return
        if self._osc:
            self._osc.add_target(name, host, port)
            if self._save:
                self._save()
        dpg.set_value("osc_add_status", f"→ {name} added")
        dpg.set_value("osc_add_name", "")
        self._refresh_osc_table()
    def _on_osc_remove(self, _sender, _app, user_data):
        name = user_data
        if self._osc:
            self._osc.remove_target(name)
            if self._save:
                self._save()
        self._refresh_osc_table()
    def _on_osc_test(self, _sender, _app, user_data):
        name = user_data
        if self._osc:
            self._osc.send("/studio/ping", 1, target=name)
    def _build_midi_popup(self):
        """Floating MIDI mapping window — hidden by default, opened via header button."""
        with dpg.window(tag="midi_window", label="midi mappings",
                        width=860, height=540, show=False,
                        pos=(200, 150), no_collapse=False):
            dpg.add_text("midi mappings", color=_C_ACCENT)
            dpg.add_separator()

            # ── Port selector ──────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("port:", color=_C_DIM)
                try:
                    import mido as _mido_tmp
                    _port_names = _mido_tmp.get_input_names()
                except Exception:
                    _port_names = []
                dpg.add_combo(tag="midi_port_combo",
                              items=_port_names,
                              default_value=_port_names[1] if len(_port_names) > 1 else (_port_names[0] if _port_names else ""),
                              width=280)
                dpg.add_button(label="connect", width=70,
                               callback=self._on_midi_port_connect)
                dpg.add_button(label="disconnect", width=80,
                               callback=self._on_midi_port_disconnect)
                dpg.add_spacer(width=6)
                dpg.add_text("", tag="midi_port_status", color=_C_DIM)
            dpg.add_separator()

            with dpg.table(tag="midi_table", header_row=True,
                           borders_innerH=True, borders_outerH=True,
                           borders_innerV=True, borders_outerV=True,
                           row_background=True, scrollY=True,
                           height=200):
                dpg.add_table_column(label="ch",      width_fixed=True, init_width_or_weight=32)
                dpg.add_table_column(label="cc/note", width_fixed=True, init_width_or_weight=65)
                dpg.add_table_column(label="type",    width_fixed=True, init_width_or_weight=45)
                dpg.add_table_column(label="name",    width_stretch=True)
                dpg.add_table_column(label="status",  width_fixed=True, init_width_or_weight=90)
                dpg.add_table_column(label="del",     width_fixed=True, init_width_or_weight=36)
                dpg.add_table_column(label="rsn",     width_fixed=True, init_width_or_weight=36)

            self._refresh_midi_table()

            # Reassign panel — activated when user clicks ► on a row
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("reassign:", color=_C_DIM)
                dpg.add_text("select a row →", tag="rsn_selected", color=_C_DIM)
                target_names = list(self.target_registry.keys())
                dpg.add_combo(items=target_names, tag="rsn_target",
                              default_value=target_names[0] if target_names else "",
                              width=230)
                dpg.add_button(label="apply", width=70,
                               callback=self._on_apply_reassign)

            dpg.add_separator()
            dpg.add_text("add mapping:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_radio_button(items=["cc", "note"],
                                     tag="learn_type_radio",
                                     default_value="cc",
                                     horizontal=True,
                                     callback=self._on_learn_type_change)
                dpg.add_button(label="learn", tag="learn_btn",
                               callback=self._toggle_learn)
                dpg.add_text("", tag="learn_status", color=_C_ACCENT)

            target_names = list(self.target_registry.keys())
            dpg.add_combo(items=target_names,
                          tag="learn_target",
                          default_value=target_names[0] if target_names else "",
                          width=300)
            dpg.add_text("click learn, then move the control (cc) or press a key/pad (note).", color=_C_DIM)

            # ── direct entry (no physical MIDI needed) ────────
            with dpg.group(horizontal=True):
                dpg.add_text("direct:", color=_C_DIM)
                dpg.add_text("ch", color=_C_DIM)
                dpg.add_input_int(tag="direct_ch",   label="", width=42,
                                  default_value=1, min_value=1, max_value=16,
                                  step=0, step_fast=0)
                dpg.add_radio_button(items=["cc", "note"],
                                     tag="direct_type_radio",
                                     default_value="cc", horizontal=True)
                dpg.add_input_int(tag="direct_num",  label="", width=46,
                                  default_value=7, min_value=0, max_value=127,
                                  step=0, step_fast=0)
                dpg.add_combo(items=target_names, tag="direct_target",
                              default_value=target_names[0] if target_names else "",
                              width=200)
                dpg.add_button(label="add", width=52,
                               callback=self._on_direct_add)
                dpg.add_text("", tag="direct_status", color=_C_ACCENT)

            dpg.add_separator()
            dpg.add_text("go directly to a cue via note:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_text("stk", color=_C_DIM)
                dpg.add_input_int(tag="midi_go_cs",  label="", width=46,
                                  default_value=1, min_value=1, max_value=16,
                                  step=0, step_fast=0)
                dpg.add_text("cue", color=_C_DIM)
                dpg.add_input_float(tag="midi_go_cue", label="", width=52,
                                    default_value=1, min_value=1, max_value=9999,
                                    step=0, format="%.0f")
                dpg.add_button(label="learn note", width=100,
                               callback=self._start_go_cue_learn)
                dpg.add_text("", tag="go_cue_status", color=_C_ACCENT)

            dpg.add_separator()
            dpg.add_text("flash a fader while a pad is held:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_text("fdr", color=_C_DIM)
                dpg.add_input_int(tag="midi_flash_exec", label="", width=46,
                                  default_value=1, min_value=1, max_value=99,
                                  step=0, step_fast=0)
                dpg.add_button(label="learn note", width=100,
                               callback=self._start_exec_flash_learn)
                dpg.add_text("", tag="flash_learn_status", color=_C_ACCENT)

            dpg.add_separator()
            dpg.add_text("go/back a specific fader via note:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_text("fdr", color=_C_DIM)
                dpg.add_input_int(tag="midi_exec_gb_num", label="", width=46,
                                  default_value=1, min_value=1, max_value=99,
                                  step=0, step_fast=0)
                dpg.add_radio_button(items=["go", "back"],
                                     tag="midi_exec_gb_type",
                                     default_value="go", horizontal=True)
                dpg.add_button(label="learn note", width=100,
                               callback=self._start_exec_gb_learn)
                dpg.add_text("", tag="midi_exec_gb_status", color=_C_ACCENT)
    def _build_patch_popup(self):
        """Floating patch editor — hidden by default, opened via header PATCH button."""
        profiles = list(self._library.profiles.keys()) if self._library else ["SGM_RGB_54"]
        with dpg.window(tag="patch_window", label="patch editor",
                        width=780, height=460, show=False,
                        pos=(160, 120), no_collapse=False):
            dpg.add_text("patch editor", color=_C_ACCENT)
            dpg.add_separator()

            # ── Current patch table ───────────────────────────
            with dpg.table(tag="patch_table", header_row=True,
                           borders_innerH=True, borders_outerH=True,
                           borders_innerV=True, borders_outerV=True,
                           row_background=True, scrollY=True, height=220):
                dpg.add_table_column(label="id",       width_fixed=True,  init_width_or_weight=36)
                dpg.add_table_column(label="name",     width_fixed=True,  init_width_or_weight=110)
                dpg.add_table_column(label="profile",  width_fixed=True,  init_width_or_weight=130)
                dpg.add_table_column(label="univ",     width_fixed=True,  init_width_or_weight=44)
                dpg.add_table_column(label="start",    width_fixed=True,  init_width_or_weight=52)
                dpg.add_table_column(label="channels", width_fixed=True,  init_width_or_weight=70)
                dpg.add_table_column(label="end",      width_fixed=True,  init_width_or_weight=52)
                dpg.add_table_column(label="",         width_stretch=True)

            self._refresh_patch_table()

            dpg.add_separator()
            dpg.add_text("add fixture:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_input_int(tag="patch_add_id",    label="", width=46,
                                  default_value=1, min_value=1, max_value=999,
                                  step=0, step_fast=0)
                dpg.add_text("id", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_input_text(tag="patch_add_name",  label="", width=110,
                                   default_value="fixture")
                dpg.add_text("name", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_combo(tag="patch_add_profile", label="", width=130,
                              items=profiles,
                              default_value=profiles[0] if profiles else "")
                dpg.add_text("profile", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_input_int(tag="patch_add_univ",  label="", width=46,
                                  default_value=1, min_value=1, max_value=64,
                                  step=0, step_fast=0)
                dpg.add_text("universe", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_input_int(tag="patch_add_addr",  label="", width=60,
                                  default_value=1, min_value=1, max_value=512,
                                  step=0, step_fast=0)
                dpg.add_text("start addr", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_input_int(tag="patch_add_clone_src", label="", width=46,
                                  default_value=0, min_value=0, max_value=999,
                                  step=0, step_fast=0)
                dpg.add_text("clone from (0=none)", color=_C_DIM)
                dpg.add_spacer(width=8)
                dpg.add_button(label="add fixture", width=110,
                               callback=self._on_patch_add)

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="save patch", width=110,
                               callback=self._on_patch_save)
                dpg.add_spacer(width=8)
                dpg.add_text("changes are live. re-open console to rebuild monitors.",
                             color=_C_DIM)

            dpg.add_separator()
            dpg.add_text("sacn network", color=_C_ACCENT)
            with dpg.group(horizontal=True):
                dpg.add_text("bind ip:", color=_C_DIM)
                # network (NetworkEngine instance) is defined in
                # studio_console/state.py, not reachable as a module-level
                # import here — deferred import, same pattern used
                # throughout this split.
                from __main__ import network
                _saved_bind, _saved_univs = ShowFile.load_network()
                dpg.add_input_text(tag="net_bind_input", label="", width=160,
                                   default_value=_saved_bind or network.bind_address or "",
                                   hint="e.g. 192.168.1.161")
                dpg.add_spacer(width=8)
                dpg.add_text("universes:", color=_C_DIM)
                _univ_str = " ".join(str(u) for u in (_saved_univs or network.universes))
                dpg.add_input_text(tag="net_univs_input", label="", width=120,
                                   default_value=_univ_str,
                                   hint="e.g. 1 2")
                dpg.add_spacer(width=8)
                dpg.add_button(label="save network", width=110,
                               callback=self._on_net_save)
            dpg.add_text("saved settings apply on next console restart.",
                         color=_C_DIM)
    def _on_net_save(self, *_):
        try:
            bind = dpg.get_value("net_bind_input").strip()
            univs_raw = dpg.get_value("net_univs_input").strip().split()
            univs = [int(v) for v in univs_raw if v.isdigit()]
            if not univs:
                self._log("  network: universe list must contain at least one number")
                return
        except Exception as e:
            self._log(f"  network: bad input — {e}")
            return
        ShowFile.save_network(bind, univs)
        self._log(f"  network saved: bind={bind or '(auto)'}  universes={univs}  (restart to apply)")
    def _refresh_patch_table(self):
        """Rebuild the rows in the patch table from the current patch state."""
        try:
            dpg.delete_item("patch_table", children_only=True, slot=1)
        except Exception:
            return
        for master in self._patch.all_fixtures():
            first_sub = next(iter(master.sub_fixtures.values()), None)
            if not first_sub or not first_sub.outputs:
                continue
            primary = first_sub.outputs[0]
            total_ch = master.profile.total_channels
            end_addr = primary["address"] + total_ch - 1
            with dpg.table_row(parent="patch_table"):
                dpg.add_text(str(master.fixture_id))
                dpg.add_text(master.name)
                dpg.add_text(master.profile.name)
                dpg.add_text(str(primary["universe"]))
                dpg.add_text(str(primary["address"]))
                dpg.add_text(str(total_ch))
                dpg.add_text(str(end_addr))
                dpg.add_button(label="remove", width=70,
                               callback=self._on_patch_remove,
                               user_data=master.fixture_id)
    def _on_patch_add(self):
        try:
            fid        = dpg.get_value("patch_add_id")
            name       = dpg.get_value("patch_add_name").strip() or f"Fixture {fid}"
            profile    = dpg.get_value("patch_add_profile")
            universe   = dpg.get_value("patch_add_univ")
            addr       = dpg.get_value("patch_add_addr")
            clone_src  = dpg.get_value("patch_add_clone_src")
        except Exception:
            return
        if fid in self._patch.fixtures:
            self._log(f"fixture {fid} already patched — remove it first")
            return
        master = self._patch.patch_fixture(fid, name, profile, universe, addr)
        if master:
            self._log(f"patched: {master.name} (id {fid}) — {profile} u{universe}@{addr}")
            if clone_src and clone_src != 0 and clone_src in self._patch.fixtures:
                msg = self._cmd(f"CLONE {clone_src} TO {fid}") if self._cmd else ""
                if msg:
                    self._log(msg)
            elif clone_src and clone_src != 0:
                self._log(f"  clone src {clone_src} not in patch — skipped")
            self._refresh_patch_table()
        else:
            self._log(f"failed to patch — check profile name '{profile}'")
    def _on_patch_remove(self, _sender, _app_data, user_data):
        fid = int(user_data)
        if fid in self._patch.fixtures:
            name = self._patch.fixtures[fid].name
            del self._patch.fixtures[fid]
            # Clear any programmer data for this fixture
            fid_str = str(fid)
            self._prog.data.pop(fid_str, None)
            keys_to_del = [k for k in self._prog.data if k.startswith(fid_str + '.')]
            for k in keys_to_del:
                del self._prog.data[k]
            self._log(f"removed: {name} (id {fid})")
            self._refresh_patch_table()
    def _on_patch_save(self):
        if self._save_patch:
            self._save_patch()
            self._log("> patch saved to patch.json")
        else:
            self._log("> no save_patch_fn wired")
    def _on_midi_port_connect(self):
        """Switch the MIDI input port to the one selected in the combo."""
        try:
            port_name = dpg.get_value("midi_port_combo")
        except Exception:
            return
        if not port_name:
            return
        if self._midi:
            self._midi.stop()
            self._midi.start(port_name)
        try:
            dpg.set_value("midi_port_status", f"→ {port_name}")
            dpg.configure_item("midi_port_status", color=_C_ACCENT)
        except Exception:
            pass
    def _on_midi_port_disconnect(self):
        """Close the current MIDI port without opening a new one."""
        if self._midi:
            self._midi.stop()
        try:
            dpg.set_value("midi_port_status", "disconnected")
            dpg.configure_item("midi_port_status", color=_C_DIM)
        except Exception:
            pass
    def _on_direct_add(self):
        """Add a CC or Note mapping directly from typed channel/number inputs."""
        try:
            ch   = int(dpg.get_value("direct_ch"))
            num  = int(dpg.get_value("direct_num"))
            kind = dpg.get_value("direct_type_radio")  # "CC" or "Note"
            target_name = dpg.get_value("direct_target")
        except Exception:
            return
        if not target_name or target_name not in self.target_registry:
            try:
                dpg.set_value("direct_status", "pick target")
            except Exception:
                pass
            return
        entry  = self.target_registry[target_name]
        cb     = entry[0]
        soft   = entry[1]
        off_cb = entry[3] if len(entry) > 3 else None
        if kind == "cc":
            self._midi.map_cc(ch, num, cb, name=target_name, soft_takeover=soft)
            label = f"cc{num}"
        else:
            self._midi.map_note(ch, num, cb, off_cb, name=target_name)
            label = f"note{num}"
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()
        try:
            dpg.set_value("direct_status", f"ch{ch} {label} → {target_name}")
        except Exception:
            pass
    def _on_learn_type_change(self, sender, value):
        self._learn_type = 'cc' if value == 'cc' else 'note'
    def _toggle_learn(self):
        if self._learn_armed:
            # already armed — cancel
            self._learn_armed = False
            self._midi.cancel_learn()
            dpg.set_item_label("learn_btn", "learn")
            dpg.set_value("learn_status", "cancelled")
            return
        target_name = dpg.get_value("learn_target")
        if not target_name or target_name not in self.target_registry:
            dpg.set_value("learn_status", "← pick target first")
            return
        self._learn_target = target_name
        self._learn_armed  = True
        type_str = dpg.get_value("learn_type_radio")
        self._learn_type = 'cc' if type_str == 'cc' else 'note'
        self._learn_armed_type = self._learn_type
        wait_label = "CC knob/fader" if self._learn_type == 'cc' else "key or pad"
        dpg.set_value("learn_status", f"waiting for {wait_label}...")
        dpg.set_item_label("learn_btn", "cancel")
        self._midi.start_learn(self._learn_type, self._on_learn_captured)
    def _start_go_cue_learn(self):
        # GUIEngine (the final composed class) isn't importable at module
        # level here — this mixin module loads before studio_project.py
        # finishes assembling it. Deferred import, same pattern used
        # throughout this split.
        from __main__ import GUIEngine
        try:
            stk_n  = int(dpg.get_value("midi_go_cs"))
            cue_n = float(dpg.get_value("midi_go_cue"))
        except Exception:
            return
        name = f"GO stk {stk_n} CUE {int(cue_n)}"
        cmd  = f"GO stk {stk_n} CUE {cue_n}"
        cb   = (lambda c=cmd: self._cmd(c)) if self._cmd else (lambda: None)
        GUIEngine.target_registry[name] = (cb, False, True)
        # Arm learn as a note targeting this dynamic entry
        self._learn_target     = name
        self._learn_armed      = True
        self._learn_armed_type = 'note'
        self._midi.start_learn('note', self._on_go_cue_captured)
        dpg.set_value("go_cue_status", f"waiting for note → {name}...")
    def _start_exec_flash_learn(self):
        """
        Learn a note for 'fdr <n> Flash' — live only while the pad is held.
        Unlike _start_go_cue_learn (GO-only, no release action), this needs
        an off_callback, so it delegates to the general _on_learn_captured
        handler (which already reads entry[3] as off_cb) instead of a
        bespoke capture handler.
        """
        # Deferred import — see _start_go_cue_learn above for rationale.
        from __main__ import GUIEngine
        try:
            ex_n = int(dpg.get_value("midi_flash_exec"))
        except Exception:
            return
        name    = f"fader {ex_n} Flash"
        on_cmd  = f"FADER {ex_n} flash on"
        off_cmd = f"FADER {ex_n} flash off"
        on_cb   = (lambda c=on_cmd:  self._cmd(c)) if self._cmd else (lambda: None)
        off_cb  = (lambda c=off_cmd: self._cmd(c)) if self._cmd else (lambda: None)
        GUIEngine.target_registry[name] = (on_cb, False, True, off_cb)
        self._learn_target     = name
        self._learn_armed      = True
        self._learn_armed_type = 'note'
        self._midi.start_learn('note', self._on_learn_captured)
        dpg.set_value("flash_learn_status", f"waiting for note → {name}...")
    def _start_exec_gb_learn(self):
        """
        Learn a note for 'fdr <n> GO' or 'fdr <n> BACK' — steps that
        specific fader's stack forward/back on press. Unlike the
        fixed "GO"/"BACK" targets in target_registry (which always act on
        whichever fader is currently active via STACK <n>), and unlike
        _start_go_cue_learn (which jumps straight to one cue number), this
        drives an arbitrary fader's normal GO/BACK — the MIDI-side
        equivalent of what /gma3/key/<page>/<fdr>/go already does over OSC.
        """
        # Deferred import — see _start_go_cue_learn above for rationale.
        from __main__ import GUIEngine
        try:
            ex_n = int(dpg.get_value("midi_exec_gb_num"))
        except Exception:
            return
        verb = dpg.get_value("midi_exec_gb_type")  # 'go' or 'back'
        name = f"fdr {ex_n} {verb}"
        cmd  = f"fdr {ex_n} {verb.upper()}"
        cb   = (lambda c=cmd: self._cmd(c)) if self._cmd else (lambda: None)
        GUIEngine.target_registry[name] = (cb, False, True)
        self._learn_target     = name
        self._learn_armed      = True
        self._learn_armed_type = 'note'
        self._midi.start_learn('note', self._on_learn_captured)
        dpg.set_value("midi_exec_gb_status", f"waiting for note → {name}...")
    def _on_go_cue_captured(self, ch, number):
        """MIDI-thread callback for GO stk+CUE note learn."""
        # Deferred import — see _start_go_cue_learn above for rationale.
        from __main__ import GUIEngine
        name = self._learn_target
        self._learn_armed = False
        entry = GUIEngine.target_registry.get(name)
        if entry:
            self._midi.map_note(ch, number, entry[0], name=name)
        dpg.set_value("go_cue_status", f"ch{ch} note{number} → {name}")
        try:
            dpg.set_item_label("learn_btn", "learn")
        except Exception:
            pass
        self._pending_table_refresh = True
    def _on_learn_captured(self, ch, number):
        """Called from MIDI thread when a CC/note is received during learn.
        NOTE: self._learn_type is already None here (cleared by MIDIEngine
        before firing the callback), so we use self._learn_armed_type instead.
        Table rebuild is deferred to the main-thread update loop via a flag
        because DearPyGui item creation/deletion must happen on the main thread.
        """
        armed_type  = self._learn_armed_type   # 'cc' or 'note', still valid
        target_name = self._learn_target
        self._learn_armed = False

        entry = self.target_registry.get(target_name)
        if entry is None:
            dpg.set_value("learn_status", "target gone?")
            return

        cb, soft_takeover = entry[0], entry[1]
        off_cb = entry[3] if len(entry) > 3 else None
        if armed_type == 'cc':
            self._midi.map_cc(ch, number, cb,
                              name=target_name, soft_takeover=soft_takeover)
            type_label = "cc"
        else:
            self._midi.map_note(ch, number, cb, off_cb, name=target_name)
            type_label = "note"

        # set_value is thread-safe; item rebuild deferred to main thread
        dpg.set_value("learn_status",
                      f"CH{ch} {type_label}{number} → {target_name}")
        try:
            dpg.set_item_label("learn_btn", "learn")
        except Exception:
            pass
        self._pending_table_refresh = True
    def _remove_cc_map(self, ch, cc):
        self._midi.cc_maps.pop((ch, cc), None)
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()
    def _remove_note_map(self, ch, note):
        self._midi.note_maps.pop((ch, note), None)
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()
    def _on_midi_row_select_reassign(self, sender, app_data, user_data):
        """Mark a mapping row for reassignment and update the reassign UI."""
        kind, ch, num, current_name = user_data
        self._reassign_pending = {'type': kind, 'ch': ch, 'num': num}
        label = f"ch{ch} {'cc' if kind == 'cc' else 'note'}{num}  ({current_name})"
        try:
            dpg.set_value("rsn_selected", label)
            dpg.configure_item("rsn_selected", color=_C_ACCENT)
            if current_name in self.target_registry:
                dpg.set_value("rsn_target", current_name)
        except Exception:
            pass
    def _on_apply_reassign(self):
        """Apply the pending reassignment from rsn_target combo."""
        p = self._reassign_pending
        if p is None:
            return
        new_name = dpg.get_value("rsn_target")
        if not new_name or new_name not in self.target_registry:
            return
        entry   = self.target_registry[new_name]
        cb      = entry[0]
        off_cb  = entry[3] if len(entry) > 3 else None
        soft    = entry[1]
        ch, num = p['ch'], p['num']
        if p['type'] == 'cc':
            self._midi.map_cc(ch, num, cb, name=new_name, soft_takeover=soft)
        else:
            self._midi.map_note(ch, num, cb, off_cb, name=new_name)
        ShowFile.save_midi(self._midi)
        self._reassign_pending = None
        try:
            dpg.set_value("rsn_selected", "select a row →")
            dpg.configure_item("rsn_selected", color=_C_DIM)
        except Exception:
            pass
        self._refresh_midi_table()
    def _reassign_cc_map(self, ch, cc, new_target):
        """Reassign an existing CC mapping to a different target by name."""
        if new_target not in self.target_registry:
            return
        entry  = self.target_registry[new_target]
        cb, soft = entry[0], entry[1]
        self._midi.map_cc(ch, cc, cb, name=new_target, soft_takeover=soft)
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()
    def _reassign_note_map(self, ch, note, new_target):
        """Reassign an existing Note mapping to a different target by name."""
        if new_target not in self.target_registry:
            return
        entry  = self.target_registry[new_target]
        cb     = entry[0]
        off_cb = entry[3] if len(entry) > 3 else None
        self._midi.map_note(ch, note, cb, off_cb, name=new_target)
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()
    def _refresh_midi_table(self):
        """Rebuild the MIDI mapping table rows from current mappings."""
        # Delete existing rows
        for tag in list(self._map_rows.values()):
            try:
                dpg.delete_item(tag)
            except Exception:
                pass
        self._map_rows.clear()

        for (ch, cc), m in list(self._midi.cc_maps.items()):
            row_tag = f"mr_cc_{ch}_{cc}"
            self._map_rows[('cc', ch, cc)] = row_tag
            status = "live" if m.taken_over else "◐ takeover"
            with dpg.table_row(tag=row_tag, parent="midi_table"):
                dpg.add_text(str(ch))
                dpg.add_text(str(cc))
                dpg.add_text("cc", color=_C_ACCENT)
                dpg.add_text(m.name, tag=f"mr_name_cc_{ch}_{cc}")
                dpg.add_text(status, tag=f"mr_st_cc_{ch}_{cc}",
                             color=_C_TEXT if m.taken_over else _C_DIM)
                dpg.add_button(label="del",
                               callback=lambda s, a, u: self._remove_cc_map(*u),
                               user_data=(ch, cc), width=34)
                dpg.add_button(label="►",
                               callback=self._on_midi_row_select_reassign,
                               user_data=('cc', ch, cc, m.name), width=34)

        for (ch, note), m in list(self._midi.note_maps.items()):
            row_tag = f"mr_note_{ch}_{note}"
            self._map_rows[('note', ch, note)] = row_tag
            with dpg.table_row(tag=row_tag, parent="midi_table"):
                dpg.add_text(str(ch))
                dpg.add_text(str(note))
                dpg.add_text("note", color=_C_P_BEAM)
                dpg.add_text(m.name, tag=f"mr_name_note_{ch}_{note}")
                dpg.add_text("—")
                dpg.add_button(label="del",
                               callback=lambda s, a, u: self._remove_note_map(*u),
                               user_data=(ch, note), width=34)
                dpg.add_button(label="►",
                               callback=self._on_midi_row_select_reassign,
                               user_data=('note', ch, note, m.name), width=34)
