import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const billing = readFileSync(new URL('../src/BillingWorkspace.tsx', import.meta.url), 'utf8')

test('patients can reach My Bills and receive the Finance-issued-bills empty state', () => {
  assert.match(app, /role === 'patient'\) return \['Overview', 'Billing'\]/)
  assert.match(app, /<BillingWorkspace token=\{token\} role="patient"[^>]+recentOnly/)
  assert.match(billing, /You don't have any bills yet\. Bills will appear here when the hospital's Finance team generates a bill for your services\./)
  assert.match(billing, /!patient && detail && Number\(detail\.outstanding\) > 0/)
})

test('billing confirmation uses the server review before executing an approval', () => {
  assert.match(billing, /setReview\(await reviewBill\(/)
  assert.match(billing, /setReview\(await reviewPayment\(/)
  assert.match(billing, /money\(review\.total_amount\)/)
  assert.match(billing, /decideAIApproval\(review\.approval_id, 'approve', token\)/)
  assert.match(billing, /decideAIApproval\(review\.approval_id, 'reject', token\)/)
})
