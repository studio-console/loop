"""Studio Console command dispatcher — the run_command() entry point.

Phase 9 of the run_command split: the original 117-branch dispatcher
(4,265 lines, one giant function) is now 114 small functions across 9
category files (stack/fader/programmer/fx/misc/macro/io/patch/presets),
plus this module, which:

  1. Does the exact preamble the original had (REC->RECORD alias, macro
     recording capture) — unchanged, moved verbatim.
  2. Calls every branch function in the EXACT original top-to-bottom
     order, stopping at the first one that returns non-None. This
     preserves the original file's first-match-wins semantics exactly,
     including cases where the same token (RECORD x9, GO x4, CLEAR x5,
     PROGRAMMER x9...) is handled by multiple independent, non-adjacent
     `if` blocks that ended up in different category files after the
     split — order here is NOT "all of stack.py's branches, then all of
     fader.py's", it's the literal original sequence, interleaved across
     files as needed.
  3. Falls through to the original default case (forward to the
     programmer) if nothing matched — also moved verbatim.

Each branch function takes (t0, tokens, raw) and returns either a result
string (branch matched and handled the command) or None (branch's
condition didn't match — try the next one). None is unambiguous as "not
handled": verified the original file never does a bare `return` or
`return None` anywhere in run_command — every branch always returns an
actual string once its condition is met, even if empty ("").
"""

from .stack import (
    cmd_006_stack_select,
    cmd_007_record_stack_settings,
    cmd_009_assign_stk_to,
    cmd_017_go_fade,
    cmd_018_go,
    cmd_019_back,
    cmd_020_goto,
    cmd_021_reload,
    cmd_022_delete_cue,
    cmd_023_delete_other,
    cmd_024_record_stk_cue,
    cmd_025_record_cue,
    cmd_026_update_alias,
    cmd_027_go_back_stk_no_cue,
    cmd_028_go_stk_cue,
    cmd_073_cues_list,
    cmd_098_cue_note,
    cmd_099_cue_show_info,
    cmd_100_cue_timing,
    cmd_101_stk_cue_timing,
    cmd_102_cue_shift,
    cmd_105_copy_cue_stk,
    cmd_106_move_cue_stk,
    cmd_107_copy_to_variant,
    cmd_125_update_main,
)
from .fader import (
    cmd_010_fader_swap,
    cmd_011_fader_all_clear,
    cmd_012_fader_main,
    cmd_013_page,
    cmd_016_fader_select,
    cmd_094_priority,
    cmd_095_release,
)
from .programmer import (
    cmd_014_prog_time,
    cmd_015_prog_fade_clear,
    cmd_043_snapshot,
    cmd_044_blind,
    cmd_045_live,
    cmd_047_freeze,
    cmd_048_solo,
    cmd_049_park,
    cmd_050_unpark,
    cmd_051_highlight,
    cmd_053_master,
    cmd_054_grandmaster,
    cmd_055_blackout,
    cmd_056_bbo,
    cmd_109_clear_dmx,
    cmd_111_clear_len2,
    cmd_112_clear_len3,
    cmd_113_clear_len1,
    cmd_114_undo,
    cmd_115_programmer_show,
    cmd_116_programmer_capture,
    cmd_117_programmer_save,
    cmd_118_programmer_load,
    cmd_119_programmer_snapshots,
    cmd_120_programmer_scale,
    cmd_121_programmer_stats,
    cmd_122_set_default,
    cmd_123_default,
)
from .fx import (
    cmd_029_form_list,
    cmd_030_record_form,
    cmd_033_bpm,
    cmd_034_tap,
    cmd_035_size,
    cmd_036_spread,
    cmd_037_strobe,
    cmd_038_rainbow,
    cmd_039_fx_main,
    cmd_040_record_fx,
    cmd_041_fire_fx,
    cmd_108_kill_fx,
    cmd_110_clear_fx,
)
from .misc import (
    cmd_042_clone_to,
    cmd_052_output_status,
    cmd_057_show_info,
    cmd_072_status_state,
    cmd_090_list_main,
    cmd_103_rename,
    cmd_124_list_refs,
)
from .macro import (
    cmd_046_macro_main,
)
from .io import (
    cmd_058_backup,
    cmd_059_save,
    cmd_060_load_cue,
    cmd_061_load_show,
    cmd_063_list_shows,
    cmd_064_export_presets,
    cmd_065_import_presets,
    cmd_066_network,
    cmd_067_osc,
    cmd_068_audio,
    cmd_069_midi,
    cmd_070_midi_clock,
    cmd_071_dmx,
)
from .patch import (
    cmd_062_patch_main,
    cmd_091_fixture_swap,
    cmd_092_fixture_groups,
    cmd_093_fixture_info,
    cmd_104_copy_fixture_to,
    cmd_126_viz_layout,
)
from .presets import (
    cmd_074_group,
    cmd_075_record_group,
    cmd_076_color,
    cmd_077_record_color,
    cmd_078_dim,
    cmd_079_record_dim,
    cmd_081_record_attr,
    cmd_082_attr_bare,
    cmd_083_rate,
    cmd_084_sizep,
    cmd_085_spreadp,
    cmd_086_record_rate,
    cmd_087_record_sizep,
    cmd_088_record_spreadp,
    cmd_089_speed,
)

from studio_console.state import _macro_recording, prog


_DISPATCH = [
    cmd_006_stack_select,
    cmd_007_record_stack_settings,
    cmd_009_assign_stk_to,
    cmd_010_fader_swap,
    cmd_011_fader_all_clear,
    cmd_012_fader_main,
    cmd_013_page,
    cmd_014_prog_time,
    cmd_015_prog_fade_clear,
    cmd_016_fader_select,
    cmd_017_go_fade,
    cmd_018_go,
    cmd_019_back,
    cmd_020_goto,
    cmd_021_reload,
    cmd_022_delete_cue,
    cmd_023_delete_other,
    cmd_024_record_stk_cue,
    cmd_025_record_cue,
    cmd_026_update_alias,
    cmd_027_go_back_stk_no_cue,
    cmd_028_go_stk_cue,
    cmd_029_form_list,
    cmd_030_record_form,
    cmd_033_bpm,
    cmd_034_tap,
    cmd_035_size,
    cmd_036_spread,
    cmd_037_strobe,
    cmd_038_rainbow,
    cmd_039_fx_main,
    cmd_040_record_fx,
    cmd_041_fire_fx,
    cmd_042_clone_to,
    cmd_043_snapshot,
    cmd_044_blind,
    cmd_045_live,
    cmd_046_macro_main,
    cmd_047_freeze,
    cmd_048_solo,
    cmd_049_park,
    cmd_050_unpark,
    cmd_051_highlight,
    cmd_052_output_status,
    cmd_053_master,
    cmd_054_grandmaster,
    cmd_055_blackout,
    cmd_056_bbo,
    cmd_057_show_info,
    cmd_058_backup,
    cmd_059_save,
    cmd_060_load_cue,
    cmd_061_load_show,
    cmd_062_patch_main,
    cmd_063_list_shows,
    cmd_064_export_presets,
    cmd_065_import_presets,
    cmd_066_network,
    cmd_067_osc,
    cmd_068_audio,
    cmd_069_midi,
    cmd_070_midi_clock,
    cmd_071_dmx,
    cmd_072_status_state,
    cmd_073_cues_list,
    cmd_074_group,
    cmd_075_record_group,
    cmd_076_color,
    cmd_077_record_color,
    cmd_078_dim,
    cmd_079_record_dim,
    cmd_081_record_attr,
    cmd_082_attr_bare,
    cmd_083_rate,
    cmd_084_sizep,
    cmd_085_spreadp,
    cmd_086_record_rate,
    cmd_087_record_sizep,
    cmd_088_record_spreadp,
    cmd_089_speed,
    cmd_090_list_main,
    cmd_091_fixture_swap,
    cmd_092_fixture_groups,
    cmd_093_fixture_info,
    cmd_094_priority,
    cmd_095_release,
    cmd_098_cue_note,
    cmd_099_cue_show_info,
    cmd_100_cue_timing,
    cmd_101_stk_cue_timing,
    cmd_102_cue_shift,
    cmd_103_rename,
    cmd_104_copy_fixture_to,
    cmd_105_copy_cue_stk,
    cmd_106_move_cue_stk,
    cmd_107_copy_to_variant,
    cmd_108_kill_fx,
    cmd_109_clear_dmx,
    cmd_110_clear_fx,
    cmd_111_clear_len2,
    cmd_112_clear_len3,
    cmd_113_clear_len1,
    cmd_114_undo,
    cmd_115_programmer_show,
    cmd_116_programmer_capture,
    cmd_117_programmer_save,
    cmd_118_programmer_load,
    cmd_119_programmer_snapshots,
    cmd_120_programmer_scale,
    cmd_121_programmer_stats,
    cmd_122_set_default,
    cmd_123_default,
    cmd_124_list_refs,
    cmd_125_update_main,
    cmd_126_viz_layout,
]


def run_command(cmd_str):
    raw    = cmd_str.strip()
    tokens = raw.upper().split()
    if not tokens:
        return ""

    # REC is a shorthand alias for RECORD
    if tokens[0] == 'REC':
        tokens[0] = 'RECORD'

    t0 = tokens[0]

    # ── macro record capture ──────────────────────────────────
    # While recording, capture every command except MACRO STOP / MACRO ABORT.
    # The command still executes normally so the operator sees live feedback.
    if _macro_recording["slot"] is not None:
        is_macro_stop = (t0 == 'MACRO' and len(tokens) >= 2
                         and tokens[1] in ('STOP', 'ABORT'))
        if not is_macro_stop:
            _macro_recording["cmds"].append(raw)

    for branch_fn in _DISPATCH:
        result = branch_fn(t0, tokens, raw)
        if result is not None:
            return result

    # ── Default: programmer ───────────────────────────────────
    try:
        prog.execute(raw)
        return ""   # programmer already prints its own output
    except Exception as e:
        return f"error: {e}"
