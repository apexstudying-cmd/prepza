from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP_SCREEN = ROOT / "frontend" / "src" / "shop" / "ShopScreen.tsx"


def test_listing_cards_are_semantic_keyboard_operable_buttons():
    source = SHOP_SCREEN.read_text(encoding="utf-8")
    card_start = source.index("const card =")
    card_end = source.index("\n\n  if (loading", card_start)
    card = source[card_start:card_end]

    assert "<button" in card
    assert 'aria-label={' in card
    assert "onClick={() => openDetail(item)}" in card
    assert "type=\"button\"" in card


def test_browse_filters_have_one_tap_clear_and_visible_active_state():
    source = SHOP_SCREEN.read_text(encoding="utf-8")
    browse_start = source.index("{page === 'browse' && <>")
    browse_end = source.index("\n      {page === 'mine'", browse_start)
    browse = source[browse_start:browse_end]

    assert "activeFilterCount" in browse
    assert "Clear filters" in browse
    assert "setQuery('')" in browse
    assert "setCategory('')" in browse
    assert "setCondition('')" in browse
    assert "setLocation('')" in browse
    assert "setSort('newest')" in browse
    assert "aria-pressed" in browse


def test_filtered_empty_state_offers_clear_filters_and_unfiltered_empty_state_offers_sell_action():
    source = SHOP_SCREEN.read_text(encoding="utf-8")
    browse_start = source.index("{page === 'browse' && <>")
    browse_end = source.index("\n      {page === 'mine'", browse_start)
    browse = source[browse_start:browse_end]

    assert "No listings match these filters" in browse
    assert "No listings yet" in browse
    assert "Sell an item" in browse


def test_shop_primary_navigation_and_listing_cards_meet_touch_target_guidance():
    source = SHOP_SCREEN.read_text(encoding="utf-8")
    assert "minHeight: 44" in source
    assert "minHeight: 44" in source[source.index("const card ="):]
