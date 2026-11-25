import assert from 'node:assert/strict'
import { test } from 'node:test'
import { renderToStaticMarkup } from 'react-dom/server'
import DoctorSelectionCards, { patientDoctorOptions, visibleChatTrace } from '../src/DoctorSelectionCards.js'

const doctor = { id: 17, name: 'Asha Rao', specialization: 'Cardiology', department: 'Heart Care' }

test('doctor cards render patient-safe names, specialties, departments and selection action', () => {
  const html = renderToStaticMarkup(DoctorSelectionCards({ doctors: [doctor], onSelect() {} }))

  assert.match(html, /Dr\. Asha Rao/)
  assert.match(html, /Cardiology/)
  assert.match(html, /Heart Care/)
  assert.match(html, /Select Doctor/)
  assert.doesNotMatch(html, /17/)
})

test('doctor result adapter accepts direct API data and nested tool results', () => {
  assert.deepEqual(patientDoctorOptions({ doctors: [doctor] }), [doctor])
  assert.deepEqual(patientDoctorOptions({
    tool_results: [{ tool: 'search_doctors', result: { doctors: [doctor] } }],
  }), [doctor])
})

test('selecting a doctor invokes the conversation continuation callback', () => {
  let selected
  const tree = DoctorSelectionCards({ doctors: [doctor], onSelect: (item) => { selected = item } })
  const card = tree.props.children[0]
  const button = card.props.children[1]
  button.props.onClick()

  assert.equal(selected, doctor)
})

test('patient chat hides internal traces while staff debugging can retain them', () => {
  const trace = [{ tool: 'search_doctors', status: 'success' }]
  assert.equal(visibleChatTrace('patient', trace), null)
  assert.equal(visibleChatTrace('admin', trace), 'search_doctors: success')
})
