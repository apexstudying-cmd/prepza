from pathlib import Path

from b2b_campaign_metering import _unit_price_minor, record_billable_event
from discovery_billing import _normalize_billable_event_id


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


def test_billable_event_id_requires_a_valid_stable_uuid():
    assert _normalize_billable_event_id("c7e1f4b1-5c3e-4e4b-a9d7-9b90d1f4a001") == "c7e1f4b1-5c3e-4e4b-a9d7-9b90d1f4a001"
    assert _normalize_billable_event_id(None) is None
    assert _normalize_billable_event_id("   ") is None
    assert _normalize_billable_event_id("not-a-uuid") is None
    assert _normalize_billable_event_id("c7e1f4b1-5c3e-4e4b-a9d7-9b90d1f4a001" + "x") is None


def test_sponsored_impression_requires_1500ms_continuous_visibility_and_tab_reset():
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    start = source.index("function SponsoredOpportunityCard")
    end = source.index("const OPP_FILTERS", start)
    component = source[start:end]
    assert "entry.intersectionRatio >= 0.5" in component
    assert "}, 1500)" in component
    assert "visibilitychange" in component
    assert "document.visibilityState" in component


def test_sponsored_click_uses_stable_uuid_without_forcing_an_impression():
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    start = source.index("function SponsoredOpportunityCard")
    end = source.index("const OPP_FILTERS", start)
    component = source[start:end]
    assert "clickEventId" in component
    assert "body: JSON.stringify({ event_id: stableClickId })" in component
    assert "pendingEventId(clickStorageKey, clickEventId)" in component
    assert "Keep the UUID in sessionStorage" in component
    open_start = component.index("const open = async () =>")
    open_end = component.index("\n  return (", open_start)
    assert "await recordImpression()" not in component[open_start:open_end]


def test_sponsored_click_telemetry_is_distinct_from_billable_clicks_and_debounced():
    source = Path("discovery_billing.py").read_text(encoding="utf-8")
    start = source.index('@app.post("/api/discovery/campaigns/<int:campaign_id>/click")')
    end = source.index('@app.post("/api/discovery/campaigns/<int:campaign_id>/application")', start)
    route = source[start:end]
    assert "rawclick:{campaign_id}:{uid}:{supplied_key}" in route
    assert "'click_raw'" in route
    assert "timedelta(milliseconds=750)" in route
    assert '"billable": bool(result.get("ok"))' in route
    assert "record_billable_event(" in route


def test_advertiser_report_has_unique_click_ctr_csv_and_nairobi_dates():
    source = Path("discovery_billing.py").read_text(encoding="utf-8")
    start = source.index('@app.get("/api/organisations/<int:organisation_id>/discovery/report")')
    end = source.index('@app.post("/api/discovery/campaigns/<int:campaign_id>/application")', start)
    route = source[start:end]
    assert "org_access(organisation_id, uid)" in route
    assert "COUNT(DISTINCT user_id)" in route
    assert "raw_clicks" in route
    assert "unique_clicks" in route
    assert "billable_clicks" in route
    assert "unique_ctr_percent" in route
    assert 'request.args.get("format", "").lower() == "csv"' in route
    assert '"text/csv; charset=utf-8"' in route
    assert 'ZoneInfo("Africa/Nairobi")' in source
    assert '"billing_basis": "prepaid campaign ledger"' in route


def test_discovery_target_normalizer_preserves_and_validates_billing_modes():
    source = Path("discovery_billing.py").read_text(encoding="utf-8")
    allowed = source[source.index("ALLOWED_TARGET_KEYS"):source.index("def normalize_target")]
    normalizer_start = source.index("def normalize_target")
    normalizer_end = source.index("def eligible_users", normalizer_start)
    normalizer = source[normalizer_start:normalizer_end]
    assert '"billing_modes"' in allowed
    assert 'raw_target.get("billing_modes")' in normalizer
    assert 'target["billing_modes"]' in normalizer
    assert 'not in ("cpm", "cpc")' in normalizer


def test_sponsored_events_capture_campus_id_for_aggregate_reporting():
    source = Path("b2b_campaign_metering.py").read_text(encoding="utf-8")
    assert 'SELECT university_id FROM "user" WHERE id=:uid' in source
    assert '"campus_id": int(campus_id) if campus_id is not None else None' in source

    discovery = Path("discovery_billing.py").read_text(encoding="utf-8")
    click_start = discovery.index('@app.post("/api/discovery/campaigns/<int:campaign_id>/click")')
    report_start = discovery.index('@app.get("/api/organisations/<int:organisation_id>/discovery/report")')
    report_end = discovery.index('@app.post("/api/discovery/campaigns/<int:campaign_id>/application")', report_start)
    click_route = discovery[click_start:report_start]
    report_route = discovery[report_start:report_end]
    assert '"campus_id": int(campus_id) if campus_id is not None else None' in click_route
    assert '"campus_breakdown"' in report_route
    assert "unique_reach < 10" in report_route
    assert "COUNT(DISTINCT user_id)" in report_route
