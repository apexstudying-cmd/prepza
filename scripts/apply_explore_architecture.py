from pathlib import Path

# The current App.tsx already owns the consolidated Explore surface.
# This build step is intentionally a no-op so CI never rewrites that source
# with the obsolete pre-consolidation Explore implementation.
APP = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'App.tsx'
print('Explore architecture: current App source is authoritative; skipping legacy transform.')
