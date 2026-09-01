"""GUIEngine's stage visualizer panel (per-fixture RGB+dim preview grid).

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

import math

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.models.fixtures import MasterFixture


class GUIEngineStage:
    @staticmethod
    def _best_sub_layout(pixel_count, slot_w, sub_h):
        """Return (rows, cols, dot_size) maximising dot size for given slot dimensions."""
        import math
        if pixel_count <= 1:
            return 1, 1, int(min(slot_w, sub_h))
        sq = int(math.sqrt(pixel_count))
        while sq > 0 and pixel_count % sq != 0:
            sq -= 1
        if sq == 0:
            sq = 1
        ra, ca = sq, pixel_count // sq          # landscape candidate
        rb, cb = ca, ra                          # portrait candidate
        # dot_s = stride including 1px gap; maximise min of both axes
        dot_a = min(slot_w / ca, sub_h / ra)
        dot_b = min(slot_w / cb, sub_h / rb)
        if dot_b >= dot_a:
            rows, cols, dot_f = rb, cb, dot_b
        else:
            rows, cols, dot_f = ra, ca, dot_a
        return rows, cols, max(1, int(dot_f) - 1)
    def _build_stage_panel(self):
        """Inline stage view — third column in the main row, fills remaining width."""
        vp_w      = getattr(self, '_vp_w', self._W)
        canvas_w  = max(200, vp_w - self._W_LEFT - self._W_RIGHT - 16)
        canvas_h  = self._H_MAIN - 42   # _H_MAIN minus master-fader row and padding
        with dpg.child_window(tag="stage_win", width=-1, height=self._H_MAIN,
                              border=True, no_scrollbar=True,
                              no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text("master", color=_C_ACCENT)
                dpg.add_slider_int(
                    tag="stage_master_fader",
                    default_value=100, min_value=0, max_value=100,
                    format="%d%%", width=-1,
                    callback=lambda s, a, u: (
                        setattr(self._out, 'master_level', a / 100.0)
                        if self._out else None
                    ),
                )
            with dpg.drawlist(tag="stage_canvas", width=canvas_w, height=canvas_h):
                fixtures = list(self._patch.all_fixtures())
                for i, master in enumerate(fixtures):
                    dpg.draw_rectangle(
                        pmin=(0, 0), pmax=(1, 1),
                        tag=f"stage_rect_{i}",
                        fill=(18, 13, 40, 255),
                        color=(55, 38, 105, 255),
                        thickness=1,
                        rounding=4,
                    )
                    dpg.draw_text(
                        pos=(0, 0), tag=f"stage_lbl_{i}",
                        text="", color=_C_TEXT, size=12,
                    )
                    dpg.draw_text(
                        pos=(0, 0), tag=f"stage_dim_{i}",
                        text="", color=_C_DIM, size=11,
                    )
                    for j in range(len(master.sub_fixtures)):
                        dpg.draw_rectangle(
                            pmin=(0, 0), pmax=(1, 1),
                            tag=f"stage_sub_{i}_{j}",
                            fill=(8, 6, 18, 255),
                            color=(0, 0, 0, 0), thickness=0,
                        )
    def _tick_stage(self):
        """Recompute fixture colours from output state and update stage canvas.
        All geometry is computed here from the actual canvas size so the layout
        scales automatically when the window is resized.
        First, clamp the drawlist to the real visible stage window so fixture
        slots never run past the right edge (fixes last fixture being clipped)."""
        try:
            sw = dpg.get_item_rect_size("stage_win")            # visible column
            rect = dpg.get_item_rect_size("stage_canvas")       # configured drawlist
            if sw and sw[0] > 20 and sw[0] != rect[0]:
                # Clamp only the WIDTH to the real visible column so the rightmost
                # fixture is never clipped; keep the canvas height as configured.
                dpg.configure_item("stage_canvas", width=sw[0])
                rect = (sw[0], rect[1])
            w, h = rect[0], rect[1]
        except Exception:
            return
        if w < 20 or h < 20:
            return
        fixtures = list(self._patch.all_fixtures())
        n = len(fixtures)
        if not n:
            return

        cue_merged = self._out._merged_cue_layer() if self._out else {}
        gm = self._out.master_level if self._out else 1.0

        # Layout constants
        gap    = 10
        mh     = 50                    # master bar height
        sub_y0 = gap + mh + 10        # top of sub-pixel region
        sub_h  = h - sub_y0 - gap     # vertical space for sub-pixel grid
        tw     = (w - gap * (n + 1)) / n   # width slot per fixture

        for i, master in enumerate(fixtures):
            x0  = gap + i * (tw + gap)
            x1  = x0 + tw
            fid = str(master.fixture_id)

            # --- Master bar colour (sampled from first sub-fixture) ---
            r = g = b = 0
            dim = master.virtual_dimmer   # default before output engine query
            if self._out:
                first_sub = next(iter(master.sub_fixtures.values()), None)
                if first_sub:
                    sfid   = str(first_sub.fixture_id)
                    prog_s = self._out.programmer_layer.get(sfid, {})
                    cue_s  = cue_merged.get(sfid, {})
                    fx_s   = self._out.fx_layer.get(sfid, {})
                    base_r = prog_s.get('red',   cue_s.get('red',   0))
                    base_g = prog_s.get('green', cue_s.get('green', 0))
                    base_b = prog_s.get('blue',  cue_s.get('blue',  0))
                    # Envelope-blended merge (matches get_dmx_for_universe)
                    if 'red' in fx_s:
                        env_r = fx_s.get('_env_red', 1.0)
                        r = max(0, min(255, int(base_r * (1.0 - env_r) + fx_s['red'])))
                    else:
                        r = int(base_r)
                    if 'green' in fx_s:
                        env_g = fx_s.get('_env_green', 1.0)
                        g = max(0, min(255, int(base_g * (1.0 - env_g) + fx_s['green'])))
                    else:
                        g = int(base_g)
                    if 'blue' in fx_s:
                        env_b = fx_s.get('_env_blue', 1.0)
                        b = max(0, min(255, int(base_b * (1.0 - env_b) + fx_s['blue'])))
                    else:
                        b = int(base_b)
                    mp  = self._out.programmer_layer.get(fid, {})
                    mc  = cue_merged.get(fid, {})
                    fxm = self._out.fx_layer.get(fid, {})
                    fdr = fxm.get('dim')
                    # pixel-scope dim FX lives under the sub fixture ID, not master
                    if fdr is None:
                        fdr = fx_s.get('dim')
                    ron = any(fx_s.get(f'_env_{c}', 0.0) > 0.001
                              for c in ('red', 'green', 'blue'))
                    if fdr is not None:
                        dim = max(0.0, min(1.0, mp.get('dim', mc.get('dim', master.virtual_dimmer)) * (fdr / 255.0)))
                    elif ron:
                        cd  = mc.get('dim')
                        dim = mp.get('dim', cd if cd is not None else 1.0)
                    else:
                        dim = mp.get('dim', mc.get('dim', master.virtual_dimmer))
                    r = max(0, min(255, int(r * dim * gm)))
                    g = max(0, min(255, int(g * dim * gm)))
                    b = max(0, min(255, int(b * dim * gm)))
            hl_active = (self._out and self._out.highlight_mode and
                         (master.fixture_id in self._out.highlight_fids
                          or any(str(s.fixture_id) in self._out.highlight_fids
                                 for s in master.all_subs())))
            if hl_active:
                fill = (255, 255, 255, 255)
            elif r or g or b:
                fill = (r, g, b, 255)
            elif dim > 0:
                grey = max(0, min(255, int(dim * gm * 200)))
                fill = (grey, grey, grey, 255)
            else:
                fill = (18, 13, 40, 255)
            sel_masters = {f.fixture_id for f in self._prog.selection
                           if isinstance(f, MasterFixture)}
            border_col = (162, 115, 255, 255) if master.fixture_id in sel_masters else (55, 38, 105, 255)
            dim_pct = int(dim * gm * 100)
            dim_col = _C_TEXT if dim_pct > 0 else _C_DIM
            try:
                dpg.configure_item(f"stage_rect_{i}", pmin=(x0, gap), pmax=(x1, gap + mh),
                                   fill=fill, color=border_col, thickness=2, rounding=4)
                dpg.configure_item(f"stage_lbl_{i}",  pos=(x0 + 4, gap + 6),  text=master.name[:10])
                dpg.configure_item(f"stage_dim_{i}",  pos=(x0 + 4, gap + 28),
                                   text=f"{dim_pct}%", color=dim_col)
            except Exception:
                pass

            # --- Sub-pixel dots — auto-pick orientation that maximises dot size ---
            if not self._out or sub_h < 2:
                continue
            subs = list(master.sub_fixtures.values())
            pc   = len(subs)
            rows, cols, dot = self._best_sub_layout(pc, tw, sub_h)
            dot_s = dot + 1   # stride = dot + 1px gap

            for j, sub in enumerate(subs):
                row  = j // cols
                col  = j % cols
                sx0  = x0 + col * dot_s
                sy0  = sub_y0 + row * dot_s
                sfid = str(sub.fixture_id)
                ps   = self._out.programmer_layer.get(sfid, {})
                stk   = cue_merged.get(sfid, {})
                fs   = self._out.fx_layer.get(sfid, {})
                br   = ps.get('red',   stk.get('red',   0))
                bg2  = ps.get('green', stk.get('green', 0))
                bb   = ps.get('blue',  stk.get('blue',  0))
                # Envelope-blended merge (matches get_dmx_for_universe)
                if 'red' in fs:
                    env_r = fs.get('_env_red', 1.0)
                    sr = max(0, min(255, int(int(br) * (1.0 - env_r) + fs['red'])))
                else:
                    sr = int(br)
                if 'green' in fs:
                    env_g = fs.get('_env_green', 1.0)
                    sg = max(0, min(255, int(int(bg2) * (1.0 - env_g) + fs['green'])))
                else:
                    sg = int(bg2)
                if 'blue' in fs:
                    env_b = fs.get('_env_blue', 1.0)
                    sb2 = max(0, min(255, int(int(bb) * (1.0 - env_b) + fs['blue'])))
                else:
                    sb2 = int(bb)
                mp   = self._out.programmer_layer.get(fid, {})
                mc   = cue_merged.get(fid, {})
                fxm  = self._out.fx_layer.get(fid, {})
                fdr  = fxm.get('dim')
                # pixel-scope dim FX lives under the sub fixture ID, not master
                if fdr is None:
                    fdr = fs.get('dim')
                ron  = any(fs.get(f'_env_{c}', 0.0) > 0.001 for c in ('red', 'green', 'blue'))
                if fdr is not None:
                    sdim = max(0.0, min(1.0, mp.get('dim', mc.get('dim', master.virtual_dimmer)) * (fdr / 255.0)))
                elif ron:
                    cd   = mc.get('dim')
                    sdim = mp.get('dim', cd if cd is not None else 1.0)
                else:
                    sdim = mp.get('dim', mc.get('dim', master.virtual_dimmer))
                sr  = max(0, min(255, int(sr  * sdim * gm)))
                sg  = max(0, min(255, int(sg  * sdim * gm)))
                sb2 = max(0, min(255, int(sb2 * sdim * gm)))
                if hl_active:
                    sfill = (255, 255, 255, 255)
                elif sr or sg or sb2:
                    sfill = (sr, sg, sb2, 255)
                elif sdim > 0:
                    sgrey = max(0, min(255, int(sdim * gm * 200)))
                    sfill = (sgrey, sgrey, sgrey, 255)
                else:
                    sfill = (16, 11, 36, 255)
                try:
                    dpg.configure_item(f"stage_sub_{i}_{j}",
                                       pmin=(sx0, sy0), pmax=(sx0 + dot, sy0 + dot),
                                       fill=sfill)
                except Exception:
                    pass
    def _on_fixture_dim_slider(self, _sender, value, user_data):
        """Write dim directly into programmer layer without changing fixture selection."""
        fid    = int(user_data)
        dim    = max(0.0, min(1.0, float(value)))
        fid_s  = str(fid)
        if self._out:
            self._out.programmer_layer.setdefault(fid_s, {})['dim'] = dim
        if self._patch and fid in self._patch.fixtures:
            # MasterFixture.set_dimmer() takes a 0.0-1.0 fraction (see its
            # own docstring) -- dim is already that fraction. A stray "* 100"
            # here meant any drag above ~1% clamped virtual_dimmer to 1.0
            # (max(0.0, min(1.0, dim*100)) == 1.0 for basically all inputs).
            # programmer.set_dimmer() and the AI dim action both pass the
            # already-normalized fraction straight through; match that.
            self._patch.fixtures[fid].set_dimmer(dim)
    def _on_fixture_dim_select_all(self):
        """Select all fixtures in the programmer."""
        if self._cmd and self._patch:
            fids = sorted(m.fixture_id for m in self._patch.all_fixtures())
            if fids:
                self._cmd(f"{fids[0]} THRU {fids[-1]}")
    def _on_fixture_chip_click(self, sender, app_data, user_data):
        """Click a fixture chip in the status bar to select it (Shift+click to add)."""
        fid = int(user_data)
        if not self._patch or fid not in self._patch.fixtures:
            return
        master = self._patch.fixtures[fid]
        shift = (dpg.is_key_down(dpg.mvKey_LShift) or
                 dpg.is_key_down(dpg.mvKey_RShift))
        if shift and self._prog:
            cur = [f for f in self._prog.selection if isinstance(f, MasterFixture)]
            if master in cur:
                cur.remove(master)
            else:
                cur.append(master)
            self._prog.select(cur)
            sel_str = " ".join(str(m.fixture_id) for m in cur) or "none"
            self._log(f"> SELECT {sel_str}")
        else:
            if self._cmd:
                self._cmd(str(fid))
