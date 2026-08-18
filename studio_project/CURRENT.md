# Studio Console — Current State

**Date:** 2026-08-17
**Version:** v0.21
**Smoke test:** 456/456 PASS
**Branch:** main, 28 commits ahead of origin/main (not pushed)

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
- AI engine integration
- Save/load show, backup, named saves in `studio_saves/`
- Commands are case-insensitive (`stk`, `STK`, `fdr`, `FDR` all work)
- Codebase is now a package (`studio_console/`) instead of one 21k-line file — same behavior, verified against the 456-case smoke test at every step (see below)

## Recent changes

1. **`GUIEngine._tick()` decomposed into 12 sub-tick methods** (2026-08-17):
   - Was 789 lines, the one method the Phase 7 mixin split had left alone (flagged as future work in `CURRENT.md`'s "Known / pending"). Already delegated to `_tick_pools`/`_tick_stage`/`_tick_fader_page`/`_tick_audio`, but ~600 lines of status-bar, cue-list, programmer-monitor, output-monitor, MIDI/OSC, and autosave logic still lived directly in the method body.
   - Split into `_tick_first_sync`, `_tick_deferred_maintenance`, `_tick_prog_live_fades`, `_tick_status_bar`, `_tick_playbacks_and_faders`, `_tick_cue_list`, `_tick_fx_header`, `_tick_programmer_monitor`, `_tick_output_monitor`, `_tick_midi_osc`, `_tick_autosave` — all still on `GUIEngineCore` in `gui/core.py`, called in the exact original order
   - Pure boundary extraction: every new method's body verified byte-identical to its slice of the original `_tick()`, plus `py_compile`, an AST undefined-name pass, and the smoke test at 456/456 ×3
   - Not yet pushed to origin

2. **studio_project.py split into the studio_console/ package** (2026-08-13):
   - `studio_project.py`: 21,191 lines → 180-line entry point. Everything else moved into 39 files under `studio_console/`: `models/` (fixture + preset data classes), `engine/` (playback + FX), `drivers/` (network/midi/osc/audio/ai), `gui/` (14 mixin files composing `GUIEngine`), `commands/` (9 category files + dispatcher composing `run_command`), plus `show.py`, `state.py`, `paths.py`, `tests_smoke.py`
   - 11 phases, each its own commit, each independently verified against the smoke test (stayed 456/456 throughout) — zero intended behavior change, though the process did catch and fix several real latent bugs along the way (see commit messages, `git log --oneline` for "Phase N:" subjects)
   - Phases 0/1/3/4/6 (models, drivers, show.py, theme, package skeleton) done via DeepSeek through Continue; phases 2/5/7/8/9/10 (engine, state.py wiring, the 210-method GUIEngine mixin split, the 117-branch run_command split, the entry point) done directly — the latter group all had real cross-reference complexity that made hand-off riskier than tooled in-session extraction
   - Full architecture reference: `CLAUDE.md`'s "Package layout" section. Full design rationale: `~/.claude/plans/glimmering-spinning-moth.md`
   - Goal achieved: an AI session working on one feature area now only needs to load that one file — e.g. the FX editor popup is `gui/fx_editor.py` (~450 lines), not the full codebase
   - Not yet pushed to origin

3. **Project moved into subfolder** (2026-08-12):
   - All files now live in `studio_project/` (was Documents root)
   - Git repo root stays at `/Users/c/Documents`; `.gitignore` updated to match new paths
   - VS Code workspace should be opened at `/Users/c/Documents/studio_project/`
   - Session history for prior work: `~/.claude/projects/-Users-c-Documents/305f777b-...jsonl`

4. **Font set to 17px Avenir** (2026-08-12):
   - `_setup_fonts()`, now in `studio_console/gui/theme.py`: both surface and mono fonts at 17px
   - Previously 13px (DeepSeek), bumped through 14→15→18→17 to find sweet spot

5. **GUI visual polish** (DeepSeek, 2026-08-12):
   - Avenir font throughout, rounded corners (12px panels), deeper violet palette
   - Elevated card panels, inset input wells, STUDIO wordmark in header
   - Forms pool width fix, 6th fixture clipping fix in stage visualiser

6. **stk/fdr rename** (DeepSeek, 2026-08-12):
   - `CS`/`EXEC` removed — now `stk`/`fdr` (or full `stack`/`fader`)
   - Data files: `stacks.json`, `faders.json`, `fader_pages.json`
   - Commits: `e1a2026`, `1b265a2`

7. **CLAUDE.md + CURRENT.md added** for AI handoff efficiency

## Known / pending

- Test stacks 11–14 get wiped by headless smoke test (`SaveShow` overwrites files) — re-seed manually after any headless run
- **File split is done** (see Recent changes #1) — not yet pushed to origin (ahead of origin/main; push blocked in the assistant's environment, needs a manual `git push origin main`)
- **`GUIEngine._tick()` decomposed** (2026-08-17): split into 12 named `_tick_*` sub-methods (`_tick_first_sync`, `_tick_deferred_maintenance`, `_tick_prog_live_fades`, `_tick_status_bar`, `_tick_playbacks_and_faders`, `_tick_cue_list`, `_tick_fx_header`, `_tick_programmer_monitor`, `_tick_output_monitor`, `_tick_midi_osc`, `_tick_autosave`), all still in `gui/core.py`, called in original order — pure boundary extraction, verified byte-identical against git history, 456/456 ×3
- Deliberately deferred, not urgent: converting `tests_smoke.py`'s 456 sequential checks to a real pytest suite (many checks share state built up by earlier ones in the same run — decoupling that is real work, not a mechanical conversion)
- DeepSeek API ($2 budget, refilled once mid-split) used across the split's phases 1/3/4/6 plus the earlier rename/GUI-polish sessions — exact final balance not tracked here, check with whoever's account it is

## How to hand off to a new AI session

1. Open VS Code workspace at `/Users/c/Documents/studio_project/`
2. In Continue or Claude Code, reference: `@CLAUDE.md` and `@CURRENT.md`
3. Or paste both files' contents at the start of the chat
4. Point the AI at the specific `studio_console/` file for the feature area in question (see `CLAUDE.md`'s "Package layout") rather than loading the whole codebase — that's the entire point of the split
