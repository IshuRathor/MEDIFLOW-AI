import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement as h } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import TriageResults from '../src/TriageResults.js'

const doctor = {
  id: 789654,
  name: 'Dr. Recorded',
  specialization: 'General Medicine',
  department: 'Medicine',
  experience_years: 8,
  availability: 'available',
  upcoming_slots: ['2026-11-26T13:30:00'],
  matching_explanation: 'Listed under General Medicine.',
}
const assessment = {
  urgency: 'High',
  recommended_department: 'General Medicine',
  recommended_action: 'Arrange medical evaluation.',
  safety_notice: 'Seek immediate care for life-threatening symptoms.',
  disclaimer: 'This is not a medical diagnosis.',
  availability_window_days: 14,
}
const render = (result) => renderToStaticMarkup(h(TriageResults, { result, onBook() {}, onReset() {} }))

test('renders verified recommendations, alternatives and distinct availability states', () => {
  const result = render({ ...assessment, recommended_doctors: [
    doctor,
    { ...doctor, id: 2, name: 'Dr. Busy', availability: 'no_slots', upcoming_slots: [] },
    { ...doctor, id: 3, name: 'Dr. No Schedule', availability: 'unverified', upcoming_slots: [] },
  ] })
  assert.match(result, /Next verified slot/)
  assert.match(result, /datetime="2026-11-26T13:30:00"/i)
  assert.match(result, /8 years of experience/)
  assert.match(result, /Listed under General Medicine/)
  assert.match(result, /Other matching doctors/)
  assert.match(result, /No verified open slots/)
  assert.match(result, /Availability could not be verified/)
  assert.match(result, /View booking options for Dr. Recorded/)
  assert.doesNotMatch(result, /789654/)
})

test('distinguishes a missing specialist and suppresses all booking options during emergencies', () => {
  assert.match(render({ ...assessment, recommended_department: 'Oncology', recommended_doctors: [] }), /No doctor matching Oncology is currently registered/)
  const emergency = render({ ...assessment, urgency: 'Emergency', recommended_doctors: [doctor] })
  assert.match(emergency, /role="alert"/)
  assert.doesNotMatch(emergency, /Dr. Recorded|booking options|Recommended doctors/)
})

test('chest warnings precede secondary directory information and hide slots and booking', () => {
  const assessmentWithWarning = {
    ...assessment,
    urgency: 'Emergency',
    recommended_department: 'Emergency / Cardiology',
    recommended_action: 'Call local emergency services now. Do not wait for an appointment.',
  }
  const empty = render({ ...assessmentWithWarning, recommended_doctors: [] })
  assert.match(empty, /No matching cardiologist/)
  assert.match(empty, /Do not wait for an appointment/)
  const result = render({ ...assessmentWithWarning, recommended_doctors: [{ ...doctor, specialization: 'Cardiology' }] })
  assert.match(result, /role="alert"[^>]*>Call local emergency services now/)
  assert.match(result, /Dr. Recorded/)
  assert.ok(result.indexOf('Do not wait') < result.indexOf('Dr. Recorded'))
  assert.doesNotMatch(result, /booking options|Next verified slot/)
})

test('booking options pass the selected directory record to the existing booking flow', () => {
  let selected
  const view = TriageResults({
    result: { ...assessment, recommended_doctors: [doctor] },
    onBook: (record) => { selected = record },
    onReset() {},
  })
  const section = view.props.children.find((child) => child?.type === 'section')
  const recommendation = section.props.children.find((child) => child?.type === 'ul').props.children
  const row = recommendation.type(recommendation.props)
  row.props.children.find((child) => child.type === 'button').props.onClick()
  assert.equal(selected, doctor)
})
