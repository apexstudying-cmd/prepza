from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP_SCREEN = ROOT / "frontend" / "src" / "shop" / "ShopScreen.tsx"


def test_listing_cards_are_keyboard_operable_semantic_controls():
    source = SHOP_SCREEN.read_text(encoding="utf-8")

    assert "<button" in source[source.index("const card ="):source.index("\n\n  if (loading")]
    card = source[source.index("const card ="):source.index("\n\n  if (loading")]
    assert "type=\"button\"" in card
    assert "aria-label={`Open listing: ${item.title}`}" in card
    assert "</button>" in card
    assert "<article" not in card


def test_browse_filters_have_one_tap_clear_and_visible_active_state():
    source = SHOP_SCREEN.read_text(encoding="utf-8")

    assert "const hasActiveFilters = Boolean(query.trim() || category || condition || location.trim())" in source
    assert "const clearFilters = () =>" in source
    assert "setQuery('')" in source
    assert "setCategory('')" in source
    assert "setCondition('')" in source
    assert "setLocation('')" in source
    assert "Clear filters" in source
    assert "aria-pressed={hasActiveFilters}" in source


def test_filtered_empty_state_explains_how_to_recover():
    source = SHOP_SCREEN.read_text(encoding="utf-8")

    assert "No listings match these filters" in source
    assert "Clear filters to see all listings" in source
    assert "No listings yet" in source


def test_shop_navigation_and_listing_loading_reserve_accessible_touch_targets():
    source = SHOP_SCREEN.read_text(encoding="utf-8")

    nav_start = source.index("{nav.map(item =>")
    nav_end = source.index("</div>", nav_start)
    assert "minHeight: 44" in source[nav_start:nav_end]
    assert 'aria-busy={loading}' in source
    assert "aria-label=\"Loading listings\"" in source
    assert "minHeight: 44" in source[source.index("function ShopButton"):source.index("function Field")]
    header_start = source.index("<header style={{ ...ui.header")
    header_end = source.index("</header>", header_start)
    header = source[header_start:header_end]
    assert "width: 44" in header
    assert "height: 44" in header
    assert "Back to Home" in header and "Back to Shop" in header
    assert "page !== 'browse'" in source[source.index("if (loading && !listings.length"):source.index("  return <div style={ui.root}")]
    assert "if (!cached) setLoading(true)" in source
    assert "setLoading(false)" in source[source.index("const loadBrowse = async"):source.index("  const loadMine")]
