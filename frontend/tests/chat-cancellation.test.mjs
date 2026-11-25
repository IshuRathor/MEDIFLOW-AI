import assert from 'node:assert/strict'
import { test } from 'node:test'
import { renderToStaticMarkup } from 'react-dom/server'
import ChatCancellation from '../src/ChatCancellation.js'
import { restoreConversationState } from '../src/aiConversationState.js'

const appointment = {
  id: 918273,
  doctor_name: 'Asha Rao',
  specialization: 'Cardiology',
  appointment_date: '2030-07-12T11:30:00',
  status: 'Scheduled',
}
const props = { disabled: false, canConfirm: false, onSelect() {}, onDecision() {} }

test('cancellation cards show the appointment details without rendering its internal ID', () => {
  const html = renderToStaticMarkup(ChatCancellation({ ...props, data: { cancellation_options: [appointment] } }))
  assert.match(html, /Dr\. Asha Rao/)
  assert.match(html, /Cardiology/)
  assert.match(html, /Scheduled/)
  assert.ok(html.includes(new Date(appointment.appointment_date).toLocaleDateString()))
  assert.match(html, /11:30/)
  assert.match(html, /Select appointment/)
  assert.doesNotMatch(html, /918273|Confirm cancellation request/)
  assert.equal(ChatCancellation({ ...props, data: { cancellation_options: [] } }), null)
})

test('selection and explicit confirmation use separate callbacks', () => {
  const selections = []
  const decisions = []
  const actions = {
    ...props,
    onSelect: (id) => selections.push(id),
    onDecision: (decision) => decisions.push(decision),
  }
  const picker = ChatCancellation({ ...actions, data: { cancellation_options: [appointment] } })
  picker.props.children[0].props.children[1].props.onClick()
  assert.deepEqual(selections, [appointment.id])
  assert.deepEqual(decisions, [])

  const data = { cancellation_selection: appointment }
  assert.equal(ChatCancellation({ ...actions, data }), null)
  const confirmation = ChatCancellation({ ...actions, data, canConfirm: true })
  const buttons = confirmation.props.children[1].props.children
  assert.equal(buttons[0].props.children, 'Confirm cancellation request')
  buttons[0].props.onClick()
  buttons[1].props.onClick()
  assert.deepEqual(decisions, ['approve', 'reject'])

  const disabled = renderToStaticMarkup(ChatCancellation({ ...actions, data, canConfirm: true, disabled: true }))
  assert.match(disabled, /disabled=""/)
  assert.doesNotMatch(disabled, /918273/)
})

test('restoration keeps cancellation selection and confirmation distinct from booking', () => {
  const action = 'request_appointment_cancellation'
  const snapshot = {
    conversation_id: 'saved-cancellation',
    messages: [{ role: 'assistant', content: 'Do you want to send a cancellation request to your doctor?' }],
    last_response: {
      agent: 'Hospital Operations Agent',
      status: 'approval_required',
      data: { cancellation_selection: appointment },
    },
    pending_approval: { id: 'confirmation', action },
  }
  const restored = restoreConversationState(snapshot)
  assert.equal(restored.selectedDoctor, null)
  assert.equal(restored.response.approval_id, 'confirmation')
  assert.equal(restored.response.data.cancellation_selection, appointment)
  assert.equal(restored.response.trace[0].tool, action)

  const completed = restoreConversationState({
    ...snapshot,
    messages: [...snapshot.messages, { role: 'assistant', content: 'Cancellation request submitted. Pending Doctor Approval.' }],
    last_response: null,
    pending_approval: null,
  })
  assert.equal(completed.response.approval_id, null)
  assert.match(completed.response.message, /Pending Doctor Approval/)
})
