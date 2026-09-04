"""GUIEngine's 3D rig visualizer — an old-school vector-arcade wireframe
view (Battlezone/Tron style) of the live rig, driven by real fixture
output. Positions come from VIZ POSITION (commands/patch.py) or an
auto-arranged fallback; colour/brightness come from
gui/stage.py's _compute_sub_rgb_dim() (shared, not re-derived here).
Per-pixel fixtures (pixel_count > 1) get a real grid of pixel dots on
their front face, laid out via the same VIZ LAYOUT override / auto
best-fit algorithm gui/stage.py's 2D dot grid uses (GUIEngineStage's
_best_sub_layout/_explicit_grid_layout — reused directly since both
mixins compose into the same GUIEngine class). A 1-pixel fixture with
pan/tilt (a mover) gets a beam line instead, showing live pan/tilt
direction — stylised (DMX 0-255 mapped straight to a sweep angle, no
per-profile range calibration), not physically exact.

Interactive controls, all scoped to hovering viz3d_canvas at the moment
the button goes down (same is_item_hovered-gated pattern
left_column.py's stage-canvas click handling already uses):
  - Left-click-drag a fixture: moves it along its current height plane
    (x/z only), writing straight into MasterFixture.viz_position — same
    effect as VIZ POSITION, just interactive. Uses _viz3d_unproject_to_ground,
    the algebraic inverse of _viz3d_project's yaw+pitch rotation. A plain
    2D mouse position only disambiguates two axes at once, so the third
    (height) needs a modifier instead of a plane intersection:
      - Shift-drag: adjusts height (world y) via vertical mouse delta
        from the press point, x/z held at whatever they currently are.
    Toggling the modifier mid-drag composes rather than resets, since
    each mode only ever touches its own axis/axes off the live current
    value.
  - Right-click-drag: manually orbits the camera — horizontal mouse
    delta orbits (as before), vertical mouse delta tilts the camera up/
    down (clamped so it can't flip past looking straight up or down).
    Both ride the same drag rather than needing a second modifier, same
    as any standard 3D viewer's orbit+tilt control. Both fixture
    rotation axes live on this SAME button too, gated by a modifier —
    each only takes over when a fixture is actually under the cursor at
    press time; elsewhere on the canvas it's always the plain camera
    orbit+tilt above:
      - Ctrl+right-drag on a fixture: rotates its YAW (spin left/right
        around the vertical axis) via horizontal mouse delta.
      - Alt+right-drag on a fixture: rotates its PITCH (nose up/down —
        tilting the housing itself) via vertical mouse delta.
  - "pause orbit" button: stops the automatic "attract mode" spin without
    affecting manual dragging.
Pitch is a fixture's own placement property (how it's physically
mounted — e.g. a truss par angled down at the stage), stored in
viz_position alongside x/y/z/yaw and rendered as an actual tilt of its
wireframe housing/pixel grid — distinct from a mover's live pan/tilt
beam (driven by real DMX output, see below), which composes with this
static mount pitch rather than replacing it.
The camera's orbit angle (_viz3d_orbit_angle) and pitch (_viz3d_cam_pitch)
are both accumulators, advanced/adjusted each tick rather than derived
straight from time.monotonic() like the first version's orbit angle,
since that can't be paused or offset by a drag.

This is a stylised spatial read for the operator and a target surface
for the AI to arrange (VIZ POSITION is in the AI's command reference),
not a WYSIWYG/photoreal capture — DearPyGui has no true 3D scene graph
in practical use here, so this is a hand-rolled perspective projection
drawn with plain 2D drawlist primitives (draw_line), the same technique
vector arcade games used.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

import math
import time

from studio_console.gui.theme import *  # noqa: F401,F403


class GUIEngineViz3D:
    _VIZ3D_GRID_N       = 10     # grid lines each direction, from -N to +N
    # Units are feet — one grid square is 1x1ft, and the marker cube
    # (half-size 0.5) is exactly a 1x1x1ft box, so a fixture's cube in
    # this view is literally "one grid square tall/wide". Chosen so
    # VIZ POSITION coordinates map onto a real, checkable measurement
    # rather than an arbitrary scale (documented for the AI too — see
    # command_reference.py's "3D viz coordinate system" entry).
    _VIZ3D_GRID_SPACING = 1.0    # feet between grid lines
    _VIZ3D_CAM_DIST     = 16.0   # camera orbit radius, feet
    _VIZ3D_CAM_HEIGHT   = 6.0    # camera height above the ground plane
    _VIZ3D_CAM_PITCH    = 0.30   # radians, initial downward tilt (adjustable via right-drag)
    _VIZ3D_CAM_PITCH_MIN = math.radians(-15)   # slightly looking up
    _VIZ3D_CAM_PITCH_MAX = math.radians(80)    # nearly straight down — stops short of gimbal flip
    _VIZ3D_CAM_PERIOD   = 40.0   # seconds per full auto orbit — slow "attract mode"
    _VIZ3D_ORBIT_DRAG_SENSITIVITY = 0.006   # radians of orbit per screen pixel dragged (horizontal)
    _VIZ3D_PITCH_DRAG_SENSITIVITY = 0.006   # radians of pitch per screen pixel dragged (vertical)
    _VIZ3D_FOV          = 50.0   # degrees, vertical field of view
    _VIZ3D_MARKER       = 0.5    # half-size of each fixture's wireframe cube
    _VIZ3D_BEAM_LEN_FACTOR = 3.0 # mover beam length, as a multiple of _VIZ3D_MARKER
    _VIZ3D_DRAG_HIT_PX  = 30     # click-drag hit radius around a fixture's screen anchor
    _VIZ3D_HEIGHT_DRAG_SENSITIVITY = 0.02   # feet of height per pixel of Shift-drag
    _VIZ3D_YAW_DRAG_SENSITIVITY    = 0.5    # degrees of yaw per pixel of Ctrl-drag
    _VIZ3D_FIXTURE_PITCH_DRAG_SENSITIVITY = 0.5   # degrees of fixture pitch per pixel of Alt+right-drag
    _VIZ3D_FIXTURE_PITCH_MIN = -90.0   # degrees — straight up
    _VIZ3D_FIXTURE_PITCH_MAX = 90.0    # degrees — straight down
    _VIZ3D_GRID_COLOR       = (90,  66, 168, 130)
    _VIZ3D_GRID_COLOR_FAR   = (90,  66, 168, 40)
    _VIZ3D_MARKER_OFF_COLOR = (100, 78, 190, 255)   # dim violet — unlit fixture, still visible
    _VIZ3D_BEAM_OFF_COLOR   = (150, 140, 255, 160)  # dim beam when the mover has no colour output
    _VIZ3D_LABEL_COLOR      = (150, 130, 210, 220)

    def _on_viz3d_toggle(self):
        try:
            if dpg.is_item_shown("viz3d_window"):
                self._save_popup_layout()
                dpg.hide_item("viz3d_window")
            else:
                dpg.show_item("viz3d_window")
        except Exception:
            pass

    def _on_viz3d_orbit_pause_toggle(self):
        self._viz3d_orbit_paused = not self._viz3d_orbit_paused
        try:
            dpg.set_item_label("viz3d_pause_btn",
                               "resume orbit" if self._viz3d_orbit_paused else "pause orbit")
        except Exception:
            pass

    def _build_viz3d_popup(self):
        """Floating 3D viz window. All draw primitives (ground grid, one
        wireframe cube per patched fixture, one dot per pixel for any
        fixture with more than one, one beam line per 1-pixel mover) are
        created once here with fixed tags and repositioned every tick in
        _tick_viz3d() — same reconfigure-in-place pattern gui/stage.py
        already uses, since DPG drawlist items are cheap to move but not
        to recreate every frame."""
        # Per-instance interaction state, initialized here (build() runs
        # once before the tick loop starts) rather than in an __init__ —
        # this mixin has no __init__ of its own, GUIEngineCore's is the
        # only one in the composed class (see studio_project.py).
        self._viz3d_orbit_angle          = 0.0
        self._viz3d_cam_pitch            = self._VIZ3D_CAM_PITCH
        self._viz3d_orbit_paused         = False
        self._viz3d_orbit_dragging       = False
        self._viz3d_orbit_drag_start_x   = 0.0
        self._viz3d_orbit_drag_start_y   = 0.0
        self._viz3d_orbit_drag_start_angle = 0.0
        self._viz3d_orbit_drag_start_pitch = 0.0
        self._viz3d_last_tick_t          = None
        self._viz3d_drag_fid             = None
        self._viz3d_drag_start_y         = 0.0
        self._viz3d_drag_start_my        = 0.0
        # Right-click fixture rotation (Ctrl=yaw, Alt=pitch) — one shared
        # set of state since only one mode can be active per drag.
        self._viz3d_rotate_fid           = None
        self._viz3d_rotate_mode          = None   # 'yaw' or 'pitch'
        self._viz3d_rotate_start_yaw     = 0.0
        self._viz3d_rotate_start_pitch   = 0.0
        self._viz3d_rotate_start_mx      = 0.0
        self._viz3d_rotate_start_my      = 0.0
        self._viz3d_screen_pos           = {}   # {fixture_id: (screen_x, screen_y)} — refreshed every tick

        fixtures = list(self._patch.all_fixtures())
        with dpg.window(tag="viz3d_window", label="3d viz", width=900, height=680,
                        show=False, pos=(10, 10), no_collapse=False):
            dpg.add_button(label="pause orbit", tag="viz3d_pause_btn", width=110,
                           callback=self._on_viz3d_orbit_pause_toggle)
            dpg.add_text("rig viz — glow = live RGB output, dim wire = unlit  "
                         "(1 grid square = 1ft. drag=move, shift-drag=height. "
                         "right-drag=orbit+tilt, ctrl+right-drag on a fixture=yaw, "
                         "alt+right-drag on a fixture=pitch)",
                         color=_C_DIM, tag="viz3d_help_text", wrap=880)
            with dpg.drawlist(tag="viz3d_canvas", width=880, height=640):
                dpg.draw_rectangle((0, 0), (880, 640), fill=_C_BG, color=(0, 0, 0, 0),
                                   tag="viz3d_bg")
                # Ground grid — 2*(2N+1) lines, fixed count regardless of patch.
                n = self._VIZ3D_GRID_N
                for i in range(2 * n + 1):
                    dpg.draw_line((0, 0), (0, 0), color=self._VIZ3D_GRID_COLOR,
                                  thickness=1, tag=f"viz3d_grid_x_{i}")
                    dpg.draw_line((0, 0), (0, 0), color=self._VIZ3D_GRID_COLOR,
                                  thickness=1, tag=f"viz3d_grid_z_{i}")
                # One wireframe cube (12 edges) + one label per fixture,
                # plus one pixel dot per sub-fixture for a multi-pixel
                # fixture, or one beam line for a 1-pixel mover.
                for i, m in enumerate(fixtures):
                    for e in range(12):
                        dpg.draw_line((0, 0), (0, 0), color=self._VIZ3D_MARKER_OFF_COLOR,
                                      thickness=2, tag=f"viz3d_edge_{i}_{e}")
                    dpg.draw_text((0, 0), "", color=self._VIZ3D_LABEL_COLOR,
                                  size=13, tag=f"viz3d_label_{i}")
                    if m.pixel_count > 1:
                        for j in range(m.pixel_count):
                            dpg.draw_rectangle((0, 0), (0, 0),
                                               fill=self._VIZ3D_MARKER_OFF_COLOR,
                                               color=(0, 0, 0, 0),
                                               tag=f"viz3d_pixel_{i}_{j}")
                    elif m.profile.is_moving():
                        dpg.draw_line((0, 0), (0, 0), color=self._VIZ3D_BEAM_OFF_COLOR,
                                      thickness=2, tag=f"viz3d_beam_{i}")

    # ------------------------------------------------------------
    # Mouse handlers — registered from gui/core.py's build(), same
    # dpg.handler_registry() block the existing global click handlers
    # use (see left_column.py's _on_global_mouse_click/_on_global_right_click
    # for the proven is_item_hovered + get_mouse_pos(local=False) pattern
    # this mirrors).
    # ------------------------------------------------------------

    def _on_viz3d_left_down(self, sender, app_data):
        if app_data != 0:   # 0 = left button
            return
        try:
            if not dpg.is_item_hovered("viz3d_canvas"):
                return
            mouse = dpg.get_mouse_pos(local=False)
            canvas_min = dpg.get_item_rect_min("viz3d_canvas")
        except Exception:
            return
        mx, my = mouse[0] - canvas_min[0], mouse[1] - canvas_min[1]
        best_fid, best_d2 = None, self._VIZ3D_DRAG_HIT_PX ** 2
        for fid, (sx, sy) in self._viz3d_screen_pos.items():
            d2 = (mx - sx) ** 2 + (my - sy) ** 2
            if d2 < best_d2:
                best_fid, best_d2 = fid, d2
        self._viz3d_drag_fid = best_fid
        if best_fid is not None:
            # Anchor for Shift-drag's height mode, which works off a
            # vertical mouse delta from the press point, so it needs the
            # fixture's height at press time, not just the current frame's.
            master = self._patch.get(best_fid)
            pos = getattr(master, 'viz_position', None) if master else None
            self._viz3d_drag_start_y  = pos['y'] if pos else self._VIZ3D_MARKER
            self._viz3d_drag_start_my = my

    def _on_viz3d_left_up(self, sender, app_data):
        if app_data != 0:
            return
        if self._viz3d_drag_fid is not None:
            self._viz3d_drag_fid = None
            try:
                if self._save:
                    self._save()
            except Exception:
                pass

    def _on_viz3d_right_down(self, sender, app_data):
        if app_data != 1:   # 1 = right button
            return
        try:
            if not dpg.is_item_hovered("viz3d_canvas"):
                return
            mouse = dpg.get_mouse_pos(local=False)
            canvas_min = dpg.get_item_rect_min("viz3d_canvas")
        except Exception:
            return

        # Ctrl+right-drag or Alt+right-drag over a fixture rotates its
        # yaw or pitch instead of orbiting the camera. Only takes over
        # when a fixture is actually under the cursor; otherwise falls
        # through to the normal camera orbit+tilt below, same as a plain
        # right-drag anywhere else on the canvas. If both are somehow
        # held, Ctrl (yaw) wins — an arbitrary but harmless tie-break.
        ctrl = (dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
                or dpg.is_key_down(dpg.mvKey_ModSuper))
        alt  = dpg.is_key_down(dpg.mvKey_LAlt) or dpg.is_key_down(dpg.mvKey_RAlt)
        if ctrl or alt:
            mx, my = mouse[0] - canvas_min[0], mouse[1] - canvas_min[1]
            best_fid, best_d2 = None, self._VIZ3D_DRAG_HIT_PX ** 2
            for fid, (sx, sy) in self._viz3d_screen_pos.items():
                d2 = (mx - sx) ** 2 + (my - sy) ** 2
                if d2 < best_d2:
                    best_fid, best_d2 = fid, d2
            if best_fid is not None:
                master = self._patch.get(best_fid)
                eff = next((p for p in self._viz3d_fixture_positions() if p[0] is master), None)
                self._viz3d_rotate_fid = best_fid
                self._viz3d_rotate_mode = 'yaw' if ctrl else 'pitch'
                self._viz3d_rotate_start_yaw   = math.degrees(eff[4]) if eff else 0.0
                self._viz3d_rotate_start_pitch = math.degrees(eff[5]) if eff else 0.0
                self._viz3d_rotate_start_mx = mouse[0]
                self._viz3d_rotate_start_my = mouse[1]
                return   # don't also start a camera orbit on this press

        self._viz3d_orbit_dragging = True
        self._viz3d_orbit_drag_start_x = mouse[0]
        self._viz3d_orbit_drag_start_y = mouse[1]
        self._viz3d_orbit_drag_start_angle = self._viz3d_orbit_angle
        self._viz3d_orbit_drag_start_pitch = self._viz3d_cam_pitch

    def _on_viz3d_right_up(self, sender, app_data):
        if app_data != 1:
            return
        if self._viz3d_rotate_fid is not None:
            self._viz3d_rotate_fid = None
            self._viz3d_rotate_mode = None
            try:
                if self._save:
                    self._save()
            except Exception:
                pass
        self._viz3d_orbit_dragging = False

    # ------------------------------------------------------------
    # Projection
    # ------------------------------------------------------------

    def _viz3d_camera_pose(self):
        """Camera position + facing yaw for "now" — slow auto-orbit
        around the scene's centre (average of all fixture x/z
        positions, or the origin if there are none/no overrides).
        Orbit angle is an accumulator advanced in _tick_viz3d(), not
        derived straight from wall-clock time, so it can be paused or
        manually dragged without a discontinuous jump."""
        fixtures = self._viz3d_fixture_positions()
        if fixtures:
            cx0 = sum(p[1] for p in fixtures) / len(fixtures)
            cz0 = sum(p[3] for p in fixtures) / len(fixtures)
        else:
            cx0 = cz0 = 0.0
        orbit = self._viz3d_orbit_angle
        cam_x = cx0 + self._VIZ3D_CAM_DIST * math.sin(orbit)
        cam_z = cz0 + self._VIZ3D_CAM_DIST * math.cos(orbit)
        cam_y = self._VIZ3D_CAM_HEIGHT
        # Yaw that points the camera back at the centre.
        yaw = math.atan2(cx0 - cam_x, cz0 - cam_z)
        return cam_x, cam_y, cam_z, yaw, self._viz3d_cam_pitch

    def _viz3d_project(self, wx, wy, wz, cam, focal, screen_cx, screen_cy):
        """World point -> (screen_x, screen_y, depth) or None if behind
        the camera. Hand-rolled perspective projection: translate to
        camera space, rotate by yaw (around Y) then pitch (around the
        camera's local X), then divide by depth."""
        cx, cy, cz, yaw, pitch = cam
        dx, dy, dz = wx - cx, wy - cy, wz - cz
        # Yaw: rotate into the camera's forward/right frame.
        rx =  dx * math.cos(yaw) - dz * math.sin(yaw)
        rz =  dx * math.sin(yaw) + dz * math.cos(yaw)
        ry = dy
        # Pitch: tilt forward/up around the camera's right axis.
        ry2 = ry * math.cos(pitch) + rz * math.sin(pitch)
        rz2 = -ry * math.sin(pitch) + rz * math.cos(pitch)
        if rz2 <= 0.5:
            return None  # behind (or right on top of) the camera
        sx = screen_cx + (rx / rz2) * focal
        sy = screen_cy - (ry2 / rz2) * focal
        return sx, sy, rz2

    def _viz3d_unproject_to_ground(self, sx, sy, cam, focal, screen_cx, screen_cy, plane_y):
        """Inverse of _viz3d_project, constrained to the horizontal
        plane y=plane_y — the exact algebraic inverse of the yaw+pitch
        rotation used there (verified by round-trip: project then
        unproject at the same plane_y recovers the original x,z to
        within float error, checked across 200 randomized camera/point
        trials before wiring this into the drag handler). Used for
        click-drag fixture placement: cast a ray from the camera through
        the mouse's screen position and find where it crosses the
        fixture's current height, so dragging moves it along its own
        plane rather than toward/away from the camera. Returns None if
        the ray is parallel to the plane or the plane is behind the
        camera along it (dragging to an unreachable screen position)."""
        cam_x, cam_y, cam_z, yaw, pitch = cam
        kx = (sx - screen_cx) / focal
        ky = (screen_cy - sy) / focal
        ry = ky * math.cos(pitch) - math.sin(pitch)
        rz = ky * math.sin(pitch) + math.cos(pitch)
        rx = kx
        dx = rx * math.cos(yaw) + rz * math.sin(yaw)
        dz = -rx * math.sin(yaw) + rz * math.cos(yaw)
        dy = ry
        if abs(dy) < 1e-6:
            return None
        t = (plane_y - cam_y) / dy
        if t <= 0:
            return None
        return cam_x + t * dx, cam_z + t * dz

    def _viz3d_local_to_world(self, fx, fy, fz, cos_y, sin_y, cos_p, sin_p, lx, ly, lz):
        """One point in a fixture's own local space (lx,ly,lz) -> world
        space, applying the fixture's placement pitch (rotation around
        its own local X — nose up/down) THEN yaw (rotation around world
        Y — spin left/right), then translating to its position. Shared
        by the cube-corner and pixel-grid transforms below so pitch
        composes with yaw identically in both — a fixture's housing and
        its pixel grid should tilt together, not separately."""
        ly1 = ly * cos_p - lz * sin_p
        lz1 = ly * sin_p + lz * cos_p
        wx = fx + (lx * cos_y - lz1 * sin_y)
        wz = fz + (lx * sin_y + lz1 * cos_y)
        wy = fy + ly1
        return wx, wy, wz

    def _viz3d_fixture_positions(self):
        """Every patched master's (fixture, x, y, z, yaw, pitch) in feet/
        radians. Uses viz_position when set; otherwise auto-arranges in
        a line along x at ground level (z=0), 2.5ft apart centre-to-
        centre (1.5ft of clear space either side of each 1x1ft cube),
        ordered by patch id — same "sensible default, explicit override
        wins" shape as VIZ LAYOUT. pitch is a placement property (how
        the fixture is physically mounted — a truss par angled down at
        the stage, say), separate from a mover's live pan/tilt beam."""
        fixtures = list(self._patch.all_fixtures())
        n = len(fixtures)
        out = []
        for i, m in enumerate(fixtures):
            pos = getattr(m, 'viz_position', None)
            if pos:
                out.append((m, pos['x'], pos['y'], pos['z'],
                            math.radians(pos.get('yaw', 0.0)),
                            math.radians(pos.get('pitch', 0.0))))
            else:
                x = (i - (n - 1) / 2.0) * 2.5
                out.append((m, x, self._VIZ3D_MARKER, 0.0, 0.0, 0.0))
        return out

    def _viz3d_pixel_grid(self, master):
        """(rows, cols, order) for this fixture's pixel grid — reuses
        GUIEngineStage's own layout algorithm (VIZ LAYOUT override, else
        auto best-fit) so the 3D view's pixel arrangement matches the 2D
        stage view's exactly, not a second guess. Passed a square (1,1)
        slot since the 3D panel this maps onto (the cube's front face)
        is square — stage.py's own slot_w/sub_h only affect the returned
        dot *size*, which is ignored here (the 3D tick computes its own
        perspective-scaled screen size from world-space stride)."""
        pc = master.pixel_count
        layout = getattr(master, 'viz_layout', None)
        if layout and layout.get('cols') and layout.get('rows'):
            rows, cols, _ = self._explicit_grid_layout(layout['cols'], layout['rows'], pc, 1.0, 1.0)
            order = layout.get('order', 'rowmajor')
        else:
            rows, cols, _ = self._best_sub_layout(pc, 1.0, 1.0)
            order = 'rowmajor'
        return rows, cols, order

    # ------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------

    def _tick_viz3d(self):
        if not dpg.is_item_shown("viz3d_window"):
            return
        # Resize the canvas (and the help text's wrap width) to fill
        # whatever the floating window's current size is — same
        # resize-to-fit idea as gui/stage.py's _tick_stage(), just
        # tracking both dimensions since this is a free-floating,
        # user-resizable window rather than a fixed-height panel
        # embedded in the main layout.
        try:
            win_size = dpg.get_item_rect_size("viz3d_window")
        except Exception:
            win_size = None
        if win_size and win_size[0] > 40 and win_size[1] > 80:
            target_w = max(200, int(win_size[0]) - 20)
            target_h = max(150, int(win_size[1]) - 60)
            try:
                cur = dpg.get_item_rect_size("viz3d_canvas")
                if abs(cur[0] - target_w) > 1 or abs(cur[1] - target_h) > 1:
                    dpg.configure_item("viz3d_canvas", width=target_w, height=target_h)
                dpg.configure_item("viz3d_help_text", wrap=target_w)
            except Exception:
                pass
        try:
            rect = dpg.get_item_rect_size("viz3d_canvas")
            w, h = rect[0], rect[1]
        except Exception:
            return
        if w < 20 or h < 20:
            return
        try:
            dpg.configure_item("viz3d_bg", pmin=(0, 0), pmax=(w, h))
        except Exception:
            pass

        # ---- advance (or hold) the camera orbit ----
        now = time.monotonic()
        last = self._viz3d_last_tick_t
        self._viz3d_last_tick_t = now
        if self._viz3d_orbit_dragging:
            try:
                if dpg.is_mouse_button_down(dpg.mvMouseButton_Right):
                    mouse = dpg.get_mouse_pos(local=False)
                    ddx = mouse[0] - self._viz3d_orbit_drag_start_x
                    ddy = mouse[1] - self._viz3d_orbit_drag_start_y
                    self._viz3d_orbit_angle = (self._viz3d_orbit_drag_start_angle
                                               + ddx * self._VIZ3D_ORBIT_DRAG_SENSITIVITY)
                    new_pitch = (self._viz3d_orbit_drag_start_pitch
                                 + ddy * self._VIZ3D_PITCH_DRAG_SENSITIVITY)
                    self._viz3d_cam_pitch = max(self._VIZ3D_CAM_PITCH_MIN,
                                                min(self._VIZ3D_CAM_PITCH_MAX, new_pitch))
                else:
                    # Button released without the up-event reaching us
                    # (e.g. released outside the canvas) — stop dragging
                    # rather than orbiting forever.
                    self._viz3d_orbit_dragging = False
            except Exception:
                pass
        elif not self._viz3d_orbit_paused and last is not None:
            dt = max(0.0, min(0.25, now - last))  # clamp so a long-hidden window doesn't jump on reshow
            self._viz3d_orbit_angle += dt * (2.0 * math.pi / self._VIZ3D_CAM_PERIOD)

        # ---- apply an in-progress Ctrl/Alt+right-drag fixture rotation ----
        if self._viz3d_rotate_fid is not None:
            if dpg.is_mouse_button_down(dpg.mvMouseButton_Right):
                try:
                    mouse = dpg.get_mouse_pos(local=False)
                except Exception:
                    mouse = None
                master = self._patch.get(self._viz3d_rotate_fid)
                if mouse is not None and master is not None:
                    eff = next((p for p in self._viz3d_fixture_positions() if p[0] is master), None)
                    if eff:
                        cx, cy, cz = eff[1], eff[2], eff[3]
                        cyaw, cpitch = math.degrees(eff[4]), math.degrees(eff[5])
                    else:
                        cx, cy, cz, cyaw, cpitch = 0.0, self._VIZ3D_MARKER, 0.0, 0.0, 0.0
                    if self._viz3d_rotate_mode == 'yaw':
                        dx_screen = mouse[0] - self._viz3d_rotate_start_mx
                        cyaw = (self._viz3d_rotate_start_yaw
                                + dx_screen * self._VIZ3D_YAW_DRAG_SENSITIVITY) % 360.0
                        cyaw = round(cyaw, 1)
                    else:   # 'pitch'
                        dy_screen = mouse[1] - self._viz3d_rotate_start_my
                        new_pitch = (self._viz3d_rotate_start_pitch
                                     + dy_screen * self._VIZ3D_FIXTURE_PITCH_DRAG_SENSITIVITY)
                        cpitch = round(max(self._VIZ3D_FIXTURE_PITCH_MIN,
                                           min(self._VIZ3D_FIXTURE_PITCH_MAX, new_pitch)), 1)
                    master.viz_position = {"x": cx, "y": cy, "z": cz, "yaw": cyaw, "pitch": cpitch}
            else:
                # Same released-outside-canvas safety net as the other drags.
                self._viz3d_rotate_fid = None
                self._viz3d_rotate_mode = None
                try:
                    if self._save:
                        self._save()
                except Exception:
                    pass

        cam = self._viz3d_camera_pose()
        screen_cx, screen_cy = w / 2.0, h / 2.0
        focal = (h / 2.0) / math.tan(math.radians(self._VIZ3D_FOV) / 2.0)

        def proj(wx, wy, wz):
            return self._viz3d_project(wx, wy, wz, cam, focal, screen_cx, screen_cy)

        # ---- apply an in-progress fixture drag before laying out this frame ----
        # Plain drag moves along the floor plane (x/z, height fixed) —
        # the two axes a straight 2D mouse position maps onto without
        # ambiguity. The third axis needs a modifier to disambiguate
        # which 1D mouse motion (dx or dy from the press point) it means:
        #   Shift-drag  -> height (world y): vertical mouse delta
        #   Ctrl-drag   -> yaw rotation:      horizontal mouse delta
        # Each mode leaves the OTHER axes at whatever they currently are
        # (not reset to the drag-start values), so toggling the modifier
        # mid-drag composes naturally instead of undoing prior motion.
        if self._viz3d_drag_fid is not None:
            if dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
                try:
                    mouse = dpg.get_mouse_pos(local=False)
                    canvas_min = dpg.get_item_rect_min("viz3d_canvas")
                    mx, my = mouse[0] - canvas_min[0], mouse[1] - canvas_min[1]
                except Exception:
                    mx = my = None
                master = self._patch.get(self._viz3d_drag_fid)
                if mx is not None and master is not None:
                    # Look up the fixture's CURRENT effective position —
                    # not just its viz_position (None for a fixture still
                    # auto-arranged, i.e. never dragged/VIZ POSITION'd
                    # before). Falling back to a hardcoded (0,0,0) there
                    # would snap it away from its real auto-arranged spot
                    # the instant a shift-drag (which must preserve the
                    # other axes, unlike the plain floor-drag branch
                    # below, which always computes x/z fresh) touched it.
                    eff = next((p for p in self._viz3d_fixture_positions() if p[0] is master), None)
                    if eff:
                        _, cur_x, cur_y, cur_z, cur_yaw_rad, cur_pitch_rad = eff
                        cur_yaw   = math.degrees(cur_yaw_rad)
                        cur_pitch = math.degrees(cur_pitch_rad)
                    else:
                        cur_x = cur_y = cur_z = cur_yaw = cur_pitch = 0.0
                    shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)
                    if shift:
                        dy_screen = self._viz3d_drag_start_my - my   # mouse up = higher
                        new_y = max(0.05, self._viz3d_drag_start_y
                                    + dy_screen * self._VIZ3D_HEIGHT_DRAG_SENSITIVITY)
                        master.viz_position = {"x": cur_x, "y": round(new_y, 3), "z": cur_z,
                                               "yaw": cur_yaw, "pitch": cur_pitch}
                    else:
                        hit = self._viz3d_unproject_to_ground(mx, my, cam, focal, screen_cx, screen_cy, cur_y)
                        if hit:
                            wx, wz = hit
                            master.viz_position = {"x": round(wx, 3), "y": cur_y, "z": round(wz, 3),
                                                   "yaw": cur_yaw, "pitch": cur_pitch}
            else:
                # Same released-outside-canvas safety net as the orbit drag.
                self._viz3d_drag_fid = None
                try:
                    if self._save:
                        self._save()
                except Exception:
                    pass

        # ---- ground grid ----
        n = self._VIZ3D_GRID_N
        sp = self._VIZ3D_GRID_SPACING
        span = n * sp
        for i in range(2 * n + 1):
            gx = -span + i * sp
            p1 = proj(gx, 0.0, -span)
            p2 = proj(gx, 0.0,  span)
            try:
                if p1 and p2:
                    dpg.configure_item(f"viz3d_grid_x_{i}", p1=p1[:2], p2=p2[:2],
                                       show=True)
                else:
                    dpg.configure_item(f"viz3d_grid_x_{i}", show=False)
            except Exception:
                pass
            gz = -span + i * sp
            p1 = proj(-span, 0.0, gz)
            p2 = proj( span, 0.0, gz)
            try:
                if p1 and p2:
                    dpg.configure_item(f"viz3d_grid_z_{i}", p1=p1[:2], p2=p2[:2],
                                       show=True)
                else:
                    dpg.configure_item(f"viz3d_grid_z_{i}", show=False)
            except Exception:
                pass

        # ---- fixtures: one wireframe cube each, coloured by live output;
        #      multi-pixel fixtures also get a grid of pixel dots on their
        #      front face; 1-pixel movers get a beam instead ----
        cue_merged = self._out._merged_cue_layer() if self._out else {}
        gm = self._out.master_level if self._out else 1.0
        hs = self._VIZ3D_MARKER
        self._viz3d_screen_pos = {}

        for i, (master, fx, fy, fz, fyaw, fpitch) in enumerate(self._viz3d_fixture_positions()):
            cos_y, sin_y = math.cos(fyaw), math.sin(fyaw)
            cos_p, sin_p = math.cos(fpitch), math.sin(fpitch)
            multi_pixel = master.pixel_count > 1

            center_p = proj(fx, fy, fz)
            if center_p:
                self._viz3d_screen_pos[master.fixture_id] = (center_p[0], center_p[1])

            # Housing wireframe colour: for a 1-pixel fixture (a mover)
            # the cube IS the only output, so it carries the live colour
            # like before; for a multi-pixel fixture the pixel dots below
            # carry the real colour, so the housing stays a plain dim
            # outline rather than competing with/averaging over them.
            color = self._VIZ3D_MARKER_OFF_COLOR
            if not multi_pixel and self._out:
                first_sub = next(iter(master.sub_fixtures.values()), None)
                if first_sub:
                    r, g, b, _dim = self._compute_sub_rgb_dim(master, first_sub, cue_merged, gm)
                    if r or g or b:
                        color = (r, g, b, 255)

            # 8 cube corners in the fixture's own local space, then
            # pitch + yaw + translate into world space.
            corners = []
            for lx in (-hs, hs):
                for ly in (-hs, hs):
                    for lz in (-hs, hs):
                        wx, wy, wz = self._viz3d_local_to_world(
                            fx, fy, fz, cos_y, sin_y, cos_p, sin_p, lx, ly, lz)
                        corners.append(proj(wx, wy, wz))

            # Corner order above is binary-counted (lx,ly,lz), so edges
            # connect indices that differ in exactly one bit.
            edges = []
            for a in range(8):
                for bit in (1, 2, 4):
                    b_idx = a ^ bit
                    if b_idx > a:
                        edges.append((a, b_idx))

            any_visible = False
            for e, (a, b_idx) in enumerate(edges):
                p1, p2 = corners[a], corners[b_idx]
                try:
                    if p1 and p2:
                        dpg.configure_item(f"viz3d_edge_{i}_{e}", p1=p1[:2], p2=p2[:2],
                                           color=color, show=True)
                        any_visible = True
                    else:
                        dpg.configure_item(f"viz3d_edge_{i}_{e}", show=False)
                except Exception:
                    pass

            if multi_pixel:
                subs = master.all_subs()
                rows, cols, order = self._viz3d_pixel_grid(master)
                stride_x = (2 * hs) / cols
                stride_y = (2 * hs) / rows
                half_world = min(stride_x, stride_y) * 0.42
                for j, sub in enumerate(subs):
                    if order == 'colmajor':
                        col, row = j // rows, j % rows
                    else:
                        row, col = j // cols, j % cols
                    lx = -hs + (col + 0.5) * stride_x
                    ly =  hs - (row + 0.5) * stride_y   # row 0 at top
                    lz = hs + 0.02   # just proud of the front face
                    wx, wy, wz = self._viz3d_local_to_world(
                        fx, fy, fz, cos_y, sin_y, cos_p, sin_p, lx, ly, lz)
                    p = proj(wx, wy, wz)
                    tag = f"viz3d_pixel_{i}_{j}"
                    try:
                        if p:
                            sx, sy, depth = p
                            hr = max(1.5, half_world * focal / depth)
                            r, g, b, _pd = self._compute_sub_rgb_dim(master, sub, cue_merged, gm)
                            pcolor = (r, g, b, 255) if (r or g or b) else self._VIZ3D_MARKER_OFF_COLOR
                            dpg.configure_item(tag, pmin=(sx - hr, sy - hr), pmax=(sx + hr, sy + hr),
                                               fill=pcolor, show=True)
                        else:
                            dpg.configure_item(tag, show=False)
                    except Exception:
                        pass

            elif master.profile.is_moving():
                # Stylised beam direction from live pan/tilt — DMX 0-255
                # mapped straight to a sweep angle (pan: full 360 degrees,
                # tilt: -90..+90 from level), not calibrated per profile's
                # real physical range. Programmer wins over cue, same
                # precedent as _tick_output_monitor's own attr merge.
                # Composes with the fixture's own placement pitch (how
                # it's physically mounted) rather than ignoring it — a
                # fixture installed angled down should show its beam
                # angled down even at a level (centred) tilt channel.
                # tilt_angle's "positive = up" and fpitch's "positive =
                # down" are opposite sign conventions, hence the minus.
                sub_fid = f"{master.fixture_id}.1"
                pl = self._out.programmer_layer.get(sub_fid, {}) if self._out else {}
                cm = cue_merged.get(sub_fid, {})
                merged = {**cm, **pl}
                pan_frac  = max(0.0, min(1.0, merged.get('pan', 127.5) / 255.0))
                tilt_frac = max(0.0, min(1.0, merged.get('tilt', 127.5) / 255.0))
                pan_angle  = pan_frac * 2.0 * math.pi
                tilt_angle = (tilt_frac - 0.5) * math.pi - fpitch
                beam_yaw = fyaw + pan_angle
                cos_b, sin_b = math.cos(beam_yaw), math.sin(beam_yaw)
                dir_y = math.sin(tilt_angle)
                dir_z = math.cos(tilt_angle)
                beam_len = hs * self._VIZ3D_BEAM_LEN_FACTOR
                ex = fx + beam_len * (0.0 * cos_b - dir_z * sin_b)
                ez = fz + beam_len * (0.0 * sin_b + dir_z * cos_b)
                ey = fy + beam_len * dir_y
                p1 = proj(fx, fy, fz)
                p2 = proj(ex, ey, ez)
                beam_color = color if color != self._VIZ3D_MARKER_OFF_COLOR else self._VIZ3D_BEAM_OFF_COLOR
                try:
                    if p1 and p2:
                        dpg.configure_item(f"viz3d_beam_{i}", p1=p1[:2], p2=p2[:2],
                                           color=beam_color, show=True)
                    else:
                        dpg.configure_item(f"viz3d_beam_{i}", show=False)
                except Exception:
                    pass

            top_center = proj(fx, fy + hs, fz)
            try:
                if any_visible and top_center:
                    dpg.configure_item(f"viz3d_label_{i}",
                                       pos=(top_center[0] - 10, top_center[1] - 18),
                                       text=master.name[:12], show=True)
                else:
                    dpg.configure_item(f"viz3d_label_{i}", show=False)
            except Exception:
                pass
