from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(
    str(ROOT / 'scripts' / 'apply_study_navigation_polish.py'),
    run_name='__main__',
)
