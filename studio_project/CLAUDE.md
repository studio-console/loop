# Studio Console — CLAUDE.md

Single-file Python lighting console (`studio_project.py`, ~21k lines).
GUI: DearPyGui 2.3.1. All show data lives in `studio_data/`. Version: v0.21.

---

## How to run

```bash
python3 studio_project.py                                      # normal launch
STUDIO_DRY_RUN=1 STUDIO_HEADLESS=1 python3 studio_project.py  # headless smoke test
python3 -m py_compile studio_project.py                        # compile check only
```

Smoke test must stay at **456/456 PASS**. Run it after every change.  
`STUDIO_DRY_RUN=1` disables sACN output. `STUDIO_HEADLESS=1` skips the GUI and runs tests.

---

## Architecture — key classes (all in studio_project.py)

### Data models
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

### Engine
| Class / Function | Purpose |
|-----------------|---------|
| `OutputState` | Merges all layers → DMX. `_merged_cue_layer()` returns `{fid: {ch: val}}` |
| `FadeEngine` | Ticks active fades; `.start_fade(fader, cue, ...)` |
| `FXEngine` | Waveform oscillators per fixture per channel |
| `_vfade_apply(fader)` | Lerps `fader.layer` between `vfade_from` and `vfade_to` at `fader.level` |
| `_exec_fader_mode_hook(fader)` | Called on fader level change; handles moment/vfade logic |
| `_stack_go/back/goto` | Advance/retreat cue position, trigger fade |

### Commands
| Function | Purpose |
|----------|---------|
| `run_command(cmd_str)` | Main entry point (line ~14262). Uppercases tokens, dispatches |

All commands are **case-insensitive** — the parser does `.upper()` on input.

### GUI (`GUIEngine`, line ~5687)
| Method | Purpose |
|--------|---------|
| `_build_fader_page()` | 10-slot MA-style fader grid |
| `_fpg_reflow(w, h)` | Resizes all fader slot widgets dynamically on window resize |
| `_tick()` | Main render loop; syncs all widget state from engine |
| `_setup_fonts()` | Loads Avenir (surface) + mono fonts; currently **17px** |

### Show file (`ShowFile`, line ~12141)
`save_show()` / `load_show()` — reads/writes all `studio_data/*.json`.  
Data format version: `"3.0"`.

### Drivers
| Class | Purpose |
|-------|---------|
| `NetworkEngine` | sACN DMX output |
| `MIDIEngine` | MIDI CC/note input; mappable to any command |
| `OSCEngine` | OSC input; MA3-compatible `/gma3/fader/...` routes |
| `AudioEngine` | Audio-to-FX mapper |
| `AIEngine` | AI assistant integration |

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

---

## Theme / palette

```python
_C_BG     = (3, 2, 8)
_C_PANEL  = (13, 10, 28)
_C_BORDER = (60, 42, 115)
_C_ACCENT = (162, 115, 255)
_C_DIM    = (95, 74, 148)
_C_HOT    = (212, 152, 255)
```
