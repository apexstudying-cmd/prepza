import { N } from '../theme/theme'
import { AdminCard } from './AdminShared'
import type { AdminPlatformSettings } from './AdminShared'
import B2BFinanceAdmin from './B2BFinanceAdmin'
import AdminOperationsDashboard from './AdminOperationsDashboard'
import { AdminAmbassadorsPanel, AdminOpportunitiesPanel, AdminPromotionsPanel, AdminOrganisationsPanel, AdminGroupsPanel, AdminUniversitiesPanel, AdminCommunityPanel } from './AdminPanels'
import { useAdminSectionController } from './useAdminSectionController'
import { AdminDashboardSection, AdminUsersSection, AdminContentSection, AdminAiUsageSection, AdminPaymentsSection, AdminModerationSection, AdminAnalyticsSection } from './AdminSectionCoreViews'
import { AdminSystemSection, AdminCommunicationsSection } from './AdminSectionPlatformViews'

// Screen dispatch only; the controller retains state, effects, and API ownership.
export default function AdminSection({ section, setSection }: { section: string; setSection: (section: string) => void }) {
  const controller = useAdminSectionController(section, setSection)
  const { mode, T, settingsDraft, setSettingsDraft, settingsLoading, settingsError, settingsSaving, settingsSaveError, settingsSaved, setPrepzaControlEnabled, savePlatformSettings } = controller

  if (section === 'dashboard') return <AdminDashboardSection controller={controller} />
  
    if (section === 'users') return <AdminUsersSection controller={controller} />
  
    if (section === 'content') return <AdminContentSection controller={controller} />
  
    if (section === 'ai-usage') return <AdminAiUsageSection controller={controller} />
  
    if (section === 'b2b-finance') {
      return <B2BFinanceAdmin tokens={T} />
    }
  
    if (section === 'payments') return <AdminPaymentsSection controller={controller} />
  
    if (section === 'moderation') return <AdminModerationSection controller={controller} />
  
    if (section === 'analytics') return <AdminAnalyticsSection controller={controller} />
  
    if (section === 'operations') return <AdminOperationsDashboard />
  
    if (section === 'system') return <AdminSystemSection controller={controller} />
  
    if (section === 'settings') {
      const numField = (label: string, key: keyof AdminPlatformSettings, opts?: { allowNull?: boolean; prefix?: string }) => (
        <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '10px 0', borderBottom: `1px solid ${T.border}` }}>
          <span style={{ fontSize: 13, color: T.text, fontWeight: 600 }}>{label}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {opts?.prefix && <span style={{ fontSize: 12, color: T.textMuted }}>{opts.prefix}</span>}
            <input
              type="text"
              value={settingsDraft ? (settingsDraft[key] == null ? '' : String(settingsDraft[key])) : ''}
              placeholder={opts?.allowNull ? 'Unlimited' : ''}
              onChange={e => {
                if (!settingsDraft) return
                const raw = e.target.value.replace(/[^0-9.]/g, '')
                const num = raw === '' ? (opts?.allowNull ? null : 0) : Number(raw)
                setSettingsDraft({ ...settingsDraft, [key]: num as any })
              }}
              style={{ width: 100, textAlign: 'right', border: `1px solid ${T.border}`, borderRadius: 8, padding: '6px 10px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }}
            />
          </div>
        </div>
      )
      return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {settingsLoading ? (
          <div style={{ padding: '24px 0', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading settings…</div>
        ) : settingsError ? (
          <div style={{ padding: '24px 0', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{settingsError}</div>
        ) : settingsDraft && (
          <>
            <AdminCard title="Maintenance Mode">
              <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                  <input type="checkbox" checked={settingsDraft.maintenance_mode} onChange={e => setSettingsDraft({ ...settingsDraft, maintenance_mode: e.target.checked })} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: T.text }}>Put the app into maintenance mode</span>
                </label>
                <textarea
                  value={settingsDraft.maintenance_message}
                  onChange={e => setSettingsDraft({ ...settingsDraft, maintenance_message: e.target.value })}
                  placeholder="Message shown to users while in maintenance mode…"
                  rows={3}
                  maxLength={500}
                  style={{ border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, resize: 'vertical' }}
                />
              </div>
            </AdminCard>
  
            <AdminCard title="Prepza Control Access">
              <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.55 }}>
                  Controls the private developer API used by trusted Prepza tooling. It is disabled by default and still requires a separate server-side token.
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>{settingsDraft.prepza_control_enabled ? 'Control access is ON' : 'Control access is OFF'}</div>
                    <div style={{ fontSize: 11, color: T.textMuted, marginTop: 3 }}>
                      {settingsDraft.prepza_control_enabled ? 'The API can be reached only with the server-side bearer token.' : 'All control API requests are rejected immediately.'}
                    </div>
                  </div>
                  <button
                    onClick={() => setPrepzaControlEnabled(!settingsDraft.prepza_control_enabled)}
                    disabled={settingsSaving}
                    style={{ background: settingsDraft.prepza_control_enabled ? '#DC2626' : '#16A34A', color: '#fff', border: 'none', borderRadius: 10, padding: '9px 16px', cursor: settingsSaving ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 12, opacity: settingsSaving ? 0.6 : 1 }}
                  >{settingsSaving ? 'Updating…' : (settingsDraft.prepza_control_enabled ? 'Disable Control Access' : 'Enable Control Access')}</button>
                </div>
                <div style={{ fontSize: 11, color: '#92400E', background: '#FEF3C7', borderRadius: 8, padding: '8px 10px' }}>
                  Keep this OFF unless you are actively using the trusted control connection.
                </div>
              </div>
            </AdminCard>
  
            <AdminCard title="Content Prices (KES)">
              <div style={{ padding: '4px 18px 8px' }}>
                {numField('Notes', 'price_notes', { prefix: 'KES' })}
                {numField('Past Paper', 'price_past_paper', { prefix: 'KES' })}
                {numField('Q&A', 'price_qna', { prefix: 'KES' })}
                {numField('Opportunity — Standard', 'price_promotion_standard', { prefix: 'KES' })}
                {numField('Opportunity — Featured', 'price_promotion_featured', { prefix: 'KES' })}
                {numField('Opportunity — Sponsored', 'price_promotion_sponsored', { prefix: 'KES' })}
              </div>
              <div style={{ padding: '0 18px 14px', fontSize: 11, color: T.textMuted }}>
                Promotion prices are snapshotted when an organisation submits a request. Changing these prices affects new requests, not existing campaigns.
              </div>
            </AdminCard>
  
            <AdminCard title="AI Daily Limits">
              <div style={{ padding: '4px 18px 8px' }}>
                {numField('Chat — Free tier', 'ai_daily_limit_free', { allowNull: true })}
                {numField('Chat — Plus tier', 'ai_daily_limit_plus', { allowNull: true })}
                {numField('Chat — Premium tier', 'ai_daily_limit_premium', { allowNull: true })}
                {numField('Tutor — Free tier', 'ai_daily_tutor_limit_free', { allowNull: true })}
                {numField('Tutor — Plus tier', 'ai_daily_tutor_limit_plus', { allowNull: true })}
                {numField('Tutor — Premium tier', 'ai_daily_tutor_limit_premium', { allowNull: true })}
              </div>
              <div style={{ padding: '0 18px 14px', fontSize: 11, color: T.textMuted }}>Leave blank for unlimited.</div>
            </AdminCard>
  
            <AdminCard title="AI Monthly Budget">
              <div style={{ padding: '4px 18px 8px' }}>
                {numField('Budget (USD)', 'ai_monthly_budget_usd', { prefix: '$' })}
              </div>
            </AdminCard>
  
            {settingsSaveError && <div style={{ color: '#DC2626', fontSize: 12 }}>{settingsSaveError}</div>}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <button
                disabled={settingsSaving}
                onClick={savePlatformSettings}
                style={{ background: N.navy, color: '#fff', border: 'none', borderRadius: 10, padding: '10px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, opacity: settingsSaving ? 0.6 : 1 }}
              >{settingsSaving ? 'Saving…' : 'Save Settings'}</button>
              {settingsSaved && !settingsSaving && <span style={{ fontSize: 12, color: '#16A34A', fontWeight: 600 }}>Saved.</span>}
            </div>
          </>
        )}
      </div>
      )
    }
  
    if (section === 'groups') return <AdminGroupsPanel />
  
    if (section === 'ambassadors') return <AdminAmbassadorsPanel />
  
    if (section === 'communications') return <AdminCommunicationsSection controller={controller} />
  
    if (section === 'opportunities') return <AdminOpportunitiesPanel />
  
    if (section === 'promotions') return <AdminPromotionsPanel />
  
    if (section === 'organisations') return <AdminOrganisationsPanel />
  
    if (section === 'universities') return <AdminUniversitiesPanel />
  
    if (section === 'community') return <AdminCommunityPanel />
  
}
