import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

test('the dashboard triage button is exclusive to the authenticated patient role', () => {
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const header = app.match(/<header className="topbar">[\s\S]*?<\/header>/)?.[0] ?? ''
  const gate = header.match(/\{currentUser\?\.role === '(\w+)' && <button[^{}]*onClick=\{\(\) => setTriageOpen\(true\)\}>\+ New triage<\/button>\}/)
  assert.ok(gate, 'the button must use an exact authenticated role check')
  for (const [role, visible] of [['patient', true], ['clinician', false], ['staff', false], ['admin', false]]) {
    assert.equal(role === gate[1], visible, role)
  }
  assert.equal((app.match(/\+ New triage/g) ?? []).length, 1)
})
