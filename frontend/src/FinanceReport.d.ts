import type { ReactElement } from 'react'

export type FinanceChartData = {
  title: string
  kind: 'line' | 'bar'
  labels: string[]
  has_activity: boolean
  series: Array<{ label: string; values: string[] }>
}

export type FinanceReportData = {
  title: string
  currency: 'INR'
  timezone: 'Asia/Kolkata'
  start_date: string | null
  end_date: string
  notes: string[]
  metrics: Array<{ label: string; value: string | null; unit: 'INR' | 'count' | 'percent' }>
  charts: FinanceChartData[]
}

export const financePrompts: string[]
export function formatINR(value: number | string): string
export default function FinanceReport(props: { report?: FinanceReportData }): ReactElement | null
