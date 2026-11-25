import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8')

test('public registration offers only Patient, Doctor and Finance Staff', () => {
  const picker = app.match(/<fieldset className="role-picker registration-role-picker">([\s\S]*?)<\/fieldset>/)
  assert.ok(picker)
  assert.deepEqual(Array.from(picker[1].matchAll(/\['(\w+)', '([^']+)'/g), ([, role, label]) => [role, label]), [
    ['patient', 'Patient'], ['clinician', 'Doctor'], ['staff', 'Finance staff'],
  ])
  assert.doesNotMatch(picker[1], /Administrator|['"]admin['"]/i)
  assert.match(api, /PublicRegistrationInput = \{[\s\S]*?role: 'patient' \| 'clinician' \| 'staff'\s/)
})

test('Administrator and other roles remain available in the login picker', () => {
  const roles = app.match(/const roleOptions:[\s\S]*?= \[([\s\S]*?)\n\]/)
  assert.ok(roles)
  assert.deepEqual(Array.from(roles[1].matchAll(/value: '(\w+)'/g), ([, value]) => value), ['admin', 'patient', 'clinician', 'staff'])
  assert.match(app, /mode === 'login' && <fieldset[^>]*>[\s\S]*?roleOptions\.map/)
})
