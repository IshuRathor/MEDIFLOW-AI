import type { ReactElement } from 'react'
import type { TriageDoctor, TriageResponse } from './api'

export default function TriageResults(props: {
  result: TriageResponse
  onBook: (doctor: TriageDoctor) => void
  onReset: () => void
}): ReactElement
