# Studio Console — CLAUDE.md

Python lighting console. `studio_project.py` is a thin entry point (~180
lines); almost everything lives in the `studio_console/` package (see
Package layout below). GUI: DearPyGui 2.3.1. All show data lives in
`studio_data/`. Version: v0.21.

---

## How to run

```bash
python3 studio_project.py                                      # normal launch
STUDIO_DRY_RUN=1 STUDIO_HEADLESS=1 python3 studio_project.py  # headless smoke test
python3 -m py_compile studio_project.py                        # compile check only
pytest                                                          # same 456 checks, pytest-native reporting
```

Smoke test must stay at **456/456 PASS**. Run it after every change (either form — see below).  
`STUDIO_DRY_RUN=1` disables sACN output. `STUDIO_HEADLESS=1` skips the GUI and runs tests.

Always run `studio_project.py` directly as the entry point — most of
`studio_console/` depends on it being the running `__main__` (see
"Deferred imports" under Key gotchas below). Importing pieces of
`studio_console/` standalone (e.g. `python3 -c "import studio_console.state"`)
does not work and isn't meant to.

**Two ways to run the same 456 checks:**
- `STUDIO_DRY_RUN=1 STUDIO_HEADLESS=1 python3 studio_project.py` — the
  original oracle (`studio_console/tests_smoke.py`, `run_smoke_test(gui)`).
  Every phase of the package split was verified against this; it's the
  source of truth and stays untouched.
- `pytest` (needs `pytest` + `pytest-subtests` installed) — runs
  `studio_console/tests/test_smoke_pytest.py`, a generated, additive
  pytest port of the exact same check sequence (`pytest.ini` points
  `testpaths` at it). Per-check pass/fail via `-v`, `-k` filtering,
  JUnit XML for CI. It's one long `test_smoke_full_pipeline` function,
  not ~456 independent tests — the checks are genuinely sequential
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
  tests_smoke.py             the 456-case headless smoke test (run_smoke_test(gui))
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
                                 pools, FXLayer, FXEngine
  drivers/
    network.py, midi.py, osc.py, audio.py, ai.py
                                 NetworkEngine, MIDIEngine, OSCEngine,
                                 AudioEngine/AudioMapper, AIEngine
  gui/                         GUIEngine — composed in studio_project.py via
                                multiple inheritance from 14 mixin classes:
    theme.py                    palette, DPG themes, font setup
    core.py                     __init__, build(), run(), _tick(), _log,
                                 all class-level layout constants
    header.py, left_column.py, right_column.py, stage.py, pools_panel.py,
    hardware_popups.py, misc_popups.py, fx_editor.py, ai_popups.py,
    color_picker.py, speed_master.py, fader_page.py, audio_monitors.py
                                 one file per panel/popup cluster
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
| `FXEngine` | Waveform oscillators per fixture per channel |
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
| `NetworkEngine` | `network.py` | sACN DMX output |
| `MIDIEngine` | `midi.py` | MIDI CC/note input; mappable to any command |
| `OSCEngine` | `osc.py` | OSC input; MA3-compatible `/gma3/fader/...` routes |
| `AudioEngine` | `audio.py` | Audio-to-FX mapper |
| `AIEngine` | `ai.py` | AI assistant integration |

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

All pool files follow the same pattern: `{"version": "3.0", "<pool_key>": {...}}`.

---

## Key gotchas

- `fader_pool.get(n)` **auto-creates** a blank Fader if n doesn't exist — never assume a missing ID means "not assigned".
- Smoke test runs `save_show()` repeatedly — it will overwrite `studio_data/` files. Don't pre-seed test data before running headless; use in-memory fixtures instead.
- DPG 2.3.1 uses `num_items` (not `num_displayed_items`) for listboxes.
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
