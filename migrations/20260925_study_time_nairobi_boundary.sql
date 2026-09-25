-- Study-time calendar boundary is Nairobi time (Africa/Nairobi).
-- The application owns activity_date values; this helper gives SQL/reporting
-- one canonical conversion instead of relying on the database session timezone.
CREATE OR REPLACE FUNCTION prepza_nairobi_date(ts TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)
RETURNS DATE
LANGUAGE SQL
STABLE
AS $$
  SELECT (ts AT TIME ZONE 'Africa/Nairobi')::date;
$$;

COMMENT ON FUNCTION prepza_nairobi_date(TIMESTAMPTZ)
IS 'Canonical Prepza study calendar date in Africa/Nairobi.';