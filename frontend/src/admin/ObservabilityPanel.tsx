import { useCallback, useEffect, useState } from 'react'

type ObservabilityEvent = {
  request_id: string
  method: string
  route: string
  status_code: number
  duration_ms: number | null
  occurred_at: string | null
}
type ObservabilityData = {
  status: string
  window_minutes: number
  summary: { recent_5xx: number; recent_slow: number; events_last_hour: number }
  alerts: { key: string; severity: string; count: number; threshold: number; window_minutes: number; message: string }[]
  recent_events: ObservabilityEvent[]
}

function Metric({ label, value, hint }: { label: string; value: string | number; hint: string }) {
  return <div style={{ background: 'rgba(127,127,127,.07)', borderRadius: 10, padding: '12px 14px', minWidth: 0 }}>
    <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: .4, opacity: .6 }}>{label}</div>
    <div style={{ fontSize: 21, fontWeight: 800, marginTop: 3 }}>{value}</div>
    <div style={{ fontSize: 10, opacity: .6, marginTop: 3 }}>{hint}</div>
  </div>
}

export default function ObservabilityPanel() {
  const [data, setData] = useState<ObservabilityData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    fetch('/admin/observability', { credentials: 'include' })
      .then(async response => {
        const body = await response.json()
        if (!response.ok) throw new Error(body.error || 'Observability data is unavailable')
        return body as ObservabilityData
      })
      .then(setData)
      .catch(value => setError(value instanceof Error ? value.message : 'Observability data is unavailable'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  return <section style={{ background: 'var(--prepza-card,#fff)', border: '1px solid var(--prepza-border,#E5E7EB)', borderRadius: 14, padding: 18 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 14 }}>
      <div>
        <div style={{ fontWeight: 800, fontSize: 14 }}>HTTP observability</div>
        <div style={{ fontSize: 11, opacity: .6, marginTop: 3 }}>Request correlation, server errors and slow endpoints. No request bodies or query strings are stored.</div>
      </div>
      <button onClick={load} disabled={loading} style={{ padding: '7px 10px', border: '1px solid var(--prepza-border,#E5E7EB)', background: 'transparent', borderRadius: 8, cursor: loading ? 'wait' : 'pointer', flexShrink: 0 }}>
        {loading ? 'Loading…' : 'Refresh'}
      </button>
    </div>

    {error ? <div role="status" style={{ borderRadius: 10, padding: 12, background: '#FEF3C7', color: '#92400E', fontSize: 12 }}>
      {error}. Apply the request-observability migration if this is a new deployment.
    </div> : loading && !data ? <div style={{ fontSize: 12, opacity: .65 }}>Loading request metrics…</div> : data ? <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 8, marginBottom: 12 }}>
        <Metric label="5xx · 5m" value={data.summary.recent_5xx} hint="Server errors" />
        <Metric label="Slow · 5m" value={data.summary.recent_slow} hint="At least 5 seconds" />
        <Metric label="Events · 1h" value={data.summary.events_last_hour} hint="Errors and slow requests" />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginBottom: 14 }}>
        {data.alerts.length === 0 ? <div style={{ border: '1px solid var(--prepza-border,#E5E7EB)', borderRadius: 10, padding: 11, fontSize: 12 }}>
          No active HTTP error/latency alerts in the last {data.window_minutes} minutes.
        </div> : data.alerts.map(alert => <div key={alert.key} role="status" style={{ background: alert.severity === 'critical' ? '#FEE2E2' : '#FEF3C7', color: alert.severity === 'critical' ? '#991B1B' : '#92400E', borderRadius: 10, padding: 11 }}>
          <div style={{ fontSize: 11, fontWeight: 850, textTransform: 'uppercase' }}>{alert.severity} · {alert.count} / threshold {alert.threshold}</div>
          <div style={{ fontSize: 12, marginTop: 3 }}>{alert.message}</div>
        </div>)}
      </div>

      <div style={{ fontWeight: 750, fontSize: 12, marginBottom: 7 }}>Recent request events</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
          <thead><tr style={{ textAlign: 'left', opacity: .55 }}>
            <th style={{ padding: '6px' }}>Time</th><th style={{ padding: '6px' }}>Route</th><th style={{ padding: '6px' }}>Status</th><th style={{ padding: '6px' }}>Latency</th><th style={{ padding: '6px' }}>Request ID</th>
          </tr></thead>
          <tbody>{data.recent_events.map(event => <tr key={event.request_id + event.occurred_at}>
            <td style={{ padding: '7px 6px', borderTop: '1px solid var(--prepza-border,#E5E7EB)', whiteSpace: 'nowrap' }}>{event.occurred_at ? new Date(event.occurred_at + (event.occurred_at.endsWith('Z') ? '' : 'Z')).toLocaleString() : '—'}</td>
            <td style={{ padding: '7px 6px', borderTop: '1px solid var(--prepza-border,#E5E7EB)', minWidth: 180 }}>{event.method} {event.route}</td>
            <td style={{ padding: '7px 6px', borderTop: '1px solid var(--prepza-border,#E5E7EB)', color: event.status_code >= 500 ? '#B91C1C' : 'inherit', fontWeight: 750 }}>{event.status_code}</td>
            <td style={{ padding: '7px 6px', borderTop: '1px solid var(--prepza-border,#E5E7EB)', whiteSpace: 'nowrap' }}>{event.duration_ms == null ? '—' : Math.round(event.duration_ms) + ' ms'}</td>
            <td style={{ padding: '7px 6px', borderTop: '1px solid var(--prepza-border,#E5E7EB)', fontFamily: 'monospace', fontSize: 10 }}>{event.request_id}</td>
          </tr>)}</tbody>
        </table>
      </div>
      {data.recent_events.length === 0 && <div style={{ fontSize: 11, opacity: .6, marginTop: 8 }}>No slow/error events have been captured yet.</div>}
      <div style={{ fontSize: 10, opacity: .55, marginTop: 10 }}>Alerts are shown in this admin panel and emitted as structured server logs. External email/pager delivery is not configured by this feature.</div>
    </> : null}
  </section>
}
