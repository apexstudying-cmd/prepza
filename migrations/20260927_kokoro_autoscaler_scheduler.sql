-- Safe scheduler hook for the Kokoro autoscaler.
--
-- Supabase pg_cron + pg_net can wake the existing Prepza control plane every
-- minute without creating a permanently-running Render service. Render Cron
-- would have a $1/month minimum, so it is intentionally not required here.
--
-- The job is harmless until BOTH Vault secrets exist:
--   prepza_autoscaler_base_url  = https://prepza-sf60.onrender.com
--   prepza_autoscaler_token     = the KOKORO_CONTROL_TOKEN value
--
-- Store them in Supabase Vault; never put the control token in SQL source.
-- Then this migration's scheduled job will start calling /internal/kokoro/reconcile.
BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

CREATE OR REPLACE FUNCTION public.prepza_kokoro_autoscaler_tick()
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault, net
AS $$
DECLARE
  base_url TEXT;
  control_token TEXT;
BEGIN
  SELECT decrypted_secret INTO base_url
  FROM vault.decrypted_secrets
  WHERE name = 'prepza_autoscaler_base_url'
  LIMIT 1;

  SELECT decrypted_secret INTO control_token
  FROM vault.decrypted_secrets
  WHERE name = 'prepza_autoscaler_token'
  LIMIT 1;

  IF COALESCE(base_url, '') = '' OR COALESCE(control_token, '') = '' THEN
    RETURN NULL;
  END IF;

  RETURN net.http_post(
    url := rtrim(base_url, '/') || '/internal/kokoro/reconcile',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || control_token
    ),
    body := jsonb_build_object('source', 'supabase_pg_cron'),
    timeout_milliseconds := 5000
  );
END;
$$;

REVOKE ALL ON FUNCTION public.prepza_kokoro_autoscaler_tick() FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'prepza-kokoro-autoscaler') THEN
    PERFORM cron.unschedule('prepza-kokoro-autoscaler');
  END IF;

  PERFORM cron.schedule(
    'prepza-kokoro-autoscaler',
    '* * * * *',
    $job$SELECT public.prepza_kokoro_autoscaler_tick();$job$
  );
END;
$$;

COMMIT;
