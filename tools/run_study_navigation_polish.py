from pathlib import Path
import os
import runpy

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
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
    "localStorage.setItem('prepza-navigation-state'",
    'resumeOffline={() => {',
    'const stored = storedNavigation',
]
NAVIGATION = ROOT / 'frontend' / 'src' / 'navigation' / 'useAppNavigation.ts'
navigation_text = NAVIGATION.read_text(encoding='utf-8')
splash = (ROOT / 'frontend' / 'src' / 'screens' / 'onboarding' / 'SplashScreen.tsx').read_text(encoding='utf-8')
missing = [marker for marker in required if marker not in text]
if "localStorage.getItem('prepza-navigation-state')" not in navigation_text:
    missing.append("localStorage.getItem('prepza-navigation-state') in extracted navigation hook")
if "window.history.back()" not in navigation_text:
    missing.append("window.history.back() in extracted navigation hook")
if 'resumeOffline()' not in splash:
    missing.append('resumeOffline() in extracted SplashScreen module')
if missing:
    raise SystemExit('Study navigation polish verification failed: ' + ', '.join(missing))

print('Study navigation polish applied and verified.')
