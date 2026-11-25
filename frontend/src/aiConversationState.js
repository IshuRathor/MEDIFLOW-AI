export function restoreConversationState(snapshot) {
  const messages = Array.isArray(snapshot?.messages) ? snapshot.messages : []
  const conversationId = typeof snapshot?.conversation_id === 'string' ? snapshot.conversation_id : undefined
  const lastAssistant = [...messages].reverse().find((message) => message.role === 'assistant')
  const pendingApproval = snapshot?.pending_approval ?? null
  const stored = snapshot?.last_response ?? null

  if (!conversationId || !lastAssistant) {
    return {
      conversationId,
      messages,
      response: null,
      selectedDoctor: null,
      selectedDate: '',
      selectedTime: '',
      expiredApproval: Boolean(snapshot?.expired_approval),
    }
  }

  const trace = Array.isArray(stored?.trace) ? [...stored.trace] : []
  if (pendingApproval && !trace.some((item) => item.tool === pendingApproval.action)) {
    trace.push({ tool: pendingApproval.action, status: 'approval_required', duration_ms: 0 })
  }
  const data = stored?.data && typeof stored.data === 'object' ? stored.data : {}
  const doctor = data.doctor && typeof data.doctor === 'object' ? data.doctor : null
  const selectedDate = typeof data.date === 'string' ? data.date.slice(0, 10) : ''
  const selectedTime = typeof data.time === 'string' ? data.time.slice(0, 5) : ''

  return {
    conversationId,
    messages,
    response: {
      conversation_id: conversationId,
      agent: stored?.agent ?? 'MediFlow AI',
      status: pendingApproval ? 'approval_required' : snapshot?.expired_approval ? 'error' : stored?.status ?? 'completed',
      message: lastAssistant.content,
      data,
      trace,
      approval_id: pendingApproval?.id ?? null,
    },
    selectedDoctor: doctor,
    selectedDate,
    selectedTime,
    expiredApproval: Boolean(snapshot?.expired_approval),
  }
}

export function startNewConversationState() {
  return {
    conversationId: undefined,
    messages: [],
    response: null,
    selectedDoctor: null,
    selectedDate: '',
    selectedTime: '',
    expiredApproval: false,
  }
}
