export type PaymentStatusMeta = {
  icon: string
  color: string
  label: string
}

export const PAYMENT_STATUS_META: Record<string, PaymentStatusMeta> = {
  success: { icon: '✅', color: '#4CC97B', label: 'Success' },
  pending: { icon: '⏳', color: '#D97706', label: 'Pending' },
  failed: { icon: '❌', color: '#C94C4C', label: 'Failed' },
  refunded: { icon: '↩️', color: '#6B7280', label: 'Refunded' },
}
