from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(
    str(ROOT / 'scripts' / 'apply_study_navigation_polish.py'),
    run_name='__main__',
)

# Fail the production build if the navigation transformation did not actually
# reach the frontend bundle source. This prevents another silent regression
# where the source patch exists but the build hook never executes it.
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
text = APP.read_text(encoding='utf-8')
required = [
    "localStorage.getItem('prepza-navigation-state')",
    "localStorage.setItem('prepza-navigation-state'",
    'const resumeOffline = () =>',
]
missing = [marker for marker in required if marker not in text]
if missing:
    raise SystemExit('Study navigation polish verification failed: ' + ', '.join(missing))

print('Study navigation polish applied and verified.')
