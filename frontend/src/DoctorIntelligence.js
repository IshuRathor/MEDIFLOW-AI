import { createElement as h } from 'react'

export const doctorPrompts = [
  'Give me my daily briefing',
  'What appointments do I have this week?',
  'Show my pending appointment requests',
  'Show my pending cancellation requests',
  'Compare this week with last week',
  'Show my assigned patients',
]

function dateLabel(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString()
}

function periodLabel({ start, end }) {
  return `${dateLabel(start)} – ${dateLabel(end)}`
}

export default function DoctorIntelligence({ result, onSelect, disabled }) {
  if (!result) return null
  return h('section', { className: 'doctor-intelligence', 'aria-label': result.title },
    h('h3', null, result.title),
    result.period
      ? h('p', null, periodLabel(result.period))
      : result.date && h('time', { dateTime: result.date }, dateLabel(result.date)),
    result.metrics && h('dl', { className: 'doctor-intelligence-metrics' },
      result.metrics.map((metric) => h('div', { key: metric.label },
        h('dt', null, metric.label), h('dd', null, metric.value),
      )),
    ),
    result.periods?.map((period) => h('article', { className: 'doctor-intelligence-card', key: period.start },
      h('h4', null, period.title),
      h('p', null, periodLabel(period)),
      h('dl', { className: 'doctor-intelligence-metrics' },
        h('div', null, h('dt', null, 'Scheduled'), h('dd', null, period.scheduled)),
        h('div', null, h('dt', null, 'Completed'), h('dd', null, period.completed)),
        h('div', null, h('dt', null, 'Cancelled'), h('dd', null, period.cancelled)),
      ),
    )),
    result.sections?.map((section) => h('article', { className: 'doctor-intelligence-card', key: section.title },
      h('h4', null, section.title),
      section.visits.length ? h('ul', null, section.visits.map((visit, index) => h('li', { key: index },
        h('strong', null, visit.patient_name),
        h('time', { dateTime: visit.appointment_date }, new Date(visit.appointment_date).toLocaleString()),
        h('span', null, visit.status),
        visit.cancellation_status && h('span', null, `Cancellation · ${visit.cancellation_status}`),
        visit.reason && h('span', null, visit.reason),
      ))) : h('p', null, 'No matching appointments.'),
      section.has_more && h('small', null, 'Showing the first 20 matching appointments.'),
    )),
    result.patients && (result.patients.length
      ? h('div', { className: 'ai-prompts' }, result.patients.map((patient) => h('button', {
        key: patient.id, type: 'button', disabled, onClick: () => onSelect(patient.id),
      }, patient.name)))
      : h('p', null, 'No assigned patients.')),
    result.has_more && h('small', null, 'Showing the first 20 patients. Ask for a patient by full name.'),
  )
}
