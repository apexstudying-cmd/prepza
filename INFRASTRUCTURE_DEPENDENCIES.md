# Prepza infrastructure dependency register

This is the launch dependency register. The Admin → Infrastructure endpoint returns the same dependency IDs with live/configuration status and an upgrade trigger.

| Dependency | Purpose | What to monitor | When to consider paying/upgrading |
|---|---|---|---|
| Render | Web service, runtime, builds | service health, CPU/RAM, bandwidth, build minutes, instance limits | Only when measured runtime/build/bandwidth limits block the product |
| Supabase | PostgreSQL, Storage, Realtime | DB size, storage, egress, realtime connections/messages | When measured usage approaches the active plan ceiling |
| Amazon SES | Transactional email OTP | 24h quota, send rate, rolling usage, sandbox/production state | When SES quota/rate or sandbox restrictions block legitimate users |
| Cloudflare R2 | Audio/object storage | stored GB, operations, transfer/egress | When audio/material storage needs justify migration/expansion |
| Render Key Value / Redis-compatible store | shared cache, queues, distributed rate limits | memory, connection count, queue depth, latency | When multiple instances or queue/cache consistency requires shared state |
| AWS/external TTS fallback | fallback speech generation | minutes/characters, errors, spend | When Kokoro capacity/reliability is insufficient |
| Paystack | subscriptions/payments | successful payments, fees, reversals/refunds | When payment volume/merchant requirements justify plan/business changes |

## Rule

Prepza must not silently upgrade or subscribe to a provider.

Admin should show:
- current status;
- measured usage where API access exists;
- the relevant ceiling/quota;
- the reason an upgrade would become necessary;
- the environment variable/API credential required for live telemetry if it is missing.

Provider credentials are never shown in the student UI and secret values are never committed to Git.
