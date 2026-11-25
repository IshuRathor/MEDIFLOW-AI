import { createElement as h } from 'react'
import { ReportChart, ReportMetrics } from './FinanceReport.js'

export const adminPrompts = [
  'Give me the hospital executive overview',
  'Show monthly appointment demand',
  'Show appointment status distribution',
  'Analyze appointment cancellations',
  'Analyze doctor distribution by department',
  'Show pending operational queues',
  'Compare hospital performance across months',
  'Prepare a hospital performance report',
  'Compare revenue and expenses',
]

const indiaDateTime = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata',
})

export default function AdminReport({ report, loading = false, error }) {
  if (loading) return h('p', { role: 'status' }, 'Loading hospital intelligence…')
  if (error) return h('p', { role: 'alert', className: 'form-error' }, error)
  if (!report) return null

  const period = report.start_date ? `${report.start_date} to ${report.end_date}` : 'Current snapshot'
  return h('section', { className: 'finance-report', 'aria-label': report.title },
    h('p', null, `${period} · IST`),
    h('p', null, 'Reporting cutoff ', h('time', { dateTime: report.cutoff }, indiaDateTime.format(new Date(report.cutoff)))),
    h(ReportMetrics, { metrics: report.metrics }),
    report.queues.length > 0 && h('section', { 'aria-label': 'Operational queues', className: 'finance-report' },
      h('h4', null, 'Operational queues'),
      h('div', { className: 'finance-metrics' }, report.queues.map((queue) => h('div', { key: queue.title },
        h('strong', null, queue.title),
        h('p', null, queue.count ? `${queue.count} pending` : 'No pending items'),
        queue.oldest_at && h('p', null, `Oldest · ${queue.oldest_age_hours} hours · `,
          h('time', { dateTime: queue.oldest_at }, indiaDateTime.format(new Date(queue.oldest_at)))),
        queue.count > 0 && !queue.oldest_at && h('p', null, 'Oldest age unavailable'),
        h('small', null, `${queue.status} · ${queue.source}`),
      ))),
    ),
    report.charts.map((chart) => h(ReportChart, { key: chart.title, chart })),
    report.notes.length > 0 && h('section', { 'aria-label': 'Reporting notes' },
      h('h4', null, 'Reporting notes'),
      h('ul', { className: 'finance-notes' }, report.notes.map((note) => h('li', { key: note }, note))),
    ),
  )
}
