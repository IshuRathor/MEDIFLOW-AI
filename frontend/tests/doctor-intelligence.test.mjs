import assert from 'node:assert/strict'
import { test } from 'node:test'
import { renderToStaticMarkup } from 'react-dom/server'
import DoctorIntelligence from '../src/DoctorIntelligence.js'
import { visibleChatTrace } from '../src/DoctorSelectionCards.js'

test('doctor briefing presents recorded visit dates and empty sections', () => {
  const result = {
    title: 'Doctor daily briefing',
    sections: [
      { title: 'Scheduled today', visits: [{ patient_name: 'Example Patient', appointment_date: '2030-06-10T09:00:00', status: 'Scheduled' }] },
      { title: 'Pending cancellation requests', visits: [] },
    ],
  }
  const html = renderToStaticMarkup(DoctorIntelligence({ result }))
  assert.match(html, /2030-06-10T09:00:00/)
  assert.match(html, /Example Patient/)
  assert.match(html, /No matching appointments/)
})

test('doctor workload distinguishes scheduled, completed and cancelled counts', () => {
  const result = { title: 'Weekly workload', periods: [{ title: 'This week', start: '2030-06-10', end: '2030-06-16', scheduled: 8, completed: 3, cancelled: 1 }] }
  const html = renderToStaticMarkup(DoctorIntelligence({ result }))
  assert.match(html, /Scheduled<\/dt><dd>8/)
  assert.match(html, /Completed<\/dt><dd>3/)
  assert.match(html, /Cancelled<\/dt><dd>1/)
})

test('assigned patient selection passes the reference without rendering an internal ID', () => {
  let selected
  const result = { title: 'Assigned patients', patients: [{ id: 987654, name: 'Example Patient' }] }
  const view = DoctorIntelligence({ result, onSelect: (id) => { selected = id } })
  const buttons = view.props.children.find((child) => child?.props?.className === 'ai-prompts')
  buttons.props.children[0].props.onClick()
  assert.equal(selected, 987654)
  assert.doesNotMatch(renderToStaticMarkup(view), /987654/)
})

test('the empty November weekly view displays its date range and the footer uses the returned tool', () => {
  const period = { start: '2026-11-23', end: '2026-11-29' }
  const label = (date) => new Date(`${date}T00:00:00`).toLocaleDateString()
  const report = renderToStaticMarkup(DoctorIntelligence({ result: {
    title: 'Appointments this week', date: '2026-11-25', period,
    sections: [{ title: 'Appointments this week', visits: [] }],
  } }))
  assert.ok(report.includes(`${label(period.start)} – ${label(period.end)}`))
  assert.match(report, /No matching appointments/)
  assert.equal(visibleChatTrace('clinician', [{ tool: 'doctor_daily_briefing', status: 'success' }]), 'doctor_daily_briefing: success')
  assert.equal(visibleChatTrace('clinician', [{ tool: 'doctor_weekly_workload', status: 'success' }]), 'doctor_weekly_workload: success')

  const empty = { scheduled: 0, completed: 0, cancelled: 0 }
  const comparison = renderToStaticMarkup(DoctorIntelligence({ result: {
    title: 'Weekly appointment workload',
    periods: [
      { title: 'This week', ...period, ...empty },
      { title: 'Last week', start: '2026-11-16', end: '2026-11-22', ...empty },
    ],
  } }))
  assert.match(comparison, /This week/)
  assert.match(comparison, /Last week/)
  assert.equal((comparison.match(/<dd>0<\/dd>/g) ?? []).length, 6)
})
