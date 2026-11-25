import type { ReactElement } from 'react'

export const doctorPrompts: string[]

type Visit = {
  patient_name: string
  appointment_date: string
  status: string
  cancellation_status: string | null
  reason: string | null
}

export type DoctorIntelligenceResult = {
  title: string
  date?: string
  period?: { start: string; end: string }
  metrics?: Array<{ label: string; value: number }>
  periods?: Array<{ title: string; start: string; end: string; scheduled: number; completed: number; cancelled: number }>
  sections?: Array<{ title: string; visits: Visit[]; has_more: boolean }>
  patients?: Array<{ id: number; name: string }>
  has_more?: boolean
}

export default function DoctorIntelligence(props: {
  result?: DoctorIntelligenceResult
  onSelect: (id: number) => void
  disabled: boolean
}): ReactElement | null
