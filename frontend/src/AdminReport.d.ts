import type { ReactElement } from 'react'
import type { FinanceReportData } from './FinanceReport.js'

export type AdminReportData = Omit<FinanceReportData, 'currency'> & {
  cutoff: string
  queues: Array<{
    title: string
    source: string
    status: string
    count: number
    oldest_at: string | null
    oldest_age_hours: number | null
  }>
}

export const adminPrompts: string[]
export default function AdminReport(props: {
  report?: AdminReportData
  loading?: boolean
  error?: string
}): ReactElement | null
