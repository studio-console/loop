# Studio Console — Current State

**Date:** 2026-10-14
**Version:** v0.22
**Smoke test:** 496/496 PASS
**Branch:** main, up to date with origin/main

---

## What's working

- Full MA2/MA3-style fader page: 10 slots per page, cue list + thin fader side-by-side, priority badge (hi/nrm/lo), output-mode badge (nrm/moment/vfade)
- Faders: 0–255 integer resolution, dynamic resize with window
- Output modes: normal, moment (active only while level > 0), vfade (fader crossfades between two cues)
- Trigger modes: toggle, flash, moment (fade out on release via off_time)
- Priority: hi/nrm/lo — controls LTP merge order
- FX engine: sine/ramp/square/pulse/triangle/sawtooth/flicker waveforms, per-channel per-fixture
- Speed master: 16-slot BPM presets, MIDI-mappable
- Full attribute channel support: pan/tilt/gobo/zoom/focus/iris/strobe
- Moving light profiles (Generic_Moving, Generic_Moving_Wash)
- MIDI CC/note mapping (live, no code changes needed)
- OSC input: MA3-compatible `/gma3/fader/...` routes
- sACN output: single explicit FX driver — `NetworkEngine`'s 100Hz staging thread is the only thread calling `FXEngine.compute_merged()`, so nothing contends for `FXEngine._lock` on the pre-send critical path. Packets leave the wire at a true 44Hz (`fps=44`, set on `sACNsender()`; the sacn library's own UDP thread paces transmission and previously defaulted to 30Hz). The staging loop is paced by `time.perf_counter()` deadlines so it holds ~100Hz under jitter. The socket binds to the physical ethernet IP **and** pins multicast egress to it via `IP_MULTICAST_IF` (`_pin_multicast_egress()`), so on a Mac with WiFi as the default route the sACN multicast actually leaves the lighting NIC instead of WiFi. A rolling-shutter phase-offset slider in the patch window drives `network.set_shutter_delay_ms()` (clamped to one wire frame); the value is stored/staged but not yet applied to wire timing (needs the deferred manual-flush scheduler — see below)
- Audio-reactive framework (infrastructure): pitch→MIDI bridge, key→colour mapper, sub-harmonic strobe engine — modules wired idle, tick/command wiring pending
- Audio routing matrix: `AUDIO ROUTE` commands + the Audio Control & Routing window — band-level thresholds (`level`/`low`/`mid`/`high`) that fire any registered console target, with rising-edge-only firing and an off-callback released once the band re-arms. Live 4-band level meter with threshold markers, add/remove route table. Persists to `audio_routes.json`
- AI engine integration
- Save/load show, backup, named saves in `studio_saves/`
- Commands are case-insensitive (`stk`, `STK`, `fdr`, `FDR` all work)
- Codebase is now a package (`studio_console/`) instead of one 21k-line file — same behavior, verified against the smoke test at every step (see below)
- The same smoke test also runs under pytest (`pytest` from the project root) with per-check pass/fail, `-k` filtering, JUnit XML — alongside, not instead of, the original `STUDIO_HEADLESS` oracle. Both report 496 checks

## Recent changes

1. **sACN: pin multicast egress to the lighting NIC, perf_counter-paced staging loop, rolling-shutter delay slider** (2026-10-14):
   - **App would not start (fixed):** `studio_project.py` had lost its `class GUIEngine(...)` mixin definition, the `from studio_console.gui.theme import *` import, and `from studio_console.commands import run_command` — an incomplete prior-session refactor. Also imported `studio_console.gui.audio_levels` (module + `GUIEngineAudioLevels` mixin) that was never created, though it was already referenced by `audio_monitors.py` (`_build_audio_levels_panel()`, the nestable device + raw-peak panel), `core.py` (`_tick_audio_levels`), and full smoke/pytest coverage. Recreated `gui/audio_levels.py` to that spec and restored the class/imports, so the console builds and the whole suite runs again (496/496 via both `STUDIO_HEADLESS` and pytest).
   - **Multicast egress was leaving the wrong interface.** `bind_address` threaded into `sACNsender` binds the UDP *source* IP, but that does **not** control multicast egress: the sacn library leaves `IP_MULTICAST_IF = 0.0.0.0`, so the kernel picks the egress NIC from the routing table. On this Mac Mini the default route is `en1` (WiFi) while the lighting LAN is `en0` (Ethernet 192.168.1.161), and `224.0.0/4` exists on both — so sACN multicast could leave over WiFi even with the socket bound to the wired IP. `NetworkEngine._pin_multicast_egress()` now sets `IP_MULTICAST_IF` to the bind address (verified against a live bound socket: `0.0.0.0` → `192.168.1.161`).
   - **Staging loop now deadline-paced by `time.perf_counter()`** (was `time.monotonic()` + a flat `sleep(interval)`, which drifted well under 100Hz when a tick overran). `_run()` targets `next_tick` and sleeps only the remainder, re-arming from `perf_counter()` each tick and catching up after an overrun. Pure timing refinement — a long tick still skips ahead instead of compounding drift.
   - **Rolling-shutter phase-offset slider** added to the patch window's sACN network section, wired live to the new `NetworkEngine.set_shutter_delay_ms()`, which clamps to `[0, 1000/SACN_FPS]` (one wire frame ≈ 22.7ms) and rejects non-numeric input. Deliberately **not** applied to wire timing yet: the sacn sender still auto-flushes on its own thread, so honoring the offset requires the deferred manual-flush scheduler (`manual_flush=True` + per-universe `send_out(out, t)`, proven callable against the installed library) — left for a live camera test per user direction.
   - 496/496 via both oracles (4 new `set_shutter_delay_ms` clamp/reject checks added to both), plus `py_compile` and a real non-headless boot (launches the GUI and blocks with no errors).

2. **sACN output pipeline: single explicit FX driver + true 44Hz wire cadence** (2026-10-12, commit f3dc09c):
   - Two independent defects were costing send-time precision on the DMX line. Neither was visible in the smoke test — both are timing/concurrency properties of live output, and the headless suite exercises the compute path without ever opening a socket.
   - **Removed duplicate thread lock contention.** `FXEngine.__init__` unconditionally started its own 44Hz thread calling `compute_merged()`, while `NetworkEngine._run` independently called the same method at 100Hz. Every FX layer was therefore evaluated twice per wire frame by two threads contending for `FXEngine._lock` — a lock the sACN staging thread needs on its critical path immediately before each send, so losing that race delayed the send by however long the redundant evaluation took. That is the send-time jitter a strobe rig feels.
   - `FXEngine` now starts **no thread on construction**. `compute_merged()` has exactly one driver, selected explicitly: `claim_external_driver()` (called by `NetworkEngine.start()`; idempotent, never joins from the loop's own thread), `start_background_loop()` (the fallback, only when nothing else ticks FX — without it envelopes/outfades would never advance), and `stop()` delegating to the claim so either path shuts down cleanly.
   - Edge case handled: `NetworkEngine.start()`'s existing "sACN port busy" branch returns early without starting a staging loop. Harmless before, but under the single-driver rule it would have frozen FX permanently — that branch now calls `start_background_loop()`.
   - **Activated a true 44Hz wire cadence (`fps=44`).** The class docstring claimed 44Hz and the staging loop ran at 100Hz, but neither sets the wire rate: transmission is paced by the sacn library's own internal UDP sender thread at `1/fps`, and that library defaults `fps` to **30** — never overridden here. The rig had been transmitting at 30Hz regardless of anything this codebase did. `fps=44` is now passed explicitly to both `sACNsender()` constructions, confirmed against the installed library (22.73ms socket interval vs 33.33ms when omitted).
   - The 100Hz staging loop is unchanged in behavior and kept deliberately faster than the wire rate — it stages `dmx_data` into the sender's buffers, so a strobe phase boundary is picked up within ~10ms rather than waiting up to a full 22ms wire frame. Both rates are now named constants (`SACN_FPS`, `STAGING_HZ`) instead of inline literals, making the compute-vs-transmit distinction explicit rather than being the thing that hid the 30Hz bug.
   - Also: `NetworkEngine.stop()` now joins the staging thread (bounded, 1s) and clears the handle instead of just flipping a flag; both background threads are named (`sacn-staging`, `fx-engine-tick`) for debuggability.
   - **`self.phase_delay_ms = 0.0` is active inside `NetworkEngine`** as the placeholder variable hook for the upcoming per-universe phase-offset UI slider. It is deliberately **not applied**: packet timing lives in the sacn library's own UDP sender thread, so true camera phase matching will require scheduling shifts inside that underlying library's thread rather than in our staging loop — applying the offset in the staging loop would silently do nothing.
   - 484/484 via both `STUDIO_HEADLESS` and pytest. Also confirmed against real startup wiring that `sacn-staging` is live while the FX fallback thread is `None`, that `stop()` leaves no threads behind, and that the fallback is restartable on demand. **Real-hardware strobe-timing verification is still outstanding** — the headless suite exercises the compute path with no socket and cannot confirm the timing improvement.

2. **Audio routing matrix + AUDIO ROUTE commands; meter tick fix** (2026-10-12, commit 15c9141):
   - New `engine/audio_router.py` — `AudioRouter`: routes keyed by band channel (`level`/`low`/`mid`/`high`) and threshold. Threadless and deterministic (no internal thread, no `tick()` side effects beyond firing), so firing order is reproducible and there is nothing to stop at shutdown. Fires on the rising edge only, and releases an off-callback once the band drops back under threshold. Enabled/route state persists via `ShowFile.save_audio_routes`/`load_audio_routes` → `audio_routes.json`
   - New `gui/audio_routing.py` — Audio Control & Routing window: device pick + master controls, a 4-band level meter with threshold markers, and the routing matrix table with add/remove. Built hidden like the other popups; driven by `GUIEngine._tick()` → `_tick_audio_routing()`
   - `commands/io.py` — `AUDIO ROUTE ADD/LIST/DEL/ON/OFF/THRESHOLD`, validating unknown channel, bad threshold value, and missing target
   - **Fixed a bug that made the meter impossible to render.** `_tick_audio_routing_meter()` repositioned its 12 pre-built draw primitives with `draw_rectangle(tag=...)`/`draw_line(tag=...)` — creation calls, not updates. Outside any enclosing `with dpg.drawlist(...)` and with no `parent=`, DPG 2.3.1 raises `SystemError` *and deregisters the existing item*, so the first tick destroyed the primitives and every later tick failed too. The bare `except Exception: pass` in the tick swallowed it, so the symptom was a permanently blank meter with no error anywhere. Now `configure_item()`, which updates in place and keeps the drawlist at exactly 12 children
   - Two related fixes in the same tick: silent bands kept a stale bar (a fill was only drawn when >1px wide and never cleared — it's now always reconfigured, collapsing to zero when inaudible), and `get_item_rect_size()` returns 0x0 forever in headless mode, making `row_h` a division by zero (now falls back to the drawlist's configured size)
   - Smoke test: 2 checks corrected alongside the bug. The oracle asserted draw items in drawlist **slot 0** — they live in **slot 2**, slot 0 is always empty, so the check could never pass. And it called `_tick_audio_routing()`, which gates its meter half on `is_item_shown("audio_routing_window")` while the popup is built `show=False`, so the meter was never exercised at all. Both oracles now drive `_tick_audio_routing_meter()` directly and assert the primitives were reconfigured off their degenerate `(0,0)-(0,0)` rect rather than merely existing
   - 484/484 via both `STUDIO_HEADLESS` and pytest. Confirmed the new check has teeth: reverting only the meter body to `draw_*` makes it fail again (482/483)

3. **Audio-reactive framework laid down** (2026-10-12):
   - Three new modules, all construct-safe/idle at startup (opt-in, same as audio_engine):
     - `drivers/audio_midi.py` - `AudioMIDIBridge`: unbiased-autocorrelation pitch tracking (first-peak-above-85%-threshold selection rejects sub-harmonic octave errors), hysteresis-cleaned MIDI notes (stability_frames + min_hold + release_after), optional mido out port; pure-math core (`detect_freq`/`freq_to_midi`/`quantize`) testable headless
     - `engine/key_color.py` - `KeyColorMapper`: Krumhansl-Schmuckler key detection over a decaying pitch-class histogram fed by bridge note events; minor->cold (blues/concert) / major->warm (white/amber) palettes in ColorPreset channel format, 3 s crossfade, manual `set_key()` override
     - `engine/subharmonic.py` - `SubHarmonicStrobe`: octave-ladder division of tracked pitch, bass-onset transient detection on the low band, onset->clamped strobe rate (0.5-25 Hz safety band)->sACN `gate_dict()` (audio_layer format) + Resolume OSC (`/resolume/<target>/strobe/{fire,rate,gate}`)
   - `AudioEngine` gained an `on_chunk` hook (raw samples per capture, before band analysis); bridge attaches via `attach(audio_engine)`
   - Wired as idle singletons in `state.py` (`audio_midi`, `key_color`, `strobe_engine`), exported through `studio_project.py`'s state import
   - Not yet ticked/driven anywhere (no command handlers, no GUI panel, no tick wiring) - that's the next phase; smoke test untouched, 460/460 via both STUDIO_HEADLESS and pytest at the time

4. **`tests_smoke.py` ported to pytest** (2026-08-17):
   - New, additive `studio_console/tests/test_smoke_pytest.py` — the same 456 checks, generated by mechanically converting every `_check(label, cond)` into `with subtests.test(msg=label): assert (cond)` (`pytest-subtests`), verified via AST structural comparison against the original (457/457 identical) rather than eyeballed
   - One long test function, not 456 independent ones — the checks are genuinely sequential (each depends on state earlier ones left in `fader_pool`/`patch`/`stack_pool`), so subtests reports each individually without pretending they're isolated
   - `gui` and every singleton come from actually running `studio_project.py` via `runpy.run_path(..., run_name="__main__")` — same construction/wiring as a real launch. Needed one small addition to `studio_project.py`: a `STUDIO_PYTEST_COLLECT` branch that stops right after `gui = GUIEngine(...)`, before the smoke-test/GUI-loop/shutdown tail — existing `STUDIO_HEADLESS` and normal-launch paths verified unchanged (456/456 ×3 before and after)
   - `tests_smoke.py` itself is untouched — stays the oracle
   - Added `pytest.ini` (`testpaths = studio_console/tests`) so bare `pytest` works from the project root; needs `pytest` + `pytest-subtests` installed
   - Verified: 1 passed, 456 subtests passed, ×3, via both `pytest studio_console/tests/test_smoke_pytest.py` and bare `pytest`
   - Pushed to origin

5. **`GUIEngine._tick()` decomposed into 12 sub-tick methods** (2026-08-17):
   - Was 789 lines, the one method the Phase 7 mixin split had left alone (flagged as future work in `CURRENT.md`'s "Known / pending"). Already delegated to `_tick_pools`/`_tick_stage`/`_tick_fader_page`/`_tick_audio`, but ~600 lines of status-bar, cue-list, programmer-monitor, output-monitor, MIDI/OSC, and autosave logic still lived directly in the method body.
   - Split into `_tick_first_sync`, `_tick_deferred_maintenance`, `_tick_prog_live_fades`, `_tick_status_bar`, `_tick_playbacks_and_faders`, `_tick_cue_list`, `_tick_fx_header`, `_tick_programmer_monitor`, `_tick_output_monitor`, `_tick_midi_osc`, `_tick_autosave` — all still on `GUIEngineCore` in `gui/core.py`, called in the exact original order
   - Pure boundary extraction: every new method's body verified byte-identical to its slice of the original `_tick()`, plus `py_compile`, an AST undefined-name pass, and the smoke test at 456/456 ×3
   - Pushed to origin along with the rest of the split (29 commits)

6. **studio_project.py split into the studio_console/ package** (2026-08-13):
   - `studio_project.py`: 21,191 lines → 180-line entry point. Everything else moved into 39 files under `studio_console/`: `models/` (fixture + preset data classes), `engine/` (playback + FX), `drivers/` (network/midi/osc/audio/ai), `gui/` (14 mixin files composing `GUIEngine`), `commands/` (9 category files + dispatcher composing `run_command`), plus `show.py`, `state.py`, `paths.py`, `tests_smoke.py`
   - 11 phases, each its own commit, each independently verified against the smoke test (stayed 456/456 throughout) — zero intended behavior change, though the process did catch and fix several real latent bugs along the way (see commit messages, `git log --oneline` for "Phase N:" subjects)
   - Phases 0/1/3/4/6 (models, drivers, show.py, theme, package skeleton) done via DeepSeek through Continue; phases 2/5/7/8/9/10 (engine, state.py wiring, the 210-method GUIEngine mixin split, the 117-branch run_command split, the entry point) done directly — the latter group all had real cross-reference complexity that made hand-off riskier than tooled in-session extraction
   - Full architecture reference: `CLAUDE.md`'s "Package layout" section. Full design rationale: `~/.claude/plans/glimmering-spinning-moth.md`
   - Goal achieved: an AI session working on one feature area now only needs to load that one file — e.g. the FX editor popup is `gui/fx_editor.py` (~450 lines), not the full codebase
   - Pushed to origin

7. **Project moved into subfolder** (2026-08-12):
   - All files now live in `studio_project/` (was Documents root)
   - Git repo root stays at `/Users/c/Documents`; `.gitignore` updated to match new paths
   - VS Code workspace should be opened at `/Users/c/Documents/studio_project/`
   - Session history for prior work: `~/.claude/projects/-Users-c-Documents/305f777b-...jsonl`

8. **Font set to 17px Avenir** (2026-08-12):
   - `_setup_fonts()`, now in `studio_console/gui/theme.py`: both surface and mono fonts at 17px
   - Previously 13px (DeepSeek), bumped through 14→15→18→17 to find sweet spot

9. **GUI visual polish** (DeepSeek, 2026-08-12):
   - Avenir font throughout, rounded corners (12px panels), deeper violet palette
   - Elevated card panels, inset input wells, STUDIO wordmark in header
   - Forms pool width fix, 6th fixture clipping fix in stage visualiser

10. **stk/fdr rename** (DeepSeek, 2026-08-12):
   - `CS`/`EXEC` removed — now `stk`/`fdr` (or full `stack`/`fader`)
   - Data files: `stacks.json`, `faders.json`, `fader_pages.json`
   - Commits: `e1a2026`, `1b265a2`

11. **CLAUDE.md + CURRENT.md added** for AI handoff efficiency

## Known / pending

- **File split is done** (see Recent changes #6) and pushed to origin
- **`GUIEngine._tick()` decomposed** (see Recent changes #5) — pushed to origin
- **`tests_smoke.py` ported to pytest** (see Recent changes #4) — the previously-deferred item; `tests_smoke.py` itself stays the untouched oracle, `pytest` is now an additional, equally-verified way to run the same 496 checks
- **Real-hardware strobe-timing verification outstanding** (see Recent changes #1) — the f3dc09c sACN fixes (single FX driver, true 44Hz wire rate) are concurrency/timing properties of live output that the headless suite cannot exercise, since it runs the compute path with no socket. Needs a physical run on the rig to confirm the improvement. Same applies to the multicast-egress pin: verified at the socket level (`IP_MULTICAST_IF` moves off `0.0.0.0` onto the wired IP) but not yet confirmed arriving at fixtures.
- **Rolling-shutter `set_shutter_delay_ms()` is wired to its slider but not yet applied to wire timing** (see Recent changes #1) — the setter clamps/stores the value live and the slider reports it, but honoring a per-universe offset requires switching the sacn sender to `manual_flush=True` and driving per-universe `send_out(out, t)` scheduling (proven callable against the installed library). That refactor is deferred until a live camera test shows it is actually needed.
- No other known outstanding scope items from the split
- DeepSeek API ($2 budget, refilled once mid-split) used across the split's phases 1/3/4/6 plus the earlier rename/GUI-polish sessions — exact final balance not tracked here, check with whoever's account it is

## How to hand off to a new AI session

1. Open VS Code workspace at `/Users/c/Documents/studio_project/`
2. In Continue or Claude Code, reference: `@CLAUDE.md` and `@CURRENT.md`
3. Or paste both files' contents at the start of the chat
4. Point the AI at the specific `studio_console/` file for the feature area in question (see `CLAUDE.md`'s "Package layout") rather than loading the whole codebase — that's the entire point of the split
