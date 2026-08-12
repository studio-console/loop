# Studio Console — Current State

**Date:** 2026-08-12
**Version:** v0.21
**Smoke test:** 456/456 PASS
**Branch:** main, up to date with origin

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

## Recent changes

1. **Project moved into subfolder** (2026-08-12):
   - All files now live in `studio_project/` (was Documents root)
   - Git repo root stays at `/Users/c/Documents`; `.gitignore` updated to match new paths
   - VS Code workspace should be opened at `/Users/c/Documents/studio_project/`
   - Session history for prior work: `~/.claude/projects/-Users-c-Documents/305f777b-...jsonl`

2. **Font set to 17px Avenir** (2026-08-12):
   - `_setup_fonts()` at line ~5665: both surface and mono fonts at 17px
   - Previously 13px (DeepSeek), bumped through 14→15→18→17 to find sweet spot

3. **GUI visual polish** (DeepSeek, 2026-08-12):
   - Avenir font throughout, rounded corners (12px panels), deeper violet palette
   - Elevated card panels, inset input wells, STUDIO wordmark in header
   - Forms pool width fix, 6th fixture clipping fix in stage visualiser

4. **stk/fdr rename** (DeepSeek, 2026-08-12):
   - `CS`/`EXEC` removed — now `stk`/`fdr` (or full `stack`/`fader`)
   - Data files: `stacks.json`, `faders.json`, `fader_pages.json`
   - Commits: `e1a2026`, `1b265a2`

5. **CLAUDE.md + CURRENT.md added** for AI handoff efficiency

## Known / pending

- Test stacks 11–14 get wiped by headless smoke test (`SaveShow` overwrites files) — re-seed manually after any headless run
- File split planned: `studio_project.py` is ~21k lines / ~319k tokens. Plan: split into `models.py`, `engine.py`, `commands.py`, `gui.py`, `drivers.py`, `show.py`, `tests.py`, `main.py`
- DeepSeek API ($2 budget) used for the rename + GUI polish sessions — ~$1.60 spent

## How to hand off to a new AI session

1. Open VS Code workspace at `/Users/c/Documents/studio_project/`
2. In Continue or Claude Code, reference: `@CLAUDE.md` and `@CURRENT.md`
3. Or paste both files' contents at the start of the chat
4. Point the AI at specific functions/lines rather than loading the whole file
