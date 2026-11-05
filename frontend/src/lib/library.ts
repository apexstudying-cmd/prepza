export const LIBRARY_MATERIAL_TYPES: { value: string; label: string }[] = [
  { value: 'lecture_notes', label: 'Lecture Notes' },
  { value: 'past_paper', label: 'Past Paper' },
  { value: 'summary', label: 'Summary' },
  { value: 'other', label: 'Other' },
]
export const materialTypeLabel = (v: string) => LIBRARY_MATERIAL_TYPES.find(t => t.value === v)?.label ?? v
