"""
Chunk 4 patch (2/N): creates ONLY the 4 new tables (LibraryPublication,
SavedLibraryMaterial, LibraryReport, XpEvent) added by patch_chunk4_models.py.

Does NOT touch any existing table - uses db.metadata.create_all(tables=[...])
scoped to just these 4, so it's safe to run against your real dev/prod DB
without risk of altering anything already there.

Usage (run AFTER patch_chunk4_models.py has been applied):
    cd ~/Desktop/prepza
    python create_chunk4_tables.py
"""

import sys

def main():
    try:
        import app as prepza_app
    except Exception as e:
        print(f"Could not import app.py: {e}")
        return 1

    required = ["LibraryPublication", "SavedLibraryMaterial", "LibraryReport", "XpEvent"]
    missing = [name for name in required if not hasattr(prepza_app, name)]
    assert not missing, (
        f"app.py is missing model(s) {missing} - run patch_chunk4_models.py first."
    )

    tables = [
        prepza_app.LibraryPublication.__table__,
        prepza_app.SavedLibraryMaterial.__table__,
        prepza_app.LibraryReport.__table__,
        prepza_app.XpEvent.__table__,
    ]

    with prepza_app.app.app_context():
        prepza_app.db.metadata.create_all(bind=prepza_app.db.engine, tables=tables)

    print("Created (or confirmed existing): library_publication, saved_library_material, "
          "library_report, xp_event")
    return 0


if __name__ == "__main__":
    sys.exit(main())
