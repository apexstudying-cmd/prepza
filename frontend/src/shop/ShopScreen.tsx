import { useEffect, useRef, useState, type ChangeEvent, type CSSProperties, type ReactNode } from 'react'

type ImageRef = { key: string; url: string | null }
type Listing = { id: number; title: string; description: string | null; category: string; condition: string; price_kes: number; location_area: string; images: ImageRef[]; status: string; seller_id: number; seller_name: string; whatsapp_url?: string | null; saved: boolean; is_mine: boolean; posting_fee_kes: number; posting_fee_paid: boolean; posting_fee_expires_at?: string | null; posting_payment_reference?: string | null; posting_payment_review_note?: string | null; moderation_note?: string | null }
type Page = 'browse' | 'detail' | 'create' | 'mine' | 'saved' | 'admin'
type Props = { setScreen: (screen: any) => void; setActiveConversationId: (id: number) => void }
const CATEGORIES = ['Books & study', 'Electronics', 'Hostel & home', 'Fashion', 'Accessories', 'Sports & fitness', 'Other']
const CONDITIONS = [{ value: 'new', label: 'New' }, { value: 'good', label: 'Good' }, { value: 'fair', label: 'Fair' }, { value: 'for_parts', label: 'For parts / repair' }]
const REASONS = [{ value: 'scam', label: 'Scam or suspicious' }, { value: 'prohibited_item', label: 'Prohibited item' }, { value: 'misleading', label: 'Misleading listing' }, { value: 'harassment', label: 'Harassment' }, { value: 'spam', label: 'Spam or duplicate' }, { value: 'other', label: 'Other' }]
const money = (amount: number) => 'KSh ' + Math.round(amount).toLocaleString('en-KE')

// Public browse snapshots live only in this tab's memory. Never persist account-specific
// saved/is_mine flags or payment/admin responses in browser storage.
const BROWSE_CACHE_TTL_MS = 5 * 60 * 1000
const browseSnapshots = new Map<string, { listings: Listing[]; savedAt: number }>()
const invalidateBrowseSnapshots = () => browseSnapshots.clear()
// Cache only fields safe for public browse. Viewer flags and payment/moderation
// details must never leak across account changes through this module-level cache.
const toPublicBrowseSnapshot = (items: Listing[]): Listing[] => items.map(item => ({
  id: item.id,
  title: item.title,
  description: item.description,
  category: item.category,
  condition: item.condition,
  price_kes: item.price_kes,
  location_area: item.location_area,
  images: (item.images || []).map(image => ({ key: image.key, url: image.url })),
  status: item.status,
  seller_id: item.seller_id,
  seller_name: item.seller_name,
  ...(item.whatsapp_url ? { whatsapp_url: item.whatsapp_url } : {}),
  saved: false,
  is_mine: false,
  posting_fee_kes: item.posting_fee_kes,
  posting_fee_paid: item.posting_fee_paid,
  posting_fee_expires_at: item.posting_fee_expires_at,
}))
const filterCurrentListings = (items: Listing[]) => items.filter(item => item.status === 'active' && Boolean(item.posting_fee_expires_at && Date.parse(item.posting_fee_expires_at) > Date.now()))
const conditionLabel = (value: string) => CONDITIONS.find(item => item.value === value)?.label || value
const ui: Record<string, CSSProperties> = {
  root: { flex: 1, minHeight: 0, overflowY: 'auto', background: 'var(--prepza-generation-page, #F8F9FC)', color: 'var(--prepza-generation-text, #0B1437)', fontFamily: 'Plus Jakarta Sans, system-ui, sans-serif' },
  header: { background: 'linear-gradient(130deg, var(--prepza-brand-navy, #101B35), #24365B)', color: '#fff', padding: '20px 18px 18px' },
  wrap: { width: '100%', maxWidth: 1080, margin: '0 auto', padding: 18, boxSizing: 'border-box' },
  button: { border: 0, borderRadius: 12, padding: '11px 14px', fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12 },
  primary: { background: 'var(--prepza-brand-gold, #C9A84C)', color: 'var(--prepza-brand-navy, #101B35)' },
  secondary: { background: 'var(--prepza-generation-card, #FFFFFF)', color: 'var(--prepza-generation-text, #0B1437)', border: '1px solid var(--prepza-generation-border, #E1E5ED)' },
  input: { width: '100%', boxSizing: 'border-box', border: '1px solid var(--prepza-generation-border, #E1E5ED)', borderRadius: 12, padding: '12px 13px', fontSize: 13, color: 'var(--prepza-generation-text, #0B1437)', background: 'var(--prepza-generation-card, #FFFFFF)', colorScheme: 'var(--prepza-generation-color-scheme, light)' as CSSProperties['colorScheme'], fontFamily: 'inherit' },
  panel: { background: 'var(--prepza-generation-card, #FFFFFF)', border: '1px solid var(--prepza-generation-border, #E1E5ED)', borderRadius: 17, padding: 16 },
}
async function shopApi<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData
  const response = await fetch(path, { credentials: 'include', ...options, headers: { ...(isForm ? {} : { 'Content-Type': 'application/json' }), ...(options.headers || {}) } })
  let body: any = null
  try { body = await response.json() } catch { /* no JSON body */ }
  if (!response.ok) {
    const error = new Error(body?.error || ('Request failed (' + response.status + ')')) as Error & { status?: number; code?: string }
    error.status = response.status
    error.code = body?.code
    throw error
  }
  return body as T
}
function ShopButton({ children, onClick, disabled, secondary = false }: { children: ReactNode; onClick: () => void; disabled?: boolean; secondary?: boolean }) {
  return <button type="button" disabled={disabled} onClick={onClick} style={{ ...ui.button, ...(secondary ? ui.secondary : ui.primary), opacity: disabled ? .55 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}>{children}</button>
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label style={{ display: 'block', minWidth: 0 }}><span style={{ display: 'block', fontSize: 11, fontWeight: 800, marginBottom: 5, color: 'var(--prepza-generation-muted, #596579)' }}>{label}</span>{children}</label>
}

export default function ShopScreen({ setScreen, setActiveConversationId }: Props) {
  const [page, setPage] = useState<Page>('browse')
  const [listings, setListings] = useState<Listing[]>([])
  const [mine, setMine] = useState<Listing[]>([])
  const [saved, setSaved] = useState<Listing[]>([])
  const [selected, setSelected] = useState<Listing | null>(null)
  const [csrf, setCsrf] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [adminListings, setAdminListings] = useState<Listing[]>([])
  const [paymentReviews, setPaymentReviews] = useState<Listing[]>([])
  const [paymentReviewNotes, setPaymentReviewNotes] = useState<Record<number, string>>({})
  const [reports, setReports] = useState<any[]>([])
  const [query, setQuery] = useState('')
  const browseRequestId = useRef(0)
  const [category, setCategory] = useState('')
  const [condition, setCondition] = useState('')
  const [location, setLocation] = useState('')
  const [sort, setSort] = useState('newest')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [formId, setFormId] = useState<number | null>(null)
  const [form, setForm] = useState({ title: '', description: '', category: CATEGORIES[0], condition: 'good', price_kes: '0', location_area: '', whatsapp_number: '' })
  const [files, setFiles] = useState<File[]>([])
  const [formImages, setFormImages] = useState<ImageRef[]>([])
  const [reporting, setReporting] = useState(false)
  const [reportReason, setReportReason] = useState('scam')
  const [reportDetails, setReportDetails] = useState('')

  const feedback = () => { setError(''); setNotice('') }
  const loadBrowse = async () => {
    const requestId = ++browseRequestId.current
    const params = new URLSearchParams()
    if (query.trim()) params.set('q', query.trim())
    if (category) params.set('category', category)
    if (condition) params.set('condition', condition)
    if (location.trim()) params.set('location', location.trim())
    params.set('sort', sort)
    const path = '/api/shop/listings?' + params.toString()
    const cacheKey = params.toString()
    const cached = browseSnapshots.get(cacheKey)
    if (cached) {
      // Render this exact query's snapshot immediately while revalidating.
      // Older snapshots remain usable only as clearly-labelled fallback data.
      setListings(filterCurrentListings(cached.listings))
      setLoading(false)
      setError(Date.now() - cached.savedAt <= BROWSE_CACHE_TTL_MS
        ? ''
        : 'Showing recently viewed listings while availability is refreshed.')
    }
    try {
      const fresh = (await shopApi<{ listings: Listing[] }>(path)).listings || []
      browseSnapshots.set(cacheKey, { listings: toPublicBrowseSnapshot(fresh), savedAt: Date.now() })
      if (requestId !== browseRequestId.current) return
      setListings(filterCurrentListings(fresh))
      setError('')
    } catch (cause) {
      if (requestId !== browseRequestId.current) return
      if (!cached) throw cause
      // Fall back to this query's cached public snapshot, never the previous query's rows.
      setListings(filterCurrentListings(cached.listings))
      setLoading(false)
      setError('Showing recently viewed listings. Reconnect to refresh availability and status.')
    }
  }
  const loadMine = async () => setMine((await shopApi<{ listings: Listing[] }>('/api/shop/my-listings')).listings || [])
  const loadSaved = async () => setSaved((await shopApi<{ listings: Listing[] }>('/api/shop/saved')).listings || [])
  const loadAdmin = async () => {
    const data = await shopApi<{ listings: Listing[]; payment_reviews: Listing[]; reports: any[] }>('/api/shop/admin/queue')
    setAdminListings(data.listings || [])
    setPaymentReviews(data.payment_reviews || [])
    setReports(data.reports || [])
  }

  useEffect(() => {
    let alive = true
    shopApi<{ csrf_token: string; is_admin?: boolean }>('/me')
      .then(me => { if (alive) { setCsrf(me.csrf_token || ''); setIsAdmin(Boolean(me.is_admin)) } })
      .catch(() => { if (alive) setError('Please sign in again to use Prepza Shop.') })
      .finally(() => { if (alive) setLoading(false) })
    const reference = new URLSearchParams(window.location.search).get('shop_payment')
    if (reference) {
      shopApi<{ status: string }>( '/api/shop/payments/' + encodeURIComponent(reference))
        .then(result => { if (alive) { setPage('mine'); setNotice(result.status === 'success' ? 'Posting fee confirmed. Your draft is ready to publish.' : result.status === 'pending' ? 'Paystack is still confirming the posting fee. Refresh My Listings shortly.' : result.status === 'mismatched' ? 'Payment needs manual verification. Do not retry this charge; contact Prepza support.' : 'Payment was not completed. Your draft remains available to retry.') } })
        .catch(() => { if (alive) setError('Could not verify the posting payment yet. Check My Listings before retrying.') })
        .finally(() => { const url = new URL(window.location.href); url.searchParams.delete('shop_payment'); window.history.replaceState({}, '', url.toString()) })
    }
    return () => { alive = false }
  }, [])

  useEffect(() => {
    let alive = true
    setLoading(true)
    const work = page === 'browse' || page === 'detail' ? Promise.resolve()
      : page === 'mine' || page === 'create' ? loadMine()
      : page === 'saved' ? loadSaved()
      : page === 'admin' ? loadAdmin()
      : Promise.resolve()
    work.catch((e: any) => { if (alive) setError(e?.message || 'Shop could not load. Please retry.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [page])

  useEffect(() => {
    if (page !== 'browse') return
    const timer = window.setTimeout(() => loadBrowse().catch((e: any) => setError(e?.message || 'Could not search listings.')), 250)
    return () => window.clearTimeout(timer)
  }, [page, query, category, condition, location, sort])

  const periodCurrent = (listing: Listing) => Boolean(listing.posting_fee_paid && listing.posting_fee_expires_at && Date.parse(listing.posting_fee_expires_at) > Date.now())
  const statusLabel = (status: string) => ({ draft: 'Draft', pending_payment: 'Payment pending', payment_review: 'Payment review required', pending_review: 'Awaiting review', active: 'Live', paused: 'Paused', sold: 'Sold', rejected: 'Needs changes', removed: 'Removed' } as Record<string, string>)[status] || status
  const imageFor = (listing: Listing) => listing.images?.find(image => image.url)?.url || null
  const openDetail = async (listing: Listing) => {
    feedback()
    try { setSelected((await shopApi<{ listing: Listing }>('/api/shop/listings/' + listing.id)).listing); setPage('detail') }
    catch (e: any) { setError(e?.message || 'Listing could not be opened.') }
  }
  const startCreate = (listing?: Listing) => {
    feedback(); setFormId(listing?.id ?? null)
    setForm({ title: listing?.title || '', description: listing?.description || '', category: listing?.category || CATEGORIES[0], condition: listing?.condition || 'good', price_kes: String(listing?.price_kes ?? 0), location_area: listing?.location_area || '', whatsapp_number: '' })
    setFiles([]); setFormImages(listing?.images || []); setPage('create')
  }
  const removeFormImage = async (index: number) => {
    if (!formId) return
    feedback()
    try {
      const result = await shopApi<{ images: ImageRef[] }>('/api/shop/listings/' + formId + '/images/' + index, { method: 'DELETE', headers: { 'X-CSRF-Token': csrf } })
      setFormImages(result.images || [])
      invalidateBrowseSnapshots()
      setNotice('Photo removed.')
    } catch (e: any) { setError(e?.message || 'Could not remove photo.') }
  }
  const uploadFiles = async (listingId: number, chosen: File[]) => {
    for (const file of chosen) {
      const body = new FormData(); body.append('image', file)
      const uploaded = await shopApi<{ images: ImageRef[] }>('/api/shop/listings/' + listingId + '/images', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body })
      setFormImages(uploaded.images || [])
      invalidateBrowseSnapshots()
      setFiles(current => {
        const uploadedIndex = current.indexOf(file)
        return uploadedIndex < 0 ? current : current.filter((_, index) => index !== uploadedIndex)
      })
    }
  }
  const publish = async (listingId: number) => {
    try {
      const result = await shopApi<{ listing: Listing }>('/api/shop/listings/' + listingId + '/publish', { method: 'POST', headers: { 'X-CSRF-Token': csrf } })
      invalidateBrowseSnapshots()
      setNotice('Submitted for review. Your product appears in Shop after approval.')
      setPage('mine'); await loadMine()
      return result
    } catch (e: any) {
      if (e?.status === 402 && e?.code === 'SHOP_POSTING_FEE_REQUIRED') {
        const checkout = await shopApi<{ redirect_url: string }>('/api/shop/listings/' + listingId + '/checkout', { method: 'POST', headers: { 'X-CSRF-Token': csrf } })
        window.location.assign(checkout.redirect_url); return null
      }
      throw e
    }
  }
  const saveForm = async () => {
    if (saving) return
    setSaving(true); feedback()
    try {
      const payload = { title: form.title.trim(), description: form.description.trim(), category: form.category, condition: form.condition, price_kes: Number(form.price_kes), location_area: form.location_area.trim(), whatsapp_number: form.whatsapp_number.trim() }
      let id = formId
      if (formId) id = (await shopApi<{ listing: Listing }>('/api/shop/listings/' + formId, { method: 'PATCH', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(payload) })).listing.id
      else id = (await shopApi<{ listing: Listing }>('/api/shop/listings', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify(payload) })).listing.id
      invalidateBrowseSnapshots()
      if (!id) throw new Error('Draft saved but the listing ID was not returned.')
      setFormId(id)
      if (files.length) await uploadFiles(id, files)
      setFiles([])
      await publish(id)
    } catch (e: any) {
      setError(e?.message || 'Could not save listing. Your draft is saved; review the message and retry when ready.')
    } finally { setSaving(false) }
  }
  const saveToggle = async (listing: Listing) => {
    feedback()
    try {
      if (listing.saved) await shopApi('/api/shop/listings/' + listing.id + '/save', { method: 'DELETE', headers: { 'X-CSRF-Token': csrf } })
      else await shopApi('/api/shop/listings/' + listing.id + '/save', { method: 'POST', headers: { 'X-CSRF-Token': csrf } })
      invalidateBrowseSnapshots()
      if (selected?.id === listing.id) setSelected({ ...selected, saved: !listing.saved })
      await loadBrowse()
      if (page === 'saved') await loadSaved()
    } catch (e: any) { setError(e?.message || 'Could not update saved listings.') }
  }
  const contactInApp = async (listing: Listing) => {
    feedback()
    try {
      const result = await shopApi<{ id: number; status: string }>('/chats', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ is_group: false, participant_ids: [listing.seller_id] }) })
      setActiveConversationId(result.id)
      if (result.status === 'pending') setNotice('Message request created. Track it in Chats → Requests.')
      else setScreen('chat-detail')
    } catch (e: any) { setError(e?.message || 'Could not start a chat. Please try again.') }
  }
  const report = async () => {
    if (!selected) return
    try {
      await shopApi('/api/shop/listings/' + selected.id + '/report', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ reason: reportReason, details: reportDetails }) })
      setReporting(false); setReportDetails(''); setNotice('Thanks. Your report has been sent to the moderation team.')
    } catch (e: any) { setError(e?.message || 'Could not send report.') }
  }
  const resumeCheckout = async (listing: Listing) => {
    feedback()
    try {
      const checkout = await shopApi<{ redirect_url: string }>('/api/shop/listings/' + listing.id + '/checkout', { method: 'POST', headers: { 'X-CSRF-Token': csrf } })
      window.location.assign(checkout.redirect_url)
    } catch (e: any) { setError(e?.message || 'Could not resume posting-fee checkout.') }
  }
  const listingAction = async (listing: Listing, action: 'pause' | 'mark-sold' | 'remove' | 'publish') => {
    feedback()
    try {
      if (action === 'publish') { await publish(listing.id); return }
      if (action === 'remove') await shopApi('/api/shop/listings/' + listing.id, { method: 'DELETE', headers: { 'X-CSRF-Token': csrf } })
      else await shopApi('/api/shop/listings/' + listing.id + '/' + (action === 'pause' ? 'pause' : 'mark-sold'), { method: 'POST', headers: { 'X-CSRF-Token': csrf } })
      invalidateBrowseSnapshots()
      await loadMine(); if (selected?.id === listing.id) setSelected({ ...selected, status: action === 'pause' ? 'paused' : action === 'mark-sold' ? 'sold' : 'removed' })
      setNotice(action === 'pause' ? 'Listing paused.' : action === 'mark-sold' ? 'Marked as sold.' : 'Listing removed.')
    } catch (e: any) { setError(e?.message || 'Could not update listing.') }
  }
  const moderate = async (id: number, action: 'approve' | 'reject' | 'remove') => {
    try {
      await shopApi('/api/shop/admin/listings/' + id + '/moderate', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ action }) })
      invalidateBrowseSnapshots()
      await loadAdmin(); setNotice(action === 'approve' ? 'Listing approved and published.' : action === 'remove' ? 'Reported listing removed.' : 'Moderation decision saved.')
    } catch (e: any) { setError(e?.message || 'Could not moderate listing.') }
  }
  const resolveReport = async (id: number) => {
    try { await shopApi('/api/shop/admin/reports/' + id + '/resolve', { method: 'POST', headers: { 'X-CSRF-Token': csrf } }); await loadAdmin() }
    catch (e: any) { setError(e?.message || 'Could not resolve report.') }
  }
  const resolvePaymentReview = async (id: number, action: 'confirm_paid' | 'allow_retry') => {
    const note = (paymentReviewNotes[id] || '').trim()
    if (note.length < 10) { setError('Record at least 10 characters describing the provider-side verification before resolving this payment.'); return }
    try {
      await shopApi('/api/shop/admin/listings/' + id + '/resolve-payment', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ action, note }) })
      setPaymentReviewNotes(current => ({ ...current, [id]: '' }))
      await loadAdmin()
      setNotice(action === 'confirm_paid' ? 'Payment manually reconciled. The seller can now submit the draft.' : 'Payment review closed. The seller can retry after you confirmed no fee remains captured.')
    } catch (e: any) { setError(e?.message || 'Could not resolve the posting payment.') }
  }
  const nav: { id: Page; label: string }[] = [{ id: 'browse', label: 'Browse' }, { id: 'mine', label: 'My listings' }, { id: 'saved', label: 'Saved' }, ...(isAdmin ? [{ id: 'admin' as Page, label: 'Moderation' }] : [])]
  const card = (item: Listing, owned = false) => <article key={item.id} onClick={() => openDetail(item)} style={{ ...ui.panel, padding: 0, overflow: 'hidden', minWidth: 0, cursor: 'pointer' }}>
    {imageFor(item) ? <img src={imageFor(item)!} alt={item.title} loading="lazy" style={{ width: '100%', height: 148, objectFit: 'cover', display: 'block', background: 'var(--prepza-generation-border, #E1E5ED)' }} /> : <div style={{ height: 148, display: 'grid', placeItems: 'center', background: 'var(--prepza-generation-page, #F8F9FC)', color: 'var(--prepza-generation-muted, #596579)', fontSize: 12 }}>Photo unavailable</div>}
    <div style={{ padding: 12 }}><div style={{ fontSize: 15, fontWeight: 900, marginBottom: 5 }}>{money(item.price_kes)}</div><div style={{ fontSize: 12, fontWeight: 800, lineHeight: 1.4, minHeight: 32 }}>{item.title}</div><div style={{ color: 'var(--prepza-generation-muted, #596579)', fontSize: 10, marginTop: 7 }}>{conditionLabel(item.condition)} · {item.category}</div><div style={{ color: 'var(--prepza-generation-muted, #596579)', fontSize: 10, marginTop: 5 }}>{item.location_area}</div>{owned && <div style={{ display: 'inline-block', marginTop: 9, background: 'var(--prepza-generation-border, #E1E5ED)', borderRadius: 8, padding: '5px 7px', fontSize: 10, fontWeight: 800 }}>{item.status === 'active' && !periodCurrent(item) ? 'Renewal due' : statusLabel(item.status)}</div>}</div>
  </article>

  if (loading && !listings.length && !mine.length && !saved.length) return <div style={ui.root}><header style={ui.header}><strong style={{ fontSize: 22 }}>Prepza Shop</strong><div style={{ opacity: .7, fontSize: 12, marginTop: 5 }}>Useful finds from your campus</div></header><div style={ui.wrap}>Loading Shop…</div></div>
  return <div style={ui.root}>
    <header style={ui.header}><div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <button type="button" onClick={() => page === 'browse' ? setScreen('home') : (setPage(selected?.is_mine ? 'mine' : 'browse'), setSelected(null))} style={{ background: 'none', border: 0, color: 'rgba(255,255,255,.72)', padding: 0, marginBottom: 13, cursor: 'pointer', fontSize: 11, fontWeight: 800 }}>‹ {page === 'browse' ? 'Home' : 'Back'}</button>
      <div style={{ display: 'flex', gap: 12, justifyContent: 'space-between', alignItems: 'center' }}><div><div style={{ fontSize: 23, fontWeight: 900 }}>Shop</div><div style={{ color: 'rgba(255,255,255,.68)', fontSize: 12, marginTop: 4 }}>Find useful things near campus. Connect directly with sellers.</div></div><ShopButton onClick={() => startCreate()}>＋ Sell an item</ShopButton></div>
      <div style={{ display: 'flex', gap: 7, marginTop: 17, overflowX: 'auto' }}>{nav.map(item => <button key={item.id} type="button" onClick={() => { feedback(); setPage(item.id) }} style={{ flexShrink: 0, border: '1px solid ' + (page === item.id ? '#C9A84C' : 'rgba(255,255,255,.18)'), background: page === item.id ? '#C9A84C' : 'rgba(255,255,255,.08)', color: page === item.id ? '#101B35' : '#fff', padding: '8px 12px', borderRadius: 20, fontSize: 11, fontWeight: 800, cursor: 'pointer' }}>{item.label}</button>)}</div>
    </div></header>
    <main style={ui.wrap}>
      {notice && <div role="status" style={{ background: 'color-mix(in srgb, #22C55E 10%, var(--prepza-generation-page, #F8F9FC))', border: '1px solid color-mix(in srgb, #22C55E 28%, var(--prepza-generation-border, #E1E5ED))', color: 'var(--prepza-generation-text, #0B1437)', borderRadius: 12, padding: 12, fontSize: 12, marginBottom: 12 }}>{notice}</div>}
      {error && <div role="alert" style={{ background: 'color-mix(in srgb, #EF4444 10%, var(--prepza-generation-page, #F8F9FC))', border: '1px solid color-mix(in srgb, #EF4444 28%, var(--prepza-generation-border, #E1E5ED))', color: 'var(--prepza-generation-text, #0B1437)', borderRadius: 12, padding: 12, fontSize: 12, marginBottom: 12 }}>{error}<button onClick={() => setError('')} style={{ float: 'right', border: 0, background: 'transparent', cursor: 'pointer' }}>Dismiss</button></div>}

      {page === 'browse' && <>
        <section style={{ ...ui.panel, marginBottom: 16 }}><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 10 }}>
          <Field label="Search products"><input style={ui.input} value={query} onChange={e => setQuery(e.target.value)} placeholder="Textbooks, calculators…" /></Field>
          <Field label="Category"><select style={ui.input} value={category} onChange={e => setCategory(e.target.value)}><option value="">All categories</option>{CATEGORIES.map(item => <option key={item}>{item}</option>)}</select></Field>
          <Field label="Condition"><select style={ui.input} value={condition} onChange={e => setCondition(e.target.value)}><option value="">Any condition</option>{CONDITIONS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></Field>
          <Field label="Campus / area"><input style={ui.input} value={location} onChange={e => setLocation(e.target.value)} placeholder="e.g. Kahawa, KU" /></Field>
          <Field label="Sort by"><select style={ui.input} value={sort} onChange={e => setSort(e.target.value)}><option value="newest">Newest</option><option value="price_low">Price: low to high</option><option value="price_high">Price: high to low</option></select></Field>
        </div></section>
        {loading ? <div style={{ padding: 22, textAlign: 'center', color: 'var(--prepza-generation-muted, #596579)' }}>Finding listings…</div> : listings.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(155px,1fr))', gap: 12 }}>{listings.map(item => card(item))}</div> : <div style={{ ...ui.panel, textAlign: 'center', padding: 18 }}><div style={{ fontSize: 17, fontWeight: 900 }}>No listings yet</div><p style={{ color: 'var(--prepza-generation-muted, #596579)', fontSize: 12, lineHeight: 1.4, margin: '6px 0 0' }}>Use Sell an item above to post.</p></div>}
      </>}

      {page === 'mine' && <><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginBottom: 14 }}><div><h2 style={{ fontSize: 17, margin: 0 }}>My listings</h2><p style={{ color: 'var(--prepza-generation-muted, #596579)', fontSize: 11, margin: '5px 0 0' }}>Each listing costs KES 100 per 30 days.</p></div><ShopButton onClick={() => startCreate()}>＋ New listing</ShopButton></div>{mine.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(155px,1fr))', gap: 12 }}>{mine.map(item => card(item, true))}</div> : <div style={{ ...ui.panel, textAlign: 'center', padding: 28 }}><h3 style={{ marginTop: 0 }}>No products posted yet</h3><p style={{ fontSize: 12, color: 'var(--prepza-generation-muted, #596579)' }}>Each item costs KES 100 per 30 days. Add a photo, complete secure checkout, then submit it for review.</p><ShopButton onClick={() => startCreate()}>Create your first listing</ShopButton></div>}</>}

      {page === 'saved' && (saved.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(155px,1fr))', gap: 12 }}>{saved.map(item => card(item))}</div> : <div style={{ ...ui.panel, textAlign: 'center', padding: 30 }}>No saved listings yet. Save products to compare them later.</div>)}

      {page === 'create' && <section style={{ ...ui.panel, maxWidth: 760, margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'start', marginBottom: 18 }}><div><h2 style={{ margin: 0, fontSize: 18 }}>{formId ? 'Edit listing' : 'List a product'}</h2><p style={{ color: 'var(--prepza-generation-muted, #596579)', fontSize: 12, margin: '6px 0 0' }}>Buyers contact you directly. Prepza never takes payment for the product.</p></div><button type="button" onClick={() => setPage('mine')} style={{ border: 0, background: 'transparent', fontWeight: 800, cursor: 'pointer' }}>Cancel</button></div>
        <div style={{ background: 'color-mix(in srgb, #C9A84C 13%, var(--prepza-generation-page, #F8F9FC))', border: '1px solid color-mix(in srgb, #C9A84C 40%, var(--prepza-generation-border, #E1E5ED))', borderRadius: 12, padding: 12, marginBottom: 15, fontSize: 12, lineHeight: 1.55, color: 'var(--prepza-generation-text, #0B1437)' }}><strong>Posting fee: KES 100 per item for each 30-day period, including your first.</strong> Pay securely before submitting for review. Buyers pay you directly; Prepza never handles product purchases.</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', rowGap: 6, columnGap: 13 }}>
          <Field label="Product title"><input style={ui.input} value={form.title} maxLength={100} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="e.g. Casio scientific calculator" required /></Field>
          <Field label="Category"><select style={ui.input} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>{CATEGORIES.map(item => <option key={item}>{item}</option>)}</select></Field>
          <Field label="Condition"><select style={ui.input} value={form.condition} onChange={e => setForm(f => ({ ...f, condition: e.target.value }))}>{CONDITIONS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></Field>
          <Field label="Price (KES)"><input style={ui.input} type="number" min="0" max="10000000" step="1" value={form.price_kes} onChange={e => setForm(f => ({ ...f, price_kes: e.target.value }))} required /></Field>
          <Field label="Campus / area"><input style={ui.input} value={form.location_area} maxLength={100} onChange={e => setForm(f => ({ ...f, location_area: e.target.value }))} placeholder="Area only, not your home address" required /></Field>
          <Field label="WhatsApp number (optional)"><input style={ui.input} inputMode="tel" value={form.whatsapp_number} onChange={e => setForm(f => ({ ...f, whatsapp_number: e.target.value }))} placeholder="0712345678" /></Field>
        </div>
        <div style={{ marginTop: 13 }}><Field label="Description"><textarea style={{ ...ui.input, resize: 'vertical', minHeight: 105 }} value={form.description} maxLength={2000} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Describe the item honestly, including wear, defects and what is included." required /></Field><div style={{ color: 'var(--prepza-generation-muted, #596579)', textAlign: 'right', fontSize: 10 }}>{form.description.length}/2000</div></div>
        {formImages.length > 0 && <div style={{ marginTop: 13 }}><div style={{ fontSize: 11, fontWeight: 800, marginBottom: 7 }}>Current photos</div><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(92px,1fr))', gap: 8 }}>{formImages.map((image, index) => <div key={image.key} style={{ border: '1px solid var(--prepza-generation-border, #E1E5ED)', borderRadius: 10, padding: 6 }}>{image.url ? <img src={image.url} alt={'Current product photo ' + (index + 1)} style={{ width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', borderRadius: 7 }} /> : <div style={{ aspectRatio: '1 / 1', background: 'var(--prepza-generation-border, #E1E5ED)', borderRadius: 7 }} />}<button type="button" onClick={() => removeFormImage(index)} style={{ width: '100%', marginTop: 5, border: 0, background: 'color-mix(in srgb, #EF4444 10%, var(--prepza-generation-page, #F8F9FC))', color: 'var(--prepza-generation-text, #0B1437)', borderRadius: 7, padding: 6, fontSize: 10, fontWeight: 800, cursor: 'pointer' }}>Remove</button></div>)}</div></div>}
        <div style={{ marginTop: 13 }}><Field label={'Add photos (' + Math.max(0, 6 - formImages.length) + ' slots left; JPEG, PNG or WebP; 5 MB each)'}><input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(e: ChangeEvent<HTMLInputElement>) => setFiles(Array.from(e.target.files || []).slice(0, Math.max(0, 6 - formImages.length)))} style={{ ...ui.input, padding: 10 }} disabled={formImages.length >= 6} /></Field><p style={{ color: 'var(--prepza-generation-muted, #596579)', fontSize: 10, lineHeight: 1.5 }}>Use clear photos of the actual item. Photos are resized and location metadata is removed before storage.</p>{files.length > 0 && <div style={{ fontSize: 11, marginBottom: 8 }}>{files.length} photo(s) selected: {files.map(f => f.name).join(', ')}</div>}<p style={{ color: 'var(--prepza-generation-text, #0B1437)', fontSize: 10, lineHeight: 1.5 }}>Do not list stolen or counterfeit goods, weapons, medicines, alcohol, tobacco/nicotine, or other prohibited or regulated items.</p></div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 18 }}><ShopButton onClick={saveForm} disabled={saving}>{saving ? 'Saving…' : formId ? 'Save changes' : 'Save & publish'}</ShopButton><ShopButton secondary onClick={() => setPage('mine')}>Cancel</ShopButton></div>
      </section>}

      {page === 'detail' && selected && <section style={{ ...ui.panel, maxWidth: 900, margin: '0 auto' }}>
        <button type="button" onClick={() => { setSelected(null); setPage(selected.is_mine ? 'mine' : 'browse') }} style={{ border: 0, background: 'transparent', padding: 0, marginBottom: 15, cursor: 'pointer', fontWeight: 800 }}>‹ Back to {selected.is_mine ? 'My listings' : 'Shop'}</button>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 20 }}>
          <div>{selected.images?.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(100px,1fr))', gap: 8 }}>{selected.images.map((img, i) => img.url ? <img key={img.key} src={img.url} alt={selected.title + ' photo ' + (i + 1)} style={{ width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', borderRadius: 12 }} /> : <div key={img.key} style={{ background: 'var(--prepza-generation-border, #E1E5ED)', borderRadius: 12, minHeight: 100 }} />)}</div> : <div style={{ background: 'var(--prepza-generation-border, #E1E5ED)', borderRadius: 14, minHeight: 220, display: 'grid', placeItems: 'center', color: 'var(--prepza-generation-muted, #596579)' }}>No photos available</div>}</div>
          <div><div style={{ color: 'var(--prepza-generation-muted, #596579)', fontSize: 11 }}>{selected.category} · {conditionLabel(selected.condition)}</div><h2 style={{ fontSize: 23, margin: '7px 0' }}>{selected.title}</h2><div style={{ fontSize: 22, fontWeight: 900 }}>{money(selected.price_kes)}</div><div style={{ color: 'var(--prepza-generation-muted, #596579)', fontSize: 12, marginTop: 7 }}>{selected.location_area}</div><div style={{ marginTop: 15, whiteSpace: 'pre-wrap', lineHeight: 1.65, fontSize: 13 }}>{selected.description}</div><div style={{ marginTop: 17, padding: 13, background: 'var(--prepza-generation-page, #F8F9FC)', borderRadius: 12 }}><div style={{ fontSize: 11, color: 'var(--prepza-generation-muted, #596579)' }}>Seller</div><div style={{ fontSize: 14, fontWeight: 900, marginTop: 3 }}>{selected.seller_name}</div><div style={{ color: 'var(--prepza-generation-muted, #596579)', fontSize: 10, marginTop: 4 }}>Prepza connects you directly. Payment and handover are agreed with the seller.</div></div>
          {!selected.is_mine && <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 14 }}><ShopButton onClick={() => contactInApp(selected)}>Message in Prepza</ShopButton>{selected.whatsapp_url && <ShopButton secondary onClick={() => window.open(selected.whatsapp_url!, '_blank', 'noopener,noreferrer')}>WhatsApp seller</ShopButton>}<ShopButton secondary onClick={() => saveToggle(selected)}>{selected.saved ? 'Saved ✓' : 'Save item'}</ShopButton><ShopButton secondary onClick={() => setReporting(v => !v)}>Report</ShopButton></div>}
          {selected.is_mine && <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 14 }}>{selected.status !== 'payment_review' && !['sold', 'removed'].includes(selected.status) && <ShopButton onClick={() => startCreate(selected)}>Edit listing</ShopButton>}{selected.status === 'active' && <ShopButton secondary onClick={() => listingAction(selected, 'pause')}>Pause</ShopButton>}{['active', 'paused'].includes(selected.status) && <ShopButton secondary onClick={() => listingAction(selected, 'mark-sold')}>Mark sold</ShopButton>}{selected.status === 'pending_payment' && !periodCurrent(selected) && <ShopButton onClick={() => resumeCheckout(selected)}>Resume KES 100 checkout</ShopButton>}{['active', 'paused'].includes(selected.status) && !periodCurrent(selected) && <ShopButton onClick={() => resumeCheckout(selected)}>Renew for KES 100 / 30 days</ShopButton>}{['draft', 'paused', 'pending_review'].includes(selected.status) && <ShopButton secondary onClick={() => listingAction(selected, 'publish')}>Publish / resubmit</ShopButton>}{selected.status !== 'payment_review' && selected.status !== 'pending_payment' && <ShopButton secondary onClick={() => listingAction(selected, 'remove')}>Remove</ShopButton>}</div>}
          {selected.is_mine && selected.status === 'payment_review' && <div role="alert" style={{ marginTop: 12, padding: 12, background: 'color-mix(in srgb, #EF4444 10%, var(--prepza-generation-page, #F8F9FC))', color: 'var(--prepza-generation-text, #0B1437)', borderRadius: 10, fontSize: 11 }}>The payment provider reported a result that needs manual verification. Your listing is unpublished. Do not retry the charge; contact Prepza support.</div>}{selected.is_mine && <div style={{ marginTop: 12, fontSize: 11, color: 'var(--prepza-generation-muted, #596579)' }}>Status: <strong>{statusLabel(selected.status)}</strong>{selected.moderation_note ? ' · ' + selected.moderation_note : ''} · Posting fee {money(selected.posting_fee_kes)}{periodCurrent(selected) ? ' paid through ' + new Date(selected.posting_fee_expires_at as string).toLocaleDateString('en-KE') : ' renewal due'}</div>}
          {reporting && !selected.is_mine && <div style={{ marginTop: 14, ...ui.panel }}><Field label="Reason"><select style={ui.input} value={reportReason} onChange={e => setReportReason(e.target.value)}>{REASONS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></Field><Field label="Details (optional)"><textarea style={{ ...ui.input, marginTop: 10 }} rows={3} maxLength={1000} value={reportDetails} onChange={e => setReportDetails(e.target.value)} placeholder="What should our moderators know?" /></Field><div style={{ marginTop: 10 }}><ShopButton onClick={report}>Submit report</ShopButton></div></div>}
          </div>
        </div>
        <div style={{ marginTop: 18, background: 'color-mix(in srgb, #C9A84C 13%, var(--prepza-generation-page, #F8F9FC))', border: '1px solid color-mix(in srgb, #C9A84C 40%, var(--prepza-generation-border, #E1E5ED))', borderRadius: 12, padding: 13, fontSize: 11, lineHeight: 1.6, color: 'var(--prepza-generation-text, #0B1437)' }}><strong>Stay safe:</strong> inspect items before paying, meet in a public place, avoid advance-payment pressure, and never share passwords, OTPs or M-Pesa PINs. Prepza does not handle purchases or guarantee seller transactions.</div>
      </section>}

      {page === 'admin' && isAdmin && <section style={{ display: 'grid', gap: 18 }}><div><h2 style={{ margin: '0 0 5px', fontSize: 18 }}>Listing moderation</h2><p style={{ margin: 0, fontSize: 11, color: 'var(--prepza-generation-muted, #596579)' }}>Review products before they become visible to students.</p></div>
        <div><h3 style={{ fontSize: 15 }}>Posting payment exceptions</h3><p style={{ fontSize: 11, color: 'var(--prepza-generation-muted, #596579)' }}>Verify the exact reference, KES amount and currency in Paystack before confirming a charge. Do not allow a retry until you confirm no money remains captured or the incorrect charge is handled.</p>{paymentReviews.length ? paymentReviews.map(item => <div key={item.id} style={{ ...ui.panel, marginBottom: 10, borderColor: 'color-mix(in srgb, #EF4444 35%, var(--prepza-generation-border, #E1E5ED))' }}><strong>{item.title} · Listing #{item.id}</strong><div style={{ fontSize: 11, color: 'var(--prepza-generation-muted, #596579)', marginTop: 5 }}>Seller: {item.seller_name} · Reference: {item.posting_payment_reference || 'missing'}</div><p style={{ fontSize: 11 }}>{item.posting_payment_review_note || 'Posting payment amount/currency requires manual verification.'}</p><Field label="Provider verification note"><textarea style={ui.input} rows={2} maxLength={500} value={paymentReviewNotes[item.id] || ''} onChange={e => setPaymentReviewNotes(notes => ({ ...notes, [item.id]: e.target.value }))} placeholder="Record provider reference, amount/currency verified, and outcome." /></Field><div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 9 }}><ShopButton onClick={() => resolvePaymentReview(item.id, 'confirm_paid')}>Confirm verified KES 100 payment</ShopButton><ShopButton secondary onClick={() => resolvePaymentReview(item.id, 'allow_retry')}>Allow retry after verification</ShopButton></div></div>) : <div style={ui.panel}>No posting-payment exceptions.</div>}</div>
        <div><h3 style={{ fontSize: 15 }}>Listings awaiting approval</h3>{adminListings.length ? adminListings.map(item => <div key={item.id} style={{ ...ui.panel, display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'center', marginBottom: 9 }}>{imageFor(item) && <img src={imageFor(item)!} alt="" style={{ width: 74, height: 74, borderRadius: 10, objectFit: 'cover' }} />}<div style={{ flex: 1, minWidth: 170 }}><strong>{item.title}</strong><div style={{ fontSize: 11, color: 'var(--prepza-generation-muted, #596579)', marginTop: 4 }}>{item.seller_name} · {money(item.price_kes)} · {item.location_area}</div><div style={{ fontSize: 11, marginTop: 5 }}>{item.description}</div></div><ShopButton onClick={() => moderate(item.id, 'approve')}>Approve</ShopButton><ShopButton secondary onClick={() => moderate(item.id, 'reject')}>Reject</ShopButton></div>) : <div style={ui.panel}>No listings awaiting review.</div>}</div>
        <div><h3 style={{ fontSize: 15 }}>Reports</h3>{reports.length ? reports.map(report => <div key={report.id} style={{ ...ui.panel, marginBottom: 9 }}><strong>Listing #{report.listing_id} · {report.reason}</strong><p style={{ fontSize: 11 }}>{report.details || 'No extra details.'}</p><div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}><ShopButton secondary onClick={() => moderate(report.listing_id, 'remove')}>Remove listing</ShopButton><ShopButton secondary onClick={() => resolveReport(report.id)}>Resolve report</ShopButton></div></div>) : <div style={ui.panel}>No open reports.</div>}</div></section>}
    </main>
  </div>
}
