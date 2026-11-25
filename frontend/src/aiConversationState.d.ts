import type { ChatResponse, ConversationMessage, LatestConversation } from './api'

export function restoreConversationState(snapshot: LatestConversation): {
  conversationId: string | undefined
  messages: ConversationMessage[]
  response: ChatResponse | null
  selectedDoctor: Record<string, unknown> | null
  selectedDate: string
  selectedTime: string
  expiredApproval: boolean
}

export function startNewConversationState(): {
  conversationId: undefined
  messages: ConversationMessage[]
  response: null
  selectedDoctor: null
  selectedDate: ''
  selectedTime: ''
  expiredApproval: false
}
