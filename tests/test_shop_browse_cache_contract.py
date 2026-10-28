from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP_SCREEN = ROOT / "frontend" / "src" / "shop" / "ShopScreen.tsx"


def test_browse_snapshots_strip_viewer_and_moderation_fields():
    source = SHOP_SCREEN.read_text(encoding="utf-8")

    assert "const toPublicBrowseSnapshot =" in source
    helper_start = source.index("const toPublicBrowseSnapshot =")
    helper_end = source.index("\nconst conditionLabel", helper_start)
    helper = source[helper_start:helper_end]

    # The per-tab cache is shared across auth/session changes, so only public
    # listing fields may survive in a snapshot. Viewer flags are reset rather
    # than reusing a prior account's values.
    assert "saved: false" in helper
    assert "is_mine: false" in helper
    assert "posting_payment_reference" not in helper
    assert "posting_payment_review_note" not in helper
    assert "moderation_note" not in helper


def test_browse_cache_writes_sanitized_snapshots_and_falls_back_for_same_query():
    source = SHOP_SCREEN.read_text(encoding="utf-8")

    assert "browseSnapshots.set(cacheKey, { listings: toPublicBrowseSnapshot(fresh), savedAt: Date.now() })" in source
    catch_start = source.index("    } catch (cause) {", source.index("const loadBrowse = async"))
    catch_end = source.index("\n  }\n  const loadMine", catch_start)
    catch_block = source[catch_start:catch_end]

    assert "if (!cached) throw cause" in catch_block
    assert "setListings(filterCurrentListings(cached.listings))" in catch_block
    assert "Showing recently viewed listings. Reconnect to refresh availability and status." in catch_block


def test_public_browse_cache_is_invalidated_after_moderation_changes():
    source = SHOP_SCREEN.read_text(encoding="utf-8")
    moderate_start = source.index("  const moderate = async")
    moderate_end = source.index("  const resolveReport", moderate_start)
    moderate_block = source[moderate_start:moderate_end]

    assert "invalidateBrowseSnapshots()" in moderate_block
