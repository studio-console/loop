import os
import tempfile as _tempfile

# Anchored to the directory containing studio_project.py (one level up from
# this package), not to this file's own directory — studio_data/ and
# studio_saves/ live next to the entry-point script.
_SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR    = os.path.join(_SCRIPT_DIR, "studio_data")
SAVES_DIR   = os.path.join(_SCRIPT_DIR, "studio_saves")

if os.environ.get('STUDIO_HEADLESS') == '1':
    # Automated/unattended smoke-test runs must never read or overwrite the
    # real show — use a throwaway scratch directory so RECORD/GO/save_show
    # during the smoke test can't touch studio_data/*.json.
    DATA_DIR = _tempfile.mkdtemp(prefix="studio_console_headless_")
    print(f"*** STUDIO_HEADLESS — using isolated scratch data dir (not your real show): {DATA_DIR} ***")

os.makedirs(DATA_DIR, exist_ok=True)

# Legacy single-file path (read-only — migrated on first run)
_LEGACY_FILE = os.path.join(_SCRIPT_DIR, "studio_show.json")
