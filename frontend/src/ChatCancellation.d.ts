import type { ReactElement } from 'react'

export default function ChatCancellation(props: {
  data: Record<string, unknown>
  disabled: boolean
  canConfirm: boolean
  onSelect: (id: number) => void
  onDecision: (decision: 'approve' | 'reject') => void
}): ReactElement | null
