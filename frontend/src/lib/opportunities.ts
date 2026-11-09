export const OPP_TYPE_META: Record<string, { icon: string; color: string; label: string }> = {
  job: { icon: '📋', color: '#9B59B6', label: 'Job' },
  internship: { icon: '💼', color: '#4CC97B', label: 'Internship' },
  scholarship: { icon: '🎓', color: '#C9A84C', label: 'Scholarship' },
  competition: { icon: '🏆', color: '#4C7BC9', label: 'Competition' },
  volunteering: { icon: '🤲', color: '#4CC97B', label: 'Volunteering' },
  event: { icon: '🎪', color: '#C94C4C', label: 'Event' },
  other: { icon: '🔖', color: '#6B7280', label: 'Other' },
}

export function oppTypeMeta(t: string) {
  return OPP_TYPE_META[t] || OPP_TYPE_META.other
}

export function fmtDeadline(iso: string | null) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-KE', { month: 'short', day: 'numeric', year: 'numeric' })
}
