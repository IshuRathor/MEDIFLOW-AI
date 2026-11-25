import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import AdminReport, { adminPrompts } from '../src/AdminReport.js'
import { ReportChart } from '../src/FinanceReport.js'

const types = [
  ['Monthly appointment activity', 'line'],
  ['Current status of appointments in the period', 'bar'],
  ['Recorded cancellation activity', 'line'],
  ['Registered doctors by current department', 'bar'],
  ['Appointments by current doctor department', 'bar'],
  ['Appointments by doctor', 'bar'],
  ['Pending queues by age', 'bar'],
]
const charts = types.map(([title, kind]) => ({
  title, kind, unit: 'count', labels: ['November'], has_activity: true,
  series: [{ label: 'Records', values: ['2'] }],
}))
const report = {
  title: 'Hospital performance report',
  timezone: 'Asia/Kolkata',
  start_date: '2026-11-01',
  end_date: '2026-11-25',
  cutoff: '2026-11-25T12:00:00+05:30',
  metrics: [
    { label: 'Registered patients · current', value: '12', unit: 'count' },
    { label: 'Completed collections in period', value: '100.25', unit: 'INR' },
  ],
  charts,
  queues: [
    { title: 'Booking requests', source: 'Appointment.created_at', status: 'Pending Doctor Approval', count: 1,
      oldest_at: '2026-11-17T12:00:00+05:30', oldest_age_hours: 192 },
    { title: 'Account approvals', source: 'User.created_at', status: 'pending', count: 0, oldest_at: null, oldest_age_hours: null },
  ],
  notes: ['Review the oldest pending entries.'],
}

test('admin prompts link the dashboard and chat to executive reports and shared Finance', () => {
  for (const prompt of ['Give me the hospital executive overview', 'Show monthly appointment demand',
    'Show appointment status distribution', 'Analyze doctor distribution by department',
    'Show pending operational queues', 'Compare hospital performance across months',
    'Prepare a hospital performance report', 'Compare revenue and expenses']) assert.ok(adminPrompts.includes(prompt))
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  assert.match(app, /aria-label="Admin AI suggestions"/)
  assert.match(app, /adminPrompts\.map/)
  assert.match(app, /currentUser\?\.role === 'admin' && <AdminReport report=/)
})

test('admin executive cards show dates, queue ages, notes and accessible count charts', () => {
  const html = renderToStaticMarkup(createElement(AdminReport, { report }))
  assert.match(html, /2026-11-01 to 2026-11-25 · IST/)
  assert.match(html, /datetime="2026-11-25T12:00:00\+05:30"/i)
  assert.match(html, /Registered patients · current<\/dt><dd>12/)
  assert.match(html, /₹100\.25/)
  assert.match(html, /Oldest · 192 hours/)
  assert.match(html, /No pending items/)
  assert.match(html, /Appointment\.created_at/)
  assert.match(html, /Review the oldest pending entries/)
  for (const chart of charts) {
    const markup = renderToStaticMarkup(createElement(ReportChart, { chart }))
    assert.ok(markup.includes(chart.title))
    assert.match(markup, chart.kind === 'line' ? /<polyline/ : /<rect/)
    assert.match(markup, /tabindex="0"/)
    assert.match(markup, /November, Records: 2/)
    assert.match(markup, /<th scope="row">November<\/th><td>2<\/td>/)
    assert.doesNotMatch(markup, /₹/)
  }
  assert.equal((html.match(/View data table/g) ?? []).length, charts.length)
})

test('admin reports expose empty, loading, error and responsive chart states', () => {
  const withoutRecords = { ...report, charts: [{ ...charts[0], has_activity: false }] }
  const empty = renderToStaticMarkup(createElement(AdminReport, { report: withoutRecords }))
  assert.match(empty, /No records in this range/)
  assert.doesNotMatch(empty, /<svg/)
  assert.match(renderToStaticMarkup(createElement(AdminReport, { loading: true })), /role="status".*Loading hospital intelligence/)
  assert.match(renderToStaticMarkup(createElement(AdminReport, { error: 'Invalid date range' })), /role="alert".*Invalid date range/)
  const responsive = renderToStaticMarkup(createElement(AdminReport, { report }))
  assert.match(responsive, /class="finance-chart-scroll"/)
  assert.match(responsive, /viewBox="0 0 620 202"/)
  const css = readFileSync(new URL('../src/App.css', import.meta.url), 'utf8')
  assert.match(css, /\.finance-chart-scroll, \.finance-table-scroll \{ overflow-x: auto;/)
})
