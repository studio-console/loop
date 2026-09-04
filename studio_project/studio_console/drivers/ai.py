"""Studio Console AI driver — extracted verbatim from studio_project.py
(the "Block 12: AI Engine" section: AIEngine). Pure move, zero behavior
change, EXCEPT one deliberate addition: `_state()` now does a function-local
`from __main__ import Fader` instead of relying on a bare `Fader` name
resolved from studio_project.py's global scope (which is how it worked when
this class lived inside studio_project.py directly). `Fader` still lives in
studio_project.py — it isn't extracted until a later phase.

IMPORTANT: this must be `from __main__ import Fader`, NOT `from
studio_project import Fader`. studio_project.py has no `if __name__ ==
"__main__":` guard, so when it's run normally (`python3 studio_project.py`),
it registers itself in sys.modules as `__main__`, not as `studio_project`.
`from studio_project import Fader` would therefore not find the already-
running module — it would trigger Python to import studio_project.py fresh,
as a second, separate module object, re-executing every top-level
side-effecting line (engine construction, sockets, GUI build, the smoke
test) a second time. `from __main__ import Fader` reaches into the actual
running script's namespace via the `__main__` alias, which is always
already in sys.modules once the script has started — a pure lookup, no
re-execution. This import must stay deferred (inside the function, not at
module top) to avoid a circular-import ordering problem at load time either
way. Do not change it to import from studio_console.models — that path
doesn't exist yet.
"""

import os
import json
import anthropic

from studio_console.command_reference import COMMAND_REFERENCE


class AIEngine:
    """
    Translates natural language into lighting console actions.

    How it works:
    1. ai.ask("make it dramatic") is called
    2. Current console state is described in a system prompt
    3. Claude returns a JSON list of actions
    4. execute() runs each action on the actual console

    The AI knows about:
    - Your fixtures and their IDs
    - All stacks and their cues
    - Available FX waveforms and parameters
    - programmer commands (same syntax as command line)
    """

    ACTION_SCHEMA = """
Return a JSON array of action objects. Each action is one of:

{"action": "goto_cue",    "stack": 1, "num": 2}
{"action": "cue_go",      "stack": 1}
{"action": "cue_back",    "stack": 1}
{"action": "cue_fire",    "stack": 1, "num": 3}
{"action": "prog",        "cmd": "1 THRU 6 AT R 255 G 0 B 0"}
  (raw channel values — only when no saved preset already matches; for a
   named-preset match, use TWO prog actions instead: one to select, one
   for the recall, e.g. {"action":"prog","cmd":"1.1"} then
   {"action":"prog","cmd":"COLOR 3"} — see rules below)
{"action": "dim",         "value": 0.85}
{"action": "fx_start",    "waveform": "sine", "channel": "red",
                          "bpm": 60, "size": 100, "spread": 0.0}
{"action": "fx_stop",     "channel": "red"}
{"action": "fx_clear"}
{"action": "group_select","group": 2}
{"action": "fade_time",   "seconds": 3.0}
{"action": "exec_level",  "fdr": 1, "level": 0.75}
{"action": "say",         "text": "explanation, answer, or clarifying question"}

Rules:
- "group_select" selects all fixtures in group N as the programmer selection.
- "fx_stop" stops FX on one channel; omit "channel" to stop all.
- "exec_level" sets a fader's master level (level 0.0–1.0).
- "cue_fire" is an alias for goto_cue (fires the named cue immediately).
- "fade_time" only affects the next cue_go/cue_back/goto_cue/cue_fire action
  in this same array — put it immediately before the cue action it should
  apply to (e.g. a slow fade into a cue: [{"action":"fade_time","seconds":5},
  {"action":"goto_cue","stack":1,"num":2}]). It does not change any other
  timing and is not a standing default.
- "stack" identifies a stack by id, not a fader slot — it is resolved
  to whichever fader that stack is currently assigned to.
- "say" is plain text shown directly to the operator — not a command, does
  nothing to the console. Use it to answer a question, explain a non-obvious
  choice, admit you're not sure what's wanted, or say what you'd need to
  know to do this properly. It can stand alone (pure question, nothing to
  execute yet) or sit alongside real actions in the same array (a short
  note on why you picked what you picked). Don't add one for routine,
  self-explanatory requests — only when it actually helps the operator
  understand or steer you.
- Only return the JSON array. No markdown fences. "say" is the one place
  free text belongs — it still has to be inside a JSON action object like
  everything else, never prose before/after the array.
"""

    _CMD_HISTORY_MAX = 12
    _CHAT_HISTORY_MAX = 6   # exchanges (user+assistant pairs) kept for conversational context

    # DeepSeek publishes an Anthropic-compatible endpoint (same
    # messages.create() shape, same response.content[0].text /
    # response.usage.input_tokens|output_tokens fields) — so switching
    # provider is just a different api_key/base_url/model, not a
    # different request/response code path. AI_PROVIDER picks which;
    # unset or unrecognized falls back to real Anthropic.
    _PROVIDERS = {
        "anthropic": {
            "env_key":  "ANTHROPIC_API_KEY",
            "base_url": None,
            "model":    "claude-haiku-4-5-20251001",
        },
        "deepseek": {
            "env_key":  "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com/anthropic",
            "model":    "deepseek-v4-flash",
        },
    }

    # Section titles pulled from command_reference.py's COMMAND_REFERENCE
    # to build the AI's full command-vocabulary reference (see
    # _build_command_ref). Everything that's actually a *command* the AI
    # could put in a "prog" action — i.e. everything the operator can do
    # from the command line — so "be an expert at this program, do/save/
    # recall/rename anything it's capable of" has a real vocabulary to
    # draw from instead of guessing. Deliberately excludes the sections
    # that only describe GUI buttons/panels/keyboard shortcuts, not
    # commands (network/sacn, osc, ai control, keyboard, status bar &
    # quick controls, fixture dim panel) — those don't help construct a
    # valid prog command and would just be dead weight on every request.
    _AI_COMMAND_REF_SECTIONS = [
        "selection", "colour & dim", "programmer math (AT verbs)",
        "moving lights / attributes", "fx", "list / inspect",
        "record (saving presets/pools)", "rename / copy / delete",
        "stack go/back", "faders & pages", "attribute pools", "programmer",
        "direct dmx", "patch commands", "macros", "speed masters",
        "midi clock", "audio reactive",
    ]

    @classmethod
    def _build_command_ref(cls):
        """Full command-vocabulary reference, pulled straight from
        command_reference.py (the same manual the ? popup shows) so it
        can't drift out of sync with the real command set. Built once —
        called from __init__, not per-request."""
        lines = []
        by_title = dict(COMMAND_REFERENCE)
        for title in cls._AI_COMMAND_REF_SECTIONS:
            rows = by_title.get(title)
            if not rows:
                continue
            lines.append(f"# {title}")
            for cmd, desc in rows:
                lines.append(f"  {cmd}  —  {desc}")
        return "\n".join(lines)

    def __init__(self, patch, prog, output_state, fx_engine, fade_engine,
                 stack_pool=None, fader_pool=None,
                 color_pool=None, dim_pool=None, group_pool=None, fx_pool=None,
                 attr_pools=None, rate_pool=None, size_pool=None,
                 spread_pool=None, form_pool=None,
                 cmd_fn=None, log_fn=None, model=None):
        provider = os.environ.get("AI_PROVIDER", "anthropic").strip().lower()
        if provider not in self._PROVIDERS:
            provider = "anthropic"
        _cfg = self._PROVIDERS[provider]
        self._provider  = provider
        self._env_key   = _cfg["env_key"]   # readable even while disabled
        api_key = os.environ.get(_cfg["env_key"])
        if not api_key:
            print(f"  AI Engine: {_cfg['env_key']} not set — AI disabled.")
            print(f"  Run:  export {_cfg['env_key']}='...' "
                  f"(or add it to studio_data/.env)")
            self._enabled = False
            return
        self._client          = anthropic.Anthropic(api_key=api_key,
                                                      base_url=_cfg["base_url"])
        self._model           = model or _cfg["model"]
        self._patch          = patch
        self._prog           = prog
        self._output         = output_state
        self._fx             = fx_engine
        self._fade           = fade_engine
        # Live pool references (not snapshots) so newly created/loaded
        # stacks/presets are visible without re-constructing the AI engine.
        self._stack_pool     = stack_pool
        self._fader_pool  = fader_pool
        self._color_pool     = color_pool
        self._dim_pool       = dim_pool
        self._group_pool     = group_pool
        self._fx_pool        = fx_pool
        self._attr_pools     = attr_pools or {}   # {name: AttributePool} — position/gobo/zoom/focus/beam/control
        self._rate_pool      = rate_pool
        self._size_pool      = size_pool
        self._spread_pool    = spread_pool
        self._form_pool      = form_pool
        self._cmd            = cmd_fn    # run_command — full console command parser
        self._log            = log_fn    # GUI log callback
        self._enabled        = True
        self._last_fade      = None      # pending fade_time override, consumed by the next cue fire
        self._cmd_history    = []        # last N commands for context
        self._chat_history   = []        # last N (user, assistant) turns — see ask()/_push_chat_history
        self._token_cb       = None      # optional callback(in_tok, out_tok) for GUI
        # Read the command manual once at startup (see _build_command_ref) —
        # was reported as "working but isn't great at saving pools, calling
        # pools/fx into the programmer", then "I want it to be an expert at
        # this program, do/save/recall/rename anything and everything it's
        # capable of" — the AI only ever saw a small fixed ACTION_SCHEMA
        # with no RECORD/RENAME/COPY/DELETE/FADER/PATCH/etc verbs in it at
        # all, even though "prog" could already run any of them — it just
        # never knew that. Cached once, not rebuilt per ask().
        self._command_ref    = self._build_command_ref()
        print(f"  AI Engine: ready ({provider}: {self._model})")

    def push_cmd_history(self, cmd_str):
        """Call after each user command to feed recent context into AI prompts."""
        self._cmd_history.append(cmd_str)
        if len(self._cmd_history) > self._CMD_HISTORY_MAX:
            self._cmd_history = self._cmd_history[-self._CMD_HISTORY_MAX:]

    def _push_chat_history(self, prompt, raw_reply):
        """Record one (operator prompt, model reply) turn for conversational
        continuity — separate from _cmd_history, which tracks executed
        command strings, not the actual back-and-forth. Stores the model's
        raw JSON reply verbatim (not a hand-written summary) so a follow-up
        turn sees exactly what it said last time, "say" text included.
        Only the prompt text is kept for history turns — the current
        request still gets a fresh state_json prepended in ask() itself,
        so old turns don't need to carry a stale state snapshot too."""
        self._chat_history.append({"role": "user", "content": prompt})
        self._chat_history.append({"role": "assistant", "content": raw_reply})
        _cap = self._CHAT_HISTORY_MAX * 2
        if len(self._chat_history) > _cap:
            self._chat_history = self._chat_history[-_cap:]

    def clear_chat_history(self):
        """Start a fresh conversation — call when the operator closes the AI
        window or explicitly wants to reset context (see ai_popups.py)."""
        self._chat_history = []

    def _state(self):
        # Fader still lives in studio_project.py until a later phase moves it
        # to studio_console/models/presets.py — deferred (function-local)
        # import avoids a circular import at module load time. Must be
        # `from __main__`, not `from studio_project` — see the module
        # docstring above before changing this.
        from __main__ import Fader
        fixtures = [
            {"id": m.fixture_id, "name": m.name,
             "pixels": len(list(m.all_subs())),
             # 3D rig-viz placement — None means auto-arranged (a line
             # along x ordered by patch id), not "no fixture here".
             # Included so a request like "arrange them in a circle" can
             # see what's already placed instead of arranging blind.
             "viz_position": getattr(m, 'viz_position', None)}
            for m in self._patch.all_fixtures()
        ]
        stacks = {}
        for sid, stack in (self._stack_pool.stacks.items() if self._stack_pool else {}):
            cues = [
                {"num": n, "name": stack.cues[n].name,
                 "fade": stack.cues[n].fade_time}
                for n in stack._sorted_cue_numbers()
            ]
            stacks[str(sid)] = {
                "name": stack.name,
                "cues": cues,
                "current": getattr(stack, 'current', None),
            }
        fx_active = []
        for layer in self._fx._layers.values():
            fx_active.append({"waveform": layer.waveform,
                               "channel": layer.channel,
                               "bpm": layer.rate_bpm,
                               "size": layer.size,
                               "spread": layer.spread})
        # programmer contents (what's currently edited, not yet stored in a
        # cue). Values aren't all numeric — 'fx' is a list of layer-def
        # dicts, *_ref fields are preset ids — round() on those raised and
        # (wrapped in a single try/except around the whole loop) silently
        # dropped ALL programmer visibility for every fixture the moment
        # any one of them had live FX, which is exactly the situation
        # "calling fx into the programmer" prompts most need this for.
        def _jsonable(v):
            if isinstance(v, float):
                return round(v, 3)
            if isinstance(v, list):
                return [_jsonable(x) for x in v]
            if isinstance(v, dict):
                return {k: _jsonable(x) for k, x in v.items()}
            return v
        prog_data = {}
        for fid, vals in self._prog.data.items():
            try:
                prog_data[fid] = {k: _jsonable(v) for k, v in vals.items()}
            except Exception:
                continue
        # Active faders
        active_execs = []
        if self._fader_pool:
            for eid, ex in sorted(self._fader_pool.faders.items()):
                if ex.is_active and ex.stack:
                    cur  = ex.stack.current
                    cue  = ex.stack.cues.get(cur) if cur is not None else None
                    active_execs.append({
                        "fdr": eid,
                        "stack": ex.stack.name,
                        "current_cue": cur,
                        "cue_name": cue.name if cue else None,
                        "level": round(ex.level, 2),
                        "priority": Fader.PRIORITY_LABELS.get(ex.priority, 'NRM'),
                    })
        # What's already saved in each pool — so the AI can reference an
        # existing preset by name/number ("use the Amber color preset")
        # instead of guessing blind or re-recording a duplicate. Names
        # only, not full contents (RGB/level/etc. is a COLOR n / DIM n
        # command away and isn't worth the tokens for every slot on every
        # request).
        def _pool_names(pool, items_attr='presets'):
            if not pool:
                return {}
            return {str(pid): getattr(p, 'name', str(pid))
                    for pid, p in getattr(pool, items_attr).items()}
        pools = {
            "color": _pool_names(self._color_pool),
            "dim":   _pool_names(self._dim_pool),
            "group": _pool_names(self._group_pool, items_attr='groups'),
            "fx":    _pool_names(self._fx_pool),
            "rate":   _pool_names(self._rate_pool),
            "size":   _pool_names(self._size_pool),
            "spread": _pool_names(self._spread_pool),
            "form":   _pool_names(self._form_pool, items_attr='forms'),
        }
        for _attr_name, _attr_pool in self._attr_pools.items():
            pools[_attr_name] = _pool_names(_attr_pool)
        return {
            "fixtures": fixtures,
            "stacks": stacks,
            "fx": fx_active,
            "programmer": prog_data,
            "active_faders": active_execs,
            "pools": pools,
            "recent_commands": list(self._cmd_history),
        }

    def ask(self, prompt, execute=True):
        """
        Send a natural language prompt. Returns the list of actions
        and optionally executes them immediately.
        """
        if not self._enabled:
            print(f"  AI disabled — set {self._env_key} first.")
            return []

        state_json = json.dumps(self._state(), indent=2)
        system = (
            "You are the AI control layer for Studio Console, "
            "a custom lighting console controlling 6 SGM RGB pixel tubes "
            "(54 pixels each) via sACN. "
            "Translate the user's intent into console actions. "
            "Be creative with lighting — colour, movement, mood. "
            "Available waveforms: sine, ramp, pulse, square. "
            "Available channels: red, green, blue. "
            "programmer commands use MA3-style syntax: "
            "'FIXTURE_ID AT VALUE', 'R 255 G 0 B 0', 'AT FULL', 'AT OUT'.\n\n"
            "You are an expert operator of this specific console — you should "
            "be able to do, save, recall, rename, copy, or delete anything the "
            "program itself is capable of, not just apply colours and run FX. "
            "The \"prog\" action is NOT limited to AT-value syntax — its "
            "\"cmd\" field is a full passthrough to the real console command "
            "parser, so it can run ANY command in the reference below verbatim: "
            "recording the current programmer into a saved preset (RECORD "
            "COLOR/DIM/GROUP/FX/POSITION/RATE/...), recalling one back into the "
            "programmer (COLOR n, DIM PRESET n, GROUP n, FIRE FX n, POSITION n, "
            "...), renaming/copying/deleting any preset or cue (RENAME COLOR n "
            "Name, COPY FX n TO m, DELETE FORM n, CLEAR GROUP n, ...), stack/"
            "fader playback control (GO, BACK, GOTO n, FADER n LEVEL/MODE/"
            "OUTPUT/ASSIGN, PAGE ...), macros, patch edits, direct DMX, LIST "
            "commands to inspect a pool, and everything else in the reference "
            "below — there is no dedicated action type for most of this, prog "
            "covers it. Prefer a saved preset over improvising raw values, "
            "for EVERY pool type, not just colour — colour, dim, group, fx, "
            "position, gobo, zoom, focus, beam, control, rate, size, spread, "
            "form all have a pools.<name> section in the state below; check "
            "it for a name matching the request BEFORE improvising with "
            "prog/fx_start/raw AT values. If pools.fx already has an entry "
            "whose name matches, use prog \"FIRE FX n\" instead of an "
            "fx_start action; if pools.position/gobo/zoom/... has a match, "
            "use prog \"POSITION n\" / \"GOBO n\" / etc, not raw AT values. "
            "This applies at any selection scope, including a single "
            "sub-fixture (e.g. \"1.1 green\" → check pools.color for a "
            "name matching \"green\" first). Only fall back to raw values "
            "or fx_start when nothing in the relevant pool actually fits — "
            "don't force a loose match just to avoid improvising.\n"
            "IMPORTANT — COLOR/DIM preset recall syntax: 'COLOR n' and 'DIM "
            "PRESET n' only work as their OWN prog action, sent AFTER a "
            "separate prog action that makes the selection. Combining them "
            "in one command string (e.g. \"1.1 COLOR 3\") does NOT recall "
            "the preset — 'COLOR' there is parsed as a moving-light colour-"
            "wheel channel instead, silently NOT applying the saved RGB. "
            "So a request like \"1.1 green\", when pools.color has a preset "
            "named Green (id 3), must be TWO prog actions in the array: "
            "[{\"action\":\"prog\",\"cmd\":\"1.1\"}, "
            "{\"action\":\"prog\",\"cmd\":\"COLOR 3\"}] — never "
            "\"1.1 COLOR 3\" as a single cmd string. Same two-step rule for "
            "DIM PRESET n.\n"
            "Be cautious with clearly destructive, hard-to-undo commands "
            "(PATCH REMOVE, DELETE FORM/RATE/SIZEP/SPREADP, CLEAR <pool> n, "
            "stk N CLEAR) — only use those when the user explicitly asked for "
            "that specific removal, never as an improvised part of a creative "
            "lighting request.\n\n"
            "House style, when interpreting a creative request: build looks "
            "incrementally (select, set colour, set dim, set movement) rather "
            "than one giant blast of every fixture at once. Vary cue timing "
            "intentionally — a moody wash and a hard snap cue should not "
            "share the same fade time. Think in terms of contrast and "
            "balance, not just colour: a look with a few fixtures lit and the "
            "rest dark often reads better than everything matching. For a "
            "vague request like 'moody' or 'dramatic', lean toward slower "
            "fades (2-4s) and lower saturation/dim; for 'energetic' or "
            "'party', faster and brighter. Prefer fewer, more decisive "
            "changes over constant small tweaks.\n\n"
            "This is a real conversation, not one-shot requests — a short "
            "window of your own recent turns (prompt + your reply, exactly "
            "as you sent it) is included as prior messages below, so you can "
            "answer follow-ups like 'why didn't that work' or 'what did you "
            "mean' with actual continuity instead of guessing fresh each "
            "time. Use the \"say\" action (see ACTION_SCHEMA) whenever the "
            "operator is asking you something rather than asking you to do "
            "something — including asking what you'd need from them to do a "
            "request properly, or why a previous result wasn't what they "
            "wanted. Don't force a request into actions that don't fit it "
            "just to avoid returning an empty-ish array; a \"say\" asking "
            "for clarification is a better answer than a wrong guess.\n\n"
            "FULL COMMAND REFERENCE (this is the real command vocabulary — "
            "read it before assuming a capability doesn't exist):\n"
            + self._command_ref + "\n\n"
            "The console state includes recent_commands — the last few commands the "
            "operator ran. Use them to resolve pronouns and implicit references: "
            "if the user says 'them', 'those', 'it', or 'same fixtures', infer "
            "the target from fixture IDs visible in recent commands or programmer state. "
            "If the user says 'do it again' or 'same but slower', repeat/modify the "
            "most recent relevant action. When in doubt, use group_select or prog actions "
            "that target the fixtures most recently mentioned.\n\n"
            + self.ACTION_SCHEMA
        )
        user_msg = f"Console state:\n{state_json}\n\nRequest: {prompt}"
        # Prior turns carry just the bare prompt/reply text, not a repeated
        # state_json — only the live request below needs current state, and
        # replaying old snapshots on every turn would grow tokens for no
        # benefit. See _push_chat_history().
        messages = list(self._chat_history) + [{"role": "user", "content": user_msg}]

        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=system,
                messages=messages,
                timeout=30.0,
                # DeepSeek's models think by default (unlike Claude, where
                # it's opt-in) — a ThinkingBlock then leads resp.content,
                # which has no .text attribute at all, so a bare
                # content[0].text would AttributeError on every DeepSeek
                # request. We want fast, deterministic JSON here, not
                # chain-of-thought, so disable it outright; harmless
                # no-op against real Anthropic, which already defaults
                # to this for a non-extended-thinking model.
                thinking={"type": "disabled"},
            )
            _text_block = next(
                (b for b in resp.content if getattr(b, "text", None) is not None),
                None)
            if _text_block is None:
                raise ValueError(f"no text block in response: {resp.content!r}")
            raw = _text_block.text.strip()
            # Strip markdown code fences if model wraps in them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            try:
                actions = json.loads(raw)
            except json.JSONDecodeError:
                # The model replied with plain prose instead of the
                # required JSON action array — happens even with the
                # system prompt's "always JSON" rule, especially on a
                # conversational/explanatory turn (e.g. answering "why
                # did that happen") rather than a request to act. That
                # used to surface as a bare "AI error: Expecting value:
                # line 1 column 1 (char 0)" and silently threw away
                # whatever the model actually said. Treat the raw text as
                # a spoken reply instead — the say-action branch below
                # already renders it exactly like a normal chat response.
                actions = [{"action": "say", "text": raw}] if raw else []
            self._push_chat_history(prompt, raw)
            # Report token usage
            try:
                in_tok  = resp.usage.input_tokens
                out_tok = resp.usage.output_tokens
                if self._token_cb:
                    self._token_cb(in_tok, out_tok)
            except Exception:
                in_tok = out_tok = 0
            if self._log:
                self._log(f"AI → {len(actions)} action(s)  [{in_tok}↑ {out_tok}↓ tok]")
                for a in actions:
                    act = a.get("action", "?")
                    if act == "say":
                        # Shown here (not re-logged by execute()) — free text
                        # meant for the operator to actually read, not a
                        # key=value action dump.
                        self._log(f"  AI: {a.get('text', '')}")
                        continue
                    detail = ", ".join(f"{k}={v}" for k, v in a.items() if k != "action")
                    self._log(f"  {act}  {detail}")
            else:
                print(f"\n  AI → {len(actions)} action(s):")
                for a in actions:
                    print(f"    {a}")
            if execute:
                self.execute(actions)
            return actions
        except Exception as e:
            msg = f"AI error: {e}"
            if self._log:
                self._log(msg)
            else:
                print(f"\n  {msg}")
            return []

    def _exec_for_stack(self, stack_id):
        """
        Resolve a stack id (as used in ACTION_SCHEMA's "stack" field and
        in _state()'s stacks section) to the fader slot it's actually
        assigned to. Falls back to a same-numbered fader slot if no
        fader currently has that stack assigned (preserves the
        default 1:1 stack/fader wiring set up at startup).
        """
        if not self._fader_pool:
            return None
        for ex in self._fader_pool.faders.values():
            if ex.stack and ex.stack.stack_id == stack_id:
                return ex
        return self._fader_pool.get(stack_id)

    def _fire(self, ex, fire_fn, *args):
        """
        Fire a cue via one of Fader.go/back/goto, applying a pending
        fade_time override (if any) for just this one fire, then logging
        the result (including failures like 'no stack assigned', which
        were previously discarded silently).
        """
        if self._last_fade is not None:
            prev = (ex.time_override_on, ex.time_override_fade, ex.time_override_delay)
            ex.time_override_on    = True
            ex.time_override_fade  = self._last_fade
            ex.time_override_delay = 0.0
            try:
                msg = fire_fn(*args)
            finally:
                (ex.time_override_on, ex.time_override_fade,
                 ex.time_override_delay) = prev
            self._last_fade = None
        else:
            msg = fire_fn(*args)
        if msg and self._log:
            self._log(f"  → {msg}")
        return msg

    def _run_cmd(self, cmd_str):
        """Run a command string through the real parser, exactly the way
        every self._cmd(...) call site in execute() below needs to: log
        the result (was silently discarded before -- if the model's
        generated command had a typo or hit a "usage: ..." error, nothing
        showed up anywhere, no feedback for the operator or a chance for
        a follow-up prompt to course-correct) and push it into
        _cmd_history so a follow-up prompt in the same conversation
        ("now make it slower") sees what the AI itself just did, not just
        whatever the operator last typed by hand."""
        if not self._cmd:
            return None
        result = self._cmd(cmd_str)
        self.push_cmd_history(cmd_str)
        if result and self._log:
            self._log(f"  → {result}")
        return result

    def execute(self, actions):
        """Run a list of action dicts on the console."""
        for a in actions:
            try:
                act = a.get("action", "")
                if act == "prog":
                    if self._cmd:
                        self._run_cmd(a["cmd"])
                    else:
                        self._prog.execute(a["cmd"])
                elif act == "goto_cue":
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._fader_pool.bump_priority(ex.fdr_id)
                        self._fire(ex, ex.goto, a["num"], self._patch, self._fade)
                elif act == "cue_go":
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._fader_pool.bump_priority(ex.fdr_id)
                        self._fire(ex, ex.go, self._patch, self._fade)
                elif act == "cue_back":
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._fader_pool.bump_priority(ex.fdr_id)
                        self._fire(ex, ex.back, self._patch, self._fade)
                elif act == "dim":
                    # Clamp like every sibling dim-setter (programmer.set_dimmer,
                    # the GUI fixture-dim slider, MasterFixture.set_dimmer) --
                    # this value comes straight from the model's JSON with no
                    # bounds of its own. Unclamped, an out-of-range value here
                    # is invisible live (final DMX render clamps on the way
                    # out) but would persist verbatim into a RECORDed cue --
                    # the same bug class already fixed for HUE SAT/VAL.
                    val = max(0.0, min(1.0, float(a["value"])))
                    for master in self._patch.all_fixtures():
                        self._output.programmer_layer.setdefault(
                            str(master.fixture_id), {})['dim'] = val
                        master.set_dimmer(val)
                elif act == "fx_start":
                    # Route through run_command so it goes into the programmer
                    # (channel-additive, doesn't wipe other running FX)
                    wf  = a.get("waveform", "sine").upper()
                    ch  = a.get("channel",  "red").upper()
                    bpm = float(a.get("bpm",    60))
                    sz  = float(a.get("size",  100))
                    sp  = float(a.get("spread", 0.0))
                    cmd = f"FX {wf} {ch} BPM {bpm:.1f} SIZE {sz:.0f} SPREAD {sp:.1f}"
                    if self._cmd:
                        self._run_cmd(cmd)
                    else:
                        all_s = [s for m in self._patch.all_fixtures()
                                 for s in m.all_subs()]
                        self._fx.add(
                            1, a.get("waveform", "sine"), a.get("channel", "red"),
                            rate_bpm=bpm, size=sz, targets=all_s, spread=sp
                        )
                elif act == "cue_fire" and "num" in a:
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._fader_pool.bump_priority(ex.fdr_id)
                        self._fire(ex, ex.goto, float(a["num"]), self._patch, self._fade)
                elif act == "group_select":
                    if self._cmd:
                        self._run_cmd(f"GROUP {a['group']}")
                elif act == "fx_stop":
                    ch = a.get("channel")
                    if self._cmd:
                        self._run_cmd(f"FX CLEAR {ch.upper()}" if ch else "FX CLEAR")
                    else:
                        self._fx.clear()
                elif act == "exec_level":
                    if self._fader_pool and self._cmd:
                        self._run_cmd(f"FADER {a.get('fdr', 1)} LEVEL {float(a.get('level', 1.0)) * 100:.0f}")
                elif act == "fx_clear":
                    # Route through the real FX CLEAR handler — it both stops
                    # the FX engine layers *and* clears the programmer's
                    # pending 'fx' defs, so a rebuild tick can't resurrect
                    # them. self._fx.clear() alone did neither correctly:
                    # it also wiped fader-owned cue FX layers whose ids
                    # are tracked separately in ex._fx_ids.
                    if self._cmd:
                        self._run_cmd("FX CLEAR")
                    else:
                        self._fx.clear()
                elif act == "fade_time":
                    # Applied once, to whichever cue-fire action follows in
                    # this same batch (see _fire()) — not a standing default.
                    self._last_fade = float(a["seconds"])
                elif act == "say":
                    # Free text for the operator, already shown in ask()'s
                    # action log (see the "say" special-case there) —
                    # nothing to execute on the console.
                    pass
            except Exception as e:
                print(f"  AI execute error ({a}): {e}")


__all__ = ["AIEngine"]