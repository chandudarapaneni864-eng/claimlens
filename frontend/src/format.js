const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const inr2 = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const money = (v) => (v === null || v === undefined || v === '' ? '—' : `₹${inr.format(Number(v))}`)
export const money2 = (v) => (v === null || v === undefined || v === '' ? '—' : `₹${inr2.format(Number(v))}`)
export const compactMoney = (v) => {
  const n = Number(v || 0)
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(1)}k`
  return `₹${inr.format(n)}`
}

export const date = (v) => {
  if (!v) return '—'
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v)
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}
export const dateTime = (v) => {
  if (!v) return '—'
  return new Date(v).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}
export const ago = (v) => {
  if (!v) return ''
  const s = (Date.now() - new Date(v).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  const d = Math.floor(s / 86400)
  return d === 1 ? 'yesterday' : `${d} days ago`
}
export const today = () => new Date().toISOString().slice(0, 10)
export const initials = (name = '') => name.split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase()

export const STATUS_TONE = {
  DRAFT: 'gray',
  UNDER_REVIEW: 'blue',
  CORRECTION_REQUESTED: 'amber',
  DOCS_REQUESTED: 'amber',
  APPROVED: 'teal',
  REJECTED: 'red',
  PAYMENT_INITIATED: 'violet',
  PAID: 'green',
}
export const STATUS_LABEL = {
  DRAFT: 'Draft',
  UNDER_REVIEW: 'Under review',
  CORRECTION_REQUESTED: 'Correction requested',
  DOCS_REQUESTED: 'Documents requested',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  PAYMENT_INITIATED: 'Payment initiated',
  PAID: 'Settled',
}

export const CATEGORIES = [
  { value: 'travel', label: 'Travel', icon: 'plane', hint: 'Flights, trains, cabs' },
  { value: 'accommodation', label: 'Accommodation', short: 'Hotel stay', icon: 'bed', hint: 'Hotels, guest houses' },
  { value: 'food', label: 'Food', icon: 'food', hint: 'Meals with bills' },
  { value: 'medical', label: 'Medical', icon: 'medical', hint: 'OPD, tests, medicines' },
  { value: 'other', label: 'Other', icon: 'box', hint: 'Fees, courier, supplies' },
]
export const CATEGORY_ICON = Object.fromEntries(CATEGORIES.map((c) => [c.value, c.icon]))

export const DOC_TYPES = [
  { value: 'invoice', label: 'Invoice' },
  { value: 'bill', label: 'Bill' },
  { value: 'receipt', label: 'Receipt' },
  { value: 'ticket', label: 'Ticket' },
  { value: 'payment_proof', label: 'Payment proof' },
  { value: 'approval', label: 'Approval document' },
  { value: 'medical_bill', label: 'Medical bill' },
  { value: 'prescription', label: 'Prescription' },
  { value: 'other', label: 'Other' },
]
export const DOC_LABEL = Object.fromEntries(DOC_TYPES.map((d) => [d.value, d.label]))

// Mirrors claims/verification/checks.py so the form can show which requirements are met.
export const DOC_EQUIVALENTS = {
  invoice: ['invoice', 'bill', 'receipt', 'ticket', 'medical_bill'],
  bill: ['bill', 'receipt', 'invoice'],
  receipt: ['receipt', 'bill', 'invoice'],
  ticket: ['ticket'],
  payment_proof: ['payment_proof'],
  approval: ['approval'],
  medical_bill: ['medical_bill', 'bill', 'invoice'],
  prescription: ['prescription'],
}
export const requirementMet = (req, uploadedTypes) => (DOC_EQUIVALENTS[req] || [req]).some((t) => uploadedTypes.includes(t))

export const FIELD_LABEL = {
  amount: 'Amount',
  invoice_number: 'Invoice / bill no.',
  date: 'Date',
  vendor: 'Vendor',
  employee_name: 'Name on document',
  transaction_id: 'Transaction ref.',
  gstin: 'GSTIN',
  check_in: 'Check-in',
  check_out: 'Check-out',
  category: 'Looks like',
}

export const RECOMMENDATION = {
  approve: { stamp: 'Looks fine', tone: 'approve' },
  review: { stamp: 'Needs review', tone: 'review' },
  reject: { stamp: 'Likely reject', tone: 'reject' },
}
