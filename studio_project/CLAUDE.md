# Studio Console — CLAUDE.md

Python lighting console. `studio_project.py` is a thin entry point (~180
lines); almost everything lives in the `studio_console/` package (see
Package layout below). GUI: DearPyGui 2.3.1. All show data lives in
`studio_data/`. Version: v0.22.

---

## How to run

```bash
python3 studio_project.py                                      # normal launch
STUDIO_DRY_RUN=1 STUDIO_HEADLESS=1 python3 studio_project.py  # headless smoke test
python3 -m py_compile studio_project.py                        # compile check only
pytest                                                          # same 507 checks, pytest-native reporting
```

Smoke test must stay at **507/507 PASS**. Run it after every change (either form — see below).  
`STUDIO_DRY_RUN=1` disables sACN output. `STUDIO_HEADLESS=1` skips the GUI and runs tests.

Always run `studio_project.py` directly as the entry point — most of
`studio_console/` depends on it being the running `__main__` (see
"Deferred imports" under Key gotchas below). Importing pieces of
`studio_console/` standalone (e.g. `python3 -c "import studio_console.state"`)
does not work and isn't meant to.

**Two ways to run the same 507 checks:**
- `STUDIO_DRY_RUN=1 STUDIO_HEADLESS=1 python3 studio_project.py` — the
  original oracle (`studio_console/tests_smoke.py`, `run_smoke_test(gui)`).
  Every phase of the package split was verified against this; it's the
  source of truth and stays untouched.
- `pytest` (needs `pytest` + `pytest-subtests` installed) — runs
  `studio_console/tests/test_smoke_pytest.py`, a generated, additive
  pytest port of the exact same check sequence (`pytest.ini` points
  `testpaths` at it). Per-check pass/fail via `-v`, `-k` filtering,
  JUnit XML for CI. It's one long `test_smoke_full_pipeline` function,
  not ~507 independent tests — the checks are genuinely sequential
  (each depends on state the earlier ones left in `fader_pool`/`patch`/
  `stack_pool`), so `pytest-subtests` reports each one individually
  without pretending they're isolated. It builds `gui` and every engine
  singleton by actually running `studio_project.py` via `runpy` (see
  `STUDIO_PYTEST_COLLECT` in `studio_project.py`), so it's exactly the
  same construction/wiring as a real launch, not a re-derived copy.

---

## Package layout

```
studio_project.py            entry point: wiring imports, builds GUIEngine,
                              launches GUI or (STUDIO_HEADLESS) the smoke test
studio_console/
  paths.py                   DATA_DIR/SAVES_DIR, anchored to studio_project.py's dir
  state.py                   startup wiring — every pool/engine/driver singleton,
                              show-file loading, MIDI/OSC setup, save_show/cue_go/
                              goto_cue and other closely-coupled helpers
  show.py                    ShowFile — save/load all studio_data/*.json
  tests_smoke.py             the 507-case headless smoke test (run_smoke_test(gui))
  models/
    fixtures.py               FixtureProfile, FixtureLibrary, GDTFLoader,
                               SubFixture, MasterFixture, Patch, programmer
    presets.py                ColorPreset/Pool, DimmerPreset/Pool, Group/Pool,
                               Cue, Stack, CuePool, StackPool, Fader, FaderPool,
                               FXPreset/Pool, Fade
  engine/
    playback.py                FadeEngine, OutputState, _resolve_cue_refs,
                                _vfade_apply, _exec_fader_mode_hook, _stack_go/
                                back/goto/reload
    fx.py                       Waveform, Form/Rate/Size/Spread/SpeedMaster
                                 pools, FXLayer, FXEngine. FXEngine starts no
                                 thread on its own — see "Single FX driver" below
    key_color.py                KeyColorMapper (audio-reactive framework) —
                                 Krumhansl-Schmuckler key detection over a
                                 pitch-class histogram, minor→cold / major→warm
                                 palette crossfade
    subharmonic.py              SubHarmonicStrobe (audio-reactive framework) —
                                 sub-harmonic division math, bass-onset strobe
                                 rates → sACN layer dict + Resolume OSC
    audio_router.py             AudioRouter — band-level thresholds that fire
                                 console targets (AUDIO ROUTE commands).
                                 Threadless and deterministic: tick() is
                                 driven externally, from the GUI tick or
                                 directly in headless tests
  drivers/
    network.py, midi.py, osc.py, audio.py, audio_midi.py, ai.py
                                 NetworkEngine (SACN_FPS / STAGING_HZ
                                 constants), MIDIEngine, OSCEngine,
                                 AudioEngine/AudioMapper, AudioMIDIBridge
                                 (audio-reactive framework: pitch → clean MIDI notes
                                 via AudioEngine.on_chunk hook), AIEngine
  gui/                         GUIEngine — composed in studio_project.py via
                                multiple inheritance from 14 mixin classes:
    theme.py                    palette, DPG themes, font setup
    core.py                     __init__, build(), run(), _tick(), _log,
                                 all class-level layout constants
    header.py, left_column.py, right_column.py, stage.py, pools_panel.py,
    hardware_popups.py, misc_popups.py, fx_editor.py, ai_popups.py,
    color_picker.py, speed_master.py, fader_page.py, audio_monitors.py,
    audio_routing.py
                                 one file per panel/popup cluster — audio_routing
                                 is the Audio Control & Routing window: device/
                                 master controls, 4-band level meter with
                                 threshold markers, routing matrix table
  commands/                    run_command() — composed in commands/__init__.py
                                from 114 branch functions across 9 category files:
    __init__.py                 dispatcher: preamble + ordered dispatch list +
                                 default-to-programmer fallback
    _shared.py                   _record_cue_into, _prog_fx_stop/start/rebuild
    stack.py, fader.py, programmer.py, fx.py, misc.py, macro.py, io.py,
    patch.py, presets.py
                                 one file per command category
```

Full rationale for this layout: `/Users/c/.claude/plans/glimmering-spinning-moth.md`.

---

## Architecture — key classes

### Data models (`studio_console/models/`)
| Class | Purpose |
|-------|---------|
| `MasterFixture` / `SubFixture` | Patched fixture with profile channels |
| `Patch` | Fixture registry; `.get(fid)` → MasterFixture |
| `programmer` | Live programmer state; `.data[fid][channel] = value` |
| `Cue` | Single cue: `.data`, `.fade_time`, `.follow_time`, `.fx` |
| `Stack` | Ordered cue list; `.cues`, `.current`, `.wrap`, `.bounce` |
| `StackPool` | `stacks[id]` dict; `stacks_pool.get(n)` auto-creates |
| `Fader` | Playback slot: `.level` (0–1), `.stack`, `.is_active`, `.output_mode`, `.priority` |
| `FaderPool` | `executors[id]` dict; `fader_pool.get(n)` auto-creates |

### Engine (`studio_console/engine/`)
| Class / Function | Purpose |
|-----------------|---------|
| `OutputState` | Merges all layers → DMX. `_merged_cue_layer()` returns `{fid: {ch: val}}` |
| `FadeEngine` | Ticks active fades; `.start_fade(fader, cue, ...)` |
| `FXEngine` | Waveform oscillators per fixture per channel. `compute_merged(now)` is driven by exactly one thread — see "Single FX driver" below |
| `_vfade_apply(fader)` | Lerps `fader.layer` between `vfade_from` and `vfade_to` at `fader.level` |
| `_exec_fader_mode_hook(fader)` | Called on fader level change; handles moment/vfade logic |
| `_stack_go/back/goto` | Advance/retreat cue position, trigger fade |

### Commands (`studio_console/commands/`)
| Function | Purpose |
|----------|---------|
| `run_command(cmd_str)` | `commands/__init__.py`. Uppercases tokens, dispatches to whichever of 114 branch functions (across 9 category files) matches first, in original first-match-wins order |

All commands are **case-insensitive** — the parser does `.upper()` on input.

### GUI (`GUIEngine`, composed in `studio_project.py` from `studio_console/gui/*.py`)
| Method | File | Purpose |
|--------|------|---------|
| `_build_fader_page_popup()` | `gui/fader_page.py` | MA-style fader grid |
| `_fpg_reflow(w, h)` | `gui/fader_page.py` | Resizes all fader slot widgets dynamically on window resize |
| `_tick()` | `gui/core.py` | Main render loop; syncs all widget state from engine |
| `_setup_fonts()` | `gui/theme.py` | Loads Avenir (surface) + mono fonts; currently **17px** |

### Show file (`ShowFile`, `studio_console/show.py`)
`save_show()` / `load_show()` — reads/writes all `studio_data/*.json`.  
Data format version: `"3.0"`.

### Drivers (`studio_console/drivers/`)
| Class | File | Purpose |
|-------|------|---------|
| `NetworkEngine` | `network.py` | sACN DMX output. Staging loop at `STAGING_HZ` (100) on a dedicated background thread; packets leave the wire at `SACN_FPS` (44), paced by the sacn library's own internal sender thread. Claims the FX driver role on start() |
| `MIDIEngine` | `midi.py` | MIDI CC/note input; mappable to any command |
| `OSCEngine` | `osc.py` | OSC input; MA3-compatible `/gma3/fader/...` routes |
| `AudioEngine` | `audio.py` | Audio-to-FX mapper |
| `AIEngine` | `ai.py` | AI assistant integration |

### Single FX driver + sACN output pipeline

The sACN path runs on **exactly one explicit driver pattern** — a single
designated thread calls `FXEngine.compute_merged()`, and no second thread
ever competes with it.

```
NetworkEngine._run()   ← staging loop, STAGING_HZ = 100, named "sacn-staging"
  ├─ fx_engine.compute_merged(now)          ← the ONLY FX driver when running
  ├─ output_state.get_dmx_for_universe(u)   ← reads merged live state directly
  └─ self._sender[u].dmx_data = dmx        ← stages into the sender's buffers
                                                │
sacn library's own UDP sender thread ───────────┘  transmits at SACN_FPS = 44
```

**Two distinct rates — don't conflate them.** `STAGING_HZ` (100) is how often
we *compute and stage*; `SACN_FPS` (44) is how often packets actually leave
the wire. Transmission is paced by the sacn library's internal sender thread
(`sacn/sending/sender_socket_udp.py`), **not** by our loop — so `fps=` on
`sACNsender()` is the only thing that sets the wire rate. Staging faster than
the wire rate is deliberate and free: a strobe phase boundary is picked up
within ~10ms instead of waiting up to a full 22ms wire frame.

**FXEngine starts no thread in `__init__`.** It used to start a 44Hz
`compute_merged()` loop unconditionally, which raced `NetworkEngine._run`'s
own 100Hz calls for `FXEngine._lock` — a lock the network thread needs on its
critical path just before each send, so losing that race delayed the send.
Driver selection is now explicit:

| Method | Role |
|--------|------|
| `claim_external_driver()` | Called by `NetworkEngine.start()`. Stops the fallback thread; exactly one driver remains. Idempotent, never joins from the loop's own thread |
| `start_background_loop()` | The fallback — only when nothing else ticks FX. Idempotent. Without it, envelopes/outfades would never advance |
| `stop()` | Delegates to `claim_external_driver()`, so either path shuts down cleanly |

If you add another thread that calls `compute_merged()`, it must claim the
role through this protocol. And note `NetworkEngine.start()`'s "sACN port
busy" branch returns before starting its staging loop — that path calls
`start_background_loop()` so FX keeps advancing with no output.

**`NetworkEngine.phase_delay_ms`** is a placeholder (`0.0`) for a future
per-universe phase-offset UI slider. It is **not applied**. Packet timing
lives in the sacn library's thread, so honoring a per-universe offset
requires shifting that library's send scheduling — applying it in the
staging loop would silently do nothing.

The staging loop reads `OutputState` directly rather than accepting DMX
frames from the main thread. Handing frames in would push the expensive FX
re-evaluation onto the GUI thread and add a frame of latency; the staging
loop is already fully off the main thread, so GUI render lag cannot stall
output.

---

## Command vocabulary

Case-insensitive. Short aliases work everywhere.

| Concept | Full word | Short alias |
|---------|-----------|-------------|
| Cue list | `stack` | `stk` |
| Playback slot | `fader` | `fdr` |

**CS and EXEC no longer exist** — removed in the stk/fdr rename (commit e1a2026).

Common patterns:
```
stk 3 go          fdr 5 go          fdr 3 back        fdr 2 stop
record stk 7 cue 1 My Cue
fader 3 output vfade
fader 3 priority hi
stk 2 wrap on
prog fade 2        prog fade off      prog fade clear
```

---

## Data files (`studio_data/`)

| File | Contents |
|------|----------|
| `stacks.json` | All cue stacks (was `cuestacks.json`) |
| `faders.json` | Fader assignments + settings (was `executors.json`) |
| `fader_pages.json` | Fader page layout (was `executor_pages.json`) |
| `patch.json` | Fixture patch |
| `colors.json` | Color preset pool |
| `dims.json` | Dimmer preset pool |
| `fx_pool.json` | FX presets |
| `midi.json` | MIDI mappings |
| `state.json` | Runtime state (active fader, etc.) |
| `changelog.json` | Session history log |
| `audio_routes.json` | AudioRouter enabled flag, default threshold, routes |

All pool files follow the same pattern: `{"version": "3.0", "<pool_key>": {...}}`.

---

## Key gotchas

- `fader_pool.get(n)` **auto-creates** a blank Fader if n doesn't exist — never assume a missing ID means "not assigned".
- Smoke test runs `save_show()` repeatedly — it will overwrite `studio_data/` files. Don't pre-seed test data before running headless; use in-memory fixtures instead.
- DPG 2.3.1 uses `num_items` (not `num_displayed_items`) for listboxes.
- **To move a pre-built `drawlist` primitive at runtime, use
  `configure_item(tag, pmin/pmax=...)` or `(p1/p2=...)` for lines — never
  `draw_rectangle(tag=...)` / `draw_line(tag=...)`.** Those are *creation*
  calls: outside an enclosing `with dpg.drawlist(...)` and with no `parent=`,
  DPG 2.3.1 raises `SystemError` **and deregisters the existing item**, so the
  primitive disappears and every later tick fails too. A bare
  `except Exception: pass` in the tick path hides this completely — the widget
  just goes permanently blank. See `gui/audio_routing.py`'s meter tick.
- **Draw items live in child slot 2 of a `drawlist`, not slot 0.** `slot 0` is
  always empty; `get_item_children(tag)` with no slot returns a 4-key dict.
  Asserting slot 0 in a test can never pass.
- `get_item_rect_size()` returns **0x0 before the first layout pass** — and
  forever in `STUDIO_HEADLESS`, where no frame is ever laid out. Any geometry
  math in a tick needs a fallback to the item's configured
  `width`/`height` (`get_item_configuration(tag)`) or it divides by zero.
- **Never start a second thread that calls `FXEngine.compute_merged()`.** One
  driver only — a concurrent caller contends on `FXEngine._lock`, which the
  sACN staging thread needs on its critical path just before each send, so it
  shows up as send-time jitter rather than as an error. A new caller must go
  through `claim_external_driver()` / `start_background_loop()` (see "Single FX
  driver" above).
- **The sACN wire rate is set by `fps=` on `sACNsender()`, not by our loop.**
  Transmission is paced by the sacn library's own internal sender thread, and
  that library defaults `fps` to **30** — omitting it silently runs the rig at
  30Hz no matter what `NetworkEngine._run` does. `STAGING_HZ` (our loop) and
  `SACN_FPS` (the wire) are separate knobs for a reason.
- Fonts must be sized as integers; fallback to DPG built-in if font file not found.
- `output_mode`: `'normal'` / `'moment'` / `'vfade'`
- `trigger_mode`: `'toggle'` / `'flash'` / `'moment'`
- `priority`: `-1` (lo) / `0` (nrm) / `1` (hi) — controls LTP merge order

### Deferred imports (`from __main__ import X`)

Several modules in `studio_console/` reach back into `studio_project.py`
with a **function-local** `from __main__ import X` instead of a normal
top-level import — e.g. `drivers/ai.py` importing `Fader`,
`engine/playback.py` importing `_prog_time`, several `commands/*.py`
files importing `run_command` itself. This is deliberate, not leftover
debt:

- `studio_project.py` runs as `__main__`, not as a module literally
  named `studio_project` — `from studio_project import X` fails or
  (worse) silently re-imports and re-executes the whole file as a
  second module.
- Some of these are genuine circular dependencies (e.g. `commands/*.py`
  needs `run_command`, which is itself assembled from `commands/*.py`
  in `commands/__init__.py`) — a top-level import would fail outright.
- The import is **function-local** (inside the method that uses it),
  not module-level, so it only resolves at call time — by then, the
  whole file has finished loading and the name genuinely exists in
  `__main__`. A lambda can't contain an import statement, which is why
  a couple of these got converted to small named wrapper functions
  instead.

If you add a new cross-module reference in this codebase: check whether
the target is defined *earlier* or *later* in `studio_project.py`'s
import order than the module you're editing. Earlier → safe as a normal
top-level import. Later, or genuinely circular → needs this pattern.

`studio_console/tests/test_smoke_pytest.py` is the one place that
deliberately works around the `__main__`-only assumption: it runs
`studio_project.py` via `runpy.run_path(..., run_name="__main__")` (real
construction/wiring, no duplicated setup) and then manually re-pins
`sys.modules['__main__']` to the harvested namespace afterward, since
`runpy` restores the caller's original `__main__` once it returns — and
these deferred imports keep firing well after that point, throughout the
whole check sequence.

Related, easy to reintroduce by accident: any class-level constant
computed via `os.path.dirname(os.path.abspath(__file__))` breaks
silently if the code defining it ever moves to a file at a different
directory depth than the one it was written for — anchor to
`studio_console/paths.py`'s `DATA_DIR`/`_SCRIPT_DIR` instead. And moving
module-level code into a function body can silently turn a bare name
rebind (`_some_flag = False`) into an `UnboundLocalError`, if anything
reads that name earlier in the same function — Python treats a name as
local to the *whole* function if it's assigned anywhere in it,
regardless of execution order.

---

## Theme / palette (`studio_console/gui/theme.py`)

```python
_C_BG     = (3, 2, 8)
_C_PANEL  = (13, 10, 28)
_C_BORDER = (60, 42, 115)
_C_ACCENT = (162, 115, 255)
_C_DIM    = (95, 74, 148)
_C_HOT    = (212, 152, 255)
```
