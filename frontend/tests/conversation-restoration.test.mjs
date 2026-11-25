import test from 'node:test'
import assert from 'node:assert/strict'

import { restoreConversationState, startNewConversationState } from '../src/aiConversationState.js'

test('restores the latest conversation and pending booking confirmation', () => {
  const restored = restoreConversationState({
    conversation_id: 'conversation-1',
    messages: [
      { role: 'user', content: 'I want an appointment with Dr Rao' },
      { role: 'assistant', content: 'Which date would you prefer?' },
      { role: 'user', content: '2026-12-04 at 10 AM' },
      { role: 'assistant', content: 'Review and confirm the appointment request.' },
    ],
    last_response: {
      status: 'approval_required',
      agent: 'Hospital Operations Agent',
      data: { doctor: { id: 3, name: 'Dr Rao' }, date: '2026-12-04', time: '10:30' },
      trace: [{ tool: 'create_appointment', status: 'approval_required', duration_ms: 0 }],
    },
    pending_approval: { id: 'approval-1', action: 'create_appointment', expires_at: '2026-12-01T10:10:00+00:00' },
    expired_approval: false,
  })

  assert.equal(restored.conversationId, 'conversation-1')
  assert.equal(restored.messages.length, 4)
  assert.equal(restored.response.status, 'approval_required')
  assert.equal(restored.response.approval_id, 'approval-1')
  assert.equal(restored.response.data.date, '2026-12-04')
  assert.equal(restored.selectedDoctor.name, 'Dr Rao')
  assert.equal(restored.selectedDate, '2026-12-04')
  assert.equal(restored.selectedTime, '10:30')
})

test('restores completed conversations without reviving an approval', () => {
  const restored = restoreConversationState({
    conversation_id: 'conversation-2',
    messages: [
      { role: 'user', content: 'Show my appointments' },
      { role: 'assistant', content: 'Found one appointment.' },
    ],
    last_response: { status: 'completed', agent: 'Hospital Operations Agent', data: {} },
    pending_approval: null,
    expired_approval: false,
  })
  assert.equal(restored.response.status, 'completed')
  assert.equal(restored.response.approval_id, null)
  assert.equal(restored.messages[1].content, 'Found one appointment.')
})

test('expired confirmations restore as unavailable without confirmation controls', () => {
  const restored = restoreConversationState({
    conversation_id: 'conversation-expired',
    messages: [
      { role: 'user', content: 'Book an appointment' },
      { role: 'assistant', content: 'This confirmation expired. Start a new conversation to continue.' },
    ],
    last_response: { status: 'error', agent: 'Hospital Operations Agent', data: {} },
    pending_approval: null,
    expired_approval: true,
  })
  assert.equal(restored.response.status, 'error')
  assert.equal(restored.response.approval_id, null)
  assert.equal(restored.expiredApproval, true)
})

test('new conversation state does not reuse a prior conversation id or messages', () => {
  assert.deepEqual(startNewConversationState(), {
    conversationId: undefined,
    messages: [],
    response: null,
    selectedDoctor: null,
    selectedDate: '',
    selectedTime: '',
    expiredApproval: false,
  })
})
