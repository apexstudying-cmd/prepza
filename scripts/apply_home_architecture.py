"""Compatibility entry point for the module-owned Home architecture check."""
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / 'scripts' / 'apply_home_architecture_v2.py'), run_name='__main__')
