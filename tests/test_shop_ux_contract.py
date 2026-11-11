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
    assert 'aria-live="polite"' in source
    assert "{hasActiveFilters ? 'Filters applied' : 'Refine your search'}" in source


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
    button_style_start = source.index("  button: {")
    button_style_end = source.index("\n  primary:", button_style_start)
    assert "minHeight: 44" in source[button_style_start:button_style_end]
    assert '<nav aria-label="Shop sections"' in source
    assert "aria-current={page === item.id ? 'page' : undefined}" in source
    header_start = source.index("<header style={{ ...ui.header")
    header_end = source.index("</header>", header_start)
    header = source[header_start:header_end]
    assert "width: 44" in header
    assert "height: 44" in header
    assert "Back to Home" in header and "Back to Shop" in header
    assert "page !== 'browse'" in source[source.index("if (loading && !listings.length"):source.index("  return <div style={ui.root}")]
    load_browse = source[source.index("const loadBrowse = async"):source.index("  const loadMine")]
    assert "} else {\n      setLoading(true)" in load_browse
    assert "setLoading(false)" in load_browse

def test_listing_editor_uses_native_form_validation_and_single_submit_path():
    source = SHOP_SCREEN.read_text(encoding="utf-8")
    create_start = source.index("{page === 'create' &&")
    detail_start = source.index("{page === 'detail' &&", create_start)
    editor = source[create_start:detail_start]

    assert "<form" in editor
    assert "onSubmit=" in editor
    assert "type=\"submit\"" in editor
    assert "required" in editor
    assert "Save & publish" in editor

def test_listing_grids_expand_single_results_instead_of_leaving_empty_columns():
    source = SHOP_SCREEN.read_text(encoding="utf-8")

    assert source.count("repeat(auto-fit,minmax(155px,1fr))") == 4
    assert "repeat(auto-fill,minmax(155px,1fr))" not in source

def test_mobile_browse_keeps_search_visible_and_collapses_secondary_filters():
    source = SHOP_SCREEN.read_text(encoding="utf-8")
    stylesheet = (ROOT / "frontend" / "src" / "shop" / "ShopScreen.css").read_text(encoding="utf-8")

    search = source.index('<Field label="Search products"')
    filters = source.index('id="shop-additional-filters"')
    assert search < filters
    assert 'className="shop-filter-toggle"' in source
    assert "aria-expanded={filtersExpanded}" in source
    assert 'aria-controls="shop-additional-filters"' in source
    compact_stylesheet = " ".join(stylesheet.split())
    assert ".shop-filter-grid { display: none; }" in compact_stylesheet
    assert ".shop-filter-grid.is-expanded { display: grid; }" in compact_stylesheet
    assert "@media (min-width: 640px)" in stylesheet

def test_shop_scroll_content_clears_the_fixed_global_bottom_navigation():
    source = SHOP_SCREEN.read_text(encoding="utf-8")
    wrap_start = source.index("  wrap: {")
    wrap_end = source.index("\n  button:", wrap_start)
    wrap_style = source[wrap_start:wrap_end]

    assert "paddingBottom" in wrap_style
    assert "safe-area-inset-bottom" in wrap_style



def test_shop_tabs_and_listing_cards_follow_prepza_shell_hierarchy():
    source = SHOP_SCREEN.read_text(encoding="utf-8")
    nav_start = source.index('<nav aria-label="Shop sections"')
    nav_end = source.index("</nav>", nav_start)
    nav = source[nav_start:nav_end]
    assert "borderBottom: '1px solid rgba(255,255,255,.12)'" in nav
    assert "background: 'transparent'" in nav
    assert "borderRadius: 0" in nav
    assert "minHeight: 44" in nav
    assert "borderBottom: '2px solid '" in nav

    card_start = source.index("const card =")
    card_end = source.index("\n\n  if (loading", card_start)
    card = source[card_start:card_end]
    assert "borderRadius: 14" in card
    assert card.count("height: 124") == 2
    assert "height: 148" not in card
    assert "fontSize: 16" in card
    assert "fontSize: 13" in card
    assert "fontSize: 11" in card
