from pathlib import Path

from b2b_campaign_metering import _unit_price_minor, record_billable_event


def campaign(**overrides):
    row = {
        "placement": "home_carousel",
        "status": "active",
        "funding_status": "funded",
        "starts_at": None,
        "ends_at": None,
        "currency": "KES",
        "bid_type": "both",
        "bid_kes": 350,
        "target_json": {"billing_modes": ["cpm", "cpc"]},
        "pricing_snapshot": {
            "home_impression_cpm": {"value": {"amount_kes": 350}},
            "click_cpc": {"value": {"amount_kes": 20}},
            "home_frequency_cap": {"value": {"max_impressions": 5, "window_days": 7}},
        },
        "funded_amount_minor": 100000,
        "spent_amount_minor": 0,
    }
    row.update(overrides)
    return row


class Result:
    def __init__(self, mapping=None, scalar=None):
        self.mapping = mapping
        self.scalar_value = scalar

    def mappings(self):
        return self

    def first(self):
        return self.mapping

    def scalar_one_or_none(self):
        return self.scalar_value

    def scalar(self):
        return self.scalar_value


class Nested:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Session:
    def __init__(self, campaign_row, existing=None, prior_impression=False):
        self.campaign_row = campaign_row
        self.existing = existing
        self.prior_impression = prior_impression

    def begin_nested(self):
        return Nested()

    def execute(self, statement, params=None):
        sql = str(statement)
        if "SELECT * FROM discovery_campaign" in sql:
            return Result(mapping=self.campaign_row)
        if "FROM discovery_event" in sql and "event_key" in sql:
            return Result(mapping=self.existing)
        if "FROM discovery_event" in sql and "event_type='impression'" in sql:
            return Result(mapping=( {} if self.prior_impression else None))
        raise AssertionError("Unexpected SQL in regression fixture: " + sql[:180])

    def rollback(self):
        pass

    def commit(self):
        pass


class DB:
    def __init__(self, session):
        self.session = session


def test_podcast_is_a_billable_visual_impression_placement():
    assert _unit_price_minor(campaign(placement="podcast"), "impression") == 35


def test_all_named_discovery_placements_are_billable_for_cpm():
    for placement in ("home_carousel", "explore", "trending", "opportunities_feed", "podcast"):
        assert _unit_price_minor(campaign(placement=placement), "impression") == 35


def test_click_without_prior_impression_is_rejected_before_billing():
    db = DB(Session(campaign(), existing=None, prior_impression=False))
    result = record_billable_event(db, 1, 42, "click", "home_carousel", "click-no-impression")
    assert result == {"ok": False, "reason": "click_without_impression"}


def test_retried_same_event_is_idempotent():
    existing = {"id": 9, "amount_kes": 0.35, "metadata": {"amount_minor": 35}}
    db = DB(Session(campaign(), existing=existing))
    result = record_billable_event(db, 1, 42, "impression", "home_carousel", "same-event")
    assert result["ok"] is True
    assert result["duplicate"] is True
    assert result["amount_minor"] == 35


def test_click_is_not_billable_as_cpm_only():
    assert _unit_price_minor(campaign(target_json={"billing_modes": ["cpm"]}), "click") == 0


def test_frequency_cap_and_user_serialization_are_part_of_atomic_metering():
    source = Path("b2b_campaign_metering.py").read_text(encoding="utf-8")
    assert "SELECT id FROM \"user\" WHERE id=:uid FOR UPDATE" in source
    assert "max_impressions" in source
    assert "window_days" in source
    assert "COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE" in source


def test_click_guard_happens_before_price_and_ledger_work():
    source = Path("b2b_campaign_metering.py").read_text(encoding="utf-8")
    guard = source.index('reason": "click_without_impression"')
    price = source.index("price = _unit_price_minor")
    ledger = source.index("delivery_", price)
    assert guard < price < ledger
