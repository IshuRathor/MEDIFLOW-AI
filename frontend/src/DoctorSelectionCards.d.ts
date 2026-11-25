import type { ReactElement } from 'react'

export type PatientDoctorOption = {
  id: number | string
  name: string
  specialization?: string | null
  department?: string | null
  [key: string]: unknown
}

export function patientDoctorOptions(data: Record<string, unknown>): PatientDoctorOption[]
export function visibleChatTrace(role: string | undefined, trace: Array<{ tool: string; status: string }>): string | null

export default function DoctorSelectionCards(props: {
  doctors: PatientDoctorOption[]
  onSelect: (doctor: PatientDoctorOption) => void
  disabled?: boolean
}): ReactElement | null
